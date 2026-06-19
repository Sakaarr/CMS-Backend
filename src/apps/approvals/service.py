from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.boq.models import BudgetVersion, BudgetVersionStatus
from src.apps.documents.models import ApprovalStatus, Document, DocumentApproval, DocumentStatus
from src.apps.finance.models import ChangeOrder, ChangeOrderStatus, Expense, ExpenseStatus, Invoice, InvoiceStatus
from src.apps.identity.models import UserPermission
from src.apps.inventory.models import MaterialRequest, MaterialRequestStatus
from src.apps.projects.models import Project
from src.apps.procurement.models import POStatus, PurchaseOrder
from src.apps.approvals.schemas import ApprovalInboxItem


class ApprovalInboxService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(model.tenant_id == self.tenant_id, model.deleted_at.is_(None))

    def _item(
        self,
        *,
        id: str,
        module: str,
        item_type: str,
        title: str,
        status: str,
        created_at,
        project_id: str | None = None,
        project_name: str | None = None,
        project_code: str | None = None,
        subtitle: str | None = None,
        action_url: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> ApprovalInboxItem:
        clean_meta = {
            key: value
            for key, value in (meta or {}).items()
            if value is not None
        }
        return ApprovalInboxItem(
            id=id,
            module=module,
            item_type=item_type,
            title=title,
            subtitle=subtitle,
            status=status,
            project_id=project_id,
            project_name=project_name,
            project_code=project_code,
            created_at=created_at,
            action_url=action_url,
            meta=clean_meta,
        )

    async def _pending_finance(self) -> list[ApprovalInboxItem]:
        items: list[ApprovalInboxItem] = []

        invoice_rows = await self.db.execute(
            select(
                Invoice.id,
                Invoice.invoice_number,
                Invoice.status,
                Invoice.grand_total,
                Invoice.currency,
                Invoice.created_at,
                Project.id,
                Project.name,
                Project.code,
            )
            .join(Project, Project.id == Invoice.project_id)
            .where(and_(
                self._scope(Invoice),
                self._scope(Project),
                Invoice.status == InvoiceStatus.SUBMITTED,
            ))
            .order_by(Invoice.created_at.desc())
        )
        for row in invoice_rows.all():
            items.append(self._item(
                id=row[0],
                module="finance",
                item_type="invoice_approval",
                title=f"Invoice {row[1]}",
                subtitle="Invoice awaiting approval",
                status=row[2].value if hasattr(row[2], "value") else str(row[2]),
                project_id=row[6],
                project_name=row[7],
                project_code=row[8],
                created_at=row[5],
                action_url=f"/finance?projectId={row[6]}",
                meta={
                    "invoice_number": row[1],
                    "grand_total": row[3],
                    "currency": row[4],
                },
            ))

        expense_rows = await self.db.execute(
            select(
                Expense.id,
                Expense.expense_number,
                Expense.status,
                Expense.total_amount,
                Expense.currency,
                Expense.created_at,
                Project.id,
                Project.name,
                Project.code,
            )
            .join(Project, Project.id == Expense.project_id)
            .where(and_(
                self._scope(Expense),
                self._scope(Project),
                Expense.status == ExpenseStatus.SUBMITTED,
            ))
            .order_by(Expense.created_at.desc())
        )
        for row in expense_rows.all():
            items.append(self._item(
                id=row[0],
                module="finance",
                item_type="expense_approval",
                title=f"Expense {row[1]}",
                subtitle="Expense awaiting approval",
                status=row[2].value if hasattr(row[2], "value") else str(row[2]),
                project_id=row[6],
                project_name=row[7],
                project_code=row[8],
                created_at=row[5],
                action_url=f"/finance?projectId={row[6]}",
                meta={
                    "expense_number": row[1],
                    "total_amount": row[3],
                    "currency": row[4],
                },
            ))

        co_rows = await self.db.execute(
            select(
                ChangeOrder.id,
                ChangeOrder.co_number,
                ChangeOrder.status,
                ChangeOrder.amount,
                ChangeOrder.created_at,
                Project.id,
                Project.name,
                Project.code,
            )
            .join(Project, Project.id == ChangeOrder.project_id)
            .where(and_(
                self._scope(ChangeOrder),
                self._scope(Project),
                ChangeOrder.status == ChangeOrderStatus.SUBMITTED,
            ))
            .order_by(ChangeOrder.created_at.desc())
        )
        for row in co_rows.all():
            items.append(self._item(
                id=row[0],
                module="finance",
                item_type="change_order_approval",
                title=f"Change Order {row[1]}",
                subtitle="Change order awaiting approval",
                status=row[2].value if hasattr(row[2], "value") else str(row[2]),
                project_id=row[5],
                project_name=row[6],
                project_code=row[7],
                created_at=row[4],
                action_url=f"/finance?projectId={row[5]}",
                meta={
                    "co_number": row[1],
                    "amount": row[3],
                },
            ))

        return items

    async def _pending_procurement(self) -> list[ApprovalInboxItem]:
        rows = await self.db.execute(
            select(
                PurchaseOrder.id,
                PurchaseOrder.po_number,
                PurchaseOrder.status,
                PurchaseOrder.grand_total,
                PurchaseOrder.currency,
                PurchaseOrder.created_at,
                Project.id,
                Project.name,
                Project.code,
            )
            .join(Project, Project.id == PurchaseOrder.project_id)
            .where(and_(
                self._scope(PurchaseOrder),
                self._scope(Project),
                PurchaseOrder.status == POStatus.PENDING_APPROVAL,
            ))
            .order_by(PurchaseOrder.created_at.desc())
        )
        items: list[ApprovalInboxItem] = []
        for row in rows.all():
            items.append(self._item(
                id=row[0],
                module="procurement",
                item_type="purchase_order_approval",
                title=f"PO {row[1]}",
                subtitle="Purchase order awaiting approval",
                status=row[2].value if hasattr(row[2], "value") else str(row[2]),
                project_id=row[6],
                project_name=row[7],
                project_code=row[8],
                created_at=row[5],
                action_url=f"/procurement?projectId={row[6]}",
                meta={
                    "po_number": row[1],
                    "grand_total": row[3],
                    "currency": row[4],
                },
            ))
        return items

    async def _pending_inventory(self) -> list[ApprovalInboxItem]:
        rows = await self.db.execute(
            select(
                MaterialRequest.id,
                MaterialRequest.mr_number,
                MaterialRequest.status,
                MaterialRequest.created_at,
                Project.id,
                Project.name,
                Project.code,
            )
            .join(Project, Project.id == MaterialRequest.project_id)
            .where(and_(
                self._scope(MaterialRequest),
                self._scope(Project),
                MaterialRequest.status == MaterialRequestStatus.SUBMITTED,
            ))
            .order_by(MaterialRequest.created_at.desc())
        )
        items: list[ApprovalInboxItem] = []
        for row in rows.all():
            items.append(self._item(
                id=row[0],
                module="inventory",
                item_type="material_request_approval",
                title=f"Material Request {row[1]}",
                subtitle="Material request awaiting approval",
                status=row[2].value if hasattr(row[2], "value") else str(row[2]),
                project_id=row[4],
                project_name=row[5],
                project_code=row[6],
                created_at=row[3],
                action_url=f"/inventory?projectId={row[4]}",
                meta={"mr_number": row[1]},
            ))
        return items

    async def _pending_boq(self) -> list[ApprovalInboxItem]:
        rows = await self.db.execute(
            select(
                BudgetVersion.id,
                BudgetVersion.name,
                BudgetVersion.version_number,
                BudgetVersion.status,
                BudgetVersion.grand_total,
                BudgetVersion.currency,
                BudgetVersion.created_at,
                Project.id,
                Project.name,
                Project.code,
            )
            .join(Project, Project.id == BudgetVersion.project_id)
            .where(and_(
                self._scope(BudgetVersion),
                self._scope(Project),
                BudgetVersion.status == BudgetVersionStatus.SUBMITTED,
            ))
            .order_by(BudgetVersion.created_at.desc())
        )
        items: list[ApprovalInboxItem] = []
        for row in rows.all():
            items.append(self._item(
                id=row[0],
                module="boq",
                item_type="budget_version_approval",
                title=f"Budget Version {row[1]}",
                subtitle=f"Version {row[2]} awaiting approval",
                status=row[3].value if hasattr(row[3], "value") else str(row[3]),
                project_id=row[7],
                project_name=row[8],
                project_code=row[9],
                created_at=row[6],
                action_url=f"/boq?projectId={row[7]}",
                meta={
                    "version_name": row[1],
                    "version_number": row[2],
                    "grand_total": row[4],
                    "currency": row[5],
                },
            ))
        return items

    async def _pending_documents(self) -> list[ApprovalInboxItem]:
        rows = await self.db.execute(
            select(
                DocumentApproval.id,
                DocumentApproval.approver_name,
                DocumentApproval.status,
                DocumentApproval.sequence,
                DocumentApproval.created_at,
                Document.id,
                Document.document_number,
                Document.title,
                Document.status,
                Project.id,
                Project.name,
                Project.code,
            )
            .join(Document, Document.id == DocumentApproval.document_id)
            .join(Project, Project.id == Document.project_id)
            .where(and_(
                self._scope(DocumentApproval),
                self._scope(Document),
                self._scope(Project),
                DocumentApproval.approver_id == self.user_id,
                DocumentApproval.status == ApprovalStatus.PENDING,
            ))
            .order_by(DocumentApproval.created_at.desc())
        )
        items: list[ApprovalInboxItem] = []
        for row in rows.all():
            items.append(self._item(
                id=row[0],
                module="documents",
                item_type="document_review",
                title=f"Document {row[6]}",
                subtitle=row[7],
                status=row[2].value if hasattr(row[2], "value") else str(row[2]),
                project_id=row[9],
                project_name=row[10],
                project_code=row[11],
                created_at=row[4],
                action_url=f"/documents?projectId={row[9]}",
                meta={
                    "document_id": row[5],
                    "document_number": row[6],
                    "document_status": row[8].value if hasattr(row[8], "value") else str(row[8]),
                    "approver_name": row[1],
                    "sequence": row[3],
                },
            ))
        return items

    async def get_inbox(self, allowed_modules: set[str], limit: int = 100) -> dict:
        items: list[ApprovalInboxItem] = []

        if "finance" in allowed_modules:
            items.extend(await self._pending_finance())
        if "procurement" in allowed_modules:
            items.extend(await self._pending_procurement())
        if "inventory" in allowed_modules:
            items.extend(await self._pending_inventory())
        if "boq" in allowed_modules:
            items.extend(await self._pending_boq())
        if "documents" in allowed_modules:
            items.extend(await self._pending_documents())

        items.sort(key=lambda item: item.created_at, reverse=True)
        counts = Counter(item.module for item in items)
        return {
            "total": len(items),
            "counts": dict(counts),
            "items": items[:limit],
        }
