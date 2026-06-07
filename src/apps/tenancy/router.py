from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.tenancy.service import TenantService
from src.apps.tenancy.schemas import (
    CreateTenantRequest,
    UpdateTenantRequest,
    TenantResponse,
)
from src.apps.identity.dependencies import CurrentUser, SuperAdmin
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response
from src.apps.identity.schemas import CreateTenantAdminRequest
from src.apps.identity.service import UserManagementService
from pydantic import BaseModel, field_validator, EmailStr
import re

router = APIRouter(prefix="/tenants", tags=["Tenancy"])


@router.post("", response_model=APIResponse[TenantResponse], status_code=201)
async def create_tenant(
    data: CreateTenantRequest,
    current_user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    service = TenantService(db)
    tenant = await service.create(data, created_by=current_user.id)
    return success_response(
        data=TenantResponse.model_validate(tenant),
        message="Tenant created successfully",
    )


@router.get("", response_model=PaginatedResponse[TenantResponse])
async def list_tenants(
    current_user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = TenantService(db)
    skip = (page - 1) * page_size
    tenants, total = await service.list_all(skip=skip, limit=page_size)
    return paginated_response(
        data=[TenantResponse.model_validate(t) for t in tenants],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{tenant_id}", response_model=APIResponse[TenantResponse])
async def get_tenant(
    tenant_id: str,
    current_user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    service = TenantService(db)
    tenant = await service.get_by_id(tenant_id)
    return success_response(data=TenantResponse.model_validate(tenant))


@router.patch("/{tenant_id}", response_model=APIResponse[TenantResponse])
async def update_tenant(
    tenant_id: str,
    data: UpdateTenantRequest,
    current_user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    service = TenantService(db)
    tenant = await service.update(tenant_id, data)
    return success_response(
        data=TenantResponse.model_validate(tenant),
        message="Tenant updated",
    )


@router.post("/{tenant_id}/suspend", response_model=APIResponse[TenantResponse])
async def suspend_tenant(
    tenant_id: str,
    current_user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    service = TenantService(db)
    tenant = await service.suspend(tenant_id)
    return success_response(
        data=TenantResponse.model_validate(tenant),
        message="Tenant suspended",
    )


@router.post("/{tenant_id}/activate", response_model=APIResponse[TenantResponse])
async def activate_tenant(
    tenant_id: str,
    current_user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    service = TenantService(db)
    tenant = await service.activate(tenant_id)
    return success_response(
        data=TenantResponse.model_validate(tenant),
        message="Tenant activated",
    )

from src.apps.identity.schemas import CreateTenantAdminRequest
from src.apps.identity.service import UserManagementService

class CreateTenantWithAdminRequest(BaseModel):
    # All existing tenant fields
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
    # Admin fields
    admin_full_name: str
    admin_email: EmailStr
    admin_phone: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.lower().strip()
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug can only contain lowercase letters, numbers, hyphens")
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Slug must be 3-50 characters")
        return v


@router.post("", response_model=APIResponse[TenantResponse], status_code=201)
async def create_tenant(
    data: CreateTenantWithAdminRequest,
    current_user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    

    tenant_service = TenantService(db)

    # Create the tenant first
    from src.apps.tenancy.schemas import CreateTenantRequest
    tenant_data = CreateTenantRequest(
        name=data.name, slug=data.slug, email=data.email,
        phone=data.phone, address=data.address, country=data.country,
        currency=data.currency, timezone=data.timezone,
        pan_number=data.pan_number, vat_number=data.vat_number,
    )
    tenant = await tenant_service.create(tenant_data, created_by=current_user.id)

    # Create the admin user for this tenant
    user_svc = UserManagementService(
        db=db, tenant_id=tenant.id, acting_user_id=current_user.id
    )
    admin_data = CreateTenantAdminRequest(
        email=data.admin_email,
        full_name=data.admin_full_name,
        phone=data.admin_phone,
    )
    await user_svc.create_tenant_admin(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        data=admin_data,
    )

    return success_response(
        data=TenantResponse.model_validate(tenant),
        message=f"Tenant created. Admin credentials sent to {data.admin_email}",
    )