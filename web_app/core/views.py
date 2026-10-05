from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.models import User
from batches.models import Batch
from placements.models import Placement


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        batches = Batch.objects.select_related("trainer").prefetch_related("enrollments__trainee__user")
        if not user.is_superuser and user.role != User.Role.ADMIN:
            if user.role == User.Role.TRAINER:
                batches = batches.filter(trainer=user)
            elif user.role == User.Role.TRAINEE:
                batches = batches.filter(enrollments__trainee__user=user).distinct()

        today = timezone.localdate()
        upcoming = batches.filter(start_date__gte=today).order_by("start_date")[:5]
        context.update(
            active_batches=batches.filter(status=Batch.Status.RUNNING).distinct().count(),
            total_trainees=User.objects.filter(role=User.Role.TRAINEE).count() if user.role == User.Role.ADMIN else
                batches.values("enrollments__trainee_id").distinct().count(),
            upcoming_batches=upcoming,
            all_batches_count=Batch.objects.count() if user.role == User.Role.TRAINER else None,
        )
        if user.role == User.Role.TRAINEE:
            placements = Placement.objects.filter(trainee__user=user)
            context["placement_status"] = placements.order_by("-updated_at").values_list("status", flat=True).first()
        elif user.role == User.Role.ADMIN or user.is_superuser:
            joined = Placement.objects.filter(status=Placement.Status.JOINED)
            context.update(
                total_placed=joined.count(),
                placement_companies=Placement.objects.values("company_name").distinct().count(),
                companies_hired_from=joined.annotate(company_key=Lower("company_name")).values("company_key").distinct().count(),
                pending_verification=Placement.objects.filter(verified=False).count(),
                placement_status_counts=list(Placement.objects.values("status").annotate(total=Count("id")).order_by("status")),
                batch_placement_rates=Batch.objects.annotate(
                    trainee_total=Count("enrollments", distinct=True),
                    placed_total=Count("placements", filter=Q(placements__status=Placement.Status.JOINED), distinct=True),
                ).select_related("trainer"),
            )
            for batch in context["batch_placement_rates"]:
                batch.placement_rate = round(batch.placed_total * 100 / batch.trainee_total) if batch.trainee_total else 0
        return context


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
