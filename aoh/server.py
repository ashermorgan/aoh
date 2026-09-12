import logging
import os

from flask import Flask, abort, render_template, request, session
from flask_apscheduler import APScheduler

from aoh.config import AOH_MAX_RUNNERS, AOH_ORIGIN
from aoh.playbook import PlaybookFileError, get_playbook
from aoh.runner import Runner, RunnerError
from aoh.security import (
    PasswordFileError,
    get_required_passwords,
    validate_aoh_password,
    validate_args,
)

_RUNNERS = {}

# Every 60s, tear down runners that finished more than 60s ago
_GC_INTERVAL = 60
_GC_THRESHOLD = 60

app = Flask(__name__)
app.secret_key = os.urandom(16)

scheduler = APScheduler()
scheduler.init_app(app)

logger = logging.getLogger(__name__)


@scheduler.task('interval', seconds=_GC_INTERVAL)
def gc():
    """Tear down and delete timed-out runners."""

    runners = list(_RUNNERS.items())
    for id, runner in runners:
        if runner and runner.has_timed_out(_GC_THRESHOLD):
            logger.info(f'{runner.playbook.name} (#{id[:8]}): Runner torn down '
                        'due to inactivity')
            runner.teardown()
            _RUNNERS.pop(id, None)


@app.context_processor
def inject_stage_and_region():
    return {
        'AOH_ORIGIN': AOH_ORIGIN or request.host_url[:-1]
    }


@app.errorhandler(PasswordFileError)
@app.errorhandler(PlaybookFileError)
@app.errorhandler(RunnerError)
def error(e):
    path = (request.view_args or {}).get('path', '')
    short_id = (request.view_args or {}).get('short_id')
    if path and short_id:
        prefix = f'{path} (#{short_id}): '
    elif path:
        prefix = f'{path}: '
    else:
        prefix = ''

    logger.error(prefix + str(e))
    return {'msg': 'Internal server error'}, 500


@app.get('/run')
@app.get('/run.py')
def install():
    return render_template('client.py')


@app.post('/runners/<path:path>')
def new_runner(path):
    playbook = get_playbook(path)
    if not playbook:
        return {'err': f'Playbook not found: {path}'}, 400

    if AOH_MAX_RUNNERS != 0 and len(_RUNNERS) >= AOH_MAX_RUNNERS:
        logger.info(f'{path}: No runners available')
        return {'err': 'No runners available'}, 503

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
        logger.info(f'{path}: Received incorrect password')
        return {'err': 'Incorrect AoH password'}, 401
    act_pws.pop('aoh_password', None) # Don't pass AoH password on to runner

    if not validate_args(playbook, request.json['args']):
        logger.info(f"{path}: Received bad arguments: {request.json['args']}")
        return {'err': 'Bad or banned arguments passed'}, 400

    runner = Runner(playbook, request.json['host'], request.json['args'],
                    act_pws)

    assert runner.id is not None
    _RUNNERS[runner.id] = runner
    session['runner'] = runner.id
    short_id = runner.id[:8]

    logger.info(f'{path} (#{short_id}): Created runner')

    return {}, 201, {'Location': f'/runners/{path}/{short_id}'}


@app.put('/runners/<path:path>/<short_id>')
def runner_update(path, short_id):
    id = session.get('runner')
    if not id or not id.startswith(short_id):
        return {'err': 'Invalid runner ID'}, 404

    runner = _RUNNERS.get(id)
    if not runner:
        # Runner must have existed at some point, so likely a client timeout
        return {'err': 'Runner torn down. Maybe the client timed out?'}, 200
    if runner.playbook.name != path:
        return {'err': f'Playbook not found: {path}'}, 400

    logger.debug(f'{path} (#{short_id}): Received client message')
    res = runner.process_message(request.json)

    if res['finished']:
        logger.info(f'{runner.playbook.name} (#{short_id}): Runner torn down '
                    'due to completion')
        runner.teardown()
        _RUNNERS.pop(id, None)

    return res


@app.get('/')
@app.get('/<path:path>')
def web(path='main.yml'):
    playbook = get_playbook(path)
    if not playbook or playbook.web_description is None:
        return abort(404)

    is_windows = 'indows' in request.headers.get('User-Agent', '')

    return render_template('home.html', description=playbook.web_description,
                           playbook=playbook.name, is_windows=is_windows)
