"""Dispatch jobs to Celery (when BEAST_BROKER_URL is set) or to a local thread pool."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from ..core.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def _pool() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=max(1, get_settings().max_parallel_jobs), thread_name_prefix="beast-job")


def dispatch(job_id: str) -> str:
    """Queue a job. Returns "celery" or "thread"."""
    if get_settings().broker_url:
        from .celery_app import run_job_task
        run_job_task.delay(job_id)
        return "celery"
    from ..services.pipeline import run_job
    _pool().submit(run_job, job_id)
    return "thread"
