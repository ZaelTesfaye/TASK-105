"""
Singleton extension instances — imported by the app factory and individual modules.
Never import `app` from here; always use Flask's application context.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from apscheduler.schedulers.background import BackgroundScheduler

db = SQLAlchemy()
migrate = Migrate()
# async_mode is set in create_app via SOCKETIO_ASYNC_MODE config key.
# Default: "threading" (works everywhere). Production: set to "eventlet" or "gevent".
socketio = SocketIO(cors_allowed_origins="*")
scheduler = BackgroundScheduler(timezone="UTC")
