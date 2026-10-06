import mimetypes

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.models import User
from accounts.permissions import AdminRequiredMixin
from batches.models import Batch
from trainees.forms import AdminTraineeEditForm, TraineeCreateForm, TraineeEnrollmentForm
from trainees.models import Enrollment, Trainee
from trainees.services import enroll_trainee, unenroll_trainee
from placements.models import JobApplication, Placement, WorkflowAudit
from placements.workflow import notify_workflow_users, publish_workflow_event, record_status_change


class TraineeListView(AdminRequiredMixin, ListView):
    model = Trainee
    template_name = "trainees/trainee_list.html"
    context_object_name = "trainees"
    paginate_by = 10

    def get_queryset(self):
        batch_count = Count("enrollments", distinct=True)
        queryset = (
            Trainee.objects.visible_to(self.request.user)
            .select_related("user", "verified_by")
            .prefetch_related(
                Prefetch(
                    "enrollments",
                    queryset=Enrollment.objects.select_related("batch").order_by("-enrolled_on", "-pk"),
                ),
                Prefetch(
                    "job_applications",
                    queryset=JobApplication.objects.only("pk", "trainee_id", "status", "updated_at").order_by("-updated_at", "-pk"),
                ),
                Prefetch(
                    "placements",
                    queryset=Placement.objects.only("pk", "trainee_id", "status", "updated_at").order_by("-updated_at", "-pk"),
                ),
            )
            .annotate(batch_count=batch_count)
            .order_by("user__first_name", "user__username", "pk")
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(user__username__icontains=query) | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(user__email__icontains=query) | Q(phone__icontains=query))
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.GET.get("verification"):
            queryset = queryset.filter(verification_status=self.request.GET["verification"])
        if self.request.GET.get("batch"):
            queryset = queryset.filter(enrollments__batch_id=self.request.GET["batch"])
        if self.request.GET.get("start"):
            queryset = queryset.filter(joined_on__gte=self.request.GET["start"])
        if self.request.GET.get("end"):
            queryset = queryset.filter(joined_on__lte=self.request.GET["end"])
        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = Trainee.Status.choices
        context["verification_choices"] = Trainee.VerificationStatus.choices
        context["batch_choices"] = Batch.objects.visible_to(self.request.user)
        return context


class TraineeDetailView(LoginRequiredMixin, DetailView):
    model = Trainee
    template_name = "trainees/trainee_detail.html"
    queryset = Trainee.objects.select_related("user", "updated_by").prefetch_related("enrollments__batch")

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollments = self.object.enrollments.select_related("batch").all()
        context["enrollments"] = enrollments
        context["placement_history"] = self.object.placements.select_related("batch", "verified_by").all()
        context["application_history"] = self.object.job_applications.select_related("batch").prefetch_related("interviews", "audit_entries__actor").all()
        context["profile_completion"] = self.object.profile_completion_percentage()
        if self.request.user.is_admin_role:
            context["is_eligible_for_batch"] = self.object.is_verified
            if self.object.is_verified:
                context["enrollment_form"] = TraineeEnrollmentForm(
                    trainee=self.object,
                    request_user=self.request.user,
                )
        return context


class TraineeCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = TraineeCreateForm
    template_name = "trainees/trainee_form.html"

    @transaction.atomic
    def form_valid(self, form):
        user = form.save(commit=False)
        temporary_password = get_random_string(24)
        user.role = User.Role.TRAINEE
        user.must_change_password = True
        user.set_password(temporary_password)
        user.save()
        trainee = user.trainee_profile
        trainee.updated_by = self.request.user
        trainee.verification_status = Trainee.VerificationStatus.VERIFIED
        trainee.verified_by = self.request.user
        trainee.verified_at = timezone.now()
        trainee.save()
        batch = form.cleaned_data.get("batch")
        if batch:
            enroll_trainee(trainee, batch, self.request.user)
        notify_workflow_users(
            trainee,
            "trainee.created",
            "Your trainee account is ready. Sign in and complete your profile.",
            self.request.user,
        )
        messages.success(self.request, "Trainee account created. Share the temporary password securely.")
        response = render(
            self.request,
            "trainees/trainee_created.html",
            {"trainee": trainee, "temporary_password": temporary_password},
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class TraineeUpdateView(AdminRequiredMixin, UpdateView):
    model = Trainee
    form_class = AdminTraineeEditForm
    template_name = "trainees/trainee_form.html"
    def get_queryset(self):
        return Trainee.objects.visible_to(self.request.user).select_related("user")

    @transaction.atomic
    def form_valid(self, form):
        old_status = self.object.status
        old_verification = self.object.verification_status
        messages.success(self.request, "Trainee details updated successfully.")
        response = super().form_valid(form)
        record_status_change(
            trainee=self.object,
            application=None,
            actor=self.request.user,
            entity_type="trainee",
            entity_id=self.object.pk,
            field_name="status",
            old_value=old_status,
            new_value=self.object.status,
        )
        record_status_change(
            trainee=self.object,
            application=None,
            actor=self.request.user,
            entity_type="trainee",
            entity_id=self.object.pk,
            field_name="verification_status",
            old_value=old_verification,
            new_value=self.object.verification_status,
        )
        notify_workflow_users(
            self.object,
            "trainee.profile_updated",
            "An Admin updated your trainee profile or batch assignment.",
            self.request.user,
        )
        return response

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("trainees:detail", args=[self.object.pk])


class TraineeDeleteView(AdminRequiredMixin, DeleteView):
    model = Trainee
    template_name = "trainees/trainee_confirm_delete.html"
    success_url = reverse_lazy("trainees:list")

    def get_queryset(self):
        return Trainee.objects.visible_to(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Trainee deleted.")
        return super().form_valid(form)


class EnrollmentToggleView(AdminRequiredMixin, View):
    def post(self, request, trainee_id, batch_id):
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=trainee_id)
        batch = get_object_or_404(Batch.objects.manageable_to(request.user), pk=batch_id)
        enrollment = Enrollment.objects.filter(trainee=trainee, batch=batch)
        if enrollment.exists():
            unenroll_trainee(trainee, batch, request.user)
            messages.success(request, "Trainee unenrolled.")
        else:
            enroll_trainee(trainee, batch, request.user)
            messages.success(request, "Trainee enrolled.")
        return redirect("trainees:detail", pk=trainee.pk)


class TraineeEnrollmentView(AdminRequiredMixin, View):
    def post(self, request, trainee_id):
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=trainee_id)
        if not trainee.is_verified:
            messages.error(request, "Verify this trainee before assigning a batch.")
            return redirect("trainees:detail", pk=trainee.pk)
        form = TraineeEnrollmentForm(
            request.POST,
            trainee=trainee,
            request_user=request.user,
        )
        if not form.is_valid():
            messages.error(request, "Select a batch the trainee is not already enrolled in.")
            return redirect("trainees:detail", pk=trainee.pk)

        batch = form.cleaned_data["batch"]
        try:
            enroll_trainee(trainee, batch, request.user)
        except ValidationError:
            messages.error(request, f"{trainee} is already enrolled in {batch.name}.")
        else:
            messages.success(request, f"{trainee} enrolled in {batch.name}.")
        return redirect("trainees:detail", pk=trainee.pk)


