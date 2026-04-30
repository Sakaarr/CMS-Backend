from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
from src.apps.projects.models import (
    Project, Site, Milestone, ProjectMember,
    ProjectStatus, SiteStatus, MilestoneStatus
)
from src.apps.projects.schemas import (
    CreateProjectRequest, UpdateProjectRequest, ProjectStatusUpdateRequest,
    CreateSiteRequest, UpdateSiteRequest,
    CreateMilestoneRequest, UpdateMilestoneRequest,
    AddProjectMemberRequest,
)
from src.core.exceptions import (
    NotFoundError, ConflictError, ValidationError, ForbiddenError
)


# ── Valid project status transitions ─────────────────────────────

STATUS_TRANSITIONS: dict[ProjectStatus, list[ProjectStatus]] = {
    ProjectStatus.DRAFT: [ProjectStatus.PLANNING, ProjectStatus.CANCELLED],
    ProjectStatus.PLANNING: [ProjectStatus.ACTIVE, ProjectStatus.ON_HOLD, ProjectStatus.CANCELLED],
    ProjectStatus.ACTIVE: [ProjectStatus.ON_HOLD, ProjectStatus.COMPLETED, ProjectStatus.CANCELLED],
    ProjectStatus.ON_HOLD: [ProjectStatus.ACTIVE, ProjectStatus.CANCELLED],
    ProjectStatus.COMPLETED: [],
    ProjectStatus.CANCELLED: [],
}


