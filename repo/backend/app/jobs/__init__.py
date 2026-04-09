import uuid

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, g


def register_jobs(scheduler: BackgroundScheduler, app: Flask) -> None:
    from .message_redelivery import redeliver_messages
    from .trending_precompute import precompute_trending
    from .safety_stock import check_safety_stock
    from .slow_moving import flag_slow_moving
    from .attachment_cleanup import cleanup_attachments

    # Message redelivery every minute
    scheduler.add_job(
        func=_with_context(app, redeliver_messages),
        trigger="interval", minutes=1, id="message_redelivery", replace_existing=True,
    )
    # Trending precompute every 15 minutes
    scheduler.add_job(
        func=_with_context(app, precompute_trending),
        trigger="interval", minutes=15, id="trending_precompute", replace_existing=True,
    )
    # Safety stock check every 10 minutes
    scheduler.add_job(
        func=_with_context(app, check_safety_stock),
        trigger="interval", minutes=10, id="safety_stock", replace_existing=True,
    )
    # Slow-moving flag — daily at 02:00 UTC
    scheduler.add_job(
        func=_with_context(app, flag_slow_moving),
        trigger="cron", hour=2, minute=0, id="slow_moving", replace_existing=True,
    )
    # Attachment cleanup — daily at 03:00 UTC
    scheduler.add_job(
        func=_with_context(app, cleanup_attachments),
        trigger="cron", hour=3, minute=0, id="attachment_cleanup", replace_existing=True,
    )


def _with_context(app: Flask, fn):
    """Wraps a job function so it runs inside the app context with a correlation_id."""
    def wrapper(*args, **kwargs):
        with app.app_context():
            g.correlation_id = f"job-{fn.__name__}-{uuid.uuid4()}"
            fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper
