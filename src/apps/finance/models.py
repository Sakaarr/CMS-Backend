import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Date, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class InvoiceType(str, enum.Enum):
    CLIENT = "client"          # we bill the client
    VENDOR = "vendor"          # vendor bills us
    SUBCONTRACTOR = "subcontractor"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PaymentMethod(str, enum.Enum):
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    CASH = "cash"
    ESEWA = "esewa"
    KHALTI = "khalti"
    FONEPAY = "fonepay"


class ExpenseCategory(str, enum.Enum):
    MATERIAL = "material"
    LABOUR = "labour"
    EQUIPMENT = "equipment"
    TRANSPORT = "transport"
    OFFICE = "office"
    UTILITIES = "utilities"
    PROFESSIONAL = "professional"
    MISCELLANEOUS = "miscellaneous"


class ExpenseStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    REIMBURSED = "reimbursed"


class ChangeOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentCertStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"


class Invoice(TenantScopedModel):
    __tablename__ = "invoices"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    invoice_type: Mapped[InvoiceType] = mapped_column(
        SAEnum(InvoiceType), nullable=False
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False
    )

    # Parties
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    billing_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Dates
    invoice_date: Mapped[str] = mapped_column(Date, nullable=False)
    due_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    period_from: Mapped[str | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[str | None] = mapped_column(Date, nullable=True)

    # Amounts
    subtotal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    taxable_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    vat_rate: Mapped[float] = mapped_column(Float, default=13.0, nullable=False)  # Nepal VAT
    vat_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    retention_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    retention_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    grand_total: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    paid_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    balance_due: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        back_populates="invoice", lazy="select", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice", lazy="select", cascade="all, delete-orphan"
    )


class InvoiceLineItem(TenantScopedModel):
    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    boq_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_rate: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="line_items")


class Payment(TenantScopedModel):
    __tablename__ = "payments"

    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payment_number: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_date: Mapped[str] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        SAEnum(PaymentMethod), default=PaymentMethod.BANK_TRANSFER, nullable=False
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")


class Expense(TenantScopedModel):
    __tablename__ = "expenses"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expense_number: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        SAEnum(ExpenseCategory), nullable=False
    )
    status: Mapped[ExpenseStatus] = mapped_column(
        SAEnum(ExpenseStatus), default=ExpenseStatus.DRAFT, nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    vat_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    expense_date: Mapped[str] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    boq_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ChangeOrder(TenantScopedModel):
    __tablename__ = "change_orders"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    co_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ChangeOrderStatus] = mapped_column(
        SAEnum(ChangeOrderStatus), default=ChangeOrderStatus.DRAFT, nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    impact_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    original_contract_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    revised_contract_value: Mapped[float | None] = mapped_column(Float, nullable=True)


class PaymentCertificate(TenantScopedModel):
    __tablename__ = "payment_certificates"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    invoice_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    cert_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[PaymentCertStatus] = mapped_column(
        SAEnum(PaymentCertStatus), default=PaymentCertStatus.DRAFT, nullable=False
    )
    period_from: Mapped[str] = mapped_column(Date, nullable=False)
    period_to: Mapped[str] = mapped_column(Date, nullable=False)
    work_done_value: Mapped[float] = mapped_column(Float, nullable=False)
    materials_on_site: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    gross_amount: Mapped[float] = mapped_column(Float, nullable=False)
    retention_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    previous_payments: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_payable: Mapped[float] = mapped_column(Float, nullable=False)
    issued_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)