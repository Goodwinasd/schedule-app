"""add specialty_id, cycle, control_form to curriculum

Revision ID: f7g8h9i0j1k2
Revises: e5f6a7b8c9d0
Create Date: 2026-08-03 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f7g8h9i0j1k2'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _curriculum_exists(bind) -> bool:
    return sa.inspect(bind).has_table('curriculum') if bind else False


def _columns(bind) -> set:
    if not _curriculum_exists(bind):
        return set()
    return {row[1] for row in bind.exec_driver_sql('PRAGMA table_info(curriculum)')}


def upgrade() -> None:
    bind = op.get_bind()
    if not _curriculum_exists(bind):
        # Fresh DB: таблица curriculum создаётся позже через db.ensure_curriculum_table(),
        # который уже включает новые поля. Здесь нечего мигрировать.
        return
    cols = _columns(bind)
    with op.batch_alter_table('curriculum') as batch_op:
        if 'specialty_id' not in cols:
            batch_op.add_column(sa.Column('specialty_id', sa.Integer(), nullable=True))
        if 'cycle' not in cols:
            batch_op.add_column(sa.Column('cycle', sa.String(), nullable=True))
        if 'control_form' not in cols:
            batch_op.add_column(sa.Column('control_form', sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _curriculum_exists(bind):
        return
    cols = _columns(bind)
    with op.batch_alter_table('curriculum') as batch_op:
        if 'control_form' in cols:
            batch_op.drop_column('control_form')
        if 'cycle' in cols:
            batch_op.drop_column('cycle')
        if 'specialty_id' in cols:
            batch_op.drop_column('specialty_id')