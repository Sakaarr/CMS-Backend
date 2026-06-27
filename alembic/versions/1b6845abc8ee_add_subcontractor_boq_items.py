"""add_subcontractor_boq_items

Revision ID: 1b6845abc8ee
Revises: 5d690d8ab628
Create Date: 2026-06-25 21:19:25.076797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b6845abc8ee'
down_revision: Union[str, None] = '5d690d8ab628'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('subcontractor_boq_items',
        sa.Column('contract_id', sa.String(36), nullable=False),
        sa.Column('boq_item_id', sa.String(36), nullable=False),
        sa.Column('assigned_quantity', sa.Float(), nullable=False, server_default='0'),
        sa.Column('unit_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('contract_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status',
            sa.Enum('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='boqitemassignmentstatus'),
            nullable=False, server_default='PENDING',
        ),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('updated_by', sa.String(36), nullable=True),
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['contract_id'], ['subcontractor_contracts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['boq_item_id'], ['boq_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subcontractor_boq_items_contract_id'), 'subcontractor_boq_items', ['contract_id'], unique=False)
    op.create_index(op.f('ix_subcontractor_boq_items_boq_item_id'), 'subcontractor_boq_items', ['boq_item_id'], unique=False)
    op.create_index(op.f('ix_subcontractor_boq_items_tenant_id'), 'subcontractor_boq_items', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_subcontractor_boq_items_tenant_id'), table_name='subcontractor_boq_items')
    op.drop_index(op.f('ix_subcontractor_boq_items_boq_item_id'), table_name='subcontractor_boq_items')
    op.drop_index(op.f('ix_subcontractor_boq_items_contract_id'), table_name='subcontractor_boq_items')
    op.drop_table('subcontractor_boq_items')
    op.execute('DROP TYPE IF EXISTS boqitemassignmentstatus')
