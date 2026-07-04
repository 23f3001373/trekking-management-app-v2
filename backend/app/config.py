"""
config.py — Application Configuration Module
=============================================
Defines hierarchical configuration classes using a base + environment-specific
inheritance pattern. This approach keeps secrets out of source control,
centralizes all tuneable parameters, and makes environment switching (dev/prod)
a single environment-variable change rather than a code edit.

Why a class-based config instead of a flat .env file?
  - Allows computed/derived values (e.g., SQLALCHEMY_DATABASE_URI built from parts).
  - Enables typed defaults and IDE auto-complete.
  - Integrates cleanly with Flask's `app.config.from_object()`.
"""

import os
from datetime import timedelta


class BaseApplicationConfig:
    """
    BaseApplicationConfig — shared settings inherited by all environments.

    Every environment (development, testing, production) extends this class
    and overrides only what differs. Common values live here exactly once,
    avoiding duplication-driven drift between environment configs.
    """

    # ------------------------------------------------------------------ #
    # Flask Core                                                           #
    # ------------------------------------------------------------------ #

    # Secret key for session signing and CSRF protection.
    # In production this MUST come from an environment variable, never hardcoded.
    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY", "trek-app-v2-dev-secret-change-in-prod")

    # ------------------------------------------------------------------ #
    # Database — SQLite via SQLAlchemy                                     #
    # ------------------------------------------------------------------ #

    # Absolute path to the SQLite database file.
    # `os.path.abspath` ensures portability across different working directories.
    _BASE_DIR: str = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.abspath(os.path.join(_BASE_DIR, '..', 'instance', 'trekking_platform.db')).replace('\\\\', '/').replace('\\', '/')}"
    )

    # Disable SQLAlchemy's event system modification tracking to save memory
    # overhead — we don't need it since we manage our own session lifecycle.
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # Enable connection pooling pre-ping to gracefully handle stale SQLite
    # file locks that can appear after long idle periods in dev.
    SQLALCHEMY_ENGINE_OPTIONS: dict = {"pool_pre_ping": True}

    # ------------------------------------------------------------------ #
    # JWT Authentication (Flask-JWT-Extended)                              #
    # ------------------------------------------------------------------ #

    # Access token lifetime — short-lived to limit blast radius if stolen.
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(hours=1)

    # Refresh token lifetime — longer, stored securely, used only to mint new access tokens.
    JWT_REFRESH_TOKEN_EXPIRES: timedelta = timedelta(days=7)

    # Store JWTs in HTTP-only cookies so they are inaccessible to JavaScript
    # (XSS protection). CSRF double-submit cookies are then auto-enabled.
    JWT_TOKEN_LOCATION: list = ["headers"]

    # ------------------------------------------------------------------ #
    # Redis — shared between Flask-Caching and Celery                     #
    # ------------------------------------------------------------------ #

    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # ------------------------------------------------------------------ #
    # Flask-Caching (Redis backend)                                        #
    # ------------------------------------------------------------------ #

    CACHE_TYPE: str = "RedisCache"
    CACHE_REDIS_URL: str = REDIS_URL
    # Default TTL for cached responses: 5 minutes. Trek listings change
    # infrequently but must stay fresh after bookings or admin edits.
    CACHE_DEFAULT_TIMEOUT: int = 300

    # ------------------------------------------------------------------ #
    # Celery Distributed Task Queue                                        #
    # ------------------------------------------------------------------ #

    # Use Redis as both the message broker (job queue) and the result backend
    # (where task return values and status are stored).
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL

    # Serialise task arguments and results as JSON rather than the default
    # pickle — JSON is language-agnostic and avoids arbitrary code execution
    # vulnerabilities present in pickle-based deserialization.
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: list = ["json"]

    # Timezone alignment — all scheduled Celery beats fire in IST context.
    CELERY_TIMEZONE: str = "Asia/Kolkata"
    CELERY_ENABLE_UTC: bool = True

    # ------------------------------------------------------------------ #
    # Email / SMTP (used by Celery reminder tasks)                         #
    # ------------------------------------------------------------------ #

    MAIL_SERVER: str = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT: int = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS: bool = True
    MAIL_USERNAME: str = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER: str = os.environ.get("MAIL_SENDER", "noreply@trekkingplatform.com")
    GOOGLE_CHAT_WEBHOOK_URL: str = os.environ.get("GOOGLE_CHAT_WEBHOOK_URL", "")

    # ------------------------------------------------------------------ #
    # Application-level business constants                                 #
    # ------------------------------------------------------------------ #

    # Prefix used for all Redis cache keys to namespace them and avoid
    # collisions with other applications sharing the same Redis instance.
    CACHE_KEY_PREFIX_OPEN_TREKS: str = "trek_platform:open_treks:"

    # Admin seed credentials — used only if no Admin user exists in the DB.
    # Override these via environment variables in any real deployment.
    ADMIN_SEED_EMAIL: str = os.environ.get("ADMIN_SEED_EMAIL", "admin@trekapp.com")
    ADMIN_SEED_PASSWORD: str = os.environ.get("ADMIN_SEED_PASSWORD", "Admin@SecurePass123")
    ADMIN_SEED_FULL_NAME: str = "Platform Administrator"


class DevelopmentConfig(BaseApplicationConfig):
    """
    DevelopmentConfig — settings optimised for local development.

    Enables Flask's built-in debugger and reloader. Debug mode must NEVER
    be True in production — it exposes an interactive Python console.
    """
    DEBUG: bool = True
    TESTING: bool = False

    # In dev we print SQL queries to stdout to make ORM behaviour transparent.
    SQLALCHEMY_ECHO: bool = True


class TestingConfig(BaseApplicationConfig):
    """
    TestingConfig — settings for the automated test suite.

    Uses an in-memory SQLite database so tests are fully isolated,
    fast, and leave no artefacts on disk.
    """
    DEBUG: bool = False
    TESTING: bool = True

    # In-memory DB: created fresh for each test session, destroyed on exit.
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"

    # Disable CSRF protection in tests so forms can be submitted programmatically.
    WTF_CSRF_ENABLED: bool = False

    # Use a simple in-memory dict cache in tests to avoid needing a live Redis.
    CACHE_TYPE: str = "SimpleCache"


class ProductionConfig(BaseApplicationConfig):
    """
    ProductionConfig — hardened settings for deployment.

    DEBUG is off, secrets come exclusively from environment variables,
    and SQLAlchemy query echo is suppressed to avoid log leakage.
    """
    DEBUG: bool = False
    TESTING: bool = False
    SQLALCHEMY_ECHO: bool = False

    # In production, we get keys safely here and validate them at runtime during app construction.
    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY", "")
    ADMIN_SEED_PASSWORD: str = os.environ.get("ADMIN_SEED_PASSWORD", "")


# ------------------------------------------------------------------ #
# Config registry — maps string names to config classes.             #
# The FLASK_ENV environment variable selects the active profile.     #
# ------------------------------------------------------------------ #
ENVIRONMENT_CONFIG_MAP: dict = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

# Default to development if FLASK_ENV is not explicitly set.
active_config = ENVIRONMENT_CONFIG_MAP.get(
    os.environ.get("FLASK_ENV", "development"),
    DevelopmentConfig,
)
