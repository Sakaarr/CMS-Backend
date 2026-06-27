from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Optional
from src.apps.progress.models import ProgressStatus, CertificateStatus


# ── Progress Entry ──────────────────────────────────────────────

class CreateProgressEntryRequest(BaseModel):
    contract_id: str
    boq_item_id: str
    assignment_id: Optional[str] = None
    work_date: date
    quantity_completed: float = Field(gt=0)
    remarks: Optional[str] = None
    attachments: Optional[str] = None


class UpdateProgressEntryRequest(BaseModel):
    work_date: Optional[date] = None
    quantity_completed: Optional[float] = Field(default=None, gt=0)
    remarks: Optional[str] = None
    attachments: Optional[str] = None
    version: Optional[int] = None


class ProgressEntryResponse(BaseModel):
    id: str
    project_id: str
    contract_id: str
    boq_item_id: str
    assignment_id: Optional[str] = None
    report_date: date
    work_date: date
    quantity_completed: float
    cumulative_quantity: float
    remarks: Optional[str] = None
    attachments: Optional[str] = None
    status: ProgressStatus
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProgressEntrySummary(BaseModel):
    id: str
    boq_item_id: str
    report_date: date
    work_date: date
    quantity_completed: float
    cumulative_quantity: float
    status: ProgressStatus
    remarks: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Payment Certificate ─────────────────────────────────────────

class CreateCertificateRequest(BaseModel):
    contract_id: str
    period_start: date
    period_end: date
    is_final: bool = False
    deductions: float = 0.0
    remarks: Optional[str] = None


class UpdateCertificateRequest(BaseModel):
    deductions: Optional[float] = None
    remarks: Optional[str] = None
    version: Optional[int] = None


class SubcontractorCertificateItemResponse(BaseModel):
    id: str
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
    remarks: Optional[str] = None

    model_config = {"from_attributes": True}


class SubcontractorCertificateResponse(BaseModel):
    id: str
    project_id: str
    contract_id: str
    certificate_number: str
    period_start: date
    period_end: date
    is_final: bool
    status: CertificateStatus
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
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    invoice_id: Optional[str] = None
    revision_number: int
    parent_id: Optional[str] = None
    remarks: Optional[str] = None
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    items: list[SubcontractorCertificateItemResponse] = []

    model_config = {"from_attributes": True}


class SubcontractorCertificateSummary(BaseModel):
    id: str
    contract_id: str
    certificate_number: str
    period_start: date
    period_end: date
    status: CertificateStatus
    total_certified_value: float
    net_payable: float
    amount_due: float
    retention_amount: float
    deductions: float
    invoice_id: Optional[str] = None
    revision_number: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Summary / Dashboard ────────────────────────────────────────

class ContractProgressSummary(BaseModel):
    contract_id: str
    contract_number: str
    project_id: str
    subcontractor_name: str
    subcontractor_specialty: Optional[str] = None
    total_assigned_quantity: float = 0
    total_completed_quantity: float = 0
    completion_percentage: float = 0
    total_contract_value: float = 0
    certified_value: float = 0
    pending_certification: float = 0
    last_progress_date: Optional[date] = None


class ProgressDashboard(BaseModel):
    total_contracts: int = 0
    active_contracts: int = 0
    total_progress_entries: int = 0
    pending_approval_entries: int = 0
    total_certificates: int = 0
    approved_certificates: int = 0
    total_pending_payment: float = 0
    total_certified_value: float = 0
    total_retention_held: float = 0
    contracts: list[ContractProgressSummary] = []
