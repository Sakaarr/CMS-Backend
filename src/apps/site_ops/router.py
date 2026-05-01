from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.site_ops.service import SiteOpsService
from src.apps.site_ops.schemas import (
    CreateDPRRequest, UpdateDPRRequest, DPRResponse, DPRSummary
)
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response

router = APIRouter(tags=["Site Operations"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> SiteOpsService:
    return SiteOpsService(db=db, tenant_id=tenant.id, user_id=current_user.id)


@router.post("/projects/{project_id}/dprs", response_model=APIResponse[DPRResponse], status_code=201)
async def create_dpr(project_id: str, data: CreateDPRRequest, svc: SiteOpsService = Depends(get_svc)):
    dpr = await svc.create_dpr(project_id, data)
    return success_response(data=DPRResponse.model_validate(dpr), message="DPR created")


@router.get("/projects/{project_id}/dprs", response_model=PaginatedResponse[DPRSummary])
async def list_dprs(
    project_id: str,
    site_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    svc: SiteOpsService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    dprs, total = await svc.list_dprs(project_id, site_id=site_id, skip=skip, limit=page_size)
    return paginated_response(
        data=[DPRSummary.model_validate(d) for d in dprs],
        total=total, page=page, page_size=page_size,
    )


@router.get("/dprs/{dpr_id}", response_model=APIResponse[DPRResponse])
async def get_dpr(dpr_id: str, svc: SiteOpsService = Depends(get_svc)):
    dpr = await svc.get_dpr(dpr_id)
    return success_response(data=DPRResponse.model_validate(dpr))


@router.patch("/dprs/{dpr_id}", response_model=APIResponse[DPRResponse])
async def update_dpr(dpr_id: str, data: UpdateDPRRequest, svc: SiteOpsService = Depends(get_svc)):
    dpr = await svc.update_dpr(dpr_id, data)
    return success_response(data=DPRResponse.model_validate(dpr), message="DPR updated")


@router.post("/dprs/{dpr_id}/submit", response_model=APIResponse[DPRResponse])
async def submit_dpr(dpr_id: str, svc: SiteOpsService = Depends(get_svc)):
    dpr = await svc.submit_dpr(dpr_id)
    return success_response(data=DPRResponse.model_validate(dpr), message="DPR submitted")


@router.get("/projects/{project_id}/site-ops-summary", response_model=APIResponse[dict])
async def site_ops_summary(project_id: str, svc: SiteOpsService = Depends(get_svc)):
    summary = await svc.get_site_ops_summary(project_id)
    return success_response(data=summary)