"""Celery worker entry point: `celery -A app.jobs.celery_app worker`."""

from __future__ import annotations

from celery import Celery

from ..core.config import get_settings

settings = get_settings()
celery = Celery("codm_beast_studio", broker=settings.broker_url or "redis://localhost:6379/0")
celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.job_timeout_seconds + 120,
    task_soft_time_limit=settings.job_timeout_seconds,
    broker_connection_retry_on_startup=True,
    beat_schedule={"cleanup-old-files": {"task": "beast.cleanup", "schedule": 6 * 3600.0}},
)


@celery.task(name="beast.run_job")
def run_job_task(job_id: str) -> None:
    from ..services.pipeline import run_job
    run_job(job_id)


@celery.task(name="beast.cleanup")
def cleanup_task() -> dict:
    from ..services.maintenance import cleanup_expired
    return cleanup_expired()
