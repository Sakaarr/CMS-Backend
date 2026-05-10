from datetime import date
from pydantic import BaseModel
from src.apps.quality.models import (
    InspectionType, InspectionStatus, NCRStatus, NCRSeverity,
    IncidentSeverity, IncidentStatus, PunchListStatus,
)


# ── Inspection ────────────────────────────────────────────────────

class ChecklistItemRequest(BaseModel):
    item_number: str
    description: str
    is_mandatory: bool = True
    sort_order: int = 0


class CreateInspectionRequest(BaseModel):
    title: str
    inspection_type: InspectionType
    scheduled_date: date
    site_id: str | None = None
    inspector_name: str | None = None
    location: str | None = None
    description: str | None = None
    is_third_party: bool = False
    checklist_items: list[ChecklistItemRequest] = []


class UpdateInspectionRequest(BaseModel):
    title: str | None = None
    status: InspectionStatus | None = None
    completed_date: date | None = None
    findings: str | None = None
    recommendations: str | None = None
    score: float | None = None


class UpdateChecklistItemRequest(BaseModel):
    is_passed: bool | None = None
    remarks: str | None = None
    evidence_url: str | None = None


class ChecklistItemResponse(BaseModel):
    id: str
    item_number: str
    description: str
    is_mandatory: bool
    is_passed: bool | None
    remarks: str | None
    sort_order: int
    model_config = {"from_attributes": True}


class InspectionResponse(BaseModel):
    id: str
    project_id: str
    site_id: str | None
    inspection_number: str
    title: str
    inspection_type: InspectionType
    status: InspectionStatus
    scheduled_date: date
    completed_date: date | None
    inspector_name: str | None
    location: str | None
    findings: str | None
    score: float | None
    is_third_party: bool
    checklist_items: list[ChecklistItemResponse] = []
    model_config = {"from_attributes": True}


class InspectionSummary(BaseModel):
    id: str
    inspection_number: str
    title: str
    inspection_type: InspectionType
    status: InspectionStatus
    scheduled_date: date
    inspector_name: str | None
    score: float | None
    model_config = {"from_attributes": True}


# ── NCR ───────────────────────────────────────────────────────────

class CreateNCRRequest(BaseModel):
    title: str
    description: str
    severity: NCRSeverity = NCRSeverity.MEDIUM
    site_id: str | None = None
    inspection_id: str | None = None
    location: str | None = None
    assigned_to: str | None = None
    due_date: date | None = None


class UpdateNCRRequest(BaseModel):
    status: NCRStatus | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    preventive_action: str | None = None
    assigned_to: str | None = None
    due_date: date | None = None
    evidence_url: str | None = None


class NCRResponse(BaseModel):
    id: str
    project_id: str
    ncr_number: str
    title: str
    description: str
    status: NCRStatus
    severity: NCRSeverity
    location: str | None
    due_date: date | None
    closed_date: date | None
    root_cause: str | None
    corrective_action: str | None
    model_config = {"from_attributes": True}


# ── Safety Incident ───────────────────────────────────────────────

class CreateIncidentRequest(BaseModel):
    title: str
    description: str
    severity: IncidentSeverity
    incident_date: date
    incident_time: str | None = None
    site_id: str | None = None
    location: str | None = None
    persons_involved: int = 0
    injuries: int = 0
    fatalities: int = 0
    property_damage: float = 0.0
    immediate_action: str | None = None
    is_reportable: bool = False


class UpdateIncidentRequest(BaseModel):
    status: IncidentStatus | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    investigated_by: str | None = None
    evidence_url: str | None = None


class IncidentResponse(BaseModel):
    id: str
    project_id: str
    incident_number: str
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    incident_date: date
    location: str | None
    persons_involved: int
    injuries: int
    fatalities: int
    property_damage: float
    immediate_action: str | None
    is_reportable: bool
    model_config = {"from_attributes": True}


# ── Punch List ────────────────────────────────────────────────────

class CreatePunchItemRequest(BaseModel):
    description: str
    location: str | None = None
    site_id: str | None = None
    inspection_id: str | None = None
    assigned_to: str | None = None
    due_date: date | None = None
    priority: str = "medium"


class UpdatePunchItemRequest(BaseModel):
    status: PunchListStatus | None = None
    completed_date: date | None = None
    verified_by: str | None = None
    remarks: str | None = None


class PunchItemResponse(BaseModel):
    id: str
    project_id: str
    item_number: str
    description: str
    location: str | None
    status: PunchListStatus
    priority: str
    due_date: date | None
    completed_date: date | None
    model_config = {"from_attributes": True}


# ── Quality Summary ───────────────────────────────────────────────

class QualitySummary(BaseModel):
    total_inspections: int
    passed_inspections: int
    failed_inspections: int
    open_ncrs: int
    critical_ncrs: int
    open_incidents: int
    open_punch_items: int
    avg_inspection_score: float