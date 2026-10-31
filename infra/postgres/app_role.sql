-- Run as a schema owner / privileged DBA, never as the application role.
-- First create a login with a strong password securely outside this file, e.g.
-- CREATE ROLE loyalty_app LOGIN PASSWORD '<generated secret>';
-- Then execute this grants script as your database administrator.
GRANT CONNECT ON DATABASE loyalty TO loyalty_app;
GRANT USAGE ON SCHEMA public TO loyalty_app;
GRANT SELECT ON TABLE public.tenants, public.api_credentials, public.branches TO loyalty_app;
REVOKE CREATE ON SCHEMA public FROM loyalty_app;
-- Do not grant table ownership, bypassrls or schema DDL to loyalty_app.
-- For tenant-scoped tables, FORCE RLS is configured by migrations.
