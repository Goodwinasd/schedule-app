"""add group shift and classroom/subject room types

Revision ID: a9b8c7d6e5f4
Revises: f7g8h9i0j1k2
Create Date: 2026-10-28 21:30:00.000000

Реальные расписания техникума:
- группы учатся в 1-ю (с 8:30) или 2-ю (с 13:30) смену → groups_list.shift;
- спец. аудитории (Динамо, Атмосфера, 501 левая/правая) → classrooms_list.room_type;
- предметы требуют тип аудитории (физкультура → gym, информатика → computer)
  → subjects.required_room_type.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'f7g8h9i0j1k2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = [
    ('groups_list', 'shift', sa.Integer(), 'Смена обучения: 1 — с 8:30, 2 — с 13:30'),
    ('classrooms_list', 'room_type', sa.String(), 'Тип аудитории: normal/gym/computer/court'),
    ('subjects', 'required_room_type', sa.String(), 'Требуемый тип аудитории (NULL — обычная)'),
]


def _table_exists(bind, table) -> bool:
    return sa.inspect(bind).has_table(table) if bind else False


def _columns(bind, table) -> set:
    if not _table_exists(bind, table):
        return set()
    return {row[1] for row in bind.exec_driver_sql(f'PRAGMA table_info("{table}")')}


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, coltype, comment in COLUMNS:
        if not _table_exists(bind, table):
            continue
        if column in _columns(bind, table):
            continue
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column(column, coltype, nullable=True, comment=comment))


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, _coltype, _comment in reversed(COLUMNS):
        if not _table_exists(bind, table):
            continue
        if column not in _columns(bind, table):
            continue
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column(column)
