import os
import smtplib
from email.message import EmailMessage

# -----------------------------
# EMAIL DETAILS
# -----------------------------
# Before running, set your app password in the terminal:
#   Mac/Linux:  export EMAIL_PASSWORD="your-app-password"
#   Windows:    set EMAIL_PASSWORD=your-app-password

SENDER_EMAIL = "praghnareddy.d@gmail.com"
RECEIVER_EMAIL = "praghnareddy.d@gmail.com"
APP_PASSWORD = "nfeghyddxkrvxmxi"


# -----------------------------
# YOUR JOB (change only this part)
# -----------------------------

try:
    print("Running program...")

    marks = [70, 85, 90]
    average = sum(marks) / len(marks)   # <-- the job

    status = "PASS"
    message = f"""
Python Test Result: PASS

The program ran successfully.

Average marks: {average}
"""

except Exception as e:
    status = "FAIL"
    message = f"""
Python Test Result: FAIL

Error Type: {type(e).__name__}
Error Reason: {str(e)}
"""


# -----------------------------
# SEND EMAIL
# -----------------------------

email = EmailMessage()
email["From"] = SENDER_EMAIL
email["To"] = RECEIVER_EMAIL
email["Subject"] = f"Python Test - {status}"
email.set_content(message)

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
    smtp.login(SENDER_EMAIL, APP_PASSWORD)
    smtp.send_message(email)

print("Email sent successfully!")
print(status)
