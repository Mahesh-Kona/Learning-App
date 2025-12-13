"""Remove unused columns from students table

Revision ID: 9012defg
Revises: 8901cdef
Create Date: 2025-12-08 19:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '9012defg'
down_revision = '8901cdef'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('students', schema=None) as batch_op:
        # Drop columns that we don't need
        try:
            batch_op.drop_column('created_at')
        except:
            pass
        
        try:
            batch_op.drop_column('grade')
        except:
            pass
        
        try:
            batch_op.drop_column('school')
        except:
            pass


def downgrade():
    pass
