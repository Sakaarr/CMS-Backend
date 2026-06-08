import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html_body: str) -> bool:
    """
    In development (no SMTP host configured): logs email to console.
    In production: sends via SMTP.
    """
    # Dev mode — always log when no SMTP configured
    if not settings.smtp_host:
        separator = "=" * 70
        logger.info(
            f"\n{separator}\n"
            f"📧 DEV EMAIL — would be sent in production\n"
            f"TO:      {to}\n"
            f"SUBJECT: {subject}\n"
            f"{separator}"
        )
        # Also print to stdout so it's visible even without log config
        print(
            f"\n{separator}\n"
            f"📧 DEV EMAIL\n"
            f"TO:      {to}\n"
            f"SUBJECT: {subject}\n"
            f"{separator}\n",
            flush=True,
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
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

    # Print credentials clearly to dev console
    if not settings.smtp_host:
        print(
            f"\n{'='*70}\n"
            f"📧 TENANT ADMIN CREDENTIALS (dev mode)\n"
            f"Name:        {full_name}\n"
            f"Email:       {to}\n"
            f"Org slug:    {tenant_slug}\n"
            f"Org name:    {tenant_name}\n"
            f"Temp pass:   {temp_password}\n"
            f"Login URL:   {dashboard_url}/login\n"
            f"{'='*70}\n",
            flush=True,
        )

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#111827;">
  <div style="background:#2563eb;padding:24px;border-radius:12px 12px 0 0;text-align:center;">
    <h1 style="color:white;margin:0;font-size:22px;">CMS Platform</h1>
    <p style="color:#bfdbfe;margin:8px 0 0;">Construction Management System</p>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;padding:32px;border-radius:0 0 12px 12px;">
    <h2 style="color:#111827;margin-top:0;">Hello {full_name},</h2>
    <p style="color:#374151;line-height:1.6;">
      Your organisation <strong>{tenant_name}</strong> has been set up on CMS Platform.
      You have been assigned as the <strong>Company Admin</strong>.
    </p>
    <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:20px;margin:24px 0;">
      <p style="margin:0 0 12px;font-weight:600;color:#374151;">Your login credentials:</p>
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="padding:4px 0;color:#6b7280;width:140px;">Organisation slug</td>
            <td style="padding:4px 0;font-family:monospace;font-weight:600;color:#111827;">{tenant_slug}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Email</td>
            <td style="padding:4px 0;color:#111827;">{to}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Temporary password</td>
            <td style="padding:4px 0;font-family:monospace;font-size:18px;font-weight:700;color:#dc2626;">{temp_password}</td></tr>
      </table>
    </div>
    <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin-bottom:24px;">
      <p style="margin:0;color:#92400e;font-size:14px;">⚠️ Please change your password immediately after first login.</p>
    </div>
    <a href="{dashboard_url}" style="display:inline-block;background:#2563eb;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">
      Access Dashboard →
    </a>
  </div>
</body>
</html>"""
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

    # Print credentials clearly to dev console
    if not settings.smtp_host:
        print(
            f"\n{'='*70}\n"
            f"📧 USER CREDENTIALS (dev mode)\n"
            f"Name:        {full_name}\n"
            f"Email:       {to}\n"
            f"Org slug:    {tenant_slug}\n"
            f"Org name:    {tenant_name}\n"
            f"Role:        {role}\n"
            f"Temp pass:   {temp_password}\n"
            f"Login URL:   {dashboard_url}/login\n"
            f"{'='*70}\n",
            flush=True,
        )

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#111827;">
  <div style="background:#2563eb;padding:24px;border-radius:12px 12px 0 0;text-align:center;">
    <h1 style="color:white;margin:0;font-size:22px;">CMS Platform</h1>
    <p style="color:#bfdbfe;margin:8px 0 0;">{tenant_name}</p>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;padding:32px;border-radius:0 0 12px 12px;">
    <h2 style="color:#111827;margin-top:0;">Hello {full_name},</h2>
    <p style="color:#374151;line-height:1.6;">
      An account has been created for you on <strong>{tenant_name}</strong>'s CMS Platform.
      Your role is <strong style="text-transform:capitalize;">{role.replace("_"," ")}</strong>.
    </p>
    <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:20px;margin:24px 0;">
      <p style="margin:0 0 12px;font-weight:600;color:#374151;">Your login credentials:</p>
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="padding:4px 0;color:#6b7280;width:140px;">Organisation slug</td>
            <td style="padding:4px 0;font-family:monospace;font-weight:600;color:#111827;">{tenant_slug}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Email</td>
            <td style="padding:4px 0;color:#111827;">{to}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Temporary password</td>
            <td style="padding:4px 0;font-family:monospace;font-size:18px;font-weight:700;color:#dc2626;">{temp_password}</td></tr>
      </table>
    </div>
    <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px;margin-bottom:24px;">
      <p style="margin:0;color:#92400e;font-size:14px;">⚠️ Please change your password immediately after first login.</p>
    </div>
    <a href="{dashboard_url}" style="display:inline-block;background:#2563eb;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">
      Access Dashboard →
    </a>
  </div>
</body>
</html>"""
    return send_email(to, subject, html)