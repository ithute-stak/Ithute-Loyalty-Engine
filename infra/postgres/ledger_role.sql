-- Apply as privileged database administrator AFTER Alembic migrations.
-- The role must already exist with a securely generated password:
-- CREATE ROLE loyalty_ledger LOGIN PASSWORD '<secret>';
-- Never use the schema owner, superuser or BYPASSRLS as runtime.
GRANT CONNECT ON DATABASE loyalty TO loyalty_ledger;
GRANT USAGE ON SCHEMA public TO loyalty_ledger;
GRANT SELECT ON public.points_accounts, public.points_entries TO loyalty_ledger;
GRANT UPDATE (balance) ON public.points_accounts TO loyalty_ledger;
GRANT INSERT ON public.points_entries TO loyalty_ledger;
REVOKE CREATE ON SCHEMA public FROM loyalty_ledger;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.points_entries FROM loyalty_ledger;
-- The ledger does not require write privileges on tenants or loyalty_programmes.
-- RLS still requires transaction-local app.tenant_id on every command.
