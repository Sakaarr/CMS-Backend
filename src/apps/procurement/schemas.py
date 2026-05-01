from datetime import date
from pydantic import BaseModel, EmailStr
from src.apps.procurement.models import (
    VendorStatus, VendorCategory, RFQStatus,
    QuotationStatus, POStatus, GRNStatus
)


# ── Vendor ────────────────────────────────────────────────────────

class CreateVendorRequest(BaseModel):
    name: str
    code: str
    category: VendorCategory = VendorCategory.OTHER
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    pan_number: str | None = None
    vat_number: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    credit_days: int = 0
    notes: str | None = None


class UpdateVendorRequest(BaseModel):
    name: str | None = None
    category: VendorCategory | None = None
    status: VendorStatus | None = None
    contact_person: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    pan_number: str | None = None
    vat_number: str | None = None
    credit_days: int | None = None
    rating: float | None = None
    notes: str | None = None


class VendorResponse(BaseModel):
    id: str
    name: str
    code: str
    category: VendorCategory
    status: VendorStatus
    contact_person: str | None
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    pan_number: str | None
    credit_days: int
    rating: float
    model_config = {"from_attributes": True}


# ── RFQ ───────────────────────────────────────────────────────────

class RFQItemRequest(BaseModel):
    description: str
    unit: str
    quantity: float
    specification: str | None = None
    sort_order: int = 0


class CreateRFQRequest(BaseModel):
    title: str
    description: str | None = None
    due_date: date | None = None
    delivery_address: str | None = None
    terms_conditions: str | None = None
    vendor_ids: list[str] = []
    items: list[RFQItemRequest] = []


class RFQItemResponse(BaseModel):
    id: str
    description: str
    unit: str
    quantity: float
    specification: str | None
    sort_order: int
    model_config = {"from_attributes": True}


class RFQResponse(BaseModel):
    id: str
    project_id: str
    rfq_number: str
    title: str
    status: RFQStatus
    due_date: date | None
    items: list[RFQItemResponse] = []
    model_config = {"from_attributes": True}


# ── Quotation ─────────────────────────────────────────────────────

class QuotationItemRequest(BaseModel):
    rfq_item_id: str | None = None
    description: str
    unit: str
    quantity: float
    unit_rate: float
    remarks: str | None = None


class CreateQuotationRequest(BaseModel):
    rfq_id: str
    vendor_id: str
    quotation_number: str
    valid_until: date | None = None
    delivery_days: int | None = None
    notes: str | None = None
    items: list[QuotationItemRequest] = []


class QuotationItemResponse(BaseModel):
    id: str
    description: str
    unit: str
    quantity: float
    unit_rate: float
    amount: float
    model_config = {"from_attributes": True}


class QuotationResponse(BaseModel):
    id: str
    rfq_id: str
    vendor_id: str
    quotation_number: str
    status: QuotationStatus
    total_amount: float
    currency: str
    valid_until: date | None
    delivery_days: int | None
    items: list[QuotationItemResponse] = []
    model_config = {"from_attributes": True}


# ── Purchase Order ────────────────────────────────────────────────

class POItemRequest(BaseModel):
    description: str
    unit: str
    quantity: float
    unit_rate: float
    boq_item_id: str | None = None


class CreatePORequest(BaseModel):
    vendor_id: str
    quotation_id: str | None = None
    delivery_date: date | None = None
    delivery_address: str | None = None
    payment_terms: str | None = None
    currency: str = "NPR"
    notes: str | None = None
    items: list[POItemRequest] = []


class POItemResponse(BaseModel):
    id: str
    description: str
    unit: str
    quantity: float
    unit_rate: float
    amount: float
    received_quantity: float
    model_config = {"from_attributes": True}


class POResponse(BaseModel):
    id: str
    project_id: str
    vendor_id: str
    po_number: str
    status: POStatus
    delivery_date: date | None
    total_amount: float
    tax_amount: float
    grand_total: float
    currency: str
    approved_by: str | None
    items: list[POItemResponse] = []
    model_config = {"from_attributes": True}


# ── GRN ───────────────────────────────────────────────────────────

class GRNItemRequest(BaseModel):
    po_item_id: str
    description: str
    unit: str
    ordered_quantity: float
    received_quantity: float
    rejected_quantity: float = 0.0
    unit_rate: float
    remarks: str | None = None


class CreateGRNRequest(BaseModel):
    po_id: str
    received_date: date
    delivery_note: str | None = None
    inspection_passed: bool = True
    notes: str | None = None
    items: list[GRNItemRequest] = []


class GRNItemResponse(BaseModel):
    id: str
    description: str
    unit: str
    ordered_quantity: float
    received_quantity: float
    rejected_quantity: float
    unit_rate: float
    amount: float
    model_config = {"from_attributes": True}


class GRNResponse(BaseModel):
    id: str
    po_id: str
    project_id: str
    grn_number: str
    status: GRNStatus
    received_date: date
    inspection_passed: bool
    items: list[GRNItemResponse] = []
    model_config = {"from_attributes": True}