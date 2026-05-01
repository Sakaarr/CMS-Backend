import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class WarehouseStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TransactionType(str, enum.Enum):
    RECEIPT = "receipt"           # GRN → stock in
    ISSUE = "issue"               # to site
    TRANSFER = "transfer"         # warehouse to warehouse
    RETURN = "return"             # from site back
    ADJUSTMENT = "adjustment"     # manual correction
    CONSUMPTION = "consumption"   # site usage logged


class MaterialRequestStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    ISSUED = "issued"
    REJECTED = "rejected"


class Warehouse(TenantScopedModel):
    __tablename__ = "warehouses"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[WarehouseStatus] = mapped_column(
        SAEnum(WarehouseStatus), default=WarehouseStatus.ACTIVE, nullable=False
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_site_store: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    keeper_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    stock_items: Mapped[list["StockItem"]] = relationship(
        back_populates="warehouse", lazy="select", cascade="all, delete-orphan"
    )


class StockItem(TenantScopedModel):
    __tablename__ = "stock_items"

    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity_on_hand: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reserved_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reorder_level: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    @property
    def available_quantity(self) -> float:
        return max(0.0, self.quantity_on_hand - self.reserved_quantity)

    @property
    def needs_reorder(self) -> bool:
        return self.quantity_on_hand <= self.reorder_level

    warehouse: Mapped["Warehouse"] = relationship(back_populates="stock_items")
    transactions: Mapped[list["StockTransaction"]] = relationship(
        back_populates="stock_item", lazy="select"
    )


class StockTransaction(TenantScopedModel):
    __tablename__ = "stock_transactions"

    stock_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stock_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    transaction_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)

    stock_item: Mapped["StockItem"] = relationship(back_populates="transactions")


class MaterialRequest(TenantScopedModel):
    __tablename__ = "material_requests"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    from_warehouse_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    mr_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[MaterialRequestStatus] = mapped_column(
        SAEnum(MaterialRequestStatus), default=MaterialRequestStatus.DRAFT, nullable=False
    )
    required_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    issued_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    items: Mapped[list["MaterialRequestItem"]] = relationship(
        back_populates="request", lazy="select", cascade="all, delete-orphan"
    )


class MaterialRequestItem(TenantScopedModel):
    __tablename__ = "material_request_items"

    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("material_requests.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    stock_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stock_items.id", ondelete="SET NULL"), nullable=True
    )
    material_code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    approved_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    issued_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    request: Mapped["MaterialRequest"] = relationship(back_populates="items")