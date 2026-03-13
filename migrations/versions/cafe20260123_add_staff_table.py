"""Add staff table

Revision ID: cafe20260123
Revises: 4ed06ecee594
Create Date: 2026-01-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = 'cafe20260123'
down_revision = '4ed06ecee594'
branch_labels = None
depends_on = None


def upgrade():
    # Enums (safe on MySQL; ignored/handled by others)
    try:
        sa.Enum('male', 'female', 'other', name='staff_gender').create(op.get_bind(), checkfirst=True)
    except Exception:
        pass

    try:
        sa.Enum('active', 'inactive', name='staff_status').create(op.get_bind(), checkfirst=True)
    except Exception:
        pass

    # Only create the staff table if it does not already exist.
    # This makes the migration idempotent in environments where the table
    # was created manually or by a previous run.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'staff' not in existing_tables:
        op.create_table(
            'staff',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True, index=True),

            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('gender', sa.Enum('male', 'female', 'other', name='staff_gender'), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('phone', sa.String(length=20), nullable=False),
            sa.Column('city', sa.String(length=120), nullable=True),
            sa.Column('department', sa.String(length=100), nullable=True),

            sa.Column('role', sa.String(length=100), nullable=False),
            sa.Column('status', sa.Enum('active', 'inactive', name='staff_status'), nullable=False, server_default='active'),
            sa.Column('permissions', mysql.JSON(), nullable=True),

            sa.Column('avatar', sa.String(length=1024), nullable=True),
            sa.Column('join_date', sa.Date(), nullable=True),

            sa.Column('password_hash', sa.String(length=255), nullable=True),
            sa.Column('send_email', sa.Boolean(), nullable=False, server_default=sa.text('1')),
            sa.Column('send_sms', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.Column('last_login_at', sa.DateTime(), nullable=True),

            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),

            sa.UniqueConstraint('email', name='uq_staff_email'),
        )

    # Indexes
    try:
        op.create_index('ix_staff_email', 'staff', ['email'], unique=True)
    except Exception:
        pass
    try:
        op.create_index('ix_staff_role', 'staff', ['role'], unique=False)
    except Exception:
        pass
    try:
        op.create_index('ix_staff_status', 'staff', ['status'], unique=False)
    except Exception:
        pass
    try:
        op.create_index('ix_staff_department', 'staff', ['department'], unique=False)
    except Exception:
        pass
    try:
        op.create_index('ix_staff_user_id', 'staff', ['user_id'], unique=False)
    except Exception:
        pass


def downgrade():
    try:
        op.drop_index('ix_staff_user_id', table_name='staff')
    except Exception:
        pass
    try:
        op.drop_index('ix_staff_department', table_name='staff')
    except Exception:
        pass
    try:
        op.drop_index('ix_staff_status', table_name='staff')
    except Exception:
        pass
    try:
        op.drop_index('ix_staff_role', table_name='staff')
    except Exception:
        pass
    try:
        op.drop_index('ix_staff_email', table_name='staff')
    except Exception:
        pass

    try:
        op.drop_table('staff')
    except Exception:
        pass

    try:
        sa.Enum(name='staff_status').drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass

    try:
        sa.Enum(name='staff_gender').drop(op.get_bind(), checkfirst=True)
    except Exception:
        pass
