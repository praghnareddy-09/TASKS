"""
Task 1: Scheduled trigger -> starts jobs ; Event trigger -> mail on SUCCESS / FAILED
Task 2: Run history     -> every run is logged to run_history.csv + workflow.log
                           and a SUMMARY (runs, success/fail, timing) can be printed.

Install:  pip install apscheduler
Run jobs: python workflow_triggers.py
Summary : python workflow_triggers.py summary
Task 3: End-of-day mail -> every day at 11:55 PM: today's runs, success/failed,
                           jobs NOT run, and today's log.
Test it : python workflow_triggers.py daily      (sends the daily mail right now)
"""
import csv
import logging
import os
import smtplib
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import escape

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_SUBMITTED
from apscheduler.schedulers.blocking import BlockingScheduler

# ------------------------------------------------------------------ settings
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "praghnareddy.d@gmail.com"
SMTP_PASS = "tcebpgrvbcujbdup"    # App Password, set as env variable
MAIL_TO = "praghnareddy.d@gmail.com"

# Jobs that SHOULD run every day. If one has no run today, the daily mail says "NOT RUN".
EXPECTED_JOBS = ["data_load", "report_job", "backup_job"]
DAILY_REPORT_TIME = (16, 31)                   # hour, minute -> end-of-day mail at 11:55 PM

HISTORY_FILE = "run_history.csv"
LOG_FILE = "workflow.log"
FIELDS = ["job_id", "started", "ended", "duration_sec", "status", "details", "traceback"]
TIME_FMT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("workflow")
file_lock = threading.Lock()                    # jobs finish in different threads


