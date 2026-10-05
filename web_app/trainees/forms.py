from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.crypto import get_random_string

from accounts.models import User
from batches.models import Batch
from trainees.models import Enrollment, Trainee


class TraineeForm(forms.ModelForm):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    password = forms.CharField(widget=forms.PasswordInput(), required=False, help_text="Set only when creating an account.")

    class Meta:
        model = Trainee
        fields = ("phone", "status")

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)
        self.fields["batches"] = forms.ModelMultipleChoiceField(queryset=Batch.objects.none(), required=False)
        if self.request_user:
            qs = Batch.objects.manageable_to(self.request_user)
            self.fields["batches"].queryset = qs
        if self.instance and self.instance.pk:
            user = self.instance.user
            for name in ("username", "first_name", "last_name", "email"):
                self.fields[name].initial = getattr(user, name)
            self.fields["batches"].initial = self.instance.enrollments.values_list("batch_id", flat=True)
            self.fields["password"].help_text = "Leave blank to keep the current password."
        else:
            self.fields["password"].required = True

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            candidate = User(username=self.cleaned_data.get("username", ""), email=self.cleaned_data.get("email", ""))
            try:
                validate_password(password, user=candidate)
            except DjangoValidationError as exc:
                raise forms.ValidationError(exc.messages) from exc
        return password

    def clean_username(self):
        username = self.cleaned_data["username"]
        users = User.objects.exclude(pk=self.instance.user_id) if self.instance and self.instance.pk else User.objects.all()
        if users.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def save(self, commit=True):
        trainee = super().save(commit=False)
        phone = trainee.phone
        status = trainee.status
        creating = not bool(trainee.pk)
        if creating:
            user = User(username=self.cleaned_data["username"], role=User.Role.TRAINEE)
            user.set_password(self.cleaned_data.get("password") or get_random_string(32))
        else:
            user = trainee.user
            user.username = self.cleaned_data["username"]
        for name in ("first_name", "last_name", "email"):
            setattr(user, name, self.cleaned_data.get(name, ""))
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            if creating:
                trainee = user.trainee_profile
            else:
                trainee.user = user
            trainee.phone = phone
            trainee.status = status
            trainee.save()
            allowed_batches = Batch.objects.manageable_to(self.request_user) if self.request_user else Batch.objects.all()
            Enrollment.objects.filter(trainee=trainee, batch__in=allowed_batches).exclude(batch__in=self.cleaned_data["batches"]).delete()
            existing = set(trainee.enrollments.values_list("batch_id", flat=True))
            Enrollment.objects.bulk_create([
                Enrollment(trainee=trainee, batch=batch)
                for batch in self.cleaned_data["batches"] if batch.pk not in existing
            ])
        return trainee
