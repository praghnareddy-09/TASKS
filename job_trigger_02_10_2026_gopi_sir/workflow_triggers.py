"""
Scheduled trigger  -> starts the jobs at a set time (cron / one-time / interval)
Event trigger      -> when ANY job finishes, a listener sends a mail:
                      success  -> SUCCESS mail
                      failure  -> FAILED mail + reason + traceback

Install:  pip install apscheduler
Run:      python workflow_triggers.py
"""
import os
import smtplib
import time
from datetime import datetime, timedelta
from email.message import EmailMessage

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_SUBMITTED
from apscheduler.schedulers.blocking import BlockingScheduler

# ------------------------------------------------------------------ settings
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "praghnareddy.d@gmail.com"
SMTP_PASS = os.environ.get("SMTP_PASS", "")    # App Password, set as env variable
MAIL_TO = "praghnareddy.d@gmail.com"


# ---------------------------------------------------------------------- mail
def send_mail(subject, body):
    if not SMTP_PASS:                             # no password set -> just print (test mode)
        print(f"\n--- MAIL (test mode) ---\nTo: {MAIL_TO}\nSubject: {subject}\n{body}\n------------------------")
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, SMTP_USER, MAIL_TO
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


# ---------------------------------------------------------------------- jobs
# These are the programs that may take hours. Here they just sleep, to simulate that.
def data_load():
    time.sleep(5)                                 # pretend: 5 seconds (really: hours)
    return "1500 rows loaded"


def report_job():
    time.sleep(3)
    raise ConnectionError("Database db.internal:5432 refused connection")   # this one fails


def backup_job():
    time.sleep(8)
    return "backup completed, 2.3 GB"


# ----------------------------------------------------- event trigger (mail)
start_times = {}


def on_job_started(event):
    start_times[event.job_id] = datetime.now()


def on_job_finished(event):
    """Runs automatically the moment ANY job ends - success or failure."""
    started = start_times.get(event.job_id, datetime.now())
    ended = datetime.now()
    info = (f"Job      : {event.job_id}\n"
            f"Started  : {started:%Y-%m-%d %H:%M:%S}\n"
            f"Ended    : {ended:%Y-%m-%d %H:%M:%S}\n"
            f"Duration : {ended - started}\n")

    if event.exception:                           # the job crashed
        body = (info + f"Status   : FAILED\n"
                       f"Reason   : {type(event.exception).__name__}: {event.exception}\n\n"
                       f"Traceback:\n{event.traceback}")
        send_mail(f"[FAILED] {event.job_id}", body)
    else:                                         # the job finished normally
        body = info + f"Status   : SUCCESS\nResult   : {event.retval}\n"
        send_mail(f"[SUCCESS] {event.job_id}", body)


# ---------------------------------------------------------------- scheduler
if __name__ == "__main__":
    scheduler = BlockingScheduler()               # runs each job in its own thread

    # Connect the event trigger
    scheduler.add_listener(on_job_started, EVENT_JOB_SUBMITTED)
    scheduler.add_listener(on_job_finished, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # Scheduled triggers
    soon = datetime.now() + timedelta(seconds=2)
    scheduler.add_job(data_load,   "date", run_date=soon, id="data_load")      # one-time
    scheduler.add_job(report_job,  "date", run_date=soon, id="report_job")
    scheduler.add_job(backup_job,  "date", run_date=soon, id="backup_job")

    # Real-life versions of the same thing:
    # scheduler.add_job(data_load,  "cron", hour=2, minute=0, id="data_load")           # every day 2:00 AM
    # scheduler.add_job(backup_job, "cron", day_of_week="sun", hour=1, id="backup_job") # every Sunday 1 AM
    # scheduler.add_job(report_job, "interval", minutes=30, id="report_job")            # every 30 minutes

    print("Scheduler started. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Stopped.")
