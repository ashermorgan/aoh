import yaml

CONFIG_FILE = 'config.yml' # TODO: make configurable

DEFAULT_OPT_WHITELIST = [
    # These options should be safe for clients to invoke
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

OPT_BLACKLIST = [
    # These options are not supported at all because they are interactive
    '--step',
    '-J', '--ask-vault-password', '--ask-vault-pass',
    '-K', '--ask-become-pass',
    '-c', '--connection,',
    '-k', '--ask-pass',
]


class PlaybookError(Exception):
    """Raised for AoH playbook configuration errors."""


class Playbook:
    def __init__(self, dict):
        """Parse a playbook configuration from a dictionary."""

        _types = {
            'playbook': str,
            'config': str,
            'cmdline': str,
            'output': bool,
            'jinja': bool,
            'allow_opts': list, # We'll just assume that elements are strings
            'block_opts': list,
        }

        if 'playbook' not in dict:
            raise PlaybookError('"playbook" field missing')

        for key, _type in _types.items():
            if key in dict and type(dict[key]) != _type:
                raise PlaybookError(f'"{key}" field must be of type {_type}')

        self.playbook = dict['playbook']
        self.config = dict.get('config', None)
        self.cmdline = dict.get('cmdline', '')
        self.output = dict.get('output', True)
        self.jinja = dict.get('jinja', False)
        self.allow_opts = dict.get('allow_opts', [])
        self.block_opts = dict.get('block_opts', [])


    def validate_args(self, args):
        """Determine if arguments pass the playbook's security policies."""

        cmdline = ' '.join(args)
        if not self.jinja and ('{{' in cmdline or '{%' in cmdline):
            return False

        opts = []
        for arg in args:
            if arg.startswith('--'):
                opts += [arg.split('=')[0]]
            elif arg.startswith('-'):
                for opt in arg.split('=')[0][1:]:
                    opts += ['-' + opt]

        for opt in opts:
            if (not (opt in DEFAULT_OPT_WHITELIST or opt in self.allow_opts) or
                    (opt in OPT_BLACKLIST or opt in self.block_opts)):
                return False

        return True


def get_playbook(playbook):
    """Lookup a playbook configuration."""

    with open(CONFIG_FILE, 'r') as f:
        CONFIG = yaml.safe_load(f)
        if playbook in CONFIG:
            return Playbook(CONFIG[playbook])
        else:
            return None
