from django import forms

from batches.models import Batch
from placements.models import ApplicationInterview, JobApplication


class JobApplicationForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = ("batch", "company_name", "job_role", "applied_date", "location", "status", "notes")
        widgets = {
            "batch": forms.Select(attrs={"class": "form-select"}),
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "job_role": forms.TextInput(attrs={"class": "form-control"}),
            "applied_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, request_user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = Batch.objects.filter(
            enrollments__trainee__user=request_user,
            enrollments__trainee__verification_status="VERIFIED",
        ).distinct().order_by("batch_number")
        self.fields["batch"].label = "Batch"


class ApplicationInterviewForm(forms.ModelForm):
    interview_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "class": "form-control"},
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = ApplicationInterview
        fields = ("interview_date", "status", "hr_name", "hr_contact", "remarks")
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "hr_name": forms.TextInput(attrs={"class": "form-control"}),
            "hr_contact": forms.TextInput(attrs={"class": "form-control"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
