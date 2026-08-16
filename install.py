#!/usr/bin/env python3

import base64
import subprocess
import time

import requests  # TODO: eliminate dependency?


API = 'http://localhost:5000'


def exec(args):
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
    except Exception as e:
        return { 'err': str(e) }


def put(args):
    try:
        with open(args['dest'], 'wb') as f:
            f.write(base64.b64decode(args['data']))
    except Exception as e:
        return { 'err': str(e) }
    else:
        return { 'ok': True }


def fetch(args):
    try:
        with open(args['dest'], 'rb') as f:
            return {
                'data': base64.b64encode(f.read()).decode(),
            }
    except Exception as e:
        return { 'err': str(e) }


def main():
    res = requests.post(f'{API}/runners/', json={
        'host': 'localhost',
    })
    assert res.status_code == 201
    cookies = res.cookies
    job_url = f'{API}{res.headers['Location']}'

    req = {}
    while True:
        res = requests.put(job_url, cookies=cookies, json=req).json()

        if 'logs' in res:
            print(res['logs'], end='')

        req = {}
        if res['finished']:
            break
        elif 'exec' in res:
            req = exec(res['exec'])
        elif 'put' in res:
            req = put(res['put'])
        elif 'fetch' in res:
            req = fetch(res['fetch'])
        else:
            time.sleep(0.1)


if __name__ == '__main__':
    main()
