from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.approvals.schemas import ApprovalInboxResponse
from src.apps.approvals.service import ApprovalInboxService
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import OrganizationMember, User, UserRole
from src.apps.identity.schemas import UserPermissionSchema
from src.apps.identity.user_management import UserManagementService
from src.apps.tenancy.service import TenantService
from src.core.database import get_db
from src.core.exceptions import TenantNotFoundError
from src.shared.response import APIResponse, success_response

router = APIRouter(prefix="/approvals", tags=["Approvals"])


def _full_access_permissions() -> UserPermissionSchema:
    return UserPermissionSchema(
        can_projects=True,
        can_boq=True,
        can_procurement=True,
        can_inventory=True,
        can_site_ops=True,
        can_finance=True,
        can_quality=True,
        can_documents=True,
        can_subcontractors=True,
    )


async def _resolve_permissions(
    request: Request,
    current_user: User,
    db: AsyncSession,
) -> tuple[str | None, UserPermissionSchema | None]:
    tenant_slug = getattr(request.state, "tenant_slug", None)
    if not tenant_slug:
        if current_user.is_superadmin:
            return None, None
        raise TenantNotFoundError()

    tenant = await TenantService(db).get_by_slug(tenant_slug)
    if current_user.is_superadmin:
        return tenant.id, _full_access_permissions()

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
        return tenant.id, _full_access_permissions()

    svc = UserManagementService(
        db=db,
        tenant_id=tenant.id,
        acting_user_id=current_user.id,
    )
    perms = await svc.get_my_permissions(current_user.id)
    if not perms:
        perms = UserPermissionSchema(
            can_projects=True,
            can_boq=False,
            can_procurement=False,
            can_inventory=False,
            can_site_ops=False,
            can_finance=False,
            can_quality=False,
            can_documents=False,
            can_subcontractors=False,
        )
    return tenant.id, UserPermissionSchema.model_validate(perms)


@router.get("/inbox", response_model=APIResponse[ApprovalInboxResponse])
async def get_inbox(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
):
    tenant_id, perms = await _resolve_permissions(request, current_user, db)

    # Superadmin without tenant context → empty inbox
    if not tenant_id or not perms:
        empty = ApprovalInboxResponse(
            items=[], total=0, counts={},
        )
        return success_response(data=empty.model_dump())

    allowed_modules: set[str] = set()
    if perms.can_finance:
        allowed_modules.add("finance")
    if perms.can_procurement:
        allowed_modules.add("procurement")
    if perms.can_inventory:
        allowed_modules.add("inventory")
    if perms.can_boq:
        allowed_modules.add("boq")
    if perms.can_documents:
        allowed_modules.add("documents")

    service = ApprovalInboxService(
        db=db,
        tenant_id=tenant_id,
        user_id=current_user.id,
    )
    inbox = await service.get_inbox(allowed_modules=allowed_modules, limit=limit)
    return success_response(data=ApprovalInboxResponse.model_validate(inbox))
