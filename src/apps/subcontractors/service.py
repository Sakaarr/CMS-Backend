from __future__ import annotations

from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from src.apps.subcontractors.models import (
    Subcontractor, SubcontractorContract, WorkOrder,
    SubcontractorStatus, ContractStatus, WorkOrderStatus,
)
from src.apps.subcontractors.schemas import (
    CreateSubcontractorRequest, UpdateSubcontractorRequest,
    CreateContractRequest, UpdateContractRequest,
    CreateWorkOrderRequest, UpdateWorkOrderRequest,
)
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
