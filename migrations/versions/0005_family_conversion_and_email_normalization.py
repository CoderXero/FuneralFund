"""Add family conversion metadata and normalize user emails.

Revision ID: 0005_family_conversion
Revises: 0004_archive_messages
Create Date: 2026-05-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_family_conversion"
down_revision = "0004_archive_messages"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("family_members") as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("converted_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_family_members_converted_user_id_users",
            "users",
            ["converted_user_id"],
            ["id"],
        )
    op.execute("update users set email = lower(trim(email))")


def downgrade():
    with op.batch_alter_table("family_members") as batch_op:
        batch_op.drop_constraint("fk_family_members_converted_user_id_users", type_="foreignkey")
        batch_op.drop_column("converted_user_id")
        batch_op.drop_column("email")
