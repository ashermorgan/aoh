# AoH: Ansible-over-HTTP

Run an Ansible playbook with a single `curl <aoh server url> | python` command.

More specifically, this triggers an `ansible-playbook` run on the AoH server,
with the local client fetching commands for its own tasks over HTTP. This is
especially useful for machines that are behind a NAT or firewall (thus
preventing the use of `ansible-playbook` directly), but also either run Windows
or aren't trusted with full repository access (thus preventing the use of
`ansible-pull`). For example, AoH can be used to easily run a dotfile
installation playbook on new machines, anytime, anywhere.


## Comparison with Traditional Ansible & Ansible Pull

|                                   | Ansible            | AoH         | Ansible Pull     |
| --------------------------------- | ------------------ | ----------- | ---------------- |
| Architecture                      | Push               | Pull        | Pull             |
| Server requirements               | `ansible-playbook` | `aoh`       | Any git server   |
| Client requirements               | `python`           | `python`    | `ansible-pull`   |
| Ansible controller                | Server             | Server      | Client           |
| Client has full repository access | No                 | No          | Yes              |
| Connection method                 | Usually SSH        | HTTP        | Local connection |

Note that Ansible controllers don't support Windows, so the `ansible-playbook`,
`aoh`, and `ansible-pull` programs all must be run on a Unix-based system.


## Getting Started

First, run the AoH server docker image.

```
$ docker run --rm --detach --name aoh -p 8000:8000 ghcr.io/ashermorgan/aoh
```

Then run the [demo playbook](demo/my-playbook.yml) via the client Python script.
The demo AoH password is `hunter2`.

```
$ curl -s 127.0.0.1:8000/run | python3
AoH password:

PLAY [Demo play] ***************************************************************

TASK [Gathering Facts] *********************************************************
ok: [my-host]

TASK [Write message to ~/aoh-demo.txt] *****************************************
--- before
+++ after: /home/me/.ansible/tmp/ansible-local-23520hhz8owqd/tmpddlm2qex/message.j2
@@ -0,0 +1,8 @@
+Welcome to AoH!
+
+The server is running this playbook with ansible-playbook, and your client is
+fetching commands for its own tasks over HTTP.
+
+Username: me
+Hostname: my-host
+Timestamp: 2026-09-12 22:58:10 UTC

changed: [my-host]

PLAY RECAP *********************************************************************
my-host                    : ok=2    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

Clients can pass options to control which playbook is executed and what
`ansible-playbook` arguments are used. Use the `--help` flag to view the CLI
syntax.

```
$ curl -s 127.0.0.1:8000/run | python3 - --help
Usage: curl -s http://127.0.0.1:8000/run | python3 - [-h] [<playbook>] [<opts>...]

Runs Ansible playbooks on a remote server and fetches commands for the local
host's tasks over HTTP.

Arguments:
  playbook          The name of the playbook to run (defaults to "main.yml")

Options:
  -h, --help        Show this help message and exit
  <opts>            Any (server-approved) ansible-playbook(1) options
```

Windows clients are also supported. Just use the `Invoke-RestMethod` cmdlet
instead of `curl`.

```
PS> irm http://<server IP>:8000 | python
```

Finally, stop the AoH server when you're done using it.

```
$ docker stop aoh
```

Next steps for deploying AoH include:

- Copy your own Ansible playbooks to the server
- Create your own `playbooks.yml` and `passwords.yml` files and mount them under
  `/aoh/` (see the [playbooks](#playbooks) and [playbook
  passwords](#playbook-passwords) sections for reference)
- Apply the recommended [security measures](#security)


## Configuration

### Environment Variables

AoH supports the following configuration options, which are set via environment
variables.

- `AOH_DEBUG`: If set to `1`, the AoH server will copy `ansible-playbook` output
  to the server's stdout. Defaults to `0`.

- `AOH_LOG_LEVEL`: The threshold for AoH logs, which are written to the server's
  stdout. Must be one of `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG`.
  Defaults to `ERROR`.

- `AOH_MAX_RUNNERS`: The maximum number of concurrent `ansible-playbook`
  sessions, or `0` for no limit. Defaults to `0`.

- `AOH_ORIGIN`: The origin of the AoH server (e.g.
  `https://aoh.example.com:5000`). This must be set if AoH is running behind a
  reverse proxy. Defaults to the origin on which requests are received.