# ---------------------------------------------------------------------- mail
def send_mail(subject, body, html=None):
    if not SMTP_PASS:                             # no password set -> just print (test mode)
        print(f"\n--- MAIL (test mode) ---\nTo: {MAIL_TO}\nSubject: {subject}\n{body}\n------------------------")
        if html:                                  # save the HTML so you can open it in a browser
            with open("mail_preview.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("HTML version saved -> mail_preview.html (open it in your browser)")
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, SMTP_USER, MAIL_TO
    msg.set_content(body)                         # plain-text fallback
    if html:
        msg.add_alternative(html, subtype="html") # pretty version
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


# ---------------------------------------------------------------------- jobs
def data_load():
    time.sleep(5)
    return "1500 rows loaded"


def report_job():
    time.sleep(3)
    raise ConnectionError("Database db.internal:5432 refused connection")


def backup_job():
    time.sleep(8)
    return "backup completed, 2.3 GB"


# ------------------------------------------------------------ run history
def ensure_history_schema():
    """Old run_history.csv files have no 'traceback' column - upgrade them in place."""
    if not os.path.exists(HISTORY_FILE):
        return
    with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == FIELDS:
            return
        rows = list(reader)
    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def save_run(job_id, started, ended, status, details, traceback_text=""):
    """Append one row to the CSV history file."""
    with file_lock:
        ensure_history_schema()
        new_file = not os.path.exists(HISTORY_FILE)
        with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                w.writeheader()
            w.writerow({
                "job_id": job_id,
                "started": started.strftime(TIME_FMT),
                "ended": ended.strftime(TIME_FMT),
                "duration_sec": round((ended - started).total_seconds(), 2),
                "status": status,
                "details": details.replace("\n", " ")[:300],
                "traceback": (traceback_text or "").strip()[:6000],
            })


def fmt_secs(s):
    s = int(round(s))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def build_summary():
    """Read the history file and return a text summary."""
    if not os.path.exists(HISTORY_FILE):
        return "No runs recorded yet."

    with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return "No runs recorded yet."

    per_job = defaultdict(list)
    for r in rows:
        per_job[r["job_id"]].append(r)

    total = len(rows)
    ok = sum(r["status"] == "SUCCESS" for r in rows)
    lines = [
        "=" * 78,
        "WORKFLOW RUN SUMMARY",
        f"Generated : {datetime.now():{TIME_FMT}}",
        f"Total runs: {total}   Success: {ok}   Failed: {total - ok}",
        "=" * 78,
        f"{'Job':<14}{'Runs':>5}{'OK':>5}{'Fail':>6}{'Min':>10}{'Avg':>10}{'Max':>10}  Last run",
        "-" * 78,
    ]
    for job, runs in sorted(per_job.items()):
        durs = [float(r["duration_sec"]) for r in runs]
        n_ok = sum(r["status"] == "SUCCESS" for r in runs)
        last = runs[-1]
        lines.append(
            f"{job:<14}{len(runs):>5}{n_ok:>5}{len(runs) - n_ok:>6}"
            f"{fmt_secs(min(durs)):>10}{fmt_secs(sum(durs) / len(durs)):>10}{fmt_secs(max(durs)):>10}"
            f"  {last['started']} [{last['status']}]"
        )

    lines += ["", "RUN LOG (latest 20)", "-" * 78]
    for r in rows[-20:]:
        lines.append(f"{r['started']} -> {r['ended']}  {r['job_id']:<12} "
                     f"{fmt_secs(float(r['duration_sec']))}  {r['status']:<8} {r['details'][:60]}")

    failures = [r for r in rows if r["status"] == "FAILED"][-5:]
    if failures:
        lines += ["", "RECENT FAILURES (latest 5, with traceback)", "-" * 78]
        for r in failures:
            lines.append(f"{r['started']}  {r['job_id']}  {r['details']}")
            if r.get("traceback"):
                lines += [f"    {t}" for t in r["traceback"].splitlines()]
            lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------- end-of-day report
start_times = {}                                # also tells us which jobs are still running
REPORT_JOB_ID = "daily_report"                  # the report itself is not logged as a job


def build_daily_report():
    """Return (subject, body) describing today's runs, failures and missing jobs."""
    today = datetime.now().strftime("%Y-%m-%d")
    rows = today_rows()

    ran = {r["job_id"] for r in rows}
    running = set(start_times)                   # started but not finished yet
    not_run = [j for j in EXPECTED_JOBS if j not in ran and j not in running]
    ok = [r for r in rows if r["status"] == "SUCCESS"]
    bad = [r for r in rows if r["status"] == "FAILED"]

    lines = [
        f"DAILY JOB REPORT - {today}",
        "=" * 70,
        f"Total runs : {len(rows)}",
        f"Success    : {len(ok)}",
        f"Failed     : {len(bad)}",
        f"Not run    : {len(not_run)}",
        f"Still running: {len(running)}",
        "",
    ]

    if not_run:
        lines += ["JOBS NOT RUN TODAY", "-" * 70] + [f"  !! {j}" for j in not_run] + [""]
    if running:
        lines += ["STILL RUNNING AT REPORT TIME", "-" * 70] + [f"  .. {j}" for j in sorted(running)] + [""]
    if bad:
        lines += ["FAILED JOBS", "-" * 70]
        for r in bad:
            lines.append(f"  {r['job_id']:<12} {r['started']}  {r['details'][:80]}")
            if r.get("traceback"):
                lines += ["", "  Traceback:"] + [f"    {t}" for t in r["traceback"].splitlines()]
            lines.append("")

    lines += ["TODAY'S LOG", "-" * 70]
    if rows:
        for r in rows:
            lines.append(f"{r['started'][11:]} -> {r['ended'][11:]}  {r['job_id']:<12} "
                         f"{fmt_secs(float(r['duration_sec']))}  {r['status']:<8} {r['details'][:50]}")
    else:
        lines.append("  No jobs ran today.")

    if not_run or bad:
        status = "ATTENTION"
    else:
        status = "ALL OK"
    subject = (f"[DAILY REPORT {status}] {today} - {len(ok)} success, "
               f"{len(bad)} failed, {len(not_run)} not run")
    return subject, "\n".join(lines)


def today_rows():
    """All history rows whose job started today."""
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["started"].startswith(today)]


# status -> (label, badge background, badge text colour)
STATUS_STYLE = {
    "SUCCESS": ("Success", "#e6f4ea", "#137333"),
    "FAILED":  ("Failed",  "#fce8e6", "#c5221f"),
    "NOT RUN": ("Not run", "#fef7e0", "#7f5d34"),
    "RUNNING": ("Running", "#e8f0fe", "#1a56db"),
}
TH = "text-align:left;padding:6px 8px;font-size:12px;color:#1a2b49;border-bottom:1px solid #d0d7e2;"
TD = "padding:6px 8px;font-size:12px;color:#333;border-bottom:1px solid #eef1f5;vertical-align:top;"


