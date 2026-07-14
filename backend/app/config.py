

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class BaseApplicationConfig:

    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY", "trek-app-v2-dev-secret-change-in-prod")

    ALLOWED_CORS_ORIGINS: list = [
        origin.strip() for origin in os.environ.get("ALLOWED_CORS_ORIGINS", "").split(",") if origin.strip()
    ] or [
        "http://localhost:5173",
        "http://127.0.0.1:5500",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://127.0.0.1:5501",
        "http://localhost:5501"
    ]

    _BASE_DIR: str = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.abspath(os.path.join(_BASE_DIR, '..', 'instance', 'trekking_platform.db')).replace('\\\\', '/').replace('\\', '/')}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    SQLALCHEMY_ENGINE_OPTIONS: dict = {"pool_pre_ping": True}

    # check credentials

    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(hours=1)

    JWT_REFRESH_TOKEN_EXPIRES: timedelta = timedelta(days=7)

    JWT_TOKEN_LOCATION: list = ["headers"]

    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

    CACHE_TYPE: str = "RedisCache"
    CACHE_REDIS_URL: str = REDIS_URL
    CACHE_DEFAULT_TIMEOUT: int = 300

    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL

    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: list = ["json"]

    CELERY_TIMEZONE: str = "Asia/Kolkata"
    CELERY_ENABLE_UTC: bool = True

    # query db

    MAIL_SERVER: str = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT: int = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS: bool = True
    MAIL_USERNAME: str = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER: str = os.environ.get("MAIL_SENDER", "noreply@trekkingplatform.com")
    GOOGLE_CHAT_WEBHOOK_URL: str = os.environ.get("GOOGLE_CHAT_WEBHOOK_URL", "")

    CACHE_KEY_PREFIX_OPEN_TREKS: str = "trek_platform:open_treks:"

    ADMIN_SEED_EMAIL: str = os.environ.get("ADMIN_SEED_EMAIL", "admin@trekapp.com")
    ADMIN_SEED_PASSWORD: str = os.environ.get("ADMIN_SEED_PASSWORD", "Admin@SecurePass123")
    ADMIN_SEED_FULL_NAME: str = "Platform Administrator"

class DevelopmentConfig(BaseApplicationConfig):

    DEBUG: bool = True
    TESTING: bool = False

    SQLALCHEMY_ECHO: bool = True

class TestingConfig(BaseApplicationConfig):

    DEBUG: bool = False
    TESTING: bool = True

    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"

    WTF_CSRF_ENABLED: bool = False

    CACHE_TYPE: str = "SimpleCache"

class ProductionConfig(BaseApplicationConfig):

    DEBUG: bool = False
    TESTING: bool = False
    SQLALCHEMY_ECHO: bool = False

    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY", "")
    ADMIN_SEED_PASSWORD: str = os.environ.get("ADMIN_SEED_PASSWORD", "")

ENVIRONMENT_CONFIG_MAP: dict = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

active_config = ENVIRONMENT_CONFIG_MAP.get(
    os.environ.get("FLASK_ENV", "development"),
    DevelopmentConfig,
)
