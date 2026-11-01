"""Forbid mutation of already posted loyalty entries.

Revision ID: 0006_ledger_immutability
Revises: 0005_points_ledger
"""
from alembic import op

revision = "0006_ledger_immutability"
down_revision = "0005_points_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION reject_points_entry_mutation() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'loyalty points ledger entries are immutable';
    END;
    $$;
    """)
    op.execute("""
    CREATE TRIGGER points_entries_append_only
    BEFORE UPDATE OR DELETE ON points_entries
    FOR EACH ROW EXECUTE FUNCTION reject_points_entry_mutation();
    """)


def downgrade():
    op.execute("DROP TRIGGER points_entries_append_only ON points_entries")
    op.execute("DROP FUNCTION reject_points_entry_mutation()")
