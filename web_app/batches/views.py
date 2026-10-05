from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.views import View
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect

from accounts.models import User
from accounts.permissions import TrainerRequiredMixin
from batches.forms import BatchForm
from batches.models import Batch
from batches.services import complete_batch


class BatchListView(LoginRequiredMixin, ListView):
    model = Batch
    template_name = "batches/batch_list.html"
    context_object_name = "batches"
    paginate_by = 10

    def get_queryset(self):
        queryset = Batch.objects.visible_to(self.request.user).select_related("trainer").annotate(trainee_count=Count("enrollments", distinct=True)).order_by("-start_date", "name", "pk")
        if self.request.user.role == User.Role.TRAINER and self.request.GET.get("mine") == "1":
            queryset = queryset.filter(trainer=self.request.user)
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(course__icontains=query) | Q(trainer__first_name__icontains=query) | Q(trainer__last_name__icontains=query))
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.user.role == User.Role.ADMIN and self.request.GET.get("trainer"):
            queryset = queryset.filter(trainer_id=self.request.GET["trainer"])
        if self.request.GET.get("start"):
            queryset = queryset.filter(start_date__gte=self.request.GET["start"])
        if self.request.GET.get("end"):
            queryset = queryset.filter(end_date__lte=self.request.GET["end"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = Batch.Status.choices
        context["trainers"] = User.objects.filter(role=User.Role.TRAINER).order_by("first_name", "username")
        context["manageable_batch_ids"] = set(Batch.objects.manageable_to(self.request.user).values_list("pk", flat=True))
        return context


class BatchDetailView(LoginRequiredMixin, DetailView):
    model = Batch
    template_name = "batches/batch_detail.html"
    queryset = Batch.objects.select_related("trainer").prefetch_related("enrollments__trainee__user")

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollments = self.object.enrollments.select_related("trainee__user").all()
        if self.request.user.role == User.Role.TRAINEE and not self.request.user.is_superuser:
            enrollments = enrollments.filter(trainee__user=self.request.user)
        elif self.request.user.role == User.Role.TRAINER and self.object.trainer_id != self.request.user.pk:
            enrollments = enrollments.none()
        context["enrollments"] = enrollments
        context["can_manage_batch"] = Batch.objects.manageable_to(self.request.user).filter(pk=self.object.pk).exists()
        return context


class BatchCreateView(TrainerRequiredMixin, CreateView):
    model = Batch
    form_class = BatchForm
    template_name = "batches/batch_form.html"
    success_url = reverse_lazy("batches:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        if self.request.user.role == User.Role.TRAINER:
            form.instance.trainer = self.request.user
        messages.success(self.request, "Batch created successfully.")
        return super().form_valid(form)


class BatchUpdateView(TrainerRequiredMixin, UpdateView):
    model = Batch
    form_class = BatchForm
    template_name = "batches/batch_form.html"
    success_url = reverse_lazy("batches:list")

    def get_queryset(self):
        return Batch.objects.manageable_to(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Batch updated successfully.")
        return super().form_valid(form)


class BatchDeleteView(TrainerRequiredMixin, DeleteView):
    model = Batch
    template_name = "batches/batch_confirm_delete.html"
    success_url = reverse_lazy("batches:list")

    def get_queryset(self):
        return Batch.objects.manageable_to(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Batch deleted.")
        return super().form_valid(form)


class BatchCompleteView(TrainerRequiredMixin, View):
    def get(self, request, pk):
        get_object_or_404(Batch.objects.manageable_to(request.user), pk=pk)
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        batch = get_object_or_404(Batch.objects.manageable_to(request.user), pk=pk)
        complete_batch(batch, actor=request.user)
        messages.success(request, "Batch marked as completed.")
        return redirect("batches:detail", pk=batch.pk)
