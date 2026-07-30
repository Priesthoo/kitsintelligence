"""
Celery application factory. Defines queues, task routing, and the periodic
beat schedule that drives continuous background hydration of external data
sources into Redis/Postgres -- the mechanism that lets API requests always
be served from cache instead of blocking on upstream APIs.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "kitsintelligence",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.hydration_tasks",
        "app.workers.tasks.notification_tasks",
        "app.workers.tasks.report_tasks",
        "app.workers.tasks.maintenance_tasks",
        "app.workers.tasks.correlation_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.TIMEZONE,
    enable_utc=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_acks_late=True,
    worker_prefetch_multiplier=4,
    task_reject_on_worker_lost=True,
    result_expires=3600,
    task_default_queue="default",
    task_routes={
        "app.workers.tasks.hydration_tasks.*": {"queue": "hydration"},
        "app.workers.tasks.notification_tasks.*": {"queue": "notifications"},
        "app.workers.tasks.report_tasks.*": {"queue": "reports"},
        "app.workers.tasks.maintenance_tasks.*": {"queue": "default"},
        "app.workers.tasks.correlation_tasks.*": {"queue": "default"},
    },
    beat_schedule={
        "hydrate-active-data-sources": {
            "task": "app.workers.tasks.hydration_tasks.hydrate_all_active_sources",
            "schedule": settings.HYDRATION_DEFAULT_INTERVAL_SECONDS,
        },
        "process-scheduled-notifications": {
            "task": "app.workers.tasks.notification_tasks.process_pending_notifications",
            "schedule": 30.0,
        },
        "run-event-correlation": {
            "task": "app.workers.tasks.correlation_tasks.run_correlation_for_all_orgs",
            "schedule": 120.0,
        },
        "cleanup-expired-tokens": {
            "task": "app.workers.tasks.maintenance_tasks.purge_expired_refresh_tokens",
            "schedule": crontab(hour="*/6", minute=0),
        },
        "cleanup-stale-cache-locks": {
            "task": "app.workers.tasks.maintenance_tasks.release_stale_locks",
            "schedule": crontab(minute="*/15"),
        },
        "compact-audit-logs": {
            "task": "app.workers.tasks.maintenance_tasks.archive_old_audit_logs",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)