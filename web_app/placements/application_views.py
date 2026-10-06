from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.permissions import AdminRequiredMixin
from placements.application_forms import ApplicationInterviewForm, JobApplicationForm
from placements.models import ApplicationInterview, JobApplication
from placements.workflow import application_status_updated, save_interview_update
from trainees.models import Trainee


class ApplicationListView(LoginRequiredMixin, ListView):
    model = JobApplication
    template_name = "placements/application_list.html"
    context_object_name = "applications"
    paginate_by = 15

    def get_queryset(self):
        queryset = JobApplication.objects.visible_to(self.request.user).select_related(
            "trainee__user", "batch"
        ).prefetch_related("interviews")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(company_name__icontains=query)
                | Q(job_role__icontains=query)
                | Q(trainee__user__first_name__icontains=query)
                | Q(trainee__user__last_name__icontains=query)
            )
        if self.request.GET.get("batch"):
            queryset = queryset.filter(batch_id=self.request.GET["batch"])
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = JobApplication.Status.choices
        context["is_admin"] = self.request.user.is_admin_role
        if self.request.user.is_admin_role:
            from batches.models import Batch

            context["batch_choices"] = Batch.objects.order_by("batch_number")
        if self.request.user.is_trainee_role:
            context["application_count"] = self.get_queryset().count()
        return context


class VerifiedTraineeMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return (
            self.request.user.is_trainee_role
            and hasattr(self.request.user, "trainee_profile")
            and self.request.user.trainee_profile.is_verified
            and self.request.user.trainee_profile.status == Trainee.Status.ACTIVE
        )


class ApplicationCreateView(VerifiedTraineeMixin, CreateView):
    model = JobApplication
    form_class = JobApplicationForm
    template_name = "placements/application_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        form.instance.trainee = self.request.user.trainee_profile
        response = super().form_valid(form)
        application_status_updated(self.object, self.request.user, "")
        messages.success(self.request, "Job application added.")
        return response

    def get_success_url(self):
        return reverse("placements:application_detail", args=[self.object.pk])


class ApplicationUpdateView(VerifiedTraineeMixin, UpdateView):
    model = JobApplication
    form_class = JobApplicationForm
    template_name = "placements/application_form.html"

    def get_queryset(self):
        return JobApplication.objects.filter(trainee__user=self.request.user).select_related("batch")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        old_status = self.object.status
        response = super().form_valid(form)
        application_status_updated(self.object, self.request.user, old_status)
        messages.success(self.request, "Job application updated.")
        return response

    def get_success_url(self):
        return reverse("placements:application_detail", args=[self.object.pk])


class ApplicationDetailView(LoginRequiredMixin, DetailView):
    model = JobApplication
    template_name = "placements/application_detail.html"
    queryset = JobApplication.objects.select_related("trainee__user", "batch").prefetch_related(
        "interviews__updated_by", "audit_entries__actor"
    )

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit_application"] = (
            self.request.user.is_trainee_role
            and self.object.trainee.user_id == self.request.user.pk
            and self.object.trainee.is_verified
        )
        context["is_admin"] = self.request.user.is_admin_role
        return context


class ApplicationDeleteView(VerifiedTraineeMixin, DeleteView):
    model = JobApplication
    template_name = "placements/application_confirm_delete.html"
    success_url = reverse_lazy("placements:applications")

    def get_queryset(self):
        return JobApplication.objects.filter(trainee__user=self.request.user)

    @transaction.atomic
    def form_valid(self, form):
        application = self.object
        from placements.workflow import notify_workflow_users

        notify_workflow_users(
            application.trainee,
            "application.deleted",
            f"Application to {application.company_name} was deleted.",
            self.request.user,
        )
        response = super().form_valid(form)
        messages.success(self.request, "Job application deleted.")
        return response


class InterviewListView(AdminRequiredMixin, ListView):
    model = ApplicationInterview
    template_name = "placements/interview_list.html"
    context_object_name = "interviews"
    paginate_by = 15

    def get_queryset(self):
        queryset = ApplicationInterview.objects.select_related(
            "application__trainee__user", "application__batch", "updated_by"
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(application__company_name__icontains=query)
                | Q(application__job_role__icontains=query)
                | Q(application__trainee__user__first_name__icontains=query)
                | Q(application__trainee__user__last_name__icontains=query)
                | Q(hr_name__icontains=query)
            )
        if self.request.GET.get("batch"):
            queryset = queryset.filter(application__batch_id=self.request.GET["batch"])
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.GET.get("start"):
            queryset = queryset.filter(interview_date__date__gte=self.request.GET["start"])
        if self.request.GET.get("end"):
            queryset = queryset.filter(interview_date__date__lte=self.request.GET["end"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from batches.models import Batch

        context["batch_choices"] = Batch.objects.order_by("batch_number")
        context["status_choices"] = ApplicationInterview.Status.choices
        return context


class InterviewCreateView(AdminRequiredMixin, CreateView):
    model = ApplicationInterview
    form_class = ApplicationInterviewForm
    template_name = "placements/interview_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.application = get_object_or_404(
            JobApplication.objects.select_related("trainee", "batch"),
            pk=kwargs["application_id"],
        )
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        form.instance.application = self.application
        save_interview_update(form.instance, self.request.user)
        messages.success(self.request, "HR interview status saved and synchronized.")
        return redirect("placements:application_detail", pk=self.application.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["application"] = self.application
        return context


class InterviewUpdateView(AdminRequiredMixin, UpdateView):
    model = ApplicationInterview
    form_class = ApplicationInterviewForm
    template_name = "placements/interview_form.html"
    queryset = ApplicationInterview.objects.select_related("application__trainee__user", "application__batch")

    @transaction.atomic
    def form_valid(self, form):
        save_interview_update(form.instance, self.request.user)
        messages.success(self.request, "HR interview status saved and synchronized.")
        return redirect("placements:application_detail", pk=self.object.application_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["application"] = self.object.application
        return context
