from datetime import datetime
from pydantic import BaseModel, Field


class ApprovalInboxItem(BaseModel):
    id: str
    module: str
    item_type: str
    title: str
    subtitle: str | None = None
    status: str
    project_id: str | None = None
    project_name: str | None = None
    project_code: str | None = None
    created_at: datetime
    action_url: str | None = None
    meta: dict[str, str | int | float | None] = Field(default_factory=dict)


class ApprovalInboxResponse(BaseModel):
    total: int
    counts: dict[str, int]
    items: list[ApprovalInboxItem]
