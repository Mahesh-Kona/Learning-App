"""Add questions_json column to practice_quizzes

Revision ID: f0e1d2c3b4a5
Revises: cafe20260123
Create Date: 2026-03-12 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'f0e1d2c3b4a5'
down_revision = 'cafe20260123'
branch_labels = None
depends_on = None


def upgrade():
    """Add JSON column for storing practice quiz questions."""
    with op.batch_alter_table('practice_quizzes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('questions_json', mysql.JSON(), nullable=True))


def downgrade():
    """Drop JSON column for practice quiz questions."""
    with op.batch_alter_table('practice_quizzes', schema=None) as batch_op:
        try:
            batch_op.drop_column('questions_json')
        except Exception:
            # Be defensive in case the column was removed manually
            pass
