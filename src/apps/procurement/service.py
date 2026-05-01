from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from src.apps.procurement.models import (
    Vendor, RFQ, RFQItem, RFQVendor, Quotation, QuotationItem,
    PurchaseOrder, POItem, GRN, GRNItem,
    POStatus, GRNStatus, RFQStatus, QuotationStatus
)
from src.apps.procurement.schemas import (
    CreateVendorRequest, UpdateVendorRequest,
    CreateRFQRequest, CreateQuotationRequest,
    CreatePORequest, CreateGRNRequest,
)
from src.core.exceptions import NotFoundError, ConflictError, ValidationError
import uuid


def _next_number(prefix: str) -> str:
    short = str(uuid.uuid4())[:8].upper()
    return f"{prefix}-{short}"


class ProcurementService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(
            model.tenant_id == self.tenant_id,
            model.deleted_at.is_(None),
        )

    # ── Vendors ───────────────────────────────────────────────────

    async def create_vendor(self, data: CreateVendorRequest) -> Vendor:
        exists = await self.db.execute(
            select(Vendor).where(and_(
                Vendor.tenant_id == self.tenant_id,
                Vendor.code == data.code.upper(),
                Vendor.deleted_at.is_(None),
            ))
        )
        if exists.scalar_one_or_none():
            raise ConflictError(f"Vendor code '{data.code}' already exists")

        vendor = Vendor(
            **data.model_dump(),
            code=data.code.upper(),
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(vendor)
        await self.db.flush()
        return vendor

    async def list_vendors(self, search: str | None = None) -> list[Vendor]:
        conditions = [self._scope(Vendor)]
        if search:
            conditions.append(
                Vendor.name.ilike(f"%{search}%") | Vendor.code.ilike(f"%{search}%")
            )
        result = await self.db.execute(
            select(Vendor).where(and_(*conditions)).order_by(Vendor.name)
        )
        return list(result.scalars().all())

    async def get_vendor(self, vendor_id: str) -> Vendor:
        result = await self.db.execute(
            select(Vendor).where(and_(Vendor.id == vendor_id, self._scope(Vendor)))
        )
        v = result.scalar_one_or_none()
        if not v:
            raise NotFoundError("Vendor")
        return v

    async def update_vendor(self, vendor_id: str, data: UpdateVendorRequest) -> Vendor:
        vendor = await self.get_vendor(vendor_id)
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(vendor, k, v)
        vendor.updated_by = self.user_id
        await self.db.flush()
        return vendor

    # ── RFQ ───────────────────────────────────────────────────────

    async def create_rfq(self, project_id: str, data: CreateRFQRequest) -> RFQ:
        rfq = RFQ(
            project_id=project_id,
            rfq_number=_next_number("RFQ"),
            title=data.title,
            description=data.description,
            due_date=data.due_date,
            delivery_address=data.delivery_address,
            terms_conditions=data.terms_conditions,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(rfq)
        await self.db.flush()

        for i, item_data in enumerate(data.items):
            item = RFQItem(
                **item_data.model_dump(),
                rfq_id=rfq.id,
                tenant_id=self.tenant_id,
                sort_order=i,
                created_by=self.user_id,
            )
            self.db.add(item)

        for vendor_id in data.vendor_ids:
            rv = RFQVendor(
                rfq_id=rfq.id,
                vendor_id=vendor_id,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(rv)

        await self.db.flush()
        return rfq

    async def list_rfqs(self, project_id: str) -> list[RFQ]:
        result = await self.db.execute(
            select(RFQ).where(and_(
                RFQ.project_id == project_id,
                self._scope(RFQ),
            )).order_by(RFQ.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_rfq(self, rfq_id: str) -> RFQ:
        result = await self.db.execute(
            select(RFQ).where(and_(RFQ.id == rfq_id, self._scope(RFQ)))
        )
        rfq = result.scalar_one_or_none()
        if not rfq:
            raise NotFoundError("RFQ")
        return rfq

    async def send_rfq(self, rfq_id: str) -> RFQ:
        rfq = await self.get_rfq(rfq_id)
        if rfq.status != RFQStatus.DRAFT:
            raise ValidationError("Only draft RFQs can be sent")
        rfq.status = RFQStatus.SENT
        rfq.updated_by = self.user_id
        await self.db.flush()
        return rfq

    # ── Quotation ─────────────────────────────────────────────────

    async def create_quotation(self, data: CreateQuotationRequest) -> Quotation:
        await self.get_rfq(data.rfq_id)
        await self.get_vendor(data.vendor_id)

        total = sum(i.quantity * i.unit_rate for i in data.items)
        quotation = Quotation(
            rfq_id=data.rfq_id,
            vendor_id=data.vendor_id,
            quotation_number=data.quotation_number,
            valid_until=data.valid_until,
            delivery_days=data.delivery_days,
            notes=data.notes,
            total_amount=round(total, 2),
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(quotation)
        await self.db.flush()

        for item_data in data.items:
            amount = round(item_data.quantity * item_data.unit_rate, 2)
            item = QuotationItem(
                **item_data.model_dump(),
                quotation_id=quotation.id,
                amount=amount,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(item)

        await self.db.flush()
        return quotation

    async def list_quotations(self, rfq_id: str) -> list[Quotation]:
        result = await self.db.execute(
            select(Quotation).where(and_(
                Quotation.rfq_id == rfq_id,
                self._scope(Quotation),
            ))
        )
        return list(result.scalars().all())

    async def accept_quotation(self, quotation_id: str) -> Quotation:
        result = await self.db.execute(
            select(Quotation).where(and_(
                Quotation.id == quotation_id,
                self._scope(Quotation),
            ))
        )
        q = result.scalar_one_or_none()
        if not q:
            raise NotFoundError("Quotation")
        q.status = QuotationStatus.ACCEPTED
        await self.db.flush()
        return q

    # ── Purchase Order ────────────────────────────────────────────

    async def create_po(self, project_id: str, data: CreatePORequest) -> PurchaseOrder:
        await self.get_vendor(data.vendor_id)

        total = sum(i.quantity * i.unit_rate for i in data.items)
        tax = round(total * 0.13, 2)  # 13% VAT Nepal

        po = PurchaseOrder(
            project_id=project_id,
            vendor_id=data.vendor_id,
            quotation_id=data.quotation_id,
            po_number=_next_number("PO"),
            delivery_date=data.delivery_date,
            delivery_address=data.delivery_address,
            payment_terms=data.payment_terms,
            currency=data.currency,
            notes=data.notes,
            total_amount=round(total, 2),
            tax_amount=tax,
            grand_total=round(total + tax, 2),
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(po)
        await self.db.flush()

        for item_data in data.items:
            amount = round(item_data.quantity * item_data.unit_rate, 2)
            item = POItem(
                **item_data.model_dump(),
                po_id=po.id,
                amount=amount,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(item)

        await self.db.flush()
        return po

    async def list_pos(self, project_id: str) -> list[PurchaseOrder]:
        result = await self.db.execute(
            select(PurchaseOrder).where(and_(
                PurchaseOrder.project_id == project_id,
                self._scope(PurchaseOrder),
            )).order_by(PurchaseOrder.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_po(self, po_id: str) -> PurchaseOrder:
        result = await self.db.execute(
            select(PurchaseOrder).where(and_(
                PurchaseOrder.id == po_id,
                self._scope(PurchaseOrder),
            ))
        )
        po = result.scalar_one_or_none()
        if not po:
            raise NotFoundError("Purchase Order")
        return po

    async def approve_po(self, po_id: str) -> PurchaseOrder:
        po = await self.get_po(po_id)
        if po.status != POStatus.PENDING_APPROVAL:
            raise ValidationError("PO must be in pending_approval status to approve")
        po.status = POStatus.APPROVED
        po.approved_by = self.user_id
        await self.db.flush()
        return po

    async def submit_po(self, po_id: str) -> PurchaseOrder:
        po = await self.get_po(po_id)
        if po.status != POStatus.DRAFT:
            raise ValidationError("Only draft POs can be submitted for approval")
        po.status = POStatus.PENDING_APPROVAL
        await self.db.flush()
        return po

    # ── GRN ───────────────────────────────────────────────────────

    async def create_grn(self, project_id: str, data: CreateGRNRequest) -> GRN:
        po = await self.get_po(data.po_id)
        if po.status not in [POStatus.APPROVED, POStatus.SENT, POStatus.PARTIALLY_RECEIVED]:
            raise ValidationError("PO must be approved before receiving goods")

        grn = GRN(
            po_id=data.po_id,
            project_id=project_id,
            grn_number=_next_number("GRN"),
            received_date=data.received_date,
            delivery_note=data.delivery_note,
            inspection_passed=data.inspection_passed,
            notes=data.notes,
            received_by=self.user_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(grn)
        await self.db.flush()

        for item_data in data.items:
            amount = round(item_data.received_quantity * item_data.unit_rate, 2)
            grn_item = GRNItem(
                **item_data.model_dump(),
                grn_id=grn.id,
                amount=amount,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(grn_item)

            # Update received quantity on PO item
            await self.db.execute(
                update(POItem)
                .where(POItem.id == item_data.po_item_id)
                .values(
                    received_quantity=POItem.received_quantity + item_data.received_quantity
                )
            )

        # Update PO status
        await self._update_po_receipt_status(data.po_id)
        await self.db.flush()
        return grn

    async def _update_po_receipt_status(self, po_id: str) -> None:
        result = await self.db.execute(
            select(
                func.sum(POItem.quantity).label("ordered"),
                func.sum(POItem.received_quantity).label("received"),
            ).where(POItem.po_id == po_id)
        )
        row = result.one()
        ordered = row.ordered or 0
        received = row.received or 0

        if received >= ordered:
            new_status = POStatus.FULLY_RECEIVED
        elif received > 0:
            new_status = POStatus.PARTIALLY_RECEIVED
        else:
            return

        await self.db.execute(
            update(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .values(status=new_status)
        )

    async def list_grns(self, project_id: str) -> list[GRN]:
        result = await self.db.execute(
            select(GRN).where(and_(
                GRN.project_id == project_id,
                self._scope(GRN),
            )).order_by(GRN.created_at.desc())
        )
        return list(result.scalars().all())

    async def confirm_grn(self, grn_id: str) -> GRN:
        result = await self.db.execute(
            select(GRN).where(and_(GRN.id == grn_id, self._scope(GRN)))
        )
        grn = result.scalar_one_or_none()
        if not grn:
            raise NotFoundError("GRN")
        grn.status = GRNStatus.CONFIRMED
        await self.db.flush()
        return grn

    async def get_procurement_stats(self, project_id: str) -> dict:
        po_result = await self.db.execute(
            select(
                func.count(PurchaseOrder.id).label("total"),
                func.sum(PurchaseOrder.grand_total).label("total_value"),
            ).where(and_(
                PurchaseOrder.project_id == project_id,
                self._scope(PurchaseOrder),
            ))
        )
        row = po_result.one()
        pending_result = await self.db.execute(
            select(func.count(PurchaseOrder.id)).where(and_(
                PurchaseOrder.project_id == project_id,
                PurchaseOrder.status == POStatus.PENDING_APPROVAL,
                self._scope(PurchaseOrder),
            ))
        )
        return {
            "total_pos": row.total or 0,
            "total_po_value": row.total_value or 0.0,
            "pending_approval": pending_result.scalar_one() or 0,
        }