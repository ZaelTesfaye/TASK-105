"""
Flask configuration classes.

All environment variables are read from the ``config`` package (Single Source
of Truth).  These classes adapt those values into Flask's config interface and
provide environment-specific overrides (development / testing / production).
"""
import os

from config import settings


class Config:
    SECRET_KEY = settings.SECRET_KEY
    SQLALCHEMY_DATABASE_URI = settings.DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # WAL mode enabled in extensions.py via SQLite pragma event
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}

    FERNET_KEY_PATH = settings.FERNET_KEY_PATH
    APP_VERSION = settings.APP_VERSION

    LOG_LEVEL = settings.LOG_LEVEL
    LOG_FILE = settings.LOG_FILE

    ATTACHMENT_DIR = settings.ATTACHMENT_DIR
    ATTACHMENT_MAX_BYTES = settings.ATTACHMENT_MAX_BYTES
    ATTACHMENT_ALLOWED_MIME = settings.ATTACHMENT_ALLOWED_MIME

    JOBS_ENABLED = settings.JOBS_ENABLED
    BCRYPT_ROUNDS = settings.BCRYPT_ROUNDS

    ENABLE_TLS = settings.ENABLE_TLS

    # Search
    SEARCH_HISTORY_CAP = settings.SEARCH_HISTORY_CAP
    SEARCH_PAGE_SIZE_MAX = settings.SEARCH_PAGE_SIZE_MAX


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_DATABASE_URI = settings.DATABASE_URL if settings.DATABASE_URL != "sqlite:///data/db.sqlite3" else (
        "sqlite:///" + os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "db.sqlite3"
        )
    )


class TestingConfig(Config):
    TESTING = True
    LOG_FILE = settings.LOG_FILE if settings.LOG_FILE != "data/logs/app.jsonl" else os.devnull
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": __import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
    }
    JOBS_ENABLED = False
    WTF_CSRF_ENABLED = False
    BCRYPT_ROUNDS = 4


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
