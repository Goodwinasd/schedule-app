"""add is_special_event and classroom_id_2 to lessons

Revision ID: d4e5f6a7b8c9
Revises: a9b8c7d6e5f4
Create Date: 2026-10-28 22:00:00.000000

Разовые мероприятия и экзамены: урок помечается is_special_event, генератор
и очистка недели его не трогают. Экзамен может занимать две аудитории сразу
(501 левая / 501 правая) — classroom_id_2.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind) -> set:
    if not sa.inspect(bind).has_table('lessons'):
        return set()
    return {row[1] for row in bind.exec_driver_sql('PRAGMA table_info("lessons")')}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind)
    if 'is_special_event' not in cols:
        with op.batch_alter_table('lessons') as batch_op:
            batch_op.add_column(sa.Column('is_special_event', sa.Integer(), nullable=False,
                                          server_default='0'))
    if 'classroom_id_2' not in cols:
        with op.batch_alter_table('lessons') as batch_op:
            batch_op.add_column(sa.Column('classroom_id_2', sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    cols = _columns(bind)
    if 'classroom_id_2' in cols:
        with op.batch_alter_table('lessons') as batch_op:
            batch_op.drop_column('classroom_id_2')
    if 'is_special_event' in cols:
        with op.batch_alter_table('lessons') as batch_op:
            batch_op.drop_column('is_special_event')
