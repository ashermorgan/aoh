#!/usr/bin/env python3

import base64
import getpass
import os
import platform
import subprocess
import sys
import time

import requests  # TODO: eliminate dependency?

API = '{{ API_URL }}' # Substitution performed by Flask

PASSWORD_PROMPTS = {
    'vault_password': 'Vault password: ',
    'become_password': 'BECOME password: ',
    'connection_password': 'SSH password: ',
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

def runner_loop(runner_url, cookies):
    """Main execution loop."""

    req = {}
    while True:
        res = requests.put(runner_url, cookies=cookies, json=req).json()

        if 'logs' in res:
            print(res['logs'], end='')

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

    req = {
        'host': platform.node() or 'aoh_node',
        'playbook': playbook,
        'args': args,
    }
    res = requests.post(f'{API}/runners/', json=req)

    if res.status_code == 401 and 'passwords' in res.json():
        req['passwords'] = {}
        for pw_type in res.json()['passwords']:
            req['passwords'][pw_type] = \
                    getpass.getpass(PASSWORD_PROMPTS[pw_type])
        res = requests.post(f'{API}/runners/', json=req)

    if res.status_code != 201:
        print(res.json()['err'])
        sys.exit(1)

    runner_loop(f'{API}{res.headers['Location']}', res.cookies)


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
              'to "main")')
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
        playbook = 'main'
        aoh_args = args[1:]

    create_runner(playbook, aoh_args)


if __name__ == '__main__':
    cli(sys.argv)
