from datetime import date, timedelta
from io import BytesIO
import re
import secrets

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from tempfile import TemporaryDirectory
from PIL import Image

from batches.models import Batch
from placements.forms import PlacementForm
from placements.models import Placement
from trainees.models import Enrollment, Trainee

User = get_user_model()


class TweakTechTests(TestCase):
    def setUp(self):
        today = date.today()
        self.admin = User.objects.create_user("admin", password="ValidDemoPass94!", role=User.Role.ADMIN, is_staff=True)
        self.trainer = User.objects.create_user("trainer", email="trainer@example.com", password="ValidDemoPass94!", role=User.Role.ADMIN)
        self.other_trainer = User.objects.create_user("other", password="ValidDemoPass94!", role=User.Role.ADMIN)
        self.trainee_user = User.objects.create_user("learner", password="ValidDemoPass94!", role=User.Role.TRAINEE)
        self.other_trainee_user = User.objects.create_user("otherlearner", password="ValidDemoPass94!", role=User.Role.TRAINEE)
        self.trainee = self.trainee_user.trainee_profile
        self.other_trainee = self.other_trainee_user.trainee_profile
        self.batch = Batch.objects.create(batch_number=1, name="Alpha", course="Django", trainer=self.trainer, start_date=today - timedelta(days=3), end_date=today + timedelta(days=3), status=Batch.Status.RUNNING)
        self.other_batch = Batch.objects.create(batch_number=2, name="Beta", course="Python", trainer=self.other_trainer, start_date=today - timedelta(days=3), end_date=today + timedelta(days=3))
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

    def test_batch_date_constraint_and_owner_validation(self):
        invalid = Batch(batch_number=3, name="Invalid", course="Test", trainer=self.trainer, start_date=date.today(), end_date=date.today() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        with self.assertRaises(ValidationError):
            Batch(batch_number=4, name="Wrong owner", course="Test", trainer=self.trainee_user, start_date=date.today(), end_date=date.today()).full_clean()

    def test_enrollment_unique_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrollment.objects.create(trainee=self.trainee, batch=self.batch)

    def test_admin_sees_and_manages_batches(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("batches:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha")
        self.assertContains(response, "Beta")
        self.assertContains(response, "Batch number")
        self.assertContains(response, "1")
        detail = self.client.get(reverse("batches:detail", args=[self.other_batch.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Batch number")
        self.assertContains(detail, "2")
        self.assertEqual(self.client.get(reverse("batches:update", args=[self.other_batch.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("batches:delete", args=[self.other_batch.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("batches:complete", args=[self.other_batch.pk])).status_code, 302)

    def test_admin_batch_form_accepts_required_batch_number(self):
        self.client.force_login(self.admin)
        form_page = self.client.get(reverse("batches:create"))
        self.assertEqual(form_page.status_code, 200)
        self.assertContains(form_page, "Batch number")
        self.assertContains(form_page, "For example 25")
        today = date.today()
        response = self.client.post(
            reverse("batches:create"),
            {
                "batch_number": 25,
                "name": "Twenty Five",
                "course": "Testing",
                "trainer": self.admin.pk,
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=7)).isoformat(),
                "status": Batch.Status.UPCOMING,
            },
        )
        self.assertRedirects(response, reverse("batches:list"))
        self.assertTrue(Batch.objects.filter(batch_number=25, name="Twenty Five").exists())

    def test_trainee_batch_scope_and_foreign_profile_access(self):
        self.client.force_login(self.trainee_user)
        self.assertEqual(self.client.get(reverse("batches:list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("batches:detail", args=[self.batch.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("trainees:detail", args=[self.other_trainee.pk])).status_code, 404)

    def test_admin_sees_all_trainee_batch_details(self):
        Enrollment.objects.create(trainee=self.trainee, batch=self.other_batch)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("trainees:detail", args=[self.trainee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha")
        self.assertContains(response, "Beta")

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
                self.client.force_login(self.other_trainee_user)
                unauthorized_response = self.client.get(reverse("placements:offer_letter", args=[self.placement.pk]))
                self.assertEqual(unauthorized_response.status_code, 404)
                unauthorized_response.close()

    def test_admin_sees_all_placements(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("placements:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Northstar Labs")
        self.assertContains(response, "BluePeak Systems")
        self.assertEqual(self.client.get(reverse("placements:detail", args=[self.other_placement.pk])).status_code, 200)

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
        self.client.force_login(self.other_trainer)
        response = self.client.get(reverse("placements:companies"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Northstar Labs")
        self.assertContains(response, "BluePeak Systems")
        self.assertEqual(
            self.client.get(reverse("placements:company_detail", args=[self.other_placement.pk])).status_code,
            200,
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
        self.client.force_login(self.other_trainer)
        response = self.client.get(reverse("placements:companies"), {"format": "csv"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Northstar Labs", content)
        self.assertIn("BluePeak Systems", content)
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

    def test_trainee_dashboard_and_navigation_keep_my_placement_only(self):
        self.client.force_login(self.trainee_user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Placement status")
        self.assertNotContains(response, "My Company")
        self.assertNotContains(response, "My company")
        self.assertNotContains(response, "placements/my-company")
        self.assertContains(response, "My Placement")
        self.assertEqual(self.client.get("/placements/my-company/").status_code, 404)
        self.assertEqual(self.client.get(reverse("placements:my_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("placements:my_create")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("placements:my_update", args=[self.placement.pk])).status_code,
            200,
        )

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("placements:companies")).status_code, 200)

    def test_trainee_is_blocked_from_admin_placement_list(self):
        self.client.force_login(self.trainee_user)
        self.assertEqual(self.client.get(reverse("placements:list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("placements:report")).status_code, 403)
        self.assertEqual(self.client.get(reverse("placements:companies")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("placements:company_detail", args=[self.placement.pk])).status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("batches:list")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("batches:detail", args=[self.batch.pk])).status_code,
            403,
        )

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
            (self.other_trainer, ("core:dashboard", "batches:list", "trainees:list", "placements:list", "placements:companies", f"placements:company_detail:{self.placement.pk}")),
            (self.trainee_user, ("core:dashboard", "placements:my_list", "placements:my_create", f"placements:my_update:{self.placement.pk}")),
        )
        for user, names in pages:
            self.client.force_login(user)
            for name in names:
                with self.subTest(user=user.username, url=name):
                    if name.startswith("placements:company_detail:"):
                        url = reverse("placements:company_detail", args=[name.rsplit(":", 1)[1]])
                    elif name.startswith("placements:my_update:"):
                        url = reverse("placements:my_update", args=[name.rsplit(":", 1)[1]])
                    else:
                        url = reverse(name)
                    self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.trainee_user)
        for name in ("batches:list", "placements:list", "placements:companies", "placements:report"):
            with self.subTest(user=self.trainee_user.username, url=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_batch_completion_service_includes_placement_counts(self):
        from batches.services import complete_batch

        complete_batch(self.batch)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, Batch.Status.COMPLETED)

    def test_superuser_is_assigned_admin_role(self):
        superuser = User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password="ValidDemoPass94!",
        )
        self.assertEqual(superuser.role, User.Role.ADMIN)
        superuser.role = User.Role.TRAINEE
        superuser.save()
        superuser.refresh_from_db()
        self.assertEqual(superuser.role, User.Role.ADMIN)

    def test_dashboard_uses_role_specific_templates_and_data(self):
        self.client.force_login(self.admin)
        admin_response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(admin_response.status_code, 200)
        self.assertTemplateUsed(admin_response, "core/dashboard_admin.html")
        self.assertIn("active_batches", admin_response.context)

        self.client.force_login(self.trainee_user)
        trainee_response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(trainee_response.status_code, 200)
        self.assertTemplateUsed(trainee_response, "core/dashboard_trainee.html")
        self.assertContains(trainee_response, "Placement status")
        self.assertContains(trainee_response, "Northstar Labs")
        self.assertNotContains(trainee_response, "My Company")
        self.assertNotContains(trainee_response, "My company")
        self.assertNotContains(trainee_response, "BluePeak Systems")

    def test_trainee_dashboard_greets_trainee(self):
        self.client.force_login(self.trainee_user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome back, learner")
        self.assertContains(response, "Profile completion")
        self.assertContains(response, "Complete your profile")

    def test_admin_creates_minimal_trainee_with_temporary_password_and_enrollment(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse("trainees:create"))
        self.assertEqual(page.status_code, 200)
        for field in ("first_name", "last_name", "username", "email", "batch"):
            self.assertContains(page, f'name="{field}"')
        for field in ("password", "phone", "status"):
            self.assertNotContains(page, f'name="{field}"')

        response = self.client.post(
            reverse("trainees:create"),
            {
                "first_name": "New",
                "last_name": "Learner",
                "username": "newlearner",
                "email": "newlearner@example.com",
                "batch": self.batch.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Share this temporary password securely")
        self.assertContains(response, "data-copy-target")
        self.assertEqual(response["Cache-Control"], "no-store")
        created_user = User.objects.get(username="newlearner")
        created_trainee = created_user.trainee_profile
        temporary_password = re.search(
            r'id="temporary-password" type="text" value="([^"]+)"',
            response.content.decode(),
        ).group(1)
        self.assertTrue(created_user.check_password(temporary_password))
        self.assertTrue(created_user.must_change_password)
        self.assertTrue(Enrollment.objects.filter(trainee=created_trainee, batch=self.batch).exists())

        second_response = self.client.post(
            reverse("trainees:create"),
            {
                "first_name": "Batchless",
                "last_name": "Learner",
                "username": "batchless",
                "email": "batchless@example.com",
                "batch": "",
            },
        )
        self.assertEqual(second_response.status_code, 200)
        batchless = User.objects.get(username="batchless").trainee_profile
        self.assertFalse(batchless.enrollments.exists())

        self.client.force_login(created_user)
        blocked = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(blocked, reverse("accounts:password_change"))
        change_page = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(change_page.status_code, 200)
        changed = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": temporary_password,
                "new_password1": "A-unique-new-passphrase-2026!",
                "new_password2": "A-unique-new-passphrase-2026!",
            },
        )
        self.assertRedirects(changed, reverse("accounts:password_change_done"))
        created_user.refresh_from_db()
        self.assertFalse(created_user.must_change_password)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)

    def test_trainee_profile_edit_is_self_scoped_and_records_editor(self):
        self.client.force_login(self.trainee_user)
        trainee_list = self.client.get(reverse("trainees:list"))
        self.assertEqual(trainee_list.status_code, 200)
        self.assertNotContains(trainee_list, "Add trainee")
        self.assertNotContains(trainee_list, "Incomplete")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username (read-only)")
        self.assertContains(response, "Batch (assigned by Admin)")
        self.assertNotContains(response, 'name="username"')
        self.assertNotContains(response, 'name="batch"')

        response = self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "Updated",
                "last_name": "Learner",
                "email": "learner@example.com",
                "phone": "9876543210",
                "date_of_birth": "2000-01-02",
                "address": "1 Main Road",
                "city": "Pune",
                "state": "Maharashtra",
                "highest_qualification": "B.Tech",
                "college_university": "Example University",
                "graduation_year": "2022",
                "emergency_contact_name": "Family Contact",
                "emergency_contact_phone": "9123456789",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.trainee.refresh_from_db()
        self.trainee_user.refresh_from_db()
        self.assertEqual(self.trainee.phone, "9876543210")
        self.assertEqual(self.trainee.updated_by, self.trainee_user)
        self.assertEqual(self.trainee_user.first_name, "Updated")
        self.assertEqual(self.trainee.profile_completion_percentage(), 100)
        self.client.force_login(self.admin)
        complete_list = self.client.get(reverse("trainees:list"))
        self.assertContains(complete_list, "Complete")

        self.client.force_login(self.trainee_user)
        self.assertEqual(
            self.client.get(reverse("trainees:update", args=[self.other_trainee.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("trainees:photo", args=[self.other_trainee.pk])).status_code,
            404,
        )

    def test_profile_phone_validation_and_admin_trainee_edit(self):
        self.client.force_login(self.trainee_user)
        invalid = self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "Learner",
                "last_name": "One",
                "email": "learner@example.com",
                "phone": "123456",
                "emergency_contact_phone": "9876543210",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertIn("phone", invalid.context["form"].errors)
        self.other_trainee_user.email = "taken@example.com"
        self.other_trainee_user.save()
        duplicate_email = self.client.post(
            reverse("accounts:profile"),
            {
                "first_name": "Learner",
                "last_name": "One",
                "email": "taken@example.com",
            },
        )
        self.assertEqual(duplicate_email.status_code, 200)
        self.assertIn("email", duplicate_email.context["form"].errors)
        self.assertEqual(
            self.client.get(reverse("trainees:create")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("trainees:update", args=[self.trainee.pk])).status_code,
            403,
        )

        self.client.force_login(self.admin)
        page = self.client.get(reverse("trainees:update", args=[self.trainee.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Highest qualification")
        updated = self.client.post(
            reverse("trainees:update", args=[self.trainee.pk]),
            {
                "first_name": "Admin",
                "last_name": "Updated",
                "email": "admin-updated-learner@example.com",
                "phone": "9876543210",
                "date_of_birth": "2001-02-03",
                "address": "New address",
                "city": "Mumbai",
                "state": "Maharashtra",
                "highest_qualification": "MCA",
                "college_university": "University",
                "graduation_year": "2023",
                "emergency_contact_name": "Contact",
                "emergency_contact_phone": "9123456789",
                "status": Trainee.Status.INACTIVE,
                "batch": self.other_batch.pk,
            },
        )
        self.assertRedirects(updated, reverse("trainees:list"))
        self.trainee.refresh_from_db()
        self.assertEqual(self.trainee.updated_by, self.admin)
        self.assertEqual(self.trainee.highest_qualification, "MCA")
        self.assertEqual(list(self.trainee.enrollments.values_list("batch_id", flat=True)), [self.other_batch.pk])

    def test_profile_photo_is_validated_and_served_only_to_authorized_users(self):
        image_data = BytesIO()
        Image.new("RGB", (2, 2), color="white").save(image_data, format="PNG")
        image_data.seek(0)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.client.force_login(self.trainee_user)
            response = self.client.post(
                reverse("accounts:profile"),
                {
                    "first_name": "Learner",
                    "last_name": "One",
                    "email": "learner@example.com",
                    "profile_photo": SimpleUploadedFile(
                        "learner.png",
                        image_data.read(),
                        content_type="image/png",
                    ),
                },
            )
            self.assertRedirects(response, reverse("accounts:profile"))
            photo_url = reverse("trainees:photo", args=[self.trainee.pk])
            own_photo = self.client.get(photo_url)
            self.assertEqual(own_photo.status_code, 200)
            self.assertEqual(own_photo["Content-Type"], "image/png")
            own_photo.close()
            profile_page = self.client.get(reverse("accounts:profile"))
            self.assertNotContains(profile_page, "/media/")
            self.assertContains(profile_page, photo_url)

            self.client.force_login(self.other_trainee_user)
            self.assertEqual(self.client.get(photo_url).status_code, 404)

            self.client.force_login(self.admin)
            admin_photo = self.client.get(photo_url)
            self.assertEqual(admin_photo.status_code, 200)
            admin_photo.close()

            self.client.force_login(self.trainee_user)
            invalid_image = self.client.post(
                reverse("accounts:profile"),
                {
                    "first_name": "Learner",
                    "last_name": "One",
                    "email": "learner@example.com",
                    "profile_photo": SimpleUploadedFile(
                        "not-an-image.png",
                        b"not an image",
                        content_type="image/png",
                    ),
                },
            )
            self.assertEqual(invalid_image.status_code, 200)
            self.assertIn("profile_photo", invalid_image.context["form"].errors)

            large_data = BytesIO()
            large_image = Image.frombytes("RGB", (1024, 1024), secrets.token_bytes(3 * 1024 * 1024))
            large_image.save(large_data, format="PNG", compress_level=0)
            self.assertGreater(len(large_data.getvalue()), 2 * 1024 * 1024)
            large_data.seek(0)
            oversized = self.client.post(
                reverse("accounts:profile"),
                {
                    "first_name": "Learner",
                    "last_name": "One",
                    "email": "learner@example.com",
                    "profile_photo": SimpleUploadedFile(
                        "large.png",
                        large_data.read(),
                        content_type="image/png",
                    ),
                },
            )
            self.assertEqual(oversized.status_code, 200)
            self.assertIn("2 MB or smaller", oversized.context["form"].errors["profile_photo"][0])

    def test_admin_trainee_list_shows_profile_completion_badges(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("trainees:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile")
        self.assertContains(response, "Incomplete")
        self.assertEqual(self.trainee.profile_completion_percentage(), 0)

    def test_batch_numbers_must_be_unique_and_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Batch.objects.create(
                batch_number=self.batch.batch_number,
                name="Duplicate number",
                course="Testing",
                trainer=self.admin,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=1),
            )
        invalid = Batch(
            batch_number=0,
            name="Zero number",
            course="Testing",
            trainer=self.admin,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_batch_ordinal_formatting(self):
        from core.utils import ordinal

        expected = {1: "1st", 2: "2nd", 3: "3rd", 11: "11th", 12: "12th", 13: "13th", 21: "21st", 25: "25th"}
        for number, formatted in expected.items():
            with self.subTest(number=number):
                self.assertEqual(ordinal(number), formatted)

    def test_admin_can_enrol_and_remove_trainees_from_either_detail_page(self):
        self.client.force_login(self.admin)
        trainee_enrol_url = reverse("trainees:enrol", args=[self.other_trainee.pk])
        response = self.client.post(trainee_enrol_url, {"batch": self.batch.pk}, follow=True)
        self.assertRedirects(response, reverse("trainees:detail", args=[self.other_trainee.pk]))
        self.assertContains(response, f"{self.other_trainee} enrolled in {self.batch.name}.")
        self.assertTrue(Enrollment.objects.filter(trainee=self.other_trainee, batch=self.batch).exists())

        response = self.client.post(
            reverse("trainees:enrollment_remove", args=[self.other_trainee.pk, self.batch.pk])
        )
        self.assertRedirects(response, reverse("trainees:detail", args=[self.other_trainee.pk]))
        self.assertFalse(Enrollment.objects.filter(trainee=self.other_trainee, batch=self.batch).exists())

        response = self.client.post(
            reverse("batches:enrol", args=[self.batch.pk]),
            {"trainees": [self.other_trainee.pk]},
            follow=True,
        )
        self.assertRedirects(response, reverse("batches:detail", args=[self.batch.pk]))
        self.assertContains(response, f"{self.other_trainee} enrolled in {self.batch.name}.")
        self.assertTrue(Enrollment.objects.filter(trainee=self.other_trainee, batch=self.batch).exists())
        response = self.client.post(
            reverse("batches:enrollment_remove", args=[self.batch.pk, self.other_trainee.pk])
        )
        self.assertRedirects(response, reverse("batches:detail", args=[self.batch.pk]))
        self.assertFalse(Enrollment.objects.filter(trainee=self.other_trainee, batch=self.batch).exists())

    def test_trainee_cannot_access_enrollment_actions(self):
        self.client.force_login(self.trainee_user)
        requests = (
            ("trainees:enrol", [self.other_trainee.pk], {"batch": self.other_batch.pk}),
            ("trainees:enrollment_remove", [self.trainee.pk, self.batch.pk], {}),
            ("batches:enrol", [self.batch.pk], {"trainees": [self.other_trainee.pk]}),
            ("batches:enrollment_remove", [self.batch.pk, self.trainee.pk], {}),
        )
        for name, args, data in requests:
            with self.subTest(action=name):
                response = self.client.post(reverse(name, args=args), data)
                self.assertIn(response.status_code, (403, 404))

    def test_trainee_dashboard_shows_batch_ordinal_after_admin_enrolment(self):
        self.trainee.enrollments.all().delete()
        self.client.force_login(self.trainee_user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Waiting for admin to add you to a batch")
        self.assertContains(response, "—")
        self.assertNotContains(response, "My batches")
        self.assertNotIn("my_batches", response.context)

        batch_25 = Batch.objects.create(
            batch_number=25,
            name="Batch Twenty Five",
            course="Testing",
            trainer=self.admin,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=10),
            status=Batch.Status.UPCOMING,
        )
        self.client.force_login(self.admin)
        self.client.post(reverse("trainees:enrol", args=[self.trainee.pk]), {"batch": batch_25.pk})
        self.client.force_login(self.trainee_user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "25th")
        self.assertNotContains(response, "Waiting for admin to add you to a batch")

    def test_trainee_dashboard_prioritizes_running_then_upcoming_batches(self):
        running_batch = Batch.objects.create(
            batch_number=21,
            name="Another Running",
            course="Testing",
            trainer=self.admin,
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() + timedelta(days=10),
            status=Batch.Status.RUNNING,
        )
        upcoming_batch = Batch.objects.create(
            batch_number=25,
            name="Latest Upcoming",
            course="Testing",
            trainer=self.admin,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=20),
            status=Batch.Status.UPCOMING,
        )
        Enrollment.objects.create(trainee=self.trainee, batch=running_batch)
        Enrollment.objects.create(trainee=self.trainee, batch=upcoming_batch)
        self.client.force_login(self.trainee_user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "1st")
        self.assertNotContains(response, "25th")

        Enrollment.objects.filter(trainee=self.trainee, batch=self.batch).delete()
        Enrollment.objects.filter(trainee=self.trainee, batch=running_batch).delete()
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "25th")

    def test_admin_dashboard_remains_role_specific_and_unchanged(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:dashboard"))
        self.assertTemplateUsed(response, "core/dashboard_admin.html")
        self.assertIn("active_batches", response.context)
        self.assertNotIn("batch_ordinal", response.context)

    def test_registration_submits_without_role_and_requires_approval(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="role"')

        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newapplicant",
                "first_name": "New",
                "last_name": "Applicant",
                "email": "applicant@example.com",
                "role": User.Role.ADMIN,
                "password1": "StrongPass!12345",
                "password2": "StrongPass!12345",
            },
        )
        self.assertRedirects(response, reverse("accounts:registration_submitted"))
        applicant = User.objects.get(username="newapplicant")
        self.assertFalse(applicant.is_approved)
        self.assertFalse(applicant.is_active)
        self.assertEqual(applicant.role, User.Role.TRAINEE)
        self.assertNotIn("_auth_user_id", self.client.session)

        login_response = self.client.post(
            reverse("accounts:login"),
            {"username": "newapplicant", "password": "StrongPass!12345"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_dashboard_notifies_and_approves_registration_with_selected_role(self):
        applicant = User.objects.create_user(
            username="pending",
            email="pending@example.com",
            password="StrongPass!12345",
            first_name="Pending",
            last_name="Applicant",
            is_approved=False,
        )
        self.assertFalse(applicant.is_active)
        self.client.force_login(self.admin)
        dashboard = self.client.get(reverse("core:dashboard"))
        self.assertContains(dashboard, "Registration requests")
        self.assertContains(dashboard, "Pending Applicant")
        self.assertEqual(dashboard.context["pending_registration_count"], 1)

        self.assertEqual(self.client.get(reverse("accounts:registration_queue")).status_code, 200)
        review_url = reverse("accounts:registration_review", args=[applicant.pk])
        self.assertEqual(self.client.get(review_url).status_code, 200)
        response = self.client.post(review_url, {"role": User.Role.ADMIN})
        self.assertRedirects(response, reverse("accounts:registration_queue"))
        applicant.refresh_from_db()
        self.assertTrue(applicant.is_approved)
        self.assertTrue(applicant.is_active)
        self.assertEqual(applicant.role, User.Role.ADMIN)

    def test_trainee_cannot_view_or_approve_registration_requests(self):
        applicant = User.objects.create_user(
            username="pending",
            email="pending@example.com",
            password="StrongPass!12345",
            is_approved=False,
        )
        self.client.force_login(self.trainee_user)
        self.assertEqual(self.client.get(reverse("accounts:registration_queue")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("accounts:registration_review", args=[applicant.pk])).status_code,
            403,
        )

    def test_dashboard_requires_login(self):
        self.assertRedirects(self.client.get(reverse("core:dashboard")), f"{reverse('accounts:login')}?next=/")

    def test_offline_page_is_public_and_self_contained(self):
        response = self.client.get(reverse("core:offline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check your connection")
        self.assertContains(response, "You're offline. We'll reconnect automatically.")
        self.assertContains(response, "aria-hidden=\"true\"")
        self.assertContains(response, "window.addEventListener(\"online\"")
        self.assertNotContains(response, "static/css/style.css")
        self.assertNotContains(response, "static/js/app.js")
        self.assertNotContains(response, "https://")

    def test_service_worker_is_root_scoped_and_only_caches_offline_shell_assets(self):
        response = self.client.get(reverse("core:service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        script = response.content.decode()
        self.assertIn('"/offline/"', script)
        self.assertIn('"/static/css/style.css"', script)
        self.assertIn('"/static/js/app.js"', script)
        self.assertIn('event.request.mode !== "navigate"', script)
        self.assertIn('fetch(event.request).catch', script)
        self.assertNotIn("cache.put(", script)
        self.assertNotIn("placements", script)
        self.assertNotIn("trainees", script)
