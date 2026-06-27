from datetime import date, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import selectinload
from src.apps.portal.models import (
    SubcontractorUser,
    SubcontractorPortalRole,
    PortalNotification,
    PortalNotificationType,
)
from src.apps.subcontractors.models import (
    Subcontractor,
    SubcontractorContract,
    SubcontractorBOQItem,
)
from src.apps.quality.models import NCR, PunchListItem, SafetyObservation
from src.apps.compliance.models import SubcontractorComplianceDocument
from src.apps.progress.models import ProgressEntry, SubcontractorCertificate, SubcontractorCertificateItem
from src.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.core.exceptions import (
    UnauthorizedError,
    NotFoundError,
    ValidationError,
    ForbiddenError,
    BusinessRuleError,
)
from src.core.config import settings
import hashlib
import uuid


_TOKEN_EXPIRE_MINUTES = getattr(settings, "jwt_access_token_expire_minutes", 30)
_REFRESH_EXPIRE_DAYS = getattr(settings, "jwt_refresh_token_expire_days", 7)


def _num(prefix: str) -> str:
    return f"{prefix}-{str(uuid.uuid4())[:8].upper()}"


class PortalService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    # ── Auth ──────────────────────────────────────────────────────

    async def login(self, email: str, password: str) -> dict:
        result = await self.db.execute(
            select(SubcontractorUser)
            .options(selectinload(SubcontractorUser.subcontractor))
            .where(
                SubcontractorUser.email == email,
                SubcontractorUser.tenant_id == self.tenant_id,
                SubcontractorUser.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()
        if not user or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedError("Account is inactive")
        if not user.subcontractor or (user.subcontractor.deleted_at is not None):
            raise UnauthorizedError("Linked subcontractor not found")

        user.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()

        extra = {
            "type": "portal_access",
            "subcontractor_id": user.subcontractor_id,
            "role": user.role.value,
            "subcontractor_name": user.subcontractor.name,
        }
        access_token = create_access_token(user.id, extra)
        refresh_token = create_refresh_token(user.id)
        expires_in = _TOKEN_EXPIRE_MINUTES * 60

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "user": {
                "id": user.id,
                "subcontractor_id": user.subcontractor_id,
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
                "role": user.role,
                "is_active": user.is_active,
                "must_change_password": user.must_change_password,
                "last_login_at": user.last_login_at,
                "subcontractor_name": user.subcontractor.name,
            },
        }

    async def refresh_token(self, token: str) -> dict:
        try:
            payload = decode_token(token)
        except ValueError:
            raise UnauthorizedError("Invalid or expired refresh token")
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")

        user_id = payload.get("sub")
        result = await self.db.execute(
            select(SubcontractorUser)
            .options(selectinload(SubcontractorUser.subcontractor))
            .where(
                SubcontractorUser.id == user_id,
                SubcontractorUser.is_active.is_(True),
                SubcontractorUser.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UnauthorizedError("User not found")

        extra = {
            "type": "portal_access",
            "subcontractor_id": user.subcontractor_id,
            "role": user.role.value,
            "subcontractor_name": user.subcontractor.name,
        }
        access_token = create_access_token(user.id, extra)
        new_refresh = create_refresh_token(user.id)
        return {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "expires_in": _TOKEN_EXPIRE_MINUTES * 60,
        }

    async def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        result = await self.db.execute(
            select(SubcontractorUser).where(
                SubcontractorUser.id == user_id,
                SubcontractorUser.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User")
        if not verify_password(current_password, user.hashed_password):
            raise ValidationError("Current password is incorrect")
        user.hashed_password = hash_password(new_password)
        user.must_change_password = False
        await self.db.flush()

    # ── Portal User Management ────────────────────────────────────

    async def create_portal_user(
        self, subcontractor_id: str, data: "CreatePortalUserRequest"
    ) -> SubcontractorUser:
        existing = await self.db.execute(
            select(SubcontractorUser).where(
                SubcontractorUser.email == data.email,
                SubcontractorUser.tenant_id == self.tenant_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValidationError("Email already registered")

        user = SubcontractorUser(
            subcontractor_id=subcontractor_id,
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            phone=data.phone,
            role=data.role,
            must_change_password=True,
            tenant_id=self.tenant_id,
            created_by=subcontractor_id,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def list_portal_users(
        self, subcontractor_id: str
    ) -> list[SubcontractorUser]:
        result = await self.db.execute(
            select(SubcontractorUser).where(
                SubcontractorUser.subcontractor_id == subcontractor_id,
                SubcontractorUser.tenant_id == self.tenant_id,
                SubcontractorUser.deleted_at.is_(None),
            ).order_by(SubcontractorUser.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_portal_user(
        self, user_id: str, data: "UpdatePortalUserRequest"
    ) -> SubcontractorUser:
        result = await self.db.execute(
            select(SubcontractorUser).where(
                SubcontractorUser.id == user_id,
                SubcontractorUser.tenant_id == self.tenant_id,
                SubcontractorUser.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError("Portal user")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(user, k, v)
        await self.db.flush()
        return user

    async def reset_portal_user_password(self, user_id: str) -> str:
        result = await self.db.execute(
            select(SubcontractorUser).where(
                SubcontractorUser.id == user_id,
                SubcontractorUser.tenant_id == self.tenant_id,
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError("Portal user")
        temp = "Temp@" + str(uuid.uuid4())[:8]
        user.hashed_password = hash_password(temp)
        user.must_change_password = True
        await self.db.flush()
        return temp

    # ── Dashboard ─────────────────────────────────────────────────

    async def get_dashboard(self, subcontractor_id: str) -> dict:
        # Active contracts
        contract_count = (await self.db.execute(
            select(func.count()).select_from(SubcontractorContract).where(
                SubcontractorContract.subcontractor_id == subcontractor_id,
                SubcontractorContract.status == "active",
                self._scope(SubcontractorContract),
            )
        )).scalar_one()

        total_value = (await self.db.execute(
            select(func.coalesce(func.sum(SubcontractorContract.contract_value), 0)).where(
                SubcontractorContract.subcontractor_id == subcontractor_id,
                SubcontractorContract.status.in_(["active", "completed"]),
                self._scope(SubcontractorContract),
            )
        )).scalar_one()

        # Find all contract IDs for this subcontractor
        contract_ids_result = await self.db.execute(
            select(SubcontractorContract.id).where(
                SubcontractorContract.subcontractor_id == subcontractor_id,
                self._scope(SubcontractorContract),
            )
        )
        contract_ids = [r[0] for r in contract_ids_result.all()]
        if not contract_ids:
            return {
                "active_contracts": contract_count,
                "total_contract_value": float(total_value),
                "total_certified_value": 0.0,
                "total_paid_amount": 0.0,
                "pending_progress_entries": 0,
                "approved_progress_entries": 0,
                "open_ncrs": 0,
                "open_punch_items": 0,
                "expiring_documents": 0,
            }

        # Certified and paid amounts
        cert_total = (await self.db.execute(
            select(func.coalesce(func.sum(SubcontractorCertificate.total_certified_value), 0)).where(
                SubcontractorCertificate.contract_id.in_(contract_ids),
                SubcontractorCertificate.status.in_(["approved", "paid"]),
                self._scope(SubcontractorCertificate),
            )
        )).scalar_one()

        paid_total = (await self.db.execute(
            select(func.coalesce(func.sum(SubcontractorCertificate.amount_due), 0)).where(
                SubcontractorCertificate.contract_id.in_(contract_ids),
                SubcontractorCertificate.status == "paid",
                self._scope(SubcontractorCertificate),
            )
        )).scalar_one()

        # Progress entries
        pending = (await self.db.execute(
            select(func.count()).select_from(ProgressEntry).where(
                ProgressEntry.contract_id.in_(contract_ids),
                ProgressEntry.status.in_(["draft", "submitted"]),
                self._scope(ProgressEntry),
            )
        )).scalar_one()

        approved = (await self.db.execute(
            select(func.count()).select_from(ProgressEntry).where(
                ProgressEntry.contract_id.in_(contract_ids),
                ProgressEntry.status == "approved",
                self._scope(ProgressEntry),
            )
        )).scalar_one()

        # Quality items
        open_ncrs = (await self.db.execute(
            select(func.count()).select_from(NCR).where(
                NCR.subcontractor_id == subcontractor_id,
                NCR.status.in_(["open", "acknowledged", "in_progress"]),
                self._scope(NCR),
            )
        )).scalar_one()

        open_punch = (await self.db.execute(
            select(func.count()).select_from(PunchListItem).where(
                PunchListItem.subcontractor_id == subcontractor_id,
                PunchListItem.status.in_(["open", "in_progress"]),
                self._scope(PunchListItem),
            )
        )).scalar_one()

        # Expiring compliance documents
        thirty_days = date.today() + timedelta(days=30)
        expiring = (await self.db.execute(
            select(func.count()).select_from(SubcontractorComplianceDocument).where(
                SubcontractorComplianceDocument.subcontractor_id == subcontractor_id,
                SubcontractorComplianceDocument.expiry_date <= thirty_days,
                SubcontractorComplianceDocument.expiry_date >= date.today(),
                SubcontractorComplianceDocument.status.in_(["active", "expiring_soon"]),
                self._scope(SubcontractorComplianceDocument),
            )
        )).scalar_one()

        return {
            "active_contracts": contract_count,
            "total_contract_value": float(total_value),
            "total_certified_value": float(cert_total),
            "total_paid_amount": float(paid_total),
            "pending_progress_entries": pending,
            "approved_progress_entries": approved,
            "open_ncrs": open_ncrs,
            "open_punch_items": open_punch,
            "expiring_documents": expiring,
        }

    # ── Contracts ─────────────────────────────────────────────────

    async def list_contracts(
        self, subcontractor_id: str
    ) -> list[dict]:
        result = await self.db.execute(
            select(SubcontractorContract)
            .where(
                SubcontractorContract.subcontractor_id == subcontractor_id,
                self._scope(SubcontractorContract),
            )
            .order_by(SubcontractorContract.created_at.desc())
        )
        contracts = result.scalars().all()

        output = []
        for c in contracts:
            boq_count = (await self.db.execute(
                select(func.count()).select_from(SubcontractorBOQItem).where(
                    SubcontractorBOQItem.contract_id == c.id,
                    self._scope(SubcontractorBOQItem),
                )
            )).scalar_one()

            output.append({
                "id": c.id,
                "project_id": c.project_id,
                "project_name": None,
                "contract_number": c.contract_number,
                "title": c.title,
                "description": c.description,
                "status": c.status.value if hasattr(c.status, "value") else c.status,
                "contract_value": c.contract_value,
                "currency": c.currency,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "scope_of_work": c.scope_of_work,
                "boq_item_count": boq_count,
            })
        return output

    async def list_boq_items(self, contract_id: str, subcontractor_id: str) -> list[dict]:
        # Verify contract belongs to this subcontractor
        result = await self.db.execute(
            select(SubcontractorContract).where(
                SubcontractorContract.id == contract_id,
                SubcontractorContract.subcontractor_id == subcontractor_id,
                self._scope(SubcontractorContract),
            )
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("Contract")

        # Use the same query pattern as SubcontractorService.list_contract_boq_items
        from src.apps.boq.models import BOQItem

        result = await self.db.execute(
            select(
                SubcontractorBOQItem,
                BOQItem.item_number,
                BOQItem.description,
                BOQItem.unit,
                BOQItem.quantity,
                BOQItem.unit_rate,
            )
            .join(BOQItem, SubcontractorBOQItem.boq_item_id == BOQItem.id)
            .where(
                SubcontractorBOQItem.contract_id == contract_id,
                self._scope(SubcontractorBOQItem),
            )
            .order_by(BOQItem.item_number)
        )
        rows = result.all()

        output = []
        for row, item_number, description, unit, qty, unit_rate in rows:
            cumulative = (await self.db.execute(
                select(func.coalesce(func.sum(ProgressEntry.cumulative_quantity), 0)).where(
                    ProgressEntry.contract_id == contract_id,
                    ProgressEntry.boq_item_id == row.boq_item_id,
                    ProgressEntry.status.in_(["approved", "submitted"]),
                    ProgressEntry.deleted_at.is_(None),
                )
            )).scalar_one()

            remaining = max(0, row.assigned_quantity - float(cumulative))

            output.append({
                "id": row.id,
                "boq_item_id": row.boq_item_id,
                "item_number": item_number or "",
                "description": description or "",
                "unit": unit or "",
                "boq_quantity": float(qty or 0),
                "boq_unit_rate": float(unit_rate or 0),
                "assigned_quantity": row.assigned_quantity,
                "unit_rate": row.unit_rate,
                "contract_amount": row.contract_amount,
                "status": row.status.value if hasattr(row.status, "value") else row.status,
                "cumulative_progress": float(cumulative),
                "remaining_quantity": remaining,
            })
        return output

    # ── Progress ──────────────────────────────────────────────────

    async def _get_contract_ids(self, subcontractor_id: str) -> list[str]:
        result = await self.db.execute(
            select(SubcontractorContract.id).where(
                SubcontractorContract.subcontractor_id == subcontractor_id,
                self._scope(SubcontractorContract),
            )
        )
        return [r[0] for r in result.all()]

    async def create_progress(
        self, subcontractor_id: str, user_id: str, data: "PortalCreateProgressRequest"
    ) -> ProgressEntry:
        contract_ids = await self._get_contract_ids(subcontractor_id)
        if data.contract_id not in contract_ids:
            raise ForbiddenError("Contract does not belong to your subcontractor")

        # Look up contract for project_id and status
        contract_result = await self.db.execute(
            select(SubcontractorContract).where(
                SubcontractorContract.id == data.contract_id,
                self._scope(SubcontractorContract),
            )
        )
        contract = contract_result.scalar_one_or_none()
        if not contract:
            raise NotFoundError("Contract")

        # Verify BOQ item is assigned to this contract
        result = await self.db.execute(
            select(SubcontractorBOQItem).where(
                SubcontractorBOQItem.contract_id == data.contract_id,
                SubcontractorBOQItem.boq_item_id == data.boq_item_id,
                self._scope(SubcontractorBOQItem),
            )
        )
        if not result.scalar_one_or_none():
            raise ValidationError("BOQ item not assigned to this contract")

        # Calculate cumulative
        cumulative = (await self.db.execute(
            select(func.coalesce(func.sum(ProgressEntry.quantity_completed), 0)).where(
                ProgressEntry.contract_id == data.contract_id,
                ProgressEntry.boq_item_id == data.boq_item_id,
                ProgressEntry.status.in_(["submitted", "approved"]),
                ProgressEntry.deleted_at.is_(None),
            )
        )).scalar_one()

        new_cumulative = float(cumulative) + data.quantity_completed

        # Check against assigned quantity
        assign_result = await self.db.execute(
            select(SubcontractorBOQItem).where(
                SubcontractorBOQItem.contract_id == data.contract_id,
                SubcontractorBOQItem.boq_item_id == data.boq_item_id,
                self._scope(SubcontractorBOQItem),
            )
        )
        assignment = assign_result.scalar_one_or_none()
        if assignment and new_cumulative > assignment.assigned_quantity:
            raise ValidationError(
                f"Cumulative quantity ({new_cumulative:.2f}) exceeds assigned quantity ({assignment.assigned_quantity:.2f})"
            )

        entry = ProgressEntry(
            project_id=contract.project_id,
            contract_id=data.contract_id,
            boq_item_id=data.boq_item_id,
            assignment_id=assignment.id if assignment else None,
            report_date=data.report_date,
            work_date=data.work_date,
            quantity_completed=data.quantity_completed,
            cumulative_quantity=new_cumulative,
            remarks=data.remarks,
            status="draft",
            tenant_id=self.tenant_id,
            created_by=user_id,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_progress(
        self, subcontractor_id: str, status: str | None = None,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[dict], int]:
        contract_ids = await self._get_contract_ids(subcontractor_id)
        if not contract_ids:
            return [], 0

        conditions = [
            ProgressEntry.contract_id.in_(contract_ids),
            ProgressEntry.deleted_at.is_(None),
        ]
        if status:
            conditions.append(ProgressEntry.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(ProgressEntry).where(and_(*conditions))
        )).scalar_one()

        from src.apps.boq.models import BOQItem

        result = await self.db.execute(
            select(ProgressEntry, BOQItem.item_number, BOQItem.description)
            .outerjoin(BOQItem, ProgressEntry.boq_item_id == BOQItem.id)
            .where(and_(*conditions))
            .order_by(ProgressEntry.created_at.desc())
            .offset(skip).limit(limit)
        )
        rows = result.all()

        output = []
        for entry, item_num, item_desc in rows:
            output.append({
                "id": entry.id,
                "contract_id": entry.contract_id,
                "boq_item_id": entry.boq_item_id,
                "item_number": item_num or "",
                "item_description": item_desc or "",
                "report_date": entry.report_date,
                "work_date": entry.work_date,
                "quantity_completed": entry.quantity_completed,
                "cumulative_quantity": entry.cumulative_quantity,
                "remarks": entry.remarks,
                "attachments": entry.attachments,
                "status": entry.status.value if hasattr(entry.status, "value") else entry.status,
                "rejection_reason": entry.rejection_reason,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            })
        return output, total

    async def submit_progress(self, entry_id: str, subcontractor_id: str) -> ProgressEntry:
        contract_ids = await self._get_contract_ids(subcontractor_id)
        result = await self.db.execute(
            select(ProgressEntry).where(
                ProgressEntry.id == entry_id,
                ProgressEntry.contract_id.in_(contract_ids),
                ProgressEntry.deleted_at.is_(None),
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise NotFoundError("Progress entry")
        if entry.status != "draft":
            raise ValidationError("Only draft entries can be submitted")
        entry.status = "submitted"
        entry.submitted_at = datetime.now(timezone.utc)
        entry.submitted_by = subcontractor_id
        await self.db.flush()
        return entry

    # ── Certificates ──────────────────────────────────────────────

    async def list_certificates(
        self, subcontractor_id: str, skip: int = 0, limit: int = 20,
    ) -> tuple[list[dict], int]:
        contract_ids = await self._get_contract_ids(subcontractor_id)
        if not contract_ids:
            return [], 0

        conditions = [
            SubcontractorCertificate.contract_id.in_(contract_ids),
            SubcontractorCertificate.deleted_at.is_(None),
        ]

        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorCertificate).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SubcontractorCertificate)
            .where(and_(*conditions))
            .order_by(SubcontractorCertificate.created_at.desc())
            .offset(skip).limit(limit)
        )
        certs = result.scalars().all()

        output = []
        for c in certs:
            output.append({
                "id": c.id,
                "contract_id": c.contract_id,
                "contract_title": None,
                "certificate_number": c.certificate_number,
                "period_start": c.period_start,
                "period_end": c.period_end,
                "status": c.status.value if hasattr(c.status, "value") else c.status,
                "previous_certified_value": c.previous_certified_value,
                "current_completed_value": c.current_completed_value,
                "total_certified_value": c.total_certified_value,
                "retention_percentage": c.retention_percentage,
                "retention_amount": c.retention_amount,
                "deductions": c.deductions,
                "gross_payable": c.gross_payable,
                "net_payable": c.net_payable,
                "previous_paid_amount": c.previous_paid_amount,
                "amount_due": c.amount_due,
                "revision_number": c.revision_number,
                "remarks": c.remarks,
                "approved_at": c.approved_at,
                "created_at": c.created_at,
            })
        return output, total

    async def get_certificate(
        self, cert_id: str, subcontractor_id: str
    ) -> dict | None:
        contract_ids = await self._get_contract_ids(subcontractor_id)
        result = await self.db.execute(
            select(SubcontractorCertificate)
            .options(selectinload(SubcontractorCertificate.items))
            .where(
                SubcontractorCertificate.id == cert_id,
                SubcontractorCertificate.contract_id.in_(contract_ids),
                SubcontractorCertificate.deleted_at.is_(None),
            )
        )
        cert = result.scalar_one_or_none()
        if not cert:
            return None

        items_data = []
        for item in cert.items:
            items_data.append({
                "boq_item_id": item.boq_item_id,
                "description": item.description,
                "unit": item.unit,
                "assigned_quantity": item.assigned_quantity,
                "unit_rate": item.unit_rate,
                "previous_certified_qty": item.previous_certified_qty,
                "previous_certified_amount": item.previous_certified_amount,
                "current_qty": item.current_qty,
                "current_amount": item.current_amount,
                "total_certified_qty": item.total_certified_qty,
                "total_certified_amount": item.total_certified_amount,
                "remaining_qty": item.remaining_qty,
            })

        return {
            "id": cert.id,
            "contract_id": cert.contract_id,
            "contract_title": None,
            "certificate_number": cert.certificate_number,
            "period_start": cert.period_start,
            "period_end": cert.period_end,
            "status": cert.status.value if hasattr(cert.status, "value") else cert.status,
            "previous_certified_value": cert.previous_certified_value,
            "current_completed_value": cert.current_completed_value,
            "total_certified_value": cert.total_certified_value,
            "retention_percentage": cert.retention_percentage,
            "retention_amount": cert.retention_amount,
            "deductions": cert.deductions,
            "gross_payable": cert.gross_payable,
            "net_payable": cert.net_payable,
            "previous_paid_amount": cert.previous_paid_amount,
            "amount_due": cert.amount_due,
            "revision_number": cert.revision_number,
            "remarks": cert.remarks,
            "approved_at": cert.approved_at,
            "created_at": cert.created_at,
            "items": items_data,
        }

    # ── Quality - NCRs ────────────────────────────────────────────

    async def list_ncrs(
        self, subcontractor_id: str, status: str | None = None,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[NCR], int]:
        conditions = [
            NCR.subcontractor_id == subcontractor_id,
            self._scope(NCR),
        ]
        if status:
            conditions.append(NCR.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(NCR).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(NCR).where(and_(*conditions))
            .order_by(NCR.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def respond_to_ncr(
        self, ncr_id: str, subcontractor_id: str, root_cause: str,
        corrective_action: str, preventive_action: str | None = None,
    ) -> NCR:
        result = await self.db.execute(
            select(NCR).where(
                NCR.id == ncr_id,
                NCR.subcontractor_id == subcontractor_id,
                self._scope(NCR),
            )
        )
        ncr = result.scalar_one_or_none()
        if not ncr:
            raise NotFoundError("NCR")
        if ncr.status in ["closed", "resolved"]:
            raise ValidationError("NCR is already closed/resolved")
        ncr.root_cause = root_cause
        ncr.corrective_action = corrective_action
        ncr.preventive_action = preventive_action
        ncr.status = "resolved"
        ncr.closed_date = date.today()
        ncr.updated_by = subcontractor_id
        await self.db.flush()
        return ncr

    # ── Quality - Punch List ──────────────────────────────────────

    async def list_punch_items(
        self, subcontractor_id: str, status: str | None = None,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[PunchListItem], int]:
        conditions = [
            PunchListItem.subcontractor_id == subcontractor_id,
            self._scope(PunchListItem),
        ]
        if status:
            conditions.append(PunchListItem.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(PunchListItem).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(PunchListItem).where(and_(*conditions))
            .order_by(PunchListItem.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def respond_to_punch_item(
        self, item_id: str, subcontractor_id: str, remarks: str, status: str = "completed",
    ) -> PunchListItem:
        result = await self.db.execute(
            select(PunchListItem).where(
                PunchListItem.id == item_id,
                PunchListItem.subcontractor_id == subcontractor_id,
                self._scope(PunchListItem),
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise NotFoundError("Punch list item")
        if item.status in ["completed", "verified", "rejected"]:
            raise ValidationError("Punch item already resolved")
        item.remarks = remarks
        item.status = status
        if status == "completed":
            item.completed_date = date.today()
        await self.db.flush()
        return item

    # ── Quality - Safety Observations ─────────────────────────────

    async def list_safety_observations(
        self, subcontractor_id: str, skip: int = 0, limit: int = 20,
    ) -> tuple[list[SafetyObservation], int]:
        conditions = [
            SafetyObservation.subcontractor_id == subcontractor_id,
            self._scope(SafetyObservation),
        ]
        total = (await self.db.execute(
            select(func.count()).select_from(SafetyObservation).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SafetyObservation).where(and_(*conditions))
            .order_by(SafetyObservation.observation_date.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    # ── Compliance Documents ──────────────────────────────────────

    async def list_compliance_docs(
        self, subcontractor_id: str, category: str | None = None,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[SubcontractorComplianceDocument], int]:
        conditions = [
            SubcontractorComplianceDocument.subcontractor_id == subcontractor_id,
            self._scope(SubcontractorComplianceDocument),
        ]
        if category:
            conditions.append(SubcontractorComplianceDocument.category == category)

        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorComplianceDocument).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SubcontractorComplianceDocument).where(and_(*conditions))
            .order_by(SubcontractorComplianceDocument.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    # ── Payments ──────────────────────────────────────────────────

    async def list_payments(
        self, subcontractor_id: str, skip: int = 0, limit: int = 20,
    ) -> tuple[list[dict], int]:
        contract_ids = await self._get_contract_ids(subcontractor_id)
        if not contract_ids:
            return [], 0

        from src.apps.finance.models import Invoice, Payment

        conditions = [
            Invoice.id == Payment.invoice_id,
            Invoice.deleted_at.is_(None),
            Payment.deleted_at.is_(None),
            Invoice.tenant_id == self.tenant_id,
        ]

        # Filter to invoices linked to our subcontractor's certificates
        cert_subq = (
            select(SubcontractorCertificate.invoice_id)
            .where(
                SubcontractorCertificate.contract_id.in_(contract_ids),
                SubcontractorCertificate.invoice_id.isnot(None),
                SubcontractorCertificate.deleted_at.is_(None),
            )
        ).subquery()

        total = (await self.db.execute(
            select(func.count()).select_from(Payment)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .where(
                Invoice.id.in_(select(cert_subq.c.invoice_id)),
                *conditions,
            )
        )).scalar_one()

        result = await self.db.execute(
            select(
                Payment.id,
                Invoice.invoice_number,
                Invoice.grand_total.label("gross_amount"),
                Invoice.discount_amount.label("deductions"),
                Invoice.balance_due.label("net_amount"),
                Invoice.paid_amount,
                Payment.payment_date,
                Payment.method.label("payment_method"),
                Invoice.status,
                Payment.created_at,
                SubcontractorCertificate.certificate_number,
            )
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .outerjoin(
                SubcontractorCertificate,
                SubcontractorCertificate.invoice_id == Invoice.id,
            )
            .where(
                Invoice.id.in_(select(cert_subq.c.invoice_id)),
                *conditions,
            )
            .order_by(Payment.created_at.desc())
            .offset(skip).limit(limit)
        )
        rows = result.all()

        output = []
        for row in rows:
            output.append({
                "id": row.id,
                "invoice_number": row.invoice_number,
                "certificate_number": row.certificate_number,
                "gross_amount": float(row.gross_amount or 0),
                "deductions": float(row.deductions or 0),
                "net_amount": float(row.net_amount or 0),
                "paid_amount": float(row.paid_amount or 0),
                "payment_date": row.payment_date,
                "payment_method": row.payment_method,
                "status": row.status,
                "created_at": row.created_at,
            })
        return output, total

    # ── Notifications ─────────────────────────────────────────────

    async def create_notification(
        self, user_id: str, title: str, message: str,
        notif_type: PortalNotificationType,
        reference_type: str | None = None,
        reference_id: str | None = None,
    ) -> PortalNotification:
        notif = PortalNotification(
            subcontractor_user_id=user_id,
            title=title,
            message=message,
            notification_type=notif_type,
            reference_type=reference_type,
            reference_id=reference_id,
            tenant_id=self.tenant_id,
        )
        self.db.add(notif)
        await self.db.flush()
        return notif

    async def list_notifications(
        self, user_id: str, unread_only: bool = False,
        skip: int = 0, limit: int = 50,
    ) -> tuple[list[PortalNotification], int]:
        conditions = [
            PortalNotification.subcontractor_user_id == user_id,
            PortalNotification.deleted_at.is_(None),
        ]
        if unread_only:
            conditions.append(PortalNotification.is_read.is_(False))

        total = (await self.db.execute(
            select(func.count()).select_from(PortalNotification).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(PortalNotification).where(and_(*conditions))
            .order_by(PortalNotification.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def mark_notification_read(self, notif_id: str, user_id: str) -> PortalNotification:
        result = await self.db.execute(
            select(PortalNotification).where(
                PortalNotification.id == notif_id,
                PortalNotification.subcontractor_user_id == user_id,
                PortalNotification.deleted_at.is_(None),
            )
        )
        notif = result.scalar_one_or_none()
        if not notif:
            raise NotFoundError("Notification")
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        await self.db.flush()
        return notif

    async def mark_all_notifications_read(self, user_id: str) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(PortalNotification).where(
                PortalNotification.subcontractor_user_id == user_id,
                PortalNotification.is_read.is_(False),
                PortalNotification.deleted_at.is_(None),
            )
        )
        count = result.scalar_one()

        from sqlalchemy import update as sql_update
        await self.db.execute(
            sql_update(PortalNotification)
            .where(
                PortalNotification.subcontractor_user_id == user_id,
                PortalNotification.is_read.is_(False),
                PortalNotification.deleted_at.is_(None),
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        await self.db.flush()
        return count
