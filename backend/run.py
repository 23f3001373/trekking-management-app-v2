"""
run.py — Flask Development Server Entry Point
=============================================
This file is the standard entry point for running the Flask development server.

Usage:
    python run.py

Or with Flask CLI (recommended for production-like behaviour):
    flask --app run:flask_application_instance run --debug

Why a dedicated run.py instead of using `flask run` directly?
--------------------------------------------------------------
  1. Allows programmatic control over host/port (useful for Docker).
  2. Makes the entry point explicit for new developers reading the codebase.
  3. Enables pre-startup checks (e.g., verifying Redis is reachable) before
     accepting connections.
"""

import os
from app import create_flask_application

# The environment (development/testing/production) is read from FLASK_ENV.
# If unset, defaults to "development" inside create_flask_application.
active_environment = os.environ.get("FLASK_ENV", "development")

# Create the fully configured Flask application via the factory.
flask_application_instance = create_flask_application(active_environment)

if __name__ == "__main__":
    # `debug=False` here — debug mode is controlled via the config class,
    # not via this flag. Setting debug=True at the run() call level can
    # cause the factory to run twice due to the reloader's subprocess mechanism.
    flask_application_instance.run(
        host="0.0.0.0",   # Listen on all interfaces (required for Docker).
        port=int(os.environ.get("FLASK_PORT", 5000)),
        debug=flask_application_instance.config.get("DEBUG", False),
        use_reloader=flask_application_instance.config.get("DEBUG", False),
    )
