from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.subcontractors.service import SubcontractorService
from src.apps.subcontractors.models import SubcontractorStatus, ContractStatus, WorkOrderStatus
from src.apps.subcontractors.schemas import (
    CreateSubcontractorRequest, UpdateSubcontractorRequest,
    SubcontractorResponse, SubcontractorSummary,
    CreateContractRequest, UpdateContractRequest,
    ContractResponse, ContractSummary,
    CreateWorkOrderRequest, UpdateWorkOrderRequest,
    WorkOrderResponse, WorkOrderSummary,
    AssignBOQItemsRequest, AssignedBOQItemResponse, ContractBOQItemResponse,
    ProjectSubcontractorResponse,
)
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response
from src.core.dependencies import require_module

router = APIRouter(tags=["Subcontractors"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_module("subcontractors")),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> SubcontractorService:
    return SubcontractorService(db=db, tenant_id=tenant.id, user_id=current_user.id)


@router.post("/subcontractors", response_model=APIResponse[SubcontractorResponse], status_code=201)
async def create_subcontractor(
    data: CreateSubcontractorRequest,
    svc: SubcontractorService = Depends(get_svc),
):
    sub = await svc.create(data)
    return success_response(data=SubcontractorResponse.model_validate(sub), message="Subcontractor created")


@router.get("/subcontractors", response_model=PaginatedResponse[SubcontractorSummary])
async def list_subcontractors(
    status: SubcontractorStatus | None = Query(None),
    specialty: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: SubcontractorService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    subs, total = await svc.list(
        status=status, specialty=specialty, search=search,
        skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[SubcontractorSummary.model_validate(s) for s in subs],
        total=total, page=page, page_size=page_size,
    )


@router.get("/subcontractors/{subcontractor_id}", response_model=APIResponse[SubcontractorResponse])
async def get_subcontractor(subcontractor_id: str, svc: SubcontractorService = Depends(get_svc)):
    sub = await svc.get(subcontractor_id)
    return success_response(data=SubcontractorResponse.model_validate(sub))


@router.patch("/subcontractors/{subcontractor_id}", response_model=APIResponse[SubcontractorResponse])
async def update_subcontractor(
    subcontractor_id: str, data: UpdateSubcontractorRequest,
    svc: SubcontractorService = Depends(get_svc),
):
    sub = await svc.update(subcontractor_id, data)
    return success_response(data=SubcontractorResponse.model_validate(sub), message="Subcontractor updated")


@router.delete("/subcontractors/{subcontractor_id}", response_model=APIResponse[None])
async def delete_subcontractor(subcontractor_id: str, svc: SubcontractorService = Depends(get_svc)):
    await svc.delete(subcontractor_id)
    return success_response(message="Subcontractor deleted")


# ── Contract BOQ Item Assignment ───────────────────────────────

@router.get("/contracts/{contract_id}/boq-items", response_model=PaginatedResponse[ContractBOQItemResponse])
async def list_contract_boq_items(
    contract_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: SubcontractorService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_contract_boq_items(
        contract_id, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[ContractBOQItemResponse(**i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/contracts/{contract_id}/boq-items", response_model=APIResponse[list], status_code=201)
async def assign_boq_items(
    contract_id: str, data: AssignBOQItemsRequest,
    svc: SubcontractorService = Depends(get_svc),
):
    items = await svc.assign_boq_items(contract_id, data.items)
    return success_response(
        data=[AssignedBOQItemResponse.model_validate(i) for i in items],
        message="BOQ items assigned",
    )


@router.get("/projects/{project_id}/subcontractors", response_model=PaginatedResponse[ProjectSubcontractorResponse])
async def list_project_subcontractors(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: SubcontractorService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.get_project_subcontractors(
        project_id, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[ProjectSubcontractorResponse(**i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/projects/{project_id}/contracts", response_model=APIResponse[ContractResponse], status_code=201)
async def create_contract(
    project_id: str, data: CreateContractRequest,
    svc: SubcontractorService = Depends(get_svc),
):
    contract = await svc.create_contract(project_id, data)
    return success_response(data=ContractResponse.model_validate(contract), message="Contract created")


@router.get("/contracts", response_model=PaginatedResponse[ContractSummary])
async def list_contracts(
    project_id: str | None = Query(None),
    subcontractor_id: str | None = Query(None),
    status: ContractStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: SubcontractorService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    contracts, total = await svc.list_contracts(
        project_id=project_id, subcontractor_id=subcontractor_id,
        status=status, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[ContractSummary.model_validate(c) for c in contracts],
        total=total, page=page, page_size=page_size,
    )


@router.get("/contracts/{contract_id}", response_model=APIResponse[ContractResponse])
async def get_contract(contract_id: str, svc: SubcontractorService = Depends(get_svc)):
    contract = await svc.get_contract(contract_id)
    return success_response(data=ContractResponse.model_validate(contract))


@router.patch("/contracts/{contract_id}", response_model=APIResponse[ContractResponse])
async def update_contract(
    contract_id: str, data: UpdateContractRequest,
    svc: SubcontractorService = Depends(get_svc),
):
    contract = await svc.update_contract(contract_id, data)
    return success_response(data=ContractResponse.model_validate(contract), message="Contract updated")


@router.post("/projects/{project_id}/work-orders", response_model=APIResponse[WorkOrderResponse], status_code=201)
async def create_work_order(
    project_id: str, data: CreateWorkOrderRequest,
    svc: SubcontractorService = Depends(get_svc),
):
    wo = await svc.create_work_order(project_id, data)
    return success_response(data=WorkOrderResponse.model_validate(wo), message="Work order created")


@router.get("/work-orders", response_model=PaginatedResponse[WorkOrderSummary])
async def list_work_orders(
    project_id: str | None = Query(None),
    contract_id: str | None = Query(None),
    status: WorkOrderStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: SubcontractorService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    orders, total = await svc.list_work_orders(
        project_id=project_id, contract_id=contract_id,
        status=status, skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[WorkOrderSummary.model_validate(o) for o in orders],
        total=total, page=page, page_size=page_size,
    )


@router.get("/work-orders/{work_order_id}", response_model=APIResponse[WorkOrderResponse])
async def get_work_order(work_order_id: str, svc: SubcontractorService = Depends(get_svc)):
    wo = await svc.get_work_order(work_order_id)
    return success_response(data=WorkOrderResponse.model_validate(wo))


@router.patch("/work-orders/{work_order_id}", response_model=APIResponse[WorkOrderResponse])
async def update_work_order(
    work_order_id: str, data: UpdateWorkOrderRequest,
    svc: SubcontractorService = Depends(get_svc),
):
    wo = await svc.update_work_order(work_order_id, data)
    return success_response(data=WorkOrderResponse.model_validate(wo), message="Work order updated")
