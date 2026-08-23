import os
import tempfile

import ansible_runner
import yaml

CONFIG_FILE = 'config.yml' # TODO: make configurable

_CLI_OPT_WHITELIST = [
    # These options should be safe for clients to invoke
    '--ask-become-pass', '-K',
    '--ask-pass', '-k',
    '--ask-vault-password', '--ask-vault-pass', '-J',
    '--check', '-C',
    '--diff', '-D',
    '--extra-vars', '-e',
    '--help', '-h',
    '--limit', '-l',
    '--list-tags',
    '--skip-tags',
    '--start-at-task',
    '--step',
    '--tags', '-t',
    '--verbose', '-v',
    '--version',
]

_CLI_OPT_BLACKLIST = [
    # These options are not supported at all by AoH
    '--step',               # Interactive
    '-c', '--connection,',  # Conflicts with ansible_connection=aoh
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


def _get_opts(args):
    """Identify options present in a list of CLI arguments."""

    opts = []

    for arg in args:
        if arg == '--':
            break
        elif arg.startswith('--'):
            opts += [arg.split('=')[0]]
        elif arg.startswith('-'):
            for opt in arg.split('=')[0][1:]:
                opts += ['-' + opt]

    return opts


class PlaybookError(Exception):
    """Raised for AoH playbook configuration errors."""


class Playbook:
    def __init__(self, name, dict):
        """Parse a playbook configuration from a dictionary."""

        _types = {
            'path': str,
            'config': str,
            'cmdline': str,
            'output': bool,
            'jinja': bool,
            'allow_opts': list, # We'll just assume that elements are strings
            'block_opts': list,
        }

        for key, _type in _types.items():
            if key in dict and type(dict[key]) != _type:
                raise PlaybookError(f'"{key}" field must be of type {_type}')

        self.path = dict.get('path', name)
        self.config = dict.get('config', None)
        self.cmdline = dict.get('cmdline', '')
        self.output = dict.get('output', True)
        self.jinja = dict.get('jinja', False)
        self.allow_opts = dict.get('allow_opts', [])
        self.block_opts = dict.get('block_opts', [])

        # TODO: allow a default playbook dir to be specified?
        self.path = os.path.abspath(self.path)
        self.config = os.path.abspath(self.config)


    def validate_args(self, args):
        """Determine if arguments pass the playbook's security policies."""

        cmdline = ' '.join(args)
        if not self.jinja and ('{{' in cmdline or '{%' in cmdline):
            return False

        for opt in _get_opts(args):
            if (not (opt in _CLI_OPT_WHITELIST or opt in self.allow_opts) or
                    (opt in _CLI_OPT_BLACKLIST or opt in self.block_opts)):
                return False

        return True


    def get_required_passwords(self, args):
        """Determine what passwords the user must be prompted for."""

        pw_types = set()

        opts = _get_opts(args)
        for opt, pw_type in _CLI_PASSWORD_OPTS.items():
            if opt in opts:
                pw_types.add(pw_type)

        with tempfile.TemporaryDirectory(prefix='aoh-') as dir:
            raw_config = ansible_runner.get_ansible_config(
                'dump',
                self.config,
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


def get_playbook(name):
    """Lookup a playbook configuration."""

    with open(CONFIG_FILE, 'r') as f:
        CONFIG = yaml.safe_load(f)
        if name in CONFIG:
            return Playbook(name, CONFIG[name])
        else:
            return None
