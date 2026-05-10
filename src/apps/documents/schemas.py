from datetime import datetime
from pydantic import BaseModel, field_validator
from src.apps.documents.models import (
    DocumentCategory, DocumentStatus, ApprovalStatus
)


class CreateDocumentRequest(BaseModel):
    title: str
    category: DocumentCategory
    file_name: str
    file_url: str
    file_size_kb: float | None = None
    file_type: str | None = None
    description: str | None = None
    tags: str | None = None
    site_id: str | None = None
    discipline: str | None = None
    drawing_number: str | None = None
    sheet_number: str | None = None
    version: str = "1.0"


class UpdateDocumentRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: DocumentStatus | None = None
    tags: str | None = None
    discipline: str | None = None


class AddRevisionRequest(BaseModel):
    change_description: str
    file_url: str
    file_name: str
    new_version: str


class ApprovalActionRequest(BaseModel):
    status: ApprovalStatus
    comments: str | None = None


class AddApproverRequest(BaseModel):
    approver_id: str
    approver_name: str
    sequence: int = 1


class DocumentApprovalResponse(BaseModel):
    id: str
    approver_id: str
    approver_name: str
    status: ApprovalStatus
    comments: str | None
    sequence: int
    model_config = {"from_attributes": True}


class DocumentRevisionResponse(BaseModel):
    id: str
    version: str
    revision_number: int
    change_description: str
    file_url: str
    file_name: str
    created_at: datetime
    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: str
    project_id: str
    site_id: str | None
    document_number: str
    title: str
    category: DocumentCategory
    status: DocumentStatus
    description: str | None
    tags: str | None
    file_name: str
    file_url: str
    file_size_kb: float | None
    file_type: str | None
    version: str
    revision_number: int
    is_latest: bool
    discipline: str | None
    drawing_number: str | None
    sheet_number: str | None
    created_at: datetime
    approvals: list[DocumentApprovalResponse] = []
    revisions: list[DocumentRevisionResponse] = []
    model_config = {"from_attributes": True}


class DocumentSummary(BaseModel):
    id: str
    document_number: str
    title: str
    category: DocumentCategory
    status: DocumentStatus
    file_name: str
    file_type: str | None
    version: str
    is_latest: bool
    discipline: str | None
    drawing_number: str | None
    created_at: datetime
    model_config = {"from_attributes": True}
