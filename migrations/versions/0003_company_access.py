"""Company users, roles and branch-scoped access.

Revision ID: 0003_company_access
Revises: 0002_api_credentials
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_company_access"
down_revision = "0002_api_credentials"
branch_labels = None
depends_on = None

def tenant_policy(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )

def upgrade():
    op.create_table(
        "company_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_subject", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "external_subject", name="uq_user_tenant_subject"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_user_tenant_id"),
    )
    op.create_table(
        "company_roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_role_tenant_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_role_tenant_id"),
    )
    op.create_table(
        "company_user_roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id", "user_id"], ["company_users.tenant_id", "company_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "role_id"], ["company_roles.tenant_id", "company_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "user_id", "role_id", "branch_id", name="uq_membership_scope"),
    )
    op.create_index("ix_company_users_tenant_id", "company_users", ["tenant_id"])
    op.create_index("ix_company_roles_tenant_id", "company_roles", ["tenant_id"])
    op.create_index("ix_company_user_roles_tenant_id", "company_user_roles", ["tenant_id"])
    # PostgreSQL UNIQUE treats NULL as distinct. Use a partial unique index for global assignments.
    op.create_index("uq_membership_global", "company_user_roles",
        ["tenant_id", "user_id", "role_id"], unique=True,
        postgresql_where=sa.text("branch_id IS NULL"))
    for table in ("company_users", "company_roles", "company_user_roles"):
        tenant_policy(table)

def downgrade():
    op.drop_table("company_user_roles")
    op.drop_table("company_roles")
    op.drop_table("company_users")
