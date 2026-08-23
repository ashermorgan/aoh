from dotenv import load_dotenv

from .server import app, scheduler


def create_app():
    load_dotenv()
    scheduler.start()
    return app
