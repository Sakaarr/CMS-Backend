from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.tenancy.models import Tenant
from src.apps.projects.dependencies import get_current_tenant
from src.apps.quality.service import QualityService
from src.apps.quality.models import InspectionStatus, NCRStatus, NCRSeverity, PunchListStatus
from src.apps.quality.schemas import (
    CreateInspectionRequest, UpdateInspectionRequest,
    InspectionResponse, InspectionSummary, UpdateChecklistItemRequest, ChecklistItemResponse,
    CreateNCRRequest, UpdateNCRRequest, NCRResponse,
    CreateIncidentRequest, UpdateIncidentRequest, IncidentResponse,
    CreatePunchItemRequest, UpdatePunchItemRequest, PunchItemResponse,
)
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response
from src.core.dependencies import require_module

router = APIRouter(tags=["Quality & Safety"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_module("quality")),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> QualityService:
    return QualityService(db=db, tenant_id=tenant.id, user_id=current_user.id)


# ── Inspections ───────────────────────────────────────────────────

@router.post("/projects/{project_id}/inspections",
    response_model=APIResponse[InspectionResponse], status_code=201)
async def create_inspection(
    project_id: str, data: CreateInspectionRequest,
    svc: QualityService = Depends(get_svc),
):
    insp = await svc.create_inspection(project_id, data)
    return success_response(data=InspectionResponse.model_validate(insp), message="Inspection created")


@router.get("/projects/{project_id}/inspections",
    response_model=PaginatedResponse[InspectionSummary])
async def list_inspections(
    project_id: str,
    status: InspectionStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: QualityService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    inspections, total = await svc.list_inspections(
        project_id, status=status, skip=skip, limit=page_size
    )
    return paginated_response(
        data=[InspectionSummary.model_validate(i) for i in inspections],
        total=total, page=page, page_size=page_size,
    )


@router.get("/inspections/{inspection_id}", response_model=APIResponse[InspectionResponse])
async def get_inspection(inspection_id: str, svc: QualityService = Depends(get_svc)):
    insp = await svc.get_inspection(inspection_id)
    return success_response(data=InspectionResponse.model_validate(insp))


@router.patch("/inspections/{inspection_id}", response_model=APIResponse[InspectionResponse])
async def update_inspection(
    inspection_id: str, data: UpdateInspectionRequest,
    svc: QualityService = Depends(get_svc),
):
    insp = await svc.update_inspection(inspection_id, data)
    return success_response(data=InspectionResponse.model_validate(insp))


@router.post("/inspections/{inspection_id}/pass", response_model=APIResponse[InspectionResponse])
async def pass_inspection(inspection_id: str, svc: QualityService = Depends(get_svc)):
    insp = await svc.complete_inspection(inspection_id, InspectionStatus.PASSED)
    return success_response(data=InspectionResponse.model_validate(insp), message="Inspection passed")


@router.post("/inspections/{inspection_id}/fail", response_model=APIResponse[InspectionResponse])
async def fail_inspection(inspection_id: str, svc: QualityService = Depends(get_svc)):
    insp = await svc.complete_inspection(inspection_id, InspectionStatus.FAILED)
    return success_response(data=InspectionResponse.model_validate(insp), message="Inspection failed")


@router.patch("/inspections/{inspection_id}/checklist/{item_id}",
    response_model=APIResponse[ChecklistItemResponse])
async def update_checklist_item(
    inspection_id: str, item_id: str,
    data: UpdateChecklistItemRequest,
    svc: QualityService = Depends(get_svc),
):
    item = await svc.update_checklist_item(inspection_id, item_id, data)
    return success_response(data=ChecklistItemResponse.model_validate(item))


# ── NCRs ──────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/ncrs",
    response_model=APIResponse[NCRResponse], status_code=201)
async def create_ncr(
    project_id: str, data: CreateNCRRequest,
    svc: QualityService = Depends(get_svc),
):
    ncr = await svc.create_ncr(project_id, data)
    return success_response(data=NCRResponse.model_validate(ncr), message="NCR raised")


@router.get("/projects/{project_id}/ncrs",
    response_model=PaginatedResponse[NCRResponse])
async def list_ncrs(
    project_id: str,
    status: NCRStatus | None = Query(None),
    severity: NCRSeverity | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: QualityService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    ncrs, total = await svc.list_ncrs(
        project_id, status=status, severity=severity,
        skip=skip, limit=page_size,
    )
    return paginated_response(
        data=[NCRResponse.model_validate(n) for n in ncrs],
        total=total, page=page, page_size=page_size,
    )


@router.patch("/ncrs/{ncr_id}", response_model=APIResponse[NCRResponse])
async def update_ncr(
    ncr_id: str, data: UpdateNCRRequest,
    svc: QualityService = Depends(get_svc),
):
    ncr = await svc.update_ncr(ncr_id, data)
    return success_response(data=NCRResponse.model_validate(ncr), message="NCR updated")


# ── Safety Incidents ──────────────────────────────────────────────

@router.post("/projects/{project_id}/safety-incidents",
    response_model=APIResponse[IncidentResponse], status_code=201)
async def create_incident(
    project_id: str, data: CreateIncidentRequest,
    svc: QualityService = Depends(get_svc),
):
    inc = await svc.create_incident(project_id, data)
    return success_response(data=IncidentResponse.model_validate(inc), message="Incident reported")


@router.get("/projects/{project_id}/safety-incidents",
    response_model=PaginatedResponse[IncidentResponse])
async def list_incidents(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: QualityService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    incidents, total = await svc.list_incidents(project_id, skip=skip, limit=page_size)
    return paginated_response(
        data=[IncidentResponse.model_validate(i) for i in incidents],
        total=total, page=page, page_size=page_size,
    )


@router.patch("/safety-incidents/{incident_id}",
    response_model=APIResponse[IncidentResponse])
async def update_incident(
    incident_id: str, data: UpdateIncidentRequest,
    svc: QualityService = Depends(get_svc),
):
    inc = await svc.update_incident(incident_id, data)
    return success_response(data=IncidentResponse.model_validate(inc))


# ── Punch List ────────────────────────────────────────────────────

@router.post("/projects/{project_id}/punch-list",
    response_model=APIResponse[PunchItemResponse], status_code=201)
async def create_punch_item(
    project_id: str, data: CreatePunchItemRequest,
    svc: QualityService = Depends(get_svc),
):
    item = await svc.create_punch_item(project_id, data)
    return success_response(data=PunchItemResponse.model_validate(item), message="Punch item created")


@router.get("/projects/{project_id}/punch-list",
    response_model=PaginatedResponse[PunchItemResponse])
async def list_punch_items(
    project_id: str,
    status: PunchListStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    svc: QualityService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    items, total = await svc.list_punch_items(
        project_id, status=status, skip=skip, limit=page_size
    )
    return paginated_response(
        data=[PunchItemResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.patch("/punch-list/{item_id}", response_model=APIResponse[PunchItemResponse])
async def update_punch_item(
    item_id: str, data: UpdatePunchItemRequest,
    svc: QualityService = Depends(get_svc),
):
    item = await svc.update_punch_item(item_id, data)
    return success_response(data=PunchItemResponse.model_validate(item))


# ── Quality Summary ───────────────────────────────────────────────

@router.get("/projects/{project_id}/quality-summary",
    response_model=APIResponse[dict])
async def quality_summary(project_id: str, svc: QualityService = Depends(get_svc)):
    summary = await svc.get_quality_summary(project_id)
    return success_response(data=summary)