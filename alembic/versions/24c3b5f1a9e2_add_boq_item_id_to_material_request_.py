"""add_boq_item_id_to_material_request_items

Revision ID: 24c3b5f1a9e2
Revises: e5d30733072f
Create Date: 2026-06-23 10:07:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "24c3b5f1a9e2"
down_revision: str | None = "e5d30733072f"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "material_request_items",
        sa.Column("boq_item_id", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("material_request_items", "boq_item_id")
