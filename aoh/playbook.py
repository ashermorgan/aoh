import os

import yaml

PLAYBOOKS_FILE = os.getenv('AOH_PLAYBOOKS_FILE', 'playbooks.yml')
PLAYBOOKS_DIR = os.getenv('AOH_PLAYBOOKS_DIR', os.path.dirname(PLAYBOOKS_FILE))



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
            'password': bool,
            'output': bool,
            'jinja': bool,
            'allow_opts': list,
            'block_opts': list,
            'extra_args': list,
            'web_description': str,
        }

        for key, _type in _types.items():
            if key in dict and type(dict[key]) != _type:
                raise PlaybookError(f'"{key}" field must be of type {_type}')

            if  _type is list and any(type(x) != str for x in dict[key]):
                raise PlaybookError(f'"{key}" elements must be of type str')

        self.name = name
        self.path = dict.get('path', name)
        self.config = dict.get('config', None)
        self.host = dict.get('host')
        self.groups = dict.get('groups', [])
        self.password = dict.get('password', False)
        self.output = dict.get('output', True)
        self.jinja = dict.get('jinja', False)
        self.allow_opts = dict.get('allow_opts', [])
        self.block_opts = dict.get('block_opts', [])
        self.extra_args = dict.get('extra_args', [])
        self.web_description = dict.get('web_description')

        self.path = os.path.abspath(os.path.join(PLAYBOOKS_DIR, self.path))
        self.config = os.path.abspath(os.path.join(PLAYBOOKS_DIR, self.config))


def get_playbook(name):
    """Lookup a playbook configuration."""

    with open(PLAYBOOKS_FILE, 'r') as f:
        CONFIG = yaml.safe_load(f)
        if name in CONFIG:
            return Playbook(name, CONFIG[name])
        else:
            return None
