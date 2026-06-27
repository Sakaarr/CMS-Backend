from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
from src.apps.finance.models import (
    Invoice, InvoiceLineItem, Payment,
    Expense, ChangeOrder, PaymentCertificate,
    InvoiceStatus, InvoiceType, ExpenseStatus,
    ExpenseCategory,
    ChangeOrderStatus, PaymentCertStatus,
)
from src.apps.finance.schemas import (
    CreateInvoiceRequest, UpdateInvoiceRequest, RecordPaymentRequest,
    CreateExpenseRequest, CreateChangeOrderRequest, CreatePaymentCertRequest,
)
from src.apps.projects.models import Project
from src.apps.identity.models import User
from src.core.exceptions import (
    NotFoundError, ConflictError, ValidationError
)
from src.core.email_templates import (
    approval_requested_html, item_approved_html, item_rejected_html,
    notify_permission_holders, notify_user_by_id,
)
import logging
import uuid

logger = logging.getLogger(__name__)


def _num(prefix: str) -> str:
    return f"{prefix}-{str(uuid.uuid4())[:8].upper()}"


class FinanceService:
    def __init__(self, db: AsyncSession, tenant_id: str, user_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _scope(self, model):
        return and_(
            model.tenant_id == self.tenant_id,
            model.deleted_at.is_(None),
        )

    # ── Invoices ──────────────────────────────────────────────────

    def _calculate_invoice_totals(
        self, line_items: list, discount: float,
        vat_rate: float, retention_rate: float
    ) -> dict:
        subtotal = round(sum(i.quantity * i.unit_rate for i in line_items), 2)
        taxable = round(subtotal - discount, 2)
        vat = round(taxable * vat_rate / 100, 2)
        gross = round(taxable + vat, 2)
        retention = round(gross * retention_rate / 100, 2)
        grand_total = round(gross - retention, 2)
        return {
            "subtotal": subtotal,
            "taxable_amount": taxable,
            "vat_amount": vat,
            "retention_amount": retention,
            "grand_total": grand_total,
            "balance_due": grand_total,
        }

    async def create_invoice(
        self, project_id: str, data: CreateInvoiceRequest
    ) -> Invoice:
        totals = self._calculate_invoice_totals(
            data.line_items, data.discount_amount,
            data.vat_rate, data.retention_rate,
        )
        invoice = Invoice(
            project_id=project_id,
            invoice_number=_num("INV"),
            invoice_type=data.invoice_type,
            client_name=data.client_name,
            vendor_id=data.vendor_id,
            billing_address=data.billing_address,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            period_from=data.period_from,
            period_to=data.period_to,
            vat_rate=data.vat_rate,
            retention_rate=data.retention_rate,
            discount_amount=data.discount_amount,
            currency=data.currency,
            notes=data.notes,
            terms=data.terms,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
            **totals,
        )
        self.db.add(invoice)
        await self.db.flush()

        for i, item in enumerate(data.line_items):
            li = InvoiceLineItem(
                invoice_id=invoice.id,
                description=item.description,
                unit=item.unit,
                quantity=item.quantity,
                unit_rate=item.unit_rate,
                amount=round(item.quantity * item.unit_rate, 2),
                sort_order=i,
                boq_item_id=item.boq_item_id,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
            )
            self.db.add(li)

        await self.db.flush()
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(and_(Invoice.id == invoice.id, self._scope(Invoice)))
        )
        return result.scalar_one()

    async def list_invoices(
        self,
        project_id: str,
        invoice_type: InvoiceType | None = None,
        status: InvoiceStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Invoice], int]:
        conditions = [
            Invoice.project_id == project_id,
            self._scope(Invoice),
        ]
        if invoice_type:
            conditions.append(Invoice.invoice_type == invoice_type)
        if status:
            conditions.append(Invoice.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(Invoice).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(Invoice)
            .where(and_(*conditions))
            .order_by(Invoice.invoice_date.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_invoice(self, invoice_id: str) -> Invoice:
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(and_(Invoice.id == invoice_id, self._scope(Invoice)))
        )
        inv = result.scalar_one_or_none()
        if not inv:
            raise NotFoundError("Invoice")
        return inv

    async def approve_invoice(self, invoice_id: str) -> Invoice:
        inv = await self.get_invoice(invoice_id)
        if inv.status != InvoiceStatus.SUBMITTED:
            raise ValidationError("Only submitted invoices can be approved")
        inv.status = InvoiceStatus.APPROVED
        inv.approved_by = self.user_id
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == inv.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            approver_name = (await self.db.execute(
                select(User.full_name).where(User.id == self.user_id)
            )).scalar_one_or_none() or "An approver"
            html = item_approved_html("Invoice", inv.invoice_number, proj_name, approver_name)
            await notify_user_by_id(self.db, inv.created_by, f"Invoice {inv.invoice_number} Approved", html)
        except Exception as e:
            logger.warning(f"Failed to send invoice approval email: {e}")

        return inv

    async def submit_invoice(self, invoice_id: str) -> Invoice:
        inv = await self.get_invoice(invoice_id)
        if inv.status != InvoiceStatus.DRAFT:
            raise ValidationError("Only draft invoices can be submitted")
        inv.status = InvoiceStatus.SUBMITTED
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == inv.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            submitter_name = (await self.db.execute(
                select(User.full_name).where(User.id == self.user_id)
            )).scalar_one_or_none() or "A user"
            html = approval_requested_html("Invoice", inv.invoice_number, proj_name, submitter_name)
            await notify_permission_holders(
                self.db, self.tenant_id, "can_finance",
                self.user_id, f"Invoice {inv.invoice_number} Awaiting Approval", html,
            )
        except Exception as e:
            logger.warning(f"Failed to send invoice submission email: {e}")

        return inv

    async def reject_invoice(self, invoice_id: str, reason: str | None = None) -> Invoice:
        inv = await self.get_invoice(invoice_id)
        if inv.status != InvoiceStatus.SUBMITTED:
            raise ValidationError("Only submitted invoices can be rejected")
        inv.status = InvoiceStatus.REJECTED
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == inv.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            html = item_rejected_html("Invoice", inv.invoice_number, proj_name, reason)
            await notify_user_by_id(self.db, inv.created_by, f"Invoice {inv.invoice_number} Rejected", html)
        except Exception as e:
            logger.warning(f"Failed to send invoice rejection email: {e}")

        return inv

    async def record_payment(
        self, invoice_id: str, data: RecordPaymentRequest
    ) -> Payment:
        inv = await self.get_invoice(invoice_id)
        if inv.status not in [
            InvoiceStatus.APPROVED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE
        ]:
            raise ValidationError("Invoice must be approved before recording payment")

        if data.amount > inv.balance_due:
            raise ValidationError(
                f"Payment amount ({data.amount}) exceeds balance due ({inv.balance_due})"
            )

        payment = Payment(
            invoice_id=invoice_id,
            project_id=inv.project_id,
            payment_number=_num("PAY"),
            payment_date=data.payment_date,
            amount=data.amount,
            method=data.method,
            reference=data.reference,
            notes=data.notes,
            received_by=self.user_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(payment)

        new_paid = round(inv.paid_amount + data.amount, 2)
        new_balance = round(inv.grand_total - new_paid, 2)
        inv.paid_amount = new_paid
        inv.balance_due = new_balance

        if new_balance <= 0:
            inv.status = InvoiceStatus.PAID
        else:
            inv.status = InvoiceStatus.PARTIALLY_PAID

        await self.db.flush()
        return payment

    async def check_overdue(self, project_id: str) -> int:
        """Mark overdue invoices — call periodically."""
        today = date.today()
        result = await self.db.execute(
            update(Invoice)
            .where(and_(
                Invoice.project_id == project_id,
                Invoice.tenant_id == self.tenant_id,
                Invoice.status == InvoiceStatus.APPROVED,
                Invoice.due_date < str(today),
                Invoice.balance_due > 0,
            ))
            .values(status=InvoiceStatus.OVERDUE)
        )
        return result.rowcount

    # ── Expenses ──────────────────────────────────────────────────

    async def create_expense(
        self, project_id: str, data: CreateExpenseRequest
    ) -> Expense:
        vat = round(data.amount * 0.13, 2) if data.include_vat else 0.0
        total = round(data.amount + vat, 2)

        expense = Expense(
            project_id=project_id,
            site_id=data.site_id,
            expense_number=_num("EXP"),
            category=data.category,
            description=data.description,
            amount=data.amount,
            vat_amount=vat,
            total_amount=total,
            expense_date=data.expense_date,
            vendor_name=data.vendor_name,
            pan_number=data.pan_number,
            receipt_url=data.receipt_url,
            notes=data.notes,
            boq_item_id=data.boq_item_id,
            submitted_by=self.user_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(expense)
        await self.db.flush()
        return expense

    async def list_expenses(
        self,
        project_id: str,
        category: ExpenseCategory | None = None,
        status: ExpenseStatus | None = None,
        skip: int = 0,
        limit: int = 30,
    ) -> tuple[list[Expense], int]:
        conditions = [
            Expense.project_id == project_id,
            self._scope(Expense),
        ]
        if category:
            conditions.append(Expense.category == category)
        if status:
            conditions.append(Expense.status == status)

        total = (await self.db.execute(
            select(func.count()).select_from(Expense).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(Expense)
            .where(and_(*conditions))
            .order_by(Expense.expense_date.desc())
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_expense(self, expense_id: str) -> Expense:
        result = await self.db.execute(
            select(Expense).where(and_(
                Expense.id == expense_id, self._scope(Expense)
            ))
        )
        exp = result.scalar_one_or_none()
        if not exp:
            raise NotFoundError("Expense")
        return exp

    async def approve_expense(self, expense_id: str) -> Expense:
        exp = await self.get_expense(expense_id)
        if exp.status != ExpenseStatus.SUBMITTED:
            raise ValidationError("Only submitted expenses can be approved")
        exp.status = ExpenseStatus.APPROVED
        exp.approved_by = self.user_id
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == exp.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            approver_name = (await self.db.execute(
                select(User.full_name).where(User.id == self.user_id)
            )).scalar_one_or_none() or "An approver"
            html = item_approved_html("Expense", exp.expense_number, proj_name, approver_name)
            await notify_user_by_id(self.db, exp.created_by, f"Expense {exp.expense_number} Approved", html)
        except Exception as e:
            logger.warning(f"Failed to send expense approval email: {e}")

        return exp

    async def submit_expense(self, expense_id: str) -> Expense:
        exp = await self.get_expense(expense_id)
        if exp.status != ExpenseStatus.DRAFT:
            raise ValidationError("Only draft expenses can be submitted")
        exp.status = ExpenseStatus.SUBMITTED
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == exp.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            submitter_name = (await self.db.execute(
                select(User.full_name).where(User.id == self.user_id)
            )).scalar_one_or_none() or "A user"
            html = approval_requested_html("Expense", exp.expense_number, proj_name, submitter_name)
            await notify_permission_holders(
                self.db, self.tenant_id, "can_finance",
                self.user_id, f"Expense {exp.expense_number} Awaiting Approval", html,
            )
        except Exception as e:
            logger.warning(f"Failed to send expense submission email: {e}")

        return exp

    async def reject_expense(self, expense_id: str, reason: str | None = None) -> Expense:
        exp = await self.get_expense(expense_id)
        if exp.status != ExpenseStatus.SUBMITTED:
            raise ValidationError("Only submitted expenses can be rejected")
        exp.status = ExpenseStatus.REJECTED
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == exp.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            html = item_rejected_html("Expense", exp.expense_number, proj_name, reason)
            await notify_user_by_id(self.db, exp.created_by, f"Expense {exp.expense_number} Rejected", html)
        except Exception as e:
            logger.warning(f"Failed to send expense rejection email: {e}")

        return exp

    # ── Change Orders ─────────────────────────────────────────────

    async def create_change_order(
        self, project_id: str, data: CreateChangeOrderRequest
    ) -> ChangeOrder:
        co = ChangeOrder(
            project_id=project_id,
            co_number=_num("CO"),
            title=data.title,
            description=data.description,
            reason=data.reason,
            amount=data.amount,
            impact_days=data.impact_days,
            original_contract_value=data.original_contract_value,
            requested_by=self.user_id,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
        )
        self.db.add(co)
        await self.db.flush()
        return co

    async def list_change_orders(self, project_id: str) -> list[ChangeOrder]:
        result = await self.db.execute(
            select(ChangeOrder).where(and_(
                ChangeOrder.project_id == project_id,
                self._scope(ChangeOrder),
            )).order_by(ChangeOrder.created_at.desc())
        )
        return list(result.scalars().all())

    async def approve_change_order(self, co_id: str) -> ChangeOrder:
        result = await self.db.execute(
            select(ChangeOrder).where(and_(
                ChangeOrder.id == co_id, self._scope(ChangeOrder)
            ))
        )
        co = result.scalar_one_or_none()
        if not co:
            raise NotFoundError("Change Order")
        if co.status != ChangeOrderStatus.SUBMITTED:
            raise ValidationError("Only submitted change orders can be approved")

        co.status = ChangeOrderStatus.APPROVED
        co.approved_by = self.user_id
        if co.original_contract_value:
            co.revised_contract_value = round(
                co.original_contract_value + co.amount, 2
            )
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == co.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            approver_name = (await self.db.execute(
                select(User.full_name).where(User.id == self.user_id)
            )).scalar_one_or_none() or "An approver"
            html = item_approved_html("Change Order", co.co_number, proj_name, approver_name)
            await notify_user_by_id(self.db, co.created_by, f"CO {co.co_number} Approved", html)
        except Exception as e:
            logger.warning(f"Failed to send CO approval email: {e}")

        return co

    async def submit_change_order(self, co_id: str) -> ChangeOrder:
        result = await self.db.execute(
            select(ChangeOrder).where(and_(
                ChangeOrder.id == co_id, self._scope(ChangeOrder)
            ))
        )
        co = result.scalar_one_or_none()
        if not co:
            raise NotFoundError("Change Order")
        if co.status != ChangeOrderStatus.DRAFT:
            raise ValidationError("Only draft change orders can be submitted")
        co.status = ChangeOrderStatus.SUBMITTED
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == co.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            submitter_name = (await self.db.execute(
                select(User.full_name).where(User.id == self.user_id)
            )).scalar_one_or_none() or "A user"
            html = approval_requested_html("Change Order", co.co_number, proj_name, submitter_name)
            await notify_permission_holders(
                self.db, self.tenant_id, "can_finance",
                self.user_id, f"CO {co.co_number} Awaiting Approval", html,
            )
        except Exception as e:
            logger.warning(f"Failed to send CO submission email: {e}")

        return co

    async def reject_change_order(self, co_id: str, reason: str | None = None) -> ChangeOrder:
        result = await self.db.execute(
            select(ChangeOrder).where(and_(
                ChangeOrder.id == co_id, self._scope(ChangeOrder)
            ))
        )
        co = result.scalar_one_or_none()
        if not co:
            raise NotFoundError("Change Order")
        if co.status != ChangeOrderStatus.SUBMITTED:
            raise ValidationError("Only submitted change orders can be rejected")
        co.status = ChangeOrderStatus.REJECTED
        await self.db.flush()

        try:
            proj = (await self.db.execute(
                select(Project.name, Project.code)
                .where(Project.id == co.project_id)
            )).one_or_none()
            proj_name = f"{proj[0]} ({proj[1]})" if proj else "—"
            html = item_rejected_html("Change Order", co.co_number, proj_name, reason)
            await notify_user_by_id(self.db, co.created_by, f"CO {co.co_number} Rejected", html)
        except Exception as e:
            logger.warning(f"Failed to send CO rejection email: {e}")

        return co

    # ── Payment Certificates ──────────────────────────────────────

    async def create_payment_cert(
        self, project_id: str, data: CreatePaymentCertRequest
    ) -> PaymentCertificate:
        gross = round(
            data.work_done_value + data.materials_on_site, 2
        )
        net = round(
            gross - data.retention_amount - data.previous_payments, 2
        )
        cert = PaymentCertificate(
            project_id=project_id,
            invoice_id=data.invoice_id,
            cert_number=_num("PC"),
            period_from=data.period_from,
            period_to=data.period_to,
            work_done_value=data.work_done_value,
            materials_on_site=data.materials_on_site,
            gross_amount=gross,
            retention_amount=data.retention_amount,
            previous_payments=data.previous_payments,
            net_payable=net,
            notes=data.notes,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
            issued_by=self.user_id,
        )
        self.db.add(cert)
        await self.db.flush()
        return cert

    async def list_payment_certs(
        self, project_id: str
    ) -> list[PaymentCertificate]:
        result = await self.db.execute(
            select(PaymentCertificate).where(and_(
                PaymentCertificate.project_id == project_id,
                self._scope(PaymentCertificate),
            )).order_by(PaymentCertificate.created_at.desc())
        )
        return list(result.scalars().all())

    # ── Finance Summary ───────────────────────────────────────────

    async def get_finance_summary(self, project_id: str) -> dict:
        # Invoice aggregates
        inv_result = await self.db.execute(
            select(
                Invoice.status,
                func.count(Invoice.id).label("count"),
                func.sum(Invoice.grand_total).label("total"),
                func.sum(Invoice.paid_amount).label("paid"),
            )
            .where(and_(
                Invoice.project_id == project_id,
                self._scope(Invoice),
            ))
            .group_by(Invoice.status)
        )
        inv_rows = inv_result.all()

        total_invoiced = sum(r.total or 0 for r in inv_rows)
        total_received = sum(r.paid or 0 for r in inv_rows)
        overdue = sum(r.count for r in inv_rows if r.status == "overdue")
        pending = sum(r.count for r in inv_rows if r.status == "submitted")
        by_status = {r.status: {"count": r.count, "total": r.total or 0} for r in inv_rows}

        # Expense total
        exp_result = await self.db.execute(
            select(func.sum(Expense.total_amount)).where(and_(
                Expense.project_id == project_id,
                self._scope(Expense),
                Expense.status.in_(["approved", "reimbursed"]),
            ))
        )
        total_expenses = exp_result.scalar_one_or_none() or 0.0

        # Change order total (approved)
        co_result = await self.db.execute(
            select(func.sum(ChangeOrder.amount)).where(and_(
                ChangeOrder.project_id == project_id,
                self._scope(ChangeOrder),
                ChangeOrder.status == ChangeOrderStatus.APPROVED,
            ))
        )
        total_co = co_result.scalar_one_or_none() or 0.0

        return {
            "total_invoiced": round(total_invoiced, 2),
            "total_received": round(total_received, 2),
            "total_outstanding": round(total_invoiced - total_received, 2),
            "total_expenses": round(total_expenses, 2),
            "total_change_orders": round(total_co, 2),
            "overdue_invoices": overdue,
            "pending_approval": pending,
            "invoice_by_status": by_status,
        }

    async def get_cashflow(self, project_id: str) -> list[dict]:
        """Monthly cashflow — invoiced vs received vs expenses."""
        inv_month = func.date_trunc("month", Invoice.invoice_date)
        inv_result = await self.db.execute(
            select(
                inv_month.label("month"),
                func.sum(Invoice.grand_total).label("invoiced"),
                func.sum(Invoice.paid_amount).label("received"),
            )
            .where(and_(
                Invoice.project_id == project_id,
                self._scope(Invoice),
            ))
            .group_by(inv_month)
            .order_by(inv_month)
        )

        exp_month = func.date_trunc("month", Expense.expense_date)
        exp_result = await self.db.execute(
            select(
                exp_month.label("month"),
                func.sum(Expense.total_amount).label("expenses"),
            )
            .where(and_(
                Expense.project_id == project_id,
                self._scope(Expense),
            ))
            .group_by(exp_month)
        )

        exp_map = {str(r.month)[:7]: r.expenses or 0 for r in exp_result.all()}

        return [
            {
                "month": str(r.month)[:7],
                "invoiced": r.invoiced or 0,
                "received": r.received or 0,
                "expenses": exp_map.get(str(r.month)[:7], 0),
            }
            for r in inv_result.all()
        ]
