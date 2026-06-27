import enum
from datetime import datetime
from sqlalchemy import String, Text, Boolean, ForeignKey, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class SubcontractorPortalRole(str, enum.Enum):
    MANAGER = "manager"
    SITE_ENGINEER = "site_engineer"
    FOREMAN = "foreman"


class PortalNotificationType(str, enum.Enum):
    PROGRESS_APPROVED = "progress_approved"
    PROGRESS_REJECTED = "progress_rejected"
    PROGRESS_SUBMITTED = "progress_submitted"
    CERT_APPROVED = "cert_approved"
    CERT_PAID = "cert_paid"
    NCR_ASSIGNED = "ncr_assigned"
    PUNCH_ASSIGNED = "punch_assigned"
    DOC_EXPIRING = "doc_expiring"
    DOC_VERIFIED = "doc_verified"
    CONTRACT_ACTIVATED = "contract_activated"
    GENERAL = "general"


class SubcontractorUser(TenantScopedModel):
    __tablename__ = "subcontractor_users"

    subcontractor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractors.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role: Mapped[SubcontractorPortalRole] = mapped_column(
        SAEnum(SubcontractorPortalRole), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subcontractor: Mapped["Subcontractor"] = relationship(lazy="select")
    notifications: Mapped[list["PortalNotification"]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )


class PortalNotification(TenantScopedModel):
    __tablename__ = "portal_notifications"

    subcontractor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("subcontractor_users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[PortalNotificationType] = mapped_column(
        SAEnum(PortalNotificationType), nullable=False
    )
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["SubcontractorUser"] = relationship(back_populates="notifications")
