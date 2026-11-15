"""mission day override for the Demo panel

Revision ID: c4e1f2a9b310
Revises: 7b609089030a
Create Date: 2026-11-14 23:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e1f2a9b310'
down_revision = '7b609089030a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('mission', schema=None) as batch_op:
        batch_op.add_column(sa.Column('day_override', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('mission', schema=None) as batch_op:
        batch_op.drop_column('day_override')
