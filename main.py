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
        self._dir = tempfile.mkdtemp()
        self._SENDBUF_PATH = f'{self._dir}/sendbuf'
        self._RECVBUF_PATH = f'{self._dir}/recvbuf'
        self._LOGS_PATH = f'{self._dir}/artifacts/{self.id}/stdout'

        os.mkfifo(self._SENDBUF_PATH)
        os.mkfifo(self._RECVBUF_PATH)

        self._start(config, playbook, host)

        self._sendbuf = open(self._SENDBUF_PATH, 'r')
        self._recvbuf = open(self._RECVBUF_PATH, 'w')
        self._logs = open(self._LOGS_PATH, 'r')


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
            'ansible_http_runner': self._dir,
            'ansible_connection': 'http',
        }

        self.thread, self.runner = ansible_runner.run_async(
            private_data_dir=self._dir,
            ident=self.id,
            envvars=env,
            extravars=vars,

            playbook=playbook,
            limit=host,

            # verbosity=3,
            quiet=True,
            suppress_env_files=True,
        )


    def _runner_finished(self):
        return self.runner.status not in ['started', 'running']


    def process_client_request(self, req):
        res = {}

        # We check runner status first, in case new logs come in afterwards
        res['finished'] = self._runner_finished()
        res['logs'] = self._logs.read()

        if req:
            self._recvbuf.write(json.dumps(req) + '\n')
            self._recvbuf.flush()

        line = self._sendbuf.readline()
        for key, val in json.loads(line or '{}').items():
            res[key] = val

        return res


    def teardown(self):
        self.thread.join()
        self.id = None
        self._sendbuf.close()
        self._recvbuf.close()
        self._logs.close()
        shutil.rmtree(self._dir)


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

    res = DATA[id].process_client_request(request.json)

    if res['finished']:
        DATA[id].teardown()
        del DATA[id]

    return res


if __name__ == '__main__':
    app.run(debug=True)
