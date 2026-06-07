import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html_body: str) -> bool:
    """
    Sends an email. Returns True on success, False on failure.
    In development mode, just logs the email content.
    """
    if settings.app_env == "development" and not settings.smtp_host:
        logger.info(f"\n{'='*60}\nEMAIL TO: {to}\nSUBJECT: {subject}\n{html_body}\n{'='*60}")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from_email
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, to, msg.as_string())

        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


def send_tenant_admin_welcome(
    to: str,
    full_name: str,
    tenant_name: str,
    tenant_slug: str,
    temp_password: str,
    dashboard_url: str,
) -> bool:
    subject = f"Welcome to CMS Platform — Your {tenant_name} Admin Account"
    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #111827;">
  <div style="background: #2563eb; padding: 24px; border-radius: 12px 12px 0 0; text-align: center;">
    <h1 style="color: white; margin: 0; font-size: 22px;">CMS Platform</h1>
    <p style="color: #bfdbfe; margin: 8px 0 0;">Construction Management System</p>
  </div>
  <div style="background: #ffffff; border: 1px solid #e5e7eb; border-top: none; padding: 32px; border-radius: 0 0 12px 12px;">
    <h2 style="color: #111827; margin-top: 0;">Hello {full_name},</h2>
    <p style="color: #374151; line-height: 1.6;">
      Your organisation <strong>{tenant_name}</strong> has been set up on CMS Platform.
      You have been assigned as the <strong>Company Admin</strong>.
    </p>
    <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 24px 0;">
      <p style="margin: 0 0 8px; font-weight: 600; color: #374151;">Your login credentials:</p>
      <p style="margin: 4px 0; color: #6b7280;">Organisation slug: <strong style="color: #111827; font-family: monospace;">{tenant_slug}</strong></p>
      <p style="margin: 4px 0; color: #6b7280;">Email: <strong style="color: #111827;">{to}</strong></p>
      <p style="margin: 4px 0; color: #6b7280;">Temporary password: <strong style="color: #dc2626; font-family: monospace; font-size: 16px;">{temp_password}</strong></p>
    </div>
    <div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 8px; padding: 12px; margin-bottom: 24px;">
      <p style="margin: 0; color: #92400e; font-size: 14px;">⚠️ Please change your password immediately after first login.</p>
    </div>
    <a href="{dashboard_url}" style="display: inline-block; background: #2563eb; color: white; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 600;">
      Access Dashboard →
    </a>
    <p style="color: #9ca3af; font-size: 13px; margin-top: 32px;">
      Dashboard URL: {dashboard_url}<br>
      If you have questions, contact your platform administrator.
    </p>
  </div>
</body>
</html>
"""
    return send_email(to, subject, html)


def send_user_welcome(
    to: str,
    full_name: str,
    tenant_name: str,
    tenant_slug: str,
    role: str,
    temp_password: str,
    dashboard_url: str,
) -> bool:
    subject = f"Your CMS Platform account — {tenant_name}"
    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #111827;">
  <div style="background: #2563eb; padding: 24px; border-radius: 12px 12px 0 0; text-align: center;">
    <h1 style="color: white; margin: 0; font-size: 22px;">CMS Platform</h1>
    <p style="color: #bfdbfe; margin: 8px 0 0;">{tenant_name}</p>
  </div>
  <div style="background: #ffffff; border: 1px solid #e5e7eb; border-top: none; padding: 32px; border-radius: 0 0 12px 12px;">
    <h2 style="color: #111827; margin-top: 0;">Hello {full_name},</h2>
    <p style="color: #374151; line-height: 1.6;">
      An account has been created for you on <strong>{tenant_name}</strong>'s CMS Platform.
      Your assigned role is <strong style="text-transform: capitalize;">{role.replace("_", " ")}</strong>.
    </p>
    <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 24px 0;">
      <p style="margin: 0 0 8px; font-weight: 600; color: #374151;">Your login credentials:</p>
      <p style="margin: 4px 0; color: #6b7280;">Organisation slug: <strong style="color: #111827; font-family: monospace;">{tenant_slug}</strong></p>
      <p style="margin: 4px 0; color: #6b7280;">Email: <strong style="color: #111827;">{to}</strong></p>
      <p style="margin: 4px 0; color: #6b7280;">Temporary password: <strong style="color: #dc2626; font-family: monospace; font-size: 16px;">{temp_password}</strong></p>
    </div>
    <div style="background: #fef3c7; border: 1px solid #fcd34d; border-radius: 8px; padding: 12px; margin-bottom: 24px;">
      <p style="margin: 0; color: #92400e; font-size: 14px;">⚠️ Please change your password immediately after first login.</p>
    </div>
    <a href="{dashboard_url}" style="display: inline-block; background: #2563eb; color: white; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 600;">
      Access Dashboard →
    </a>
  </div>
</body>
</html>
"""
    return send_email(to, subject, html)