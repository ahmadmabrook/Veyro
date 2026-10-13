import psycopg
from tests.harness.postgres import disposable_postgres
from tests.harness.tenant_isolation import ACCESS_GRANT, ACCESS_GRANT_COLUMNS, OWNER_ROLE, RUNTIME_ROLE, create_tenant_table, provision_roles
# The exact break/restore pair from test_tenant_isolation_harness.py BREAKAGES["runtime_owns_table"].
BREAK = f"ALTER TABLE harness.access_grant OWNER TO {RUNTIME_ROLE}"
RESTORE = f"ALTER TABLE harness.access_grant OWNER TO {OWNER_ROLE}"
Q = "SELECT has_table_privilege(%s, 'harness.access_grant', 'SELECT, INSERT, UPDATE, DELETE'), (SELECT relacl::text FROM pg_class WHERE oid='harness.access_grant'::regclass)"
with disposable_postgres() as pg, psycopg.connect(pg.superuser_dsn, autocommit=True) as admin:
    provision_roles(admin); create_tenant_table(admin, ACCESS_GRANT, ACCESS_GRANT_COLUMNS)
    print("before :", admin.execute(Q, (RUNTIME_ROLE,)).fetchone())
    admin.execute(BREAK); admin.execute(RESTORE)
    print("after  :", admin.execute(Q, (RUNTIME_ROLE,)).fetchone())
