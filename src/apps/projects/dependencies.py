from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.service import TenantService
from src.apps.tenancy.models import Tenant
from src.core.exceptions import TenantNotFoundError


async def get_current_tenant(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    Resolves the tenant from request state (set by TenantMiddleware).
    Superadmins can also pass ?tenant_slug= query param.
    """
    slug = getattr(request.state, "tenant_slug", None)
    if not slug:
        slug = request.query_params.get("tenant_slug")
    if not slug:
        raise TenantNotFoundError()

    service = TenantService(db)
    return await service.get_by_slug(slug)


async def get_project_service(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from src.apps.projects.service import ProjectService
    return ProjectService(db=db, tenant_id=tenant.id, user_id=current_user.id)