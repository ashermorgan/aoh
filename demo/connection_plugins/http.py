#!/usr/bin/python

# Copyright: (c) 2026, Asher Morgan <asher@ashermorgan.net>
# GNU General Public License v3.0+

DOCUMENTATION = r'''
    name: http
    short_description: Control hosts over a "reverse" HTTP connection

    options:
        runner:
            description: The UUID of the associated Ansible runner
            required: true
            vars:
                - name: ansible_http_runner
'''

# ruff: disable[E402]
import typing as t

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


    def _connect(self) -> Connection:  # noqa: F821
        """Connect to the host (nop)."""

        if not self._connected:
            display.vvv('ESTABLISH HTTP CONNECTION FOR RUNNER '
                        f'{self.get_option('runner')}',
                        host=self._play_context.remote_addr)
            self._connected = True

        return self


    def exec_command(self, cmd: str, in_data: bytes | None = None,
                     sudoable: bool = True) -> tuple[int, bytes, bytes]:
        """Run a command on the host (TODO)."""

        super(Connection, self).exec_command(cmd, in_data=in_data, sudoable=sudoable)

        display.vvv(f'EXEC {cmd}', host=self._play_context.remote_addr)

        return (0, b'', b'')


    def put_file(self, in_path: str, out_path: str) -> None:
        """Transfer file to host (TODO)."""

        super(Connection, self).put_file(in_path, out_path)

        display.vvv(f'PUT {in_path} TO {out_path}',
                    host=self._play_context.remote_addr)


    def fetch_file(self, in_path: str, out_path: str) -> None:
        """Fetch file from host (TODO)."""

        super(Connection, self).fetch_file(in_path, out_path)

        display.vvv(f'FETCH {in_path} TO {out_path}',
                    host=self._play_context.remote_addr)

        with open(out_path, 'wb') as f:
            f.write(b'')


    def close(self) -> None:
        """Close connection."""

        self._connected = False

        super(Connection, self).close()