def build_daily_report_html():
    """HTML version of the daily report: header, summary, one card per job."""
    now = datetime.now()
    rows = today_rows()
    by_job = defaultdict(list)
    for r in rows:
        by_job[r["job_id"]].append(r)
    running = set(start_times)
    job_ids = list(EXPECTED_JOBS) + sorted(j for j in by_job if j not in EXPECTED_JOBS)

    def state(job):
        if job in running:
            return "RUNNING"
        runs = by_job.get(job)
        return runs[-1]["status"] if runs else "NOT RUN"

    counts = Counter(state(j) for j in job_ids)
    all_ok = counts["FAILED"] == 0 and counts["NOT RUN"] == 0
    headline = "Completed" if all_ok else "Needs attention"
    headline_color = "#137333" if all_ok else "#c5221f"

    z = now.astimezone().strftime("%z")           # e.g. +0530 -> +05:30
    tz = f"{z[:3]}:{z[3:]}"
    first = min((r["started"] for r in rows), default="-")
    last = max((r["ended"] for r in rows), default="-")

    cards = []
    for job in job_ids:
        st = state(job)
        runs = by_job.get(job, [])
        label, bg, fg = STATUS_STYLE[st]
        if st == "SUCCESS":
            note = f"Ran {len(runs)} time(s) today. Last result: {runs[-1]['details']}"
        elif st == "FAILED":
            note = f"Last error: {runs[-1]['details']}"
        elif st == "RUNNING":
            note = "Started but not finished at report time."
        else:
            note = "No run recorded today for this expected job."

        table = ""
        if runs:
            head = "".join(f'<th style="{TH}">{h}</th>'
                           for h in ("Started", "Ended", "Duration", "Status", "Details"))
            body = "".join(
                "<tr>" + "".join(f'<td style="{TD}">{escape(str(c))}</td>' for c in (
                    r["started"][11:], r["ended"][11:], fmt_secs(float(r["duration_sec"])),
                    r["status"].title(), r["details"][:120])) + "</tr>"
                for r in runs)
            table = (f'<table style="border-collapse:collapse;width:100%;margin-top:10px;">'
                     f'<tr>{head}</tr>{body}</table>'
                     f'<div style="font-size:11px;color:#6b7686;margin-top:6px;">'
                     f'Showing {len(runs)} run(s) today.</div>')

        tb_html = ""
        for r in runs:
            tb = r.get("traceback") or ""
            if r["status"] == "FAILED" and tb.strip():
                tb_html += (
                    f'<div style="font-size:12px;color:#c5221f;margin-top:12px;"><b>Traceback</b> '
                    f'<span style="color:#6b7686;">(run at {r["started"][11:]})</span></div>'
                    f'<pre style="background:#fdf3f2;border:1px solid #f3c9c5;border-radius:4px;'
                    f'padding:10px;font-size:11px;color:#333;white-space:pre-wrap;'
                    f'word-break:break-word;margin:6px 0 0;">{escape(tb.strip())}</pre>')

        cards.append(
            f'<div style="border:1px solid #d0d7e2;border-radius:6px;padding:14px;margin:14px 0;background:#fff;">'
            f'<div><b style="font-size:14px;color:#1a2b49;">{escape(job)}</b>'
            f'<span style="background:{bg};color:{fg};font-size:11px;padding:2px 8px;'
            f'border-radius:10px;margin-left:8px;">{label}</span></div>'
            f'<div style="font-size:12px;color:#444;margin-top:8px;">{escape(note)}</div>'
            f'{table}{tb_html}</div>')

    summary = (f"Found {len(job_ids)} job(s), {len(rows)} run(s) today: "
               f"{counts['SUCCESS']} succeeded, {counts['FAILED']} failed, "
               f"{counts['NOT RUN']} not run, {counts['RUNNING']} still running.")

    return f"""<html><body style="margin:0;padding:16px;background:#f4f6f8;font-family:Segoe UI,Arial,sans-serif;">
<div style="max-width:680px;margin:auto;">
  <div style="background:#eaf1fb;border:1px solid #d0d7e2;border-radius:6px 6px 0 0;padding:18px;">
    <div style="font-size:11px;letter-spacing:1.5px;color:#5f6b7a;text-transform:uppercase;">Workflow automation</div>
    <div style="font-size:24px;font-weight:700;color:#1a2b49;margin:8px 0 4px;">Daily job report</div>
    <div style="font-size:12px;color:#444;"><b style="color:{headline_color};">{headline}</b> &middot; Automatic run &middot; {now:%Y-%m-%d}</div>
  </div>
  <div style="background:#fff;border:1px solid #d0d7e2;border-top:none;padding:14px 18px;font-size:13px;color:#222;">
    {escape(summary)}
    <table style="border-collapse:collapse;width:100%;margin-top:12px;font-size:12px;">
      <tr><td style="{TD}width:90px;"><b>First start</b></td><td style="{TD}">{first}{'' if first == '-' else f' {tz}'}</td></tr>
      <tr><td style="{TD}"><b>Last finish</b></td><td style="{TD}">{last}{'' if last == '-' else f' {tz}'}</td></tr>
    </table>
  </div>
  <div style="background:#f4f6f8;border:1px solid #d0d7e2;border-top:none;border-radius:0 0 6px 6px;padding:4px 18px 12px;">
    <div style="font-size:16px;font-weight:700;color:#1a2b49;margin-top:14px;">Job details and today's runs</div>
    {''.join(cards)}
  </div>
</div></body></html>"""


