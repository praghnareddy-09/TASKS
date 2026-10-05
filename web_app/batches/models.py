from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class BatchQuerySet(models.QuerySet):
    def visible_to(self, user):
        from accounts.models import User

        if user.is_superuser or user.role == User.Role.ADMIN:
            return self
        if user.role == User.Role.TRAINER:
            return self
        return self.filter(enrollments__trainee__user=user).distinct()

    def manageable_to(self, user):
        from accounts.models import User

        if user.is_superuser or user.role == User.Role.ADMIN:
            return self
        if user.role == User.Role.TRAINER:
            return self.filter(trainer=user)
        return self.none()

    def active(self):
        return self.filter(status=Batch.Status.RUNNING)


class Batch(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"

    name = models.CharField(max_length=120)
    course = models.CharField(max_length=120, db_index=True)
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="training_batches",
        limit_choices_to={"role": "TRAINER"},
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UPCOMING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BatchQuerySet.as_manager()

    class Meta:
        ordering = ("-start_date", "name")
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="batch_end_on_or_after_start")
        ]
        indexes = [models.Index(fields=["status", "start_date"])]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})
        if self.trainer_id and self.trainer.role != "TRAINER":
            raise ValidationError({"trainer": "Selected user must have the Trainer role."})

    def __str__(self):
        return f"{self.name} · {self.course}"
