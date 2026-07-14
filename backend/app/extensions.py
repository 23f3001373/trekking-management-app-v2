

from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_caching import Cache
from celery import Celery

database_extension = SQLAlchemy()

jwt_manager_extension = JWTManager()

# check credentials
flask_cache_extension = Cache()

celery_task_queue = Celery()
