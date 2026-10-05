from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q


phone_validator = RegexValidator(
    regex=r"^[6-9]\d{9}$",
    message="Enter a valid 10-digit Indian mobile number.",
)


def validate_offer_letter(upload):
    if upload.size > 5 * 1024 * 1024:
        raise ValidationError("Offer letter must be 5 MB or smaller.")
    extension = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    if extension not in {"pdf", "jpg", "jpeg", "png"}:
        raise ValidationError("Upload a PDF, JPG or PNG file.")
    signature = upload.read(8)
    upload.seek(0)
    valid_signatures = {
        "pdf": signature.startswith(b"%PDF-"),
        "jpg": signature.startswith(b"\xff\xd8\xff"),
        "jpeg": signature.startswith(b"\xff\xd8\xff"),
        "png": signature.startswith(b"\x89PNG\r\n\x1a\n"),
    }
    if not valid_signatures[extension]:
        raise ValidationError("The uploaded file does not match its file type.")


class PlacementQuerySet(models.QuerySet):
    def visible_to(self, user):
        from accounts.models import User

        if user.is_superuser or user.role == User.Role.ADMIN:
            return self
        if user.role == User.Role.TRAINER:
            return self.filter(batch__trainer=user)
        return self.filter(trainee__user=user)

    def manageable_by_trainee(self, user):
        return self.filter(trainee__user=user)


class Placement(models.Model):
    class Status(models.TextChoices):
        OFFERED = "OFFERED", "Offered"
        JOINED = "JOINED", "Joined"
        DECLINED = "DECLINED", "Declined"

    trainee = models.ForeignKey("trainees.Trainee", on_delete=models.CASCADE, related_name="placements")
    batch = models.ForeignKey("batches.Batch", on_delete=models.CASCADE, related_name="placements")
    company_name = models.CharField(max_length=180)
    company_location = models.CharField(max_length=180)
    hr_name = models.CharField(max_length=150)
    hr_email = models.EmailField()
    hr_phone = models.CharField(max_length=10, validators=[phone_validator])
    job_title = models.CharField(max_length=150)
    offer_date = models.DateField()
    joining_date = models.DateField(null=True, blank=True)
    package_lpa = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    offer_letter = models.FileField(upload_to="placements/offers/", blank=True, validators=[validate_offer_letter])
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OFFERED)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_placements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PlacementQuerySet.as_manager()

    class Meta:
        ordering = ("-offer_date", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=Q(joining_date__isnull=True) | Q(joining_date__gte=F("offer_date")),
                name="placement_joining_on_or_after_offer",
            )
        ]
        indexes = [models.Index(fields=["company_name"]), models.Index(fields=["status"])]

    def clean(self):
        super().clean()
        if self.joining_date and self.offer_date and self.joining_date < self.offer_date:
            raise ValidationError({"joining_date": "Joining date must be on or after the offer date."})
        if self.status == self.Status.JOINED and not self.joining_date:
            raise ValidationError({"joining_date": "A joining date is required for joined placements."})
        if self.trainee_id and self.batch_id and not self.batch.enrollments.filter(trainee_id=self.trainee_id).exists():
            raise ValidationError({"batch": "Select a batch in which you are enrolled."})

    def __str__(self):
        return f"{self.trainee} · {self.company_name} · {self.get_status_display()}"