- `AOH_PASSWORDS_FILE`: The file containing passwords for password-protected
  playbooks (see the [playbook passwords](#playbook-passwords) section below).
  Defaults to `/aoh/passwords.yml` when running the Docker image and
  `./passwords.yml` otherwise.

- `AOH_PLAYBOOKS_FILE`: The file containing playbook configuration (see the
  [playbooks](#playbooks) section below). The parent directory of this file is
  also used as the working directory for all Ansible operations. Defaults to
  `/aoh/playbooks.yml` when running the Docker image and `./playbooks.yml`
  otherwise.


### Playbooks

AoH only executes playbooks that are listed in the file specified by
the `$AOH_PLAYBOOKS_FILE` option. This file must have the following structure:

<!-- EXAMPLE COPIED FROM demo/playbooks.yml: -->

```yml
main.yml: # The playbook name

  # The path to the playbook. Relative paths are interpreted as relative to
  # $AOH_PLAYBOOKS_FILE. Defaults to the playbook name.
  path: my-playbook.yml

  # The hostname to assign to clients. If set to null, clients are assigned the
  # hostname that they report for themselves, which could be spoofed. Defaults
  # to null.
  host: my-host

  # The groups to assign to clients, in addition to the "aoh" group and any
  # groups defined in inventory files.
  groups:
    - group1
    - group2

  # A dictionary of environment variables to pass to ansible-playbook. Note that
  # the ANSIBLE_FORCE_COLOR and ANSIBLE_NOCOLOR variables are not supported
  # here as they are parsed client-side.
  env:
    ANSIBLE_PIPELINING: 'true'

  # Whether to restrict play execution to the AoH client only using
  # ansible-playbook's --limit option. If enabled, the --limit option must not
  # be present in allow_opts or extra_args. Defaults to true.
  limit: true

  # Whether to require a password to execute the playbook. Passwords must be
  # specified separately in the $AOH_PASSWORDS_FILE file (see the playbook
  # passwords section below). Defaults to false.
  password: true

  # Whether ansible-playbook output is sent to the client. Defaults to true.
  output: true

  # A list of ansible-playbooks options that users are allowed to invoke. Short
  # and long option forms must be specified separately. The following options
  # are allowed by default:
  #   --ask-become-pass / -K
  #   --ask-pass / -k
  #   --ask-vault-password / --ask-vault-pass / -J
  #   --check / -C
  #   --diff / -D
  #   --list-tags
  #   --skip-tags
  #   --start-at-task
  #   --tags / -t
  allow_opts:
    - '--become-method'

  # A list of ansible-playbook options that users are not allowed to invoke,
  # overriding the default allowed options.
  block_opts:
    - '--list-tags'

  # Whether to allow clients to use Jinja expressions in ansible-playbook
  # arguments. Defaults to false.
  jinja_args: false

  # A list of additional arguments to pass to ansible-playbook. These are not
  # subject to the allow_opts/block_opts/jinja_args restrictions. Note that the
  # --inventory option is not supported and the env.ANSIBLE_INVENTORY playbook
  # option should be used instead for specifying inventory files.
  extra_args:
    - '--diff'

  # The description displayed on the playbook web page, which is located at
  # /<playbook name>. Defaults to null, which disables the playbook web page.
  web_description: 'Run the main.yml playbook with a single command:'

another-playbook.yml:
  # and so on...
```


### Playbook Passwords

Passwords for password-protected playbooks must be included as bcrypt hashes in
the file specified by the `$AOH_PASSWORDS_FILE` option. For example:

<!-- EXAMPLE COPIED FROM demo/passwords.yml: -->

```yml
# Require the password "hunter2" to execute the main.yml playbook
main.yml: $2a$14$LfC6Bcczc0WM.OObqgQPYeVvYa10g1Z4Z8C.eERyd.GarPmNa5/ve
```

There are many tools for generating bcrypt hashes. Here is a one-liner that uses
the same `bcrypt` Python library that AoH depends on internally:

```
$ python3 -c 'import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())'
```


## Security

Like both Ansible and Ansible Pull, AoH clients must completely trust the server
and its playbooks, since they are allowed to execute arbitrary commands. AoH
does not attempt to protect clients from malicious servers.

Unlike both Ansible and Ansible Pull however, AoH introduces the risk of clients
influencing the execution of commands on the server. AoH implements various
protections against this risk by default, including blocking potentially unsafe
`ansible-playbook` arguments and limiting play execution to the AoH client.
Additional protections are available via playbook options such as `host`,
`password`, and `output`.

The following security measures are recommended as a baseline when deploying
AoH:

-  Ensure all Ansible playbooks are trusted and do not contain any potential
   security holes
-  Run the AoH server behind a reverse proxy that enforces HTTPS (and set
   the `$AOH_ORIGIN` option accordingly)
-  Restrict access for each playbook to authorized clients using the `password`
   playbook option
-  Encrypt sensitive variables using Ansible Vault and require clients to supply
   the decryption password via Ansible's `--ask-vault-pass` option
-  If clients are untrusted and an Ansible playbook contains tasks for multiple
   hosts, create separate entries in the AoH playbooks file for each host with
   the `host` option set explicitly to prevent hostname spoofing


## Limitations

- AoH directs the client's tasks to be executed over HTTP by setting the
  `ansible_connection` option via a custom inventory host variable. This
  variable must not be overridden by, for example, variables in `host_vars/*`
  files. Refer to Ansible's [variable precedence
  documentation][ansible-precedence] for more details.

[ansible-precedence]: https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html#understanding-variable-precedence


## Development

To run AoH locally for development, first install the Python dependencies and
set core configuration options via a `.env` file.

```
$ pip install -r requirements.txt
$ cp .env.example .env
```

Then start the AoH server by running the `aoh` module.

```
$ python3 -m aoh
```

Finally, open another terminal and run a playbook via the client CLI.

```
$ curl -s 127.0.0.1:5000/run | python3
```

AoH also has unit tests and end-to-end tests, which can be run with the
following commands. The end-to-end tests require Docker.

```
$ python3 -m unittest tests.unit
$ ./tests/e2e/run.sh
```
