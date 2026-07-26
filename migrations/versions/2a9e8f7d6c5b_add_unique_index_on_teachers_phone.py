"""add unique partial index on teachers.phone

Revision ID: 2a9e8f7d6c5b
Revises: fdb6c2208bbf
Create Date: 2026-07-25 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a9e8f7d6c5b'
down_revision: Union[str, Sequence[str], None] = 'fdb6c2208bbf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_teachers_phone ON teachers(phone) WHERE phone != '' AND phone IS NOT NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_teachers_phone")
