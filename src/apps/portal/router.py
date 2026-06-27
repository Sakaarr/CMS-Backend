from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.portal.service import PortalService
from src.apps.portal.schemas import (
    PortalLoginRequest, PortalLoginResponse, PortalRefreshRequest,
    PortalChangePasswordRequest, PortalUserResponse,
    CreatePortalUserRequest, UpdatePortalUserRequest,
    PortalDashboardResponse,
    PortalContractResponse, PortalBOQItemResponse,
    PortalCreateProgressRequest, PortalProgressResponse,
    PortalCertificateResponse, PortalCertificateDetailResponse,
    PortalNCRResponse, PortalNCRRespondRequest,
    PortalPunchItemResponse, PortalPunchRespondRequest,
    PortalSafetyObservationResponse,
    PortalComplianceDocResponse,
    PortalPaymentResponse,
    PortalNotificationResponse,
)
from src.apps.portal.models import SubcontractorUser, SubcontractorPortalRole
from src.apps.portal.dependencies import get_portal_user
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response
from src.core.exceptions import ForbiddenError
from src.core.dependencies import require_module

router = APIRouter(tags=["Subcontractor Portal"])


async def get_svc(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> PortalService:
    return PortalService(db=db, tenant_id=tenant.id)


# ── Admin Bootstrap (main-identity users create portal users) ─────

@router.post(
    "/portal/admin/users",
    response_model=APIResponse[PortalUserResponse],
    status_code=201,
)
async def admin_create_portal_user(
    data: CreatePortalUserRequest,
    subcontractor_id: str = Query(..., description="Subcontractor ID to link this user to"),
    _: User = Depends(require_module("subcontractors")),
    svc: PortalService = Depends(get_svc),
):
    portal_user = await svc.create_portal_user(subcontractor_id, data)
    return success_response(
        data=PortalUserResponse.model_validate(portal_user),
        message="Portal user created",
    )


def _require_role(*roles: SubcontractorPortalRole):
    """Dependency factory: raises ForbiddenError if user's role not in allowed list."""
    async def checker(user: SubcontractorUser = Depends(get_portal_user)):
        if user.role not in roles:
            raise ForbiddenError("Insufficient permissions")
        return user
    return checker


# ── Auth Endpoints (no portal user required) ──────────────────────

@router.post("/portal/auth/login", response_model=APIResponse[PortalLoginResponse])
async def portal_login(
    data: PortalLoginRequest,
    svc: PortalService = Depends(get_svc),
):
    result = await svc.login(data.email, data.password)
    return success_response(data=PortalLoginResponse(**result))


@router.post("/portal/auth/refresh", response_model=APIResponse[dict])
async def portal_refresh(
    data: PortalRefreshRequest,
    svc: PortalService = Depends(get_svc),
):
    result = await svc.refresh_token(data.refresh_token)
    return success_response(data=result)


@router.post("/portal/auth/change-password", response_model=APIResponse[None])
async def portal_change_password(
    data: PortalChangePasswordRequest,
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    await svc.change_password(user.id, data.current_password, data.new_password)
    return success_response(message="Password changed")


@router.get("/portal/auth/me", response_model=APIResponse[PortalUserResponse])
async def portal_me(
    user: SubcontractorUser = Depends(get_portal_user),
):
    return success_response(data=PortalUserResponse.model_validate(user))


# ── Portal User Management (Manager only) ────────────────────────

@router.post("/portal/users", response_model=APIResponse[PortalUserResponse], status_code=201)
async def create_portal_user(
    data: CreatePortalUserRequest,
    user: SubcontractorUser = Depends(_require_role(SubcontractorPortalRole.MANAGER)),
    svc: PortalService = Depends(get_svc),
):
    portal_user = await svc.create_portal_user(user.subcontractor_id, data)
    return success_response(
        data=PortalUserResponse.model_validate(portal_user),
        message="Portal user created",
    )


@router.get("/portal/users", response_model=PaginatedResponse[PortalUserResponse])
async def list_portal_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(_require_role(SubcontractorPortalRole.MANAGER)),
    svc: PortalService = Depends(get_svc),
):
    users = await svc.list_portal_users(user.subcontractor_id)
    total = len(users)
    skip = (page - 1) * page_size
    paged = users[skip:skip + page_size]
    return paginated_response(
        data=[PortalUserResponse.model_validate(u) for u in paged],
        total=total, page=page, page_size=page_size,
    )


@router.patch("/portal/users/{user_id}", response_model=APIResponse[PortalUserResponse])
async def update_portal_user(
    user_id: str,
    data: UpdatePortalUserRequest,
    current_user: SubcontractorUser = Depends(_require_role(SubcontractorPortalRole.MANAGER)),
    svc: PortalService = Depends(get_svc),
):
    portal_user = await svc.update_portal_user(user_id, data)
    return success_response(data=PortalUserResponse.model_validate(portal_user))


@router.post("/portal/users/{user_id}/reset-password", response_model=APIResponse[dict])
async def reset_portal_user_password(
    user_id: str,
    current_user: SubcontractorUser = Depends(_require_role(SubcontractorPortalRole.MANAGER)),
    svc: PortalService = Depends(get_svc),
):
    temp = await svc.reset_portal_user_password(user_id)
    return success_response(data={"temporary_password": temp})


# ── Dashboard ─────────────────────────────────────────────────────

@router.get("/portal/dashboard", response_model=APIResponse[PortalDashboardResponse])
async def portal_dashboard(
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    data = await svc.get_dashboard(user.subcontractor_id)
    return success_response(data=PortalDashboardResponse(**data))


# ── Contracts ─────────────────────────────────────────────────────

@router.get("/portal/contracts", response_model=PaginatedResponse[PortalContractResponse])
async def portal_list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    contracts = await svc.list_contracts(user.subcontractor_id)
    total = len(contracts)
    skip = (page - 1) * page_size
    paged = contracts[skip:skip + page_size]
    return paginated_response(
        data=[PortalContractResponse(**c) for c in paged],
        total=total, page=page, page_size=page_size,
    )


@router.get("/portal/contracts/{contract_id}/boq-items", response_model=PaginatedResponse[PortalBOQItemResponse])
async def portal_list_boq_items(
    contract_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    items = await svc.list_boq_items(contract_id, user.subcontractor_id)
    total = len(items)
    skip = (page - 1) * page_size
    paged = items[skip:skip + page_size]
    return paginated_response(
        data=[PortalBOQItemResponse(**i) for i in paged],
        total=total, page=page, page_size=page_size,
    )


# ── Progress ──────────────────────────────────────────────────────

@router.post("/portal/progress", response_model=APIResponse[PortalProgressResponse], status_code=201)
async def portal_create_progress(
    data: PortalCreateProgressRequest,
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    entry = await svc.create_progress(user.subcontractor_id, user.id, data)
    return success_response(
        data=PortalProgressResponse.model_validate(entry),
        message="Progress entry created",
    )


@router.get("/portal/progress", response_model=PaginatedResponse[PortalProgressResponse])
async def portal_list_progress(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_progress(
        user.subcontractor_id, status=status, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[PortalProgressResponse(**i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/portal/progress/{entry_id}/submit", response_model=APIResponse[PortalProgressResponse])
async def portal_submit_progress(
    entry_id: str,
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    entry = await svc.submit_progress(entry_id, user.subcontractor_id)
    return success_response(
        data=PortalProgressResponse.model_validate(entry),
        message="Progress submitted",
    )


# ── Certificates ──────────────────────────────────────────────────

@router.get("/portal/certificates", response_model=PaginatedResponse[PortalCertificateResponse])
async def portal_list_certificates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_certificates(
        user.subcontractor_id, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[PortalCertificateResponse(**i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/portal/certificates/{cert_id}", response_model=APIResponse[PortalCertificateDetailResponse])
async def portal_get_certificate(
    cert_id: str,
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    cert = await svc.get_certificate(cert_id, user.subcontractor_id)
    if not cert:
        from src.core.exceptions import NotFoundError
        raise NotFoundError("Certificate")
    return success_response(data=PortalCertificateDetailResponse(**cert))


# ── Quality - NCRs ────────────────────────────────────────────────

@router.get("/portal/quality/ncrs", response_model=PaginatedResponse[PortalNCRResponse])
async def portal_list_ncrs(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_ncrs(
        user.subcontractor_id, status=status, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[PortalNCRResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/portal/quality/ncrs/{ncr_id}/respond", response_model=APIResponse[PortalNCRResponse])
async def portal_respond_ncr(
    ncr_id: str,
    data: PortalNCRRespondRequest,
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    ncr = await svc.respond_to_ncr(
        ncr_id, user.subcontractor_id,
        data.root_cause, data.corrective_action, data.preventive_action,
    )
    return success_response(
        data=PortalNCRResponse.model_validate(ncr),
        message="NCR response submitted",
    )


# ── Quality - Punch List ──────────────────────────────────────────

@router.get("/portal/quality/punch-items", response_model=PaginatedResponse[PortalPunchItemResponse])
async def portal_list_punch_items(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_punch_items(
        user.subcontractor_id, status=status, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[PortalPunchItemResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/portal/quality/punch-items/{item_id}/respond", response_model=APIResponse[PortalPunchItemResponse])
async def portal_respond_punch_item(
    item_id: str,
    data: PortalPunchRespondRequest,
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    item = await svc.respond_to_punch_item(
        item_id, user.subcontractor_id, data.remarks, data.status,
    )
    return success_response(
        data=PortalPunchItemResponse.model_validate(item),
        message="Punch item response submitted",
    )


# ── Quality - Safety Observations ─────────────────────────────────

@router.get("/portal/quality/safety-observations", response_model=PaginatedResponse[PortalSafetyObservationResponse])
async def portal_list_safety_observations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_safety_observations(
        user.subcontractor_id, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[PortalSafetyObservationResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


# ── Compliance Documents ──────────────────────────────────────────

@router.get("/portal/compliance-docs", response_model=PaginatedResponse[PortalComplianceDocResponse])
async def portal_list_compliance_docs(
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_compliance_docs(
        user.subcontractor_id, category=category, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[PortalComplianceDocResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


# ── Payments ──────────────────────────────────────────────────────

@router.get("/portal/payments", response_model=PaginatedResponse[PortalPaymentResponse])
async def portal_list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_payments(
        user.subcontractor_id, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[PortalPaymentResponse(**i) for i in items],
        total=total, page=page, page_size=page_size,
    )


# ── Notifications ─────────────────────────────────────────────────

@router.get("/portal/notifications", response_model=PaginatedResponse[PortalNotificationResponse])
async def portal_list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_notifications(
        user.id, unread_only=unread_only, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[PortalNotificationResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/portal/notifications/{notif_id}/read", response_model=APIResponse[PortalNotificationResponse])
async def portal_mark_notification_read(
    notif_id: str,
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    notif = await svc.mark_notification_read(notif_id, user.id)
    return success_response(data=PortalNotificationResponse.model_validate(notif))


@router.post("/portal/notifications/read-all", response_model=APIResponse[dict])
async def portal_mark_all_notifications_read(
    user: SubcontractorUser = Depends(get_portal_user),
    svc: PortalService = Depends(get_svc),
):
    count = await svc.mark_all_notifications_read(user.id)
    return success_response(data={"marked_read": count})
