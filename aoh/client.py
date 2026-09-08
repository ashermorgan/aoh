#!/usr/bin/env python3

import base64
import getpass
import json
import os
import platform
import selectors
import subprocess
import sys
import time
import typing
from urllib.error import HTTPError
from urllib.request import Request, urlopen

AOH_ORIGIN = '{{ AOH_ORIGIN }}' #{# Substitution performed by Flask #}

PASSWORD_PROMPTS = {
    'aoh_password': 'AoH password: ',
    'connection_password': 'SSH password: ',
    'become_password': 'BECOME password: ',
    'vault_password': 'Vault password: ',
}

# How long to sleep after receiving an empty responses
WAIT_INTERVAL = 0.1


class ClientError(Exception):
    """Raised for miscellaneous client errors."""


def send_json_request(url, req_data=None, method='GET', cookies=''):
    """Send an HTTP request, expecting JSON to be used for all content."""

    req = Request(
        url,
        method=method,
        data=json.dumps(req_data).encode() if req_data is not None else None,
        headers={
            'Content-Type': 'application/json',
            'Cookie': cookies,
        },
    )

    try:
        with urlopen(req) as res:
            status_code = res.status
            headers = res.headers
            data = res.read()
    except HTTPError as e:
        status_code = e.code
        headers = e.headers
        data = e.fp.read()

    if headers.get('Content-Type') != 'application/json':
        if status_code >= 400:
            raise ClientError(f'Server responded with {status_code}')
        else:
            raise ClientError('Server responded with unexpected content type: '
                              f"{headers.get('Content-Type')}")

    return status_code, headers, json.loads(data)


def send_message(url, cookies, data, keep_alive=False):
    """Send a message to the AoH runner and process core response fields."""

    status, _, res = send_json_request(url, data, 'PUT', cookies)

    if 'logs' in res:
        # Strip duplicate password prompts
        logs = res['logs']
        while any(logs.startswith(prompt[:-2]) for prompt in
                    PASSWORD_PROMPTS.values()):
            logs = logs.split('\n', 1)[1]

        print(logs, end='')

    if 'err' in res:
        raise ClientError(res['err'])
    elif status != 200:
        raise ClientError(f'Server responded with {status}')
    elif keep_alive and not res.get('keep-alive'):
        raise ClientError('Received invalid keep-alive response')
    elif res.get('finished'):
        sys.exit(0)

    return res


def become(args, p):
    """
    Ensure that become succeeds using the provided arguments.

    Modeled after _ensure_become_success() in the local connection plugin.
    """

    os.set_blocking(p.stdout.fileno(), False)
    os.set_blocking(p.stderr.fileno(), False)

    prompt = args['prompt'].encode()
    password = args['password'].encode()
    success = args['success'].encode()

    stdout = b''
    stderr = b''
    stdout_offset = 0
    stderr_offset = 0

    timeout = time.monotonic() + 10
    sent_password = False

    def _error_msg(msg):
        msg += ' waiting for become success'
        if prompt and password and not sent_password:
            msg += ' or become password prompt'
        msg += '.'

        if stdout:
            msg += f'\n>>> Standard Output\n{stdout.decode()}'
        if stderr:
            msg += f'\n>>> Standard Error\n{stderr.decode()}'

        return msg

    with selectors.DefaultSelector() as selector:
        selector.register(p.stdout, selectors.EVENT_READ, 'stdout')
        selector.register(p.stderr, selectors.EVENT_READ, 'stderr')

        while not success in stdout:
            if not selector.get_map():
                # All descriptors are EOF
                raise ClientError(_error_msg('Premature end of stream'))

            events = selector.select(timeout - time.monotonic())
            if not events:
                raise ClientError(_error_msg('Timed out'))

            for key, _ in events:
                f = typing.cast(typing.BinaryIO, key.fileobj)
                output = f.read()

                if not output:
                    # Descriptor is EOF
                    selector.unregister(f)
                elif key.data == 'stdout':
                    stdout += output
                else:
                    stderr += output

            if prompt and password and (prompt in stdout[stdout_offset:] or
                                        prompt in stderr[stderr_offset:]):
                if sent_password:
                    raise ClientError(_error_msg('Duplicate become password '
                                                 'prompt encountered'))

                stdout_offset = len(stdout)
                stderr_offset = len(stderr)

                p.stdin.write(password + b'\n')
                p.stdin.flush()

                sent_password = True

    os.set_blocking(p.stdout.fileno(), True)
    os.set_blocking(p.stderr.fileno(), True)

    return stdout, stderr


