"""Store the local workspace account in the application database."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="patient"),
        sa.Column("algorithm", sa.String(length=40), nullable=False),
        sa.Column("salt", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )


def downgrade():
    op.drop_table("workspace_accounts")