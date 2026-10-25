"""add specialties table and group specialty_id

Revision ID: e5f6a7b8c9d0
Revises: df2a1c3b4e5f
Create Date: 2026-08-03 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'df2a1c3b4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'specialties',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('qualification', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True),
    )
    with op.batch_alter_table('groups_list') as batch_op:
        batch_op.add_column(sa.Column('specialty_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_groups_list_specialty', 'specialties', ['specialty_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('groups_list') as batch_op:
        batch_op.drop_constraint('fk_groups_list_specialty', type_='foreignkey')
        batch_op.drop_column('specialty_id')
    op.drop_table('specialties')