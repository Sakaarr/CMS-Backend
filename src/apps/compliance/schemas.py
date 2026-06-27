from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Optional
from src.apps.compliance.models import ComplianceDocCategory, ComplianceDocStatus


class CreateComplianceDocRequest(BaseModel):
    subcontractor_id: str
    title: str
    category: ComplianceDocCategory
    issuing_authority: Optional[str] = None
    reference_number: Optional[str] = None
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    renewable: bool = True
    reminder_days_before: int = 30
    description: Optional[str] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    notes: Optional[str] = None


class UpdateComplianceDocRequest(BaseModel):
    title: Optional[str] = None
    category: Optional[ComplianceDocCategory] = None
    issuing_authority: Optional[str] = None
    reference_number: Optional[str] = None
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    renewable: Optional[bool] = None
    reminder_days_before: Optional[int] = None
    description: Optional[str] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[ComplianceDocStatus] = None


class ComplianceDocResponse(BaseModel):
    id: str
    project_id: str
    subcontractor_id: str
    document_number: str
    title: str
    category: ComplianceDocCategory
    status: ComplianceDocStatus
    issuing_authority: Optional[str] = None
    reference_number: Optional[str] = None
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    renewable: bool
    reminder_days_before: int
    last_reminded_at: Optional[date] = None
    description: Optional[str] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    notes: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ComplianceDocSummary(BaseModel):
    id: str
    subcontractor_id: str
    document_number: str
    title: str
    category: ComplianceDocCategory
    status: ComplianceDocStatus
    expiry_date: Optional[date] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
