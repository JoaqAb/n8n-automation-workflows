-- Roles que replican los de Supabase, para que los mismos esquemas, las mismas
-- policies de RLS y la misma API REST corran contra un Postgres propio.
-- service_role es bypassrls, igual que en Supabase.
create role anon nologin noinherit;
create role authenticated nologin noinherit;
create role service_role nologin noinherit bypassrls;
create role authenticator noinherit login password 'portfolio-local';
grant anon to authenticator;
grant authenticated to authenticator;
grant service_role to authenticator;

grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public
  grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public
  grant all on sequences to anon, authenticated, service_role;
