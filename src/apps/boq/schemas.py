from pydantic import BaseModel, field_validator, model_validator
from src.apps.boq.models import (
    CostCodeCategory, BOQItemStatus, BudgetVersionStatus,
    UnitOfMeasure, RateComponentType
)


# ── Cost Code ─────────────────────────────────────────────────────

class CreateCostCodeRequest(BaseModel):
    code: str
    name: str
    description: str | None = None
    category: CostCodeCategory = CostCodeCategory.OTHER
    unit: UnitOfMeasure = UnitOfMeasure.NOS
    standard_rate: float | None = None

    @field_validator("code")
    @classmethod
    def upper_code(cls, v: str) -> str:
        return v.strip().upper()


class UpdateCostCodeRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: CostCodeCategory | None = None
    unit: UnitOfMeasure | None = None
    standard_rate: float | None = None
    is_active: bool | None = None


class CostCodeResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    category: CostCodeCategory
    unit: UnitOfMeasure
    standard_rate: float | None
    is_active: bool

    model_config = {"from_attributes": True}


# ── Budget Version ────────────────────────────────────────────────

class CreateBudgetVersionRequest(BaseModel):
    name: str
    description: str | None = None
    contingency_percentage: float = 5.0
    currency: str = "NPR"


class UpdateBudgetVersionRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    contingency_percentage: float | None = None


class BudgetVersionResponse(BaseModel):
    id: str
    project_id: str
    version_number: int
    name: str
    description: str | None
    status: BudgetVersionStatus
    total_material_cost: float
    total_labour_cost: float
    total_equipment_cost: float
    total_overhead: float
    total_amount: float
    contingency_percentage: float
    contingency_amount: float
    grand_total: float
    currency: str
    approved_by: str | None

    model_config = {"from_attributes": True}


# ── BOQ Item ──────────────────────────────────────────────────────

class CreateBOQItemRequest(BaseModel):
    item_number: str
    description: str
    specification: str | None = None
    unit: UnitOfMeasure = UnitOfMeasure.NOS
    quantity: float = 0.0
    unit_rate: float = 0.0
    material_rate: float = 0.0
    labour_rate: float = 0.0
    equipment_rate: float = 0.0
    overhead_rate: float = 0.0
    cost_code_id: str | None = None
    parent_id: str | None = None
    is_section_header: bool = False
    sort_order: int = 0

    @model_validator(mode="after")
    def set_unit_rate(self) -> "CreateBOQItemRequest":
        # If unit_rate not set but breakdown is provided, sum them
        if self.unit_rate == 0.0:
            self.unit_rate = (
                self.material_rate + self.labour_rate +
                self.equipment_rate + self.overhead_rate
            )
        return self


class UpdateBOQItemRequest(BaseModel):
    description: str | None = None
    specification: str | None = None
    unit: UnitOfMeasure | None = None
    quantity: float | None = None
    unit_rate: float | None = None
    material_rate: float | None = None
    labour_rate: float | None = None
    equipment_rate: float | None = None
    overhead_rate: float | None = None
    actual_quantity: float | None = None
    status: BOQItemStatus | None = None
    sort_order: int | None = None


class BOQItemResponse(BaseModel):
    id: str
    budget_version_id: str
    project_id: str
    cost_code_id: str | None
    parent_id: str | None
    item_number: str
    description: str
    specification: str | None
    unit: UnitOfMeasure
    quantity: float
    unit_rate: float
    amount: float
    material_rate: float
    labour_rate: float
    equipment_rate: float
    overhead_rate: float
    actual_quantity: float
    actual_amount: float
    status: BOQItemStatus
    is_section_header: bool
    sort_order: int

    model_config = {"from_attributes": True}


# ── Rate Analysis ─────────────────────────────────────────────────

class CreateRateComponentRequest(BaseModel):
    component_type: RateComponentType
    description: str
    unit: UnitOfMeasure
    quantity: float
    rate: float
    wastage_percentage: float = 0.0


class CreateRateAnalysisRequest(BaseModel):
    cost_code_id: str
    name: str
    description: str | None = None
    unit: UnitOfMeasure
    output_quantity: float = 1.0
    overhead_percentage: float = 10.0
    components: list[CreateRateComponentRequest] = []


class RateComponentResponse(BaseModel):
    id: str
    component_type: RateComponentType
    description: str
    unit: UnitOfMeasure
    quantity: float
    rate: float
    amount: float
    wastage_percentage: float

    model_config = {"from_attributes": True}


class RateAnalysisResponse(BaseModel):
    id: str
    cost_code_id: str
    name: str
    description: str | None
    unit: UnitOfMeasure
    output_quantity: float
    total_material: float
    total_labour: float
    total_equipment: float
    overhead_percentage: float
    overhead_amount: float
    unit_rate: float
    is_active: bool
    components: list[RateComponentResponse] = []

    model_config = {"from_attributes": True}


# ── Summary ───────────────────────────────────────────────────────

class BOQSummary(BaseModel):
    budget_version: BudgetVersionResponse
    items_count: int
    categories: dict[str, float]  # category → total amount