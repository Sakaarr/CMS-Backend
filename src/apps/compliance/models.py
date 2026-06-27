import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Date, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from src.shared.base_model import TenantScopedModel


class ComplianceDocCategory(str, enum.Enum):
    LICENSE = "license"
    TAX_CERTIFICATE = "tax_certificate"
    INSURANCE = "insurance"
    SAFETY_CERT = "safety_cert"
    QUALITY_CERT = "quality_cert"
    REGISTRATION = "registration"
    OTHER = "other"


class ComplianceDocStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING_RENEWAL = "pending_renewal"


class SubcontractorComplianceDocument(TenantScopedModel):
    __tablename__ = "subcontractor_compliance_docs"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    subcontractor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    document_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[ComplianceDocCategory] = mapped_column(
        SAEnum(ComplianceDocCategory), nullable=False
    )
    status: Mapped[ComplianceDocStatus] = mapped_column(
        SAEnum(ComplianceDocStatus), default=ComplianceDocStatus.ACTIVE, nullable=False
    )
    issuing_authority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issued_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    renewable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    last_reminded_at: Mapped[str | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verified_at: Mapped[str | None] = mapped_column(Date, nullable=True)
