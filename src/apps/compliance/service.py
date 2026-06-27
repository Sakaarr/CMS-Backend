import logging
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from src.apps.compliance.models import (
    SubcontractorComplianceDocument, ComplianceDocCategory, ComplianceDocStatus,
)
from src.apps.compliance.schemas import (
    CreateComplianceDocRequest, UpdateComplianceDocRequest,
)
from src.apps.subcontractors.models import Subcontractor
from src.core.exceptions import NotFoundError, ValidationError
from src.core.notifications import NotificationService

logger = logging.getLogger(__name__)


class ComplianceService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    async def _generate_doc_number(self, project_id: str, category: ComplianceDocCategory) -> str:
        prefix = category.value[:3].upper()
        count = await self.db.execute(
            select(func.count()).select_from(SubcontractorComplianceDocument).where(and_(
                SubcontractorComplianceDocument.project_id == project_id,
                self._scope(SubcontractorComplianceDocument),
            ))
        )
        return f"COMP-{prefix}-{count.scalar_one() + 1:04d}"

    async def _get_subcontractor(self, subcontractor_id: str) -> Subcontractor:
        result = await self.db.execute(
            select(Subcontractor).where(and_(
                Subcontractor.id == subcontractor_id,
                Subcontractor.deleted_at.is_(None),
            ))
        )
        s = result.scalar_one_or_none()
        if not s:
            raise NotFoundError("Subcontractor")
        return s

    # ── CRUD ─────────────────────────────────────────────────────

    async def create_doc(
        self, project_id: str, data: CreateComplianceDocRequest,
    ) -> SubcontractorComplianceDocument:
        await self._get_subcontractor(data.subcontractor_id)

        if data.expiry_date and data.issued_date and data.expiry_date <= data.issued_date:
            raise ValidationError("Expiry date must be after issued date")

        doc = SubcontractorComplianceDocument(
            project_id=project_id,
            subcontractor_id=data.subcontractor_id,
            document_number=await self._generate_doc_number(project_id, data.category),
            title=data.title,
            category=data.category,
            status=ComplianceDocStatus.ACTIVE,
            issuing_authority=data.issuing_authority,
            reference_number=data.reference_number,
            issued_date=data.issued_date,
            expiry_date=data.expiry_date,
            renewable=data.renewable,
            reminder_days_before=data.reminder_days_before,
            description=data.description,
            file_name=data.file_name,
            file_url=data.file_url,
            notes=data.notes,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self._update_expiry_status(doc)
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def list_docs(
        self, project_id: str,
        subcontractor_id: str | None = None,
        category: ComplianceDocCategory | None = None,
        status: ComplianceDocStatus | None = None,
        expiring_within_days: int | None = None,
        skip: int = 0, limit: int = 30,
    ) -> tuple[list[SubcontractorComplianceDocument], int]:
        conditions = [
            SubcontractorComplianceDocument.project_id == project_id,
            self._scope(SubcontractorComplianceDocument),
        ]
        if subcontractor_id:
            conditions.append(SubcontractorComplianceDocument.subcontractor_id == subcontractor_id)
        if category:
            conditions.append(SubcontractorComplianceDocument.category == category)
        if status:
            conditions.append(SubcontractorComplianceDocument.status == status)
        if expiring_within_days is not None:
            cutoff = date.today() + timedelta(days=expiring_within_days)
            conditions.append(SubcontractorComplianceDocument.expiry_date <= cutoff)
            conditions.append(SubcontractorComplianceDocument.expiry_date >= date.today())

        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorComplianceDocument).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SubcontractorComplianceDocument)
            .where(and_(*conditions))
            .order_by(SubcontractorComplianceDocument.expiry_date.asc().nullslast())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_doc(self, doc_id: str) -> SubcontractorComplianceDocument:
        result = await self.db.execute(
            select(SubcontractorComplianceDocument).where(and_(
                SubcontractorComplianceDocument.id == doc_id,
                self._scope(SubcontractorComplianceDocument),
            ))
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise NotFoundError("Compliance document")
        return doc

    async def update_doc(
        self, doc_id: str, data: UpdateComplianceDocRequest,
    ) -> SubcontractorComplianceDocument:
        doc = await self.get_doc(doc_id)

        for k, v in data.model_dump(exclude_none=True).items():
            setattr(doc, k, v)

        self._update_expiry_status(doc)
        doc.updated_by = self.user_id
        await self.db.flush()
        return doc

    async def delete_doc(self, doc_id: str) -> None:
        doc = await self.get_doc(doc_id)
        doc.deleted_at = date.today()
        doc.updated_by = self.user_id
        await self.db.flush()

    async def verify_doc(self, doc_id: str) -> SubcontractorComplianceDocument:
        doc = await self.get_doc(doc_id)
        doc.verified_by = self.user_id
        doc.verified_at = date.today()
        doc.updated_by = self.user_id
        await self.db.flush()
        return doc

    # ── Expiry Management ────────────────────────────────────────

    def _update_expiry_status(self, doc: SubcontractorComplianceDocument) -> None:
        """Auto-update status based on expiry date."""
        if not doc.expiry_date:
            return
        today = date.today()
        if doc.expiry_date < today:
            doc.status = ComplianceDocStatus.EXPIRED
        elif doc.expiry_date <= today + timedelta(days=doc.reminder_days_before):
            if doc.status not in (ComplianceDocStatus.EXPIRED, ComplianceDocStatus.REVOKED):
                doc.status = ComplianceDocStatus.EXPIRING_SOON

    async def refresh_expiry_statuses(self, project_id: str) -> int:
        """Scan all compliance docs and update their expiry status. Returns count updated."""
        result = await self.db.execute(
            select(SubcontractorComplianceDocument).where(and_(
                SubcontractorComplianceDocument.project_id == project_id,
                self._scope(SubcontractorComplianceDocument),
                SubcontractorComplianceDocument.expiry_date.isnot(None),
            ))
        )
        docs = result.scalars().all()
        updated = 0
        for doc in docs:
            old = doc.status
            self._update_expiry_status(doc)
            if doc.status != old:
                updated += 1
        await self.db.flush()
        return updated

    async def get_expiring_docs(
        self, project_id: str, within_days: int = 30,
    ) -> list[SubcontractorComplianceDocument]:
        today = date.today()
        cutoff = today + timedelta(days=within_days)
        result = await self.db.execute(
            select(SubcontractorComplianceDocument).where(and_(
                SubcontractorComplianceDocument.project_id == project_id,
                self._scope(SubcontractorComplianceDocument),
                SubcontractorComplianceDocument.expiry_date <= cutoff,
                SubcontractorComplianceDocument.expiry_date >= today,
            )).order_by(SubcontractorComplianceDocument.expiry_date.asc())
        )
        return list(result.scalars().all())

    async def notify_expiring_docs(
        self, project_id: str, within_days: int = 30,
    ) -> int:
        """Find expiring compliance docs and send email notifications. Returns count notified."""
        expiring = await self.get_expiring_docs(project_id, within_days)
        if not expiring:
            return 0

        notifier = NotificationService(self.db, self.tenant_id)
        notified = 0
        for doc in expiring:
            # Skip if already reminded today
            if doc.last_reminded_at and doc.last_reminded_at >= date.today():
                continue

            try:
                await notifier.notify_submitted(
                    module="subcontractors",
                    item_type="compliance_document",
                    item_id=doc.id,
                    item_number=doc.document_number,
                    submitted_by=self.user_id,
                    project_id=project_id,
                    extra_meta={
                        "title": doc.title,
                        "category": doc.category.value,
                        "expiry_date": str(doc.expiry_date) if doc.expiry_date else "N/A",
                        "subcontractor_id": doc.subcontractor_id,
                    },
                )
                doc.last_reminded_at = date.today()
                notified += 1
            except Exception as e:
                logger.error("Failed to send expiry notification for doc %s: %s", doc.id, e)

        await self.db.flush()
        return notified
