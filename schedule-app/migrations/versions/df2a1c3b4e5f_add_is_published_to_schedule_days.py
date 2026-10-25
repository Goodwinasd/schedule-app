"""add is_published to schedule_days

Revision ID: df2a1c3b4e5f
Revises: c1d2e3f4a5b6
Create Date: 2026-08-03 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'df2a1c3b4e5f'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schedule_days', sa.Column('is_published', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('schedule_days', 'is_published')