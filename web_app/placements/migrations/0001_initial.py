import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q

import placements.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("batches", "0001_initial"),
        ("trainees", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Placement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("company_name", models.CharField(max_length=180)),
                ("company_location", models.CharField(max_length=180)),
                ("hr_name", models.CharField(max_length=150)),
                ("hr_email", models.EmailField(max_length=254)),
                ("hr_phone", models.CharField(max_length=10, validators=[django.core.validators.RegexValidator(message="Enter a valid 10-digit Indian mobile number.", regex="^[6-9]\\d{9}$")])),
                ("job_title", models.CharField(max_length=150)),
                ("offer_date", models.DateField()),
                ("joining_date", models.DateField(blank=True, null=True)),
                ("package_lpa", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("offer_letter", models.FileField(blank=True, upload_to="placements/offers/", validators=[placements.models.validate_offer_letter])),
                ("status", models.CharField(choices=[("OFFERED", "Offered"), ("JOINED", "Joined"), ("DECLINED", "Declined")], default="OFFERED", max_length=10)),
                ("verified", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="placements", to="batches.batch")),
                ("trainee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="placements", to="trainees.trainee")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verified_placements", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-offer_date", "-created_at")},
        ),
        migrations.AddConstraint(
            model_name="placement",
            constraint=models.CheckConstraint(condition=Q(("joining_date__isnull", True), ("joining_date__gte", F("offer_date")), _connector="OR"), name="placement_joining_on_or_after_offer"),
        ),
        migrations.AddIndex(
            model_name="placement",
            index=models.Index(fields=["company_name"], name="placements_company_idx"),
        ),
        migrations.AddIndex(
            model_name="placement",
            index=models.Index(fields=["status"], name="placements_status_idx"),
        ),
    ]
