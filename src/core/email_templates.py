import logging
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.apps.identity.models import User, UserPermission, OrganizationMember
from src.core.email import send_email
from src.core.config import settings

logger = logging.getLogger(__name__)


def _base_html(body: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#111827;">
  <div style="background:#2563eb;padding:24px;border-radius:12px 12px 0 0;text-align:center;">
    <h1 style="color:white;margin:0;font-size:20px;">CMS Platform</h1>
    <p style="color:#bfdbfe;margin:6px 0 0;">Construction Management System</p>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;padding:32px;border-radius:0 0 12px 12px;">
    {body}
  </div>
</body>
</html>"""


def approval_requested_html(
    item_type: str,
    item_ref: str,
    project_name: str,
    submitter_name: str,
) -> str:
    return _base_html(f"""
    <h2 style="margin-top:0;">Approval Required</h2>
    <p style="color:#374151;line-height:1.6;">
      <strong>{submitter_name}</strong> has submitted a
      <strong>{item_type}</strong> for your approval.
    </p>
    <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:20px 0;">
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="padding:4px 0;color:#6b7280;width:120px;">Reference</td>
            <td style="padding:4px 0;font-weight:600;color:#111827;">{item_ref}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Type</td>
            <td style="padding:4px 0;color:#111827;">{item_type}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Project</td>
            <td style="padding:4px 0;color:#111827;">{project_name}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Submitted by</td>
            <td style="padding:4px 0;color:#111827;">{submitter_name}</td></tr>
      </table>
    </div>
    <a href="{settings.dashboard_url}/approvals"
       style="display:inline-block;background:#2563eb;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">
      Review in Approvals →
    </a>
""")


def item_approved_html(
    item_type: str,
    item_ref: str,
    project_name: str,
    approver_name: str,
) -> str:
    return _base_html(f"""
    <h2 style="margin-top:0;">✅ Approved</h2>
    <p style="color:#374151;line-height:1.6;">
      Your <strong>{item_type}</strong> has been approved by <strong>{approver_name}</strong>.
    </p>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:20px 0;">
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="padding:4px 0;color:#6b7280;width:120px;">Reference</td>
            <td style="padding:4px 0;font-weight:600;color:#111827;">{item_ref}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Type</td>
            <td style="padding:4px 0;color:#111827;">{item_type}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Project</td>
            <td style="padding:4px 0;color:#111827;">{project_name}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Approved by</td>
            <td style="padding:4px 0;color:#111827;">{approver_name}</td></tr>
      </table>
    </div>
""")


def item_rejected_html(
    item_type: str,
    item_ref: str,
    project_name: str,
    reason: str | None,
) -> str:
    return _base_html(f"""
    <h2 style="margin-top:0;">❌ Rejected</h2>
    <p style="color:#374151;line-height:1.6;">
      Your <strong>{item_type}</strong> has been rejected.
    </p>
    <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin:20px 0;">
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="padding:4px 0;color:#6b7280;width:120px;">Reference</td>
            <td style="padding:4px 0;font-weight:600;color:#111827;">{item_ref}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Type</td>
            <td style="padding:4px 0;color:#111827;">{item_type}</td></tr>
        <tr><td style="padding:4px 0;color:#6b7280;">Project</td>
            <td style="padding:4px 0;color:#111827;">{project_name}</td></tr>
        {f'<tr><td style="padding:4px 0;color:#6b7280;">Reason</td><td style="padding:4px 0;color:#111827;">{reason}</td></tr>' if reason else ""}
      </table>
    </div>
""")


async def notify_permission_holders(
    db: AsyncSession,
    tenant_id: str,
    permission_field: str,
    exclude_user_id: str,
    subject: str,
    html_body: str,
) -> int:
    """Send email to all users in a tenant with a given permission flag set to True."""
    perm_col = getattr(UserPermission, permission_field, None)
    if perm_col is None:
        logger.warning(f"Unknown permission field: {permission_field}")
        return 0

    result = await db.execute(
        select(User.email)
        .join(UserPermission, User.id == UserPermission.user_id)
        .where(and_(
            UserPermission.tenant_id == tenant_id,
            UserPermission.deleted_at.is_(None),
            perm_col.is_(True),
            User.id != exclude_user_id,
            User.is_active.is_(True),
        ))
    )
    emails = [row[0] for row in result.all() if row[0]]
    if not emails:
        logger.info(f"No users with {permission_field} to notify")
        return 0

    sent = 0
    for email in emails:
        try:
            send_email(email, subject, html_body)
            sent += 1
        except Exception as e:
            logger.error(f"Failed to notify {email}: {e}")
    return sent


async def notify_user_by_id(
    db: AsyncSession,
    user_id: str,
    subject: str,
    html_body: str,
) -> bool:
    """Send email to a specific user by their ID."""
    if not user_id:
        return False
    result = await db.execute(
        select(User.email).where(
            User.id == user_id,
            User.is_active.is_(True),
        )
    )
    email = result.scalar_one_or_none()
    if not email:
        logger.info(f"User {user_id} not found or inactive")
        return False
    try:
        send_email(email, subject, html_body)
        return True
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")
        return False
