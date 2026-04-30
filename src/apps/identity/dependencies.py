from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from src.core.database import get_db
from src.core.dependencies import get_current_user_id
from src.core.exceptions import UnauthorizedError, ForbiddenError
from src.apps.identity.models import User, UserRole, OrganizationMember


async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    from sqlalchemy import select, and_
    result = await db.execute(
        select(User).where(
            and_(User.id == user_id, User.deleted_at.is_(None))
        )
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


async def require_superadmin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superadmin:
        raise ForbiddenError("Super admin access required")
    return current_user


def require_roles(*roles: UserRole):
    async def checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> tuple[User, OrganizationMember]:
        # Superadmin bypasses all role checks
        if current_user.is_superadmin:
            return current_user, None

        # For tenant-scoped routes, check membership role
        # tenant_id comes from request state via TenantMiddleware
        # We'll wire this fully in the tenancy section
        return current_user, None
    return checker


# Type aliases
CurrentUser = Annotated[User, Depends(get_current_user)]
SuperAdmin = Annotated[User, Depends(require_superadmin)]