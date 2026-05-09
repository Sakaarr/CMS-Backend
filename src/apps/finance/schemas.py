from datetime import date
from pydantic import BaseModel, field_validator
from src.apps.finance.models import (
    InvoiceType, InvoiceStatus, PaymentMethod,
    ExpenseCategory, ExpenseStatus,
    ChangeOrderStatus, PaymentCertStatus,
)


# ── Invoice ───────────────────────────────────────────────────────

class InvoiceLineItemRequest(BaseModel):
    description: str
    unit: str
    quantity: float
    unit_rate: float
    sort_order: int = 0
    boq_item_id: str | None = None


class CreateInvoiceRequest(BaseModel):
    invoice_type: InvoiceType
    client_name: str | None = None
    vendor_id: str | None = None
    billing_address: str | None = None
    invoice_date: date
    due_date: date | None = None
    period_from: date | None = None
    period_to: date | None = None
    vat_rate: float = 13.0
    retention_rate: float = 0.0
    discount_amount: float = 0.0
    currency: str = "NPR"
    notes: str | None = None
    terms: str | None = None
    line_items: list[InvoiceLineItemRequest] = []


class UpdateInvoiceRequest(BaseModel):
    client_name: str | None = None
    billing_address: str | None = None
    due_date: date | None = None
    notes: str | None = None
    terms: str | None = None


class InvoiceLineItemResponse(BaseModel):
    id: str
    description: str
    unit: str
    quantity: float
    unit_rate: float
    amount: float
    sort_order: int
    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: str
    project_id: str
    invoice_number: str
    invoice_type: InvoiceType
    status: InvoiceStatus
    client_name: str | None
    invoice_date: date
    due_date: date | None
    period_from: date | None
    period_to: date | None
    subtotal: float
    discount_amount: float
    taxable_amount: float
    vat_rate: float
    vat_amount: float
    retention_rate: float
    retention_amount: float
    grand_total: float
    paid_amount: float
    balance_due: float
    currency: str
    notes: str | None
    approved_by: str | None
    line_items: list[InvoiceLineItemResponse] = []
    model_config = {"from_attributes": True}


class InvoiceSummary(BaseModel):
    id: str
    invoice_number: str
    invoice_type: InvoiceType
    status: InvoiceStatus
    client_name: str | None
    invoice_date: date
    due_date: date | None
    grand_total: float
    paid_amount: float
    balance_due: float
    currency: str
    model_config = {"from_attributes": True}


# ── Payment ───────────────────────────────────────────────────────

class RecordPaymentRequest(BaseModel):
    payment_date: date
    amount: float
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    reference: str | None = None
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Payment amount must be positive")
        return v


class PaymentResponse(BaseModel):
    id: str
    invoice_id: str
    payment_number: str
    payment_date: date
    amount: float
    method: PaymentMethod
    reference: str | None
    model_config = {"from_attributes": True}


# ── Expense ───────────────────────────────────────────────────────

class CreateExpenseRequest(BaseModel):
    category: ExpenseCategory
    description: str
    amount: float
    expense_date: date
    site_id: str | None = None
    vendor_name: str | None = None
    pan_number: str | None = None
    receipt_url: str | None = None
    notes: str | None = None
    boq_item_id: str | None = None
    include_vat: bool = False


class ExpenseResponse(BaseModel):
    id: str
    project_id: str
    expense_number: str
    category: ExpenseCategory
    status: ExpenseStatus
    description: str
    amount: float
    vat_amount: float
    total_amount: float
    expense_date: date
    currency: str
    vendor_name: str | None
    pan_number: str | None
    notes: str | None
    approved_by: str | None
    model_config = {"from_attributes": True}


# ── Change Order ──────────────────────────────────────────────────

class CreateChangeOrderRequest(BaseModel):
    title: str
    description: str | None = None
    reason: str | None = None
    amount: float
    impact_days: int = 0
    original_contract_value: float | None = None


class ChangeOrderResponse(BaseModel):
    id: str
    project_id: str
    co_number: str
    title: str
    status: ChangeOrderStatus
    amount: float
    impact_days: int
    approved_by: str | None
    original_contract_value: float | None
    revised_contract_value: float | None
    model_config = {"from_attributes": True}


# ── Payment Certificate ───────────────────────────────────────────

class CreatePaymentCertRequest(BaseModel):
    invoice_id: str | None = None
    period_from: date
    period_to: date
    work_done_value: float
    materials_on_site: float = 0.0
    retention_amount: float = 0.0
    previous_payments: float = 0.0
    notes: str | None = None


class PaymentCertResponse(BaseModel):
    id: str
    project_id: str
    cert_number: str
    status: PaymentCertStatus
    period_from: date
    period_to: date
    work_done_value: float
    materials_on_site: float
    gross_amount: float
    retention_amount: float
    previous_payments: float
    net_payable: float
    notes: str | None
    model_config = {"from_attributes": True}


# ── Finance Summary ───────────────────────────────────────────────

class FinanceSummary(BaseModel):
    total_invoiced: float
    total_received: float
    total_outstanding: float
    total_expenses: float
    total_change_orders: float
    overdue_invoices: int
    pending_approval: int
    invoice_by_status: dict