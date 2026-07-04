"""
__init__.py — Flask Application Factory
========================================
The application factory pattern (`create_flask_application`) is the recommended
way to structure Flask apps. Instead of creating the `app` object at module
level (which breaks testing and multiple instances), we create it inside a
function and return it. This allows:

  • Multiple configurations (dev/test/prod) with zero code duplication.
  • Isolated test instances: each test function can spin up its own app
    with a fresh in-memory SQLite DB by calling the factory with TestingConfig.
  • Clean separation of concern: extensions are initialised here, not scattered
    across route files.

Call Stack on server start
---------------------------
  run.py
    └─► create_flask_application("development")
          ├─► Load config from DevelopmentConfig
          ├─► init_app(app) for each extension
          ├─► Register blueprints (auth, admin, staff, trekker)
          ├─► Configure Celery task queue
          └─► initialise_database_and_seed_admin(app)
"""

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
    """
    Factory function that constructs and returns a fully configured Flask app.

    This is the single entry point for assembling the application. It is called
    by `run.py` for development, by the WSGI server in production, and by pytest
    fixtures in the test suite — each with a different `environment_name`.

    Args:
        environment_name: One of "development", "testing", or "production".
                          Selects the matching config class from ENVIRONMENT_CONFIG_MAP.
                          Defaults to "development" so local `flask run` works out of the box.

    Returns:
        Flask: A fully initialised and configured Flask application instance.
    """

    # ------------------------------------------------------------------ #
    # 1. Instantiate the Flask core application                           #
    # ------------------------------------------------------------------ #
    # `instance_relative_config=True` makes Flask look for `instance/` directory
    # (outside the package) for secrets — a clean separation from source-tracked files.
    flask_app = Flask(__name__, instance_relative_config=True)

    # ------------------------------------------------------------------ #
    # 2. Load the appropriate configuration class                         #
    # ------------------------------------------------------------------ #
    selected_config_class = ENVIRONMENT_CONFIG_MAP.get(environment_name, DevelopmentConfig)
    flask_app.config.from_object(selected_config_class)

    # Validate production configuration requirements at runtime
    if environment_name == "production":
        if not flask_app.config.get("SECRET_KEY") or not flask_app.config.get("ADMIN_SEED_PASSWORD"):
            raise ValueError("Production mode requires FLASK_SECRET_KEY and ADMIN_SEED_PASSWORD environment variables to be set!")

    # ------------------------------------------------------------------ #
    # 3. Configure logging                                                 #
    # ------------------------------------------------------------------ #
    # Ensure meaningful log output is visible even before the first request.
    logging.basicConfig(
        level=logging.DEBUG if flask_app.config.get("DEBUG") else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    flask_app.logger.info(
        f"Flask application starting with config: {selected_config_class.__name__}"
    )

    # ------------------------------------------------------------------ #
    # 4. Initialise Flask extensions (deferred binding)                   #
    # ------------------------------------------------------------------ #
    # Extensions were instantiated without an app in extensions.py.
    # `init_app` binds them to this specific Flask instance now.
    database_extension.init_app(flask_app)
    jwt_manager_extension.init_app(flask_app)
    flask_cache_extension.init_app(flask_app)

    # ------------------------------------------------------------------ #
    # 5. CORS — Cross-Origin Resource Sharing                             #
    # ------------------------------------------------------------------ #
    # The Vue.js SPA runs on a different port (5173 via Vite or from CDN),
    # so we must explicitly allow cross-origin requests from the frontend.
    # In production, restrict `origins` to the actual deployed frontend URL.
    CORS(
        flask_app,
        origins=flask_app.config.get("ALLOWED_CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5500"]),
        supports_credentials=True,  # Required for cookie-based JWT transport.
    )

    # ------------------------------------------------------------------ #
    # 6. Configure and integrate Celery                                   #
    # ------------------------------------------------------------------ #
    _configure_celery_with_flask_app_context(flask_app)

    # ------------------------------------------------------------------ #
    # 7. Register API Blueprints                                           #
    # ------------------------------------------------------------------ #
    # Each blueprint encapsulates a logical group of routes.
    # They are imported here (inside the factory) to avoid circular imports —
    # the route modules import `db` from extensions.py, not from this factory.
    _register_api_blueprints(flask_app)

    # ------------------------------------------------------------------ #
    # 8. JWT error handler customisation                                   #
    # ------------------------------------------------------------------ #
    _register_jwt_error_handlers(flask_app)

    # ------------------------------------------------------------------ #
    # 9. Programmatic DB init + admin seeding                             #
    # ------------------------------------------------------------------ #
    # This call is safe to make on every startup — it checks for existing
    # tables/admin before doing anything, making it fully idempotent.
    initialise_database_and_seed_admin(flask_app)

    flask_app.logger.info("Application factory completed. Flask app is ready.")
    return flask_app


