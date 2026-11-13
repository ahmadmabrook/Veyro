#!/usr/bin/env bash
# Rebuild the MOD-004 control-plane database from nothing, apply the migrations, and run the
# tenant-isolation negative tests against the result.
#
#   backend/scripts/verify_db.sh                      # local, against the veyro-pg container
#   MUTATE="ALTER TABLE ... ;" backend/scripts/verify_db.sh   # mutation test: the suite MUST fail
#   TAMPER="DELETE FROM ... ;" backend/scripts/verify_db.sh   # edits seeded rows, then re-verifies
#
# PSQL defaults to the local container. Set PSQL to any psql invocation that reads SQL on stdin
# (CI passes a plain `psql "$DATABASE_URL"`).
set -euo pipefail

PSQL=${PSQL:-"docker exec -i veyro-pg psql -U postgres"}
ROOT=$(cd "$(dirname "$0")/.." && pwd)

run() { $PSQL -v ON_ERROR_STOP=1 -q "$@"; }

# The roles are cluster-wide, so a true rebuild drops them with the database. Dropping the
# database first leaves the roles owning nothing, which is what lets DROP ROLE succeed.
run -d postgres <<'EOF'
DROP DATABASE IF EXISTS veyro;
DROP ROLE IF EXISTS veyro_iam_app;
DROP ROLE IF EXISTS veyro_cp_app;
DROP ROLE IF EXISTS veyro_cp_worker;
DROP ROLE IF EXISTS veyro_cp_platform;
DROP ROLE IF EXISTS veyro_cp_bootstrap;
DROP ROLE IF EXISTS veyro_cp_migrator;
CREATE DATABASE veyro;
EOF

# 0001 creates the roles and so runs as the bootstrap connection; everything after it runs as
# the migrator, which is what makes the migrator -- not a superuser -- the table owner. A
# superuser-owned table would bypass RLS no matter what FORCE says.
for f in "$ROOT"/migrations/platform/*.sql "$ROOT"/migrations/tenant/*.sql \
         "$ROOT"/migrations/product/*.sql; do
    if $PSQL -tAq -d veyro -c "SELECT 1 FROM pg_roles WHERE rolname='veyro_cp_migrator'" | grep -q 1; then
        { echo "SET ROLE veyro_cp_migrator;"; cat "$f"; } | run -d veyro
    else
        run -d veyro < "$f"
    fi
    echo "applied $(basename "$f")"
done

if [ -n "${MUTATE:-}" ]; then
    echo "applying mutation: $MUTATE"
    run -d veyro -c "SET ROLE veyro_cp_migrator; $MUTATE"
fi

run -d veyro < "$ROOT/tests/sql/isolation.sql"

# TAMPER applies here, between the isolation suite and the audit-chain verification, because
# MUTATE runs before any data exists: a DELETE or an UPDATE aimed at the audit log has to land
# on rows the suite has already seeded, or it silently tests nothing.
if [ -n "${TAMPER:-}" ]; then
    echo "applying tamper: $TAMPER"
    run -d veyro -c "$TAMPER"
fi

run -d veyro < "$ROOT/tests/sql/audit_chain.sql"
