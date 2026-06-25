from datetime import datetime
from pydantic import BaseModel


class CreateCommentRequest(BaseModel):
    content: str
    target_type: str
    target_id: str
    parent_id: str | None = None


class UpdateCommentRequest(BaseModel):
    content: str | None = None


class CommentResponse(BaseModel):
    id: str
    content: str
    author_id: str
    target_type: str
    target_id: str
    parent_id: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CommentWithAuthorResponse(CommentResponse):
    author_name: str | None = None
    author_avatar: str | None = None
    replies: list["CommentWithAuthorResponse"] = []


class CommentListResponse(BaseModel):
    total: int
    data: list[CommentWithAuthorResponse]