def exec(args, keep_alive_interval, keep_alive_handler):
    """Run a command on the local host."""

    try:
        p = subprocess.Popen(
            args['cmd'],
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdin = args['stdin']
        if stdin is not None:
            stdin = stdin.encode('latin1')

        if 'become' in args:
            become_stdout, become_stderr = become(args['become'], p)
        else:
            become_stdout, become_stderr = b'', b''

        while p.returncode is None:
            try:
                stdout, stderr = p.communicate(input=stdin,
                                               timeout=keep_alive_interval)
            except subprocess.TimeoutExpired:
                keep_alive_handler()
                stdin = None # Don't send input a second time

        return {
            'returncode': p.returncode,
            'stdout': (become_stdout + stdout).decode('latin1'),
            'stderr': (become_stderr + stderr).decode('latin1'),
        }
    except Exception as e:  # noqa: BLE001
        return { 'err': str(e) }


def put(args):
    """Transfer a file to the local host."""

    try:
        with open(args['dest'], 'wb') as f:
            f.write(base64.b64decode(args['data']))
    except Exception as e:  # noqa: BLE001
        return { 'err': str(e) }
    else:
        return { 'ok': True }


def fetch(args):
    """Fetch a file from the local host."""

    try:
        with open(args['dest'], 'rb') as f:
            return {
                'data': base64.b64encode(f.read()).decode(),
            }
    except Exception as e:  # noqa: BLE001
        return { 'err': str(e) }


def runner_loop(runner_url, cookies):
    """Main runner loop."""

    req = {}

    while True:
        res = send_message(runner_url, cookies, req)

        if 'exec' in res:
            keep_alive_handler = lambda res=res: send_message(
                runner_url,
                cookies,
                { 'id': res['id'], 'keep-alive': True },
                keep_alive=True
            )
            req = exec(res['exec'], res['keep-alive-interval'],
                       keep_alive_handler)
            req['id'] = res['id']
        elif 'put' in res:
            req = put(res['put'])
            req['id'] = res['id']
        elif 'fetch' in res:
            req = fetch(res['fetch'])
            req['id'] = res['id']
        else:
            req = {}
            time.sleep(WAIT_INTERVAL)


def create_runner(playbook, args):
    """Create a runner and enter the runner loop."""

    url = f'{AOH_ORIGIN}/runners/{playbook}'

    req = {
        'host': platform.node(),
        'args': args,
    }

    status, headers, res = send_json_request(url, req, 'POST')

    if status == 401 and 'passwords' in res:
        req['passwords'] = {}
        for pw_type in res['passwords']:
            req['passwords'][pw_type] = \
                    getpass.getpass(PASSWORD_PROMPTS[pw_type])
        status, headers, res = send_json_request(url, req, 'POST')

    if 'err' in res:
        raise ClientError(res['err'])
    elif status != 201:
        raise ClientError(f'Server responded with {status}')

    # We assume that only one cookie will be set
    session_token = headers['Set-Cookie'].split(';')[0]

    runner_loop(f"{AOH_ORIGIN}{headers['Location']}", session_token)


def cli(args):
    """Execute the AoH client CLI."""

    if '-h' in args or '--help' in args:
        if len(args) >= 1 and args[0] != '-':
            prog = args[0]
        else:
            prog = f'curl {AOH_ORIGIN}/run | ' \
                   f'{os.path.basename(sys.executable)} -'

        print(f'Usage: {prog} [-h] [<playbook>] [<opts>...]')
        print()
        print('Runs Ansible playbooks on a remote server and fetches commands '
              'for the local')
        print('host\'s tasks over HTTP.')
        print()
        print('Arguments: ')
        print('  playbook          The name of the playbook to run (defaults '
              'to "main.yml")')
        print()
        print('Options: ')
        print('  -h, --help        Show this help message and exit')
        print('  <opts>            Any server-approved ansible-playbook(1) '
              'options')

        sys.exit(0)

    if len(args) >= 2 and not args[1].startswith('-'):
        playbook = args[1]
        aoh_args = args[2:]
    else:
        playbook = 'main.yml'
        aoh_args = args[1:]

    try:
        create_runner(playbook, aoh_args)
    except ClientError as e:
        print(f'Error: {e}')
        sys.exit(1)


if __name__ == '__main__':
    cli(sys.argv)
