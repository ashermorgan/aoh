import os

import yaml
from flask import Flask, abort, make_response, render_template, request, session
from flask_apscheduler import APScheduler

from .runner import AoHRunner

_RUNNERS = {}
_LAST_GC = 0
_GC_INTERVAL = 60 # 1 minute

app = Flask(__name__, template_folder=os.path.dirname(__file__))
app.secret_key = os.urandom(16)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()


@scheduler.task('interval', seconds=_GC_INTERVAL)
def gc():
    """Teardown and delete timed-out runners."""

    runners = list(_RUNNERS.items())
    for id, runner in runners:
        if runner and runner.has_timed_out():
            runner.teardown()
            _RUNNERS.pop(id, None)


def _get_opts(cmdline):
    opts = []
    for arg in cmdline.split():
        if arg.startswith('--'):
            opts += [arg.split('=')[0]]
        elif arg.startswith('-'):
            for opt in arg.split('=')[0][1:]:
                opts += ['-' + opt]
    return opts


def _validate_args(cmdline):
    # Reject any sign of Jinja expressions
    if '{{' in cmdline or '{%' in cmdline:
        return False

    # Enforce whitelisted options. Other options either might not be supported
    # yet, or may pose security risks.
    OPT_WHITELIST = [
        '--check', '-C',
        '--diff', '-D',
        '--extra-vars', '-e',
        '--help', '-h',
        '--limit', '-l',
        '--list-tags',
        '--skip-tags',
        '--start-at-task',
        '--step',
        '--tags', '-t',
        '--verbose', '-v',
        '--version',
    ]
    for opt in _get_opts(cmdline):
        if opt not in OPT_WHITELIST:
            print('bad', opt)
            return False

    return True


@app.get('/install')
@app.get('/install.py')
def install():
    return render_template('install.py', API_URL=request.host_url[:-1])


@app.post('/runners/')
def job_new():
    if not _validate_args(request.json['args']):
        return { 'err': 'Bad or banned arguments passed.' }, 400

    with open('config.yml', 'r') as f:
        CONFIG = yaml.safe_load(f)

    playbook = CONFIG.get(request.json['playbook'])
    if not playbook:
        return { 'err': f"Playbook not found: {request.json['playbook']}" }, 400

    runner = AoHRunner(playbook['config'], playbook['playbook'],
                       request.json['host'], request.json['args'])

    _RUNNERS[runner.id] = runner
    session['runner'] = runner.id

    return make_response('', 201, {'Location': f'/runners/{runner.id}'})


@app.put('/runners/<id>')
def job_status(id):
    if id != session.get('runner'):
        abort(401)

    runner = _RUNNERS.get(id)
    if not runner:
        abort(400)

    res = runner.process_client_request(request.json)

    if res['finished']:
        runner.teardown()
        _RUNNERS.pop(id, None)

    return res
