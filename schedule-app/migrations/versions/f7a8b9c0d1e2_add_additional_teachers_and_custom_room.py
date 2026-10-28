"""add additional teachers and custom room name to lessons

Revision ID: f7a8b9c0d1e2
Revises: e6a7b8c9d0e1
Create Date: 2026-10-28 22:45:00.000000

Неделя 6: у курсовой/консультации может быть несколько преподавателей
(ФИО через запятую), у мероприятий вне сетки — своё место («Музей МВД»,
актовый зал) вместо аудитории.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind) -> set:
    if not sa.inspect(bind).has_table('lessons'):
        return set()
    return {row[1] for row in bind.exec_driver_sql('PRAGMA table_info("lessons")')}


def upgrade() -> None:
    cols = _columns(op.get_bind())
    with op.batch_alter_table('lessons') as batch_op:
        if 'additional_teachers' not in cols:
            batch_op.add_column(sa.Column('additional_teachers', sa.Text(), nullable=True))
        if 'custom_room_name' not in cols:
            batch_op.add_column(sa.Column('custom_room_name', sa.String(), nullable=True))


def downgrade() -> None:
    cols = _columns(op.get_bind())
    with op.batch_alter_table('lessons') as batch_op:
        for column in ('custom_room_name', 'additional_teachers'):
            if column in cols:
                batch_op.drop_column(column)
