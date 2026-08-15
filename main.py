import os

import ansible_runner
from flask import Flask, abort, make_response, request, send_file, session
from uuid import uuid4


DATA = {}
PLAYBOOK = os.path.abspath('./demo/playbook.yml') # TODO

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
                    'ansible_http_runner': id,
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
    _, r = ansible_runner.run_async(private_data_dir='private',
                                    limit=request.json['host'],
                                    inventory=inv,
                                    envvars=env,
                                    playbook=PLAYBOOK,
                                    ident=id,
                                    verbosity=4
                                    )
    DATA[id] = r
    session['runner'] = id

    return make_response('', 201, {'Location': f'/runners/{id}'})


@app.route('/runners/<id>')
def job_status(id):
    if id != session.get('runner'):
        abort(401)

    return {
        'status': DATA[id].status,
    }


if __name__ == '__main__':
    app.run(debug=True)
