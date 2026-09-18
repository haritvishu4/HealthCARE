"""Repair older local databases missing the workspace account role column."""

import sqlalchemy as sa
from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("workspace_accounts")}
    if "role" not in columns:
        op.add_column(
            "workspace_accounts",
            sa.Column("role", sa.String(length=20), nullable=False, server_default="patient"),
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("workspace_accounts")}
    if "role" in columns:
        op.drop_column("workspace_accounts", "role")