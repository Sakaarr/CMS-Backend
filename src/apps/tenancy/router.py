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