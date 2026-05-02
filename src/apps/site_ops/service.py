from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from src.apps.site_ops.models import (
    DailyProgressReport, DPRWorkItem, LabourAttendance, EquipmentLog
)
from src.apps.site_ops.schemas import CreateDPRRequest, UpdateDPRRequest
from src.core.exceptions import NotFoundError, ConflictError, ValidationError


class SiteOpsService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    async def create_dpr(self, project_id: str, data: CreateDPRRequest) -> DailyProgressReport:
        # One DPR per site per day
        existing = await self.db.execute(
            select(DailyProgressReport).where(and_(
                DailyProgressReport.project_id == project_id,
                DailyProgressReport.site_id == data.site_id,
                DailyProgressReport.report_date == data.report_date,
                self._scope(DailyProgressReport),
            ))
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"DPR already exists for this site on {data.report_date}")

        total_workers = len([a for a in data.attendance if a.status == "present"])
        total_labour_cost = sum(a.daily_wage for a in data.attendance)

        dpr = DailyProgressReport(
            project_id=project_id,
            site_id=data.site_id,
            report_date=data.report_date,
            weather=data.weather,
            temperature_celsius=data.temperature_celsius,
            work_hours=data.work_hours,
            general_notes=data.general_notes,
            safety_notes=data.safety_notes,
            total_workers=total_workers,
            total_labour_cost=round(total_labour_cost, 2),
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(dpr)
        await self.db.flush()

        for item_data in data.work_items:
            item = DPRWorkItem(
                **item_data.model_dump(),
                dpr_id=dpr.id,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(item)

        for att_data in data.attendance:
            att = LabourAttendance(
                **att_data.model_dump(),
                dpr_id=dpr.id,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(att)

        for eq_data in data.equipment_logs:
            eq = EquipmentLog(
                **eq_data.model_dump(),
                dpr_id=dpr.id,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(eq)

        await self.db.flush()
        result = await self.db.execute(
            select(DailyProgressReport)
            .options(
                selectinload(DailyProgressReport.work_items),
                selectinload(DailyProgressReport.attendance_records),
                selectinload(DailyProgressReport.equipment_logs),
            )
            .where(and_(DailyProgressReport.id == dpr.id, self._scope(DailyProgressReport)))
        )
        return result.scalar_one()

    async def list_dprs(
        self, project_id: str, site_id: str | None = None,
        skip: int = 0, limit: int = 30
    ) -> tuple[list[DailyProgressReport], int]:
        conditions = [
            DailyProgressReport.project_id == project_id,
            self._scope(DailyProgressReport),
        ]
        if site_id:
            conditions.append(DailyProgressReport.site_id == site_id)

        count = (await self.db.execute(
            select(func.count()).select_from(DailyProgressReport).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(DailyProgressReport)
            .where(and_(*conditions))
            .order_by(DailyProgressReport.report_date.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), count

    async def get_dpr(self, dpr_id: str) -> DailyProgressReport:
        result = await self.db.execute(
            select(DailyProgressReport)
            .options(
                selectinload(DailyProgressReport.work_items),
                selectinload(DailyProgressReport.attendance_records),
                selectinload(DailyProgressReport.equipment_logs),
            )
            .where(and_(DailyProgressReport.id == dpr_id, self._scope(DailyProgressReport)))
        )
        dpr = result.scalar_one_or_none()
        if not dpr:
            raise NotFoundError("Daily Progress Report")
        return dpr

    async def submit_dpr(self, dpr_id: str) -> DailyProgressReport:
        dpr = await self.get_dpr(dpr_id)
        if dpr.is_submitted:
            raise ValidationError("DPR already submitted")
        dpr.is_submitted = True
        dpr.submitted_by = self.user_id
        await self.db.flush()
        return dpr

    async def update_dpr(self, dpr_id: str, data: UpdateDPRRequest) -> DailyProgressReport:
        dpr = await self.get_dpr(dpr_id)
        if dpr.is_submitted:
            raise ValidationError("Cannot edit a submitted DPR")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(dpr, k, v)
        dpr.updated_by = self.user_id
        await self.db.flush()
        return dpr

    async def get_site_ops_summary(self, project_id: str) -> dict:
        result = await self.db.execute(
            select(
                func.count(DailyProgressReport.id).label("total_dprs"),
                func.sum(DailyProgressReport.total_workers).label("total_worker_days"),
                func.sum(DailyProgressReport.total_labour_cost).label("total_labour_cost"),
            ).where(and_(
                DailyProgressReport.project_id == project_id,
                self._scope(DailyProgressReport),
            ))
        )
        row = result.one()

        submitted = (await self.db.execute(
            select(func.count(DailyProgressReport.id)).where(and_(
                DailyProgressReport.project_id == project_id,
                DailyProgressReport.is_submitted.is_(True),
                self._scope(DailyProgressReport),
            ))
        )).scalar_one()

        return {
            "total_dprs": row.total_dprs or 0,
            "submitted_dprs": submitted,
            "total_worker_days": row.total_worker_days or 0,
            "total_labour_cost": row.total_labour_cost or 0.0,
        }
