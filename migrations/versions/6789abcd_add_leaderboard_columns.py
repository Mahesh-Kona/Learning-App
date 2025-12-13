"""Add leaderboard columns

Revision ID: 6789abcd
Revises: a79a1e73dbb7
Create Date: 2025-12-08 19:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '6789abcd'
down_revision = 'a79a1e73dbb7'
branch_labels = None
depends_on = None


def upgrade():
    # Clean up orphaned user_ids first (if any exist in leaderboard)
    try:
        connection = op.get_bind()
        connection.execute('''
            UPDATE leaderboard 
            SET user_id = NULL 
            WHERE user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM users)
        ''')
    except:
        pass
    
    # Add/alter columns in leaderboard table
    with op.batch_alter_table('leaderboard', schema=None) as batch_op:
        # Make user_id nullable
        try:
            batch_op.alter_column('user_id',
                   existing_type=mysql.INTEGER(display_width=11),
                   nullable=True)
        except:
            pass
        
        # Add missing columns
        try:
            batch_op.add_column(sa.Column('status', sa.String(length=50), nullable=True))
        except:
            pass
        
        try:
            batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        except:
            pass
        
        # Drop columns that shouldn't be there
        try:
            batch_op.drop_column('email')
        except:
            pass
        
        try:
            batch_op.drop_column('last_updated_date')
        except:
            pass
        
        try:
            batch_op.drop_column('league')
        except:
            pass


def downgrade():
    pass

