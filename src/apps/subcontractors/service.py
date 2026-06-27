from __future__ import annotations

from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import selectinload
from src.apps.subcontractors.models import (
    Subcontractor, SubcontractorContract, WorkOrder, SubcontractorBOQItem,
    SubcontractorStatus, ContractStatus, WorkOrderStatus, BOQItemAssignmentStatus,
)
from src.apps.subcontractors.schemas import (
    CreateSubcontractorRequest, UpdateSubcontractorRequest,
    CreateContractRequest, UpdateContractRequest,
    CreateWorkOrderRequest, UpdateWorkOrderRequest,
    AssignBOQItemRequest, AssignBOQItemsRequest, UpdateBOQItemAssignmentRequest,
)
from src.apps.boq.models import BOQItem, CostCode, CostCodeCategory
from src.core.exceptions import (
    NotFoundError, BusinessRuleError, DuplicateResourceError,
    ConcurrentModificationError, DependencyError, QuantityExceededError,
)
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

        # Cascade soft-delete: all contracts, work orders, and BOQ assignments
        contracts = await self.db.execute(
            select(SubcontractorContract).where(and_(
                SubcontractorContract.subcontractor_id == subcontractor_id,
                SubcontractorContract.deleted_at.is_(None),
                self._scope(SubcontractorContract),
            ))
        )
        for contract in contracts.scalars().all():
            await self._cascade_delete_contract(contract)

        sub.deleted_at = date.today()
        sub.updated_by = self.user_id
        await self.db.flush()

    async def create_contract(self, project_id: str, data: CreateContractRequest) -> SubcontractorContract:
        # 1. Status gate: subcontractor must be active
        sub = await self.get(data.subcontractor_id)
        if sub.status != SubcontractorStatus.ACTIVE:
            raise BusinessRuleError(
                f"Cannot create contract. Subcontractor '{sub.name}' is {sub.status.value}. "
                "Only active subcontractors can be assigned to projects.",
                error_code="SUBCONTRACTOR_NOT_ACTIVE",
            )

        # 2. Duplicate detection: same sub + same project
        dup = await self.db.execute(
            select(SubcontractorContract).where(and_(
                SubcontractorContract.project_id == project_id,
                SubcontractorContract.subcontractor_id == data.subcontractor_id,
                SubcontractorContract.deleted_at.is_(None),
                self._scope(SubcontractorContract),
            ))
        )
        existing = dup.scalar_one_or_none()
        if existing:
            raise DuplicateResourceError(
                f"Subcontractor '{sub.name}' is already assigned to this project "
                f"(contract: {existing.contract_number}). "
                "Use a unique contract number for multiple assignments."
            )

        # 3. Overlap check: overlapping active contracts
        if data.start_date and data.end_date:
            overlap = await self.db.execute(
                select(func.count()).select_from(SubcontractorContract).where(and_(
                    SubcontractorContract.project_id == project_id,
                    SubcontractorContract.subcontractor_id == data.subcontractor_id,
                    SubcontractorContract.deleted_at.is_(None),
                    SubcontractorContract.status.in_([
                        ContractStatus.ACTIVE, ContractStatus.DRAFT,
                    ]),
                    SubcontractorContract.start_date.isnot(None),
                    SubcontractorContract.end_date.isnot(None),
                    or_(
                        and_(
                            SubcontractorContract.start_date <= data.end_date,
                            SubcontractorContract.end_date >= data.start_date,
                        ),
                    ),
                    self._scope(SubcontractorContract),
                ))
            )
            overlap_count = overlap.scalar_one()
            if overlap_count > 0:
                raise BusinessRuleError(
                    "Subcontractor already has an active or draft contract "
                    "with overlapping dates for this project.",
                    error_code="CONTRACT_OVERLAP",
                )

        contract = SubcontractorContract(
            project_id=project_id,
            subcontractor_id=data.subcontractor_id,
            contract_number=data.contract_number or _num("SC"),
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

    # ── BOQ Item Assignment ────────────────────────────────────────────

    async def _get_specialty_mismatch_warning(
        self, subcontractor_id: str, boq_item_id: str,
    ) -> str | None:
        """Checks if subcontractor specialty matches BOQ cost code category. Returns warning if mismatch."""
        sub = await self.get(subcontractor_id)

        boq_result = await self.db.execute(
            select(BOQItem).where(BOQItem.id == boq_item_id)
        )
        boq_item = boq_result.scalar_one_or_none()
        if not boq_item or not boq_item.cost_code_id:
            return None

        cc_result = await self.db.execute(
            select(CostCode).where(CostCode.id == boq_item.cost_code_id)
        )
        cc = cc_result.scalar_one_or_none()
        if not cc:
            return None

        category = cc.category.value if hasattr(cc.category, 'value') else str(cc.category)
        spec = sub.specialty.value if hasattr(sub.specialty, 'value') else str(sub.specialty)

        MATCH_MAP = {
            CostCodeCategory.CIVIL: {SubcontractorSpecialty.STRUCTURAL, SubcontractorSpecialty.GENERAL},
            CostCodeCategory.STRUCTURAL: {SubcontractorSpecialty.STRUCTURAL, SubcontractorSpecialty.GENERAL},
            CostCodeCategory.ARCHITECTURAL: {SubcontractorSpecialty.FINISHING, SubcontractorSpecialty.GENERAL},
            CostCodeCategory.MEP: {SubcontractorSpecialty.ELECTRICAL, SubcontractorSpecialty.PLUMBING, SubcontractorSpecialty.HVAC, SubcontractorSpecialty.GENERAL},
            CostCodeCategory.FINISHING: {SubcontractorSpecialty.FINISHING, SubcontractorSpecialty.PAINTING, SubcontractorSpecialty.GENERAL},
            CostCodeCategory.EXTERNAL: {SubcontractorSpecialty.LANDSCAPING, SubcontractorSpecialty.GENERAL},
            CostCodeCategory.PRELIMINARY: {SubcontractorSpecialty.GENERAL, SubcontractorSpecialty.OTHER},
            CostCodeCategory.OTHER: {SubcontractorSpecialty.GENERAL, SubcontractorSpecialty.OTHER},
        }

        allowed = MATCH_MAP.get(cc.category, set())
        if allowed and sub.specialty not in allowed:
            return (
                f"Specialty mismatch: subcontractor specializes in '{sub.specialty.value}' "
                f"but BOQ item '{boq_item.item_number}' belongs to '{cc.category.value}' category. "
                "Consider verifying the assignment."
            )
        return None

    async def assign_boq_items(
        self, contract_id: str, data: AssignBOQItemsRequest,
    ) -> list[SubcontractorBOQItem]:
        contract = await self.get_contract(contract_id)

        items = []
        warnings: list[str] = []

        for item in data.items:
            # Verify BOQ item exists
            boq_result = await self.db.execute(
                select(BOQItem).where(
                    and_(BOQItem.id == item.boq_item_id, BOQItem.deleted_at.is_(None))
                )
            )
            boq_item = boq_result.scalar_one_or_none()
            if not boq_item:
                raise NotFoundError(f"BOQ item {item.boq_item_id}")

            # Duplicate check: same BOQ item already assigned to this contract
            dup_result = await self.db.execute(
                select(func.count()).select_from(SubcontractorBOQItem).where(and_(
                    SubcontractorBOQItem.contract_id == contract_id,
                    SubcontractorBOQItem.boq_item_id == item.boq_item_id,
                    SubcontractorBOQItem.deleted_at.is_(None),
                ))
            )
            if dup_result.scalar_one() > 0:
                raise DuplicateResourceError(
                    f"BOQ item '{boq_item.item_number}' is already assigned to this contract. "
                    "Update the existing assignment instead."
                )

            # Quantity allocation enforcement: prevent over-allocation
            if item.assigned_quantity > 0:
                total_assigned_result = await self.db.execute(
                    select(func.coalesce(func.sum(SubcontractorBOQItem.assigned_quantity), 0))
                    .where(and_(
                        SubcontractorBOQItem.boq_item_id == item.boq_item_id,
                        SubcontractorBOQItem.deleted_at.is_(None),
                    ))
                )
                already_assigned = float(total_assigned_result.scalar_one() or 0)

                new_total = already_assigned + item.assigned_quantity
                if new_total > boq_item.quantity:
                    available = boq_item.quantity - already_assigned
                    raise QuantityExceededError(
                        f"BOQ item '{boq_item.item_number}' has total quantity {boq_item.quantity:.2f} {boq_item.unit.value}. "
                        f"Already assigned: {already_assigned:.2f}. "
                        f"Requested: {item.assigned_quantity:.2f}. Available: {max(0, available):.2f}."
                    )

            # Specialty matching check (warning, not a block)
            warning = await self._get_specialty_mismatch_warning(
                contract.subcontractor_id, item.boq_item_id,
            )
            if warning:
                warnings.append(warning)

            assigned = SubcontractorBOQItem(
                contract_id=contract_id,
                boq_item_id=item.boq_item_id,
                assigned_quantity=item.assigned_quantity,
                unit_rate=item.unit_rate,
                contract_amount=item.contract_amount or (item.assigned_quantity * item.unit_rate),
                notes=item.notes,
                version=1,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(assigned)
            items.append(assigned)

        await self.db.flush()

        if warnings:
            setattr(assigned, "_warnings", warnings)
            for item in items:
                setattr(item, "_warnings", warnings)

        return items

    async def list_boq_items(
        self, contract_id: str,
        skip: int = 0, limit: int = 20,
    ) -> tuple[list[SubcontractorBOQItem], int]:
        conditions = [
            self._scope(SubcontractorBOQItem),
            SubcontractorBOQItem.contract_id == contract_id,
        ]

        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorBOQItem).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SubcontractorBOQItem).where(and_(*conditions))
            .order_by(SubcontractorBOQItem.created_at.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def update_boq_item_assignment(
        self, assignment_id: str, data: UpdateBOQItemAssignmentRequest,
    ) -> SubcontractorBOQItem:
        result = await self.db.execute(
            select(SubcontractorBOQItem).where(
                and_(SubcontractorBOQItem.id == assignment_id, self._scope(SubcontractorBOQItem))
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            raise NotFoundError("BOQ item assignment")

        # Concurrent modification protection
        if data.version is not None and data.version != assignment.version:
            raise ConcurrentModificationError(
                "This BOQ item assignment was modified by another user. "
                "Refresh and try again."
            )

        # Quantity allocation enforcement on update
        if data.assigned_quantity is not None and data.assigned_quantity != assignment.assigned_quantity:
            boq_result = await self.db.execute(
                select(BOQItem).where(BOQItem.id == assignment.boq_item_id)
            )
            boq_item = boq_result.scalar_one_or_none()
            if boq_item:
                total_assigned_result = await self.db.execute(
                    select(func.coalesce(func.sum(SubcontractorBOQItem.assigned_quantity), 0))
                    .where(and_(
                        SubcontractorBOQItem.boq_item_id == assignment.boq_item_id,
                        SubcontractorBOQItem.id != assignment_id,
                        SubcontractorBOQItem.deleted_at.is_(None),
                    ))
                )
                already_assigned = float(total_assigned_result.scalar_one() or 0)
                new_total = already_assigned + data.assigned_quantity
                if new_total > boq_item.quantity:
                    available = boq_item.quantity - already_assigned
                    raise QuantityExceededError(
                        f"BOQ item '{boq_item.item_number}' has total quantity {boq_item.quantity:.2f}. "
                        f"Already assigned to others: {already_assigned:.2f}. "
                        f"Requested: {data.assigned_quantity:.2f}. Available: {max(0, available):.2f}."
                    )

        update_data = data.model_dump(exclude_none=True)
        update_data.pop("version", None)
        for k, v in update_data.items():
            setattr(assignment, k, v)
        assignment.version += 1
        assignment.updated_by = self.user_id
        await self.db.flush()
        return assignment

    async def delete_boq_item_assignment(self, assignment_id: str) -> None:
        result = await self.db.execute(
            select(SubcontractorBOQItem).where(
                and_(SubcontractorBOQItem.id == assignment_id, self._scope(SubcontractorBOQItem))
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            raise NotFoundError("BOQ item assignment")

        # Dependency check: work orders referencing this assignment's contract+BOQ item
        from src.apps.procurement.models import POItem
        from src.apps.finance.models import InvoiceLineItem

        po_check = await self.db.execute(
            select(func.count()).select_from(POItem).where(and_(
                POItem.boq_item_id == assignment.boq_item_id,
                POItem.deleted_at.is_(None),
            ))
        )
        if po_check.scalar_one() > 0:
            raise DependencyError(
                "Cannot remove BOQ assignment: purchase order items reference this BOQ item.",
                error_code="HAS_PURCHASE_ORDERS",
            )

        inv_check = await self.db.execute(
            select(func.count()).select_from(InvoiceLineItem).where(and_(
                InvoiceLineItem.boq_item_id == assignment.boq_item_id,
                InvoiceLineItem.deleted_at.is_(None),
            ))
        )
        if inv_check.scalar_one() > 0:
            raise DependencyError(
                "Cannot remove BOQ assignment: invoice line items reference this BOQ item.",
                error_code="HAS_INVOICES",
            )

        assignment.deleted_at = date.today()
        assignment.updated_by = self.user_id
        await self.db.flush()

    async def _cascade_delete_contract(self, contract: SubcontractorContract) -> None:
        """Soft-delete a contract and all its dependents (work orders, BOQ assignments)."""
        # Cascade work orders
        await self.db.execute(
            WorkOrder.__table__.update()
            .where(and_(
                WorkOrder.contract_id == contract.id,
                WorkOrder.deleted_at.is_(None),
            ))
            .values(deleted_at=date.today(), updated_by=self.user_id)
        )

        # Cascade BOQ item assignments
        await self.db.execute(
            SubcontractorBOQItem.__table__.update()
            .where(and_(
                SubcontractorBOQItem.contract_id == contract.id,
                SubcontractorBOQItem.deleted_at.is_(None),
            ))
            .values(deleted_at=date.today(), updated_by=self.user_id)
        )

        contract.deleted_at = date.today()
        contract.updated_by = self.user_id

    async def delete_contract(self, contract_id: str) -> None:
        """Soft-delete a contract with cascade."""
        contract = await self.get_contract(contract_id)
        await self._cascade_delete_contract(contract)
        await self.db.flush()

    # ── Project & Subcontractor queries ────────────────────────────────

    async def get_subcontractor_projects(
        self, subcontractor_id: str,
    ) -> tuple[list[SubcontractorContract], int]:
        """Get all contracts (and thus projects) for a subcontractor."""
        conditions = [
            self._scope(SubcontractorContract),
            SubcontractorContract.subcontractor_id == subcontractor_id,
        ]
        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorContract).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SubcontractorContract).where(and_(*conditions))
            .options(selectinload(SubcontractorContract.subcontractor))
            .order_by(SubcontractorContract.created_at.desc())
        )
        return list(result.scalars().all()), total

    async def get_project_subcontractors(
        self, project_id: str,
    ) -> tuple[list[SubcontractorContract], int]:
        """Get all subcontractor contracts for a project."""
        conditions = [
            self._scope(SubcontractorContract),
            SubcontractorContract.project_id == project_id,
        ]
        total = (await self.db.execute(
            select(func.count()).select_from(SubcontractorContract).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(SubcontractorContract).where(and_(*conditions))
            .options(selectinload(SubcontractorContract.subcontractor))
            .order_by(SubcontractorContract.created_at.desc())
        )
        return list(result.scalars().all()), total

    # ── Dashboard / Workload ────────────────────────────────────────────

    async def get_subcontractor_workload(
        self, subcontractor_id: str,
    ) -> dict:
        """Aggregated workload data for a subcontractor."""
        await self.get(subcontractor_id)  # verify exists

        # All contracts
        contracts_conditions = [
            self._scope(SubcontractorContract),
            SubcontractorContract.subcontractor_id == subcontractor_id,
        ]
        contracts_result = await self.db.execute(
            select(SubcontractorContract).where(and_(*contracts_conditions))
            .order_by(SubcontractorContract.created_at.desc())
        )
        contracts = list(contracts_result.scalars().all())

        active_contracts = [c for c in contracts if c.status == ContractStatus.ACTIVE]

        # All BOQ items assigned to this sub via contracts
        contract_ids = [c.id for c in contracts]
        boq_conditions = [
            self._scope(SubcontractorBOQItem),
            SubcontractorBOQItem.contract_id.in_(contract_ids),
        ] if contract_ids else [self._scope(SubcontractorBOQItem)]

        boq_total_result = await self.db.execute(
            select(
                func.count(), func.coalesce(func.sum(SubcontractorBOQItem.contract_amount), 0)
            ).select_from(SubcontractorBOQItem).where(and_(*boq_conditions))
        )
        boq_count, boq_amount = boq_total_result.one()

        return {
            "subcontractor_id": subcontractor_id,
            "total_contracts": len(contracts),
            "total_contract_value": sum(c.contract_value for c in contracts),
            "active_contracts": len(active_contracts),
            "active_contract_value": sum(c.contract_value for c in active_contracts),
            "total_boq_items_assigned": boq_count,
            "total_assigned_amount": float(boq_amount or 0),
        }

    async def get_boq_items_with_details(
        self, contract_id: str,
        skip: int = 0, limit: int = 20,
    ) -> list[dict]:
        """Get BOQ item assignments with BOQ item details."""
        conditions = [
            self._scope(SubcontractorBOQItem),
            SubcontractorBOQItem.contract_id == contract_id,
        ]

        result = await self.db.execute(
            select(SubcontractorBOQItem).where(and_(*conditions))
            .order_by(SubcontractorBOQItem.created_at.desc())
            .offset(skip).limit(limit)
        )
        assignments = list(result.scalars().all())

        items = []
        for a in assignments:
            boq_result = await self.db.execute(
                select(BOQItem).where(BOQItem.id == a.boq_item_id)
            )
            boq = boq_result.scalar_one_or_none()
            items.append({
                "id": a.id,
                "boq_item_id": a.boq_item_id,
                "item_number": boq.item_number if boq else "",
                "description": boq.description if boq else "",
                "unit": boq.unit.value if boq else "",
                "boq_quantity": boq.quantity if boq else 0,
                "boq_unit_rate": boq.unit_rate if boq else 0,
                "assigned_quantity": a.assigned_quantity,
                "unit_rate": a.unit_rate,
                "contract_amount": a.contract_amount,
                "status": a.status,
                "version": a.version,
                "created_at": a.created_at,
            })

        return items
