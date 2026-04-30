from datetime import date
from pydantic import BaseModel, field_validator, model_validator
from src.apps.projects.models import (
    ProjectStatus, ProjectType, SiteStatus, MilestoneStatus
)
from src.apps.identity.models import UserRole


# ── Project schemas ──────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    code: str
    description: str | None = None
    project_type: ProjectType = ProjectType.OTHER
    client_name: str | None = None
    client_contact: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    country: str = "NP"
    latitude: float | None = None
    longitude: float | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    estimated_budget: float | None = None
    currency: str = "NPR"
    project_manager_id: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def validate_dates(self) -> "CreateProjectRequest":
        if self.planned_start_date and self.planned_end_date:
            if self.planned_end_date <= self.planned_start_date:
                raise ValueError("planned_end_date must be after planned_start_date")
        return self


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    project_type: ProjectType | None = None
    client_name: str | None = None
    client_contact: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    estimated_budget: float | None = None
    approved_budget: float | None = None
    progress_percentage: float | None = None
    project_manager_id: str | None = None


class ProjectStatusUpdateRequest(BaseModel):
    status: ProjectStatus
    reason: str | None = None


class ProjectResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    code: str
    description: str | None
    project_type: ProjectType
    status: ProjectStatus
    client_name: str | None
    client_contact: str | None
    address: str | None
    city: str | None
    district: str | None
    country: str
    latitude: float | None
    longitude: float | None
    planned_start_date: date | None
    planned_end_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    estimated_budget: float | None
    approved_budget: float | None
    currency: str
    progress_percentage: float
    project_manager_id: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ── Site schemas ─────────────────────────────────────────────────

class CreateSiteRequest(BaseModel):
    name: str
    code: str
    description: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    site_incharge_id: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return v.strip().upper()


class UpdateSiteRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: SiteStatus | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    site_incharge_id: str | None = None


class SiteResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    name: str
    code: str
    description: str | None
    status: SiteStatus
    address: str | None
    city: str | None
    district: str | None
    latitude: float | None
    longitude: float | None
    site_incharge_id: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ── Milestone schemas ─────────────────────────────────────────────

class CreateMilestoneRequest(BaseModel):
    name: str
    description: str | None = None
    site_id: str | None = None
    planned_date: date | None = None
    sequence: int = 0
    is_critical: bool = False


class UpdateMilestoneRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: MilestoneStatus | None = None
    planned_date: date | None = None
    actual_date: date | None = None
    sequence: int | None = None
    is_critical: bool | None = None
    completion_percentage: float | None = None


class MilestoneResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    site_id: str | None
    name: str
    description: str | None
    status: MilestoneStatus
    planned_date: date | None
    actual_date: date | None
    sequence: int
    is_critical: bool
    completion_percentage: float
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ── Member schemas ────────────────────────────────────────────────

class AddProjectMemberRequest(BaseModel):
    user_id: str
    role: UserRole


class ProjectMemberResponse(BaseModel):
    id: str
    project_id: str
    user_id: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


# ── Summary / list schemas ────────────────────────────────────────

class ProjectSummary(BaseModel):
    id: str
    name: str
    code: str
    status: ProjectStatus
    project_type: ProjectType
    progress_percentage: float
    planned_start_date: date | None
    planned_end_date: date | None
    city: str | None
    district: str | None
    estimated_budget: float | None
    currency: str
    site_count: int = 0
    milestone_count: int = 0

    model_config = {"from_attributes": True}