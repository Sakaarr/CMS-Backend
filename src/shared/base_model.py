import uuid 
from datetime import datetime, timezone
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class UUIDMixin:
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )


class BaseModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Abstract base for all tenant-scoped domain models.
    Every business table inherits from this.
    """
    __abstract__ = True

    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class TenantScopedModel(BaseModel):
    """
    All domain models use this. Enforces tenant_id on every table.
    """
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
