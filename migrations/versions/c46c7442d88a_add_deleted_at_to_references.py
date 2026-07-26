"""add_deleted_at_to_references

Revision ID: c46c7442d88a
Revises: 32541b42023a
Create Date: 2026-07-25 14:21:19.284044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c46c7442d88a'
down_revision: Union[str, Sequence[str], None] = '32541b42023a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ['subjects', 'teachers', 'groups_list', 'classrooms_list']:
        op.execute(f'ALTER TABLE {table} ADD COLUMN deleted_at TIMESTAMP NULL')


def downgrade() -> None:
    pass
