from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, TemplateView, UpdateView

from accounts.forms import LoginForm, ProfileForm, UserApprovalForm, UserCreateForm
from accounts.models import User
from accounts.permissions import AdminRequiredMixin
from trainees.forms import TraineeProfileForm
from trainees.models import Trainee


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


class RegistrationView(FormView):
    form_class = UserCreateForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:registration_submitted")

    def form_valid(self, form):
        user = form.save(commit=False)
        user.role = User.Role.TRAINEE
        user.is_active = False
        user.is_approved = False
        user.save()
        messages.success(self.request, "Your registration was submitted for Admin review.")
        return super().form_valid(form)


class RegistrationSubmittedView(TemplateView):
    template_name = "accounts/registration_submitted.html"


class RegistrationQueueView(AdminRequiredMixin, TemplateView):
    template_name = "accounts/registration_queue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pending_users"] = User.objects.filter(is_approved=False).exclude(
            trainee_profile__verification_status=Trainee.VerificationStatus.DECLINED
        ).select_related("trainee_profile").order_by("date_joined", "pk")
        return context


class RegistrationReviewView(AdminRequiredMixin, UpdateView):
    form_class = UserApprovalForm
    queryset = User.objects.filter(is_approved=False)
    template_name = "accounts/registration_review.html"
    pk_url_kwarg = "user_id"

    @transaction.atomic
    def form_valid(self, form):
        user = form.save(commit=False)
        decision = self.request.POST.get("decision", "approve")
        if decision == "decline":
            user.role = User.Role.TRAINEE
            user.is_approved = True
            user.is_active = False
            user.save()
            trainee = user.trainee_profile
            trainee.verification_status = Trainee.VerificationStatus.DECLINED
            trainee.verified_by = self.request.user
            trainee.verified_at = timezone.now()
            trainee.updated_by = self.request.user
            trainee.save()
            messages.success(self.request, f"Registration for {user.get_full_name() or user.username} was declined.")
            return redirect("accounts:registration_queue")
        user.is_approved = True
        user.is_active = True
        user.save()
        if user.role == User.Role.TRAINEE:
            trainee = user.trainee_profile
            trainee.verification_status = Trainee.VerificationStatus.VERIFIED
            trainee.verified_by = self.request.user
            trainee.verified_at = timezone.now()
            trainee.updated_by = self.request.user
            trainee.save()
            from placements.workflow import notify_workflow_users

            notify_workflow_users(
                trainee,
                "trainee.verified",
                "Your trainee account has been verified.",
                self.request.user,
            )
        messages.success(self.request, f"{user.get_full_name() or user.username} was approved as {user.get_role_display()}.")
        return redirect("accounts:registration_queue")


class PasswordChangeView(LoginRequiredMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.user.must_change_password:
            self.request.user.must_change_password = False
            self.request.user.save(update_fields=["must_change_password"])
        return response


class PasswordChangeDoneView(LoginRequiredMixin, auth_views.PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("accounts:profile")

    def get_form_class(self):
        if self.request.user.is_trainee_role:
            return TraineeProfileForm
        return ProfileForm

    def get_template_names(self):
        if self.request.user.is_trainee_role:
            return ["trainees/profile_form.html"]
        return [self.template_name]

    def get_object(self, queryset=None):
        if self.request.user.is_trainee_role:
            return get_object_or_404(Trainee.objects.visible_to(self.request.user), user=self.request.user)
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.user.is_trainee_role:
            kwargs["request_user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_trainee_role:
            context["enrollments"] = self.object.enrollments.select_related("batch").all()
        return context

    def form_valid(self, form):
        messages.success(self.request, "Your profile has been updated.")
        response = super().form_valid(form)
        if self.request.user.is_trainee_role:
            from placements.workflow import notify_workflow_users

            notify_workflow_users(
                self.object,
                "trainee.profile_updated",
                "Your trainee profile was updated.",
                self.request.user,
            )
        return response
