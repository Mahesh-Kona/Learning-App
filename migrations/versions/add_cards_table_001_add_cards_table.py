"""Add cards table for concept, quiz, video, and interactive cards

Revision ID: add_cards_table_001
Revises: 9012defg
Create Date: 2025-12-10 22:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'add_cards_table_001'
down_revision = '9012defg'
branch_labels = None
depends_on = None


def upgrade():
    # Create cards table
    op.create_table('cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=True),
        sa.Column('lesson_id', sa.Integer(), nullable=True),
        sa.Column('card_type', sa.Enum('concept', 'quiz', 'video', 'interactive', name='card_type'), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('data_json', mysql.JSON(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('published', sa.Boolean(), nullable=True, server_default='0'),
        sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ),
        sa.ForeignKeyConstraint(['lesson_id'], ['lessons.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_cards_card_type'), 'cards', ['card_type'], unique=False)
    op.create_index(op.f('ix_cards_created_at'), 'cards', ['created_at'], unique=False)
    op.create_index(op.f('ix_cards_display_order'), 'cards', ['display_order'], unique=False)
    op.create_index(op.f('ix_cards_topic_id'), 'cards', ['topic_id'], unique=False)
    op.create_index(op.f('ix_cards_lesson_id'), 'cards', ['lesson_id'], unique=False)
    op.create_index(op.f('ix_cards_published'), 'cards', ['published'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index(op.f('ix_cards_published'), table_name='cards')
    op.drop_index(op.f('ix_cards_lesson_id'), table_name='cards')
    op.drop_index(op.f('ix_cards_topic_id'), table_name='cards')
    op.drop_index(op.f('ix_cards_display_order'), table_name='cards')
    op.drop_index(op.f('ix_cards_created_at'), table_name='cards')
    op.drop_index(op.f('ix_cards_card_type'), table_name='cards')
    
    # Drop table
    op.drop_table('cards')
