from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.dashboard.service import DashboardService
from src.shared.response import APIResponse, success_response

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> DashboardService:
    return DashboardService(db=db, tenant_id=tenant.id, user_id=current_user.id)


@router.get("/overview", response_model=APIResponse[dict])
async def dashboard_overview(svc: DashboardService = Depends(get_svc)):
    data = await svc.get_overview()
    return success_response(data=data)


@router.get("/projects/{project_id}", response_model=APIResponse[dict])
async def project_dashboard(project_id: str, svc: DashboardService = Depends(get_svc)):
    data = await svc.get_project_dashboard(project_id)
    return success_response(data=data)
