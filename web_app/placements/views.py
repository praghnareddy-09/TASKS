import csv
import logging
from collections import Counter, defaultdict
from io import StringIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.models import User
from accounts.permissions import AdminRequiredMixin, TrainerRequiredMixin
from batches.models import Batch
from placements.forms import PlacementForm
from placements.models import Placement

logger = logging.getLogger(__name__)


class TraineePlacementMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role == User.Role.TRAINEE


def notify_team(placement, request):
    recipients = set(
        User.objects.filter(role=User.Role.ADMIN, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if placement.batch.trainer.email:
        recipients.add(placement.batch.trainer.email)
    if not recipients:
        return
    try:
        send_mail(
            subject=f"Placement update: {placement.trainee} at {placement.company_name}",
            message=(
                f"{placement.trainee} submitted a {placement.get_status_display().lower()} "
                f"placement at {placement.company_name} ({placement.batch.name})."
            ),
            from_email=None,
            recipient_list=sorted(recipients),
            fail_silently=False,
        )
    except Exception:
        logger.exception("Could not send placement notification for placement %s", placement.pk)
        messages.warning(request, "Placement saved, but the notification email could not be sent.")


class MyPlacementListView(TraineePlacementMixin, ListView):
    model = Placement
    template_name = "placements/my_list.html"
    context_object_name = "placements"
    paginate_by = 10

    def get_queryset(self):
        return Placement.objects.manageable_by_trainee(self.request.user).select_related("batch", "trainee__user", "verified_by")


class MyPlacementCreateView(TraineePlacementMixin, CreateView):
    model = Placement
    form_class = PlacementForm
    template_name = "placements/placement_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.trainee = self.request.user.trainee_profile
        response = super().form_valid(form)
        notify_team(self.object, self.request)
        messages.success(self.request, "Placement saved successfully.")
        return response

    def get_success_url(self):
        return reverse("placements:my_list")


class MyPlacementUpdateView(TraineePlacementMixin, UpdateView):
    model = Placement
    form_class = PlacementForm
    template_name = "placements/placement_form.html"

    def get_queryset(self):
        return Placement.objects.manageable_by_trainee(self.request.user).select_related("batch", "trainee__user")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        notify_team(self.object, self.request)
        messages.success(self.request, "Placement updated successfully.")
        return response

    def get_success_url(self):
        return reverse("placements:my_list")


class PlacementListView(TrainerRequiredMixin, ListView):
    model = Placement
    template_name = "placements/placement_list.html"
    context_object_name = "placements"
    paginate_by = 10

    def get_queryset(self):
        queryset = Placement.objects.visible_to(self.request.user).select_related(
            "trainee__user", "batch", "verified_by"
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(trainee__user__username__icontains=query)
                | Q(trainee__user__first_name__icontains=query)
                | Q(trainee__user__last_name__icontains=query)
                | Q(company_name__icontains=query)
                | Q(hr_name__icontains=query)
            )
        if self.request.GET.get("batch"):
            queryset = queryset.filter(batch_id=self.request.GET["batch"])
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.GET.get("verified") in {"yes", "no"}:
            queryset = queryset.filter(verified=self.request.GET["verified"] == "yes")
        start_value = self.request.GET.get("start", "")
        end_value = self.request.GET.get("end", "")
        start_date = parse_date(start_value) if start_value else None
        end_date = parse_date(end_value) if end_value else None
        if start_value and not start_date:
            messages.error(self.request, "Enter a valid start date.")
        elif start_date:
            queryset = queryset.filter(offer_date__gte=start_date)
        if end_value and not end_date:
            messages.error(self.request, "Enter a valid end date.")
        elif end_date:
            queryset = queryset.filter(offer_date__lte=end_date)
        if start_date and end_date and start_date > end_date:
            messages.error(self.request, "Start date must be on or before end date.")
            queryset = queryset.none()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = Batch.objects.visible_to(self.request.user).order_by("name")
        context.update(
            batch_choices=queryset,
            status_choices=Placement.Status.choices,
            is_admin=self.request.user.is_superuser or self.request.user.role == User.Role.ADMIN,
        )
        return context


def company_directory_rows(placements):
    grouped = defaultdict(list)
    for placement in placements:
        grouped[placement.company_name.casefold()].append(placement)

    companies = []
    for company_key, records in grouped.items():
        names = Counter(record.company_name for record in records)
        company_name = sorted(names, key=lambda name: (-names[name], name.casefold(), name))[0]
        contacts = {}
        batches = {}
        trainee_ids = set()
        for record in records:
            contact_key = (
                record.company_location.casefold(),
                record.hr_name.casefold(),
                record.hr_email.casefold(),
                record.hr_phone,
            )
            contact = contacts.setdefault(
                contact_key,
                {
                    "location": record.company_location,
                    "name": record.hr_name,
                    "email": record.hr_email,
                    "phone": record.hr_phone,
                    "placements": [],
                    "trainee_ids": set(),
                    "batches": {},
                },
            )
            contact["placements"].append(record)
            contact["trainee_ids"].add(record.trainee_id)
            contact["batches"][record.batch_id] = record.batch
            batches[record.batch_id] = record.batch
            trainee_ids.add(record.trainee_id)
        for contact in contacts.values():
            contact["trainee_count"] = len(contact.pop("trainee_ids"))
            contact["batches"] = sorted(contact.pop("batches").values(), key=lambda batch: batch.name.casefold())
        companies.append(
            {
                "key": company_key,
                "name": company_name,
                "slug": slugify(company_name) or "company",
                "placement_id": records[0].pk,
                "trainee_count": len(trainee_ids),
                "batches": sorted(batches.values(), key=lambda batch: batch.name.casefold()),
                "contacts": list(contacts.values()),
            }
        )
    return sorted(companies, key=lambda company: (company["name"].casefold(), company["key"]))


class CompanyDirectoryView(TrainerRequiredMixin, ListView):
    model = Placement
    template_name = "placements/company_directory.html"
    context_object_name = "companies"
    paginate_by = 10

    def get_queryset(self):
        queryset = Placement.objects.visible_to(self.request.user).filter(
            status=Placement.Status.JOINED
        ).select_related("trainee__user", "batch", "batch__trainer").order_by(
            "company_name", "company_location", "hr_name", "trainee__user__last_name", "pk"
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(company_name__icontains=query) | Q(hr_name__icontains=query)
            )
        if self.request.GET.get("batch"):
            queryset = queryset.filter(batch_id=self.request.GET["batch"])
        if self.request.GET.get("verified") in {"yes", "no"}:
            queryset = queryset.filter(verified=self.request.GET["verified"] == "yes")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        companies = company_directory_rows(self.object_list)
        paginator = Paginator(companies, self.paginate_by)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            companies=page_obj.object_list,
            page_obj=page_obj,
            paginator=paginator,
            is_paginated=page_obj.has_other_pages(),
            batch_choices=Batch.objects.visible_to(self.request.user).order_by("name"),
        )
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get("format") != "csv":
            return super().render_to_response(context, **response_kwargs)
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Company",
                "Location",
                "HR name",
                "HR email",
                "HR phone",
                "Joined trainees",
                "Batches",
                "Verified",
            ]
        )
        for company in company_directory_rows(self.get_queryset()):
            for contact in company["contacts"]:
                contact_placements = contact["placements"]
                writer.writerow(
                    [
                        company["name"],
                        contact["location"],
                        contact["name"],
                        contact["email"],
                        contact["phone"],
                        len({placement.trainee_id for placement in contact_placements}),
                        ", ".join(sorted({placement.batch.name for placement in contact_placements})),
                        "Yes" if all(placement.verified for placement in contact_placements) else "No",
                    ]
                )
        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="company-hr-directory.csv"'
        return response


