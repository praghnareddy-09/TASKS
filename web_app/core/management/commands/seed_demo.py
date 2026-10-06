from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from batches.models import Batch
from placements.models import Placement
from trainees.models import Enrollment, Trainee


class Command(BaseCommand):
    help = "Create a complete TweakTech demo dataset."

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        admin, _ = User.objects.update_or_create(
            username="admin",
            defaults={"email": "admin@tweaktech.example", "first_name": "Taylor", "last_name": "Admin", "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True},
        )
        admin.set_password("AdminDemo123!")
        admin.save()
        trainees = []
        for number in range(1, 21):
            user, _ = User.objects.update_or_create(
                username=f"trainee{number:02d}",
                defaults={"email": f"trainee{number:02d}@tweaktech.example", "first_name": f"Trainee{number}", "last_name": "Learner", "role": User.Role.TRAINEE},
            )
            user.set_password("TraineeDemo123!")
            user.save()
            profile, _ = Trainee.objects.get_or_create(user=user)
            profile.phone = f"+1 555 010 {number:04d}"
            profile.status = Trainee.Status.ACTIVE
            profile.save()
            trainees.append(profile)

        dates = [
            (today - timedelta(days=40), today - timedelta(days=12)),
            (today - timedelta(days=22), today + timedelta(days=8)),
            (today - timedelta(days=5), today + timedelta(days=25)),
            (today + timedelta(days=7), today + timedelta(days=37)),
            (today - timedelta(days=65), today - timedelta(days=35)),
            (today + timedelta(days=35), today + timedelta(days=65)),
        ]
        names = ["Launchpad", "CodeCraft", "Data Studio", "Cloud Foundations", "Product Design", "Python Essentials"]
        courses = ["Web Development", "Full-stack Django", "Data Analytics", "Cloud Engineering", "UX Design", "Python"]
        batches = []
        for index, (start, end) in enumerate(dates):
            status = Batch.Status.COMPLETED if end < today else Batch.Status.RUNNING if start <= today else Batch.Status.UPCOMING
            batch, created = Batch.objects.get_or_create(
                name=names[index],
                defaults={
                    "batch_number": (Batch.objects.order_by("-batch_number").values_list("batch_number", flat=True).first() or 0) + 1,
                    "course": courses[index],
                    "trainer": admin,
                    "start_date": start,
                    "end_date": end,
                    "status": status,
                },
            )
            if not created:
                batch.course = courses[index]
                batch.trainer = admin
                batch.start_date = start
                batch.end_date = end
                batch.status = status
                batch.save()
            batches.append(batch)
            for trainee in trainees:
                if (trainee.user.pk + index) % 3 != 0:
                    Enrollment.objects.get_or_create(trainee=trainee, batch=batch)
        companies = ["Northstar Labs", "BluePeak Systems", "Northstar Labs", "Cedar Works", "BrightPath", "Cloudline", "Aster Digital", "Riverstone Tech"]
        statuses = [
            Placement.Status.JOINED,
            Placement.Status.OFFERED,
            Placement.Status.JOINED,
            Placement.Status.DECLINED,
            Placement.Status.OFFERED,
            Placement.Status.JOINED,
            Placement.Status.OFFERED,
            Placement.Status.JOINED,
        ]
        for index, company in enumerate(companies):
            trainee = trainees[index]
            enrollment = Enrollment.objects.filter(trainee=trainee).select_related("batch").order_by("batch_id").first()
            if not enrollment:
                continue
            offer_date = today - timedelta(days=18 - index)
            status = statuses[index]
            defaults = {
                "batch": enrollment.batch,
                "company_name": company,
                "company_location": ["Mumbai", "Bengaluru", "Pune", "Hyderabad"][index % 4],
                "hr_name": f"HR Contact {index + 1}",
                "hr_email": f"hr{index + 1}@{company.lower().replace(' ', '')}.example",
                "hr_phone": f"987650000{index}",
                "job_title": ["Software Engineer", "Data Analyst", "Product Designer"][index % 3],
                "offer_date": offer_date,
                "joining_date": offer_date + timedelta(days=14) if status == Placement.Status.JOINED else None,
                "package_lpa": 6 + index * 0.5,
                "status": status,
                "verified": index % 3 == 0,
                "verified_by": admin if index % 3 == 0 else None,
            }
            placement = Placement.objects.filter(trainee=trainee).first()
            if placement:
                for field, value in defaults.items():
                    setattr(placement, field, value)
                placement.save()
            else:
                Placement.objects.create(trainee=trainee, **defaults)
        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
        self.stdout.write("Admin: admin / AdminDemo123!")
        self.stdout.write("Trainees: trainee01 through trainee20 / TraineeDemo123!")