def send_daily_report():
    subject, body = build_daily_report()
    log.info("DAILY REPORT sent: %s", subject)
    send_mail(subject, body, html=build_daily_report_html())


# ----------------------------------------------------- event trigger (mail)
def on_job_started(event):
    if event.job_id == REPORT_JOB_ID:
        return
    start_times[event.job_id] = datetime.now()
    log.info("STARTED  %s", event.job_id)


def on_job_finished(event):
    """Runs automatically the moment ANY job ends - logs it, saves it, mails it."""
    if event.job_id == REPORT_JOB_ID:             # don't log/mail the report job itself
        return
    started = start_times.pop(event.job_id, datetime.now())
    ended = datetime.now()
    info = (f"Job      : {event.job_id}\n"
            f"Started  : {started:{TIME_FMT}}\n"
            f"Ended    : {ended:{TIME_FMT}}\n"
            f"Duration : {ended - started}\n")

    if event.exception:
        reason = f"{type(event.exception).__name__}: {event.exception}"
        log.error("FAILED   %s | %s | took %s", event.job_id, reason, ended - started)
        save_run(event.job_id, started, ended, "FAILED", reason, event.traceback)
        body = info + f"Status   : FAILED\nReason   : {reason}\n\nTraceback:\n{event.traceback}"
        send_mail(f"[FAILED] {event.job_id}", body)
    else:
        log.info("SUCCESS  %s | %s | took %s", event.job_id, event.retval, ended - started)
        save_run(event.job_id, started, ended, "SUCCESS", str(event.retval))
        body = info + f"Status   : SUCCESS\nResult   : {event.retval}\n"
        send_mail(f"[SUCCESS] {event.job_id}", body)


# ---------------------------------------------------------------- scheduler
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        print(build_summary())
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "daily":      # test the end-of-day mail now
        send_daily_report()
        sys.exit(0)

    scheduler = BlockingScheduler()

    # End-of-day summary mail (runs every day at DAILY_REPORT_TIME)
    scheduler.add_job(send_daily_report, "cron", hour=DAILY_REPORT_TIME[0],
                      minute=DAILY_REPORT_TIME[1], id=REPORT_JOB_ID,
                      misfire_grace_time=3600)

    scheduler.add_listener(on_job_started, EVENT_JOB_SUBMITTED)
    scheduler.add_listener(on_job_finished, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    soon = datetime.now() + timedelta(seconds=2)
    scheduler.add_job(data_load,  "date", run_date=soon, id="data_load")
    scheduler.add_job(report_job, "date", run_date=soon, id="report_job")
    scheduler.add_job(backup_job, "date", run_date=soon, id="backup_job")

    # Real-life versions:
    # scheduler.add_job(data_load,  "cron", hour=2, minute=0, id="data_load")
    # scheduler.add_job(backup_job, "cron", day_of_week="sun", hour=1, id="backup_job")
    # scheduler.add_job(report_job, "interval", minutes=30, id="report_job")

    print("Scheduler started. Press Ctrl+C to stop (summary prints on exit).")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nStopped.\n")
        print(build_summary())