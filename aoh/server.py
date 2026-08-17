import os

from flask import Flask, abort, make_response, render_template, request, session

from .runner import AoHRunner

PLAYBOOK = os.path.abspath('./demo/playbook.yml') # TODO
CONFIG = os.path.abspath('./demo/ansible.cfg') # TODO

app = Flask(__name__, template_folder=os.path.dirname(__file__))
app.secret_key = os.urandom(16)

_DATA = {}


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

    runner = AoHRunner(CONFIG, PLAYBOOK, request.json['args'])

    _DATA[runner.id] = runner
    session['runner'] = runner.id

    return make_response('', 201, {'Location': f'/runners/{runner.id}'})


@app.put('/runners/<id>')
def job_status(id):
    if id != session.get('runner'):
        abort(401)

    res = _DATA[id].process_client_request(request.json)

    if res['finished']:
        _DATA[id].teardown()
        del _DATA[id]

    return res
