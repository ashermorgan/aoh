from .server import app, scheduler


def create_app():
    scheduler.start()
    return app
