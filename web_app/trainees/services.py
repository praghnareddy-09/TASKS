from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from trainees.models import Enrollment, Trainee


@transaction.atomic
def enroll_trainee(trainee, batch, actor=None):
    if trainee.user.role != User.Role.TRAINEE:
        raise ValidationError("Only trainee accounts can be enrolled.")
    if not trainee.is_verified:
        raise ValidationError("Only verified trainees can be enrolled in a batch.")
    if Enrollment.objects.filter(trainee=trainee, batch=batch).exists():
        raise ValidationError("This trainee is already enrolled in the batch.")
    if batch.capacity and batch.enrollments.count() >= batch.capacity:
        raise ValidationError("This batch has reached its capacity.")
    enrollment = Enrollment.objects.create(trainee=trainee, batch=batch)
    from placements.workflow import notify_workflow_users

    notify_workflow_users(
        trainee,
        "batch.assigned",
        f"You have been assigned to batch {batch.name}.",
        actor=actor or batch.trainer,
    )
    return enrollment


def unenroll_trainee(trainee, batch, actor=None):
    deleted, details = Enrollment.objects.filter(trainee=trainee, batch=batch).delete()
    if deleted:
        from placements.workflow import notify_workflow_users

        notify_workflow_users(
            trainee,
            "batch.unassigned",
            f"You have been removed from batch {batch.name}.",
            actor=actor or batch.trainer,
        )
    return deleted, details
