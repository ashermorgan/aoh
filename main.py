import json
import os

import ansible_runner
from flask import Flask, abort, make_response, request, send_file, session
from uuid import uuid4


DATA = {}
PLAYBOOK = os.path.abspath('./demo/playbook.yml') # TODO
PRIVATE_DIR = os.path.abspath('./private/') # TODO

app = Flask(__name__)
app.secret_key = os.urandom(16) # TODO


@app.get('/install')
@app.get('/install.py')
def install():
    return send_file('install.py')


@app.post('/runners/')
def job_new():
    id = str(uuid4())

    inv = {
        'all': {
            'hosts': {
                request.json['host']: {
                    'ansible_connection': 'http',
                    'ansible_http_runner': f'{PRIVATE_DIR}/artifacts/{id}',
                },
            },
        },
    }
    env = {
        'ANSIBLE_CONNECTION_PLUGINS': ':'.join([
            os.path.abspath('./connection_plugins/'), # TODO
            # Default paths:
            'demo/plugins/connection', # TODO
            '/usr/share/ansible/plugins/connection',
        ])
    }
    os.makedirs(f'{PRIVATE_DIR}/artifacts/{id}/')
    os.mkfifo(f'{PRIVATE_DIR}/artifacts/{id}/sendbuf')
    os.mkfifo(f'{PRIVATE_DIR}/artifacts/{id}/recvbuf')
    _, r = ansible_runner.run_async(private_data_dir=PRIVATE_DIR,
                                    limit=request.json['host'],
                                    inventory=inv,
                                    envvars=env,
                                    playbook=PLAYBOOK,
                                    ident=id,
                                    verbosity=3
                                    )
    sendbuf = open(f'{PRIVATE_DIR}/artifacts/{id}/sendbuf', 'r')
    recvbuf = open(f'{PRIVATE_DIR}/artifacts/{id}/recvbuf', 'w')
    DATA[id] = {
        'runner': r,
        'sendbuf': sendbuf,
        'recvbuf': recvbuf,
    }
    session['runner'] = id

    return make_response('', 201, {'Location': f'/runners/{id}'})


@app.put('/runners/<id>')
def job_status(id):
    if id != session.get('runner'):
        abort(401)

    data = request.json
    if data:
        DATA[id]['recvbuf'].write(json.dumps(data) + '\n')
        DATA[id]['recvbuf'].flush()

    sendline = DATA[id]['sendbuf'].readline()
    if sendline:
        res = json.loads(sendline)
    else:
        res = {}

    res['status'] = DATA[id]['runner'].status

    return res


if __name__ == '__main__':
    app.run(debug=True)
