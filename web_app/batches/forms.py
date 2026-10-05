from django import forms

from accounts.models import User
from batches.models import Batch


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ("name", "course", "trainer", "start_date", "end_date", "status")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)
        self.fields["trainer"].queryset = User.objects.filter(role=User.Role.TRAINER, is_active=True)
        if self.request_user and self.request_user.role == User.Role.TRAINER:
            self.fields["trainer"].initial = self.request_user
            self.fields["trainer"].disabled = True

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned
