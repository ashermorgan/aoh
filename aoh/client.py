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

API = '{{ API_URL }}' # Substitution performed by Flask

PASSWORD_PROMPTS = {
    'connection_password': 'SSH password: ',
    'become_password': 'BECOME password: ',
    'vault_password': 'Vault password: ',
}


def exec(args):
    """Run a command on the local host."""

    try:
        p = subprocess.Popen(
            args,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
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

    # We assume that all responses will include JSON bodies
    assert headers.get('Content-Type') == 'application/json'

    return status_code, headers, json.loads(data)


def runner_loop(runner_url, cookies):
    """Main execution loop."""

    req = {}
    while True:
        status, _, res = send_json_request(runner_url, req, 'PUT', cookies)

        assert status == 200

        if 'logs' in res:
            # Strip duplicate password prompts
            logs = res['logs']
            while any(logs.startswith(prompt[:-2]) for prompt in
                      PASSWORD_PROMPTS.values()):
                logs = logs.split('\n', 1)[1]

            print(logs, end='')

        req = {}
        if 'err' in res:
            print(res['err'])
            sys.exit(1)
        if res.get('finished'):
            break
        elif 'exec' in res:
            req = exec(res['exec'])
        elif 'put' in res:
            req = put(res['put'])
        elif 'fetch' in res:
            req = fetch(res['fetch'])
        else:
            time.sleep(0.1)


def create_runner(playbook, args):
    """Main execution loop."""

    url = f'{API}/runners/'

    req = {
        'host': platform.node() or 'aoh_node',
        'playbook': playbook,
        'args': args,
    }

    status, headers, res = send_json_request(url, req, 'POST')

    if status == 401 and 'passwords' in res:
        req['passwords'] = {}
        for pw_type in res['passwords']:
            req['passwords'][pw_type] = \
                    getpass.getpass(PASSWORD_PROMPTS[pw_type])
        status, headers, res = send_json_request(url, req, 'POST')

    if status != 201:
        print(res['err'])
        sys.exit(1)

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

    create_runner(playbook, aoh_args)


if __name__ == '__main__':
    cli(sys.argv)
