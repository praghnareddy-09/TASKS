from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from trainees.models import Enrollment, Trainee


@transaction.atomic
def enroll_trainee(trainee, batch):
    if trainee.user.role != User.Role.TRAINEE:
        raise ValidationError("Only trainee accounts can be enrolled.")
    if Enrollment.objects.filter(trainee=trainee, batch=batch).exists():
        raise ValidationError("This trainee is already enrolled in the batch.")
    return Enrollment.objects.create(trainee=trainee, batch=batch)


def unenroll_trainee(trainee, batch):
    return Enrollment.objects.filter(trainee=trainee, batch=batch).delete()
