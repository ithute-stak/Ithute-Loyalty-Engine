"""Add tenant-scoped hashed API credentials.

Revision ID: 0002_api_credentials
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_api_credentials"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_credentials_tenant_id", "api_credentials", ["tenant_id"])
    # Key lookup must use narrowly granted SELECT; keys are not returned to merchants.
    # Company data remains governed by forced RLS on the tenant-owned tables.


def downgrade():
    op.drop_table("api_credentials")
