"""
Celery Application Configuration

This module configures the Celery application for asynchronous task execution.

Features:
- Redis broker for message queue
- Scheduled tasks via Celery Beat
- Plugin-discovery task registration
- Production-ready configuration

Usage:
    # Start worker
    celery -A celery_app worker --loglevel=info

    # Start beat scheduler
    celery -A celery_app beat --loglevel=info

    # Start Flower monitoring
    celery -A celery_app flower
"""

import importlib
import os

from celery import Celery
from dotenv import load_dotenv

from app.plugin_loader import discover_plugins

# Load environment variables
load_dotenv('.env.local')
load_dotenv('.env')

# Celery configuration from environment
CELERY_BROKER_URL = os.getenv(
    'CELERY_BROKER_URL',
    'redis://localhost:6379/0'
)
CELERY_RESULT_BACKEND = os.getenv(
    'CELERY_RESULT_BACKEND',
    'redis://localhost:6379/0'
)

# Create Celery application
celery_app = Celery(
    'opama',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Timezone
    timezone='UTC',
    enable_utc=True,

    # Task execution
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 minutes soft limit

    # Worker configuration
    worker_prefetch_multiplier=1,  # Only fetch one task at a time
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks

    # Result backend
    result_expires=86400,  # Results expire after 24 hours
    result_backend_transport_options={
        'master_name': 'mymaster',
        'visibility_timeout': 3600,
    },

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Discover Celery tasks from every plugin (services/*/plugin.yaml plus any
# PLUGIN_PATHS external plugins — see app/plugin_loader.py). A plugin opts
# into Celery by shipping a `tasks` module alongside its router
# (<package>.tasks next to <package>.router, e.g. opama_pokemon_tcg.catalog.tasks)
# that exports `register_tasks(celery_app)` and, optionally, `TASK_ROUTES`
# / `BEAT_SCHEDULE` dicts merged into the config below. Plugins without a
# `tasks` module (the majority) are silently skipped, and relocating a
# plugin's package (e.g. into external_plugins/opama_<id>/) needs no change
# here — discover_plugins() finds it via PLUGIN_PATHS automatically.
task_routes: dict = {}
beat_schedule: dict = {}

for _manifest in discover_plugins():
    if _manifest.type != "local" or not _manifest.router_module:
        continue
    _tasks_path = _manifest.router_module.rsplit(".", 1)[0] + ".tasks"
    try:
        _tasks_module = importlib.import_module(_tasks_path)
    except ImportError:
        continue
    if hasattr(_tasks_module, "register_tasks"):
        _tasks_module.register_tasks(celery_app)
    task_routes.update(getattr(_tasks_module, "TASK_ROUTES", {}))
    beat_schedule.update(getattr(_tasks_module, "BEAT_SCHEDULE", {}))

celery_app.conf.task_routes = task_routes
celery_app.conf.beat_schedule = beat_schedule

__all__ = ['celery_app']


if __name__ == '__main__':
    # For debugging - print configuration
    print("=" * 60)
    print("Celery Configuration")
    print("=" * 60)
    print(f"Broker: {CELERY_BROKER_URL}")
    print(f"Backend: {CELERY_RESULT_BACKEND}")
    print("\nScheduled Tasks:")
    for name, config in celery_app.conf.beat_schedule.items():
        print(f"  - {name}")
        print(f"    Task: {config['task']}")
        print(f"    Schedule: {config['schedule']}")
    print("=" * 60)
