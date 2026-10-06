import re

from PIL import Image
from django import forms
from django.core.exceptions import ValidationError

from accounts.models import User
from batches.models import Batch
from trainees.models import Enrollment, Trainee


def clean_unique_email(form, email):
    users = User.objects.filter(email__iexact=email)
    if form.instance and getattr(form.instance, "user_id", None):
        users = users.exclude(pk=form.instance.user_id)
    if users.exists():
        raise ValidationError("A user with this email address already exists.")
    return email


class TraineeCreateForm(forms.ModelForm):
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.none(),
        required=False,
        empty_label="No batch yet",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["username"].required = True
        self.fields["email"].required = True
        self.fields["batch"].queryset = Batch.objects.order_by("batch_number", "name")

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        return clean_unique_email(self, email)


PROFILE_FIELDS = (
    "phone",
    "date_of_birth",
    "address",
    "city",
    "state",
    "highest_qualification",
    "college_university",
    "graduation_year",
    "emergency_contact_name",
    "emergency_contact_phone",
    "profile_photo",
)


class TraineeProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        max_length=254,
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Trainee
        fields = PROFILE_FIELDS
        widgets = {
            "phone": forms.TextInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "date_of_birth": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "highest_qualification": forms.TextInput(attrs={"class": "form-control"}),
            "college_university": forms.TextInput(attrs={"class": "form-control"}),
            "graduation_year": forms.NumberInput(attrs={"class": "form-control", "min": 1900}),
            "emergency_contact_name": forms.TextInput(attrs={"class": "form-control"}),
            "emergency_contact_phone": forms.TextInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "profile_photo": forms.FileInput(attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png"}),
        }
        labels = {
            "phone": "Phone",
            "date_of_birth": "Date of birth",
            "address": "Address",
            "city": "City",
            "state": "State",
            "highest_qualification": "Highest qualification",
            "college_university": "College/university",
            "graduation_year": "Graduation year",
            "emergency_contact_name": "Emergency contact name",
            "emergency_contact_phone": "Emergency contact phone",
            "profile_photo": "Profile photo",
        }

    def __init__(self, *args, request_user, **kwargs):
        self.request_user = request_user
        super().__init__(*args, **kwargs)
        for name in ("first_name", "last_name", "email"):
            self.fields[name].initial = getattr(self.instance.user, name)

    def clean_email(self):
        return clean_unique_email(self, self.cleaned_data["email"].strip())

    def clean_phone(self):
        return validate_indian_phone(self.cleaned_data.get("phone", ""), "Enter a valid 10-digit Indian phone number.")

    def clean_emergency_contact_phone(self):
        return validate_indian_phone(
            self.cleaned_data.get("emergency_contact_phone", ""),
            "Enter a valid 10-digit Indian phone number.",
        )

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        if photo.size > 2 * 1024 * 1024:
            raise ValidationError("Profile photos must be 2 MB or smaller.")
        extension = photo.name.rsplit(".", 1)[-1].lower()
        if extension not in {"jpg", "jpeg", "png"}:
            raise ValidationError("Upload a JPG or PNG image.")
        try:
            photo.seek(0)
            with Image.open(photo) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ValidationError("Upload a valid JPG or PNG image.")
                if (image.format == "JPEG" and extension not in {"jpg", "jpeg"}) or (
                    image.format == "PNG" and extension != "png"
                ):
                    raise ValidationError("The file extension must match the image type.")
                image.verify()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValidationError("Upload a valid JPG or PNG image.") from exc
        finally:
            photo.seek(0)
        return photo

    def save(self, commit=True):
        trainee = super().save(commit=False)
        trainee.user.first_name = self.cleaned_data["first_name"]
        trainee.user.last_name = self.cleaned_data["last_name"]
        trainee.user.email = self.cleaned_data["email"]
        if commit:
            trainee.user.save()
            trainee.updated_by = self.request_user
            trainee.save()
        return trainee


class AdminTraineeEditForm(TraineeProfileForm):
    status = forms.ChoiceField(
        choices=Trainee.Status.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.none(),
        required=False,
        empty_label="No batch assigned",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta(TraineeProfileForm.Meta):
        fields = (*PROFILE_FIELDS, "status")

    def __init__(self, *args, request_user, **kwargs):
        super().__init__(*args, request_user=request_user, **kwargs)
        available_batches = Batch.objects.manageable_to(request_user).order_by("batch_number", "name")
        self.fields["batch"].queryset = available_batches if self.instance.is_verified else Batch.objects.none()
        self.fields["batch"].initial = (
            self.instance.enrollments.order_by("-enrolled_on", "-pk").values_list("batch_id", flat=True).first()
        )

    def save(self, commit=True):
        trainee = super().save(commit=commit)
        if commit:
            from trainees.services import enroll_trainee, unenroll_trainee

            selected_batch = self.cleaned_data.get("batch")
            existing_batches = list(self.instance.enrollments.select_related("batch"))
            for enrollment in existing_batches:
                if selected_batch is None or enrollment.batch_id != selected_batch.pk:
                    unenroll_trainee(self.instance, enrollment.batch, self.request_user)
            if selected_batch:
                if not any(enrollment.batch_id == selected_batch.pk for enrollment in existing_batches):
                    enroll_trainee(self.instance, selected_batch, self.request_user)
        return trainee


def validate_indian_phone(value, message):
    if value and not re.fullmatch(r"[6-9]\d{9}", value):
        raise ValidationError(message)
    return value


class TraineeEnrollmentForm(forms.Form):
    batch = forms.ModelChoiceField(
        queryset=Batch.objects.none(),
        empty_label="Select a batch",
        label="Enrol in batch",
    )

    def __init__(self, *args, trainee, request_user, **kwargs):
        super().__init__(*args, **kwargs)
        enrolled_batch_ids = trainee.enrollments.values_list("batch_id", flat=True)
        self.fields["batch"].queryset = (
            Batch.objects.manageable_to(request_user)
            if trainee.is_verified
            else Batch.objects.none()
        )
        self.fields["batch"].queryset = (
            self.fields["batch"].queryset
            .exclude(pk__in=enrolled_batch_ids)
            .order_by("batch_number")
        )


class BatchEnrollmentForm(forms.Form):
    trainees = forms.ModelMultipleChoiceField(
        queryset=Trainee.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
        label="Add trainees",
    )

    def __init__(self, *args, batch, request_user, **kwargs):
        super().__init__(*args, **kwargs)
        enrolled_trainee_ids = batch.enrollments.values_list("trainee_id", flat=True)
        self.fields["trainees"].queryset = (
            Trainee.objects.visible_to(request_user).verified()
            .exclude(pk__in=enrolled_trainee_ids)
            .select_related("user")
            .order_by("user__first_name", "user__username")
        )
