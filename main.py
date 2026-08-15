import json
import os
import shutil
import tempfile

import ansible_runner
from flask import Flask, abort, make_response, request, send_file, session
from uuid import uuid4


DATA = {}
PLAYBOOK = os.path.abspath('./demo/playbook.yml') # TODO

app = Flask(__name__)
app.secret_key = os.urandom(16)


class Runner:
    def __init__(self, host, playbook):
        self.id = str(uuid4())
        self.dir = tempfile.mkdtemp()

        os.mkfifo(f'{self.dir}/sendbuf')
        os.mkfifo(f'{self.dir}/recvbuf')

        self._start(host, playbook)

        self.sendbuf = open(f'{self.dir}/sendbuf', 'r')
        self.recvbuf = open(f'{self.dir}/recvbuf', 'w')

    def _start(self, host, playbook):
        inv = {
            'all': {
                'hosts': {
                    host: {
                        'ansible_connection': 'http',
                        'ansible_http_runner': self.dir,
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

        self.thread, self.runner = ansible_runner.run_async(
            private_data_dir=self.dir,
            limit=host,
            inventory=inv,
            envvars=env,
            playbook=playbook,
            ident=self.id,
            verbosity=3
        )

    def teardown(self):
        self.thread.join()
        self.id = None
        self.sendbuf.close()
        self.recvbuf.close()
        shutil.rmtree(self.dir)


@app.get('/install')
@app.get('/install.py')
def install():
    return send_file('install.py')


@app.post('/runners/')
def job_new():
    runner = Runner(request.json['host'], PLAYBOOK)

    DATA[runner.id] = runner
    session['runner'] = runner.id

    return make_response('', 201, {'Location': f'/runners/{runner.id}'})


@app.put('/runners/<id>')
def job_status(id):
    if id != session.get('runner'):
        abort(401)
    runner = DATA[id]

    if request.json:
        runner.recvbuf.write(json.dumps(request.json) + '\n')
        runner.recvbuf.flush()

    res = json.loads(runner.sendbuf.readline() or '{}')
    res['status'] = runner.runner.status

    if runner.runner.status not in ['started', 'running']:
        runner.teardown()
        del DATA[id]

    return res


if __name__ == '__main__':
    app.run(debug=True)
