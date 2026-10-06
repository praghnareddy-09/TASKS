from django.contrib import messages
from django.db.models import Count, Q
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.views import View
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect

from accounts.models import User
from accounts.permissions import AdminRequiredMixin
from batches.forms import BatchForm
from batches.models import Batch
from batches.services import complete_batch
from trainees.forms import BatchEnrollmentForm
from trainees.models import Enrollment, Trainee
from trainees.services import enroll_trainee, unenroll_trainee


class BatchListView(AdminRequiredMixin, ListView):
    model = Batch
    template_name = "batches/batch_list.html"
    context_object_name = "batches"
    paginate_by = 10

    def get_queryset(self):
        queryset = Batch.objects.visible_to(self.request.user).select_related("trainer").annotate(trainee_count=Count("enrollments", distinct=True)).order_by("-start_date", "name", "pk")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(course__icontains=query) | Q(trainer__first_name__icontains=query) | Q(trainer__last_name__icontains=query))
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.GET.get("trainer"):
            queryset = queryset.filter(trainer_id=self.request.GET["trainer"])
        if self.request.GET.get("start"):
            queryset = queryset.filter(start_date__gte=self.request.GET["start"])
        if self.request.GET.get("end"):
            queryset = queryset.filter(end_date__lte=self.request.GET["end"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = Batch.Status.choices
        context["trainers"] = User.objects.filter(role=User.Role.ADMIN).order_by("first_name", "username")
        context["manageable_batch_ids"] = set(Batch.objects.manageable_to(self.request.user).values_list("pk", flat=True))
        return context


class BatchDetailView(AdminRequiredMixin, DetailView):
    model = Batch
    template_name = "batches/batch_detail.html"
    queryset = Batch.objects.select_related("trainer").prefetch_related("enrollments__trainee__user")

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollments = self.object.enrollments.select_related("trainee__user").all()
        context["enrollments"] = enrollments
        context["can_manage_batch"] = Batch.objects.manageable_to(self.request.user).filter(pk=self.object.pk).exists()
        if context["can_manage_batch"]:
            context["enrollment_form"] = BatchEnrollmentForm(
                batch=self.object,
                request_user=self.request.user,
            )
        return context


class BatchEnrollmentView(AdminRequiredMixin, View):
    def post(self, request, pk):
        batch = get_object_or_404(Batch.objects.manageable_to(request.user), pk=pk)
        form = BatchEnrollmentForm(
            request.POST,
            batch=batch,
            request_user=request.user,
        )
        if not form.is_valid():
            messages.error(request, "Select one or more trainees who are not already enrolled.")
            return redirect("batches:detail", pk=batch.pk)

        for trainee in form.cleaned_data["trainees"]:
            try:
                enroll_trainee(trainee, batch, request.user)
            except ValidationError:
                messages.error(request, f"{trainee} is already enrolled in this batch.")
            else:
                messages.success(request, f"{trainee} enrolled in {batch.name}.")
        return redirect("batches:detail", pk=batch.pk)


class BatchEnrollmentRemoveView(AdminRequiredMixin, View):
    def post(self, request, pk, trainee_id):
        batch = get_object_or_404(Batch.objects.manageable_to(request.user), pk=pk)
        trainee = get_object_or_404(Trainee.objects.visible_to(request.user), pk=trainee_id)
        if not Enrollment.objects.filter(batch=batch, trainee=trainee).exists():
            get_object_or_404(Enrollment, batch=batch, trainee=trainee)
        unenroll_trainee(trainee, batch, request.user)
        messages.success(request, f"{trainee} removed from {batch.name}.")
        return redirect("batches:detail", pk=batch.pk)


class BatchCreateView(AdminRequiredMixin, CreateView):
    model = Batch
    form_class = BatchForm
    template_name = "batches/batch_form.html"
    success_url = reverse_lazy("batches:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Batch created successfully.")
        return super().form_valid(form)


class BatchUpdateView(AdminRequiredMixin, UpdateView):
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


class BatchDeleteView(AdminRequiredMixin, DeleteView):
    model = Batch
    template_name = "batches/batch_confirm_delete.html"
    success_url = reverse_lazy("batches:list")

    def get_queryset(self):
        return Batch.objects.manageable_to(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Batch deleted.")
        return super().form_valid(form)


class BatchCompleteView(AdminRequiredMixin, View):
    def get(self, request, pk):
        get_object_or_404(Batch.objects.manageable_to(request.user), pk=pk)
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        batch = get_object_or_404(Batch.objects.manageable_to(request.user), pk=pk)
        complete_batch(batch, actor=request.user)
        messages.success(request, "Batch marked as completed.")
        return redirect("batches:detail", pk=batch.pk)
