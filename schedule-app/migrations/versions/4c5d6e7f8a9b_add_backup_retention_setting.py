"""add backup_retention_days setting

Revision ID: 4c5d6e7f8a9b
Revises: 3b8e4f1a2c7d
Create Date: 2026-07-25 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4c5d6e7f8a9b'
down_revision: Union[str, Sequence[str], None] = '3b8e4f1a2c7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('backup_retention_days', '30')")


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'backup_retention_days'")
