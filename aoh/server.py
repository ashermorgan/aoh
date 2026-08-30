import os

from flask import Flask, render_template, request, session
from flask_apscheduler import APScheduler

from .playbook import get_playbook
from .runner import Runner
from .security import *

_RUNNERS = {}
_GC_INTERVAL = 60 # 1 minute

app = Flask(__name__, template_folder=os.path.dirname(__file__))
app.secret_key = os.urandom(16)

scheduler = APScheduler()
scheduler.init_app(app)


@scheduler.task('interval', seconds=_GC_INTERVAL)
def gc():
    """Teardown and delete timed-out runners."""

    runners = list(_RUNNERS.items())
    for id, runner in runners:
        if runner and runner.has_timed_out():
            runner.teardown()
            _RUNNERS.pop(id, None)


@app.get('/run')
@app.get('/run.py')
def install():
    api_url = os.getenv('AOH_ORIGIN', request.host_url[:-1])
    return render_template('client.py', API_URL=api_url)


@app.post('/runners/<path:path>')
def new_runner(path):
    playbook = get_playbook(path)
    if not playbook:
        return { 'err': f"Playbook not found: {path}" }, 400

    if not validate_args(playbook, request.json['args']):
        return { 'err': 'Bad or banned arguments passed.' }, 400

    exp_pw_types = get_required_passwords(playbook, request.json['args'])
    act_pws = request.json.get('passwords', {})
    missing_pw_types = [pw_type for pw_type in exp_pw_types if pw_type not in
                        act_pws]
    if missing_pw_types:
        return {
            'err': f"Missing required passwords: {', '.join(missing_pw_types)}",
            'passwords': exp_pw_types,
        }, 401

    if not validate_aoh_password(playbook, act_pws.get('aoh_password')):
        return { 'err': 'Incorrect AoH password.' }, 401
    act_pws.pop('aoh_password', None) # Don't pass AoH password on to runner

    runner = Runner(playbook, request.json['host'], request.json['args'],
                    act_pws)

    assert runner.id is not None
    _RUNNERS[runner.id] = runner
    session['runner'] = runner.id
    short_id = runner.id.split('-')[0]

    return {}, 201, {'Location': f'/runners/{path}/{short_id}'}


@app.put('/runners/<path:path>/<short_id>')
def runner_update(path, short_id):
    id = session.get('runner')
    if not id or not id.startswith(short_id):
        return { 'err': 'Invalid runner ID' }, 401

    runner = _RUNNERS.get(id)
    if not runner:
        return { 'err': 'Runner not found' }, 404
    if runner.playbook.name != path:
        return { 'err': f"Playbook not found: {path}" }, 400

    res = runner.process_client_request(request.json)

    if res['finished']:
        runner.teardown()
        _RUNNERS.pop(id, None)

    return res
