import logging
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

AOH_DEBUG = (os.getenv('AOH_DEBUG', '0') == '1')

try:
    AOH_MAX_RUNNERS = int(os.getenv('AOH_MAX_RUNNERS', '0'))
except ValueError:
    logger.warning('$AOH_MAX_RUNNERS must be a non-negative integer')
    AOH_MAX_RUNNERS = 0
if AOH_MAX_RUNNERS < 0:
    logger.warning('$AOH_MAX_RUNNERS must be a non-negative integer')
    AOH_MAX_RUNNERS = 0

AOH_ORIGIN = os.getenv('AOH_ORIGIN')
if AOH_ORIGIN is not None:
    try:
        parts = urlsplit(AOH_ORIGIN)
        if parts.scheme == '' or parts.path != '':
            logger.warning('$AOH_ORIGIN is not a valid origin')
            AOH_ORIGIN = None
    except ValueError:
        logger.warning('$AOH_ORIGIN is not a valid origin')
        AOH_ORIGIN = None

AOH_PLAYBOOKS_FILE = os.getenv('AOH_PLAYBOOKS_FILE', 'playbooks.yml')
if not os.path.exists(AOH_PLAYBOOKS_FILE):
    logger.warning('$AOH_PLAYBOOKS_FILE does not exist')

AOH_PASSWORDS_FILE = os.getenv('AOH_PASSWORDS_FILE', 'passwords.yml')
if not os.path.exists(AOH_PASSWORDS_FILE):
    logger.warning('$AOH_PASSWORDS_FILE does not exist')
