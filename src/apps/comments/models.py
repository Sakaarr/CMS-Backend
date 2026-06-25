from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.shared.base_model import BaseModel


class Comment(BaseModel):
    __tablename__ = "comments"

    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    target_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
    )
    target_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
    )

    __table_args__ = (
        {"comment": "Polymorphic comments — target_type + target_id form a FK to any entity"},
    )
