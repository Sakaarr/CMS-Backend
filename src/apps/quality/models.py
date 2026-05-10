import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Date, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class InspectionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InspectionType(str, enum.Enum):
    STRUCTURAL = "structural"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    FIRE_SAFETY = "fire_safety"
    QUALITY = "quality"
    SAFETY = "safety"
    ENVIRONMENTAL = "environmental"
    FINAL = "final"
    OTHER = "other"


class NCRStatus(str, enum.Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    DISPUTED = "disputed"


class NCRSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentSeverity(str, enum.Enum):
    NEAR_MISS = "near_miss"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    FATAL = "fatal"


class IncidentStatus(str, enum.Enum):
    REPORTED = "reported"
    UNDER_INVESTIGATION = "under_investigation"
    RESOLVED = "resolved"
    CLOSED = "closed"


class PunchListStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ChecklistStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Inspection(TenantScopedModel):
    __tablename__ = "inspections"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    inspection_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    inspection_type: Mapped[InspectionType] = mapped_column(
        SAEnum(InspectionType), nullable=False
    )
    status: Mapped[InspectionStatus] = mapped_column(
        SAEnum(InspectionStatus), default=InspectionStatus.SCHEDULED, nullable=False
    )
    scheduled_date: Mapped[str] = mapped_column(Date, nullable=False)
    completed_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    inspector_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inspector_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_third_party: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        back_populates="inspection", lazy="select", cascade="all, delete-orphan"
    )
    ncrs: Mapped[list["NCR"]] = relationship(
        back_populates="inspection", lazy="select"
    )


class ChecklistItem(TenantScopedModel):
    __tablename__ = "checklist_items"

    inspection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    item_number: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    inspection: Mapped["Inspection"] = relationship(back_populates="checklist_items")


class NCR(TenantScopedModel):
    __tablename__ = "ncrs"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    inspection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inspections.id", ondelete="SET NULL"), nullable=True
    )
    ncr_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NCRStatus] = mapped_column(
        SAEnum(NCRStatus), default=NCRStatus.OPEN, nullable=False
    )
    severity: Mapped[NCRSeverity] = mapped_column(
        SAEnum(NCRSeverity), default=NCRSeverity.MEDIUM, nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raised_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    closed_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    preventive_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    inspection: Mapped["Inspection | None"] = relationship(back_populates="ncrs")


class SafetyIncident(TenantScopedModel):
    __tablename__ = "safety_incidents"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    incident_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        SAEnum(IncidentSeverity), nullable=False
    )
    status: Mapped[IncidentStatus] = mapped_column(
        SAEnum(IncidentStatus), default=IncidentStatus.REPORTED, nullable=False
    )
    incident_date: Mapped[str] = mapped_column(Date, nullable=False)
    incident_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    persons_involved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    injuries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fatalities: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    property_damage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    immediate_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    investigated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_reportable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PunchListItem(TenantScopedModel):
    __tablename__ = "punch_list_items"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    inspection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inspections.id", ondelete="SET NULL"), nullable=True
    )
    item_number: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PunchListStatus] = mapped_column(
        SAEnum(PunchListStatus), default=PunchListStatus.OPEN, nullable=False
    )
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    completed_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)