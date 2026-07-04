"""
extensions.py — Shared Flask Extension Instances
=================================================
This module instantiates all third-party Flask extensions WITHOUT binding
them to a specific Flask application. Binding happens later inside the
app factory (`__init__.py`) via `extension.init_app(flask_app)`.

WHY the Application Factory + extensions.py pattern?
-----------------------------------------------------
Flask extensions are designed to be instantiated once and shared. If we
created extension objects inside the app factory, circular imports would
arise the moment any model or route module tried to import `db` for its
ORM class definitions. The solution is a dedicated module that:
  1. Creates the extension objects (no app bound yet).
  2. Gets imported by models.py, routes, and the factory alike.
  3. Gets initialised (bound to the app) exclusively inside the factory.

This pattern is sometimes called "Deferred Initialisation" and is the
recommended approach in the official Flask documentation.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_caching import Cache
from celery import Celery


# --------------------------------------------------------------------------- #
# SQLAlchemy ORM — relational data persistence layer                          #
# --------------------------------------------------------------------------- #
# `db` is the central SQLAlchemy instance. All ORM models import this object
# and subclass `db.Model`. The actual engine/connection pool is not created
# until `db.init_app(app)` runs inside the factory.
database_extension = SQLAlchemy()


# --------------------------------------------------------------------------- #
# JWT Manager — stateless authentication via JSON Web Tokens                  #
# --------------------------------------------------------------------------- #
# Handles token creation, verification, refresh, and revocation callbacks.
# Configuration (secret key, expiry times) is read from `app.config` at
# init time, so there is no secret hardcoded here.
jwt_manager_extension = JWTManager()


# --------------------------------------------------------------------------- #
# Flask-Caching — Redis-backed response caching                               #
# --------------------------------------------------------------------------- #
# Used to cache the "open treks" listing endpoint so repeated reads by many
# concurrent Trekker users do not hammer SQLite with identical SELECT queries.
# Cache invalidation is triggered manually whenever trek state changes.
flask_cache_extension = Cache()


# --------------------------------------------------------------------------- #
# Celery — distributed asynchronous task queue                                #
# --------------------------------------------------------------------------- #
# Celery is not a Flask extension in the traditional sense; it doesn't have
# an `init_app` method. Instead, we configure it directly inside the factory
# using `celery_task_queue.config_from_object(app.config)` and tie its
# execution context to the Flask app via a custom task base class.
# See `__init__.py` for the full factory wiring.
celery_task_queue = Celery()
