from fastapi import APIRouter, Depends, Request, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.exceptions import ForbiddenError
from src.core.rate_limit import limiter
from src.apps.identity.service import AuthService
from src.apps.identity.user_management import UserManagementService
from src.apps.identity.schemas import (
    RegisterRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserResponse, ChangePasswordRequest,
    UpdateProfileRequest, CreateUserRequest, UpdateUserRequest,
    UserWithPermissionsResponse, UserPermissionSchema,
)
from src.apps.identity.dependencies import CurrentUser, SuperAdmin, get_current_user
from src.apps.identity.models import User, OrganizationMember, UserRole
from src.shared.response import APIResponse, success_response
from src.core.storage import save_file

# ── Auth router ───────────────────────────────────────────────────
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=APIResponse[UserResponse], status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    user = await service.register(data)
    return success_response(
        data=UserResponse.model_validate(user),
        message="Account created successfully",
    )


@router.post("/login", response_model=APIResponse[TokenResponse])
@limiter.limit("10/minute")
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    device_info = request.headers.get("User-Agent")
    ip = request.client.host if request.client else None
    # Pass tenant slug from header/state so login validates membership
    tenant_slug = getattr(request.state, "tenant_slug", None)
    tokens = await service.login(
        data,
        device_info=device_info,
        ip=ip,
        tenant_slug=tenant_slug,
    )
    return success_response(data=tokens, message="Login successful")


@router.post("/refresh", response_model=APIResponse[TokenResponse])
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    tokens = await service.refresh(data.refresh_token)
    return success_response(data=tokens, message="Token refreshed")


