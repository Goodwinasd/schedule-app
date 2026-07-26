"""add phone to teachers

Revision ID: fdb6c2208bbf
Revises: 92ef138d4cfb
Create Date: 2026-07-25 19:51:40.958394

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fdb6c2208bbf'
down_revision: Union[str, Sequence[str], None] = '92ef138d4cfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE teachers ADD COLUMN phone TEXT")


def downgrade() -> None:
    """Downgrade schema."""
    pass
