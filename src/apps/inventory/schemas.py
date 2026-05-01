from datetime import date
from pydantic import BaseModel
from src.apps.inventory.models import (
    WarehouseStatus, TransactionType, MaterialRequestStatus
)


class CreateWarehouseRequest(BaseModel):
    name: str
    code: str
    project_id: str | None = None
    site_id: str | None = None
    address: str | None = None
    is_site_store: bool = False
    keeper_id: str | None = None


class WarehouseResponse(BaseModel):
    id: str
    name: str
    code: str
    project_id: str | None
    site_id: str | None
    status: WarehouseStatus
    is_site_store: bool
    model_config = {"from_attributes": True}


class StockItemResponse(BaseModel):
    id: str
    warehouse_id: str
    material_code: str
    description: str
    unit: str
    quantity_on_hand: float
    reserved_quantity: float
    reorder_level: float
    unit_cost: float
    available_quantity: float
    needs_reorder: bool
    model_config = {"from_attributes": True}


class StockAdjustmentRequest(BaseModel):
    material_code: str
    description: str
    unit: str
    quantity: float
    unit_cost: float = 0.0
    transaction_type: TransactionType = TransactionType.ADJUSTMENT
    reference_type: str | None = None
    reference_id: str | None = None
    notes: str | None = None


class StockTransactionResponse(BaseModel):
    id: str
    stock_item_id: str
    transaction_type: TransactionType
    quantity: float
    unit_cost: float
    total_cost: float
    balance_after: float
    notes: str | None
    created_at: str
    model_config = {"from_attributes": True}


class MRItemRequest(BaseModel):
    material_code: str
    description: str
    unit: str
    requested_quantity: float
    stock_item_id: str | None = None
    remarks: str | None = None


class CreateMRRequest(BaseModel):
    site_id: str | None = None
    from_warehouse_id: str | None = None
    required_date: str | None = None
    purpose: str | None = None
    items: list[MRItemRequest] = []


class MRItemResponse(BaseModel):
    id: str
    material_code: str
    description: str
    unit: str
    requested_quantity: float
    approved_quantity: float
    issued_quantity: float
    remarks: str | None
    model_config = {"from_attributes": True}


class MRResponse(BaseModel):
    id: str
    project_id: str
    mr_number: str
    status: MaterialRequestStatus
    required_date: str | None
    purpose: str | None
    items: list[MRItemResponse] = []
    model_config = {"from_attributes": True}


class IssueMaterialRequest(BaseModel):
    items: list[dict]  # [{mr_item_id, issued_quantity}]