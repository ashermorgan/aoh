import os

import yaml

from aoh.config import AOH_PLAYBOOKS_DIR, AOH_PLAYBOOKS_FILE
from aoh.security import CLI_OPT_BLACKLIST

_ENV_VAR_BLACKLIST = [
    'ANSIBLE_FORCE_COLOR', 'ANSIBLE_NOCOLOR', 'NO_COLOR', # parsed client-side
]


class PlaybookFileError(Exception):
    """Raised for AoH playbook configuration errors."""


class Playbook:
    def __init__(self, name, raw):
        """Parse a playbook configuration from a dictionary."""

        _types = {
            'path': str,
            'host': str,
            'groups': list,
            'env': dict,
            'limit': bool,
            'password': bool,
            'output': bool,
            'allow_opts': list,
            'block_opts': list,
            'jinja_args': bool,
            'extra_args': list,
            'web_description': str,
        }

        for key, _type in _types.items():
            if key in raw:
                if type(raw[key]) != _type:
                    raise PlaybookFileError(f'"{key}" field must be of type '
                                            f'{_type}')

                if _type is list and any(type(x) != str for x in raw[key]):
                    raise PlaybookFileError(f'"{key}" elements must be of type '
                                            'str')

                if _type is dict and any(type(x) != str for x in
                                         raw[key].values()):
                    raise PlaybookFileError(f'"{key}" values must be of type '
                                            'str')

        self.name = name
        self.path = raw.get('path', name)
        self.host = raw.get('host')
        self.groups = raw.get('groups', [])
        self.env = raw.get('env', {})
        self.limit = raw.get('limit', True)
        self.password = raw.get('password', False)
        self.output = raw.get('output', True)
        self.allow_opts = raw.get('allow_opts', [])
        self.block_opts = raw.get('block_opts', [])
        self.jinja_args = raw.get('jinja_args', False)
        self.extra_args = raw.get('extra_args', [])
        self.web_description = raw.get('web_description')

        self.path = os.path.abspath(os.path.join(AOH_PLAYBOOKS_DIR, self.path))

        if self.limit:
            if '--limit' in self.allow_opts or '-l' in self.allow_opts:
                raise PlaybookFileError('allow_opts cannot contain "--limit" '
                                        'if limit is true')
            if '--limit' in self.extra_args or '-l' in self.extra_args:
                raise PlaybookFileError('extra_args cannot contain "--limit" '
                                        'if limit is true')

        for opt in CLI_OPT_BLACKLIST:
            if opt in self.allow_opts:
                raise PlaybookFileError(f'The "{opt}" option is not supported '
                                        'and cannot be included in allow_opts')
            if opt in self.extra_args:
                raise PlaybookFileError(f'The "{opt}" option is not supported '
                                        'and cannot be included in extra_args')

        for var in _ENV_VAR_BLACKLIST:
            if var in self.env:
                raise PlaybookFileError(f'The "{var}" variable is not supported'
                                        ' and cannot be included in env')


def get_playbook(name):
    """Lookup a playbook configuration."""

    with open(AOH_PLAYBOOKS_FILE, 'r') as f:
        try:
            PLAYBOOKS = yaml.safe_load(f)
        except yaml.YAMLError:
            raise PlaybookFileError('Failed to parse $AOH_PLAYBOOKS_FILE')

        if type(PLAYBOOKS) != dict:
            raise PlaybookFileError('$AOH_PASSWORDS_FILE must contain a '
                                    'dictionary of playbook entries')
        if name in PLAYBOOKS:
            return Playbook(name, PLAYBOOKS[name] or {})
        else:
            return None
