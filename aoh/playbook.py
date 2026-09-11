import os

import yaml

from .config import AOH_PLAYBOOKS_FILE
from .security import CLI_OPT_BLACKLIST

_PLAYBOOKS_DIR = os.path.dirname(AOH_PLAYBOOKS_FILE)


class PlaybookError(Exception):
    """Raised for AoH playbook configuration errors."""


class Playbook:
    def __init__(self, name, dict):
        """Parse a playbook configuration from a dictionary."""

        _types = {
            'path': str,
            'config': str,
            'host': str,
            'groups': list,
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
            if key in dict:
                if type(dict[key]) != _type:
                    raise PlaybookError(f'"{key}" field must be of type '
                                        f'{_type}')

                if  _type is list and any(type(x) != str for x in dict[key]):
                    raise PlaybookError(f'"{key}" elements must be of type str')

        self.name = name
        self.path = dict.get('path', name)
        self.config = dict.get('config', None)
        self.host = dict.get('host')
        self.groups = dict.get('groups', [])
        self.limit = dict.get('limit', True)
        self.password = dict.get('password', False)
        self.output = dict.get('output', True)
        self.allow_opts = dict.get('allow_opts', [])
        self.block_opts = dict.get('block_opts', [])
        self.jinja_args = dict.get('jinja_args', False)
        self.extra_args = dict.get('extra_args', [])
        self.web_description = dict.get('web_description')

        self.path = os.path.abspath(os.path.join(_PLAYBOOKS_DIR, self.path))
        self.config = os.path.abspath(os.path.join(_PLAYBOOKS_DIR, self.config))


        if self.limit:
            if '--limit' in self.allow_opts or '-l' in self.allow_opts:
                raise PlaybookError('allow_opts cannot contain "--limit" if '
                                    'limit is true')
            if '--limit' in self.extra_args or '-l' in self.extra_args:
                raise PlaybookError('extra_args cannot contain "--limit" if '
                                    'limit is true')

        for opt in CLI_OPT_BLACKLIST:
            if opt in self.allow_opts:
                raise PlaybookError(f'The "{opt}" option is not supported and '
                                    'cannot be included in allow_opts')
            if opt in self.extra_args:
                raise PlaybookError(f'The "{opt}" option is not supported and '
                                    'cannot be included in extra_args')


def get_playbook(name):
    """Lookup a playbook configuration."""

    with open(AOH_PLAYBOOKS_FILE, 'r') as f:
        CONFIG = yaml.safe_load(f)
        if name in CONFIG:
            return Playbook(name, CONFIG[name])
        else:
            return None
