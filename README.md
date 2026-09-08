# AoH: Ansible-over-HTTP

Run an Ansible playbook with a single `curl <url> | python` command.

More specifically, this triggers an `ansible-playbook` run on the AoH server,
with the local client fetching commands for its own tasks over HTTP. This is
especially useful for machines that are behind a NAT or firewall (thus
preventing the use of `ansible-playbook` directly), but also either run Windows
or aren't trusted with full repository access (thus preventing the use of
`ansible-pull`). For example, AoH can be used to easily run a dotfile
installation playbook on new machines, anytime, anywhere.


## Comparison with Traditional Ansible & Ansible Pull

|                                   | Ansible              | AoH                  | Ansible Pull     |
| --------------------------------- | -------------------- | -------------------- | ---------------- |
| Architecture                      | Push                 | Hybrid               | Pull             |
| Server requirements               | `ansible-playbook`   | `aoh`                | Any git server   |
| Client requirements               | `python`             | `python`             | `ansible-pull`   |
| Controller logic execution        | Server-side          | Server-side          | Client-side      |
| Client has full repository access | No                   | No                   | Yes              |
| Connection method                 | Usually SSH          | HTTP                 | Local connection |
| Connection direction              | Server &rarr; client | Client &rarr; server | NA               |


## Getting Started

The AoH server is packaged as a Docker image. You can quickly try it out with
the following commands:

```sh
# Build and run the server docker image:
docker build -t aoh .
docker run --rm --detach --name aoh -p 8000:8000 -v ./demo:/aoh aoh

# Run the client CLI (the demo AoH password is "hunter2")
curl -s 127.0.0.1:8000/run | python3
curl -s 127.0.0.1:8000/run | python3 - --help

# Stop the server docker container
docker stop aoh
```


## Configuration

### Environment Variables

AoH supports the following configuration options, specified either via
environment variables or a `.env` file.

- `AOH_DEBUG`: If set to `1`, the AoH server will copy Ansible logs to stdout.
  Defaults to `0`.

- `AOH_ORIGIN`: The origin of the AoH server, as referenced in the `/run.py`
  script (e.g. `https://aoh.example.com:5000`). This must be set if running AoH
  behind a proxy. Defaults to the origin on which requests for `/run.py` are
  received.

- `AOH_MAX_RUNNERS`: The maximum number of concurrent runners, or `0` for no
  limit. Defaults to `0`.

- `AOH_PASSWORDS_FILE`: The file containing passwords for password-protected
  playbooks (see below). Defaults to `/aoh/passwords.yml` when running the
  Docker image and `./passwords.yml` otherwise.

- `AOH_PLAYBOOKS_FILE`: The file containing playbook configuration (see below).
  Defaults to `/aoh/playbooks.yml` when running the Docker image and
  `./playbooks.yml` otherwise.


### Playbooks

AoH only executes playbooks that are listed in the `$AOH_PLAYBOOKS_FILE` file,
which must have the following structure:

<!-- EXAMPLE COPIED FROM demo/playbooks.yml: -->

```yml
main.yml: # The playbook name

  # The path to the playbook, relative to $AOH_PLAYBOOKS_FILE. Defaults to the
  # playbook name.
  path: playbooks/playbook.yml

  # The path to an associated Ansible config file, if one exists, relative to
  # $AOH_PLAYBOOKS_FILE.
  config: playbooks/ansible.cfg

  # The hostname to assign to clients. If omitted or null, each client is
  # assigned the hostname that it reports for itself.
  host: my-aoh-host

  # The groups to assign to clients, in addition to the aoh group and any groups
  # defined in inventory files.
  groups:
    - group1
    - group2

  # Whether to require a password to execute the playbook. Passwords must be
  # specified separately in the $AOH_PASSWORDS_FILE file (see below). Defaults
  # to false.
  password: true

  # Whether to print Ansible output on the client. Defaults to true.
  output: true

  # The ansible-playbooks options that users are allowed to invoke. Short and
  # long option forms must be specified separately. A reasonable set of safe
  # options are allowed by default, see aoh/security.py.
  allow_opts:
    - '--become-method'

  # A list of ansible-playbook options that users are not allowed to invoke.
  # This overrides the default allowed options and the options specified in
  # allow_opts. Some options are always blocked, see aoh/security.py.
  block_opts:
    - '--list-tags'

  # Whether to allow clients to use Jinja expressions in ansible-playbook
  # arguments. Defaults to false.
  jinja_args: true

  # Additional raw ansible-playbook options
  extra_args:
    - '--diff'

  # The description displayed on the playbook web page. Defaults to null, which
  # disables the playbook web page.
  web_description: 'Run the main.yml playbook with a single command:'
```


