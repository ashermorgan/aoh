# Copyright: (c) 2026, Asher Morgan <asher@ashermorgan.net>
# GNU General Public License v3.0+

DOCUMENTATION = """
    name: aoh
    short_description: Run tasks through an Ansible-over-HTTP (AoH) connection

    options:
        aoh_dir:
            description: The AoH runner directory
            type: string
            required: true
            vars:
                - name: ansible_aoh_dir
        aoh_timeout:
            description: The timeout for AoH responses, in seconds
            type: integer
            default: 60
            env:
                - name: ANSIBLE_TIMEOUT
            ini:
                - key: timeout
                  section: defaults
            vars:
                - name: ansible_aoh_timeout
            cli:
                - name: timeout
        aoh_keep_alive_count:
            description: The number of keep alive messages expected per timeout
            type: integer
            default: 10
            env:
                - name: ANSIBLE_AOH_KEEP_ALIVE_COUNT
            vars:
                - name: ansible_aoh_keep_alive_count
"""

import base64
import binascii
import json
import os
import select
import typing as t
from uuid import uuid4

from ansible.errors import (
    AnsibleConnectionFailure,
    AnsibleError,
    AnsibleFileNotFound,
)
from ansible.plugins.connection import ConnectionBase
from ansible.utils.display import Display

display = Display()


class Connection(ConnectionBase):
    """Ansible-over-HTTP (AoH) connection."""

    transport = 'aoh'
    has_pipelining = False


    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().__init__(*args, **kwargs)

        self.timeout = self.get_option('aoh_timeout')
        self.keep_alive_count = self.get_option('aoh_keep_alive_count')
        self.keep_alive_interval = round(self.timeout/self.keep_alive_count, 1)

        self._sendbuf = None
        self._recvbuf = None
        self._recvpoll = None
        self._connected = False


    def _connect(self) -> Connection:  # noqa: F821
        """Connect to the host."""

        if not self._connected:
            AOH_DIR = self.get_option('aoh_dir')

            with open(f'{AOH_DIR}/hostname', 'r') as f:
                hostname = f.readline().strip()
                if hostname != self._play_context.remote_addr:
                    raise AnsibleError('Attempted to connect to an AoH runner '
                                       'belonging to a different host '
                                       f'({hostname})')

            display.vvv(f'ESTABLISH CONNECTION TO AOH RUNNER {AOH_DIR}',
                        host=self._play_context.remote_addr)

            RECVBUF_PATH = f'{AOH_DIR}/recvbuf'
            SENDBUF_PATH = f'{AOH_DIR}/sendbuf'

            if not os.path.exists(RECVBUF_PATH):
                os.mkfifo(RECVBUF_PATH)
            if not os.path.exists(SENDBUF_PATH):
                os.mkfifo(SENDBUF_PATH)

            self._recvbuf = open(RECVBUF_PATH, 'r')  # noqa: SIM115
            self._sendbuf = open(SENDBUF_PATH, 'w')  # noqa: SIM115

            self._recvpoll = select.poll()
            self._recvpoll.register(self._recvbuf, select.POLLIN)

            self._connected = True

        return self


    def _send_message(self, msg: dict) -> dict:
        """Send a message to the client and wait for a response."""

        assert self._sendbuf is not None
        assert self._recvbuf is not None
        assert self._recvpoll is not None

        msg['id'] = str(uuid4())
        msg['keep-alive-interval'] = self.keep_alive_interval
        self._sendbuf.write(json.dumps(msg) + '\n')
        self._sendbuf.flush()

        while True:
            if not self._recvpoll.poll(self.timeout * 1000):
                raise AnsibleConnectionFailure('Timed out waiting for AoH '
                                               'response')

            try:
                res = json.loads(self._recvbuf.readline())
            except json.decoder.JSONDecodeError:
                raise AnsibleError('Received corrupt AoH message')

            if not 'id' in msg:
                raise AnsibleError('Received AoH message without ID')
            elif res['id'] != msg['id']:
                raise AnsibleError('Received AoH message with unexpected ID')
            elif 'err' in res:
                raise AnsibleError(str(res['err']))

            if not res.get('keep-alive'):
                return res

            self._sendbuf.write(json.dumps({
                'id': msg['id'],
                'keep-alive': True,
            }) + '\n')
            self._sendbuf.flush()


    def exec_command(self, cmd: str, in_data: bytes | None = None,
                     sudoable: bool = True) -> tuple[int, bytes, bytes]:
        """Run a command on the host."""

        super().exec_command(cmd, in_data=in_data, sudoable=sudoable)

        display.vvv(f'EXEC {cmd}', host=self._play_context.remote_addr)

        assert isinstance(cmd, str)
        assert in_data is None

        res = self._send_message({ 'exec': cmd })
        if not all(k in res for k in ['returncode', 'stdout', 'stderr']):
            raise AnsibleError('Received invalid AoH EXEC response')
        return (
            res['returncode'],
            res['stdout'].encode('latin1'),
            res['stderr'].encode('latin1'),
        )


    def put_file(self, in_path: str, out_path: str) -> None:
        """Transfer a file to the host."""

        super().put_file(in_path, out_path)

        display.vvv(f'PUT {in_path} TO {out_path}',
                    host=self._play_context.remote_addr)

        if not os.path.exists(in_path):
            raise AnsibleFileNotFound(f'File does not exist: {in_path}')
        with open(in_path, 'rb') as f:
            self._send_message({
                'put': {
                    'data': base64.b64encode(f.read()).decode(),
                    'dest': out_path,
                },
            })


    def fetch_file(self, in_path: str, out_path: str) -> None:
        """Fetch a file from the host."""

        super().fetch_file(in_path, out_path)

        display.vvv(f'FETCH {in_path} TO {out_path}',
                    host=self._play_context.remote_addr)

        res = self._send_message({ 'fetch': in_path })
        if 'data' not in res:
            raise AnsibleError('Received AoH FETCH response without data')
        try:
            data = base64.b64decode(res['data'], validate=True)
        except binascii.Error:
            raise AnsibleError('Received AoH FETCH response with corrupt data')

        with open(out_path, 'wb') as f:
            f.write(data)


    def close(self) -> None:
        """Close connection with host."""

        display.vvv('CLOSE CONNECTION FOR AOH RUNNER '
                    f'{self.get_option('runner')}',
                    host=self._play_context.remote_addr)

        if self._recvbuf:
            self._recvbuf.close()
        if self._sendbuf:
            self._sendbuf.close()

        self._connected = False

        super().close()
