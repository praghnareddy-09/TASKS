from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


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

        if user.is_admin_role:
            return self
        if user.is_trainee_role:
            return self.filter(trainee__user=user)
        return self.none()

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


class JobApplicationQuerySet(models.QuerySet):
    def visible_to(self, user):
        if user.is_admin_role:
            return self
        if user.is_trainee_role:
            return self.filter(trainee__user=user)
        return self.none()


class JobApplication(models.Model):
    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        SHORTLISTED = "SHORTLISTED", "Shortlisted"
        ASSESSMENT = "ASSESSMENT", "Assessment"
        TECHNICAL_ROUND = "TECHNICAL_ROUND", "Technical Round"
        L1_INTERVIEW = "L1_INTERVIEW", "L1 Interview"
        L2_INTERVIEW = "L2_INTERVIEW", "L2 Interview"
        HR_ROUND = "HR_ROUND", "HR Round"
        OFFER_RECEIVED = "OFFER_RECEIVED", "Offer Received"
        SELECTED = "SELECTED", "Selected"
        REJECTED = "REJECTED", "Rejected"
        JOINED = "JOINED", "Joined"

    trainee = models.ForeignKey("trainees.Trainee", on_delete=models.CASCADE, related_name="job_applications")
    batch = models.ForeignKey("batches.Batch", on_delete=models.PROTECT, related_name="job_applications")
    company_name = models.CharField(max_length=180, db_index=True)
    job_role = models.CharField(max_length=180)
    applied_date = models.DateField(default=timezone.localdate)
    location = models.CharField(max_length=180, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLIED, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = JobApplicationQuerySet.as_manager()

    class Meta:
        ordering = ("-applied_date", "-created_at")
        indexes = [
            models.Index(fields=["batch", "status"]),
            models.Index(fields=["trainee", "status"]),
        ]

    def clean(self):
        super().clean()
        if self.trainee_id and not self.trainee.is_verified:
            raise ValidationError({"trainee": "Only verified trainees may create job applications."})
        if self.trainee_id and self.batch_id and not self.batch.enrollments.filter(trainee_id=self.trainee_id).exists():
            raise ValidationError({"batch": "Choose a batch in which this trainee is enrolled."})

    def __str__(self):
        return f"{self.trainee} · {self.company_name} · {self.get_status_display()}"


class ApplicationInterview(models.Model):
    class Status(models.TextChoices):
        INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED", "Interview Scheduled"
        ASSESSMENT_COMPLETED = "ASSESSMENT_COMPLETED", "Assessment Completed"
        SHORTLISTED = "SHORTLISTED", "Shortlisted"
        SELECTED = "SELECTED", "Selected"
        REJECTED = "REJECTED", "Rejected"
        OFFER_RELEASED = "OFFER_RELEASED", "Offer Released"
        JOINED = "JOINED", "Joined"

    application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name="interviews")
    interview_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.INTERVIEW_SCHEDULED,
        db_index=True,
    )
    hr_name = models.CharField(max_length=150, blank=True)
    hr_contact = models.CharField(max_length=180, blank=True)
    remarks = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="updated_application_interviews",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("interview_date", "-updated_at")
        indexes = [
            models.Index(fields=["status", "interview_date"]),
            models.Index(fields=["application", "status"]),
        ]

    def __str__(self):
        return f"{self.application.company_name} · {self.get_status_display()}"


class WorkflowAudit(models.Model):
    trainee = models.ForeignKey("trainees.Trainee", on_delete=models.CASCADE, related_name="workflow_audits")
    application = models.ForeignKey(
        JobApplication,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="workflow_audit_entries",
    )
    entity_type = models.CharField(max_length=40)
    entity_id = models.PositiveBigIntegerField()
    field_name = models.CharField(max_length=40)
    previous_value = models.CharField(max_length=40, blank=True)
    new_value = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["trainee", "created_at"]), models.Index(fields=["entity_type", "entity_id"])]


class WorkflowNotification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workflow_notifications",
    )
    trainee = models.ForeignKey("trainees.Trainee", on_delete=models.CASCADE, related_name="workflow_notifications")
    application = models.ForeignKey(
        JobApplication,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    event_type = models.CharField(max_length=40)
    message = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["recipient", "read_at", "created_at"])]
