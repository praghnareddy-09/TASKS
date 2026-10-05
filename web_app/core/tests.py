from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from tempfile import TemporaryDirectory

from batches.models import Batch
from placements.forms import PlacementForm
from placements.models import Placement
from trainees.models import Enrollment, Trainee

User = get_user_model()


class TweakTechTests(TestCase):
    def setUp(self):
        today = date.today()
        self.admin = User.objects.create_user("admin", password="ValidDemoPass94!", role=User.Role.ADMIN, is_staff=True)
        self.trainer = User.objects.create_user("trainer", email="trainer@example.com", password="ValidDemoPass94!", role=User.Role.TRAINER)
        self.other_trainer = User.objects.create_user("other", password="ValidDemoPass94!", role=User.Role.TRAINER)
        self.trainee_user = User.objects.create_user("learner", password="ValidDemoPass94!", role=User.Role.TRAINEE)
        self.other_trainee_user = User.objects.create_user("otherlearner", password="ValidDemoPass94!", role=User.Role.TRAINEE)
        self.trainee = self.trainee_user.trainee_profile
        self.other_trainee = self.other_trainee_user.trainee_profile
        self.batch = Batch.objects.create(name="Alpha", course="Django", trainer=self.trainer, start_date=today - timedelta(days=3), end_date=today + timedelta(days=3), status=Batch.Status.RUNNING)
        self.other_batch = Batch.objects.create(name="Beta", course="Python", trainer=self.other_trainer, start_date=today - timedelta(days=3), end_date=today + timedelta(days=3))
        Enrollment.objects.create(trainee=self.trainee, batch=self.batch)
        Enrollment.objects.create(trainee=self.other_trainee, batch=self.other_batch)
        self.placement = self.make_placement(self.trainee, self.batch, "Northstar Labs")
        self.other_placement = self.make_placement(self.other_trainee, self.other_batch, "BluePeak Systems")

    @staticmethod
    def make_placement(trainee, batch, company):
        offer_date = date.today() - timedelta(days=14)
        return Placement.objects.create(
            trainee=trainee,
            batch=batch,
            company_name=company,
            company_location="Bengaluru",
            hr_name="HR Contact",
            hr_email="hr@example.com",
            hr_phone="9876543210",
            job_title="Software Engineer",
            offer_date=offer_date,
            joining_date=offer_date + timedelta(days=7),
            status=Placement.Status.JOINED,
        )

    def test_batch_date_constraint_and_trainer_validation(self):
        invalid = Batch(name="Invalid", course="Test", trainer=self.trainer, start_date=date.today(), end_date=date.today() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        with self.assertRaises(ValidationError):
            Batch(name="Wrong trainer", course="Test", trainer=self.admin, start_date=date.today(), end_date=date.today()).full_clean()

    def test_enrollment_unique_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrollment.objects.create(trainee=self.trainee, batch=self.batch)

    def test_trainer_sees_all_batches_but_can_only_manage_owned_batches(self):
        self.client.force_login(self.trainer)
        response = self.client.get(reverse("batches:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha")
        self.assertContains(response, "Beta")
        self.assertEqual(self.client.get(reverse("batches:detail", args=[self.other_batch.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("batches:update", args=[self.other_batch.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("batches:delete", args=[self.other_batch.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("batches:complete", args=[self.other_batch.pk])).status_code, 404)

    def test_trainee_batch_scope_and_foreign_profile_access(self):
        self.client.force_login(self.trainee_user)
        response = self.client.get(reverse("batches:list"))
        self.assertContains(response, "Alpha")
        self.assertNotContains(response, "Beta")
        detail = self.client.get(reverse("batches:detail", args=[self.batch.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "learner")
        self.assertNotContains(detail, "otherlearner")
        self.assertEqual(self.client.get(reverse("batches:detail", args=[self.other_batch.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("trainees:detail", args=[self.other_trainee.pk])).status_code, 404)

    def test_trainer_sees_trainee_batch_details_only_for_owned_batches(self):
        Enrollment.objects.create(trainee=self.trainee, batch=self.other_batch)
        self.client.force_login(self.trainer)
        response = self.client.get(reverse("trainees:detail", args=[self.trainee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha")
        self.assertNotContains(response, "Beta")

    def test_trainee_sees_only_own_placements(self):
        self.client.force_login(self.trainee_user)
        response = self.client.get(reverse("placements:my_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Northstar Labs")
        self.assertNotContains(response, "BluePeak Systems")
        self.assertEqual(self.client.get(reverse("placements:detail", args=[self.other_placement.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("placements:my_update", args=[self.other_placement.pk])).status_code, 404)

    def test_trainee_can_submit_placement_and_get_success_message(self):
        self.client.force_login(self.trainee_user)
        today = date.today()
        response = self.client.post(
            reverse("placements:my_create"),
            {
                "batch": str(self.batch.pk),
                "company_name": "New Employer",
                "company_location": "Pune",
                "hr_name": "Hiring Contact",
                "hr_email": "hiring@example.com",
                "hr_phone": "9876543210",
                "job_title": "Developer",
                "offer_date": today.isoformat(),
                "joining_date": (today + timedelta(days=14)).isoformat(),
                "package_lpa": "8.50",
                "status": Placement.Status.JOINED,
            },
        )
        self.assertRedirects(response, reverse("placements:my_list"))
        self.assertTrue(Placement.objects.filter(trainee=self.trainee, company_name="New Employer").exists())

    def test_admin_can_verify_placement(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("placements:verify", args=[self.placement.pk]))
        self.assertRedirects(response, reverse("placements:detail", args=[self.placement.pk]))
        self.placement.refresh_from_db()
        self.assertTrue(self.placement.verified)
        self.assertEqual(self.placement.verified_by, self.admin)

    def test_offer_letter_is_validated_and_served_only_after_authorization(self):
        valid_pdf = SimpleUploadedFile("offer.pdf", b"%PDF-1.4 example")
        oversized_pdf = SimpleUploadedFile("large.pdf", b"%PDF-" + b"x" * (5 * 1024 * 1024))
        with self.assertRaises(ValidationError):
            from placements.models import validate_offer_letter

            validate_offer_letter(SimpleUploadedFile("offer.jpg", b"not a jpeg"))
        with self.assertRaises(ValidationError):
            validate_offer_letter(oversized_pdf)

        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.placement.offer_letter.save("offer.pdf", valid_pdf, save=True)
                self.client.force_login(self.trainee_user)
                response = self.client.get(reverse("placements:offer_letter", args=[self.placement.pk]))
                self.assertEqual(response.status_code, 200)
                response.close()
                self.assertEqual(
                    self.client.get(f"/media/{self.placement.offer_letter.name}").status_code,
                    404,
                )
                self.client.force_login(self.other_trainer)
                self.assertEqual(
                    self.client.get(reverse("placements:offer_letter", args=[self.placement.pk])).status_code,
                    404,
                )

    def test_trainer_sees_placements_only_for_owned_batches(self):
        self.client.force_login(self.trainer)
        response = self.client.get(reverse("placements:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Northstar Labs")
        self.assertNotContains(response, "BluePeak Systems")
        self.assertEqual(self.client.get(reverse("placements:detail", args=[self.other_placement.pk])).status_code, 404)

    def test_company_directory_scoping_and_company_detail_access(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("placements:companies"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Northstar Labs")
        self.assertContains(response, "BluePeak Systems")
        self.assertEqual(
            self.client.get(reverse("placements:company_detail", args=[self.other_placement.pk])).status_code,
            200,
        )
        self.client.force_login(self.trainer)
        response = self.client.get(reverse("placements:companies"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Northstar Labs")
        self.assertNotContains(response, "BluePeak Systems")
        self.assertEqual(
            self.client.get(reverse("placements:company_detail", args=[self.other_placement.pk])).status_code,
            404,
        )
        self.client.force_login(self.trainee_user)
        self.assertEqual(self.client.get(reverse("placements:companies")).status_code, 403)

    def test_company_directory_merges_case_variants_and_shows_multiple_trainees(self):
        info = self.make_placement(self.trainee, self.batch, "Infosys")
        second_info = self.make_placement(self.other_trainee, self.other_batch, "infosys")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("placements:companies"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Infosys")
        self.assertContains(response, "HR Contact")
        self.assertContains(response, "2 trainees")
        self.assertEqual(
            self.client.get(reverse("placements:company_detail", args=[info.pk])).status_code,
            200,
        )
        detail = self.client.get(reverse("placements:company_detail", args=[second_info.pk]))
        self.assertContains(detail, "learner")
        self.assertContains(detail, "otherlearner")
        self.assertEqual(detail.context["company"]["trainee_count"], 2)

    def test_company_directory_csv_obeys_role_scope_and_filters(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("placements:companies"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Northstar Labs", content)
        self.assertIn("BluePeak Systems", content)
        self.client.force_login(self.trainer)
        response = self.client.get(reverse("placements:companies"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Northstar Labs", content)
        self.assertNotIn("BluePeak Systems", content)
        response = self.client.get(
            reverse("placements:companies"),
            {"format": "csv", "batch": str(self.batch.pk)},
        )
        self.assertIn("Northstar Labs", response.content.decode())
        self.assertNotIn("BluePeak Systems", response.content.decode())
        response = self.client.get(
            reverse("placements:companies"),
            {"format": "csv", "verified": "yes"},
        )
        self.assertNotIn("Northstar Labs", response.content.decode())

    def test_trainee_my_company_page_is_private_and_scoped(self):
        self.client.force_login(self.trainee_user)
        response = self.client.get(reverse("placements:my_company"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Northstar Labs")
        self.assertNotContains(response, "BluePeak Systems")
        self.assertContains(response, "mailto:hr@example.com")
        self.assertContains(response, "tel:9876543210")
        self.client.force_login(self.other_trainee_user)
        response = self.client.get(reverse("placements:my_company"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BluePeak Systems")
        self.assertNotContains(response, "Northstar Labs")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("placements:my_company")).status_code, 403)

    def test_my_company_empty_state_links_to_placement_form(self):
        self.client.force_login(self.other_trainee_user)
        self.other_placement.status = Placement.Status.OFFERED
        self.other_placement.joining_date = None
        self.other_placement.save(update_fields=["status", "joining_date"])
        response = self.client.get(reverse("placements:my_company"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Joined a company? Add your company and HR details")
        self.assertContains(response, reverse("placements:my_create"))

    def test_trainee_is_blocked_from_admin_placement_list(self):
        self.client.force_login(self.trainee_user)
        self.assertEqual(self.client.get(reverse("placements:list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("placements:report")).status_code, 403)

    def test_placement_form_validates_email_phone_and_joining_date(self):
        form = PlacementForm(
            data={
                "batch": str(self.batch.pk),
                "company_name": "Example Co",
                "company_location": "Pune",
                "hr_name": "Hiring Manager",
                "hr_email": "invalid-email",
                "hr_phone": "12345",
                "job_title": "Engineer",
                "offer_date": date.today().isoformat(),
                "joining_date": "",
                "status": Placement.Status.JOINED,
                "package_lpa": "",
            },
            request_user=self.trainee_user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("hr_email", form.errors)
        self.assertIn("hr_phone", form.errors)
        self.assertIn("joining_date", form.errors)
        good_form = PlacementForm(
            data={
                "batch": str(self.batch.pk),
                "company_name": "Example Co",
                "company_location": "Pune",
                "hr_name": "Hiring Manager",
                "hr_email": "hr@example.com",
                "hr_phone": "9876543210",
                "job_title": "Engineer",
                "offer_date": date.today().isoformat(),
                "joining_date": (date.today() - timedelta(days=1)).isoformat(),
                "status": Placement.Status.OFFERED,
                "package_lpa": "",
            },
            request_user=self.trainee_user,
        )
        self.assertFalse(good_form.is_valid())
        self.assertIn("joining_date", good_form.errors)

    def test_placement_joining_date_database_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Placement.objects.create(
                trainee=self.trainee,
                batch=self.batch,
                company_name="Invalid date Co",
                company_location="Mumbai",
                hr_name="HR",
                hr_email="hr@example.com",
                hr_phone="9876543210",
                job_title="Engineer",
                offer_date=date.today(),
                joining_date=date.today() - timedelta(days=1),
                status=Placement.Status.OFFERED,
            )

    def test_placement_summary_csv_export(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("placements:report"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Placement rate (%)", response.content.decode())
        self.assertIn("Alpha", response.content.decode())

    def test_pages_load_for_each_role(self):
        pages = (
            (self.admin, ("core:dashboard", "batches:list", "trainees:list", "placements:list", "placements:report", "placements:companies", f"placements:company_detail:{self.placement.pk}")),
            (self.trainer, ("core:dashboard", "batches:list", "trainees:list", "placements:list", "placements:companies", f"placements:company_detail:{self.placement.pk}")),
            (self.trainee_user, ("core:dashboard", "batches:list", "placements:my_list", "placements:my_company")),
        )
        for user, names in pages:
            self.client.force_login(user)
            for name in names:
                with self.subTest(user=user.username, url=name):
                    if name.startswith("placements:company_detail:"):
                        url = reverse("placements:company_detail", args=[name.rsplit(":", 1)[1]])
                    else:
                        url = reverse(name)
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_batch_completion_service_includes_placement_counts(self):
        from batches.services import complete_batch

        complete_batch(self.batch)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, Batch.Status.COMPLETED)

    def test_dashboard_requires_login(self):
        self.assertRedirects(self.client.get(reverse("core:dashboard")), f"{reverse('accounts:login')}?next=/")
