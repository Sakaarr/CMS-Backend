import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Date, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class VendorStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLACKLISTED = "blacklisted"


class VendorCategory(str, enum.Enum):
    MATERIAL_SUPPLIER = "material_supplier"
    SUBCONTRACTOR = "subcontractor"
    EQUIPMENT_RENTAL = "equipment_rental"
    CONSULTANT = "consultant"
    OTHER = "other"


class RFQStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class QuotationStatus(str, enum.Enum):
    RECEIVED = "received"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class POStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    FULLY_RECEIVED = "fully_received"
    CANCELLED = "cancelled"


class GRNStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Vendor(TenantScopedModel):
    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[VendorCategory] = mapped_column(
        SAEnum(VendorCategory), default=VendorCategory.OTHER, nullable=False
    )
    status: Mapped[VendorStatus] = mapped_column(
        SAEnum(VendorStatus), default=VendorStatus.ACTIVE, nullable=False
    )
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(50), nullable=True)
    credit_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    rfqs: Mapped[list["RFQVendor"]] = relationship(back_populates="vendor", lazy="select")
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="vendor", lazy="select")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="vendor", lazy="select")


class RFQ(TenantScopedModel):
    __tablename__ = "rfqs"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rfq_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RFQStatus] = mapped_column(
        SAEnum(RFQStatus), default=RFQStatus.DRAFT, nullable=False
    )
    due_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["RFQItem"]] = relationship(
        back_populates="rfq", lazy="select", cascade="all, delete-orphan"
    )
    vendors: Mapped[list["RFQVendor"]] = relationship(
        back_populates="rfq", lazy="select", cascade="all, delete-orphan"
    )
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="rfq", lazy="select")


class RFQItem(TenantScopedModel):
    __tablename__ = "rfq_items"

    rfq_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rfq: Mapped["RFQ"] = relationship(back_populates="items")


class RFQVendor(TenantScopedModel):
    __tablename__ = "rfq_vendors"

    rfq_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sent_at: Mapped[str | None] = mapped_column(Date, nullable=True)
    responded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    rfq: Mapped["RFQ"] = relationship(back_populates="vendors")
    vendor: Mapped["Vendor"] = relationship(back_populates="rfqs")


class Quotation(TenantScopedModel):
    __tablename__ = "quotations"

    rfq_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quotation_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[QuotationStatus] = mapped_column(
        SAEnum(QuotationStatus), default=QuotationStatus.RECEIVED, nullable=False
    )
    total_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    valid_until: Mapped[str | None] = mapped_column(Date, nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["QuotationItem"]] = relationship(
        back_populates="quotation", lazy="select", cascade="all, delete-orphan"
    )
    rfq: Mapped["RFQ"] = relationship(back_populates="quotations")
    vendor: Mapped["Vendor"] = relationship(back_populates="quotations")


class QuotationItem(TenantScopedModel):
    __tablename__ = "quotation_items"

    quotation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rfq_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rfq_items.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_rate: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    quotation: Mapped["Quotation"] = relationship(back_populates="items")


class PurchaseOrder(TenantScopedModel):
    __tablename__ = "purchase_orders"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quotation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True
    )
    po_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[POStatus] = mapped_column(
        SAEnum(POStatus), default=POStatus.DRAFT, nullable=False
    )
    delivery_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    grand_total: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["POItem"]] = relationship(
        back_populates="po", lazy="select", cascade="all, delete-orphan"
    )
    grns: Mapped[list["GRN"]] = relationship(back_populates="po", lazy="select")
    vendor: Mapped["Vendor"] = relationship(back_populates="purchase_orders")


class POItem(TenantScopedModel):
    __tablename__ = "po_items"

    po_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_rate: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    received_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    boq_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    po: Mapped["PurchaseOrder"] = relationship(back_populates="items")


class GRN(TenantScopedModel):
    __tablename__ = "grns"

    po_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grn_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[GRNStatus] = mapped_column(
        SAEnum(GRNStatus), default=GRNStatus.DRAFT, nullable=False
    )
    received_date: Mapped[str] = mapped_column(Date, nullable=False)
    received_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    delivery_note: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspection_passed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    items: Mapped[list["GRNItem"]] = relationship(
        back_populates="grn", lazy="select", cascade="all, delete-orphan"
    )
    po: Mapped["PurchaseOrder"] = relationship(back_populates="grns")


class GRNItem(TenantScopedModel):
    __tablename__ = "grn_items"

    grn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("grns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    po_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("po_items.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    ordered_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    received_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    rejected_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit_rate: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    grn: Mapped["GRN"] = relationship(back_populates="items")