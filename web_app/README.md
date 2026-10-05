# TweakTech

TweakTech is a Django workspace for managing training batches, trainees and job placements. Trainees can submit hiring-company and HR contact details, trainers can review placements for trainees in batches they own, and admins can verify placements and export summary reports. It uses Django templates and Bootstrap, SQLite by default, and supports PostgreSQL through environment configuration.

## Setup

1. Install Python 3.12 and create a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Create a local environment file and set a strong secret:

   ```powershell
   Copy-Item .env.example .env
   ```

   Set `SECRET_KEY` to a unique random value before deployment. `DEBUG` defaults to false when unset. `DB=sqlite` uses the local `db.sqlite3`; set `DB=postgres` and configure `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` and `DB_PORT` to use PostgreSQL.

4. Create and apply migrations, then load the demo dataset:

   ```powershell
   python manage.py makemigrations accounts batches trainees placements
   python manage.py migrate
   python manage.py seed_demo
   ```

5. Start the development server:

   ```powershell
   python manage.py runserver
   ```

Open <http://127.0.0.1:8000/> and sign in using a demo account listed below.

## Demo accounts

All demo accounts receive a password through `seed_demo`:

| Role | Username(s) | Password |
| --- | --- | --- |
| Admin | `admin` | `AdminDemo123!` |
| Trainer | `trainer1`, `trainer2`, `trainer3` | `TrainerDemo123!` |
| Trainee | `trainee01` through `trainee20` | `TraineeDemo123!` |

Change demo passwords before using demo records in a shared environment. The seed command is repeatable and resets the demo-account passwords each time it runs.

## Scheduler and email

APScheduler runs a daily job at 00:05 in the configured timezone. It moves batches into `RUNNING` or `COMPLETED` according to their dates. On completion it emails the trainer the batch name, trainee count and number of joined placements. When a trainee submits or updates a placement, the batch trainer and active admins are notified. SMTP settings (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, and `DEFAULT_FROM_EMAIL`) configure delivery; without `SMTP_HOST`, Django uses the console email backend.

## Placement privacy and permissions

- Trainees can create, edit and view only placements attached to their own trainee profile and a batch in which they are enrolled.
- Trainers can view every batch, but can edit, delete and complete only batches they own. They can see trainee details and placement/HR contact details only for their owned batches.
- Admins can manage every batch and placement, verify placement records, and export the placement summary CSV.
- The Company HR directory (`/placements/companies/`) and its company detail pages are available to admins and trainers. Trainers see only joined placements from their own batches; trainees cannot access the directory.
- Trainees can view their own joined company details at `/placements/my-company/`; no other trainee's HR details are exposed.
- The Company HR directory CSV export uses the same batch and verification filters and role scoping as the directory page.
- Uploaded offer letters are limited to PDF, JPG and PNG files up to 5 MB and are served only through a permission-checked application view. `MEDIA_ROOT` defaults to the project `media` directory for local development.

The development autoreloader starts the job scheduler only in its child process. In production, set `RUN_SCHEDULER=True` on exactly one application process (or run one scheduler-enabled worker) to avoid duplicate daily jobs across multiple web workers. Scheduler executions, failures and missed runs are logged.

## Tests and checks

```powershell
python manage.py check
python manage.py test
```

Tests cover model integrity, role-scoped batch and placement access, placement validation, CSV reporting, batch completion, and page responses.

## Project structure

```text
accounts/       Custom role-based user, authentication, profile and permissions
batches/        Batch model, visible/manageable querysets, lifecycle service and CRUD
core/           Dashboard, error pages, scheduler and seed_demo command
placements/     Placement and HR contact details, scoped views, company directory, validation, reports and admin
trainees/       Trainee profiles, enrollments, signals and CRUD
tweaktech/      Project settings, root routes and WSGI entry point
templates/      Shared layout and server-rendered pages
static/css/     The single custom stylesheet
static/js/      The single custom script
```
