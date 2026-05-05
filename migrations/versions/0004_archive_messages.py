"""Add message archive metadata.

Revision ID: 0004_archive_messages
Revises: 0003_rename_roles
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_archive_messages"
down_revision = "0003_rename_roles"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("messages", sa.Column("retain_until", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("messages", "retain_until")
    op.drop_column("messages", "archived_at")
