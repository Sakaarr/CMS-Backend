from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
from src.apps.quality.models import (
    Inspection, ChecklistItem, NCR, SafetyIncident,
    PunchListItem, ToolboxTalk, SafetyViolation, SafetyObservation,
    InspectionStatus, NCRStatus,
    IncidentStatus, PunchListStatus, NCRSeverity,
    ViolationSeverity, ViolationStatus,
    ObservationType, ObservationStatus, TalkStatus,
)
from src.apps.quality.schemas import (
    CreateInspectionRequest, UpdateInspectionRequest, UpdateChecklistItemRequest,
    CreateNCRRequest, UpdateNCRRequest,
    CreateIncidentRequest, UpdateIncidentRequest,
    CreatePunchItemRequest, UpdatePunchItemRequest,
)
from src.core.exceptions import NotFoundError, ValidationError
import uuid


def _num(prefix: str) -> str:
    return f"{prefix}-{str(uuid.uuid4())[:8].upper()}"


class QualityService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    # ── Inspections ───────────────────────────────────────────────

    async def create_inspection(
        self, project_id: str, data: CreateInspectionRequest
    ) -> Inspection:
        inspection = Inspection(
            project_id=project_id,
            site_id=data.site_id,
            inspection_number=_num("INSP"),
            title=data.title,
            inspection_type=data.inspection_type,
            scheduled_date=data.scheduled_date,
            inspector_name=data.inspector_name,
            location=data.location,
            description=data.description,
            is_third_party=data.is_third_party,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(inspection)
        await self.db.flush()

        for i, item in enumerate(data.checklist_items):
            ci = ChecklistItem(
                inspection_id=inspection.id,
                item_number=item.item_number or str(i + 1),
                description=item.description,
                is_mandatory=item.is_mandatory,
                sort_order=item.sort_order or i,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(ci)

        await self.db.flush()
        return await self.get_inspection(inspection.id)

    async def list_inspections(
        self, project_id: str,
        status: InspectionStatus | None = None,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[Inspection], int]:
        conditions = [
            Inspection.project_id == project_id,
            self._scope(Inspection),
        ]
        if status:
            conditions.append(Inspection.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(Inspection).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(Inspection).where(and_(*conditions))
            .order_by(Inspection.scheduled_date.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_inspection(self, inspection_id: str) -> Inspection:
        result = await self.db.execute(
            select(Inspection)
            .options(selectinload(Inspection.checklist_items))
            .where(and_(Inspection.id == inspection_id, self._scope(Inspection)))
        )
        insp = result.scalar_one_or_none()
        if not insp:
            raise NotFoundError("Inspection")
        return insp

    async def update_inspection(
        self, inspection_id: str, data: UpdateInspectionRequest
    ) -> Inspection:
        insp = await self.get_inspection(inspection_id)
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(insp, k, v)
        insp.updated_by = self.user_id
        await self.db.flush()
        return await self.get_inspection(inspection_id)

    async def update_checklist_item(
        self, inspection_id: str, item_id: str, data: UpdateChecklistItemRequest
    ) -> ChecklistItem:
        result = await self.db.execute(
            select(ChecklistItem).where(and_(
                ChecklistItem.id == item_id,
                ChecklistItem.inspection_id == inspection_id,
                self._scope(ChecklistItem),
            ))
        )
        item = result.scalar_one_or_none()
        if not item:
            raise NotFoundError("Checklist item")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(item, k, v)
        await self.db.flush()

        # Auto-calculate inspection score
        all_items = (await self.db.execute(
            select(ChecklistItem).where(
                ChecklistItem.inspection_id == inspection_id
            )
        )).scalars().all()

        answered = [i for i in all_items if i.is_passed is not None]
        if answered:
            passed = sum(1 for i in answered if i.is_passed)
            score = round((passed / len(answered)) * 100, 1)
            await self.db.execute(
                update(Inspection)
                .where(Inspection.id == inspection_id)
                .values(score=score)
            )
        return item

    async def complete_inspection(
        self, inspection_id: str, status: InspectionStatus
    ) -> Inspection:
        insp = await self.get_inspection(inspection_id)
        if insp.status in [InspectionStatus.PASSED, InspectionStatus.FAILED]:
            raise ValidationError("Inspection already completed")
        insp.status = status
        insp.completed_date = date.today()
        insp.updated_by = self.user_id
        await self.db.flush()
        return await self.get_inspection(inspection_id)

    # ── NCRs ──────────────────────────────────────────────────────

    async def create_ncr(self, project_id: str, data: CreateNCRRequest) -> NCR:
        ncr = NCR(
            project_id=project_id,
            site_id=data.site_id,
            inspection_id=data.inspection_id,
            ncr_number=_num("NCR"),
            title=data.title,
            description=data.description,
            severity=data.severity,
            location=data.location,
            assigned_to=data.assigned_to,
            due_date=data.due_date,
            raised_by=self.user_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(ncr)
        await self.db.flush()
        return ncr

    async def list_ncrs(
        self, project_id: str,
        status: NCRStatus | None = None,
        severity: NCRSeverity | None = None,
        skip: int = 0, limit: int = 30,
    ) -> tuple[list[NCR], int]:
        conditions = [NCR.project_id == project_id, self._scope(NCR)]
        if status:
            conditions.append(NCR.status == status)
        if severity:
            conditions.append(NCR.severity == severity)

        total = (await self.db.execute(
            select(func.count()).select_from(NCR).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(NCR).where(and_(*conditions))
            .order_by(NCR.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_ncr(self, ncr_id: str) -> NCR:
        result = await self.db.execute(
            select(NCR).where(and_(NCR.id == ncr_id, self._scope(NCR)))
        )
        ncr = result.scalar_one_or_none()
        if not ncr:
            raise NotFoundError("NCR")
        return ncr

    async def update_ncr(self, ncr_id: str, data: UpdateNCRRequest) -> NCR:
        ncr = await self.get_ncr(ncr_id)
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(ncr, k, v)
        if data.status == NCRStatus.CLOSED:
            ncr.closed_date = date.today()
        ncr.updated_by = self.user_id
        await self.db.flush()
        return ncr

    # ── Safety Incidents ──────────────────────────────────────────

    async def create_incident(
        self, project_id: str, data: CreateIncidentRequest
    ) -> SafetyIncident:
        incident = SafetyIncident(
            project_id=project_id,
            site_id=data.site_id,
            incident_number=_num("INC"),
            title=data.title,
            description=data.description,
            severity=data.severity,
            incident_date=data.incident_date,
            incident_time=data.incident_time,
            location=data.location,
            persons_involved=data.persons_involved,
            injuries=data.injuries,
            fatalities=data.fatalities,
            property_damage=data.property_damage,
            immediate_action=data.immediate_action,
            is_reportable=data.is_reportable,
            reported_by=self.user_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(incident)
        await self.db.flush()
        return incident

    async def list_incidents(
        self, project_id: str,
        skip: int = 0, limit: int = 30,
    ) -> tuple[list[SafetyIncident], int]:
        conditions = [
            SafetyIncident.project_id == project_id,
            self._scope(SafetyIncident),
        ]
        total = (await self.db.execute(
            select(func.count()).select_from(SafetyIncident).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SafetyIncident).where(and_(*conditions))
            .order_by(SafetyIncident.incident_date.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def update_incident(
        self, incident_id: str, data: UpdateIncidentRequest
    ) -> SafetyIncident:
        result = await self.db.execute(
            select(SafetyIncident).where(and_(
                SafetyIncident.id == incident_id, self._scope(SafetyIncident)
            ))
        )
        inc = result.scalar_one_or_none()
        if not inc:
            raise NotFoundError("Safety incident")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(inc, k, v)
        inc.updated_by = self.user_id
        await self.db.flush()
        return inc

    # ── Punch List ────────────────────────────────────────────────

    async def create_punch_item(
        self, project_id: str, data: CreatePunchItemRequest
    ) -> PunchListItem:
        count_result = await self.db.execute(
            select(func.count()).select_from(PunchListItem).where(
                and_(
                    PunchListItem.project_id == project_id,
                    self._scope(PunchListItem),
                )
            )
        )
        count = count_result.scalar_one() + 1

        item = PunchListItem(
            project_id=project_id,
            site_id=data.site_id,
            inspection_id=data.inspection_id,
            item_number=f"PL-{count:04d}",
            description=data.description,
            location=data.location,
            assigned_to=data.assigned_to,
            due_date=data.due_date,
            priority=data.priority,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_punch_items(
        self, project_id: str,
        status: PunchListStatus | None = None,
        skip: int = 0, limit: int = 30,
    ) -> tuple[list[PunchListItem], int]:
        conditions = [
            PunchListItem.project_id == project_id,
            self._scope(PunchListItem),
        ]
        if status:
            conditions.append(PunchListItem.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(PunchListItem).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(PunchListItem).where(and_(*conditions))
            .order_by(PunchListItem.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def update_punch_item(
        self, item_id: str, data: UpdatePunchItemRequest
    ) -> PunchListItem:
        result = await self.db.execute(
            select(PunchListItem).where(and_(
                PunchListItem.id == item_id, self._scope(PunchListItem)
            ))
        )
        item = result.scalar_one_or_none()
        if not item:
            raise NotFoundError("Punch list item")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(item, k, v)
        if data.status == PunchListStatus.COMPLETED and not item.completed_date:
            item.completed_date = date.today()
        item.updated_by = self.user_id
        await self.db.flush()
        return item

    # ── Summary ───────────────────────────────────────────────────

    async def get_quality_summary(self, project_id: str) -> dict:
        insp_result = await self.db.execute(
            select(
                Inspection.status,
                func.count(Inspection.id).label("count"),
                func.avg(Inspection.score).label("avg_score"),
            ).where(and_(
                Inspection.project_id == project_id,
                self._scope(Inspection),
            )).group_by(Inspection.status)
        )
        insp_rows = insp_result.all()

        total_inspections = sum(r.count for r in insp_rows)
        passed = sum(r.count for r in insp_rows if r.status == "passed")
        failed = sum(r.count for r in insp_rows if r.status == "failed")
        avg_score = next((r.avg_score for r in insp_rows if r.avg_score), None)

        open_ncrs = (await self.db.execute(
            select(func.count()).select_from(NCR).where(and_(
                NCR.project_id == project_id,
                NCR.status.in_(["open", "acknowledged", "in_progress"]),
                self._scope(NCR),
            ))
        )).scalar_one()

        critical_ncrs = (await self.db.execute(
            select(func.count()).select_from(NCR).where(and_(
                NCR.project_id == project_id,
                NCR.severity == NCRSeverity.CRITICAL,
                NCR.status != NCRStatus.CLOSED,
                self._scope(NCR),
            ))
        )).scalar_one()

        open_incidents = (await self.db.execute(
            select(func.count()).select_from(SafetyIncident).where(and_(
                SafetyIncident.project_id == project_id,
                SafetyIncident.status.in_(["reported", "under_investigation"]),
                self._scope(SafetyIncident),
            ))
        )).scalar_one()

        open_punch = (await self.db.execute(
            select(func.count()).select_from(PunchListItem).where(and_(
                PunchListItem.project_id == project_id,
                PunchListItem.status.in_(["open", "in_progress"]),
                self._scope(PunchListItem),
            ))
        )).scalar_one()

        return {
            "total_inspections": total_inspections,
            "passed_inspections": passed,
            "failed_inspections": failed,
            "open_ncrs": open_ncrs,
            "critical_ncrs": critical_ncrs,
            "open_incidents": open_incidents,
            "open_punch_items": open_punch,
            "avg_inspection_score": round(avg_score, 1) if avg_score else 0.0,
        }

    # ── Safety Metrics ──────────────────────────────────────────────

    async def get_safety_metrics(
        self, project_id: str, subcontractor_id: str | None = None,
    ) -> dict:
        conditions = [self._scope(SafetyIncident), SafetyIncident.project_id == project_id]
        violation_conditions = [self._scope(SafetyViolation), SafetyViolation.project_id == project_id]
        obs_conditions = [self._scope(SafetyObservation), SafetyObservation.project_id == project_id]
        talk_conditions = [self._scope(ToolboxTalk), ToolboxTalk.project_id == project_id]

        if subcontractor_id:
            conditions.append(SafetyIncident.subcontractor_id == subcontractor_id)
            violation_conditions.append(SafetyViolation.subcontractor_id == subcontractor_id)
            obs_conditions.append(SafetyObservation.subcontractor_id == subcontractor_id)
            talk_conditions.append(ToolboxTalk.subcontractor_id == subcontractor_id)

        total_incidents = (await self.db.execute(
            select(func.count()).select_from(SafetyIncident).where(and_(*conditions))
        )).scalar_one()

        open_incidents = (await self.db.execute(
            select(func.count()).select_from(SafetyIncident).where(and_(
                *conditions, SafetyIncident.status.in_(["reported", "under_investigation"]),
            ))
        )).scalar_one()

        fatal_incidents = (await self.db.execute(
            select(func.count()).select_from(SafetyIncident).where(and_(
                *conditions, SafetyIncident.severity == "fatal",
            ))
        )).scalar_one()

        total_violations = (await self.db.execute(
            select(func.count()).select_from(SafetyViolation).where(and_(*violation_conditions))
        )).scalar_one()

        critical_violations = (await self.db.execute(
            select(func.count()).select_from(SafetyViolation).where(and_(
                *violation_conditions, SafetyViolation.severity.in_([ViolationSeverity.HIGH, ViolationSeverity.CRITICAL]),
            ))
        )).scalar_one()

        total_observations = (await self.db.execute(
            select(func.count()).select_from(SafetyObservation).where(and_(*obs_conditions))
        )).scalar_one()

        positive_observations = (await self.db.execute(
            select(func.count()).select_from(SafetyObservation).where(and_(
                *obs_conditions, SafetyObservation.is_positive.is_(True),
            ))
        )).scalar_one()

        unsafe_observations = (await self.db.execute(
            select(func.count()).select_from(SafetyObservation).where(and_(
                *obs_conditions, SafetyObservation.observation_type == ObservationType.UNSAFE,
            ))
        )).scalar_one()

        total_talks = (await self.db.execute(
            select(func.count()).select_from(ToolboxTalk).where(and_(*talk_conditions))
        )).scalar_one()

        completed_talks = (await self.db.execute(
            select(func.count()).select_from(ToolboxTalk).where(and_(
                *talk_conditions, ToolboxTalk.status == TalkStatus.COMPLETED,
            ))
        )).scalar_one()

        total_attendees = (await self.db.execute(
            select(func.coalesce(func.sum(ToolboxTalk.attendees_count), 0)).where(and_(
                *talk_conditions, ToolboxTalk.status == TalkStatus.COMPLETED,
            ))
        )).scalar_one()

        return {
            "total_incidents": total_incidents,
            "open_incidents": open_incidents,
            "fatal_incidents": fatal_incidents,
            "total_violations": total_violations,
            "critical_violations": critical_violations,
            "total_observations": total_observations,
            "positive_observations": positive_observations,
            "unsafe_observations": unsafe_observations,
            "total_toolbox_talks": total_talks,
            "completed_toolbox_talks": completed_talks,
            "total_attendees": total_attendees,
        }
