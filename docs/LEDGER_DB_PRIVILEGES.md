# Ledger database role — least privilege

Run Alembic migrations with a privileged *migration owner* account. Create a
separate `loyalty_ledger` login with a securely generated password outside
source control, then apply `infra/postgres/ledger_role.sql` as a DBA.

The dedicated Rust ledger role is granted:
- SELECT on points_accounts and points_entries;
- UPDATE of **balance only** on points_accounts;
- INSERT on points_entries.

It must not own tables, use BYPASSRLS, insert tenants, delete ledger rows or
modify schema. Every Rust operation uses transaction-local `app.tenant_id`;
forced RLS is applied to accounts and entries by migration 0005.

## Critical operational limitations

PostgreSQL column privileges alone do not guarantee ledger correctness: this
role can change an account's balance without adding an entry. The trusted Rust
posting service must enforce atomic entry-plus-projection updates, and
reconciliation must alert on divergence. Additional database-enforced posting
routines are a future hardening step.

The SQL script assumes database name `loyalty` and a pre-existing
`loyalty_ledger` role; deployments using other database names must adapt
the CONNECT grant. Do not execute against production without reviewing existing
grants and role inheritance. Confirm the login has no additional inherited
permissions. CI now creates this role and checks the expected privileges
against a migrated disposable database.

The existing Rust concurrency tests still use the migration owner's connection
for fixture setup; running the actual post/reverse functions with a restricted
ledger role remains a separate integration gate.