class TraineeEnrollmentRemoveView(AdminRequiredMixin, View):
    def post(self, request, trainee_id, batch_id):
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=trainee_id)
        batch = get_object_or_404(Batch.objects.manageable_to(request.user), pk=batch_id)
        if not Enrollment.objects.filter(trainee=trainee, batch=batch).exists():
            get_object_or_404(Enrollment, trainee=trainee, batch=batch)
        unenroll_trainee(trainee, batch, request.user)
        messages.success(request, f"{trainee} removed from {batch.name}.")
        return redirect("trainees:detail", pk=trainee.pk)


class TraineePhotoView(LoginRequiredMixin, View):
    def get(self, request, pk):
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=pk)
        if not trainee.profile_photo:
            raise Http404("This trainee has not provided a profile photo.")
        content_type = mimetypes.guess_type(trainee.profile_photo.name)[0] or "application/octet-stream"
        return FileResponse(trainee.profile_photo.open("rb"), content_type=content_type)


class TraineeVerificationView(AdminRequiredMixin, View):
    def post(self, request, trainee_id):
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=trainee_id)
        old_status = trainee.verification_status
        trainee.verification_status = Trainee.VerificationStatus.VERIFIED
        trainee.verified_by = request.user
        trainee.verified_at = timezone.now()
        trainee.updated_by = request.user
        trainee.save()
        trainee.user.is_approved = True
        trainee.user.is_active = True
        trainee.user.save(update_fields=["is_approved", "is_active"])
        record_status_change(
            trainee=trainee,
            application=None,
            actor=request.user,
            entity_type="trainee",
            entity_id=trainee.pk,
            field_name="verification_status",
            old_value=old_status,
            new_value=trainee.verification_status,
        )
        notify_workflow_users(
            trainee,
            "trainee.verified",
            "Your trainee profile has been verified. You can now be assigned to a batch.",
            request.user,
        )
        messages.success(request, f"{trainee} has been verified and is eligible for batch assignment.")
        return redirect("trainees:detail", pk=trainee.pk)


class TraineeDeclineView(AdminRequiredMixin, View):
    def post(self, request, trainee_id):
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=trainee_id)
        old_status = trainee.verification_status
        trainee.verification_status = Trainee.VerificationStatus.DECLINED
        trainee.verified_by = request.user
        trainee.verified_at = timezone.now()
        trainee.updated_by = request.user
        trainee.save()
        trainee.user.is_approved = True
        trainee.user.is_active = False
        trainee.user.save(update_fields=["is_approved", "is_active"])
        record_status_change(
            trainee=trainee,
            application=None,
            actor=request.user,
            entity_type="trainee",
            entity_id=trainee.pk,
            field_name="verification_status",
            old_value=old_status,
            new_value=trainee.verification_status,
        )
        notify_workflow_users(trainee, "trainee.declined", "Your trainee registration was declined.", request.user)
        messages.success(request, f"Registration for {trainee} was declined.")
        return redirect("trainees:list")


class TraineeActivationToggleView(AdminRequiredMixin, View):
    def post(self, request, trainee_id):
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=trainee_id)
        old_status = trainee.status
        trainee.status = (
            Trainee.Status.INACTIVE if trainee.status == Trainee.Status.ACTIVE else Trainee.Status.ACTIVE
        )
        trainee.updated_by = request.user
        trainee.save()
        trainee.user.is_active = (
            trainee.status == Trainee.Status.ACTIVE and trainee.is_verified and trainee.user.is_approved
        )
        trainee.user.save(update_fields=["is_active"])
        record_status_change(
            trainee=trainee,
            application=None,
            actor=request.user,
            entity_type="trainee",
            entity_id=trainee.pk,
            field_name="status",
            old_value=old_status,
            new_value=trainee.status,
        )
        notify_workflow_users(
            trainee,
            "trainee.activation",
            f"Your trainee account is now {trainee.get_status_display().lower()}.",
            request.user,
        )
        messages.success(request, f"{trainee} is now {trainee.get_status_display().lower()}.")
        return redirect("trainees:detail", pk=trainee.pk)
