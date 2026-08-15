#!/usr/bin/env python3

import base64
import subprocess
import time

import requests  # TODO: eliminate dependency?

API = 'http://localhost:5000'

res = requests.post(f'{API}/runners/', json={
    'host': 'localhost',
})
cookies = res.cookies

assert res.status_code == 201

job_url = f'{API}{res.headers['Location']}'

req = {}
while True:
    res = requests.put(job_url, cookies=cookies, json=req).json()
    if res['status'] not in ['started', 'running']:
        break

    req = {}
    if (command := res.get('command')) is not None:
        print('EXEC', command)
        p = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate()
        req['returncode'] = p.returncode
        req['stdout'] = stdout.decode('latin1')
        req['stderr'] = stderr.decode('latin1')
        print('EXEC RETURN', p.returncode)

    elif (put := res.get('put')) is not None:
        print('PUT', put['dest'], len(put['data']), 'bytes')
        with open(put['dest'], 'wb') as f:
            f.write(base64.b64decode(put['data']))
        req['ok'] = True

    elif (get := res.get('get')) is not None:
        print('PUT', put['dest'], len(put['data']), 'bytes')
        with open(put['dest'], 'rb') as f:
            req['data'] = base64.b64encode(f.read()).decode()

    else:
        time.sleep(0.1)
