import os
import tempfile

import ansible_runner
import bcrypt
import yaml

_CLI_OPT_WHITELIST = [
    # These options should be safe for clients to invoke
    '--ask-become-pass', '-K',
    '--ask-pass', '-k',
    '--ask-vault-password', '--ask-vault-pass', '-J',
    '--check', '-C',
    '--diff', '-D',
    '--limit', '-l',
    '--list-tags',
    '--skip-tags',
    '--start-at-task',
    '--tags', '-t',
    '--verbose', '-v',
    '--version',
]

_CLI_OPT_BLACKLIST = [
    '--step', # Interactive, not supported
]

_CLI_PASSWORD_OPTS = {
    # These command line flags require us to prompt the user for a password
    '--ask-become-pass': 'become_password',
    '--ask-pass': 'connection_password',
    '--ask-vault-pass': 'vault_password',
    '--ask-vault-password': 'vault_password',
    '-J': 'vault_password',
    '-K': 'become_password',
    '-k': 'connection_password',
}

_CONFIG_PASSWORD_OPTS = {
    # These config options require us to prompt the user for a password
    'DEFAULT_ASK_PASS': 'connection_password',
    'DEFAULT_ASK_VAULT_PASS': 'vault_password',
    'DEFAULT_BECOME_ASK_PASS': 'become_password',
}

_PASSWORDS_FILE = os.getenv('AOH_PASSWORDS_FILE', 'passwords.yml')


def _get_opts(args):
    """Identify options present in a list of CLI arguments."""

    opts = []

    for arg in args:
        if arg.startswith('--'):
            opts += [arg.split('=')[0]]
        elif arg.startswith('-'):
            for opt in arg.split('=')[0][1:]:
                opts += ['-' + opt]

    return opts


def validate_args(playbook, args):
    """Determine if arguments pass a playbook's security policies."""

    l1 = ['{', r'\x7b', r'\u007b', r'\U0000007b']
    l2 = ['%', r'\x25', r'\u0025', r'\U00000025']
    JINJA_PATTERNS = [a+b for a in l1 for b in l1+l2]

    cmdline = ' '.join(args)
    if not playbook.jinja_args and any(x in cmdline for x in JINJA_PATTERNS):
        return False

    for opt in _get_opts(args):
        if (not (opt in _CLI_OPT_WHITELIST or opt in playbook.allow_opts) or
                (opt in _CLI_OPT_BLACKLIST or opt in playbook.block_opts)):
            return False

    return True


def get_required_passwords(playbook, args):
    """Determine what passwords the user must be prompted for."""

    pw_types = set()

    if playbook.password:
        pw_types.add('aoh_password')

    opts = _get_opts(args + playbook.extra_args)
    for opt, pw_type in _CLI_PASSWORD_OPTS.items():
        if opt in opts:
            pw_types.add(pw_type)

    with tempfile.TemporaryDirectory(prefix='aoh-') as dir:
        raw_config = ansible_runner.get_ansible_config(
            'dump',
            playbook.config,
            private_data_dir=dir,
            quiet=True,
        )[0]

        for opt, pw_type in _CONFIG_PASSWORD_OPTS.items():
            val = eval(next(
                x for x in raw_config.split('\n')
                if x.startswith(opt)
            ).split('= ')[1])
            if val:
                pw_types.add(pw_type)

    return list(pw_types)


def validate_aoh_password(playbook, password):
    """Determine whether a provided AoH password is valid for a playbook."""

    if not playbook.password:
        return True
    if password is None:
        return False

    with open(_PASSWORDS_FILE, 'r') as f:
        hash = yaml.safe_load(f).get(playbook.name)
        return bcrypt.checkpw(password.encode(), hash.encode())
