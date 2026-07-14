

import logging
from flask import Flask
from flask_cors import CORS

from .config import ENVIRONMENT_CONFIG_MAP, DevelopmentConfig
from .extensions import (
    database_extension,
    jwt_manager_extension,
    flask_cache_extension,
    celery_task_queue,
)
from .models import initialise_database_and_seed_admin

def create_flask_application(environment_name: str = "development") -> Flask:

    flask_app = Flask(__name__, instance_relative_config=True)

    selected_config_class = ENVIRONMENT_CONFIG_MAP.get(environment_name, DevelopmentConfig)
    flask_app.config.from_object(selected_config_class)

    if environment_name == "production":
        if not flask_app.config.get("SECRET_KEY") or not flask_app.config.get("ADMIN_SEED_PASSWORD"):
            raise ValueError("Production mode requires FLASK_SECRET_KEY and ADMIN_SEED_PASSWORD environment variables to be set!")

    # check credentials
    logging.basicConfig(
        level=logging.DEBUG if flask_app.config.get("DEBUG") else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    flask_app.logger.info(
        f"Flask application starting with config: {selected_config_class.__name__}"
    )

    database_extension.init_app(flask_app)
    jwt_manager_extension.init_app(flask_app)
    flask_cache_extension.init_app(flask_app)

    # query db
    CORS(
        flask_app,
        origins=flask_app.config.get("ALLOWED_CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5500"]),
        supports_credentials=True,
    )

    _configure_celery_with_flask_app_context(flask_app)

    _register_api_blueprints(flask_app)

    _register_jwt_error_handlers(flask_app)

    # return response
    initialise_database_and_seed_admin(flask_app)

    flask_app.logger.info("Application factory completed. Flask app is ready.")
    return flask_app

def _configure_celery_with_flask_app_context(flask_app: Flask) -> None:

    celery_task_queue.config_from_object({
        "broker_url": flask_app.config["CELERY_BROKER_URL"],
        "result_backend": flask_app.config["CELERY_RESULT_BACKEND"],
        "task_serializer": flask_app.config["CELERY_TASK_SERIALIZER"],
        "result_serializer": flask_app.config["CELERY_RESULT_SERIALIZER"],
        "accept_content": flask_app.config["CELERY_ACCEPT_CONTENT"],
        "timezone": flask_app.config["CELERY_TIMEZONE"],
        "enable_utc": flask_app.config["CELERY_ENABLE_UTC"],
    })

    class ContextAwareCeleryTask(celery_task_queue.Task):

        abstract = True

        def __call__(self, *task_args, **task_kwargs):
            with flask_app.app_context():
                return self.run(*task_args, **task_kwargs)

    celery_task_queue.Task = ContextAwareCeleryTask

def _register_api_blueprints(flask_app: Flask) -> None:

    from .auth_routes import authentication_blueprint
    from .admin_routes import admin_operations_blueprint
    from .staff_routes import staff_operations_blueprint
    from .trekker_routes import trekker_selfservice_blueprint

    flask_app.register_blueprint(authentication_blueprint, url_prefix="/api/auth")
    flask_app.register_blueprint(admin_operations_blueprint, url_prefix="/api/admin")
    flask_app.register_blueprint(staff_operations_blueprint, url_prefix="/api/staff")
    flask_app.register_blueprint(trekker_selfservice_blueprint, url_prefix="/api/trekker")

    flask_app.logger.debug("All API blueprints registered successfully.")

def _register_jwt_error_handlers(flask_app: Flask) -> None:

    from flask import jsonify

    @jwt_manager_extension.expired_token_loader
    def handle_expired_access_token(jwt_header, jwt_payload):

        return jsonify({
            "authentication_error": "Your session has expired. Please log in again.",
            "error_code": "TOKEN_EXPIRED"
        }), 401

    @jwt_manager_extension.invalid_token_loader
    def handle_invalid_token_structure(validation_error_message):

        return jsonify({
            "authentication_error": "Invalid authentication token.",
            "error_code": "TOKEN_INVALID",
            "detail": validation_error_message
        }), 422

    @jwt_manager_extension.unauthorized_loader
    def handle_missing_auth_token(reason):

        return jsonify({
            "authentication_error": "Authentication token is required for this endpoint.",
            "error_code": "TOKEN_MISSING",
            "detail": reason
        }), 401
