from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import CurrentUserID
from src.apps.identity.service import AuthService, UserManagementService
from src.apps.identity.schemas import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
    ChangePasswordRequest,
    UpdateProfileRequest,
    CreateUserRequest, 
    UpdateUserRequest,
    UserWithPermissionsResponse, 
    UserPermissionSchema,
)
from src.apps.identity.dependencies import CurrentUser
from src.shared.response import APIResponse, success_response
from src.apps.tenancy.service import TenantService
from src.apps.projects.dependencies import get_current_tenant
from src.apps.tenancy.models import Tenant
from src.core.exceptions import UnauthorizedError, ForbiddenError


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=APIResponse[UserResponse], status_code=201)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.register(data)
    return success_response(
        data=UserResponse.model_validate(user),
        message="Account created successfully",
    )


@router.post("/login", response_model=APIResponse[TokenResponse])
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    device_info = request.headers.get("User-Agent")
    ip = request.client.host if request.client else None
    tokens = await service.login(data, device_info=device_info, ip=ip)
    return success_response(data=tokens, message="Login successful")


@router.post("/refresh", response_model=APIResponse[TokenResponse])
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    tokens = await service.refresh(data.refresh_token)
    return success_response(data=tokens, message="Token refreshed")


@router.post("/logout", response_model=APIResponse[None])
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
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
        current_user.id,
        data.model_dump(exclude_none=True),
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
    return success_response(message="Password changed successfully")

# Add a second router for user management
user_router = APIRouter(prefix="/users", tags=["User Management"])


async def get_user_mgmt_service(
    current_user: CurrentUser,
    tenant: "Tenant" = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> UserManagementService:
    
    # Only company_admin or superadmin can manage users
    if not current_user.is_superadmin:
        # Check if user is company_admin for this tenant
        from src.apps.identity.models import OrganizationMember, UserRole
        from sqlalchemy import select, and_
        result = await db.execute(
            select(OrganizationMember).where(
                and_(
                    OrganizationMember.user_id == current_user.id,
                    OrganizationMember.tenant_id == tenant.id,
                    OrganizationMember.role == UserRole.COMPANY_ADMIN,
                    OrganizationMember.deleted_at.is_(None),
                )
            )
        )
        if not result.scalar_one_or_none():
            raise ForbiddenError("Company admin access required")
    return UserManagementService(
        db=db, tenant_id=tenant.id, acting_user_id=current_user.id
    )


@user_router.post("", response_model=APIResponse[UserWithPermissionsResponse], status_code=201)
async def create_user(
    data: CreateUserRequest,
    svc: UserManagementService = Depends(get_user_mgmt_service),
    tenant: "Tenant" = Depends(get_current_tenant),
):
    user, _ = await svc.create_user(
        tenant_slug=tenant.slug,
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
    svc: UserManagementService = Depends(get_user_mgmt_service),
):
    users = await svc.list_users()
    return success_response(
        data=[UserWithPermissionsResponse(**u) for u in users]
    )


@user_router.get("/me/permissions", response_model=APIResponse[UserPermissionSchema])
async def get_my_permissions(
    current_user: CurrentUser,
    tenant: "Tenant" = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Returns the current user's module permissions for the current tenant."""
    svc = UserManagementService(
        db=db, tenant_id=tenant.id, acting_user_id=current_user.id
    )
    perms = await svc.get_my_permissions(current_user.id)

    if current_user.is_superadmin or (perms is None):
        # Superadmin or company admin gets everything
        from src.apps.identity.schemas import ROLE_DEFAULT_PERMISSIONS
        from src.apps.identity.models import UserRole
        all_perms = ROLE_DEFAULT_PERMISSIONS[UserRole.COMPANY_ADMIN]
        return success_response(data=UserPermissionSchema(**all_perms))

    return success_response(data=UserPermissionSchema.model_validate(perms))


@user_router.get("/{user_id}", response_model=APIResponse[UserWithPermissionsResponse])
async def get_user(
    user_id: str,
    svc: UserManagementService = Depends(get_user_mgmt_service),
):
    user_data = await svc.get_user(user_id)
    return success_response(data=UserWithPermissionsResponse(**user_data))


@user_router.patch("/{user_id}", response_model=APIResponse[UserWithPermissionsResponse])
async def update_user(
    user_id: str,
    data: UpdateUserRequest,
    svc: UserManagementService = Depends(get_user_mgmt_service),
):
    user_data = await svc.update_user(user_id, data)
    return success_response(
        data=UserWithPermissionsResponse(**user_data),
        message="User updated",
    )


@user_router.put("/{user_id}/permissions", response_model=APIResponse[UserPermissionSchema])
async def update_permissions(
    user_id: str,
    data: UserPermissionSchema,
    svc: UserManagementService = Depends(get_user_mgmt_service),
):
    perms = await svc.update_permissions(user_id, data)
    return success_response(
        data=UserPermissionSchema.model_validate(perms),
        message="Permissions updated",
    )


@user_router.post("/{user_id}/deactivate", response_model=APIResponse[None])
async def deactivate_user(
    user_id: str,
    svc: UserManagementService = Depends(get_user_mgmt_service),
):
    await svc.deactivate_user(user_id)
    return success_response(message="User deactivated")


@user_router.post("/{user_id}/reset-password", response_model=APIResponse[None])
async def reset_password(
    user_id: str,
    svc: UserManagementService = Depends(get_user_mgmt_service),
    tenant: "Tenant" = Depends(get_current_tenant),
):
    await svc.reset_user_password(
        user_id=user_id,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
    )
    return success_response(message="Password reset. New credentials sent to user's email")