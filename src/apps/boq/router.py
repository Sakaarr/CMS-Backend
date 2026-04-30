from fastapi import APIRouter, Depends, Query
from src.apps.boq.service import BOQService
from src.apps.boq.schemas import (
    CreateCostCodeRequest, UpdateCostCodeRequest, CostCodeResponse,
    CreateBudgetVersionRequest, UpdateBudgetVersionRequest, BudgetVersionResponse,
    CreateBOQItemRequest, UpdateBOQItemRequest, BOQItemResponse,
    CreateRateAnalysisRequest, RateAnalysisResponse,
)
from src.apps.boq.models import CostCodeCategory
from src.apps.projects.dependencies import get_project_service, get_current_tenant
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.shared.response import APIResponse, success_response

router = APIRouter(tags=["BOQ & Estimation"])


async def get_boq_service(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> BOQService:
    return BOQService(db=db, tenant_id=tenant.id, user_id=current_user.id)


# ── Cost Codes ────────────────────────────────────────────────────

@router.post("/cost-codes", response_model=APIResponse[CostCodeResponse], status_code=201)
async def create_cost_code(data: CreateCostCodeRequest, svc: BOQService = Depends(get_boq_service)):
    cc = await svc.create_cost_code(data)
    return success_response(data=CostCodeResponse.model_validate(cc), message="Cost code created")


@router.get("/cost-codes", response_model=APIResponse[list[CostCodeResponse]])
async def list_cost_codes(
    category: CostCodeCategory | None = Query(None),
    search: str | None = Query(None),
    svc: BOQService = Depends(get_boq_service),
):
    codes = await svc.list_cost_codes(category=category, search=search)
    return success_response(data=[CostCodeResponse.model_validate(c) for c in codes])


@router.patch("/cost-codes/{cost_code_id}", response_model=APIResponse[CostCodeResponse])
async def update_cost_code(
    cost_code_id: str, data: UpdateCostCodeRequest, svc: BOQService = Depends(get_boq_service)
):
    cc = await svc.update_cost_code(cost_code_id, data)
    return success_response(data=CostCodeResponse.model_validate(cc))


# ── Rate Analysis ─────────────────────────────────────────────────

@router.post("/rate-analysis", response_model=APIResponse[RateAnalysisResponse], status_code=201)
async def create_rate_analysis(
    data: CreateRateAnalysisRequest, svc: BOQService = Depends(get_boq_service)
):
    ra = await svc.create_rate_analysis(data)
    return success_response(data=RateAnalysisResponse.model_validate(ra), message="Rate analysis created")


@router.get("/cost-codes/{cost_code_id}/rate-analysis", response_model=APIResponse[list[RateAnalysisResponse]])
async def list_rate_analyses(
    cost_code_id: str, svc: BOQService = Depends(get_boq_service)
):
    analyses = await svc.list_rate_analyses(cost_code_id)
    return success_response(data=[RateAnalysisResponse.model_validate(r) for r in analyses])


# ── Budget Versions ───────────────────────────────────────────────

@router.post("/projects/{project_id}/budget-versions", response_model=APIResponse[BudgetVersionResponse], status_code=201)
async def create_budget_version(
    project_id: str, data: CreateBudgetVersionRequest, svc: BOQService = Depends(get_boq_service)
):
    bv = await svc.create_budget_version(project_id, data)
    return success_response(data=BudgetVersionResponse.model_validate(bv), message="Budget version created")


@router.get("/projects/{project_id}/budget-versions", response_model=APIResponse[list[BudgetVersionResponse]])
async def list_budget_versions(project_id: str, svc: BOQService = Depends(get_boq_service)):
    versions = await svc.list_budget_versions(project_id)
    return success_response(data=[BudgetVersionResponse.model_validate(v) for v in versions])


@router.post("/budget-versions/{version_id}/approve", response_model=APIResponse[BudgetVersionResponse])
async def approve_budget_version(version_id: str, svc: BOQService = Depends(get_boq_service)):
    bv = await svc.approve_budget_version(version_id)
    return success_response(data=BudgetVersionResponse.model_validate(bv), message="Budget approved")


@router.get("/budget-versions/{version_id}/summary", response_model=APIResponse[dict])
async def get_boq_summary(version_id: str, svc: BOQService = Depends(get_boq_service)):
    summary = await svc.get_boq_summary(version_id)
    return success_response(data=summary)


# ── BOQ Items ─────────────────────────────────────────────────────

@router.post("/projects/{project_id}/budget-versions/{version_id}/items",
    response_model=APIResponse[BOQItemResponse], status_code=201)
async def create_boq_item(
    project_id: str, version_id: str,
    data: CreateBOQItemRequest, svc: BOQService = Depends(get_boq_service)
):
    item = await svc.create_boq_item(project_id, version_id, data)
    return success_response(data=BOQItemResponse.model_validate(item), message="BOQ item created")


@router.get("/budget-versions/{version_id}/items", response_model=APIResponse[list[BOQItemResponse]])
async def list_boq_items(
    version_id: str,
    parent_id: str | None = Query(None),
    svc: BOQService = Depends(get_boq_service)
):
    items = await svc.list_boq_items(version_id, parent_id=parent_id)
    return success_response(data=[BOQItemResponse.model_validate(i) for i in items])


@router.patch("/boq-items/{item_id}", response_model=APIResponse[BOQItemResponse])
async def update_boq_item(
    item_id: str, data: UpdateBOQItemRequest, svc: BOQService = Depends(get_boq_service)
):
    item = await svc.update_boq_item(item_id, data)
    return success_response(data=BOQItemResponse.model_validate(item), message="BOQ item updated")


@router.delete("/boq-items/{item_id}", response_model=APIResponse[None])
async def delete_boq_item(item_id: str, svc: BOQService = Depends(get_boq_service)):
    await svc.delete_boq_item(item_id)
    return success_response(message="BOQ item deleted")