"""
Clean Config module — Single Source of Truth for all environment variables.

Every external configuration value is read here with type safety and sensible
defaults.  Application logic must never access ``os.environ`` / ``os.getenv``
directly; it should import from this module instead.
"""
import os


class Settings:
    """Type-safe, centralized environment configuration with defaults."""

    # --- Core ---
    FLASK_ENV: str = os.environ.get("FLASK_ENV", "development")
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    APP_VERSION: str = os.environ.get("APP_VERSION", "0.1.0")

    # --- Database ---
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///data/db.sqlite3")

    # --- Security / Encryption ---
    FERNET_KEY_PATH: str = os.environ.get("FERNET_KEY_PATH", "data/keys/secret.key")
    BCRYPT_ROUNDS: int = int(os.environ.get("BCRYPT_ROUNDS", "12"))
    ENABLE_TLS: bool = os.environ.get("ENABLE_TLS", "false").lower() == "true"

    # --- Logging ---
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.environ.get("LOG_FILE", "data/logs/app.jsonl")

    # --- Attachments ---
    ATTACHMENT_DIR: str = os.environ.get("ATTACHMENT_DIR", "data/attachments")
    ATTACHMENT_MAX_BYTES: int = int(os.environ.get("ATTACHMENT_MAX_BYTES", "26214400"))
    ATTACHMENT_ALLOWED_MIME: set = {
        "image/png", "image/jpeg", "application/pdf", "text/plain", "text/markdown",
    }

    # --- Background Jobs ---
    JOBS_ENABLED: bool = os.environ.get("JOBS_ENABLED", "true").lower() == "true"

    # --- Search ---
    SEARCH_HISTORY_CAP: int = 50
    SEARCH_PAGE_SIZE_MAX: int = 100


settings = Settings()
