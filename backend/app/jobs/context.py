"""Job progress reporting and cancellation, shared by the thread runner and Celery worker."""

from __future__ import annotations

import time

from ..db.models import Job
from ..db.session import session_scope


class JobContext:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self._last_write = 0.0
        self._last_cancel_check = 0.0
        self._cancelled = False
        self._start = time.monotonic()
        self._lo, self._hi = 0.0, 1.0  # current sub-range of overall progress

    def span(self, lo: float, hi: float) -> JobContext:
        """Map subsequent progress(0..1) calls into [lo, hi] of the overall bar."""
        self._lo, self._hi = lo, hi
        return self

    def progress(self, frac: float, stage: str | None = None, message: str | None = None, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_write < 0.5:
            return
        self._last_write = now
        overall = self._lo + (self._hi - self._lo) * max(0.0, min(1.0, frac))
        elapsed = now - self._start
        eta = (elapsed / overall - elapsed) if overall > 0.03 else None
        with session_scope() as db:
            job = db.get(Job, self.job_id)
            if job is None:
                return
            job.progress = round(overall, 4)
            job.eta_seconds = round(eta, 1) if eta is not None else None
            if stage is not None:
                job.stage = stage
            if message is not None:
                job.message = message

    def cancelled(self) -> bool:
        if self._cancelled:
            return True
        now = time.monotonic()
        if now - self._last_cancel_check < 1.0:
            return False
        self._last_cancel_check = now
        with session_scope() as db:
            job = db.get(Job, self.job_id)
            self._cancelled = bool(job and job.cancel_requested)
        return self._cancelled
