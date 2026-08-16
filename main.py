import json
import os
import shutil
import tempfile

import ansible_runner
from flask import Flask, abort, make_response, request, send_file, session
from uuid import uuid4


DATA = {}
PLAYBOOK = os.path.abspath('./demo/playbook.yml') # TODO
CONFIG = os.path.abspath('./demo/ansible.cfg') # TODO

app = Flask(__name__)
app.secret_key = os.urandom(16)


class Runner:
    def __init__(self, config, playbook, host):
        self.id = str(uuid4())
        self.dir = tempfile.mkdtemp()

        os.mkfifo(f'{self.dir}/sendbuf')
        os.mkfifo(f'{self.dir}/recvbuf')

        self._start(config, playbook, host)

        self.sendbuf = open(f'{self.dir}/sendbuf', 'r')
        self.recvbuf = open(f'{self.dir}/recvbuf', 'w')
        self.logs = open(f'{self.dir}/artifacts/{self.id}/stdout', 'r')


    def _start(self, config, playbook, host):
        raw_config = ansible_runner.get_ansible_config('dump', config,
                                                       quiet=True)[0]

        connection_plugins = eval([
            x for x in raw_config.split('\n')
            if x.startswith('DEFAULT_CONNECTION_PLUGIN_PATH')
        ][0].split('= ')[1])

        env = {
            'ANSIBLE_CONNECTION_PLUGINS': ':'.join(
                [os.path.abspath('./connection_plugins/')]
                + connection_plugins
            ),
            'ANSIBLE_CONFIG': config,
        }
        vars = {
            'ansible_http_runner': self.dir,
            'ansible_connection': 'http',
        }

        self.thread, self.runner = ansible_runner.run_async(
            private_data_dir=self.dir,
            ident=self.id,
            envvars=env,
            extravars=vars,

            playbook=playbook,
            limit=host,

            # verbosity=3,
            quiet=True,
            suppress_env_files=True,
        )


    def teardown(self):
        self.thread.join()
        self.id = None
        self.sendbuf.close()
        self.recvbuf.close()
        self.logs.close()
        shutil.rmtree(self.dir)


@app.get('/install')
@app.get('/install.py')
def install():
    return send_file('install.py')


@app.post('/runners/')
def job_new():
    runner = Runner(CONFIG, PLAYBOOK, request.json['host'])

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
    res['logs'] = runner.logs.read()

    if runner.runner.status not in ['started', 'running']:
        runner.teardown()
        del DATA[id]

    return res


if __name__ == '__main__':
    app.run(debug=True)
