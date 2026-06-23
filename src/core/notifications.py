import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from src.apps.identity.models import OrganizationMember, User, UserRole, UserPermission
from src.core.email import send_email
from src.core.config import settings

logger = logging.getLogger(__name__)

_STYLE = """
body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #111827; }
.header { background: #2563eb; padding: 24px; border-radius: 12px 12px 0 0; text-align: center; }
.header h1 { color: white; margin: 0; font-size: 22px; }
.header p { color: #bfdbfe; margin: 8px 0 0; }
.body { background: #fff; border: 1px solid #e5e7eb; border-top: none; padding: 32px; border-radius: 0 0 12px 12px; }
.btn { display: inline-block; background: #2563eb; color: white; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; }
.meta { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 24px 0; }
.meta table { width: 100%; border-collapse: collapse; }
.meta td { padding: 4px 0; }
.meta td:first-child { color: #6b7280; width: 140px; }
.meta td:last-child { color: #111827; font-weight: 600; }
"""


def _build_html(
    greeting: str,
    body_paragraphs: list[str],
    action_url: str | None = None,
    action_label: str | None = None,
    meta_rows: list[tuple[str, str]] | None = None,
) -> str:
    meta_html = ""
    if meta_rows:
        rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in meta_rows)
        meta_html = f'<div class="meta"><table>{rows}</table></div>'

    action_html = ""
    if action_url and action_label:
        action_html = f'<p style="text-align:center;margin-top:24px;"><a href="{action_url}" class="btn">{action_label} →</a></p>'

    paragraphs = "".join(f"<p style='color:#374151;line-height:1.6;'>{p}</p>" for p in body_paragraphs)

    return f"""<!DOCTYPE html>
<html><head><style>{_STYLE}</style></head>
<body>
<div class="header"><h1>CMS Platform</h1><p>Construction Management System</p></div>
<div class="body">
  <h2>{greeting}</h2>
  {paragraphs}
  {meta_html}
  {action_html}
</div>
</body></html>"""


_MODULE_ROUTES = {
    "finance": "finance",
    "procurement": "procurement",
    "inventory": "inventory",
    "boq": "boq",
    "site_ops": "site-ops",
    "documents": "documents",
}

_MODULE_PERMISSION_FIELD = {
    "finance": "can_finance",
    "procurement": "can_procurement",
    "inventory": "can_inventory",
    "boq": "can_finance",
    "site_ops": "can_site_ops",
    "documents": "can_documents",
}


