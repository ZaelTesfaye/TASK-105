import os
from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

from .config import config_map, Config
from .extensions import db, migrate, socketio, scheduler
from .errors import register_error_handlers
from .middleware import register_middleware
from .crypto import init_fernet


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_map.get(config_name, Config))

    # --- Fernet encryption key ---
    init_fernet(app.config["FERNET_KEY_PATH"])

    # --- WebSocket event handlers ---
    # Import BEFORE socketio.init_app so @socketio.on decorators queue handlers
    # in socketio.handlers (server is still None).  Every subsequent init_app
    # call then re-registers those handlers on the new server, which is required
    # when create_app is called more than once in a test session.
    from . import websocket  # noqa: F401

    # --- Extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    async_mode = app.config.get("SOCKETIO_ASYNC_MODE", "threading")
    socketio.init_app(app, async_mode=async_mode)

    # Enable WAL mode for SQLite
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        if isinstance(dbapi_conn, sqlite3.Connection):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # --- Middleware ---
    register_middleware(app)

    # --- Blueprints ---
    _register_blueprints(app)

    # --- Error handlers ---
    register_error_handlers(app)

    # --- STOMP WebSocket endpoint ---
    from .stomp_ws import register_stomp
    register_stomp(app)

    # --- Background jobs ---
    if app.config.get("JOBS_ENABLED"):
        with app.app_context():
            _start_scheduler(app)

    return app


def _register_blueprints(app: Flask) -> None:
    from .routes.health import health_bp
    from .routes.auth import auth_bp
    from .routes.users import users_bp
    from .routes.communities import communities_bp
    from .routes.commission import commission_bp
    from .routes.catalog import catalog_bp
    from .routes.search import search_bp
    from .routes.inventory import inventory_bp
    from .routes.messaging import messaging_bp
    from .routes.content import content_bp
    from .routes.templates import templates_bp
    from .routes.admin import admin_bp

    # Health probes (no version prefix — standard convention)
    app.register_blueprint(health_bp)

    v1 = "/api/v1"
    app.register_blueprint(auth_bp, url_prefix=v1)
    app.register_blueprint(users_bp, url_prefix=v1)
    app.register_blueprint(communities_bp, url_prefix=v1)
    app.register_blueprint(commission_bp, url_prefix=v1)
    app.register_blueprint(catalog_bp, url_prefix=v1)
    app.register_blueprint(search_bp, url_prefix=v1)
    app.register_blueprint(inventory_bp, url_prefix=v1)
    app.register_blueprint(messaging_bp, url_prefix=v1)
    app.register_blueprint(content_bp, url_prefix=v1)
    app.register_blueprint(templates_bp, url_prefix=v1)
    app.register_blueprint(admin_bp, url_prefix=v1)


def _start_scheduler(app: Flask) -> None:
    from .jobs import register_jobs
    register_jobs(scheduler, app)
    if not scheduler.running:
        scheduler.start()