# --------------------------------------------------------------------------- #
# Private Helper: Celery Configuration                                         #
# --------------------------------------------------------------------------- #

def _configure_celery_with_flask_app_context(flask_app: Flask) -> None:
    """
    Binds the Celery task queue to this Flask app's configuration and
    injects a Flask application context into every Celery task execution.

    WHY is context injection needed?
    ----------------------------------
    Celery worker processes are separate OS processes from the Flask dev server.
    When a Celery task tries to use SQLAlchemy (`db.session.query(...)`) or
    Flask-Caching, those extensions need an active Flask application context to
    find the database URI and Redis URL from `app.config`. Without this custom
    Task base class, every task would crash with "RuntimeError: Working outside
    of application context".

    The `ContextTask` inner class overrides Celery's `__call__` to wrap each
    task invocation in a `with flask_app.app_context():` block automatically.

    Args:
        flask_app: The Flask application instance whose config Celery will inherit.
    """
    # Copy Flask config keys into Celery's own config namespace.
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
        """
        Custom Celery Task base class that automatically pushes a Flask
        application context before each task function runs and pops it
        after the task completes (even on exception).
        """
        abstract = True  # Prevents Celery from registering this class as a runnable task.

        def __call__(self, *task_args, **task_kwargs):
            with flask_app.app_context():
                return self.run(*task_args, **task_kwargs)

    # Override Celery's default Task class so all tasks in `tasks.py`
    # (which use `@celery_task_queue.task`) automatically use ContextAwareCeleryTask.
    celery_task_queue.Task = ContextAwareCeleryTask


# --------------------------------------------------------------------------- #
# Private Helper: Blueprint Registration                                        #
# --------------------------------------------------------------------------- #

def _register_api_blueprints(flask_app: Flask) -> None:
    """
    Registers all API route blueprints under the `/api` URL prefix.

    Blueprint registration is deferred to inside the factory (not at module
    import time) to avoid circular dependencies: route modules import
    `database_extension` from extensions.py, which must already be initialised.

    URL Scheme
    ----------
      /api/auth/*    — unauthenticated endpoints (login, register, logout)
      /api/admin/*   — admin-only CRUD endpoints
      /api/staff/*   — staff-only endpoints
      /api/trekker/* — trekker self-service endpoints
    """
    from .auth_routes import authentication_blueprint
    from .admin_routes import admin_operations_blueprint
    from .staff_routes import staff_operations_blueprint
    from .trekker_routes import trekker_selfservice_blueprint

    flask_app.register_blueprint(authentication_blueprint, url_prefix="/api/auth")
    flask_app.register_blueprint(admin_operations_blueprint, url_prefix="/api/admin")
    flask_app.register_blueprint(staff_operations_blueprint, url_prefix="/api/staff")
    flask_app.register_blueprint(trekker_selfservice_blueprint, url_prefix="/api/trekker")

    flask_app.logger.debug("All API blueprints registered successfully.")


# --------------------------------------------------------------------------- #
# Private Helper: JWT Error Handlers                                            #
# --------------------------------------------------------------------------- #

def _register_jwt_error_handlers(flask_app: Flask) -> None:
    """
    Registers custom JSON error responses for JWT authentication failures.

    Without these handlers, Flask-JWT-Extended returns HTML error pages by
    default, which break the Vue.js SPA's `fetch()` error handling. JSON
    responses with consistent error structures allow the frontend to display
    meaningful messages in the UI instead of raw HTML.
    """
    from flask import jsonify

    @jwt_manager_extension.expired_token_loader
    def handle_expired_access_token(jwt_header, jwt_payload):
        """Returns HTTP 401 when the JWT has passed its expiry timestamp."""
        return jsonify({
            "authentication_error": "Your session has expired. Please log in again.",
            "error_code": "TOKEN_EXPIRED"
        }), 401

    @jwt_manager_extension.invalid_token_loader
    def handle_invalid_token_structure(validation_error_message):
        """Returns HTTP 422 when the JWT is malformed or has an invalid signature."""
        return jsonify({
            "authentication_error": "Invalid authentication token.",
            "error_code": "TOKEN_INVALID",
            "detail": validation_error_message
        }), 422

    @jwt_manager_extension.unauthorized_loader
    def handle_missing_auth_token(reason):
        """Returns HTTP 401 when no JWT is present on a protected route."""
        return jsonify({
            "authentication_error": "Authentication token is required for this endpoint.",
            "error_code": "TOKEN_MISSING",
            "detail": reason
        }), 401
