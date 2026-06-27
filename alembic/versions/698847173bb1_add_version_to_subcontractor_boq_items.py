"""add_version_to_subcontractor_boq_items

Revision ID: 698847173bb1
Revises: 1b6845abc8ee
Create Date: 2026-06-25 22:07:12.180873

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '698847173bb1'
down_revision: Union[str, None] = '1b6845abc8ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'subcontractor_boq_items',
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('subcontractor_boq_items', 'version')
