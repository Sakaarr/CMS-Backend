from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from src.apps.progress.models import (
    ProgressEntry, ProgressStatus,
    SubcontractorCertificate, SubcontractorCertificateItem, CertificateStatus,
)
from src.apps.progress.schemas import (
    CreateProgressEntryRequest, UpdateProgressEntryRequest,
    CreateCertificateRequest, UpdateCertificateRequest,
    ContractProgressSummary, ProgressDashboard,
)
from src.apps.subcontractors.models import (
    SubcontractorContract, SubcontractorBOQItem, Subcontractor,
    SubcontractorStatus, ContractStatus,
)
from src.apps.boq.models import BOQItem
from src.apps.finance.models import (
    Invoice, InvoiceLineItem, InvoiceType, InvoiceStatus,
    Payment, PaymentMethod,
)
from src.core.exceptions import (
    NotFoundError, ValidationError, BusinessRuleError, ConflictError,
    ConcurrentModificationError,
)
from src.apps.tenancy.models import Tenant
from src.apps.projects.models import Project


class ProgressService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    # ── Helpers ─────────────────────────────────────────────────

    async def _get_contract(self, contract_id: str) -> SubcontractorContract:
        result = await self.db.execute(
            select(SubcontractorContract).options(selectinload(SubcontractorContract.subcontractor)).where(and_(
                SubcontractorContract.id == contract_id,
                self._scope(SubcontractorContract),
            ))
        )
        c = result.scalar_one_or_none()
        if not c:
            raise NotFoundError("Contract")
        return c

    async def _get_boq_item(self, boq_item_id: str) -> BOQItem:
        result = await self.db.execute(
            select(BOQItem).where(and_(
                BOQItem.id == boq_item_id,
                self._scope(BOQItem),
            ))
        )
        b = result.scalar_one_or_none()
        if not b:
            raise NotFoundError("BOQ Item")
        return b

    async def _get_project(self, project_id: str):
        from src.apps.projects.models import ProjectStatus
        result = await self.db.execute(
            select(Project).where(and_(
                Project.id == project_id,
                Project.deleted_at.is_(None),
            ))
        )
        p = result.scalar_one_or_none()
        if not p:
            raise NotFoundError("Project")
        return p

    async def _validate_contract_active(self, contract: SubcontractorContract) -> None:
        """Reject progress for cancelled/terminated contracts."""
        if contract.status in (ContractStatus.CANCELLED, ContractStatus.TERMINATED):
            raise BusinessRuleError(
                f"Cannot record progress on a {contract.status.value} contract",
                error_code="CONTRACT_CLOSED",
            )

    async def _validate_subcontractor_active(self, contract: SubcontractorContract) -> None:
        """Reject progress for inactive subcontractors."""
        sub = contract.subcontractor
        if sub and sub.status != SubcontractorStatus.ACTIVE:
            raise BusinessRuleError(
                f"Subcontractor '{sub.name}' is {sub.status.value}. Only active subcontractors can have progress.",
                error_code="SUBCONTRACTOR_INACTIVE",
            )

    async def _validate_project_active(self, project_id: str) -> None:
        """Reject progress for closed/cancelled projects."""
        from src.apps.projects.models import ProjectStatus
        project = await self._get_project(project_id)
        if project.status in (ProjectStatus.CANCELLED, ProjectStatus.COMPLETED):
            raise BusinessRuleError(
                f"Project is {project.status.value}. Cannot record progress on closed projects.",
                error_code="PROJECT_CLOSED",
            )

    async def _calc_cumulative(
        self, contract_id: str, boq_item_id: str, exclude_id: str | None = None,
    ) -> float:
        conditions = [
            ProgressEntry.contract_id == contract_id,
            ProgressEntry.boq_item_id == boq_item_id,
            ProgressEntry.status.in_([ProgressStatus.APPROVED, ProgressStatus.SUBMITTED]),
            self._scope(ProgressEntry),
        ]
        if exclude_id:
            conditions.append(ProgressEntry.id != exclude_id)
        result = await self.db.execute(
            select(func.coalesce(func.sum(ProgressEntry.quantity_completed), 0)).where(
                and_(*conditions)
            )
        )
        return result.scalar_one()

    async def _get_assigned_qty(self, contract_id: str, boq_item_id: str) -> float:
        result = await self.db.execute(
            select(func.coalesce(func.sum(SubcontractorBOQItem.assigned_quantity), 0)).where(
                and_(
                    SubcontractorBOQItem.contract_id == contract_id,
                    SubcontractorBOQItem.boq_item_id == boq_item_id,
                    SubcontractorBOQItem.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one()

    async def _get_total_project_boq_qty(self, project_id: str, boq_item_id: str) -> float:
        result = await self.db.execute(
            select(func.coalesce(func.sum(BOQItem.quantity), 0)).where(and_(
                BOQItem.id == boq_item_id,
                BOQItem.project_id == project_id,
                BOQItem.deleted_at.is_(None),
            ))
        )
        return result.scalar_one()

    async def _is_progress_certified(self, entry_id: str) -> bool:
        """Check if a progress entry's quantity has been included in any approved certificate."""
        entry = await self.get_progress(entry_id)
        if entry.status != ProgressStatus.APPROVED:
            return False
        prev_qty, _ = await self._get_prev_certified(entry.contract_id, entry.boq_item_id)
        cumulative_before = await self._calc_cumulative(
            entry.contract_id, entry.boq_item_id, exclude_id=entry_id,
        )
        return prev_qty > cumulative_before

    async def _get_prev_certified(
        self, contract_id: str, boq_item_id: str, exclude_cert_id: str | None = None,
    ) -> tuple[float, float]:
        conditions = [
            SubcontractorCertificate.contract_id == contract_id,
            SubcontractorCertificate.status.in_([CertificateStatus.APPROVED, CertificateStatus.PAID]),
            SubcontractorCertificate.deleted_at.is_(None),
        ]
        if exclude_cert_id:
            conditions.append(SubcontractorCertificate.id != exclude_cert_id)

        subq = select(SubcontractorCertificate.id).where(and_(*conditions)).subquery()
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(SubcontractorCertificateItem.current_qty), 0),
                func.coalesce(func.sum(SubcontractorCertificateItem.current_amount), 0),
            ).where(and_(
                SubcontractorCertificateItem.certificate_id.in_(select(subq.c.id)),
                SubcontractorCertificateItem.boq_item_id == boq_item_id,
                SubcontractorCertificateItem.deleted_at.is_(None),
            ))
        )
        row = result.one()
        return row[0] or 0.0, row[1] or 0.0

    async def _generate_cert_number(self, contract_id: str) -> str:
        contract = await self._get_contract(contract_id)
        short_id = contract.id[:8].upper()
        count = await self.db.execute(
            select(func.count()).select_from(SubcontractorCertificate).where(and_(
                SubcontractorCertificate.contract_id == contract_id,
                SubcontractorCertificate.deleted_at.is_(None),
            ))
        )
        return f"IPC-{short_id}-{count.scalar_one() + 1:04d}"

    # ── Progress Entry CRUD ──────────────────────────────────────

    async def create_progress(
        self, project_id: str, data: CreateProgressEntryRequest,
    ) -> ProgressEntry:
        # Validate project is active
        await self._validate_project_active(project_id)

        # Validate contract exists and belongs to project
        contract = await self._get_contract(data.contract_id)
        if contract.project_id != project_id:
            raise ValidationError("Contract does not belong to this project")

        # Validate contract is not cancelled/terminated
        await self._validate_contract_active(contract)

        # Validate subcontractor is active
        await self._validate_subcontractor_active(contract)

        # Validate BOQ item exists
        await self._get_boq_item(data.boq_item_id)

        # Validate BOQ item is assigned to this contract
        boq_assignment = await self.db.execute(
            select(SubcontractorBOQItem).where(and_(
                SubcontractorBOQItem.contract_id == data.contract_id,
                SubcontractorBOQItem.boq_item_id == data.boq_item_id,
                SubcontractorBOQItem.deleted_at.is_(None),
            ))
        )
        if not boq_assignment.scalar_one_or_none():
            raise BusinessRuleError(
                "BOQ item is not assigned to this contract",
                error_code="BOQ_NOT_ASSIGNED",
            )

        # Prevent duplicate for same contract + boq_item + work_date
        dup = await self.db.execute(
            select(ProgressEntry).where(and_(
                ProgressEntry.contract_id == data.contract_id,
                ProgressEntry.boq_item_id == data.boq_item_id,
                ProgressEntry.work_date == data.work_date,
                ProgressEntry.status.in_([ProgressStatus.DRAFT, ProgressStatus.SUBMITTED]),
                self._scope(ProgressEntry),
            ))
        )
        if dup.scalar_one_or_none():
            raise ConflictError(
                f"A progress entry already exists for this BOQ item on {data.work_date}"
            )

        cumulative = await self._calc_cumulative(data.contract_id, data.boq_item_id)
        cumulative += data.quantity_completed

        # Validate against assigned quantity (per subcontractor)
        assigned_qty = await self._get_assigned_qty(data.contract_id, data.boq_item_id)
        if assigned_qty > 0 and cumulative > assigned_qty:
            raise BusinessRuleError(
                f"Cumulative quantity ({cumulative}) exceeds assigned quantity ({assigned_qty})",
                error_code="QUANTITY_EXCEEDED",
            )

        # Validate against total project BOQ quantity
        total_boq_qty = await self._get_total_project_boq_qty(project_id, data.boq_item_id)
        if total_boq_qty > 0 and cumulative > total_boq_qty:
            raise BusinessRuleError(
                f"Cumulative quantity ({cumulative}) exceeds total project BOQ quantity ({total_boq_qty})",
                error_code="PROJECT_BOQ_EXCEEDED",
            )

        entry = ProgressEntry(
            project_id=project_id,
            contract_id=data.contract_id,
            boq_item_id=data.boq_item_id,
            assignment_id=data.assignment_id,
            report_date=date.today(),
            work_date=data.work_date,
            quantity_completed=data.quantity_completed,
            cumulative_quantity=cumulative,
            remarks=data.remarks,
            attachments=data.attachments,
            status=ProgressStatus.DRAFT,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_progress(
        self, project_id: str, contract_id: str | None = None,
        boq_item_id: str | None = None,
        status: ProgressStatus | None = None,
        skip: int = 0, limit: int = 30,
    ) -> tuple[list[ProgressEntry], int]:
        conditions = [
            ProgressEntry.project_id == project_id,
            self._scope(ProgressEntry),
        ]
        if contract_id:
            conditions.append(ProgressEntry.contract_id == contract_id)
        if boq_item_id:
            conditions.append(ProgressEntry.boq_item_id == boq_item_id)
        if status:
            conditions.append(ProgressEntry.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(ProgressEntry).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(ProgressEntry)
            .where(and_(*conditions))
            .order_by(ProgressEntry.work_date.desc(), ProgressEntry.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_progress(self, entry_id: str) -> ProgressEntry:
        result = await self.db.execute(
            select(ProgressEntry).where(and_(
                ProgressEntry.id == entry_id,
                self._scope(ProgressEntry),
            ))
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise NotFoundError("Progress entry")
        return entry

    async def update_progress(
        self, entry_id: str, data: UpdateProgressEntryRequest,
    ) -> ProgressEntry:
        entry = await self.get_progress(entry_id)

        if entry.status != ProgressStatus.DRAFT:
            raise ValidationError("Only draft entries can be edited")

        # Immutability: if approved and already included in a certificate, block edit
        if await self._is_progress_certified(entry_id):
            raise BusinessRuleError(
                "This progress entry has been included in a payment certificate. "
                "Revise the certificate first or create a new progress entry.",
                error_code="PROGRESS_CERTIFIED",
            )

        if data.quantity_completed is not None and data.quantity_completed != entry.quantity_completed:
            cumulative = await self._calc_cumulative(
                entry.contract_id, entry.boq_item_id, exclude_id=entry_id,
            )
            cumulative += data.quantity_completed
            assigned_qty = await self._get_assigned_qty(entry.contract_id, entry.boq_item_id)
            if assigned_qty > 0 and cumulative > assigned_qty:
                raise BusinessRuleError(
                    f"Cumulative quantity ({cumulative}) exceeds assigned quantity ({assigned_qty})",
                    error_code="QUANTITY_EXCEEDED",
                )
            # Also validate against project BOQ total
            total_boq = await self._get_total_project_boq_qty(entry.project_id, entry.boq_item_id)
            if total_boq > 0 and cumulative > total_boq:
                raise BusinessRuleError(
                    f"Cumulative quantity ({cumulative}) exceeds project BOQ quantity ({total_boq})",
                    error_code="PROJECT_BOQ_EXCEEDED",
                )
            entry.cumulative_quantity = cumulative

        # Version check for concurrent modification
        if data.version is not None and data.version != entry.version:
            raise ConcurrentModificationError(
                "Progress entry was modified by another user. Refresh and try again."
            )

        for k, v in data.model_dump(exclude_none=True).items():
            if k == "version":
                continue
            setattr(entry, k, v)
        entry.version += 1
        entry.updated_by = self.user_id
        await self.db.flush()
        return entry

    async def delete_progress(self, entry_id: str) -> None:
        entry = await self.get_progress(entry_id)
        if entry.status != ProgressStatus.DRAFT:
            raise ValidationError("Only draft entries can be deleted")

        # Immutability: if any quantity from this contract+boq has been certified
        if await self._is_progress_certified(entry_id):
            raise BusinessRuleError(
                "Cannot delete: progress from this BOQ item has been included in a payment certificate. "
                "Revise the certificate first.",
                error_code="PROGRESS_CERTIFIED",
            )

        entry.deleted_at = date.today()
        entry.updated_by = self.user_id
        await self.db.flush()

    # ── Progress Workflow ────────────────────────────────────────

    async def submit_progress(self, entry_id: str) -> ProgressEntry:
        entry = await self.get_progress(entry_id)
        if entry.status != ProgressStatus.DRAFT:
            raise ValidationError("Only draft entries can be submitted")
        entry.status = ProgressStatus.SUBMITTED
        entry.submitted_at = datetime.now(timezone.utc)
        entry.submitted_by = self.user_id
        entry.version += 1
        entry.updated_by = self.user_id
        await self.db.flush()
        return entry

    async def approve_progress(self, entry_id: str, rejection_reason: str | None = None) -> ProgressEntry:
        entry = await self.get_progress(entry_id)
        if entry.status != ProgressStatus.SUBMITTED:
            raise ValidationError("Only submitted entries can be approved or rejected")

        if rejection_reason:
            entry.status = ProgressStatus.REJECTED
            entry.rejection_reason = rejection_reason
        else:
            entry.status = ProgressStatus.APPROVED
            entry.approved_by = self.user_id
            entry.approved_at = datetime.now(timezone.utc)

        entry.version += 1
        entry.updated_by = self.user_id
        await self.db.flush()
        return entry

    # ── BOQ Item-level progress summary ─────────────────────────

    async def get_boq_progress_summary(
        self, contract_id: str,
    ) -> list[dict]:
        """Returns per-BOQ-item progress summary for a contract."""
        assigned_items = await self.db.execute(
            select(
                SubcontractorBOQItem,
                BOQItem.item_number,
                BOQItem.description,
                BOQItem.unit,
                BOQItem.quantity.label("boq_quantity"),
                BOQItem.unit_rate.label("boq_unit_rate"),
            )
            .select_from(SubcontractorBOQItem)
            .join(BOQItem, BOQItem.id == SubcontractorBOQItem.boq_item_id)
            .where(and_(
                SubcontractorBOQItem.contract_id == contract_id,
                SubcontractorBOQItem.deleted_at.is_(None),
                BOQItem.deleted_at.is_(None),
            ))
        )
        rows = assigned_items.all()

        result = []
        for row in rows:
            assignment = row[0]
            total_completed = await self._calc_cumulative(
                contract_id, assignment.boq_item_id,
            )
            prev_qty, prev_amount = await self._get_prev_certified(
                contract_id, assignment.boq_item_id,
            )
            current_certifiable = max(0, total_completed - prev_qty)
            current_amount = current_certifiable * assignment.unit_rate
            remaining_qty = max(0, assignment.assigned_quantity - total_completed)

            result.append({
                "assignment_id": assignment.id,
                "boq_item_id": assignment.boq_item_id,
                "item_number": row[1],
                "description": row[2],
                "unit": row[3],
                "boq_quantity": row[4] or 0,
                "boq_unit_rate": row[5] or 0,
                "assigned_quantity": assignment.assigned_quantity,
                "unit_rate": assignment.unit_rate,
                "total_completed": total_completed,
                "completion_pct": round(
                    (total_completed / assignment.assigned_quantity * 100)
                    if assignment.assigned_quantity > 0 else 0, 1
                ),
                "previous_certified_qty": prev_qty,
                "previous_certified_amount": prev_amount,
                "current_certifiable_qty": current_certifiable,
                "current_certifiable_amount": current_amount,
                "remaining_qty": remaining_qty,
            })
        return result

    # ── Payment Certificate ─────────────────────────────────────

    async def create_certificate(
        self, project_id: str, data: CreateCertificateRequest,
    ) -> SubcontractorCertificate:
        contract = await self._get_contract(data.contract_id)
        if contract.project_id != project_id:
            raise ValidationError("Contract does not belong to this project")

        # Reject if contract is cancelled/terminated
        if contract.status in (ContractStatus.CANCELLED, ContractStatus.TERMINATED):
            raise BusinessRuleError(
                f"Cannot certify progress on a {contract.status.value} contract",
                error_code="CONTRACT_CLOSED",
            )

        if data.period_start > data.period_end:
            raise ValidationError("Period start must be before period end")

        # Validate deductions don't exceed current value
        if data.deductions < 0:
            raise ValidationError("Deductions cannot be negative")

        cert_number = await self._generate_cert_number(data.contract_id)

        latest_cert = await self.db.execute(
            select(SubcontractorCertificate)
            .where(and_(
                SubcontractorCertificate.contract_id == data.contract_id,
                SubcontractorCertificate.status.in_([
                    CertificateStatus.APPROVED, CertificateStatus.PAID,
                ]),
                SubcontractorCertificate.deleted_at.is_(None),
            ))
            .order_by(SubcontractorCertificate.created_at.desc())
            .limit(1)
        )
        prev_cert = latest_cert.scalar_one_or_none()

        retention_pct = contract.retention_percentage
        previous_certified_value = prev_cert.total_certified_value if prev_cert else 0.0
        previous_paid = prev_cert.amount_due if prev_cert else 0.0

        boq_summary = await self.get_boq_progress_summary(data.contract_id)
        if not boq_summary:
            raise BusinessRuleError(
                "No BOQ items assigned to this contract. Assign BOQ items first.",
                error_code="NO_BOQ_ITEMS",
            )

        items_data = []
        total_current_value = 0.0

        for bs in boq_summary:
            current_qty = bs["current_certifiable_qty"]
            current_amount = bs["current_certifiable_amount"]
            if current_qty <= 0:
                continue
            total_current_value += current_amount
            items_data.append({
                "boq_item_id": bs["boq_item_id"],
                "description": bs["description"],
                "unit": bs["unit"],
                "assigned_quantity": bs["assigned_quantity"],
                "unit_rate": bs["unit_rate"],
                "previous_certified_qty": bs["previous_certified_qty"],
                "previous_certified_amount": bs["previous_certified_amount"],
                "current_qty": current_qty,
                "current_amount": current_amount,
                "total_certified_qty": bs["previous_certified_qty"] + current_qty,
                "total_certified_amount": bs["previous_certified_amount"] + current_amount,
                "remaining_qty": bs["remaining_qty"],
            })

        if not items_data:
            raise BusinessRuleError(
                "No new approved progress to certify in this period",
                error_code="NO_PROGRESS_TO_CERTIFY",
            )

        total_certified = previous_certified_value + total_current_value
        retention_amount = round(total_current_value * retention_pct / 100, 2)

        # Prevent negative payable amounts
        gross_payable = round(total_current_value - data.deductions, 2)
        if gross_payable < 0:
            raise BusinessRuleError(
                f"Deductions ({data.deductions}) exceed current work value ({total_current_value})",
                error_code="NEGATIVE_PAYABLE",
            )
        net_payable = round(gross_payable - retention_amount, 2)
        if net_payable < 0:
            raise BusinessRuleError(
                f"Net payable cannot be negative. Retention ({retention_amount}) exceeds gross ({gross_payable}).",
                error_code="NEGATIVE_PAYABLE",
            )
        amount_due = round(previous_paid + net_payable, 2)

        cert = SubcontractorCertificate(
            project_id=project_id,
            contract_id=data.contract_id,
            certificate_number=cert_number,
            period_start=data.period_start,
            period_end=data.period_end,
            is_final=data.is_final,
            status=CertificateStatus.DRAFT,
            previous_certified_value=previous_certified_value,
            current_completed_value=round(total_current_value, 2),
            total_certified_value=round(total_certified, 2),
            retention_percentage=retention_pct,
            retention_amount=retention_amount,
            deductions=round(data.deductions, 2),
            gross_payable=gross_payable,
            net_payable=net_payable,
            previous_paid_amount=previous_paid,
            amount_due=amount_due,
            remarks=data.remarks,
            revision_number=1,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(cert)
        await self.db.flush()

        for item_data in items_data:
            item = SubcontractorCertificateItem(
                **item_data,
                certificate_id=cert.id,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(item)

        await self.db.flush()

        result = await self.db.execute(
            select(SubcontractorCertificate)
            .options(selectinload(SubcontractorCertificate.items))
            .where(and_(SubcontractorCertificate.id == cert.id, self._scope(SubcontractorCertificate)))
        )
        return result.scalar_one()

    async def list_certificates(
        self, project_id: str, contract_id: str | None = None,
        status: CertificateStatus | None = None,
        skip: int = 0, limit: int = 30,
    ) -> tuple[list[SubcontractorCertificate], int]:
        conditions = [
            SubcontractorCertificate.project_id == project_id,
            self._scope(SubcontractorCertificate),
        ]
        if contract_id:
            conditions.append(SubcontractorCertificate.contract_id == contract_id)
        if status:
            conditions.append(SubcontractorCertificate.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorCertificate).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SubcontractorCertificate)
            .options(selectinload(SubcontractorCertificate.items))
            .where(and_(*conditions))
            .order_by(SubcontractorCertificate.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_certificate(self, cert_id: str) -> SubcontractorCertificate:
        result = await self.db.execute(
            select(SubcontractorCertificate)
            .options(selectinload(SubcontractorCertificate.items))
            .where(and_(SubcontractorCertificate.id == cert_id, self._scope(SubcontractorCertificate)))
        )
        cert = result.scalar_one_or_none()
        if not cert:
            raise NotFoundError("Payment certificate")
        return cert

    async def update_certificate(
        self, cert_id: str, data: UpdateCertificateRequest,
    ) -> SubcontractorCertificate:
        cert = await self.get_certificate(cert_id)
        if cert.status != CertificateStatus.DRAFT:
            raise ValidationError("Only draft certificates can be edited")

        # Version check
        if data.version is not None and data.version != cert.version:
            raise ConcurrentModificationError(
                "Certificate was modified by another user. Refresh and try again."
            )

        for k, v in data.model_dump(exclude_none=True).items():
            if k == "version":
                continue
            setattr(cert, k, v)
        cert.version += 1
        cert.updated_by = self.user_id
        await self.db.flush()
        return cert

    async def delete_certificate(self, cert_id: str) -> None:
        cert = await self.get_certificate(cert_id)
        if cert.status != CertificateStatus.DRAFT:
            raise ValidationError("Only draft certificates can be deleted")
        cert.deleted_at = date.today()
        cert.version += 1
        cert.updated_by = self.user_id
        await self.db.flush()

    # ── Certificate Workflow ─────────────────────────────────────

    async def submit_certificate(self, cert_id: str) -> SubcontractorCertificate:
        cert = await self.get_certificate(cert_id)
        if cert.status != CertificateStatus.DRAFT:
            raise ValidationError("Only draft certificates can be submitted")
        cert.status = CertificateStatus.SUBMITTED
        cert.version += 1
        cert.updated_by = self.user_id
        await self.db.flush()
        return cert

    async def _generate_invoice_number(self) -> str:
        result = await self.db.execute(
            select(func.count()).select_from(Invoice).where(
                self._scope(Invoice),
            )
        )
        count = result.scalar_one() + 1
        return f"SUB-INV-{count:05d}"

    async def approve_certificate(self, cert_id: str) -> SubcontractorCertificate:
        cert = await self.get_certificate(cert_id)
        if cert.status != CertificateStatus.SUBMITTED:
            raise ValidationError("Only submitted certificates can be approved")

        # Get contract for subcontractor reference
        contract = await self._get_contract(cert.contract_id)

        # Create Invoice
        invoice = Invoice(
            project_id=cert.project_id,
            invoice_number=await self._generate_invoice_number(),
            invoice_type=InvoiceType.SUBCONTRACTOR,
            status=InvoiceStatus.APPROVED,
            vendor_id=contract.subcontractor_id,
            invoice_date=date.today(),
            period_from=cert.period_start,
            period_to=cert.period_end,
            vat_rate=0.0,
            retention_rate=cert.retention_percentage,
            subtotal=cert.current_completed_value,
            taxable_amount=cert.current_completed_value,
            vat_amount=0.0,
            retention_amount=cert.retention_amount,
            discount_amount=cert.deductions,
            grand_total=cert.net_payable,
            paid_amount=0.0,
            balance_due=cert.amount_due,
            currency="NPR",
            notes=f"Auto-created from certificate {cert.certificate_number}",
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(invoice)
        await self.db.flush()

        # Create InvoiceLineItems from certificate items
        for item in cert.items:
            li = InvoiceLineItem(
                invoice_id=invoice.id,
                boq_item_id=item.boq_item_id,
                description=item.description,
                unit=item.unit,
                quantity=item.current_qty,
                unit_rate=item.unit_rate,
                amount=item.current_amount,
                sort_order=0,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(li)

        # Link certificate to invoice
        cert.invoice_id = invoice.id
        cert.status = CertificateStatus.APPROVED
        cert.approved_by = self.user_id
        cert.approved_at = datetime.now(timezone.utc)
        cert.version += 1
        cert.updated_by = self.user_id
        await self.db.flush()
        return cert

    async def _generate_payment_number(self) -> str:
        result = await self.db.execute(
            select(func.count()).select_from(Payment).where(
                self._scope(Payment),
            )
        )
        count = result.scalar_one() + 1
        return f"SUB-PMT-{count:05d}"

    async def mark_paid(self, cert_id: str) -> SubcontractorCertificate:
        cert = await self.get_certificate(cert_id)
        if cert.status != CertificateStatus.APPROVED:
            raise ValidationError("Only approved certificates can be marked as paid")

        # Sync linked invoice and create Payment record
        if cert.invoice_id:
            inv = await self.db.execute(
                select(Invoice).where(and_(
                    Invoice.id == cert.invoice_id,
                    self._scope(Invoice),
                ))
            )
            invoice = inv.scalar_one_or_none()
            if invoice:
                invoice.status = InvoiceStatus.PAID
                invoice.paid_amount = cert.amount_due
                invoice.balance_due = 0.0

                # Create Payment record for payment history
                payment = Payment(
                    invoice_id=invoice.id,
                    project_id=cert.project_id,
                    payment_number=await self._generate_payment_number(),
                    payment_date=date.today(),
                    amount=cert.amount_due,
                    method=PaymentMethod.BANK_TRANSFER,
                    notes=f"Auto-created from certificate {cert.certificate_number}",
                    tenant_id=self.tenant_id,
                    created_by=self.user_id,
                )
                self.db.add(payment)

        cert.status = CertificateStatus.PAID
        cert.version += 1
        cert.updated_by = self.user_id
        await self.db.flush()
        return cert

    async def revise_certificate(self, cert_id: str) -> SubcontractorCertificate:
        cert = await self.get_certificate(cert_id)
        if cert.status not in (CertificateStatus.APPROVED, CertificateStatus.PAID):
            raise ValidationError("Only approved/paid certificates can be revised")

        revision = SubcontractorCertificate(
            project_id=cert.project_id,
            contract_id=cert.contract_id,
            certificate_number=cert.certificate_number,
            period_start=cert.period_start,
            period_end=cert.period_end,
            is_final=cert.is_final,
            status=CertificateStatus.DRAFT,
            previous_certified_value=cert.previous_certified_value,
            current_completed_value=0,
            total_certified_value=cert.total_certified_value,
            retention_percentage=cert.retention_percentage,
            retention_amount=0,
            deductions=0,
            gross_payable=0,
            net_payable=0,
            previous_paid_amount=cert.amount_due,
            amount_due=0,
            remarks=f"Revision of {cert.certificate_number} v{cert.revision_number}",
            revision_number=cert.revision_number + 1,
            parent_id=cert.id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(revision)
        await self.db.flush()

        for old_item in cert.items:
            new_item = SubcontractorCertificateItem(
                certificate_id=revision.id,
                boq_item_id=old_item.boq_item_id,
                description=old_item.description,
                unit=old_item.unit,
                assigned_quantity=old_item.assigned_quantity,
                unit_rate=old_item.unit_rate,
                previous_certified_qty=old_item.total_certified_qty,
                previous_certified_amount=old_item.total_certified_amount,
                current_qty=0,
                current_amount=0,
                total_certified_qty=old_item.total_certified_qty,
                total_certified_amount=old_item.total_certified_amount,
                remaining_qty=old_item.remaining_qty,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(new_item)

        await self.db.flush()

        result = await self.db.execute(
            select(SubcontractorCertificate)
            .options(selectinload(SubcontractorCertificate.items))
            .where(and_(SubcontractorCertificate.id == revision.id, self._scope(SubcontractorCertificate)))
        )
        return result.scalar_one()

    # ── Dashboard / Summary ──────────────────────────────────────

    async def get_contract_progress_summary(
        self, project_id: str,
    ) -> list[ContractProgressSummary]:
        conditions = [
            SubcontractorContract.project_id == project_id,
            SubcontractorContract.deleted_at.is_(None),
        ]

        contracts = await self.db.execute(
            select(SubcontractorContract)
            .options(selectinload(SubcontractorContract.subcontractor))
            .where(and_(*conditions))
        )
        contract_list = contracts.scalars().all()

        result = []
        for c in contract_list:
            if c.subcontractor is None:
                continue

            total_assigned = await self.db.execute(
                select(func.coalesce(func.sum(SubcontractorBOQItem.assigned_quantity), 0))
                .where(and_(
                    SubcontractorBOQItem.contract_id == c.id,
                    SubcontractorBOQItem.deleted_at.is_(None),
                ))
            )
            assigned_qty = total_assigned.scalar_one()

            total_completed = await self.db.execute(
                select(func.coalesce(func.sum(ProgressEntry.quantity_completed), 0))
                .where(and_(
                    ProgressEntry.contract_id == c.id,
                    ProgressEntry.status == ProgressStatus.APPROVED,
                    self._scope(ProgressEntry),
                ))
            )
            completed_qty = total_completed.scalar_one()

            last_prog = await self.db.execute(
                select(ProgressEntry.work_date)
                .where(and_(
                    ProgressEntry.contract_id == c.id,
                    self._scope(ProgressEntry),
                ))
                .order_by(ProgressEntry.work_date.desc())
                .limit(1)
            )
            last_date = last_prog.scalar_one_or_none()

            total_certified = await self.db.execute(
                select(func.coalesce(func.sum(SubcontractorCertificate.current_completed_value), 0))
                .where(and_(
                    SubcontractorCertificate.contract_id == c.id,
                    SubcontractorCertificate.status.in_([
                        CertificateStatus.APPROVED, CertificateStatus.PAID,
                    ]),
                    SubcontractorCertificate.deleted_at.is_(None),
                ))
            )
            certified_val = total_certified.scalar_one()

            result.append(ContractProgressSummary(
                contract_id=c.id,
                contract_number=c.contract_number,
                project_id=c.project_id,
                subcontractor_name=c.subcontractor.name,
                subcontractor_specialty=c.subcontractor.specialty.value if c.subcontractor.specialty else None,
                total_assigned_quantity=assigned_qty,
                total_completed_quantity=completed_qty,
                completion_percentage=round(
                    (completed_qty / assigned_qty * 100) if assigned_qty > 0 else 0, 1
                ),
                total_contract_value=c.contract_value,
                certified_value=certified_val,
                pending_certification=max(0, c.contract_value - certified_val),
                last_progress_date=last_date,
            ))

        return result

    async def get_progress_dashboard(self, project_id: str) -> ProgressDashboard:
        contracts = await self.get_contract_progress_summary(project_id)

        total_entries = await self.db.execute(
            select(func.count()).select_from(ProgressEntry).where(and_(
                ProgressEntry.project_id == project_id,
                self._scope(ProgressEntry),
            ))
        )

        pending_entries = await self.db.execute(
            select(func.count()).select_from(ProgressEntry).where(and_(
                ProgressEntry.project_id == project_id,
                ProgressEntry.status == ProgressStatus.SUBMITTED,
                self._scope(ProgressEntry),
            ))
        )

        total_certs = await self.db.execute(
            select(func.count()).select_from(SubcontractorCertificate).where(and_(
                SubcontractorCertificate.project_id == project_id,
                self._scope(SubcontractorCertificate),
            ))
        )

        approved_certs = await self.db.execute(
            select(func.count()).select_from(SubcontractorCertificate).where(and_(
                SubcontractorCertificate.project_id == project_id,
                SubcontractorCertificate.status.in_([
                    CertificateStatus.APPROVED, CertificateStatus.PAID,
                ]),
                self._scope(SubcontractorCertificate),
            ))
        )

        total_retention = await self.db.execute(
            select(func.coalesce(func.sum(SubcontractorCertificate.retention_amount), 0))
            .where(and_(
                SubcontractorCertificate.project_id == project_id,
                self._scope(SubcontractorCertificate),
            ))
        )

        total_net = await self.db.execute(
            select(func.coalesce(func.sum(SubcontractorCertificate.net_payable), 0))
            .where(and_(
                SubcontractorCertificate.project_id == project_id,
                SubcontractorCertificate.status == CertificateStatus.APPROVED,
                self._scope(SubcontractorCertificate),
            ))
        )

        pending_payment = await self.db.execute(
            select(func.coalesce(func.sum(SubcontractorCertificate.amount_due), 0))
            .where(and_(
                SubcontractorCertificate.project_id == project_id,
                SubcontractorCertificate.status == CertificateStatus.APPROVED,
                self._scope(SubcontractorCertificate),
            ))
        )

        active_contracts = sum(1 for c in contracts if c.completion_percentage < 100)

        return ProgressDashboard(
            total_contracts=len(contracts),
            active_contracts=active_contracts,
            total_progress_entries=total_entries.scalar_one(),
            pending_approval_entries=pending_entries.scalar_one(),
            total_certificates=total_certs.scalar_one(),
            approved_certificates=approved_certs.scalar_one(),
            total_pending_payment=round(pending_payment.scalar_one(), 2),
            total_certified_value=sum(c.certified_value for c in contracts),
            total_retention_held=round(total_retention.scalar_one(), 2),
            contracts=contracts,
        )
