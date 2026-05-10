import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class DocumentCategory(str, enum.Enum):
    DRAWING = "drawing"
    CONTRACT = "contract"
    SPECIFICATION = "specification"
    REPORT = "report"
    PHOTO = "photo"
    CERTIFICATE = "certificate"
    PERMIT = "permit"
    INVOICE = "invoice"
    RFI = "rfi"
    SUBMITTAL = "submittal"
    MEETING_MINUTES = "meeting_minutes"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUIRED = "revision_required"


class Document(TenantScopedModel):
    __tablename__ = "documents"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    document_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[DocumentCategory] = mapped_column(
        SAEnum(DocumentCategory), nullable=False
    )
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus), default=DocumentStatus.DRAFT, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # File info
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_kb: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Versioning
    version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Discipline / drawing specific
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    drawing_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sheet_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    uploaded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    approvals: Mapped[list["DocumentApproval"]] = relationship(
        back_populates="document", lazy="select", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["DocumentRevision"]] = relationship(
        back_populates="document", lazy="select", cascade="all, delete-orphan"
    )


class DocumentApproval(TenantScopedModel):
    __tablename__ = "document_approvals"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    approver_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approver_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="approvals")


class DocumentRevision(TenantScopedModel):
    __tablename__ = "document_revisions"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_description: Mapped[str] = mapped_column(Text, nullable=False)
    file_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    revised_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="revisions")