class NotificationService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def notify_submitted(
        self,
        module: str,
        item_type: str,
        item_id: str,
        item_number: str,
        submitted_by: str,
        project_id: str | None = None,
        extra_meta: dict[str, str] | None = None,
    ) -> None:
        recipients = await self._get_recipients(module, exclude_user_id=submitted_by)
        if not recipients:
            logger.info("No recipients for %s %s submission notification", item_type, item_number)
            return

        action_url = self._action_url(module, project_id)
        label = item_type.replace("_", " ").title()
        meta = [("Item", item_number)]
        if extra_meta:
            meta.extend(extra_meta.items())

        subject = f"[CMS] {label} Submitted — {item_number}"
        for user in recipients:
            html = _build_html(
                greeting=f"Hello {user.full_name},",
                body_paragraphs=[
                    f"A <strong>{label}</strong> ({item_number}) has been submitted "
                    f"for approval and requires your review."
                ],
                action_url=action_url,
                action_label="View in Dashboard",
                meta_rows=meta,
            )
            send_email(user.email, subject, html)

    async def notify_approved(
        self,
        module: str,
        item_type: str,
        item_id: str,
        item_number: str,
        created_by: str,
        approved_by: str,
        project_id: str | None = None,
        extra_meta: dict[str, str] | None = None,
    ) -> None:
        user = await self._get_user(created_by)
        if not user:
            return

        approver = await self._get_user(approved_by)
        approver_name = approver.full_name if approver else "Unknown"

        action_url = self._action_url(module, project_id)
        label = item_type.replace("_", " ").title()
        meta = [("Item", item_number), ("Approved By", approver_name)]
        if extra_meta:
            meta.extend(extra_meta.items())

        subject = f"[CMS] {label} Approved — {item_number}"
        html = _build_html(
            greeting=f"Hello {user.full_name},",
            body_paragraphs=[
                f"Your <strong>{label}</strong> ({item_number}) has been approved."
            ],
            action_url=action_url,
            action_label="View in Dashboard",
            meta_rows=meta,
        )
        send_email(user.email, subject, html)

    async def notify_rejected(
        self,
        module: str,
        item_type: str,
        item_id: str,
        item_number: str,
        created_by: str,
        rejected_by: str,
        project_id: str | None = None,
        extra_meta: dict[str, str] | None = None,
    ) -> None:
        user = await self._get_user(created_by)
        if not user:
            return

        rejector = await self._get_user(rejected_by)
        rejector_name = rejector.full_name if rejector else "Unknown"

        action_url = self._action_url(module, project_id)
        label = item_type.replace("_", " ").title()
        meta = [("Item", item_number), ("Rejected By", rejector_name)]
        if extra_meta:
            meta.extend(extra_meta.items())

        subject = f"[CMS] {label} Rejected — {item_number}"
        html = _build_html(
            greeting=f"Hello {user.full_name},",
            body_paragraphs=[
                f"Your <strong>{label}</strong> ({item_number}) has been rejected."
            ],
            action_url=action_url,
            action_label="View in Dashboard",
            meta_rows=meta,
        )
        send_email(user.email, subject, html)

    async def notify_submitted_to_approver(
        self,
        module: str,
        item_type: str,
        item_id: str,
        item_number: str,
        submitted_by_name: str,
        approver: User,
        project_id: str | None = None,
        extra_meta: dict[str, str] | None = None,
    ) -> None:
        action_url = self._action_url(module, project_id)
        label = item_type.replace("_", " ").title()
        meta = [("Item", item_number), ("Submitted By", submitted_by_name)]
        if extra_meta:
            meta.extend(extra_meta.items())

        subject = f"[CMS] {label} Submitted for Your Review — {item_number}"
        html = _build_html(
            greeting=f"Hello {approver.full_name},",
            body_paragraphs=[
                f"A <strong>{label}</strong> ({item_number}) has been submitted for your review."
            ],
            action_url=action_url,
            action_label="Review in Dashboard",
            meta_rows=meta,
        )
        send_email(approver.email, subject, html)

    async def notify_dpr_submitted(
        self,
        item_number: str,
        report_date: str,
        submitted_by: str,
        project_id: str | None = None,
    ) -> None:
        recipients = await self._get_recipients("site_ops", exclude_user_id=submitted_by)
        if not recipients:
            return

        action_url = self._action_url("site_ops", project_id)
        meta = [("Report Date", report_date)]
        subject = f"[CMS] Daily Progress Report Submitted — {item_number}"
        for user in recipients:
            html = _build_html(
                greeting=f"Hello {user.full_name},",
                body_paragraphs=[
                    f"A daily progress report has been submitted and is available for review."
                ],
                action_url=action_url,
                action_label="View Report",
                meta_rows=meta,
            )
            send_email(user.email, subject, html)

    async def _get_recipients(
        self, module: str, exclude_user_id: str | None = None
    ) -> list[User]:
        admin_result = await self.db.execute(
            select(User)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(and_(
                OrganizationMember.tenant_id == self.tenant_id,
                OrganizationMember.deleted_at.is_(None),
                OrganizationMember.role == UserRole.COMPANY_ADMIN,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            ))
        )
        admin_users = set(admin_result.scalars().all())

        perm_field = _MODULE_PERMISSION_FIELD.get(module)
        perm_users: set[User] = set()
        if perm_field:
            perm_col = getattr(UserPermission, perm_field, None)
            if perm_col is not None:
                perm_result = await self.db.execute(
                    select(User)
                    .join(UserPermission, UserPermission.user_id == User.id)
                    .where(and_(
                        UserPermission.tenant_id == self.tenant_id,
                        UserPermission.deleted_at.is_(None),
                        perm_col.is_(True),
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                    ))
                )
                perm_users = set(perm_result.scalars().all())

        combined = admin_users | perm_users
        if exclude_user_id:
            combined = {u for u in combined if u.id != exclude_user_id}
        return list(combined)

    async def _get_user(self, user_id: str) -> User | None:
        result = await self.db.execute(
            select(User).where(and_(
                User.id == user_id,
                User.deleted_at.is_(None),
            ))
        )
        return result.scalar_one_or_none()

    def _action_url(self, module: str, project_id: str | None) -> str | None:
        route = _MODULE_ROUTES.get(module)
        if not route:
            return None
        base = settings.dashboard_url.rstrip("/")
        url = f"{base}/{route}"
        if project_id:
            url += f"?projectId={project_id}"
        return url
