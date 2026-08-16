import os

from flask import Flask, abort, make_response, render_template, request, session

from .runner import AoHRunner

PLAYBOOK = os.path.abspath('./demo/playbook.yml') # TODO
CONFIG = os.path.abspath('./demo/ansible.cfg') # TODO

app = Flask(__name__, template_folder=os.path.dirname(__file__))
app.secret_key = os.urandom(16)

_DATA = {}


@app.get('/install')
@app.get('/install.py')
def install():
    return render_template('install.py', API_URL=request.host_url[:-1])


@app.post('/runners/')
def job_new():
    runner = AoHRunner(CONFIG, PLAYBOOK, request.json['host'])

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
