from datetime import date, datetime
from pydantic import BaseModel
from src.apps.subcontractors.models import (
    SubcontractorStatus, SubcontractorSpecialty,
    ContractStatus, WorkOrderStatus,
)


class CreateSubcontractorRequest(BaseModel):
    name: str
    code: str
    specialty: SubcontractorSpecialty
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    gst_number: str | None = None
    pan_number: str | None = None
    license_number: str | None = None
    insurance_provider: str | None = None
    insurance_valid_until: date | None = None
    notes: str | None = None
    is_approved: bool = False


class UpdateSubcontractorRequest(BaseModel):
    name: str | None = None
    specialty: SubcontractorSpecialty | None = None
    status: SubcontractorStatus | None = None
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    gst_number: str | None = None
    pan_number: str | None = None
    license_number: str | None = None
    insurance_provider: str | None = None
    insurance_valid_until: date | None = None
    rating: float | None = None
    notes: str | None = None
    is_approved: bool | None = None


class SubcontractorResponse(BaseModel):
    id: str
    name: str
    code: str
    specialty: SubcontractorSpecialty
    status: SubcontractorStatus
    contact_person: str | None
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    gst_number: str | None
    pan_number: str | None
    license_number: str | None
    insurance_provider: str | None
    insurance_valid_until: date | None
    rating: float
    notes: str | None
    is_approved: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class SubcontractorSummary(BaseModel):
    id: str
    name: str
    code: str
    specialty: SubcontractorSpecialty
    status: SubcontractorStatus
    city: str | None
    rating: float
    is_approved: bool
    model_config = {"from_attributes": True}


class CreateContractRequest(BaseModel):
    project_id: str
    subcontractor_id: str
    title: str
    description: str | None = None
    scope_of_work: str | None = None
    contract_value: float = 0.0
    currency: str = "INR"
    start_date: date | None = None
    end_date: date | None = None
    payment_terms: str | None = None
    retention_percentage: float = 0.0


class UpdateContractRequest(BaseModel):
    title: str | None = None
    status: ContractStatus | None = None
    scope_of_work: str | None = None
    contract_value: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    payment_terms: str | None = None
    retention_percentage: float | None = None
    signed_date: date | None = None
    signed_by: str | None = None


class ContractResponse(BaseModel):
    id: str
    project_id: str
    subcontractor_id: str
    contract_number: str
    title: str
    description: str | None
    status: ContractStatus
    scope_of_work: str | None
    contract_value: float
    currency: str
    start_date: date | None
    end_date: date | None
    payment_terms: str | None
    retention_percentage: float
    signed_date: date | None
    created_at: datetime
    model_config = {"from_attributes": True}


class ContractSummary(BaseModel):
    id: str
    contract_number: str
    title: str
    status: ContractStatus
    contract_value: float
    currency: str
    start_date: date | None
    end_date: date | None
    model_config = {"from_attributes": True}


class CreateWorkOrderRequest(BaseModel):
    contract_id: str
    title: str
    description: str | None = None
    amount: float = 0.0
    currency: str = "INR"
    scheduled_start: date | None = None
    scheduled_end: date | None = None
    assigned_to: str | None = None
    notes: str | None = None


class UpdateWorkOrderRequest(BaseModel):
    title: str | None = None
    status: WorkOrderStatus | None = None
    amount: float | None = None
    scheduled_start: date | None = None
    scheduled_end: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    assigned_to: str | None = None
    notes: str | None = None


class WorkOrderResponse(BaseModel):
    id: str
    project_id: str
    contract_id: str
    work_order_number: str
    title: str
    description: str | None
    status: WorkOrderStatus
    amount: float
    currency: str
    scheduled_start: date | None
    scheduled_end: date | None
    actual_start: date | None
    actual_end: date | None
    assigned_to: str | None
    notes: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class WorkOrderSummary(BaseModel):
    id: str
    work_order_number: str
    title: str
    status: WorkOrderStatus
    amount: float
    currency: str
    scheduled_start: date | None
    scheduled_end: date | None
    model_config = {"from_attributes": True}


class AssignBOQItemRequest(BaseModel):
    boq_item_id: str
    assigned_quantity: float = 0.0
    unit_rate: float = 0.0
    contract_amount: float = 0.0


class AssignBOQItemsRequest(BaseModel):
    items: list[AssignBOQItemRequest]


class AssignedBOQItemResponse(BaseModel):
    id: str
    contract_id: str
    boq_item_id: str
    assigned_quantity: float
    unit_rate: float
    contract_amount: float
    status: str
    notes: str | None = None

    model_config = {"from_attributes": True}


class ContractBOQItemResponse(BaseModel):
    id: str
    boq_item_id: str
    item_number: str
    description: str
    unit: str
    boq_quantity: float
    boq_unit_rate: float
    assigned_quantity: float
    unit_rate: float
    contract_amount: float
    status: str
    notes: str | None = None

    model_config = {"from_attributes": True}


class ProjectSubcontractorResponse(BaseModel):
    contract_id: str
    contract_number: str
    contract_title: str
    contract_status: ContractStatus
    contract_value: float
    currency: str
    scope_of_work: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    retention_percentage: float = 0.0
    subcontractor_id: str
    subcontractor_name: str
    subcontractor_specialty: str
    boq_items_count: int = 0
    boq_items_total_amount: float = 0.0
