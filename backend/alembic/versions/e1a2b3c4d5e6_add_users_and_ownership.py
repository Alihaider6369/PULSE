"""add users table and ownership foreign keys

Revision ID: e1a2b3c4d5e6
Revises: 395fc3a2bf5d
Create Date: 2026-10-12 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '395fc3a2bf5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. Add columns to sessions table
    op.add_column('sessions', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('sessions', sa.Column('client_uuid', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_sessions_client_uuid'), 'sessions', ['client_uuid'], unique=True)
    op.create_foreign_key(
        'fk_sessions_user_id_users',
        'sessions', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

    # 3. Add columns to posture_events table
    op.add_column('posture_events', sa.Column('client_uuid', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_posture_events_client_uuid'), 'posture_events', ['client_uuid'], unique=True)

    # 4. Add columns to settings table
    op.add_column('settings', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_settings_user_id'), 'settings', ['user_id'], unique=True)
    op.create_foreign_key(
        'fk_settings_user_id_users',
        'settings', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # 4. Revert settings
    op.drop_constraint('fk_settings_user_id_users', 'settings', type_='foreignkey')
    op.drop_index(op.f('ix_settings_user_id'), table_name='settings')
    op.drop_column('settings', 'user_id')

    # 3. Revert posture_events
    op.drop_index(op.f('ix_posture_events_client_uuid'), table_name='posture_events')
    op.drop_column('posture_events', 'client_uuid')

    # 2. Revert sessions
    op.drop_constraint('fk_sessions_user_id_users', 'sessions', type_='foreignkey')
    op.drop_index(op.f('ix_sessions_client_uuid'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_column('sessions', 'client_uuid')
    op.drop_column('sessions', 'user_id')

    # 1. Revert users
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
