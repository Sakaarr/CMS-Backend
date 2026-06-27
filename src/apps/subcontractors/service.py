from __future__ import annotations

from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from src.apps.subcontractors.models import (
    Subcontractor, SubcontractorContract, WorkOrder, SubcontractorBOQItem,
    SubcontractorStatus, ContractStatus, WorkOrderStatus, BOQItemAssignmentStatus,
)
from src.apps.subcontractors.schemas import (
    CreateSubcontractorRequest, UpdateSubcontractorRequest,
    CreateContractRequest, UpdateContractRequest,
    CreateWorkOrderRequest, UpdateWorkOrderRequest,
    AssignBOQItemRequest,
)
from src.apps.boq.models import BOQItem
from src.core.exceptions import NotFoundError
import uuid


def _num(prefix: str) -> str:
    return f"{prefix}-{str(uuid.uuid4())[:8].upper()}"


class SubcontractorService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    async def create(self, data: CreateSubcontractorRequest) -> Subcontractor:
        sub = Subcontractor(
            name=data.name,
            code=data.code,
            specialty=data.specialty,
            contact_person=data.contact_person,
            email=data.email,
            phone=data.phone,
            address=data.address,
            city=data.city,
            gst_number=data.gst_number,
            pan_number=data.pan_number,
            license_number=data.license_number,
            insurance_provider=data.insurance_provider,
            insurance_valid_until=data.insurance_valid_until,
            notes=data.notes,
            is_approved=data.is_approved,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(sub)
        await self.db.flush()
        return sub

    async def list(
        self, status: SubcontractorStatus | None = None,
        specialty: str | None = None,
        search: str | None = None,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[Subcontractor], int]:
        conditions = [self._scope(Subcontractor)]
        if status:
            conditions.append(Subcontractor.status == status)
        if specialty:
            conditions.append(Subcontractor.specialty == specialty)
        if search:
            conditions.append(
                Subcontractor.name.ilike(f"%{search}%")
            )

        total = (await self.db.execute(
            select(func.count()).select_from(Subcontractor).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(Subcontractor).where(and_(*conditions))
            .order_by(Subcontractor.name.asc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get(self, subcontractor_id: str) -> Subcontractor:
        result = await self.db.execute(
            select(Subcontractor).where(
                and_(Subcontractor.id == subcontractor_id, self._scope(Subcontractor))
            )
        )
        sub = result.scalar_one_or_none()
        if not sub:
            raise NotFoundError("Subcontractor")
        return sub

    async def update(self, subcontractor_id: str, data: UpdateSubcontractorRequest) -> Subcontractor:
        sub = await self.get(subcontractor_id)
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(sub, k, v)
        sub.updated_by = self.user_id
        await self.db.flush()
        return sub

    async def delete(self, subcontractor_id: str) -> None:
        sub = await self.get(subcontractor_id)
        sub.deleted_at = date.today()
        sub.updated_by = self.user_id
        await self.db.flush()

    async def create_contract(self, project_id: str, data: CreateContractRequest) -> SubcontractorContract:
        contract = SubcontractorContract(
            project_id=project_id,
            subcontractor_id=data.subcontractor_id,
            contract_number=_num("SC"),
            title=data.title,
            description=data.description,
            scope_of_work=data.scope_of_work,
            contract_value=data.contract_value,
            currency=data.currency,
            start_date=data.start_date,
            end_date=data.end_date,
            payment_terms=data.payment_terms,
            retention_percentage=data.retention_percentage,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(contract)
        await self.db.flush()
        return contract

    async def list_contracts(
        self, project_id: str | None = None,
        subcontractor_id: str | None = None,
        status: ContractStatus | None = None,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[SubcontractorContract], int]:
        conditions = [self._scope(SubcontractorContract)]
        if project_id:
            conditions.append(SubcontractorContract.project_id == project_id)
        if subcontractor_id:
            conditions.append(SubcontractorContract.subcontractor_id == subcontractor_id)
        if status:
            conditions.append(SubcontractorContract.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorContract).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SubcontractorContract)
            .options(selectinload(SubcontractorContract.subcontractor))
            .where(and_(*conditions))
            .order_by(SubcontractorContract.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_contract(self, contract_id: str) -> SubcontractorContract:
        result = await self.db.execute(
            select(SubcontractorContract)
            .options(selectinload(SubcontractorContract.subcontractor))
            .where(and_(SubcontractorContract.id == contract_id, self._scope(SubcontractorContract)))
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise NotFoundError("Contract")
        return contract

    async def update_contract(self, contract_id: str, data: UpdateContractRequest) -> SubcontractorContract:
        contract = await self.get_contract(contract_id)
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(contract, k, v)
        contract.updated_by = self.user_id
        await self.db.flush()
        return contract

    async def create_work_order(self, project_id: str, data: CreateWorkOrderRequest) -> WorkOrder:
        wo = WorkOrder(
            project_id=project_id,
            contract_id=data.contract_id,
            work_order_number=_num("WO"),
            title=data.title,
            description=data.description,
            amount=data.amount,
            currency=data.currency,
            scheduled_start=data.scheduled_start,
            scheduled_end=data.scheduled_end,
            assigned_to=data.assigned_to,
            notes=data.notes,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(wo)
        await self.db.flush()
        return wo

    async def list_work_orders(
        self, project_id: str | None = None,
        contract_id: str | None = None,
        status: WorkOrderStatus | None = None,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[WorkOrder], int]:
        conditions = [self._scope(WorkOrder)]
        if project_id:
            conditions.append(WorkOrder.project_id == project_id)
        if contract_id:
            conditions.append(WorkOrder.contract_id == contract_id)
        if status:
            conditions.append(WorkOrder.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(WorkOrder).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(WorkOrder).where(and_(*conditions))
            .order_by(WorkOrder.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_work_order(self, work_order_id: str) -> WorkOrder:
        result = await self.db.execute(
            select(WorkOrder).where(
                and_(WorkOrder.id == work_order_id, self._scope(WorkOrder))
            )
        )
        wo = result.scalar_one_or_none()
        if not wo:
            raise NotFoundError("Work order")
        return wo

    async def update_work_order(self, work_order_id: str, data: UpdateWorkOrderRequest) -> WorkOrder:
        wo = await self.get_work_order(work_order_id)
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(wo, k, v)
        wo.updated_by = self.user_id
        await self.db.flush()
        return wo

    # ── BOQ Item Assignment ─────────────────────────────────────

    async def assign_boq_items(
        self, contract_id: str, items: list[AssignBOQItemRequest],
    ) -> list[SubcontractorBOQItem]:
        contract = await self.get_contract(contract_id)
        created = []
        for item in items:
            boq_item = await self.db.execute(
                select(BOQItem).where(and_(
                    BOQItem.id == item.boq_item_id,
                    BOQItem.deleted_at.is_(None),
                ))
            )
            if not boq_item.scalar_one_or_none():
                raise NotFoundError(f"BOQ item {item.boq_item_id}")

            assignment = SubcontractorBOQItem(
                contract_id=contract_id,
                boq_item_id=item.boq_item_id,
                assigned_quantity=item.assigned_quantity,
                unit_rate=item.unit_rate,
                contract_amount=item.contract_amount,
                status=BOQItemAssignmentStatus.PENDING,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(assignment)
            created.append(assignment)

        await self.db.flush()
        return created

    async def list_contract_boq_items(
        self, contract_id: str, skip: int = 0, limit: int = 30,
    ) -> tuple[list[dict], int]:
        contract = await self.get_contract(contract_id)

        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorBOQItem).where(and_(
                SubcontractorBOQItem.contract_id == contract_id,
                SubcontractorBOQItem.deleted_at.is_(None),
            ))
        )).scalar_one()

        rows = await self.db.execute(
            select(
                SubcontractorBOQItem,
                BOQItem.item_number,
                BOQItem.description,
                BOQItem.unit,
                BOQItem.quantity.label("boq_quantity"),
                BOQItem.unit_rate.label("boq_unit_rate"),
            )
            .select_from(SubcontractorBOQItem)
            .join(BOQItem, BOQItem.id == SubcontractorBOQItem.boq_item_id)
            .where(and_(
                SubcontractorBOQItem.contract_id == contract_id,
                SubcontractorBOQItem.deleted_at.is_(None),
                BOQItem.deleted_at.is_(None),
            ))
            .order_by(BOQItem.item_number.asc())
            .offset(skip).limit(limit)
        )
        result = []
        for row in rows.all():
            a = row[0]
            result.append({
                "id": a.id,
                "boq_item_id": a.boq_item_id,
                "item_number": row[1],
                "description": row[2],
                "unit": row[3],
                "boq_quantity": row[4] or 0,
                "boq_unit_rate": row[5] or 0,
                "assigned_quantity": a.assigned_quantity,
                "unit_rate": a.unit_rate,
                "contract_amount": a.contract_amount,
                "status": a.status.value,
                "notes": a.notes,
            })
        return result, total

    # ── Project-level subcontractor summary ──────────────────────

    async def get_project_subcontractors(
        self, project_id: str, skip: int = 0, limit: int = 30,
    ) -> tuple[list[dict], int]:
        conditions = [
            SubcontractorContract.project_id == project_id,
            SubcontractorContract.deleted_at.is_(None),
        ]
        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorContract).where(and_(*conditions))
        )).scalar_one()

        contracts = await self.db.execute(
            select(SubcontractorContract)
            .options(selectinload(SubcontractorContract.subcontractor))
            .where(and_(*conditions))
            .order_by(SubcontractorContract.created_at.desc())
            .offset(skip).limit(limit)
        )
        contract_list = contracts.scalars().all()

        result = []
        for c in contract_list:
            sub = c.subcontractor
            if not sub:
                continue

            boq_count = (await self.db.execute(
                select(func.count()).select_from(SubcontractorBOQItem).where(and_(
                    SubcontractorBOQItem.contract_id == c.id,
                    SubcontractorBOQItem.deleted_at.is_(None),
                ))
            )).scalar_one()

            boq_amount = (await self.db.execute(
                select(func.coalesce(func.sum(SubcontractorBOQItem.contract_amount), 0)).where(and_(
                    SubcontractorBOQItem.contract_id == c.id,
                    SubcontractorBOQItem.deleted_at.is_(None),
                ))
            )).scalar_one()

            result.append({
                "contract_id": c.id,
                "contract_number": c.contract_number,
                "contract_title": c.title,
                "contract_status": c.status.value,
                "contract_value": c.contract_value,
                "currency": c.currency,
                "scope_of_work": c.scope_of_work,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "retention_percentage": c.retention_percentage,
                "subcontractor_id": sub.id,
                "subcontractor_name": sub.name,
                "subcontractor_specialty": sub.specialty.value if sub.specialty else "",
                "boq_items_count": boq_count,
                "boq_items_total_amount": boq_amount,
            })

        return result, total
