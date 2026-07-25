"""add indexes on deleted_at for reference tables

Revision ID: 92ef138d4cfb
Revises: c46c7442d88a
Create Date: 2026-07-25 17:18:46.849298

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92ef138d4cfb'
down_revision: Union[str, Sequence[str], None] = 'c46c7442d88a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_subjects_deleted_at', 'subjects', ['deleted_at'])
    op.create_index('idx_teachers_deleted_at', 'teachers', ['deleted_at'])
    op.create_index('idx_groups_list_deleted_at', 'groups_list', ['deleted_at'])
    op.create_index('idx_classrooms_list_deleted_at', 'classrooms_list', ['deleted_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_subjects_deleted_at', 'subjects')
    op.drop_index('idx_teachers_deleted_at', 'teachers')
    op.drop_index('idx_groups_list_deleted_at', 'groups_list')
    op.drop_index('idx_classrooms_list_deleted_at', 'classrooms_list')
