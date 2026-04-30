import enum
from sqlalchemy import String, Boolean, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import BaseModel, TenantScopedModel

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    COMPANY_ADMIN = "company_admin"
    PROJECT_MANAGER = "project_manager"
    SITE_ENGINEER = "site_engineer"
    FINANCE = "finance"
    PROCUREMENT = "procurement"
    QA_OFFICER = "qa_officer"
    VIEWER = "viewer"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    SUSPENDED = "suspended"


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus), default=UserStatus.ACTIVE, nullable=False
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    memberships: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="user", lazy="select"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )

class OrganizationMember(TenantScopedModel):
    """
    Links a user to a tenant/organization with a specific role.
    A user can be a member of multiple tenants with different roles.
    """
    __tablename__ = "organization_members"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole), default=UserRole.VIEWER, nullable=False
    )
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invited_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="memberships")


class RefreshToken(BaseModel):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")