from datetime import date
from pydantic import BaseModel
from src.apps.site_ops.models import (
    WeatherCondition, AttendanceStatus, EquipmentStatus
)


class DPRWorkItemRequest(BaseModel):
    description: str
    unit: str
    planned_quantity: float = 0.0
    achieved_quantity: float
    cumulative_quantity: float = 0.0
    boq_item_id: str | None = None
    remarks: str | None = None
    location: str | None = None


class LabourAttendanceRequest(BaseModel):
    worker_name: str
    worker_id: str | None = None
    trade: str
    status: AttendanceStatus = AttendanceStatus.PRESENT
    check_in: str | None = None
    check_out: str | None = None
    overtime_hours: float = 0.0
    daily_wage: float = 0.0
    is_subcontractor: bool = False
    subcontractor_id: str | None = None


class EquipmentLogRequest(BaseModel):
    equipment_name: str
    equipment_code: str | None = None
    status: EquipmentStatus = EquipmentStatus.WORKING
    working_hours: float = 0.0
    idle_hours: float = 0.0
    fuel_consumed: float = 0.0
    operator_name: str | None = None
    remarks: str | None = None


class CreateDPRRequest(BaseModel):
    site_id: str
    report_date: date
    weather: WeatherCondition = WeatherCondition.SUNNY
    temperature_celsius: float | None = None
    work_hours: float = 8.0
    general_notes: str | None = None
    safety_notes: str | None = None
    work_items: list[DPRWorkItemRequest] = []
    attendance: list[LabourAttendanceRequest] = []
    equipment_logs: list[EquipmentLogRequest] = []


class UpdateDPRRequest(BaseModel):
    weather: WeatherCondition | None = None
    temperature_celsius: float | None = None
    work_hours: float | None = None
    general_notes: str | None = None
    safety_notes: str | None = None


class DPRWorkItemResponse(BaseModel):
    id: str
    description: str
    unit: str
    planned_quantity: float
    achieved_quantity: float
    cumulative_quantity: float
    remarks: str | None
    location: str | None
    model_config = {"from_attributes": True}


class LabourAttendanceResponse(BaseModel):
    id: str
    worker_name: str
    trade: str
    status: AttendanceStatus
    check_in: str | None
    check_out: str | None
    overtime_hours: float
    daily_wage: float
    is_subcontractor: bool
    model_config = {"from_attributes": True}


class EquipmentLogResponse(BaseModel):
    id: str
    equipment_name: str
    equipment_code: str | None
    status: EquipmentStatus
    working_hours: float
    idle_hours: float
    fuel_consumed: float
    operator_name: str | None
    model_config = {"from_attributes": True}


class DPRResponse(BaseModel):
    id: str
    project_id: str
    site_id: str
    report_date: date
    weather: WeatherCondition
    temperature_celsius: float | None
    work_hours: float
    is_submitted: bool
    general_notes: str | None
    safety_notes: str | None
    total_workers: int
    total_labour_cost: float
    work_items: list[DPRWorkItemResponse] = []
    attendance_records: list[LabourAttendanceResponse] = []
    equipment_logs: list[EquipmentLogResponse] = []
    model_config = {"from_attributes": True}


class DPRSummary(BaseModel):
    id: str
    project_id: str
    site_id: str
    report_date: date
    weather: WeatherCondition
    is_submitted: bool
    total_workers: int
    work_items_count: int = 0
    model_config = {"from_attributes": True}