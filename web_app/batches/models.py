from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.core.validators import MinValueValidator


class BatchQuerySet(models.QuerySet):
    def visible_to(self, user):
        if user.is_admin_role:
            return self
        if user.is_trainee_role:
            return self.filter(enrollments__trainee__user=user).distinct()
        return self.none()

    def manageable_to(self, user):
        if user.is_admin_role:
            return self
        return self.none()

    def active(self):
        return self.filter(status=Batch.Status.RUNNING)


class Batch(models.Model):
    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"

    name = models.CharField(max_length=120)
    batch_number = models.PositiveIntegerField(
        unique=True,
        validators=[MinValueValidator(1)],
        help_text="For example 25",
    )
    course = models.CharField(max_length=120, db_index=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="training_batches",
        limit_choices_to={"role": "ADMIN"},
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
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="batch_end_on_or_after_start"),
            models.CheckConstraint(condition=Q(batch_number__gt=0), name="batch_number_positive"),
            models.CheckConstraint(
                condition=Q(capacity__isnull=True) | Q(capacity__gt=0),
                name="batch_capacity_positive",
            ),
        ]
        indexes = [models.Index(fields=["status", "start_date"])]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})
        if self.trainer_id and not self.trainer.is_admin_role:
            raise ValidationError({"trainer": "Selected user must have the Admin role."})
        if self.capacity and self.pk and self.enrollments.count() > self.capacity:
            raise ValidationError({"capacity": "Capacity cannot be lower than the current enrolled trainee count."})

    @property
    def member_count(self):
        if hasattr(self, "trainee_count"):
            return self.trainee_count
        return self.enrollments.count()

    def __str__(self):
        return f"{self.name} · {self.course}"
