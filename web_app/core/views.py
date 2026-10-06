from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.db.models import Case, Count, IntegerField, Value, When
from django.db.models.functions import Lower
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView
from pathlib import Path

from accounts.models import User
from batches.models import Batch
from core.utils import ordinal
from placements.models import Placement
from placements.models import ApplicationInterview, JobApplication, WorkflowNotification
from trainees.models import Enrollment, Trainee
from accounts.permissions import AdminRequiredMixin


class OfflineView(TemplateView):
    template_name = "offline.html"


def service_worker(request):
    worker_path = Path(settings.BASE_DIR) / "static" / "js" / "sw.js"
    response = HttpResponse(worker_path.read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard_trainee.html"

    def get_template_names(self):
        if self.request.user.is_admin_role:
            return ["core/dashboard_admin.html"]
        return ["core/dashboard_trainee.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()
        if user.is_admin_role:
            joined = Placement.objects.filter(status=Placement.Status.JOINED)
            context.update(
                active_batches=Batch.objects.filter(status=Batch.Status.RUNNING).count(),
                total_trainees=User.objects.filter(role=User.Role.TRAINEE).count(),
                total_placed=joined.count(),
                companies_hired_from=joined.annotate(company_key=Lower("company_name")).values("company_key").distinct().count(),
                pending_verification=Placement.objects.filter(verified=False).count(),
                placement_status_counts=list(Placement.objects.values("status").annotate(total=Count("id")).order_by("status")),
                upcoming_batches=Batch.objects.filter(start_date__gte=today).select_related("trainer").order_by("start_date")[:5],
                recent_placements=Placement.objects.select_related("trainee__user", "batch").order_by("-updated_at", "-pk")[:8],
                pending_registrations=User.objects.filter(is_approved=False).order_by("date_joined", "pk")[:5],
                pending_registration_count=User.objects.filter(is_approved=False).count(),
            )
        else:
            trainee = Trainee.objects.get(user=user)
            batch = (
                Batch.objects.filter(enrollments__trainee__user=user)
                .order_by(
                    Case(
                        When(status=Batch.Status.RUNNING, then=Value(0)),
                        When(status=Batch.Status.UPCOMING, then=Value(1)),
                        default=Value(2),
                        output_field=IntegerField(),
                    ),
                    "-start_date",
                    "-created_at",
                    "-pk",
                )
                .first()
            )
            latest_placement = Placement.objects.filter(trainee__user=user).order_by(
                "-updated_at", "-pk"
            ).first()
            applications = JobApplication.objects.filter(trainee__user=user)
            application_status_counts = dict(
                applications.values_list("status").annotate(total=Count("pk"))
            )
            context.update(
                batch_ordinal=ordinal(batch.batch_number) if batch else None,
                latest_placement=latest_placement,
                placement_status=latest_placement.status if latest_placement else None,
                profile_completion=trainee.profile_completion_percentage(),
                trainee=trainee,
                application_count=applications.count(),
                active_interview_count=ApplicationInterview.objects.filter(
                    application__trainee__user=user,
                    status=ApplicationInterview.Status.INTERVIEW_SCHEDULED,
                ).count(),
                recent_applications=applications.select_related("batch").prefetch_related("interviews").order_by("-updated_at")[:5],
                interview_count=ApplicationInterview.objects.filter(application__trainee__user=user).count(),
                verification_status=trainee.verification_status,
                is_verified=trainee.is_verified,
                application_status_counts=application_status_counts,
                selected_applications=application_status_counts.get(JobApplication.Status.SELECTED, 0),
                offers_received=application_status_counts.get(JobApplication.Status.OFFER_RECEIVED, 0),
                rejected_applications=application_status_counts.get(JobApplication.Status.REJECTED, 0),
            )
        return context


class AnalyticsView(AdminRequiredMixin, TemplateView):
    template_name = "core/analytics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        applications = JobApplication.objects.all()
        verified_trainee_ids = set(
            Trainee.objects.verified().values_list("pk", flat=True)
        )
        legacy_placed_ids = set(
            Placement.objects.filter(status=Placement.Status.JOINED).values_list("trainee_id", flat=True)
        )
        application_placed_ids = set(
            applications.filter(status__in=[JobApplication.Status.SELECTED, JobApplication.Status.JOINED])
            .values_list("trainee_id", flat=True)
        )
        placed_ids = legacy_placed_ids | application_placed_ids
        assigned_count = Enrollment.objects.filter(trainee__verification_status=Trainee.VerificationStatus.VERIFIED).values("trainee_id").distinct().count()
        batch_rows = list(
            Batch.objects.annotate(
                trainee_count=Count("enrollments", distinct=True),
                application_count=Count("job_applications", distinct=True),
                placed_count=Count(
                    "job_applications__trainee",
                    filter=Q(job_applications__status__in=[JobApplication.Status.SELECTED, JobApplication.Status.JOINED]),
                    distinct=True,
                ),
            ).order_by("batch_number")
        )
        for batch in batch_rows:
            batch.placement_rate = round(100 * batch.placed_count / batch.trainee_count, 1) if batch.trainee_count else 0
        context.update(
            total_batches=Batch.objects.count(),
            active_batches=Batch.objects.filter(status=Batch.Status.RUNNING).count(),
            completed_batches=Batch.objects.filter(status=Batch.Status.COMPLETED).count(),
            total_registered=Trainee.objects.count(),
            verified_trainees=len(verified_trainee_ids),
            assigned_trainees=assigned_count,
            active_trainees=Trainee.objects.filter(status=Trainee.Status.ACTIVE).count(),
            placed_trainees=len(placed_ids),
            total_applications=applications.count(),
            interviews_running=applications.filter(
                status__in=[
                    JobApplication.Status.ASSESSMENT,
                    JobApplication.Status.TECHNICAL_ROUND,
                    JobApplication.Status.L1_INTERVIEW,
                    JobApplication.Status.L2_INTERVIEW,
                    JobApplication.Status.HR_ROUND,
                ]
            ).count(),
            offers_released=applications.filter(status=JobApplication.Status.OFFER_RECEIVED).count(),
            selected_applications=applications.filter(status=JobApplication.Status.SELECTED).count(),
            rejected_applications=applications.filter(status=JobApplication.Status.REJECTED).count(),
            placement_percentage=round(100 * len(placed_ids) / assigned_count, 1) if assigned_count else 0,
            batch_rows=batch_rows,
            company_rows=list(
                applications.values("company_name").annotate(
                    applications=Count("pk"),
                    placed=Count(
                        "trainee_id",
                        filter=Q(status__in=[JobApplication.Status.SELECTED, JobApplication.Status.JOINED]),
                        distinct=True,
                    ),
                ).order_by("-applications", "company_name")[:10]
            ),
        )
        return context


class WorkflowNotificationListView(LoginRequiredMixin, ListView):
    template_name = "core/notifications.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        return WorkflowNotification.objects.filter(recipient=self.request.user).select_related(
            "trainee__user", "application"
        )

    def post(self, request, *args, **kwargs):
        WorkflowNotification.objects.filter(recipient=request.user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return redirect("core:notifications")


class WorkflowNotificationCountView(LoginRequiredMixin, View):
    def get(self, request):
        count = WorkflowNotification.objects.filter(recipient=request.user, read_at__isnull=True).count()
        return JsonResponse({"unread": count})


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
