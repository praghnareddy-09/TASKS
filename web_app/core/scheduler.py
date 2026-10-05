import logging
import os
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
_scheduler = None


def _job_listener(event):
    if event.exception:
        logger.error("Batch status scheduler job failed: %s", event.exception)
    elif event.code == EVENT_JOB_MISSED:
        logger.warning("Batch status scheduler job was missed.")
    else:
        logger.info("Batch status scheduler job executed.")


def update_batch_statuses():
    from batches.services import complete_batch
    from batches.models import Batch

    today = timezone.localdate()
    for batch in Batch.objects.select_related("trainer").iterator():
        try:
            if today < batch.start_date and batch.status != Batch.Status.UPCOMING:
                batch.status = Batch.Status.UPCOMING
                batch.save(update_fields=["status", "updated_at"])
            elif batch.start_date <= today <= batch.end_date and batch.status != Batch.Status.RUNNING:
                batch.status = Batch.Status.RUNNING
                batch.save(update_fields=["status", "updated_at"])
            elif today > batch.end_date and batch.status != Batch.Status.COMPLETED:
                complete_batch(batch)
        except Exception:
            logger.exception("Unable to update status for batch %s", batch.pk)


def start_scheduler():
    global _scheduler
    is_reloader_child = os.environ.get("RUN_MAIN") == "true"
    explicitly_enabled = os.environ.get("RUN_SCHEDULER", "").lower() in {"1", "true", "yes"}
    if not (is_reloader_child or explicitly_enabled):
        return
    if _scheduler and _scheduler.running:
        return
    try:
        _scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
        _scheduler.add_job(update_batch_statuses, "cron", hour=0, minute=5, id="batch_statuses", replace_existing=True)
        _scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
        _scheduler.start()
        logger.info("TweakTech batch status scheduler started.")
    except Exception:
        logger.exception("Unable to start TweakTech scheduler.")
