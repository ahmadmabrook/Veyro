#!/bin/bash
# Every CI step that runs without Docker or a built image, in CI's own order.
#
# **Why this exists.** `CLAUDE.md`'s "Running it" section lists the database rebuild, the two
# backend linters, the two backend suites and the worker -- and `.github/workflows/`
# veyro-foundation-ci.yml runs eleven more steps on top of those. Running what the file lists
# is not running what CI runs, and that cost a red `main` on **both jobs at once**: the
# governance structural check refused an ADR header written as prose, and `design:coverage`
# refused three backlog entries whose module had just landed -- the second being a check this
# repository wrote specifically to catch a stale excuse, firing correctly on its author.
#
# It deliberately leaves out four things, and says which rather than implying coverage: the
# container build, its smoke test and the rollback rehearsal, which need Docker images; the
# browser suite, which needs a provisioned fixture and a port; and **`verify_db.sh`, which
# drops and rebuilds the development database** -- running that from a convenience script
# would destroy whatever fixture another session in this checkout is holding, which this
# repository's rules file records as a real hazard. Run it deliberately:
#
#     PSQL="docker exec -i <your container> psql -U postgres" backend/scripts/verify_db.sh
#
# What is here is everything a local run can answer without taking something away from
# somebody, so "I ran the checks" and "I ran the checks CI runs" stop being different claims.
#
#     tools/local_ci.sh
cd "$(dirname "$0")/.." || exit 1
# **`-B`, as CI does.** The domain-closure check refuses a `__pycache__` inside a lane root,
# and an ordinary local test run creates one -- so this script failed twice on an artefact of
# itself while CI was clean, because CI runs `python -B`. Cleaning first as well, because a
# pycache from an earlier run is still there.
find backend -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
PY=".venv/bin/python3 -B"
fail=0
step() {
  local name="$1"; shift
  local out; out=$("$@" 2>&1); local code=$?
  if [ "$code" -eq 0 ]; then printf 'ok    %s\n' "$name"
  else fail=1; printf 'FAIL  %s\n' "$name"; echo "$out" | tail -6 | sed 's/^/        /'; fi
}
step "compileall (tools)"        .venv/bin/python3 -m compileall -q tools/mission_runner tools/governance tools/domain_closure
step "workflow trigger shape"    $PY tools/mission_runner/workflow_check.py
step "MOD-000 runner suite"      $PY -m unittest discover -s tools/mission_runner/tests -t tools/mission_runner
step "governance validator suite" $PY -m unittest discover -s tools/governance/tests -t tools/governance
step "governance structural"     $PY tools/governance/governance_check.py check --root .
step "domain closure"            $PY tools/domain_closure/domain_closure.py check --root .
step "domain closure suite"      $PY -m unittest discover -s tools/domain_closure/tests -t tools/domain_closure
step "trusted gate suite"        $PY -m unittest discover -s tools/trusted_gate/tests -t tools/trusted_gate
step "screen contract identity"  node tools/screen_contracts/screen_contracts.mjs check-identity
step "backend ruff"              $PY -m ruff check backend
( cd backend && ../.venv/bin/python3 -m mypy >/dev/null 2>&1 ) && echo "ok    backend mypy" || { fail=1; echo "FAIL  backend mypy"; }
for s in audit:ci lint design:check tokens:check test:foundation typecheck; do
  out=$(cd web && npm run "$s" 2>&1); code=$?
  if [ "$code" -eq 0 ]; then printf 'ok    web %s\n' "$s"
  else fail=1; printf 'FAIL  web %s\n' "$s"; echo "$out" | tail -8 | sed 's/^/        /'; fi
done
echo
[ "$fail" -eq 0 ] && echo "every non-docker CI step passed" || echo "SOMETHING FAILED"
exit $fail
