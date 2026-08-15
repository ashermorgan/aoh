import os

import ansible_runner
from flask import Flask, abort, redirect, session


DATA = {}
PLAYBOOK = os.path.abspath('./demo/playbook.yml') # TODO

app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/' # TODO


@app.route('/runners/new')
def job_new():
    _, r = ansible_runner.run_async(private_data_dir='private',
                                    playbook=PLAYBOOK)
    id = r.config.ident
    DATA[id] = r
    session['runner'] = id

    return redirect(f'/runners/{id}')


@app.route('/runners/<id>')
def job_status(id):
    if id != session.get('runner'):
        abort(401)

    return DATA[id].status


if __name__ == '__main__':
    app.run(debug=True)
