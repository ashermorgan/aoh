from dotenv import load_dotenv

# Load config before importing app
load_dotenv()

from .server import app, scheduler


def create_app():
    scheduler.start()
    return app