### Playbook Passwords

Passwords for password-protected playbooks must be specified as bcrypt hashes in
the `$AOH_PASSWORDS_FILE` file. For example:

<!-- EXAMPLE COPIED FROM demo/passwords.yml: -->

```yml
# Require the password "hunter2" to execute the main.yml playbook
main.yml: $2a$14$LfC6Bcczc0WM.OObqgQPYeVvYa10g1Z4Z8C.eERyd.GarPmNa5/ve
```


## Security

Like both Ansible and Ansible Pull, AoH clients must trust the server and its
playbooks since they are allowed to execute arbitrary commands. Unlike both
Ansible and Ansible Pull however, AoH introduces the risk of clients influencing
command execution on the server. As just one example, if a malicious client
passed the options `--extra-var "foo={{ lookup('file', '/secret' }}"` to AoH and
the variable `foo` was used in a task run on the client, the contents of
`/secret` could be leaked to the client.

AoH aims to minimize these security risks as much as possible while still
providing flexibility for different use cases. Below are the measures that AoH
takes, or can be configured to take, to mitigate security risks.

- **Restricting Playbook Access:** By default, any client with access to the AoH
  server can run any playbook. If access must be restricted to certain clients,
  playbooks should be password-protected using the `password` playbook option
  and the `$AOH_PASSWORDS_FILE` file.

- **Blocking Ansible Options:** By default, clients are only allowed to invoke
  only a small subset of reasonably safe `ansible-playbook` options. Additional
  options can be allowed or blocked via the `allow_opts` and `block_opts`
  playbook options.

- **Blocking Jinja Expressions in Ansible Arguments:** By default,
  clients-supplied `ansible-playbook` options containing Jinja expressions are
  blocked. If necessary, this protection can be disabled via the `jinja_args`
  playbook option.

- **Hiding Ansible Output:** By default, clients receives and print all Ansible
  output, including `--diff` output, `--verbose` logs, and even output from
  tasks executed on other hosts. If this behavior could reveal sensitive data,
  Ansible output should be hidden entirely from clients via the `output`
  playbook option.

- **Forcing Client Hostnames:** By default, the server executes tasks on clients
  according to their reported hostnames. This could allow a client to receive
  playbook tasks meant for other hosts. If a playbook includes sensitive tasks
  for other hosts, client hostnames should be set to a safe value via the `host`
  playbook option.

- **Forcing Ansible Options:** Additional `ansible-playbook` options may be
  added to every execution via the `extra_args` playbook option. For example, if
  clients must not be able to trigger the execution of other hosts' tasks, then
  the `['--limit', 'aoh']` option should be added to `extra_args`. Consider also
  adding these options to `block_opts` to prevent clients from modifying them.

Other recommended security measures include using a reverse proxy to serve AoH
over HTTPS only, using Ansible Vault to securely store playbook secrets, and
ensuring that all playbooks are fully trusted and secure.


## Limitations

- AoH directs the client's tasks to be executed over HTTP by setting the
  `ansible_connection` option via a custom inventory host variable. This
  variable must not be overridden by, for example, variables in `host_vars/*`
  files. Refer to Ansible's [variable precedence
  documentation][ansible-precedence] for more information.

[ansible-precedence]: https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html#understanding-variable-precedence
