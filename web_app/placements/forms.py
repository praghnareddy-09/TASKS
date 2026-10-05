from django import forms
from django.core.exceptions import ValidationError

from batches.models import Batch
from placements.models import Placement, phone_validator


class PlacementForm(forms.ModelForm):
    hr_phone = forms.CharField(
        max_length=10,
        validators=[phone_validator],
        help_text="Enter a 10-digit Indian mobile number.",
    )

    class Meta:
        model = Placement
        fields = (
            "batch",
            "company_name",
            "company_location",
            "hr_name",
            "hr_email",
            "hr_phone",
            "job_title",
            "offer_date",
            "joining_date",
            "package_lpa",
            "offer_letter",
            "status",
        )
        widgets = {
            "offer_date": forms.DateInput(attrs={"type": "date"}),
            "joining_date": forms.DateInput(attrs={"type": "date"}),
            "offer_letter": forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"}),
            "package_lpa": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = Batch.objects.filter(
            enrollments__trainee__user=self.request_user
        ).distinct().order_by("name") if self.request_user else Batch.objects.none()
        self.fields["batch"].label = "Batch"
        self.fields["package_lpa"].label = "Package (LPA)"

    def clean(self):
        cleaned = super().clean()
        offer_date = cleaned.get("offer_date")
        joining_date = cleaned.get("joining_date")
        if offer_date and joining_date and joining_date < offer_date:
            self.add_error("joining_date", "Joining date must be on or after the offer date.")
        if cleaned.get("status") == Placement.Status.JOINED and not joining_date:
            self.add_error("joining_date", "A joining date is required for joined placements.")
        return cleaned
