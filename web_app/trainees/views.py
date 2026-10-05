from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.models import User
from accounts.permissions import TrainerRequiredMixin
from batches.models import Batch
from trainees.forms import TraineeForm
from trainees.models import Enrollment, Trainee
from trainees.services import enroll_trainee, unenroll_trainee


class TraineeListView(LoginRequiredMixin, ListView):
    model = Trainee
    template_name = "trainees/trainee_list.html"
    context_object_name = "trainees"
    paginate_by = 10

    def get_queryset(self):
        batch_count = Count("enrollments", distinct=True)
        if self.request.user.role == User.Role.TRAINER:
            batch_count = Count(
                "enrollments",
                filter=Q(enrollments__batch__trainer=self.request.user),
                distinct=True,
            )
        queryset = Trainee.objects.visible_to(self.request.user).select_related("user").annotate(batch_count=batch_count).order_by("user__first_name", "user__username", "pk")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(user__username__icontains=query) | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(user__email__icontains=query) | Q(phone__icontains=query))
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
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
        context["batch_choices"] = Batch.objects.visible_to(self.request.user)
        return context


class TraineeDetailView(LoginRequiredMixin, DetailView):
    model = Trainee
    template_name = "trainees/trainee_detail.html"
    queryset = Trainee.objects.select_related("user").prefetch_related("enrollments__batch")

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollments = self.object.enrollments.select_related("batch").all()
        if self.request.user.role == User.Role.TRAINER:
            enrollments = enrollments.filter(batch__trainer=self.request.user)
        context["enrollments"] = enrollments
        return context


class TraineeCreateView(TrainerRequiredMixin, CreateView):
    model = Trainee
    form_class = TraineeForm
    template_name = "trainees/trainee_form.html"
    success_url = reverse_lazy("trainees:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Trainee created successfully.")
        return super().form_valid(form)


class TraineeUpdateView(TrainerRequiredMixin, UpdateView):
    model = Trainee
    form_class = TraineeForm
    template_name = "trainees/trainee_form.html"
    success_url = reverse_lazy("trainees:list")

    def get_queryset(self):
        return Trainee.objects.visible_to(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Trainee updated successfully.")
        return super().form_valid(form)


class TraineeDeleteView(TrainerRequiredMixin, DeleteView):
    model = Trainee
    template_name = "trainees/trainee_confirm_delete.html"
    success_url = reverse_lazy("trainees:list")

    def get_queryset(self):
        return Trainee.objects.visible_to(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Trainee deleted.")
        return super().form_valid(form)


class EnrollmentToggleView(LoginRequiredMixin, View):
    def post(self, request, trainee_id, batch_id):
        if request.user.role not in (User.Role.ADMIN, User.Role.TRAINER) and not request.user.is_superuser:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=trainee_id)
        batch = get_object_or_404(Batch.objects.manageable_to(request.user), pk=batch_id)
        enrollment = Enrollment.objects.filter(trainee=trainee, batch=batch)
        if enrollment.exists():
            unenroll_trainee(trainee, batch)
            messages.success(request, "Trainee unenrolled.")
        else:
            enroll_trainee(trainee, batch)
            messages.success(request, "Trainee enrolled.")
        return redirect("trainees:detail", pk=trainee.pk)
