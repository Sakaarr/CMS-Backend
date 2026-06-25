from sqlalchemy import String, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.shared.base_model import TenantScopedModel


class DeviceToken(TenantScopedModel):
    __tablename__ = "device_tokens"

    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    token: Mapped[str] = mapped_column(String(500), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False, default="expo")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_device_tokens_user_token", "user_id", "token", unique=True),
    )
