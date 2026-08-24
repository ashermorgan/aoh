import os

from flask import Flask, make_response, render_template, request, session
from flask_apscheduler import APScheduler

from .playbook import get_playbook
from .runner import Runner

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
    return render_template('client.py', API_URL=request.host_url[:-1])


@app.post('/runners/')
def new_runner():
    playbook = get_playbook(request.json['playbook'])
    if not playbook:
        return { 'err': f"Playbook not found: {request.json['playbook']}" }, 400

    if not playbook.validate_args(request.json['args']):
        return { 'err': 'Bad or banned arguments passed.' }, 400

    exp_pw_types = playbook.get_required_passwords(request.json['args'])
    act_pws = request.json.get('passwords', {})
    missing_pw_types = [pw_type for pw_type in exp_pw_types if pw_type not in
                        act_pws]
    if missing_pw_types:
        return {
            'err': f"Missing required passwords: {', '.join(missing_pw_types)}",
            'passwords': exp_pw_types,
        }, 401

    runner = Runner(playbook, request.json['host'], request.json['args'],
                    act_pws)

    _RUNNERS[runner.id] = runner
    session['runner'] = runner.id

    return make_response({}, 201, {'Location': f'/runners/{runner.id}'})


@app.put('/runners/<id>')
def runner_update(id):
    if id != session.get('runner'):
        return make_response({
            'err': 'Invalid runner ID',
        }, 401)

    runner = _RUNNERS.get(id)
    if not runner:
        return make_response({
            'err': 'Runner not found',
        }, 404)

    res = runner.process_client_request(request.json)

    if res['finished']:
        runner.teardown()
        _RUNNERS.pop(id, None)

    return res
