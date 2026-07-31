"""add teacher_absences and teacher_subjects tables

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-07-31 09:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'teacher_absences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
    )
    op.create_table(
        'teacher_subjects',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('teacher_subjects')
    op.drop_table('teacher_absences')
