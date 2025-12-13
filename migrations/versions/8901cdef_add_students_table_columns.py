"""Add students table columns

Revision ID: 8901cdef
Revises: 6789abcd
Create Date: 2025-12-08 19:25:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '8901cdef'
down_revision = '6789abcd'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('students', schema=None) as batch_op:
        try:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        except:
            pass
        
        try:
            batch_op.add_column(sa.Column('grade', sa.String(length=50), nullable=True))
        except:
            pass
        
        try:
            batch_op.add_column(sa.Column('school', sa.String(length=255), nullable=True))
        except:
            pass
        
        try:
            batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        except:
            pass


def downgrade():
    pass
