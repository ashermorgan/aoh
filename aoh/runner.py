import json
import os
import shlex
import shutil
import tempfile
import time
from threading import Lock
from uuid import uuid4

import ansible_runner

_AOH_DEBUG = (os.getenv('AOH_DEBUG', '0') == '1')

_CONNECTION_PLUGIN_DIR = f'{os.path.dirname(__file__)}/connection_plugins/'

_PASSWORD_PROMPTS = {
    'become_password': '^BECOME password.*:\\s*?$',
    'connection_password': '^SSH password:\\s*?$',
    'vault_password': '^Vault password:\\s*?$',
}

class RunnerError(Exception):
    """Raised for AoH runner errors."""


class Runner:
    """An Ansible-over-HTTP playbook runner."""

    def __init__(self, playbook, host, args, passwords):
        """Create a new AoH runner."""

        self.id = str(uuid4()) # Runner ID (set to None after teardown)
        self.playbook = playbook
        self.host = self.playbook.host or host or 'aoh_node'
        self.args = args
        self.passwords = passwords

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

        self._t_finished = None

        try:
            # Create hostname file so connection plugin can verify hosts
            with open(f'{self._DIR}/hostname', 'w') as f:
                f.write(f'{self.host}\n')

            self._start_runner()

            # We assume that ansible-runner will eventually create its log file
            while not os.path.exists(self._LOGS_PATH):
                time.sleep(0.1)
            self._logs = open(self._LOGS_PATH, 'r')  # noqa: SIM115
        except:
            self.teardown()
            raise


    def _start_runner(self):
        """Configure and start the underlying ansible-runner."""

        # Set ansible_connection=aoh for the client host only. Note that we
        # don't use ansible-runner's inventory directory because that will
        # shadow user inventory files.
        with open(f'{self._DIR}/inventory.ini', 'w') as f:
            f.write(f'[aoh]\n{self.host} ansible_connection=aoh\n')
            f.writelines(f'[{g}]\n{self.host}\n' for g in self.playbook.groups)

        raw_config = ansible_runner.get_ansible_config(
            'dump',
            self.playbook.config,
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
            'ANSIBLE_CONFIG': self.playbook.config,
            'ANSIBLE_FORCE_COLOR': '1',
            'ANSIBLE_INVENTORY': ','.join(
                [f'{self._DIR}/inventory.ini'] + inventory
            ),
        }
        vars = {
            'ansible_aoh_dir': self._DIR,
        }
        pw_prompt_answers = {}
        for pw_type in self.passwords:
            pw_prompt_answers[_PASSWORD_PROMPTS[pw_type]] = \
                    self.passwords[pw_type]
        cmdline = ' '.join(shlex.quote(arg) for arg in self.args)
        cmdline += ' ' + self.playbook.cmdline

        def _finished_callback(_):
            self._t_finished = time.time()

        self._thread, self._runner = ansible_runner.run_async(
            private_data_dir=self._DIR,
            ident=self.id,
            envvars=env,
            extravars=vars,
            cmdline=cmdline,
            passwords=pw_prompt_answers,
            playbook=self.playbook.path,
            finished_callback=_finished_callback,
            quiet=not _AOH_DEBUG,
            suppress_env_files=True,
        )


    def _runner_finished(self):
        """Check whether the underlying ansible runner has finished."""

        assert self._runner is not None
        return self._runner.status not in ['starting', 'running']


    def has_timed_out(self, threshold):
        """Check whether the AoH runner has timed out."""

        with self._lock:
            return self._t_finished and \
                    self._t_finished < time.time() - threshold


    def process_message(self, req):
        """Process an AoH client message."""

        with self._lock:
            if self.id is None:
                # Runner has already been torn down, probably due to timeout
                return {
                    'err': 'Client timeout',
                }

            res = {}

            # We check runner status first, in case new logs come in afterwards
            res['finished'] = self._runner_finished()

            if self.playbook.output:
                assert self._logs is not None
                res['logs'] = self._logs.read()

            if not self._recvbuf and os.path.exists(self._RECVBUF_PATH):
                self._recvbuf = open(self._RECVBUF_PATH, 'w')  # noqa: SIM115
            if req and self._recvbuf:
                try:
                    self._recvbuf.write(json.dumps(req) + '\n')
                    self._recvbuf.flush()
                except BrokenPipeError:
                    # Ansible should exit soon on its own
                    pass

            if not self._sendbuf and os.path.exists(self._SENDBUF_PATH):
                self._sendbuf = open(self._SENDBUF_PATH, 'r')  # noqa: SIM115
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
                    # Send an error in case the AoH connection plugin is
                    # currently blocking on a read
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
                # The Ansible runner *should* exit if it hasn't already due to
                # a broken recvbuf pipe or the sendbuf error.
                self._thread.join(10)
                if self._thread.is_alive():
                    raise RunnerError('Ansible runner thread not terminated')

            shutil.rmtree(self._DIR)
