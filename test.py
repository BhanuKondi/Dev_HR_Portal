import smtplib
from email.mime.text import MIMEText

# ================= CONFIG =================
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587

EMAIL = "support@atikes.com"       # your email
PASSWORD = "*6kF#pP9@vR2n!LqT9"         # normal password OR app password

TO_EMAIL = "bhanu@atikes.com"   # where you want to receive

# ================= MESSAGE =================
msg = MIMEText("✅ SMTP Test Successful! Your email is working.")
msg['Subject'] = "SMTP Test Email"
msg['From'] = EMAIL
msg['To'] = TO_EMAIL

try:
    # ================= SMTP CONNECTION =================
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()  # enable TLS

    server.login(EMAIL, PASSWORD)

    server.sendmail(EMAIL, TO_EMAIL, msg.as_string())
    server.quit()

    print("✅ Email sent successfully!")

except Exception as e:
    print("❌ Email failed:")
    print(e)