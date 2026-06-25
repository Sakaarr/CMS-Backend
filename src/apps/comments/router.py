from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.apps.identity.dependencies import get_current_user
from src.apps.identity.models import User
from src.apps.comments.service import CommentService
from src.apps.comments.schemas import (
    CreateCommentRequest, UpdateCommentRequest,
    CommentResponse, CommentWithAuthorResponse, CommentListResponse,
)
from src.shared.response import APIResponse, success_response

router = APIRouter(tags=["Comments"])


async def get_svc(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommentService:
    return CommentService(db=db, user_id=current_user.id)


@router.post("/comments", response_model=APIResponse[CommentResponse], status_code=201)
async def create_comment(
    data: CreateCommentRequest,
    svc: CommentService = Depends(get_svc),
):
    comment = await svc.create(data)
    return success_response(data=CommentResponse.model_validate(comment), message="Comment created")


@router.get("/comments/{target_type}/{target_id}", response_model=APIResponse[CommentListResponse])
async def get_comments(
    target_type: str, target_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    svc: CommentService = Depends(get_svc),
):
    skip = (page - 1) * page_size
    result = await svc.get_comments_with_authors(target_type, target_id, skip=skip, limit=page_size)
    return success_response(data=result)


@router.patch("/comments/{comment_id}", response_model=APIResponse[CommentResponse])
async def update_comment(
    comment_id: str, data: UpdateCommentRequest,
    svc: CommentService = Depends(get_svc),
):
    comment = await svc.update(comment_id, data)
    return success_response(data=CommentResponse.model_validate(comment), message="Comment updated")


@router.delete("/comments/{comment_id}", response_model=APIResponse[None])
async def delete_comment(comment_id: str, svc: CommentService = Depends(get_svc)):
    await svc.delete(comment_id)
    return success_response(message="Comment deleted")
