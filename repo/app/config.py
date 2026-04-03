import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///data/db.sqlite3")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # WAL mode enabled in extensions.py via SQLite pragma event
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}

    FERNET_KEY_PATH = os.environ.get("FERNET_KEY_PATH", "data/keys/secret.key")
    APP_VERSION = os.environ.get("APP_VERSION", "0.1.0")

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE", "data/logs/app.jsonl")

    ATTACHMENT_DIR = os.environ.get("ATTACHMENT_DIR", "data/attachments")
    ATTACHMENT_MAX_BYTES = int(os.environ.get("ATTACHMENT_MAX_BYTES", 26_214_400))
    ATTACHMENT_ALLOWED_MIME = {"image/png", "image/jpeg", "application/pdf", "text/plain", "text/markdown"}

    JOBS_ENABLED = os.environ.get("JOBS_ENABLED", "true").lower() == "true"
    BCRYPT_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", 12))

    # Search
    SEARCH_HISTORY_CAP = 50
    SEARCH_PAGE_SIZE_MAX = 100


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "db.sqlite3"
        ),
    )


class TestingConfig(Config):
    TESTING = True
    # Avoid disk writes on every HTTP request during tests (major perf win for benchmarks).
    LOG_FILE = os.environ.get("LOG_FILE", os.devnull)
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # StaticPool: all connections share one in-memory DB, required for
    # WebSocket tests where Flask-SocketIO handlers run in a separate thread.
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
