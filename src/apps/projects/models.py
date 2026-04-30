import enum
from sqlalchemy import String, Text, Date, Float, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel
from src.apps.identity.models import UserRole


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectType(str, enum.Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INFRASTRUCTURE = "infrastructure"
    INDUSTRIAL = "industrial"
    RENOVATION = "renovation"
    OTHER = "other"


class SiteStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    COMPLETED = "completed"


class MilestoneStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class Project(TenantScopedModel):
    __tablename__ = "projects"

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. PRJ-2024-001
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_type: Mapped[ProjectType] = mapped_column(
        SAEnum(ProjectType), default=ProjectType.OTHER, nullable=False
    )
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus), default=ProjectStatus.DRAFT, nullable=False
    )

    # Client info
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Location
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Nepal districts
    country: Mapped[str] = mapped_column(String(2), default="NP", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Schedule
    planned_start_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    actual_start_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[str | None] = mapped_column(Date, nullable=True)

    # Budget (in tenant currency)
    estimated_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    approved_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)

    # Progress
    progress_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Manager
    project_manager_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    sites: Mapped[list["Site"]] = relationship(
        back_populates="project", lazy="select", cascade="all, delete-orphan"
    )
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="project", lazy="select", cascade="all, delete-orphan"
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", lazy="select", cascade="all, delete-orphan"
    )


class Site(TenantScopedModel):
    __tablename__ = "sites"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SiteStatus] = mapped_column(
        SAEnum(SiteStatus), default=SiteStatus.ACTIVE, nullable=False
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    site_incharge_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="sites")
    milestones: Mapped[list["Milestone"]] = relationship(
        back_populates="site", lazy="select"
    )


class Milestone(TenantScopedModel):
    __tablename__ = "milestones"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MilestoneStatus] = mapped_column(
        SAEnum(MilestoneStatus), default=MilestoneStatus.PENDING, nullable=False
    )
    planned_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    actual_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="milestones")
    site: Mapped["Site"] = relationship(back_populates="milestones")


class ProjectMember(TenantScopedModel):
    """
    Links a user to a project with a specific role.
    A user must be an org member first, then can be assigned to projects.
    """
    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="members")