from pydantic import BaseModel, EmailStr, field_validator
from src.apps.tenancy.models import TenantStatus, SubscriptionPlan
import re


class CreateTenantRequest(BaseModel):
    name: str
    slug: str
    email: EmailStr
    phone: str | None = None
    address: str | None = None
    country: str = "NP"
    currency: str = "NPR"
    timezone: str = "Asia/Kathmandu"
    pan_number: str | None = None
    vat_number: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.lower().strip()
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug can only contain lowercase letters, numbers, and hyphens")
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Slug must be between 3 and 50 characters")
        return v


class UpdateTenantRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    pan_number: str | None = None
    vat_number: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: TenantStatus
    plan: SubscriptionPlan
    email: str
    phone: str | None
    country: str
    currency: str
    timezone: str
    pan_number: str | None
    vat_number: str | None
    logo_url: str | None
    primary_color: str | None
    max_projects: int
    max_users: int
    max_storage_gb: int
    is_active: bool

    model_config = {"from_attributes": True}