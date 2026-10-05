import logging

from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from batches.models import Batch
from trainees.models import Enrollment

logger = logging.getLogger(__name__)


def complete_batch(batch, actor=None):
    if actor is not None and not Batch.objects.manageable_to(actor).filter(pk=batch.pk).exists():
        raise PermissionDenied
    if batch.status == Batch.Status.COMPLETED:
        return batch
    batch.status = Batch.Status.COMPLETED
    batch.save(update_fields=["status", "updated_at"])
    trainee_count = Enrollment.objects.filter(batch=batch).count()
    from placements.models import Placement

    placed_count = Placement.objects.filter(batch=batch, status=Placement.Status.JOINED).count()
    if batch.trainer.email:
        try:
            send_mail(
                subject=f"Batch completed: {batch.name}",
                message=f"{batch.name} has completed.\nTrainees: {trainee_count}\nPlaced: {placed_count}",
                from_email=None,
                recipient_list=[batch.trainer.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Could not email completion summary for batch %s", batch.pk)
    return batch
