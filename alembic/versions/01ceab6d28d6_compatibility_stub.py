"""compatibility stub for missing revision 01ceab6d28d6

Revision ID: 01ceab6d28d6
Revises: 42c3e998e98c
Create Date: 2026-06-24 00:00:00.000000

This placeholder restores the missing revision node so Alembic can resolve
the migration graph in environments that already reference this revision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "01ceab6d28d6"
down_revision: Union[str, None] = "42c3e998e98c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
