"""add substitution fields to lessons

Revision ID: a1b2c3d4e5f6
Revises: 92ef138d4cfb
Create Date: 2026-07-30 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '4c5d6e7f8a9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lessons', sa.Column('is_substitution', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('lessons', sa.Column('original_teacher_id', sa.Integer(), nullable=True))
    op.add_column('lessons', sa.Column('substitution_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('lessons', 'substitution_reason')
    op.drop_column('lessons', 'original_teacher_id')
    op.drop_column('lessons', 'is_substitution')
