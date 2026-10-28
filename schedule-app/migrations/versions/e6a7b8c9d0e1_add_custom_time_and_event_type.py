"""add custom time and event type to lessons

Revision ID: e6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-10-28 22:30:00.000000

РњРµСЂРѕРїСЂРёСЏС‚РёСЏ РІРЅРµ СЃРµС‚РєРё: В«Р’С‹РµР·РґРЅРѕРµ РјРµСЂРѕРїСЂРёСЏС‚РёРµ РњСѓР·РµР№ РњР’Р”В» РІ 11:00, С„РёР·РєСѓР»СЊС‚СѓСЂР°
РІ 16:00/17:30. РҐСЂР°РЅРёРј custom_start_time/custom_end_time; event_type вЂ” С‚РёРї
СЃРѕР±С‹С‚РёСЏ РґР»СЏ Р°РЅР°Р»РёС‚РёРєРё (exam/test/coursework/event).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e6a7b8c9d0e1'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind) -> set:
    if not sa.inspect(bind).has_table('lessons'):
        return set()
    return {row[1] for row in bind.exec_driver_sql('PRAGMA table_info("lessons")')}


def upgrade() -> None:
    cols = _columns(op.get_bind())
    with op.batch_alter_table('lessons') as batch_op:
        if 'custom_start_time' not in cols:
            batch_op.add_column(sa.Column('custom_start_time', sa.String(), nullable=True))
        if 'custom_end_time' not in cols:
            batch_op.add_column(sa.Column('custom_end_time', sa.String(), nullable=True))
        if 'event_type' not in cols:
            batch_op.add_column(sa.Column('event_type', sa.String(), nullable=True))


def downgrade() -> None:
    cols = _columns(op.get_bind())
    with op.batch_alter_table('lessons') as batch_op:
        for column in ('event_type', 'custom_end_time', 'custom_start_time'):
            if column in cols:
                batch_op.drop_column(column)
