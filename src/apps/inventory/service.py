from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from src.apps.inventory.models import (
    Warehouse, StockItem, StockTransaction, MaterialRequest,
    MaterialRequestItem, TransactionType, MaterialRequestStatus
)
from src.apps.inventory.schemas import (
    CreateWarehouseRequest, StockAdjustmentRequest, CreateMRRequest
)
from src.core.exceptions import NotFoundError, ConflictError, ValidationError
import uuid


def _mr_number() -> str:
    return f"MR-{str(uuid.uuid4())[:8].upper()}"


class InventoryService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    # ── Warehouses ────────────────────────────────────────────────

    async def create_warehouse(self, data: CreateWarehouseRequest) -> Warehouse:
        exists = await self.db.execute(
            select(Warehouse).where(and_(
                Warehouse.tenant_id == self.tenant_id,
                Warehouse.code == data.code.upper(),
                Warehouse.deleted_at.is_(None),
            ))
        )
        if exists.scalar_one_or_none():
            raise ConflictError(f"Warehouse code '{data.code}' already exists")

        wh = Warehouse(
            **data.model_dump(),
            code=data.code.upper(),
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(wh)
        await self.db.flush()
        return wh

    async def list_warehouses(self, project_id: str | None = None) -> list[Warehouse]:
        conditions = [self._scope(Warehouse)]
        if project_id:
            conditions.append(Warehouse.project_id == project_id)
        result = await self.db.execute(
            select(Warehouse).where(and_(*conditions)).order_by(Warehouse.name)
        )
        return list(result.scalars().all())

    async def get_warehouse(self, warehouse_id: str) -> Warehouse:
        result = await self.db.execute(
            select(Warehouse).where(and_(
                Warehouse.id == warehouse_id, self._scope(Warehouse)
            ))
        )
        wh = result.scalar_one_or_none()
        if not wh:
            raise NotFoundError("Warehouse")
        return wh

    # ── Stock ─────────────────────────────────────────────────────

    async def get_or_create_stock_item(
        self, warehouse_id: str, material_code: str,
        description: str, unit: str, unit_cost: float
    ) -> StockItem:
        result = await self.db.execute(
            select(StockItem).where(and_(
                StockItem.warehouse_id == warehouse_id,
                StockItem.material_code == material_code,
                self._scope(StockItem),
            ))
        )
        item = result.scalar_one_or_none()
        if not item:
            item = StockItem(
                warehouse_id=warehouse_id,
                material_code=material_code,
                description=description,
                unit=unit,
                unit_cost=unit_cost,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(item)
            await self.db.flush()
        return item

    async def record_transaction(
        self, warehouse_id: str, data: StockAdjustmentRequest,
        project_id: str | None = None
    ) -> StockTransaction:
        await self.get_warehouse(warehouse_id)

        stock_item = await self.get_or_create_stock_item(
            warehouse_id, data.material_code,
            data.description, data.unit, data.unit_cost
        )

        # Calculate new balance
        if data.transaction_type in [
            TransactionType.RECEIPT, TransactionType.RETURN, TransactionType.ADJUSTMENT
        ]:
            new_balance = stock_item.quantity_on_hand + data.quantity
        elif data.transaction_type in [
            TransactionType.ISSUE, TransactionType.CONSUMPTION, TransactionType.TRANSFER
        ]:
            if data.quantity > stock_item.quantity_on_hand:
                raise ValidationError(
                    f"Insufficient stock. Available: {stock_item.quantity_on_hand} {data.unit}"
                )
            new_balance = stock_item.quantity_on_hand - data.quantity
        else:
            new_balance = stock_item.quantity_on_hand

        total_cost = round(data.quantity * data.unit_cost, 2)

        txn = StockTransaction(
            stock_item_id=stock_item.id,
            warehouse_id=warehouse_id,
            project_id=project_id,
            transaction_type=data.transaction_type,
            quantity=data.quantity,
            unit_cost=data.unit_cost,
            total_cost=total_cost,
            reference_type=data.reference_type,
            reference_id=data.reference_id,
            notes=data.notes,
            balance_after=new_balance,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(txn)

        stock_item.quantity_on_hand = new_balance
        if data.unit_cost > 0:
            stock_item.unit_cost = data.unit_cost
        await self.db.flush()
        return txn

    async def list_stock(self, warehouse_id: str) -> list[StockItem]:
        await self.get_warehouse(warehouse_id)
        result = await self.db.execute(
            select(StockItem).where(and_(
                StockItem.warehouse_id == warehouse_id,
                self._scope(StockItem),
            )).order_by(StockItem.material_code)
        )
        return list(result.scalars().all())

    async def list_transactions(self, warehouse_id: str, stock_item_id: str) -> list[StockTransaction]:
        result = await self.db.execute(
            select(StockTransaction).where(and_(
                StockTransaction.warehouse_id == warehouse_id,
                StockTransaction.stock_item_id == stock_item_id,
                self._scope(StockTransaction),
            )).order_by(StockTransaction.created_at.desc()).limit(50)
        )
        return list(result.scalars().all())

    async def get_low_stock_alerts(self, project_id: str | None = None) -> list[StockItem]:
        conditions = [self._scope(StockItem)]
        if project_id:
            wh_result = await self.db.execute(
                select(Warehouse.id).where(and_(
                    Warehouse.project_id == project_id,
                    self._scope(Warehouse),
                ))
            )
            wh_ids = [r[0] for r in wh_result.all()]
            if wh_ids:
                conditions.append(StockItem.warehouse_id.in_(wh_ids))

        result = await self.db.execute(
            select(StockItem).where(and_(
                *conditions,
                StockItem.reorder_level > 0,
                StockItem.quantity_on_hand <= StockItem.reorder_level,
            ))
        )
        return list(result.scalars().all())

    # ── Material Requests ─────────────────────────────────────────

    async def create_mr(self, project_id: str, data: CreateMRRequest) -> MaterialRequest:
        mr = MaterialRequest(
            project_id=project_id,
            site_id=data.site_id,
            from_warehouse_id=data.from_warehouse_id,
            mr_number=_mr_number(),
            required_date=data.required_date,
            purpose=data.purpose,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(mr)
        await self.db.flush()

        for item_data in data.items:
            item = MaterialRequestItem(
                **item_data.model_dump(),
                request_id=mr.id,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(item)

        await self.db.flush()
        return mr

    async def list_mrs(self, project_id: str) -> list[MaterialRequest]:
        result = await self.db.execute(
            select(MaterialRequest).where(and_(
                MaterialRequest.project_id == project_id,
                self._scope(MaterialRequest),
            )).order_by(MaterialRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_mr(self, mr_id: str) -> MaterialRequest:
        result = await self.db.execute(
            select(MaterialRequest).where(and_(
                MaterialRequest.id == mr_id, self._scope(MaterialRequest)
            ))
        )
        mr = result.scalar_one_or_none()
        if not mr:
            raise NotFoundError("Material Request")
        return mr

    async def approve_mr(self, mr_id: str, approved_items: list[dict]) -> MaterialRequest:
        mr = await self.get_mr(mr_id)
        if mr.status != MaterialRequestStatus.SUBMITTED:
            raise ValidationError("Only submitted MRs can be approved")

        for ai in approved_items:
            await self.db.execute(
                update(MaterialRequestItem)
                .where(MaterialRequestItem.id == ai["item_id"])
                .values(approved_quantity=ai["approved_quantity"])
            )

        mr.status = MaterialRequestStatus.APPROVED
        mr.approved_by = self.user_id
        await self.db.flush()
        return mr

    async def issue_mr(self, mr_id: str) -> MaterialRequest:
        mr = await self.get_mr(mr_id)
        if mr.status != MaterialRequestStatus.APPROVED:
            raise ValidationError("Only approved MRs can be issued")
        if not mr.from_warehouse_id:
            raise ValidationError("No source warehouse specified for this MR")

        result = await self.db.execute(
            select(MaterialRequestItem).where(
                MaterialRequestItem.request_id == mr_id
            )
        )
        items = result.scalars().all()

        for item in items:
            if item.approved_quantity > 0:
                await self.record_transaction(
                    warehouse_id=mr.from_warehouse_id,
                    data=StockAdjustmentRequest(
                        material_code=item.material_code,
                        description=item.description,
                        unit=item.unit,
                        quantity=item.approved_quantity,
                        transaction_type=TransactionType.ISSUE,
                        reference_type="material_request",
                        reference_id=mr_id,
                    ),
                    project_id=mr.project_id,
                )
                item.issued_quantity = item.approved_quantity

        mr.status = MaterialRequestStatus.ISSUED
        mr.issued_by = self.user_id
        await self.db.flush()
        return mr

    async def submit_mr(self, mr_id: str) -> MaterialRequest:
        mr = await self.get_mr(mr_id)
        if mr.status != MaterialRequestStatus.DRAFT:
            raise ValidationError("Only draft MRs can be submitted")
        mr.status = MaterialRequestStatus.SUBMITTED
        await self.db.flush()
        return mr