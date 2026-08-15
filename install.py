#!/usr/bin/env python3

import requests # TODO: eliminate dependency?
import time

API = 'http://localhost:5000'

res = requests.post(f'{API}/runners/', json={
    'host': 'localhost',
})

assert res.status_code == 201

job_url = f'{API}{res.headers['Location']}'

while True:
    status = requests.get(job_url, cookies=res.cookies).content
    print(f'Status: {status.decode()}')

    if status not in [b'started', b'running']:
        break
    time.sleep(1)
