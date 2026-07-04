"""
celery_worker.py — Celery Application Entry Point
==================================================
This module is the entry point for starting the Celery worker and beat
scheduler processes. It creates the Flask app, extracts the Celery instance
(which is already bound to the Flask app context via ContextAwareCeleryTask),
and applies the beat schedule.

Usage:
  # Start the task worker (processes queued tasks):
  celery -A celery_worker.celery_task_queue worker --loglevel=info --concurrency=4

  # Start the beat scheduler (enqueues periodic tasks on schedule):
  celery -A celery_worker.celery_task_queue beat --loglevel=info

  # Start both in one process (development only — NOT recommended for production):
  celery -A celery_worker.celery_task_queue worker --beat --loglevel=info

WHY is the Flask app created here?
------------------------------------
The Celery task queue instance in extensions.py is created without a Flask
app bound to it. The ContextAwareCeleryTask base class (configured in __init__.py)
needs the Flask app to push an application context before each task runs. By
importing `flask_application_instance` here (which triggers create_flask_application),
the Celery worker process has a fully configured Flask app in memory before
any tasks start executing.
"""

import os
from app import create_flask_application
from app.extensions import celery_task_queue
from app.tasks import CELERY_BEAT_PERIODIC_TASK_SCHEDULE

# Initialise the Flask application so that the Celery instance (celery_task_queue)
# gets fully configured with the Flask app context injector.
_worker_flask_app = create_flask_application(
    os.environ.get("FLASK_ENV", "development")
)

# Apply the Celery Beat schedule so the beat process knows which tasks to
# enqueue and when. This must be set AFTER the Flask app is created because
# the task functions (which are referenced in the schedule) must be imported
# within an app context.
celery_task_queue.conf.beat_schedule = CELERY_BEAT_PERIODIC_TASK_SCHEDULE
celery_task_queue.conf.timezone = _worker_flask_app.config.get("CELERY_TIMEZONE", "Asia/Kolkata")

# Autodiscover tasks from the `app.tasks` module so all @celery_task_queue.task
# decorated functions are registered with the worker.
celery_task_queue.autodiscover_tasks(["app"])
