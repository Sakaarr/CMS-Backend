from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional
from src.apps.portal.models import SubcontractorPortalRole, PortalNotificationType


# ── Auth ──────────────────────────────────────────────────────────

class PortalLoginRequest(BaseModel):
    email: str
    password: str


class PortalLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "PortalUserResponse"


class PortalRefreshRequest(BaseModel):
    refresh_token: str


class PortalChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class PortalUserResponse(BaseModel):
    id: str
    subcontractor_id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: SubcontractorPortalRole
    is_active: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    subcontractor_name: Optional[str] = None

    model_config = {"from_attributes": True}


class CreatePortalUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str
    phone: Optional[str] = None
    role: SubcontractorPortalRole


class UpdatePortalUserRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[SubcontractorPortalRole] = None
    is_active: Optional[bool] = None


# ── Dashboard ─────────────────────────────────────────────────────

class PortalDashboardResponse(BaseModel):
    active_contracts: int
    total_contract_value: float
    total_certified_value: float
    total_paid_amount: float
    pending_progress_entries: int
    approved_progress_entries: int
    open_ncrs: int
    open_punch_items: int
    expiring_documents: int


# ── Contracts ─────────────────────────────────────────────────────

class PortalContractResponse(BaseModel):
    id: str
    project_id: str
    project_name: Optional[str] = None
    contract_number: str
    title: str
    description: Optional[str] = None
    status: str
    contract_value: float
    currency: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    scope_of_work: Optional[str] = None
    boq_item_count: int = 0

    model_config = {"from_attributes": True}


class PortalBOQItemResponse(BaseModel):
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
    cumulative_progress: float = 0.0
    remaining_quantity: float = 0.0

    model_config = {"from_attributes": True}


# ── Progress ──────────────────────────────────────────────────────

class PortalCreateProgressRequest(BaseModel):
    contract_id: str
    boq_item_id: str
    report_date: date
    work_date: date
    quantity_completed: float = Field(gt=0)
    remarks: Optional[str] = None


class PortalProgressResponse(BaseModel):
    id: str
    contract_id: str
    boq_item_id: str
    item_number: Optional[str] = None
    item_description: Optional[str] = None
    report_date: date
    work_date: date
    quantity_completed: float
    cumulative_quantity: float
    remarks: Optional[str] = None
    attachments: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Certificates ──────────────────────────────────────────────────

class PortalCertificateResponse(BaseModel):
    id: str
    contract_id: str
    contract_title: Optional[str] = None
    certificate_number: str
    period_start: date
    period_end: date
    status: str
    previous_certified_value: float
    current_completed_value: float
    total_certified_value: float
    retention_percentage: float
    retention_amount: float
    deductions: float
    gross_payable: float
    net_payable: float
    previous_paid_amount: float
    amount_due: float
    revision_number: int
    remarks: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PortalCertificateDetailResponse(PortalCertificateResponse):
    items: list["PortalCertificateItemResponse"] = []


class PortalCertificateItemResponse(BaseModel):
    boq_item_id: str
    description: str
    unit: str
    assigned_quantity: float
    unit_rate: float
    previous_certified_qty: float
    previous_certified_amount: float
    current_qty: float
    current_amount: float
    total_certified_qty: float
    total_certified_amount: float
    remaining_qty: float

    model_config = {"from_attributes": True}


# ── Quality ───────────────────────────────────────────────────────

class PortalNCRResponse(BaseModel):
    id: str
    project_id: str
    ncr_number: str
    title: str
    description: str
    status: str
    severity: str
    location: Optional[str] = None
    due_date: Optional[date] = None
    closed_date: Optional[date] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PortalNCRRespondRequest(BaseModel):
    root_cause: str
    corrective_action: str
    preventive_action: Optional[str] = None


class PortalPunchItemResponse(BaseModel):
    id: str
    project_id: str
    item_number: str
    description: str
    location: Optional[str] = None
    status: str
    priority: str
    due_date: Optional[date] = None
    completed_date: Optional[date] = None
    remarks: Optional[str] = None

    model_config = {"from_attributes": True}


class PortalPunchRespondRequest(BaseModel):
    remarks: str
    status: str = "completed"


class PortalSafetyObservationResponse(BaseModel):
    id: str
    observation_number: str
    title: str
    description: str
    observation_type: str
    status: str
    observation_date: date
    location: Optional[str] = None
    is_positive: bool
    action_taken: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Compliance ────────────────────────────────────────────────────

class PortalComplianceDocResponse(BaseModel):
    id: str
    document_number: str
    title: str
    category: str
    status: str
    issuing_authority: Optional[str] = None
    reference_number: Optional[str] = None
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    renewable: bool
    description: Optional[str] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    notes: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[date] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Payments ──────────────────────────────────────────────────────

class PortalPaymentResponse(BaseModel):
    id: str
    invoice_number: str
    certificate_number: Optional[str] = None
    gross_amount: float
    deductions: float
    net_amount: float
    paid_amount: float
    payment_date: Optional[date] = None
    payment_method: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Notifications ─────────────────────────────────────────────────

class PortalNotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    notification_type: PortalNotificationType
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