class CompanyDetailView(TrainerRequiredMixin, DetailView):
    model = Placement
    template_name = "placements/company_detail.html"
    context_object_name = "company_placement"
    pk_url_kwarg = "placement_id"

    def get_queryset(self):
        return Placement.objects.visible_to(self.request.user).filter(
            status=Placement.Status.JOINED
        ).select_related("trainee__user", "batch", "batch__trainer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_name = self.object.company_name
        records = self.get_queryset().filter(company_name__iexact=company_name).order_by(
            "trainee__user__last_name", "trainee__user__first_name", "pk"
        )
        grouped = company_directory_rows(records)
        context["company"] = grouped[0]
        context["placements"] = records
        return context


class MyCompanyView(TraineePlacementMixin, DetailView):
    model = Placement
    template_name = "placements/my_company.html"
    context_object_name = "placement"

    def get_queryset(self):
        return Placement.objects.manageable_by_trainee(self.request.user).filter(
            status=Placement.Status.JOINED
        ).select_related("trainee__user", "batch", "verified_by")

    def get_object(self, queryset=None):
        return self.get_queryset().order_by("-joining_date", "-updated_at").first()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.render_to_response(self.get_context_data(object=self.object))


class PlacementDetailView(LoginRequiredMixin, DetailView):
    model = Placement
    template_name = "placements/placement_detail.html"
    context_object_name = "placement"

    def get_queryset(self):
        return Placement.objects.visible_to(self.request.user).select_related(
            "trainee__user", "batch__trainer", "verified_by"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_admin"] = user.is_superuser or user.role == User.Role.ADMIN
        context["can_edit"] = context["is_admin"]
        context["is_trainee_owner"] = user.role == User.Role.TRAINEE and self.object.trainee.user_id == user.pk
        return context


class PlacementUpdateView(AdminRequiredMixin, UpdateView):
    model = Placement
    form_class = PlacementForm
    template_name = "placements/placement_form.html"
    success_url = reverse_lazy("placements:list")

    def get_queryset(self):
        return Placement.objects.all().select_related("trainee__user", "batch")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request_user"] = self.object.trainee.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Placement updated successfully.")
        return response


class PlacementDeleteView(AdminRequiredMixin, DeleteView):
    model = Placement
    template_name = "placements/placement_confirm_delete.html"
    success_url = reverse_lazy("placements:list")

    def get_queryset(self):
        return Placement.objects.all()

    def form_valid(self, form):
        messages.success(self.request, "Placement deleted.")
        return super().form_valid(form)


class PlacementVerifyView(AdminRequiredMixin, View):
    def post(self, request, pk):
        placement = get_object_or_404(Placement.objects.all(), pk=pk)
        placement.verified = not placement.verified
        placement.verified_by = request.user if placement.verified else None
        placement.save(update_fields=["verified", "verified_by", "updated_at"])
        messages.success(request, "Placement verification updated.")
        return redirect("placements:detail", pk=placement.pk)


class PlacementFileView(LoginRequiredMixin, View):
    def get(self, request, pk):
        placement = get_object_or_404(
            Placement.objects.visible_to(request.user).select_related("trainee__user", "batch__trainer"),
            pk=pk,
        )
        if not placement.offer_letter:
            raise Http404("No offer letter is available.")
        return FileResponse(placement.offer_letter.open("rb"), as_attachment=True, filename=placement.offer_letter.name.rsplit("/", 1)[-1])


class PlacementReportView(AdminRequiredMixin, View):
    def get(self, request):
        batches = Batch.objects.annotate(
            trainee_total=Count("enrollments", distinct=True),
            placed_total=Count(
                "placements",
                filter=Q(placements__status=Placement.Status.JOINED),
                distinct=True,
            ),
            company_total=Count("placements__company_name", distinct=True),
        ).order_by("name")
        if request.GET.get("format") == "csv":
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["Batch", "Trainees", "Joined placements", "Placement rate (%)", "Companies"])
            for batch in batches:
                rate = round(batch.placed_total * 100 / batch.trainee_total, 1) if batch.trainee_total else 0
                writer.writerow([batch.name, batch.trainee_total, batch.placed_total, rate, batch.company_total])
            response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="placement-summary.csv"'
            return response
        rows = list(batches)
        for batch in rows:
            batch.placement_rate = round(batch.placed_total * 100 / batch.trainee_total, 1) if batch.trainee_total else 0
        from django.shortcuts import render

        return render(request, "placements/placement_report.html", {"batches": rows})
