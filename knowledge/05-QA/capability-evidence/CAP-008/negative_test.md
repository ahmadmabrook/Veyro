---
doc: CAP-008_NEGATIVE_TEST
capability: CAP-008 (Docker Engine / Docker Desktop local + postgres:16-alpine@pinned-digest)
result: PASS
run_by: Sonnet (claude-sonnet-5), 2026-10-01 ~11:37 UTC
---

# CAP-008 negative/fail-closed test

Full detail, provenance, and license context: see `provenance_and_license.md`
in this same folder (single source of truth — not duplicated here).

**Test**: with the Docker daemon unreachable (verified, not induced — the
daemon was already down before this session started), invoke the project's
real harness entry point `backend.tests.harness.postgres.disposable_postgres()`
directly and confirm it raises rather than silently mocking or skipping.

**Command**:
```
backend/.venv/bin/python -c "
import sys; sys.path.insert(0, 'backend/tests')
from harness.postgres import disposable_postgres
try:
    with disposable_postgres(ready_timeout_s=5):
        print('UNEXPECTED: container started')
except RuntimeError as e:
    print('FAIL-CLOSED CONFIRMED:', str(e)[:200])
"
```

**Result**: `FAIL-CLOSED CONFIRMED: \`docker run\` exit 1: Cannot connect
to the Docker daemon at unix:///Users/ahmadmabrouk/.docker/run/docker.sock.
Is the docker daemon running?; the GOV-01-R02 harness needs a local Docker
engine and ne[...]`. Clean `RuntimeError`, no mock/fallback/skip, no
container created. `docker ps -a --filter name=veyro-mod001-harness`
independently confirms zero leftover containers.

**Disposition**: PASS. This session did not start Docker Desktop or its
daemon at any point — the test exploits the daemon's pre-existing down
state rather than inducing it.

**Positive test**: not run — see `provenance_and_license.md`'s "Stage 5"
section for why (Docker Desktop license-eligibility blocker, unresolved,
owner-only fact).

## Re-run, same session continuation, 2026-10-01 ~11:40 UTC

Re-invoked identically to confirm the result is stable, not a one-off:
same `FAIL-CLOSED CONFIRMED` `RuntimeError`, same zero-leftover-container
result (`docker ps -a --filter name=veyro-mod001-harness`), Docker
Desktop process confirmed still not running (`pgrep -fl "Docker.app"` →
no match) before and after. `docker context ls` shows `desktop-linux` as
the only configured engine context on this machine — no non-Desktop
Docker Engine backend exists here, so this capability cannot be exercised
at all without Desktop activation, which remains out of scope while
license eligibility is unresolved. Disposition unchanged: **PASS**
(negative), positive still not run.
