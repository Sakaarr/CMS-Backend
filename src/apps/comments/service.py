from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from src.apps.comments.models import Comment
from src.apps.comments.schemas import (
    CreateCommentRequest, UpdateCommentRequest,
    CommentWithAuthorResponse,
)
from src.apps.identity.models import User
from src.core.exceptions import NotFoundError


class CommentService:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    def _scope(self):
        return Comment.deleted_at.is_(None)

    async def create(self, data: CreateCommentRequest) -> Comment:
        comment = Comment(
            content=data.content,
            author_id=self.user_id,
            target_type=data.target_type,
            target_id=data.target_id,
            parent_id=data.parent_id,
            created_by=self.user_id,
        )
        self.db.add(comment)
        await self.db.flush()
        return await self.get(comment.id)

    async def get(self, comment_id: str) -> Comment:
        result = await self.db.execute(
            select(Comment).where(
                and_(Comment.id == comment_id, self._scope())
            )
        )
        comment = result.scalar_one_or_none()
        if not comment:
            raise NotFoundError("Comment")
        return comment

    async def update(self, comment_id: str, data: UpdateCommentRequest) -> Comment:
        comment = await self.get(comment_id)
        if comment.author_id != self.user_id:
            from src.core.exceptions import ForbiddenError
            raise ForbiddenError("You can only edit your own comments")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(comment, k, v)
        comment.updated_by = self.user_id
        await self.db.flush()
        return comment

    async def delete(self, comment_id: str) -> None:
        comment = await self.get(comment_id)
        if comment.author_id != self.user_id:
            from src.core.exceptions import ForbiddenError
            raise ForbiddenError("You can only delete your own comments")
        from datetime import datetime, timezone
        comment.deleted_at = datetime.now(timezone.utc)
        comment.updated_by = self.user_id
        await self.db.flush()

    async def get_for_target(
        self, target_type: str, target_id: str,
        skip: int = 0, limit: int = 50,
    ) -> tuple[list[Comment], int]:
        conditions = [
            Comment.target_type == target_type,
            Comment.target_id == target_id,
            self._scope(),
            Comment.parent_id.is_(None),
        ]

        total = (await self.db.execute(
            select(func.count()).select_from(Comment).where(and_(*conditions))
        )).scalar_one()

        result = await self.db.execute(
            select(Comment)
            .where(and_(*conditions))
            .order_by(Comment.created_at.asc())
            .offset(skip).limit(limit)
        )
        comments = list(result.scalars().all())

        return comments, total

    async def get_replies(self, parent_id: str) -> list[Comment]:
        result = await self.db.execute(
            select(Comment).where(
                and_(Comment.parent_id == parent_id, self._scope())
            )
            .order_by(Comment.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_comments_with_authors(
        self, target_type: str, target_id: str,
        skip: int = 0, limit: int = 50,
    ) -> dict:
        comments, total = await self.get_for_target(target_type, target_id, skip, limit)

        author_ids = set()
        for c in comments:
            author_ids.add(c.author_id)

        result = []
        if author_ids:
            users_result = await self.db.execute(
                select(User).where(User.id.in_(author_ids))
            )
            users = {u.id: u for u in users_result.scalars().all()}

            for comment in comments:
                author = users.get(comment.author_id)
                replies = await self.get_replies(comment.id)
                reply_list = []
                for r in replies:
                    reply_author = users.get(r.author_id)
                    reply_list.append(CommentWithAuthorResponse(
                        id=r.id, content=r.content,
                        author_id=r.author_id, author_name=reply_author.full_name if reply_author else None,
                        author_avatar=reply_author.avatar_url if reply_author else None,
                        target_type=r.target_type, target_id=r.target_id,
                        parent_id=r.parent_id,
                        created_at=r.created_at, updated_at=r.updated_at,
                    ))
                result.append(CommentWithAuthorResponse(
                    id=comment.id, content=comment.content,
                    author_id=comment.author_id, author_name=author.full_name if author else None,
                    author_avatar=author.avatar_url if author else None,
                    target_type=comment.target_type, target_id=comment.target_id,
                    parent_id=comment.parent_id,
                    created_at=comment.created_at, updated_at=comment.updated_at,
                    replies=reply_list,
                ))

        return {"total": total, "data": result}
