from django.conf import settings
from django.db import models
from django.db import transaction


class TraineeQuerySet(models.QuerySet):
    def verified(self):
        return self.filter(verification_status=Trainee.VerificationStatus.VERIFIED)

    def visible_to(self, user):
        from accounts.models import User

        if user.is_admin_role:
            return self
        if user.is_trainee_role:
            return self.filter(user=user)
        return self.none()


class Trainee(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Verification"
        VERIFIED = "VERIFIED", "Verified"
        DECLINED = "DECLINED", "Declined"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trainee_profile")
    phone = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    highest_qualification = models.CharField(max_length=180, blank=True)
    college_university = models.CharField(max_length=180, blank=True)
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=180, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    profile_photo = models.ImageField(upload_to="trainee_photos/", null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    verification_status = models.CharField(
        max_length=10,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_trainee_profiles",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    joined_on = models.DateField(auto_now_add=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_trainee_profiles",
    )
    updated_at = models.DateTimeField(auto_now=True)
    objects = TraineeQuerySet.as_manager()

    class Meta:
        ordering = ("user__first_name", "user__username")
        indexes = [models.Index(fields=["status", "joined_on"])]

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def profile_completion_percentage(self):
        values = (
            self.user.first_name,
            self.user.last_name,
            self.user.email,
            self.phone,
            self.date_of_birth,
            self.address,
            self.city,
            self.state,
            self.highest_qualification,
            self.college_university,
            self.graduation_year,
            self.emergency_contact_name,
            self.emergency_contact_phone,
        )
        completed = sum(bool(value) for value in values)
        return round(completed * 100 / len(values))

    @property
    def profile_is_complete(self):
        return self.profile_completion_percentage() == 100

    @property
    def is_verified(self):
        return self.verification_status == self.VerificationStatus.VERIFIED

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
