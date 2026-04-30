import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class CostCodeCategory(str, enum.Enum):
    CIVIL = "civil"
    STRUCTURAL = "structural"
    ARCHITECTURAL = "architectural"
    MEP = "mep"
    FINISHING = "finishing"
    EXTERNAL = "external"
    PRELIMINARY = "preliminary"
    OTHER = "other"


class BOQItemStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REVISED = "revised"
    LOCKED = "locked"


class BudgetVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class UnitOfMeasure(str, enum.Enum):
    SQM = "sqm"        # square meter
    CUM = "cum"        # cubic meter
    RMT = "rmt"        # running meter
    NOS = "nos"        # numbers
    KG = "kg"
    MT = "mt"          # metric ton
    LIT = "lit"        # litre
    BAG = "bag"
    LS = "ls"          # lump sum
    DAY = "day"
    HOUR = "hour"
    PERCENT = "percent"


class CostCode(TenantScopedModel):
    """
    Master list of cost codes for the organisation.
    e.g. CIVIL-001 Earthwork Excavation
    """
    __tablename__ = "cost_codes"

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[CostCodeCategory] = mapped_column(
        SAEnum(CostCodeCategory), default=CostCodeCategory.OTHER, nullable=False
    )
    unit: Mapped[UnitOfMeasure] = mapped_column(
        SAEnum(UnitOfMeasure), default=UnitOfMeasure.NOS, nullable=False
    )
    standard_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    boq_items: Mapped[list["BOQItem"]] = relationship(back_populates="cost_code", lazy="select")
    rate_analyses: Mapped[list["RateAnalysis"]] = relationship(back_populates="cost_code", lazy="select")


class BudgetVersion(TenantScopedModel):
    """
    A project can have multiple budget versions (original, revision 1, etc.)
    Only one can be APPROVED at a time.
    """
    __tablename__ = "budget_versions"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "Original Budget"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BudgetVersionStatus] = mapped_column(
        SAEnum(BudgetVersionStatus), default=BudgetVersionStatus.DRAFT, nullable=False
    )

    # Totals (auto-calculated)
    total_material_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_labour_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_equipment_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_overhead: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    contingency_percentage: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    contingency_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    grand_total: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    currency: Mapped[str] = mapped_column(String(3), default="NPR", nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Relationships
    boq_items: Mapped[list["BOQItem"]] = relationship(
        back_populates="budget_version", lazy="select", cascade="all, delete-orphan"
    )


class BOQItem(TenantScopedModel):
    """
    A single line item in the Bill of Quantities.
    """
    __tablename__ = "boq_items"

    budget_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("budget_versions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    cost_code_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cost_codes.id", ondelete="SET NULL"),
        nullable=True, index=True
    )

    # Hierarchy: sections and sub-items
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("boq_items.id", ondelete="CASCADE"), nullable=True
    )
    item_number: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. 1.2.3
    description: Mapped[str] = mapped_column(Text, nullable=False)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quantities
    unit: Mapped[UnitOfMeasure] = mapped_column(
        SAEnum(UnitOfMeasure), default=UnitOfMeasure.NOS, nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # qty * rate

    # Breakdown of unit rate
    material_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    labour_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    equipment_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overhead_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    status: Mapped[BOQItemStatus] = mapped_column(
        SAEnum(BOQItemStatus), default=BOQItemStatus.DRAFT, nullable=False
    )
    is_section_header: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Actuals (filled as work progresses)
    actual_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Relationships
    budget_version: Mapped["BudgetVersion"] = relationship(back_populates="boq_items")
    cost_code: Mapped["CostCode"] = relationship(back_populates="boq_items")
    children: Mapped[list["BOQItem"]] = relationship(
        back_populates="parent", lazy="select"
    )
    parent: Mapped["BOQItem | None"] = relationship(
        back_populates="children", remote_side="BOQItem.id"
    )


class RateAnalysis(TenantScopedModel):
    """
    Breakdown of how the unit rate for a cost code is derived.
    Materials + Labour + Equipment + Overhead = Unit Rate
    """
    __tablename__ = "rate_analyses"

    cost_code_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cost_codes.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[UnitOfMeasure] = mapped_column(SAEnum(UnitOfMeasure), nullable=False)
    output_quantity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    total_material: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_labour: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_equipment: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overhead_percentage: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    overhead_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    cost_code: Mapped["CostCode"] = relationship(back_populates="rate_analyses")
    components: Mapped[list["RateAnalysisComponent"]] = relationship(
        back_populates="rate_analysis", lazy="select", cascade="all, delete-orphan"
    )


class RateComponentType(str, enum.Enum):
    MATERIAL = "material"
    LABOUR = "labour"
    EQUIPMENT = "equipment"


class RateAnalysisComponent(TenantScopedModel):
    __tablename__ = "rate_analysis_components"

    rate_analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rate_analyses.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    component_type: Mapped[RateComponentType] = mapped_column(
        SAEnum(RateComponentType), nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[UnitOfMeasure] = mapped_column(SAEnum(UnitOfMeasure), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    wastage_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Relationships
    rate_analysis: Mapped["RateAnalysis"] = relationship(back_populates="components")