class ProjectService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    # ── Internal helpers ──────────────────────────────────────────

    def _base_query(self):
        """All queries are scoped to tenant + not deleted."""
        return and_(
            Project.tenant_id == self.tenant_id,
            Project.deleted_at.is_(None),
        )

    async def _get_project_or_404(self, project_id: str) -> Project:
        result = await self.db.execute(
            select(Project).where(
                and_(
                    Project.id == project_id,
                    Project.tenant_id == self.tenant_id,
                    Project.deleted_at.is_(None),
                )
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundError("Project")
        return project

    async def _code_exists(self, code: str, exclude_id: str | None = None) -> bool:
        q = select(Project).where(
            and_(
                Project.tenant_id == self.tenant_id,
                Project.code == code,
                Project.deleted_at.is_(None),
            )
        )
        if exclude_id:
            q = q.where(Project.id != exclude_id)
        result = await self.db.execute(q)
        return result.scalar_one_or_none() is not None

    # ── Project CRUD ──────────────────────────────────────────────

    async def create_project(self, data: CreateProjectRequest) -> Project:
        if await self._code_exists(data.code):
            raise ConflictError(f"Project code '{data.code}' already exists in this organisation")

        project = Project(
            **data.model_dump(),
            tenant_id=self.tenant_id,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.db.add(project)
        await self.db.flush()

        # Auto-add creator as project member
        member = ProjectMember(
            project_id=project.id,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            role="project_manager",
            created_by=self.user_id,
        )
        self.db.add(member)
        await self.db.flush()
        return project

    async def get_project(self, project_id: str) -> Project:
        return await self._get_project_or_404(project_id)

    async def list_projects(
        self,
        status: ProjectStatus | None = None,
        skip: int = 0,
        limit: int = 20,
        search: str | None = None,
    ) -> tuple[list[Project], int]:
        conditions = [self._base_query()]

        if status:
            conditions.append(Project.status == status)
        if search:
            conditions.append(
                Project.name.ilike(f"%{search}%") | Project.code.ilike(f"%{search}%")
            )

        count_q = select(func.count()).select_from(Project).where(*conditions)
        total = (await self.db.execute(count_q)).scalar_one()

        q = (
            select(Project)
            .where(*conditions)
            .order_by(Project.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all()), total

    async def update_project(self, project_id: str, data: UpdateProjectRequest) -> Project:
        project = await self._get_project_or_404(project_id)
        updates = data.model_dump(exclude_none=True)

        if "code" in updates and updates["code"] != project.code:
            if await self._code_exists(updates["code"], exclude_id=project_id):
                raise ConflictError(f"Project code '{updates['code']}' already exists")

        for key, value in updates.items():
            setattr(project, key, value)
        project.updated_by = self.user_id
        await self.db.flush()
        return project

    async def update_status(
        self, project_id: str, data: ProjectStatusUpdateRequest
    ) -> Project:
        project = await self._get_project_or_404(project_id)
        allowed = STATUS_TRANSITIONS.get(project.status, [])

        if data.status not in allowed:
            raise ValidationError(
                f"Cannot transition project from '{project.status}' to '{data.status}'. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

        project.status = data.status
        project.updated_by = self.user_id

        # Auto-set actual dates
        if data.status == ProjectStatus.ACTIVE and not project.actual_start_date:
            from datetime import date
            project.actual_start_date = date.today()
        if data.status == ProjectStatus.COMPLETED and not project.actual_end_date:
            from datetime import date
            project.actual_end_date = date.today()

        await self.db.flush()
        return project

    async def delete_project(self, project_id: str) -> None:
        project = await self._get_project_or_404(project_id)
        if project.status == ProjectStatus.ACTIVE:
            raise ValidationError("Cannot delete an active project. Put it on hold or cancel first.")
        from datetime import datetime, timezone
        project.deleted_at = datetime.now(timezone.utc)
        project.updated_by = self.user_id
        await self.db.flush()

    # ── Site CRUD ─────────────────────────────────────────────────

    async def create_site(self, project_id: str, data: CreateSiteRequest) -> Site:
        await self._get_project_or_404(project_id)

        # Check code uniqueness within project
        existing = await self.db.execute(
            select(Site).where(
                and_(
                    Site.project_id == project_id,
                    Site.code == data.code,
                    Site.deleted_at.is_(None),
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Site code '{data.code}' already exists in this project")

        site = Site(
            **data.model_dump(),
            project_id=project_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(site)
        await self.db.flush()
        return site

    async def list_sites(self, project_id: str) -> list[Site]:
        await self._get_project_or_404(project_id)
        result = await self.db.execute(
            select(Site).where(
                and_(
                    Site.project_id == project_id,
                    Site.tenant_id == self.tenant_id,
                    Site.deleted_at.is_(None),
                )
            ).order_by(Site.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_site(self, project_id: str, site_id: str) -> Site:
        result = await self.db.execute(
            select(Site).where(
                and_(
                    Site.id == site_id,
                    Site.project_id == project_id,
                    Site.tenant_id == self.tenant_id,
                    Site.deleted_at.is_(None),
                )
            )
        )
        site = result.scalar_one_or_none()
        if not site:
            raise NotFoundError("Site")
        return site

    async def update_site(self, project_id: str, site_id: str, data: UpdateSiteRequest) -> Site:
        site = await self.get_site(project_id, site_id)
        for key, value in data.model_dump(exclude_none=True).items():
            setattr(site, key, value)
        site.updated_by = self.user_id
        await self.db.flush()
        return site

    async def delete_site(self, project_id: str, site_id: str) -> None:
        site = await self.get_site(project_id, site_id)
        from datetime import datetime, timezone
        site.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    # ── Milestone CRUD ────────────────────────────────────────────

    async def create_milestone(self, project_id: str, data: CreateMilestoneRequest) -> Milestone:
        await self._get_project_or_404(project_id)

        if data.site_id:
            await self.get_site(project_id, data.site_id)

        milestone = Milestone(
            **data.model_dump(),
            project_id=project_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(milestone)
        await self.db.flush()
        return milestone

    async def list_milestones(
        self, project_id: str, site_id: str | None = None
    ) -> list[Milestone]:
        await self._get_project_or_404(project_id)
        conditions = [
            Milestone.project_id == project_id,
            Milestone.tenant_id == self.tenant_id,
            Milestone.deleted_at.is_(None),
        ]
        if site_id:
            conditions.append(Milestone.site_id == site_id)

        result = await self.db.execute(
            select(Milestone)
            .where(and_(*conditions))
            .order_by(Milestone.sequence.asc(), Milestone.planned_date.asc())
        )
        return list(result.scalars().all())

    async def get_milestone(self, project_id: str, milestone_id: str) -> Milestone:
        result = await self.db.execute(
            select(Milestone).where(
                and_(
                    Milestone.id == milestone_id,
                    Milestone.project_id == project_id,
                    Milestone.tenant_id == self.tenant_id,
                    Milestone.deleted_at.is_(None),
                )
            )
        )
        m = result.scalar_one_or_none()
        if not m:
            raise NotFoundError("Milestone")
        return m

    async def update_milestone(
        self, project_id: str, milestone_id: str, data: UpdateMilestoneRequest
    ) -> Milestone:
        milestone = await self.get_milestone(project_id, milestone_id)
        for key, value in data.model_dump(exclude_none=True).items():
            setattr(milestone, key, value)
        milestone.updated_by = self.user_id
        await self.db.flush()

        # Recalculate project progress based on milestones
        await self._recalculate_project_progress(project_id)
        return milestone

    async def _recalculate_project_progress(self, project_id: str) -> None:
        result = await self.db.execute(
            select(
                func.avg(Milestone.completion_percentage)
            ).where(
                and_(
                    Milestone.project_id == project_id,
                    Milestone.deleted_at.is_(None),
                )
            )
        )
        avg = result.scalar_one_or_none() or 0.0
        await self.db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(progress_percentage=round(avg, 2))
        )

    async def delete_milestone(self, project_id: str, milestone_id: str) -> None:
        milestone = await self.get_milestone(project_id, milestone_id)
        from datetime import datetime, timezone
        milestone.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    # ── Project Members ───────────────────────────────────────────

    async def add_member(self, project_id: str, data: AddProjectMemberRequest) -> ProjectMember:
        await self._get_project_or_404(project_id)

        existing = await self.db.execute(
            select(ProjectMember).where(
                and_(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == data.user_id,
                    ProjectMember.deleted_at.is_(None),
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError("User is already a member of this project")

        member = ProjectMember(
            project_id=project_id,
            user_id=data.user_id,
            role=data.role,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def list_members(self, project_id: str) -> list[ProjectMember]:
        await self._get_project_or_404(project_id)
        result = await self.db.execute(
            select(ProjectMember).where(
                and_(
                    ProjectMember.project_id == project_id,
                    ProjectMember.tenant_id == self.tenant_id,
                    ProjectMember.deleted_at.is_(None),
                    ProjectMember.is_active.is_(True),
                )
            )
        )
        return list(result.scalars().all())

    async def remove_member(self, project_id: str, member_id: str) -> None:
        result = await self.db.execute(
            select(ProjectMember).where(
                and_(
                    ProjectMember.id == member_id,
                    ProjectMember.project_id == project_id,
                    ProjectMember.tenant_id == self.tenant_id,
                    ProjectMember.deleted_at.is_(None),
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise NotFoundError("Project member")
        member.is_active = False
        member.updated_by = self.user_id
        await self.db.flush()

    # ── Dashboard summary ─────────────────────────────────────────

    async def get_project_stats(self) -> dict:
        """Aggregated stats for dashboard KPI cards."""
        result = await self.db.execute(
            select(
                Project.status,
                func.count(Project.id).label("count"),
            )
            .where(self._base_query())
            .group_by(Project.status)
        )
        rows = result.all()
        stats = {row.status: row.count for row in rows}

        budget_result = await self.db.execute(
            select(func.sum(Project.estimated_budget))
            .where(
                and_(
                    self._base_query(),
                    Project.status == ProjectStatus.ACTIVE,
                )
            )
        )
        total_active_budget = budget_result.scalar_one_or_none() or 0.0

        return {
            "total": sum(stats.values()),
            "by_status": stats,
            "active_budget_total": total_active_budget,
        }