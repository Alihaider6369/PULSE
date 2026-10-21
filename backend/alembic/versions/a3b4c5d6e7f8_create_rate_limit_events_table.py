"""create rate_limit_events table

Revision ID: a3b4c5d6e7f8
Revises: f2b3c4d5e6a7
Create Date: 2026-10-21 13:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2b3c4d5e6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rate_limit_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rate_limit_events_id'), 'rate_limit_events', ['id'], unique=False)
    op.create_index(op.f('ix_rate_limit_events_key'), 'rate_limit_events', ['key'], unique=False)
    op.create_index(op.f('ix_rate_limit_events_created_at'), 'rate_limit_events', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_rate_limit_events_created_at'), table_name='rate_limit_events')
    op.drop_index(op.f('ix_rate_limit_events_key'), table_name='rate_limit_events')
    op.drop_index(op.f('ix_rate_limit_events_id'), table_name='rate_limit_events')
    op.drop_table('rate_limit_events')
