import json
import os
import shutil
import tempfile
import time
from uuid import uuid4

import ansible_runner

_CONNECTION_PLUGIN_DIR = f'{os.path.dirname(__file__)}/connection_plugins/'

class AoHError(Exception):
    """Raised for AoC-specific errors."""


class AoHRunner:
    def __init__(self, config, playbook, host):
        self.id = str(uuid4())
        self._dir = tempfile.mkdtemp()
        self._LOGS_PATH = f'{self._dir}/artifacts/{self.id}/stdout'
        self._RECVBUF_PATH = f'{self._dir}/recvbuf'
        self._SENDBUF_PATH = f'{self._dir}/sendbuf'
        self._sendbuf = None
        self._recvbuf = None
        self._logs = None
        self._thread = None
        self._runner = None

        try:
            self._start_runner(config, playbook, host)

            # We assume that ansible-runner will eventually create its log file
            while not os.path.exists(self._LOGS_PATH):
                time.sleep(0.1)
            self._logs = open(self._LOGS_PATH, 'r')  # noqa: SIM115

            # The FIFO buffers may not get created if Ansible crashes/exits
            # before calling the AoH connection plugin
            while not os.path.exists(self._SENDBUF_PATH) and \
                    not self._runner_finished():
                time.sleep(0.1)
            if os.path.exists(self._RECVBUF_PATH):
                # Note that recvbuf is created first, so sendbuf will exist too
                self._recvbuf = open(self._RECVBUF_PATH, 'w')  # noqa: SIM115
                self._sendbuf = open(self._SENDBUF_PATH, 'r')  # noqa: SIM115
        except:
            self.teardown()
            raise


    def _start_runner(self, config, playbook, host):
        raw_config = ansible_runner.get_ansible_config(
            'dump',
            config,
            private_data_dir=self._dir,
            quiet=True,
        )[0]

        connection_plugins = eval(next(
            x for x in raw_config.split('\n')
            if x.startswith('DEFAULT_CONNECTION_PLUGIN_PATH')
        ).split('= ')[1])

        env = {
            'ANSIBLE_CONNECTION_PLUGINS': ':'.join(
                [_CONNECTION_PLUGIN_DIR] + connection_plugins
            ),
            'ANSIBLE_CONFIG': config,
        }
        vars = {
            'ansible_aoh_dir': self._dir,
            'ansible_connection': 'aoh',
        }

        self._thread, self._runner = ansible_runner.run_async(
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
        assert self._runner is not None
        return self._runner.status not in ['starting', 'running']


    def process_client_request(self, req):
        res = {}

        # We check runner status first, in case new logs come in afterwards
        res['finished'] = self._runner_finished()
        assert self._logs is not None
        res['logs'] = self._logs.read()

        try:
            if req and self._recvbuf:
                self._recvbuf.write(json.dumps(req) + '\n')
                self._recvbuf.flush()

            if self._sendbuf:
                line = self._sendbuf.readline()
                for key, val in json.loads(line or '{}').items():
                    res[key] = val
        except Exception as e:
            # This is probably a broken pipe, which indicates a fatal error.
            # Then Ansible should exit soon.
            if 'Broken pipe' not in str(e):
                raise

        return res


    def teardown(self):
        self.id = None
        if self._logs:
            self._logs.close()
        if self._recvbuf:
            self._recvbuf.close()
        if self._sendbuf:
            try:
                # Send an error in case the AoH connection plugin is currently
                # blocking on a read
                self._sendbuf.write('{"err":"Runner teardown"}\n')
                self._sendbuf.flush()
            except Exception:  # noqa: BLE001, S110
                pass
            self._sendbuf.close()

        if self._thread:
            # The Ansible runner *should* exit if it hasn't already due to a
            # broken recvbuf pipe or the sendbuf error.
            self._thread.join(10)
            if self._thread.is_alive():
                raise AoHError('Ansible runner thread not terminated')

        shutil.rmtree(self._dir)
