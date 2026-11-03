import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings
from .db import Database
from .fetcher import run_fetch

log = logging.getLogger("scheduler")


def make_scheduler(db: Database, settings: Settings) -> BackgroundScheduler:
    """In-process scheduler (chosen over a cron container: one process, one DB file)."""
    sched = BackgroundScheduler()
    sched.add_job(
        run_fetch, "interval", args=[db, settings], minutes=settings.fetch_interval_minutes,
        id="fetch", max_instances=1, coalesce=True,
        next_run_time=datetime.now() if settings.fetch_on_startup else None,
    )
    return sched
