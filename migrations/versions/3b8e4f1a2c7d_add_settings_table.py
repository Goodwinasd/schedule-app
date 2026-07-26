"""add settings table

Revision ID: 3b8e4f1a2c7d
Revises: 2a9e8f7d6c5b
Create Date: 2026-07-25 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3b8e4f1a2c7d'
down_revision: Union[str, Sequence[str], None] = '2a9e8f7d6c5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('session_lifetime', '3600')")
    op.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('login_rate_limit', '5')")
    op.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('login_rate_window', '300')")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS settings")
