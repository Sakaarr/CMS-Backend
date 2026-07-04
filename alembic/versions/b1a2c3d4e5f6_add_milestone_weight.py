"""add_milestone_weight

Revision ID: b1a2c3d4e5f6
Revises: 5d690d8ab628
Create Date: 2026-06-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, None] = '698847173bb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('milestones', sa.Column('weight', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('milestones', 'weight')
