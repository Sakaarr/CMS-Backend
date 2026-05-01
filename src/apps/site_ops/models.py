import enum
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, Date, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.shared.base_model import TenantScopedModel


class WeatherCondition(str, enum.Enum):
    SUNNY = "sunny"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    FOGGY = "foggy"
    STORMY = "stormy"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half_day"
    ON_LEAVE = "on_leave"


class EquipmentStatus(str, enum.Enum):
    WORKING = "working"
    IDLE = "idle"
    BREAKDOWN = "breakdown"
    MAINTENANCE = "maintenance"


class DailyProgressReport(TenantScopedModel):
    __tablename__ = "daily_progress_reports"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_date: Mapped[str] = mapped_column(Date, nullable=False)
    weather: Mapped[WeatherCondition] = mapped_column(
        SAEnum(WeatherCondition), default=WeatherCondition.SUNNY, nullable=False
    )
    temperature_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    work_hours: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    general_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_workers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_labour_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    work_items: Mapped[list["DPRWorkItem"]] = relationship(
        back_populates="dpr", lazy="select", cascade="all, delete-orphan"
    )
    attendance_records: Mapped[list["LabourAttendance"]] = relationship(
        back_populates="dpr", lazy="select", cascade="all, delete-orphan"
    )
    equipment_logs: Mapped[list["EquipmentLog"]] = relationship(
        back_populates="dpr", lazy="select", cascade="all, delete-orphan"
    )


class DPRWorkItem(TenantScopedModel):
    __tablename__ = "dpr_work_items"

    dpr_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("daily_progress_reports.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    boq_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    planned_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    achieved_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cumulative_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    dpr: Mapped["DailyProgressReport"] = relationship(back_populates="work_items")


class LabourAttendance(TenantScopedModel):
    __tablename__ = "labour_attendance"

    dpr_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("daily_progress_reports.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    worker_name: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trade: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(AttendanceStatus), default=AttendanceStatus.PRESENT, nullable=False
    )
    check_in: Mapped[str | None] = mapped_column(String(10), nullable=True)
    check_out: Mapped[str | None] = mapped_column(String(10), nullable=True)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    daily_wage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_subcontractor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subcontractor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    dpr: Mapped["DailyProgressReport"] = relationship(back_populates="attendance_records")


class EquipmentLog(TenantScopedModel):
    __tablename__ = "equipment_logs"

    dpr_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("daily_progress_reports.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    equipment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    equipment_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[EquipmentStatus] = mapped_column(
        SAEnum(EquipmentStatus), default=EquipmentStatus.WORKING, nullable=False
    )
    working_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    idle_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fuel_consumed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    dpr: Mapped["DailyProgressReport"] = relationship(back_populates="equipment_logs")