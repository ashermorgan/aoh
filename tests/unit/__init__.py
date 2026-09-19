import os
import unittest

# Prevent env issues in TestPlaybookGetPlaybook.test_default_values() test
os.environ['AOH_PLAYBOOKS_FILE'] = 'playbooks.yml'

from .test_playbook import *
from .test_security import *

if __name__ == '__main__':
    unittest.main()
