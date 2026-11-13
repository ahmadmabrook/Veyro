-- MOD-004 PLT-01 platform track: control-plane roles and the two schemas.
--
-- Roles are cluster-wide and created once against a fresh cluster. No GRANT <role> TO <role>
-- anywhere: ADR-0002 D6.1 item 1 bars membership edges, so each role stands alone and the
-- application connects as exactly the role whose privileges it is meant to have.
--
-- NOINHERIT on every role is belt-and-braces: with no membership edges there is nothing to
-- inherit, but a later accidental GRANT must not silently widen a runtime role.

CREATE ROLE veyro_cp_migrator NOLOGIN NOINHERIT;
CREATE ROLE veyro_cp_platform NOLOGIN NOINHERIT;
CREATE ROLE veyro_cp_bootstrap NOLOGIN NOINHERIT;
CREATE ROLE veyro_cp_app NOLOGIN NOINHERIT;
CREATE ROLE veyro_cp_worker NOLOGIN NOINHERIT;

-- PUBLIC must hold nothing on the database or on the schemas. Without this revoke every role
-- in the cluster keeps the default CONNECT and TEMPORARY, which D5 bullet 3 bars.
REVOKE ALL ON DATABASE veyro FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

GRANT CONNECT ON DATABASE veyro TO veyro_cp_migrator;
GRANT CONNECT ON DATABASE veyro TO veyro_cp_platform;
GRANT CONNECT ON DATABASE veyro TO veyro_cp_app;
GRANT CONNECT ON DATABASE veyro TO veyro_cp_worker;

CREATE SCHEMA plt01_platform AUTHORIZATION veyro_cp_migrator;
CREATE SCHEMA plt01 AUTHORIZATION veyro_cp_migrator;

-- USAGE only. Object privileges are granted per table by the migration that creates it, so a
-- new table is unreachable until its own migration says who may read it.
GRANT USAGE ON SCHEMA plt01_platform TO veyro_cp_platform;
GRANT USAGE ON SCHEMA plt01_platform TO veyro_cp_app;
GRANT USAGE ON SCHEMA plt01_platform TO veyro_cp_worker;
GRANT USAGE ON SCHEMA plt01 TO veyro_cp_app;
GRANT USAGE ON SCHEMA plt01 TO veyro_cp_worker;
