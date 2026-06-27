import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Date, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class ProgressStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class CertificateStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class ProgressEntry(TenantScopedModel):
    __tablename__ = "progress_entries"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractor_contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    boq_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("boq_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractor_boq_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    report_date: Mapped[str] = mapped_column(Date, nullable=False)
    work_date: Mapped[str] = mapped_column(Date, nullable=False)
    quantity_completed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cumulative_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProgressStatus] = mapped_column(
        SAEnum(ProgressStatus), default=ProgressStatus.DRAFT, nullable=False
    )
    submitted_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SubcontractorCertificate(TenantScopedModel):
    __tablename__ = "subcontractor_certificates"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractor_contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    certificate_number: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[str] = mapped_column(Date, nullable=False)
    period_end: Mapped[str] = mapped_column(Date, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[CertificateStatus] = mapped_column(
        SAEnum(CertificateStatus), default=CertificateStatus.DRAFT, nullable=False
    )
    previous_certified_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_completed_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_certified_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    retention_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    retention_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    gross_payable: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_payable: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    previous_paid_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    amount_due: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invoice_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    items: Mapped[list["SubcontractorCertificateItem"]] = relationship(
        back_populates="certificate", lazy="select", cascade="all, delete-orphan"
    )


class SubcontractorCertificateItem(TenantScopedModel):
    __tablename__ = "subcontractor_certificate_items"

    certificate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractor_certificates.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    boq_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("boq_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    assigned_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    previous_certified_qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    previous_certified_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_certified_qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_certified_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    remaining_qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    certificate: Mapped["SubcontractorCertificate"] = relationship(back_populates="items")
