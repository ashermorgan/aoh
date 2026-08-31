#!/usr/bin/env python3

import base64
import getpass
import json
import os
import platform
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = '{{ API_URL }}' #{# Substitution performed by Flask #}

PASSWORD_PROMPTS = {
    'aoh_password': 'AoH password: ',
    'connection_password': 'SSH password: ',
    'become_password': 'BECOME password: ',
    'vault_password': 'Vault password: ',
}

# Set 10s EXEC keep alive interval (see also TIMEOUT in aoh.py)
KEEP_ALIVE_INTERVAL = 10


class ClientError(Exception):
    """Raised for miscellaneous client errors."""


def exec(args, keep_alive_handler=None):
    """Run a command on the local host."""

    try:
        p = subprocess.Popen(
            args,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        while p.returncode is None:
            try:
                p.wait(KEEP_ALIVE_INTERVAL)
            except subprocess.TimeoutExpired:
                if keep_alive_handler:
                    keep_alive_handler()

        stdout, stderr = p.communicate()
        return {
            'returncode': p.returncode,
            'stdout': stdout.decode('latin1'),
            'stderr': stderr.decode('latin1'),
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


def runner_update(url, cookies, data, keep_alive=False):
    """Submit runner updates and process core response fields."""

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


def runner_loop(runner_url, cookies):
    """Main execution loop."""

    req = {}

    while True:
        res = runner_update(runner_url, cookies, req)

        if 'exec' in res:
            keep_alive_handler = lambda res=res: runner_update(
                runner_url,
                cookies,
                { 'id': res['id'], 'keep-alive': True },
                keep_alive=True
            )
            req = exec(res['exec'], keep_alive_handler)
            req['id'] = res['id']
        elif 'put' in res:
            req = put(res['put'])
            req['id'] = res['id']
        elif 'fetch' in res:
            req = fetch(res['fetch'])
            req['id'] = res['id']
        else:
            req = {}
            time.sleep(0.1)


def create_runner(playbook, args):
    """Main execution loop."""

    url = f'{API}/runners/{playbook}'

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

    runner_loop(f"{API}{headers['Location']}", session_token)


def cli(args):
    """Execute the AoH client CLI."""

    if '-h' in args or '--help' in args:
        if len(args) >= 1 and args[0] != '-':
            prog = args[0]
        else:
            prog = f'curl {API}/run | {os.path.basename(sys.executable)} -'

        print(f'Usage: {prog} [-h] [<playbook>] [<opts>...]')
        print()
        print('Runs an Ansible playbook on a remote server over an HTTP '
              'connection.')
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
