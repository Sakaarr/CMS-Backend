from typing import Annotated
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.security import decode_token
from src.core.exceptions import UnauthorizedError, ForbiddenError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.apps.identity.models import User as UserModel
from sqlalchemy import select, and_

security = HTTPBearer()


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> str:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedError("Invalid token payload")
        return user_id
    except ValueError:
        raise UnauthorizedError("Invalid or expired token")


class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, roles: list[str]) -> bool:
        for role in roles:
            if role in self.allowed_roles:
                return True
        raise ForbiddenError(
            f"Required roles: {', '.join(self.allowed_roles)}"
        )


# Type aliases for cleaner route signatures
DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUserID = Annotated[str, Depends(get_current_user_id)]


from src.apps.identity.models import UserPermission

MODULE_PERMISSION_MAP = {
    "projects": "can_projects",
    "boq": "can_boq",
    "procurement": "can_procurement",
    "inventory": "can_inventory",
    "site_ops": "can_site_ops",
    "finance": "can_finance",
    "quality": "can_quality",
    "documents": "can_documents",
}


def require_module(module: str):
    """
    Dependency factory that checks if current user has access to a module.
    Usage: Depends(require_module("finance"))
    """
    async def checker(
        current_user: UserModel = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        request: Request = None,
    ):
        

        # Fetch full user
        user_result = await db.execute(
            select(UserModel).where(UserModel.id == current_user)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise UnauthorizedError()

        # Superadmin bypasses all permission checks
        if user.is_superadmin:
            return user

        # Get tenant from request state
        tenant_slug = getattr(request.state, "tenant_slug", None)
        if not tenant_slug:
            raise UnauthorizedError("Tenant context required")

        from src.apps.tenancy.models import Tenant
        from src.apps.identity.models import OrganizationMember, UserRole

        # Get tenant
        tenant_result = await db.execute(
            select(Tenant).where(
                and_(Tenant.slug == tenant_slug, Tenant.is_active.is_(True))
            )
        )
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise UnauthorizedError("Invalid tenant")

        # Company admin bypasses module checks
        member_result = await db.execute(
            select(OrganizationMember).where(
                and_(
                    OrganizationMember.user_id == user.id,
                    OrganizationMember.tenant_id == tenant.id,
                    OrganizationMember.deleted_at.is_(None),
                )
            )
        )
        member = member_result.scalar_one_or_none()
        if member and member.role == UserRole.COMPANY_ADMIN:
            return user

        # Check module permission
        perm_field = MODULE_PERMISSION_MAP.get(module)
        if not perm_field:
            return user  # unknown module, allow by default

        perm_result = await db.execute(
            select(UserPermission).where(
                and_(
                    UserPermission.user_id == user.id,
                    UserPermission.tenant_id == tenant.id,
                    UserPermission.deleted_at.is_(None),
                )
            )
        )
        perms = perm_result.scalar_one_or_none()

        if not perms or not getattr(perms, perm_field, False):
            raise ForbiddenError(
                f"You do not have access to the {module} module"
            )

        return user

    return checker