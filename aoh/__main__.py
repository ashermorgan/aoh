from dotenv import load_dotenv

from .server import app, scheduler

load_dotenv()
scheduler.start()
app.run(debug=True)
