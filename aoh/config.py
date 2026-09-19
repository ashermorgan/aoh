import logging
import os
import sys
from urllib.parse import urlsplit

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

AOH_DEBUG = (os.getenv('AOH_DEBUG', '0') == '1')

AOH_LOG_LEVEL = os.getenv('AOH_LOG_LEVEL', 'ERROR')

try:
    AOH_MAX_RUNNERS = int(os.getenv('AOH_MAX_RUNNERS', '0'))
except ValueError:
    logger.critical('$AOH_MAX_RUNNERS must be a non-negative integer')
    sys.exit(1)
if AOH_MAX_RUNNERS < 0:
    logger.critical('$AOH_MAX_RUNNERS must be a non-negative integer')
    sys.exit(1)

AOH_ORIGIN = os.getenv('AOH_ORIGIN')
if AOH_ORIGIN is not None:
    try:
        parts = urlsplit(AOH_ORIGIN)
        if parts.scheme == '' or parts.path != '':
            logger.critical('$AOH_ORIGIN is not a valid origin')
            sys.exit(1)
    except ValueError:
        logger.critical('$AOH_ORIGIN is not a valid origin')
        sys.exit(1)

AOH_PLAYBOOKS_FILE = os.getenv('AOH_PLAYBOOKS_FILE', 'playbooks.yml')
if not os.path.exists(AOH_PLAYBOOKS_FILE):
    logger.warning('$AOH_PLAYBOOKS_FILE does not exist')
AOH_PLAYBOOKS_DIR = os.path.dirname(AOH_PLAYBOOKS_FILE)

AOH_PASSWORDS_FILE = os.getenv('AOH_PASSWORDS_FILE', 'passwords.yml')
if not os.path.exists(AOH_PASSWORDS_FILE):
    logger.warning('$AOH_PASSWORDS_FILE does not exist')
