from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
from src.apps.documents.models import (
    Document, DocumentApproval, DocumentRevision,
    DocumentStatus, ApprovalStatus,
)
from src.apps.documents.schemas import (
    CreateDocumentRequest, UpdateDocumentRequest,
    AddRevisionRequest, ApprovalActionRequest, AddApproverRequest,
)
from src.core.exceptions import NotFoundError, ValidationError, ConflictError
import uuid


def _doc_number() -> str:
    return f"DOC-{str(uuid.uuid4())[:8].upper()}"


class DocumentService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    # ── Documents ─────────────────────────────────────────────────

    async def create_document(
        self, project_id: str, data: CreateDocumentRequest
    ) -> Document:
        doc = Document(
            project_id=project_id,
            site_id=data.site_id,
            document_number=_doc_number(),
            title=data.title,
            category=data.category,
            file_name=data.file_name,
            file_url=data.file_url,
            file_size_kb=data.file_size_kb,
            file_type=data.file_type,
            description=data.description,
            tags=data.tags,
            discipline=data.discipline,
            drawing_number=data.drawing_number,
            sheet_number=data.sheet_number,
            version=data.version,
            uploaded_by=self.user_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(doc)
        await self.db.flush()
        return await self.get_document(doc.id)

    async def list_documents(
        self,
        project_id: str,
        category=None,
        status=None,
        search: str | None = None,
        discipline: str | None = None,
        skip: int = 0,
        limit: int = 30,
    ) -> tuple[list[Document], int]:
        conditions = [
            Document.project_id == project_id,
            Document.is_latest.is_(True),
            self._scope(Document),
        ]
        if category:
            conditions.append(Document.category == category)
        if status:
            conditions.append(Document.status == status)
        if search:
            conditions.append(
                Document.title.ilike(f"%{search}%") |
                Document.document_number.ilike(f"%{search}%") |
                Document.drawing_number.ilike(f"%{search}%")
            )
        if discipline:
            conditions.append(Document.discipline.ilike(f"%{discipline}%"))

        total = (await self.db.execute(
            select(func.count()).select_from(Document).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(Document)
            .where(and_(*conditions))
            .order_by(Document.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_document(self, document_id: str) -> Document:
        result = await self.db.execute(
            select(Document)
            .options(
                selectinload(Document.approvals),
                selectinload(Document.revisions),
            )
            .where(and_(Document.id == document_id, self._scope(Document)))
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document")
        return doc

    async def update_document(
        self, document_id: str, data: UpdateDocumentRequest
    ) -> Document:
        doc = await self.get_document(document_id)
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(doc, k, v)
        doc.updated_by = self.user_id
        await self.db.flush()
        return await self.get_document(document_id)

    async def submit_for_review(self, document_id: str) -> Document:
        doc = await self.get_document(document_id)
        if doc.status != DocumentStatus.DRAFT:
            raise ValidationError("Only draft documents can be submitted for review")
        doc.status = DocumentStatus.UNDER_REVIEW
        await self.db.flush()
        return await self.get_document(document_id)

    async def add_revision(
        self, document_id: str, data: AddRevisionRequest
    ) -> Document:
        doc = await self.get_document(document_id)

        # Save current as revision
        revision = DocumentRevision(
            document_id=document_id,
            version=doc.version,
            revision_number=doc.revision_number,
            change_description=data.change_description,
            file_url=doc.file_url,
            file_name=doc.file_name,
            revised_by=self.user_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(revision)

        # Update document with new version
        doc.version = data.new_version
        doc.revision_number += 1
        doc.file_url = data.file_url
        doc.file_name = data.file_name
        doc.status = DocumentStatus.DRAFT
        doc.updated_by = self.user_id
        await self.db.flush()
        return await self.get_document(document_id)

    async def delete_document(self, document_id: str) -> None:
        doc = await self.get_document(document_id)
        from datetime import datetime, timezone
        doc.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    # ── Approvals ─────────────────────────────────────────────────

    async def add_approver(
        self, document_id: str, data: AddApproverRequest
    ) -> DocumentApproval:
        await self.get_document(document_id)
        approval = DocumentApproval(
            document_id=document_id,
            approver_id=data.approver_id,
            approver_name=data.approver_name,
            sequence=data.sequence,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(approval)
        await self.db.flush()
        return approval

    async def action_approval(
        self, document_id: str, approval_id: str, data: ApprovalActionRequest
    ) -> DocumentApproval:
        result = await self.db.execute(
            select(DocumentApproval).where(and_(
                DocumentApproval.id == approval_id,
                DocumentApproval.document_id == document_id,
                self._scope(DocumentApproval),
            ))
        )
        approval = result.scalar_one_or_none()
        if not approval:
            raise NotFoundError("Approval")

        approval.status = data.status
        approval.comments = data.comments
        await self.db.flush()

        # Check if all approvals done
        doc = await self.get_document(document_id)
        all_approvals = (await self.db.execute(
            select(DocumentApproval).where(
                DocumentApproval.document_id == document_id
            )
        )).scalars().all()

        if all(a.status == ApprovalStatus.APPROVED for a in all_approvals):
            doc.status = DocumentStatus.APPROVED
        elif any(a.status == ApprovalStatus.REJECTED for a in all_approvals):
            doc.status = DocumentStatus.REJECTED

        await self.db.flush()
        return approval

    # ── Summary ───────────────────────────────────────────────────

    async def get_document_summary(self, project_id: str) -> dict:
        by_cat = (await self.db.execute(
            select(Document.category, func.count(Document.id))
            .where(and_(
                Document.project_id == project_id,
                Document.is_latest.is_(True),
                self._scope(Document),
            ))
            .group_by(Document.category)
        )).all()

        by_status = (await self.db.execute(
            select(Document.status, func.count(Document.id))
            .where(and_(
                Document.project_id == project_id,
                Document.is_latest.is_(True),
                self._scope(Document),
            ))
            .group_by(Document.status)
        )).all()

        pending_approvals = (await self.db.execute(
            select(func.count(DocumentApproval.id))
            .join(Document, Document.id == DocumentApproval.document_id)
            .where(and_(
                Document.project_id == project_id,
                DocumentApproval.status == ApprovalStatus.PENDING,
                self._scope(DocumentApproval),
            ))
        )).scalar_one()

        return {
            "total_documents": sum(r[1] for r in by_cat),
            "by_category": {r[0]: r[1] for r in by_cat},
            "by_status": {r[0]: r[1] for r in by_status},
            "pending_approvals": pending_approvals,
        }
