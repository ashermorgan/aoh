import json
import os
import shutil
import tempfile
import time
from threading import Lock
from uuid import uuid4

import ansible_runner

_CONNECTION_PLUGIN_DIR = f'{os.path.dirname(__file__)}/connection_plugins/'
_CLIENT_TIMEOUT = 600 # 10 minutes

class AoHError(Exception):
    """Raised for AoH-specific errors."""


class AoHRunner:
    """An Ansible-over-HTTP playbook runner."""

    def __init__(self, config, playbook, host, args):
        """Create a new AoH runner."""

        self.id = str(uuid4()) # Runner ID (set to None after teardown)

        self._lock = Lock() # Used to protect all public methods

        self._DIR = tempfile.mkdtemp(prefix='aoh-')
        self._LOGS_PATH = f'{self._DIR}/artifacts/{self.id}/stdout'
        self._RECVBUF_PATH = f'{self._DIR}/recvbuf'
        self._SENDBUF_PATH = f'{self._DIR}/sendbuf'
        self._sendbuf = None
        self._recvbuf = None
        self._logs = None

        self._thread = None
        self._runner = None

        self._last_req = time.time()

        try:
            # Create hostname file so connection plugin can verify hosts
            with open(f'{self._DIR}/hostname', 'w') as f:
                f.write(f'{host}\n')

            self._start_runner(config, playbook, host, args)

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


    def _start_runner(self, config, playbook, host, args):
        """Configure and start the underlying ansible-runner."""

        # Set ansible_connection=aoh for the client host only. Note that we
        # don't use ansible-runner's inventory directory because that will
        # shadow user inventory files.
        with open(f'{self._DIR}/inventory.ini', 'w') as f:
            f.write(f'[aoh]\n{host} ansible_connection=aoh')

        raw_config = ansible_runner.get_ansible_config(
            'dump',
            config,
            private_data_dir=self._DIR,
            quiet=True,
        )[0]

        connection_plugins = eval(next(
            x for x in raw_config.split('\n')
            if x.startswith('DEFAULT_CONNECTION_PLUGIN_PATH')
        ).split('= ')[1])
        inventory = eval(next(
            x for x in raw_config.split('\n')
            if x.startswith('DEFAULT_HOST_LIST')
        ).split('= ')[1])

        env = {
            'ANSIBLE_CONNECTION_PLUGINS': ':'.join(
                [_CONNECTION_PLUGIN_DIR] + connection_plugins
            ),
            'ANSIBLE_CONFIG': config,
            'ANSIBLE_INVENTORY': ','.join(
                [f'{self._DIR}/inventory.ini'] + inventory
            ),
        }
        vars = {
            'ansible_aoh_dir': self._DIR,
        }

        self._thread, self._runner = ansible_runner.run_async(
            private_data_dir=self._DIR,
            ident=self.id,
            envvars=env,
            extravars=vars,
            cmdline=args,

            playbook=playbook,

            quiet=True,
            suppress_env_files=True,
        )


    def _runner_finished(self):
        """Check whether the underlying ansible runner has finished."""

        assert self._runner is not None
        return self._runner.status not in ['starting', 'running']


    def has_timed_out(self):
        """Check whether the AoH runner has timed out."""

        with self._lock:
            return self._last_req < time.time() - _CLIENT_TIMEOUT


    def process_client_request(self, req):
        """Process an AoH client request."""

        with self._lock:
            if self.id is None:
                # Runner has already been torn down
                return {
                    'finished': True,
                    'err': 'Client timeout',
                }

            res = {}
            self._last_req = time.time()

            # We check runner status first, in case new logs come in afterwards
            res['finished'] = self._runner_finished()

            assert self._logs is not None
            res['logs'] = self._logs.read()

            if req and self._recvbuf:
                try:
                    self._recvbuf.write(json.dumps(req) + '\n')
                    self._recvbuf.flush()
                except BrokenPipeError:
                    # Ansible should exit soon on its own
                    pass

            if self._sendbuf:
                line = self._sendbuf.readline()
                for key, val in json.loads(line or '{}').items():
                    res[key] = val

            return res


    def teardown(self):
        """Terminate the AoH runner and free its resources."""

        with self._lock:
            if self.id is None:
                # Runner has already been torn down
                return
            self.id = None

            if self._logs:
                self._logs.close()

            if self._recvbuf:
                try:
                    # Send an error in case the AoH connection plugin is currently
                    # blocking on a read
                    self._recvbuf.write('{"err":"Runner teardown"}\n')
                    self._recvbuf.flush()
                except BrokenPipeError:
                    pass

                try:
                    self._recvbuf.close()
                except BrokenPipeError:
                    pass

            if self._sendbuf:
                try:
                    self._sendbuf.close()
                except BrokenPipeError:
                    pass

            if self._thread:
                # The Ansible runner *should* exit if it hasn't already due to a
                # broken recvbuf pipe or the sendbuf error.
                self._thread.join(10)
                if self._thread.is_alive():
                    raise AoHError('Ansible runner thread not terminated')

            shutil.rmtree(self._DIR)
