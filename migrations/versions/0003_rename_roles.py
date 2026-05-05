"""Rename application roles.

Revision ID: 0003_rename_roles
Revises: 0002_messages
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op


revision = "0003_rename_roles"
down_revision = "0002_messages"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("update users set role = 'community_admin' where role = 'leader'")
    op.execute("update users set role = 'community_user' where role = 'member'")


def downgrade():
    op.execute("update users set role = 'leader' where role = 'community_admin'")
    op.execute("update users set role = 'member' where role = 'community_user'")
