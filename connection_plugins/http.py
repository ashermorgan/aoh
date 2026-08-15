#!/usr/bin/python

# Copyright: (c) 2026, Asher Morgan <asher@ashermorgan.net>
# GNU General Public License v3.0+

DOCUMENTATION = r'''
    name: http
    short_description: Control hosts over a "reverse" HTTP connection

    options:
        runner:
            description: The artifact directory of the associated Ansible runner
            required: true
            vars:
                - name: ansible_http_runner
'''

# ruff: disable[E402]
import base64
import json
import typing as t

from ansible.module_utils.common.text.converters import to_text
from ansible.plugins.connection import ConnectionBase
from ansible.utils.display import Display
# ruff: enable[E402]

display = Display()


class Connection(ConnectionBase):
    """Reverse-HTTP connection."""

    transport = 'http'
    has_pipelining = False


    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super(Connection, self).__init__(*args, **kwargs)

        self.sendbuf = None
        self.recvbuf = None

    def _connect(self) -> Connection:  # noqa: F821
        """Connect to the host (nop)."""

        if not self._connected:
            display.vvv('ESTABLISH HTTP CONNECTION FOR RUNNER '
                        f'{self.get_option('runner')}',
                        host=self._play_context.remote_addr)

            self.sendbuf = open(f'{self.get_option('runner')}/sendbuf', 'w')
            self.recvbuf = open(f'{self.get_option('runner')}/recvbuf', 'r')
            self._connected = True

        return self


    def exec_command(self, cmd: str, in_data: bytes | None = None,
                     sudoable: bool = True) -> tuple[int, bytes, bytes]:
        """Run a command on the host (TODO)."""

        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)

        display.vvv(f'EXEC {cmd}', host=self._play_context.remote_addr)

        assert self.sendbuf is not None
        assert self.recvbuf is not None
        assert isinstance(cmd, str)
        assert in_data is None
        # assert sudoable is False

        self.sendbuf.write(json.dumps({
            'command': cmd,
        }) + '\n')
        self.sendbuf.flush()

        res = json.loads(self.recvbuf.readline())
        return (
            res['returncode'],
            res['stdout'].encode('latin1'),
            res['stderr'].encode('latin1'),
        )


    def put_file(self, in_path: str, out_path: str) -> None:
        """Transfer file to host (TODO)."""

        super(Connection, self).put_file(in_path, out_path)

        display.vvv(f'PUT {in_path} TO {out_path}',
                    host=self._play_context.remote_addr)

        assert self.sendbuf is not None
        assert self.recvbuf is not None

        with open(in_path, 'rb') as f:
            data = base64.b64encode(f.read()).decode()

        self.sendbuf.write(json.dumps({
            'put': {
                'data': data,
                'dest': out_path,
            },
        }) + '\n')
        self.sendbuf.flush()

        self.recvbuf.readline()


    def fetch_file(self, in_path: str, out_path: str) -> None:
        """Fetch file from host (TODO)."""

        super(Connection, self).fetch_file(in_path, out_path)

        display.vvv(f'FETCH {in_path} TO {out_path}',
                    host=self._play_context.remote_addr)

        assert self.sendbuf is not None
        assert self.recvbuf is not None

        self.sendbuf.write(json.dumps({
            'get': in_path,
        }) + '\n')
        self.sendbuf.flush()

        res = json.loads(self.recvbuf.readline())
        with open(out_path, 'rb') as f:
            f.write(base64.b64decode(res['data']))


    def close(self) -> None:
        """Close connection."""

        self._connected = False
        display.vvv('CLOSE HTTP CONNECTION FOR RUNNER '
                    f'{self.get_option('runner')}',
                    host=self._play_context.remote_addr)

        super(Connection, self).close()
