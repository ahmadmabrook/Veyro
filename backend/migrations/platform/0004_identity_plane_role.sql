-- MOD-007 IAM-01: the identity plane's role and schema.
--
-- **This file creates a role, so it must run as the bootstrap connection, not as the migrator.**
-- `RESET ROLE` below undoes the `SET ROLE veyro_cp_migrator` that `verify_db.sh` prepends to
-- every migration after the first; the schema is then created AUTHORIZATION veyro_cp_migrator
-- so that the identity tables still end up owned by the migrator rather than by a superuser. A
-- superuser-owned table bypasses row-level security whatever FORCE says, which is the whole
-- reason the migrator owns everything else.
RESET ROLE;

-- TSD paragraph 1151 puts IAM-01 in a "Product PostgreSQL iam schema", a different plane from
-- the control-plane database the PLT modules use. **This repository provisions one cluster and
-- one database, so the plane boundary here is a schema and a role, not a separate server.** The
-- property that actually matters is intact and is asserted by checks 27 and 28: `veyro_cp_app`
-- cannot reach `iam`, `veyro_iam_app` cannot reach `plt01` or the tenant registry, and neither
-- is a member of the other. Moving `iam` to its own database later is a connection string and
-- this file; nothing above it changes.
--
-- Why it is worth separating at all: `veyro_cp_app` is the role serving tenant configuration and
-- billing requests. If credential hashes lived in `plt01`, a SQL mistake anywhere in those paths
-- could read them. They do not, so it cannot.
CREATE ROLE veyro_iam_app NOLOGIN NOINHERIT;

GRANT CONNECT ON DATABASE veyro TO veyro_iam_app;

CREATE SCHEMA iam AUTHORIZATION veyro_cp_migrator;

-- USAGE only, and only for the identity role. Object privileges are granted per table by the
-- migration that creates it.
GRANT USAGE ON SCHEMA iam TO veyro_iam_app;

-- The identity role needs the tenant registry to exist as a foreign-key target, but it is never
-- granted anything on `plt01_platform` or `plt01`. A foreign key is enforced by the system, not
-- by the inserting role's privileges, so containment holds without a grant.
