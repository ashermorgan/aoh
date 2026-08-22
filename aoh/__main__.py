from .server import app, scheduler

scheduler.start()
app.run(debug=True)
