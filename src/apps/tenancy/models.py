import enum
from sqlalchemy import String, Boolean, Enum as SAEnum, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import BaseModel


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class Tenant(BaseModel):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    status: Mapped[TenantStatus] = mapped_column(
        SAEnum(TenantStatus), default=TenantStatus.TRIAL, nullable=False
    )
    plan: Mapped[SubscriptionPlan] = mapped_column(
        SAEnum(SubscriptionPlan), default=SubscriptionPlan.FREE, nullable=False
    )

    # Contact info
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(String(2), default="NP", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Kathmandu", nullable=False
    )

    # Nepal-specific
    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Branding / white-label
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # Limits (per plan)
    max_projects: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_storage_gb: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)