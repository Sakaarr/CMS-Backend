"""merge_heads

Revision ID: 42c3e998e98c
Revises: 24c3b5f1a9e2, 91a494b510fb
Create Date: 2026-06-23 20:53:03.652560

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42c3e998e98c'
down_revision: Union[str, None] = ('24c3b5f1a9e2', '91a494b510fb')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
