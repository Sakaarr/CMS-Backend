"""initial_schema

Revision ID: 465eded9f763
Revises: 
Create Date: 2026-05-01 00:59:56.534669

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy_utils import database_exists

from src.core.database import Base


# revision identifiers, used by Alembic.
revision: str = '465eded9f763'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
