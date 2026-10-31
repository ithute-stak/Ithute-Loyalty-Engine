"""One-use invitations and tenant audit events.

Revision ID: 0004_invitations
Revises: 0003_company_access
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0004_invitations"
down_revision = "0003_company_access"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("company_invitations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("role_code", sa.String(64), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["tenant_id","branch_id"], ["branches.tenant_id","branches.id"]),
        sa.ForeignKeyConstraint(["tenant_id","created_by"], ["company_users.tenant_id","company_users.id"]),
    )
    op.create_table("company_audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True)),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("subject_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id","actor_id"], ["company_users.tenant_id","company_users.id"]),
    )
    for table in ("company_invitations","company_audit_events"):
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} "
                   "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
                   "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)")

def downgrade():
    op.drop_table("company_audit_events")
    op.drop_table("company_invitations")
