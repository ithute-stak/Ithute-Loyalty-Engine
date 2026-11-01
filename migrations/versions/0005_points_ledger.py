"""Persistent tenant-scoped points accounts and append-only entries.

Revision ID: 0005_points_ledger
Revises: 0004_invitations
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0005_points_ledger"
down_revision = "0004_invitations"
branch_labels = None
depends_on = None


def _rls(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY tenant_isolation ON {table}
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")


def upgrade():
    op.create_table(
        "points_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("programme_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_ref", sa.String(255), nullable=False),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "programme_id"],
                                ["loyalty_programmes.tenant_id", "loyalty_programmes.id"]),
        sa.UniqueConstraint("tenant_id", "id", name="uq_points_account_tenant_id"),
        sa.UniqueConstraint("tenant_id", "programme_id", "customer_ref", name="uq_points_account_member"),
        sa.CheckConstraint("balance >= 0", name="ck_points_account_nonnegative"),
    )
    op.create_index("ix_points_accounts_tenant", "points_accounts", ["tenant_id"])
    op.create_table(
        "points_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("reverses_entry_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id", "account_id"],
                                ["points_accounts.tenant_id", "points_accounts.id"]),
        sa.UniqueConstraint("tenant_id", "account_id", "event_id", name="uq_points_entry_idempotency"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_points_entry_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id", "reverses_entry_id"],
                                ["points_entries.tenant_id", "points_entries.id"]),
        sa.CheckConstraint("kind IN ('earn','redeem','reverse')", name="ck_points_entry_kind"),
        sa.CheckConstraint("delta <> 0", name="ck_points_entry_nonzero"),
        sa.CheckConstraint("balance_after >= 0", name="ck_points_entry_balance"),
    )
    op.create_index("uq_points_entry_reversal", "points_entries", ["reverses_entry_id"],
                    unique=True, postgresql_where=sa.text("reverses_entry_id IS NOT NULL"))
    op.create_index("ix_points_entries_account_created", "points_entries",
                    ["tenant_id", "account_id", "created_at"])
    for table in ("points_accounts", "points_entries"):
        _rls(table)
    # Runtime writes must only be granted to the dedicated ledger role, not generic API users.


def downgrade():
    op.drop_table("points_entries")
    op.drop_table("points_accounts")
