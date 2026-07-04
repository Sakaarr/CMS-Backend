"""compatibility stub for missing revision 698847173bb1

Revision ID: 698847173bb1
Revises: 5d690d8ab628
Create Date: 2026-06-28 00:00:00.000000

This placeholder restores the missing revision node so Alembic can resolve
the migration graph in environments that already reference this revision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "698847173bb1"
down_revision: Union[str, None] = "5d690d8ab628"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
