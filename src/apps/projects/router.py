from fastapi import APIRouter, Depends, Query
from src.apps.projects.service import ProjectService
from src.apps.projects.dependencies import get_project_service
from src.apps.projects.schemas import (
    CreateProjectRequest, UpdateProjectRequest, ProjectStatusUpdateRequest,
    ProjectResponse, ProjectSummary,
    CreateSiteRequest, UpdateSiteRequest, SiteResponse,
    CreateMilestoneRequest, UpdateMilestoneRequest, MilestoneResponse,
    AddProjectMemberRequest, ProjectMemberResponse,
)
from src.apps.projects.models import ProjectStatus
from src.shared.response import APIResponse, PaginatedResponse, success_response, paginated_response

router = APIRouter(prefix="/projects", tags=["Projects"])


# ── Projects ──────────────────────────────────────────────────────

@router.post("", response_model=APIResponse[ProjectResponse], status_code=201)
async def create_project(
    data: CreateProjectRequest,
    svc: ProjectService = Depends(get_project_service),
):
    project = await svc.create_project(data)
    return success_response(
        data=ProjectResponse.model_validate(project),
        message="Project created",
    )


@router.get("", response_model=PaginatedResponse[ProjectSummary])
async def list_projects(
    svc: ProjectService = Depends(get_project_service),
    status: ProjectStatus | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    skip = (page - 1) * page_size
    projects, total = await svc.list_projects(
        status=status, skip=skip, limit=page_size, search=search
    )
    return paginated_response(
        data=[ProjectSummary.model_validate(p) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=APIResponse[dict])
async def get_project_stats(
    svc: ProjectService = Depends(get_project_service),
):
    stats = await svc.get_project_stats()
    return success_response(data=stats)


@router.get("/{project_id}", response_model=APIResponse[ProjectResponse])
async def get_project(
    project_id: str,
    svc: ProjectService = Depends(get_project_service),
):
    project = await svc.get_project(project_id)
    return success_response(data=ProjectResponse.model_validate(project))


@router.patch("/{project_id}", response_model=APIResponse[ProjectResponse])
async def update_project(
    project_id: str,
    data: UpdateProjectRequest,
    svc: ProjectService = Depends(get_project_service),
):
    project = await svc.update_project(project_id, data)
    return success_response(
        data=ProjectResponse.model_validate(project),
        message="Project updated",
    )


@router.patch("/{project_id}/status", response_model=APIResponse[ProjectResponse])
async def update_project_status(
    project_id: str,
    data: ProjectStatusUpdateRequest,
    svc: ProjectService = Depends(get_project_service),
):
    project = await svc.update_status(project_id, data)
    return success_response(
        data=ProjectResponse.model_validate(project),
        message=f"Project status updated to {project.status}",
    )


@router.delete("/{project_id}", response_model=APIResponse[None])
async def delete_project(
    project_id: str,
    svc: ProjectService = Depends(get_project_service),
):
    await svc.delete_project(project_id)
    return success_response(message="Project deleted")


# ── Sites ─────────────────────────────────────────────────────────

@router.post("/{project_id}/sites", response_model=APIResponse[SiteResponse], status_code=201)
async def create_site(
    project_id: str,
    data: CreateSiteRequest,
    svc: ProjectService = Depends(get_project_service),
):
    site = await svc.create_site(project_id, data)
    return success_response(data=SiteResponse.model_validate(site), message="Site created")


@router.get("/{project_id}/sites", response_model=APIResponse[list[SiteResponse]])
async def list_sites(
    project_id: str,
    svc: ProjectService = Depends(get_project_service),
):
    sites = await svc.list_sites(project_id)
    return success_response(data=[SiteResponse.model_validate(s) for s in sites])


@router.get("/{project_id}/sites/{site_id}", response_model=APIResponse[SiteResponse])
async def get_site(
    project_id: str,
    site_id: str,
    svc: ProjectService = Depends(get_project_service),
):
    site = await svc.get_site(project_id, site_id)
    return success_response(data=SiteResponse.model_validate(site))


@router.patch("/{project_id}/sites/{site_id}", response_model=APIResponse[SiteResponse])
async def update_site(
    project_id: str,
    site_id: str,
    data: UpdateSiteRequest,
    svc: ProjectService = Depends(get_project_service),
):
    site = await svc.update_site(project_id, site_id, data)
    return success_response(data=SiteResponse.model_validate(site), message="Site updated")


@router.delete("/{project_id}/sites/{site_id}", response_model=APIResponse[None])
async def delete_site(
    project_id: str,
    site_id: str,
    svc: ProjectService = Depends(get_project_service),
):
    await svc.delete_site(project_id, site_id)
    return success_response(message="Site deleted")


# ── Milestones ────────────────────────────────────────────────────

@router.post("/{project_id}/milestones", response_model=APIResponse[MilestoneResponse], status_code=201)
async def create_milestone(
    project_id: str,
    data: CreateMilestoneRequest,
    svc: ProjectService = Depends(get_project_service),
):
    m = await svc.create_milestone(project_id, data)
    return success_response(data=MilestoneResponse.model_validate(m), message="Milestone created")


@router.get("/{project_id}/milestones", response_model=APIResponse[list[MilestoneResponse]])
async def list_milestones(
    project_id: str,
    site_id: str | None = Query(None),
    svc: ProjectService = Depends(get_project_service),
):
    milestones = await svc.list_milestones(project_id, site_id=site_id)
    return success_response(data=[MilestoneResponse.model_validate(m) for m in milestones])


@router.patch("/{project_id}/milestones/{milestone_id}", response_model=APIResponse[MilestoneResponse])
async def update_milestone(
    project_id: str,
    milestone_id: str,
    data: UpdateMilestoneRequest,
    svc: ProjectService = Depends(get_project_service),
):
    m = await svc.update_milestone(project_id, milestone_id, data)
    return success_response(data=MilestoneResponse.model_validate(m), message="Milestone updated")


@router.delete("/{project_id}/milestones/{milestone_id}", response_model=APIResponse[None])
async def delete_milestone(
    project_id: str,
    milestone_id: str,
    svc: ProjectService = Depends(get_project_service),
):
    await svc.delete_milestone(project_id, milestone_id)
    return success_response(message="Milestone deleted")


# ── Members ───────────────────────────────────────────────────────

@router.post("/{project_id}/members", response_model=APIResponse[ProjectMemberResponse], status_code=201)
async def add_member(
    project_id: str,
    data: AddProjectMemberRequest,
    svc: ProjectService = Depends(get_project_service),
):
    member = await svc.add_member(project_id, data)
    return success_response(
        data=ProjectMemberResponse.model_validate(member),
        message="Member added to project",
    )


@router.get("/{project_id}/members", response_model=APIResponse[list[ProjectMemberResponse]])
async def list_members(
    project_id: str,
    svc: ProjectService = Depends(get_project_service),
):
    members = await svc.list_members(project_id)
    return success_response(data=[ProjectMemberResponse.model_validate(m) for m in members])


@router.delete("/{project_id}/members/{member_id}", response_model=APIResponse[None])
async def remove_member(
    project_id: str,
    member_id: str,
    svc: ProjectService = Depends(get_project_service),
):
    await svc.remove_member(project_id, member_id)
    return success_response(message="Member removed from project")