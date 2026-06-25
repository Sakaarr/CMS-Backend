import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Date, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class SubcontractorStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLACKLISTED = "blacklisted"


class SubcontractorSpecialty(str, enum.Enum):
    STRUCTURAL = "structural"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    HVAC = "hvac"
    FINISHING = "finishing"
    ROOFING = "roofing"
    PAINTING = "painting"
    LANDSCAPING = "landscaping"
    GENERAL = "general"
    OTHER = "other"


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    CANCELLED = "cancelled"


class WorkOrderStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Subcontractor(TenantScopedModel):
    __tablename__ = "subcontractors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    specialty: Mapped[SubcontractorSpecialty] = mapped_column(
        SAEnum(SubcontractorSpecialty), nullable=False
    )
    status: Mapped[SubcontractorStatus] = mapped_column(
        SAEnum(SubcontractorStatus), default=SubcontractorStatus.ACTIVE, nullable=False
    )
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pan_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    insurance_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insurance_valid_until: Mapped[str | None] = mapped_column(Date, nullable=True)
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SubcontractorContract(TenantScopedModel):
    __tablename__ = "subcontractor_contracts"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    subcontractor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    contract_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ContractStatus] = mapped_column(
        SAEnum(ContractStatus), default=ContractStatus.DRAFT, nullable=False
    )
    scope_of_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    start_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    retention_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    signed_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    signed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    subcontractor: Mapped["Subcontractor"] = relationship(lazy="select")


class WorkOrder(TenantScopedModel):
    __tablename__ = "work_orders"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractor_contracts.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    work_order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[WorkOrderStatus] = mapped_column(
        SAEnum(WorkOrderStatus), default=WorkOrderStatus.PENDING, nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    scheduled_start: Mapped[str | None] = mapped_column(Date, nullable=True)
    scheduled_end: Mapped[str | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[str | None] = mapped_column(Date, nullable=True)
    actual_end: Mapped[str | None] = mapped_column(Date, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
