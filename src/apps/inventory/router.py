from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.inventory.service import InventoryService
from src.apps.inventory.schemas import (
    CreateWarehouseRequest, WarehouseResponse,
    StockItemResponse, StockAdjustmentRequest, StockTransactionResponse,
    CreateMRRequest, MRResponse,
)
from src.shared.response import APIResponse, success_response

router = APIRouter(tags=["Inventory"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> InventoryService:
    return InventoryService(db=db, tenant_id=tenant.id, user_id=current_user.id)


@router.post("/warehouses", response_model=APIResponse[WarehouseResponse], status_code=201)
async def create_warehouse(data: CreateWarehouseRequest, svc: InventoryService = Depends(get_svc)):
    wh = await svc.create_warehouse(data)
    return success_response(data=WarehouseResponse.model_validate(wh), message="Warehouse created")


@router.get("/warehouses", response_model=APIResponse[list[WarehouseResponse]])
async def list_warehouses(
    project_id: str | None = Query(None), svc: InventoryService = Depends(get_svc)
):
    whs = await svc.list_warehouses(project_id=project_id)
    return success_response(data=[WarehouseResponse.model_validate(w) for w in whs])


@router.get("/warehouses/{warehouse_id}/stock", response_model=APIResponse[list[StockItemResponse]])
async def list_stock(warehouse_id: str, svc: InventoryService = Depends(get_svc)):
    items = await svc.list_stock(warehouse_id)
    return success_response(data=[StockItemResponse.model_validate(i) for i in items])


@router.post("/warehouses/{warehouse_id}/transactions", response_model=APIResponse[StockTransactionResponse], status_code=201)
async def record_transaction(
    warehouse_id: str, data: StockAdjustmentRequest,
    project_id: str | None = Query(None),
    svc: InventoryService = Depends(get_svc),
):
    txn = await svc.record_transaction(warehouse_id, data, project_id=project_id)
    return success_response(data=StockTransactionResponse.model_validate(txn), message="Transaction recorded")


@router.get("/warehouses/{warehouse_id}/stock/{stock_item_id}/transactions",
    response_model=APIResponse[list[StockTransactionResponse]])
async def list_transactions(
    warehouse_id: str, stock_item_id: str, svc: InventoryService = Depends(get_svc)
):
    txns = await svc.list_transactions(warehouse_id, stock_item_id)
    return success_response(data=[StockTransactionResponse.model_validate(t) for t in txns])


@router.get("/inventory/low-stock", response_model=APIResponse[list[StockItemResponse]])
async def low_stock_alerts(
    project_id: str | None = Query(None), svc: InventoryService = Depends(get_svc)
):
    items = await svc.get_low_stock_alerts(project_id=project_id)
    return success_response(data=[StockItemResponse.model_validate(i) for i in items])


@router.post("/projects/{project_id}/material-requests", response_model=APIResponse[MRResponse], status_code=201)
async def create_mr(project_id: str, data: CreateMRRequest, svc: InventoryService = Depends(get_svc)):
    mr = await svc.create_mr(project_id, data)
    return success_response(data=MRResponse.model_validate(mr), message="Material request created")


@router.get("/projects/{project_id}/material-requests", response_model=APIResponse[list[MRResponse]])
async def list_mrs(project_id: str, svc: InventoryService = Depends(get_svc)):
    mrs = await svc.list_mrs(project_id)
    return success_response(data=[MRResponse.model_validate(m) for m in mrs])


@router.post("/material-requests/{mr_id}/submit", response_model=APIResponse[MRResponse])
async def submit_mr(mr_id: str, svc: InventoryService = Depends(get_svc)):
    mr = await svc.submit_mr(mr_id)
    return success_response(data=MRResponse.model_validate(mr), message="MR submitted")


@router.post("/material-requests/{mr_id}/approve", response_model=APIResponse[MRResponse])
async def approve_mr(mr_id: str, approved_items: list[dict], svc: InventoryService = Depends(get_svc)):
    mr = await svc.approve_mr(mr_id, approved_items)
    return success_response(data=MRResponse.model_validate(mr), message="MR approved")


@router.post("/material-requests/{mr_id}/issue", response_model=APIResponse[MRResponse])
async def issue_mr(mr_id: str, svc: InventoryService = Depends(get_svc)):
    mr = await svc.issue_mr(mr_id)
    return success_response(data=MRResponse.model_validate(mr), message="Materials issued")