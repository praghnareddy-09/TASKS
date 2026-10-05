from django.conf import settings
from django.db import models
from django.db import transaction


class TraineeQuerySet(models.QuerySet):
    def visible_to(self, user):
        from accounts.models import User

        if user.is_superuser or user.role == User.Role.ADMIN:
            return self
        if user.role == User.Role.TRAINER:
            return self.filter(enrollments__batch__trainer=user).distinct()
        return self.filter(user=user)


class Trainee(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trainee_profile")
    phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    joined_on = models.DateField(auto_now_add=True)
    objects = TraineeQuerySet.as_manager()

    class Meta:
        ordering = ("user__first_name", "user__username")
        indexes = [models.Index(fields=["status", "joined_on"])]

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @transaction.atomic
    def delete(self, using=None, keep_parents=False):
        user = self.user
        result = super().delete(using=using, keep_parents=keep_parents)
        user.delete(using=using)
        return result


class Enrollment(models.Model):
    trainee = models.ForeignKey(Trainee, on_delete=models.CASCADE, related_name="enrollments")
    batch = models.ForeignKey("batches.Batch", on_delete=models.CASCADE, related_name="enrollments")
    enrolled_on = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ("-enrolled_on",)
        constraints = [models.UniqueConstraint(fields=("trainee", "batch"), name="unique_trainee_batch")]
        indexes = [models.Index(fields=["batch", "trainee"])]

    def __str__(self):
        return f"{self.trainee} in {self.batch}"