@router.post("/logout", response_model=APIResponse[None])
async def logout(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    await service.logout(data.refresh_token)
    return success_response(message="Logged out successfully")


@router.get("/me", response_model=APIResponse[UserResponse])
async def get_me(current_user: CurrentUser):
    return success_response(data=UserResponse.model_validate(current_user))


@router.patch("/me", response_model=APIResponse[UserResponse])
async def update_profile(
    data: UpdateProfileRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    updated = await service.update_profile(
        current_user.id, data.model_dump(exclude_none=True)
    )
    return success_response(
        data=UserResponse.model_validate(updated),
        message="Profile updated",
    )


@router.post("/change-password", response_model=APIResponse[None])
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    await service.change_password(
        current_user.id, data.current_password, data.new_password
    )
    # Clear must_change_password flag
    current_user.must_change_password = False
    await db.flush()
    return success_response(message="Password changed successfully")


# ── User management router ────────────────────────────────────────
user_router = APIRouter(prefix="/users", tags=["User Management"])


async def _require_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> tuple[User, str, str]:
    """
    Returns (current_user, tenant_id, tenant_slug).
    Allows superadmin or company_admin only.
    """
    from sqlalchemy import select, and_
    from src.apps.tenancy.models import Tenant

    if current_user.is_superadmin:
        # Superadmin must still pass a tenant slug to scope the operation
        tenant_slug = getattr(request.state, "tenant_slug", None)
        if not tenant_slug:
            raise ForbiddenError("Tenant slug required in X-Tenant-Slug header")
        tenant_result = await db.execute(
            select(Tenant).where(
                and_(Tenant.slug == tenant_slug, Tenant.deleted_at.is_(None))
            )
        )
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise ForbiddenError("Tenant not found")
        return current_user, tenant.id, tenant.slug

    # Non-superadmin: must be company_admin
    tenant_slug = getattr(request.state, "tenant_slug", None)
    if not tenant_slug:
        raise ForbiddenError("Tenant slug required")

    from src.apps.tenancy.models import Tenant
    tenant_result = await db.execute(
        select(Tenant).where(
            and_(Tenant.slug == tenant_slug, Tenant.is_active.is_(True))
        )
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise ForbiddenError("Tenant not found")

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
        raise ForbiddenError("Company admin access required to manage users")

    return current_user, tenant.id, tenant.slug


@user_router.post("", response_model=APIResponse[UserWithPermissionsResponse], status_code=201)
async def create_user(
    data: CreateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acting_user, tenant_id, tenant_slug = await _require_admin(
        current_user, db, request
    )
    from src.apps.tenancy.models import Tenant
    from sqlalchemy import select, and_
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = tenant_result.scalar_one()

    svc = UserManagementService(
        db=db, tenant_id=tenant_id, acting_user_id=acting_user.id
    )
    user, _ = await svc.create_user(
        tenant_slug=tenant_slug,
        tenant_name=tenant.name,
        data=data,
    )
    user_data = await svc.get_user(user.id)
    return success_response(
        data=UserWithPermissionsResponse(**user_data),
        message=f"User created. Credentials sent to {data.email}",
    )


@user_router.get("", response_model=APIResponse[list[UserWithPermissionsResponse]])
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acting_user, tenant_id, _ = await _require_admin(current_user, db, request)
    svc = UserManagementService(
        db=db, tenant_id=tenant_id, acting_user_id=acting_user.id
    )
    users = await svc.list_users()
    return success_response(
        data=[UserWithPermissionsResponse(**u) for u in users]
    )


@user_router.get("/me/permissions", response_model=APIResponse[UserPermissionSchema])
async def get_my_permissions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the current user's module permissions for the current tenant."""
    from src.apps.tenancy.models import Tenant
    from sqlalchemy import select, and_

    tenant_slug = getattr(request.state, "tenant_slug", None)
    if not tenant_slug:
        # No tenant context — return full access (e.g. superadmin without tenant)
        return success_response(data=UserPermissionSchema(
            can_projects=True, can_boq=True, can_procurement=True,
            can_inventory=True, can_site_ops=True, can_finance=True,
            can_quality=True, can_documents=True, can_subcontractors=True,
        ))

    tenant_result = await db.execute(
        select(Tenant).where(
            and_(Tenant.slug == tenant_slug, Tenant.is_active.is_(True))
        )
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        return success_response(data=UserPermissionSchema(
            can_projects=True, can_boq=True, can_procurement=True,
            can_inventory=True, can_site_ops=True, can_finance=True,
            can_quality=True, can_documents=True, can_subcontractors=True,
        ))

    # Superadmin and company_admin get everything
    if current_user.is_superadmin:
        return success_response(data=UserPermissionSchema(
            can_projects=True, can_boq=True, can_procurement=True,
            can_inventory=True, can_site_ops=True, can_finance=True,
            can_quality=True, can_documents=True, can_subcontractors=True,
        ))

    # Check if company_admin
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
    if member_result.scalar_one_or_none():
        return success_response(data=UserPermissionSchema(
            can_projects=True, can_boq=True, can_procurement=True,
            can_inventory=True, can_site_ops=True, can_finance=True,
            can_quality=True, can_documents=True, can_subcontractors=True,
        ))

    svc = UserManagementService(
        db=db, tenant_id=tenant.id, acting_user_id=current_user.id
    )
    perms = await svc.get_my_permissions(current_user.id)
    if not perms:
        # User exists in org but no permissions row — give minimal access
        return success_response(data=UserPermissionSchema(
            can_projects=True, can_boq=False, can_procurement=False,
            can_inventory=False, can_site_ops=False, can_finance=False,
            can_quality=False, can_documents=False, can_subcontractors=False,
        ))

    return success_response(data=UserPermissionSchema.model_validate(perms))


@user_router.get("/{user_id}", response_model=APIResponse[UserWithPermissionsResponse])
async def get_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acting_user, tenant_id, _ = await _require_admin(current_user, db, request)
    svc = UserManagementService(
        db=db, tenant_id=tenant_id, acting_user_id=acting_user.id
    )
    user_data = await svc.get_user(user_id)
    return success_response(data=UserWithPermissionsResponse(**user_data))


@user_router.patch("/{user_id}", response_model=APIResponse[UserWithPermissionsResponse])
async def update_user(
    user_id: str,
    data: UpdateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acting_user, tenant_id, _ = await _require_admin(current_user, db, request)
    svc = UserManagementService(
        db=db, tenant_id=tenant_id, acting_user_id=acting_user.id
    )
    user_data = await svc.update_user(user_id, data)
    return success_response(
        data=UserWithPermissionsResponse(**user_data),
        message="User updated",
    )


@user_router.put("/{user_id}/permissions", response_model=APIResponse[UserPermissionSchema])
async def update_permissions(
    user_id: str,
    data: UserPermissionSchema,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acting_user, tenant_id, _ = await _require_admin(current_user, db, request)
    svc = UserManagementService(
        db=db, tenant_id=tenant_id, acting_user_id=acting_user.id
    )
    perms = await svc.update_permissions(user_id, data)
    return success_response(
        data=UserPermissionSchema.model_validate(perms),
        message="Permissions updated",
    )


@user_router.post("/{user_id}/deactivate", response_model=APIResponse[None])
async def deactivate_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acting_user, tenant_id, _ = await _require_admin(current_user, db, request)
    svc = UserManagementService(
        db=db, tenant_id=tenant_id, acting_user_id=acting_user.id
    )
    await svc.deactivate_user(user_id)
    return success_response(message="User deactivated")


@user_router.post("/{user_id}/reset-password", response_model=APIResponse[None])
async def reset_password(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acting_user, tenant_id, tenant_slug = await _require_admin(
        current_user, db, request
    )
    from src.apps.tenancy.models import Tenant
    from sqlalchemy import select
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = tenant_result.scalar_one()

    svc = UserManagementService(
        db=db, tenant_id=tenant_id, acting_user_id=acting_user.id
    )
    await svc.reset_user_password(
        user_id=user_id,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
    )
    return success_response(
        message="Password reset. New credentials sent to user's email"
    )

@user_router.post("/me/avatar", response_model=APIResponse[UserResponse])
async def upload_avatar(
    avatar: UploadFile,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    try:
        url = await save_file(avatar, subfolder=f"avatars/{current_user.id}")
    except ValueError as e:
        from src.core.exceptions import ValidationError
        raise ValidationError(str(e))

    current_user.avatar_url = url
    await db.flush()
    await db.commit()
    return success_response(
        data=UserResponse.model_validate(current_user),
        message="Avatar updated",
    )
