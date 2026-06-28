import re
from fastapi import APIRouter, Depends, Query, File, UploadFile, Form, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.tenancy.service import TenantService
from src.apps.tenancy.schemas import UpdateTenantRequest, TenantResponse
from src.apps.identity.dependencies import SuperAdmin
from src.shared.response import (
    APIResponse, PaginatedResponse,
    success_response, paginated_response,
)
from src.core.storage import save_file
from src.apps.tenancy.schemas import UpdateBrandingRequest, TenantBrandingResponse
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.core.exceptions import ForbiddenError

router = APIRouter(prefix="/tenants", tags=["Tenancy"])


# ── Request schema (defined here to avoid circular imports) ───────

class CreateTenantWithAdminRequest(BaseModel):
    # Tenant fields
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
    plan: str = "free"

    # Admin user fields
    admin_full_name: str
    admin_email: EmailStr
    admin_phone: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.lower().strip()
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "Slug can only contain lowercase letters, numbers, and hyphens"
            )
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Slug must be between 3 and 50 characters")
        return v

    @field_validator("admin_full_name")
    @classmethod
    def validate_admin_name(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Admin full name must be at least 2 characters")
        return v.strip()


# ── Routes ────────────────────────────────────────────────────────

@router.post("", response_model=APIResponse[TenantResponse], status_code=201)
async def create_tenant(
    data: CreateTenantWithAdminRequest,
    current_user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    """
    Super admin creates a new tenant.
    Also creates the tenant's company admin user and emails their credentials.
    """
    from src.apps.tenancy.schemas import CreateTenantRequest, SubscriptionPlan
    from src.apps.identity.service import UserManagementService
    from src.apps.identity.schemas import CreateTenantAdminRequest

    tenant_service = TenantService(db)

    # Resolve plan
    try:
        plan = SubscriptionPlan(data.plan.lower())
    except ValueError:
        plan = SubscriptionPlan.FREE

    # Step 1: Create tenant
    tenant_data = CreateTenantRequest(
        name=data.name,
        slug=data.slug,
        email=data.email,
        phone=data.phone,
        address=data.address,
        country=data.country,
        currency=data.currency,
        timezone=data.timezone,
        pan_number=data.pan_number,
        vat_number=data.vat_number,
        plan=plan,
    )
    tenant = await tenant_service.create(tenant_data, created_by=current_user.id)

    # Step 2: Create admin user for this tenant
    user_svc = UserManagementService(
        db=db,
        tenant_id=tenant.id,
        acting_user_id=current_user.id,
    )
    admin_data = CreateTenantAdminRequest(
        email=data.admin_email,
        full_name=data.admin_full_name,
        phone=data.admin_phone,
    )
    _, temp_password = await user_svc.create_tenant_admin(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        data=admin_data,
    )

    return success_response(
        data=TenantResponse.model_validate(tenant),
        message=(
            f"Tenant '{tenant.name}' created. "
            f"Admin credentials sent to {data.admin_email}."
        ),
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


# ── "My" routes (must come BEFORE /{tenant_id} to avoid path conflict) ──

@router.get("/my/branding", response_model=APIResponse[TenantBrandingResponse])
async def get_my_branding(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns branding for the current tenant.
    Used by all users (login page, sidebar logo, etc.)
    No admin required — all members can read branding.
    """
    from src.apps.tenancy.service import TenantService
    tenant_slug = getattr(request.state, "tenant_slug", None)
    if not tenant_slug:
        return success_response(data=None)
    service = TenantService(db)
    tenant = await service.get_by_slug(tenant_slug)
    return success_response(data=TenantBrandingResponse.model_validate(tenant))


@router.post("/my/branding/logo", response_model=APIResponse[TenantBrandingResponse])
async def upload_logo(
    request: Request,
    logo: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload tenant logo. Company admin only."""
    from src.apps.tenancy.service import TenantService
    from src.apps.identity.models import OrganizationMember, UserRole
    from sqlalchemy import select, and_

    tenant_slug = getattr(request.state, "tenant_slug", None)
    if not tenant_slug:
        raise ForbiddenError("Tenant context required")

    service = TenantService(db)
    tenant = await service.get_by_slug(tenant_slug)

    if not current_user.is_superadmin:
        member_result = await db.execute(
            select(OrganizationMember).where(
                and_(
                    OrganizationMember.user_id == current_user.id,
                    OrganizationMember.tenant_id == tenant.id,
                    OrganizationMember.role == UserRole.COMPANY_ADMIN,
                    OrganizationMember.deleted_at.is_(None),
                )
            )
        )
        if not member_result.scalar_one_or_none():
            raise ForbiddenError("Company admin access required")

    try:
        url = await save_file(logo, subfolder=f"tenants/{tenant.id}/logo")
    except ValueError as e:
        from src.core.exceptions import ValidationError
        raise ValidationError(str(e))

    tenant.logo_url = url
    await db.flush()
    await db.commit()
    return success_response(
        data=TenantBrandingResponse.model_validate(tenant),
        message="Logo uploaded successfully",
    )


@router.patch("/my/branding/colors", response_model=APIResponse[TenantBrandingResponse])
async def update_colors(
    request: Request,
    data: UpdateBrandingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update brand colors. Company admin only."""
    from src.apps.tenancy.service import TenantService
    from src.apps.identity.models import OrganizationMember, UserRole
    from sqlalchemy import select, and_

    tenant_slug = getattr(request.state, "tenant_slug", None)
    if not tenant_slug:
        raise ForbiddenError("Tenant context required")

    service = TenantService(db)
    tenant = await service.get_by_slug(tenant_slug)

    if not current_user.is_superadmin:
        member_result = await db.execute(
            select(OrganizationMember).where(
                and_(
                    OrganizationMember.user_id == current_user.id,
                    OrganizationMember.tenant_id == tenant.id,
                    OrganizationMember.role == UserRole.COMPANY_ADMIN,
                    OrganizationMember.deleted_at.is_(None),
                )
            )
        )
        if not member_result.scalar_one_or_none():
            raise ForbiddenError("Company admin access required")

    if data.primary_color is not None:
        tenant.primary_color = data.primary_color
    if data.secondary_color is not None:
        tenant.secondary_color = data.secondary_color

    await db.flush()
    await db.commit()
    return success_response(
        data=TenantBrandingResponse.model_validate(tenant),
        message="Brand colors updated",
    )


# ── Tenant CRUD (must come AFTER /my/* routes) ───────────────────

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