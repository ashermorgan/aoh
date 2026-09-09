import logging

from .config import AOH_LOG_LEVEL
from .server import app, scheduler

logging.basicConfig()
logging.getLogger(__name__).setLevel(AOH_LOG_LEVEL)


def create_app():
    scheduler.start()
    return app
