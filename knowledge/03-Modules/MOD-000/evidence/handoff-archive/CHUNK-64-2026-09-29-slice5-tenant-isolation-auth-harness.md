## What happened chunk 64, 2026-09-29 — GOV-01-R02 critical slice (Slice 5): tenant-isolation/RLS harness + authentication negative-credential fixture pattern, dispatched to `veyro-critical-engineer` (Opus) per ADR-005, executed against a real disposable Postgres

Mission named GOV-01-R02 as the one critical slice for this turn,
explicitly routed to `veyro-critical-engineer` on Opus. Bootstrap
re-verified fresh (local HEAD == `origin/main` == `3552299`, Autonomous
Development Mode active, CAP-007 retired, BUG-036 closed, Slices 1-4
complete). Re-read `REQUIREMENTS.md` GOV-01-R02, `ADR-005`,
`.claude/rules/backend/{database,architecture,api,performance,concurrency}.md`,
`SCENARIOS.md`'s GOV-01-R02-tagged scenarios, and `IMPLEMENTATION.md`
§1-4 before dispatching.

**Scope boundary set before dispatch, stated explicitly rather than left
implicit:** `ADR-005` Decision 1 bounds `veyro-critical-engineer` to
three named slices (tenant-isolation/RLS harness; auth negative-credential
fixture; the RLS-lint+permission-lint gates). The mission's own text
listed all three as "applicable obligations," but the mission's own
header also said "This turn is for GOV-01-R02 only" — the gates are
GOV-01-R04. Resolved as: dispatch the two genuinely R02 items only (one
coherent slice), leave the R04 gates for a separate future dispatch
(their own valid-fixture needs real committed backend schema to lint
against, which this slice produces — natural ordering, not an
avoidance). Also found, before dispatch: the six named domain suite
scaffolds (membership/booking/payment/ledger/pos/access) and the
financial-invariant placeholder harness are GOV-01-R02 text obligations
per `REQUIREMENTS.md`, but `ADR-005` does NOT list them among the
critical-engineer's bounded slices, and `SCENARIOS.md` itself routes
SCN-MOD001-132/133 to `veyro-implementer`/Sonnet, not the critical
role — left out of this dispatch for the same reason, available as a
separate future routine slice.

**A real capability gap found and closed before dispatch:** no
`psql`/Postgres locally, and Docker's daemon was not running (`docker
info` failed) — a genuine blocker for a real RLS proof (SQLite has no
roles/RLS; faking it would be exactly the false-clean harness failure
mode `ADR-005`/the critical-engineer's own charter warn against).
Started Docker Desktop (`open -a Docker`), waited for the daemon (up in
~20s, Engine 29.6.0/29.7.2), and pulled `postgres:16-alpine` — a
free, local-only, synthetic-data-only capability, no owner approval
needed. Recorded as a fact available to the dispatch, not assumed.

**Dispatch: `veyro-critical-engineer` (Opus), foreground.** Full brief
covered the governing text, the exact scope boundary above, the
Docker/Postgres fact, the scenario IDs to satisfy (SCN-MOD001-027/028/
067/097), the negative-proof strategy `database.md`/the agent's own
charter require (production-equivalent non-privileged runtime role
only, ground-truth-observer pattern, a deliberately-broken-fixture
counter-proof), and the dependency-addition path already established by
`BUG-036` (wheel-only download → `generate_requirements_lock.py` →
`--require-hashes` install).

**What it built, independently re-verified by this session (not taken
on the subagent's report alone):** `backend/tests/harness/{postgres,
tenant_isolation,authn}.py` plus integration/unit tests. A real,
disposable, digest-pinned `postgres:16-alpine` container per pytest
session (127.0.0.1-only, force-removed after). Two distinct roles —
`veyro_schema_owner` (NOLOGIN, owns the tables) and `veyro_runtime`
(LOGIN, NOSUPERUSER, NOBYPASSRLS, no memberships, owns nothing,
password sent only as a SCRAM verifier, never cleartext to the server).
The canonical `access_grant` fixture (SCN-067) has `tenant_id NOT NULL`,
`ENABLE`/`FORCE ROW LEVEL SECURITY`, and a policy keyed on a
transaction-local `app.tenant_id` setting. Every negative-isolation
probe is measured against ground truth read by a separate superuser
observer (so "0 rows" can't mean "nothing was there"), and the harness
refuses an observer that is itself RLS-filtered. The auth harness is an
explicit non-product fixture (TSD ADR-009: real auth is a managed OIDC/
passkey provider) built around an HMAC-signed token, signature checked
before any claim is parsed, with a 13-case negative-credential catalog
and byte-identical before/after state assertions plus an audit trail
that never stores the raw credential.

**Independently re-run by this session, all confirmed:** `pytest -v`
in `backend/` — 37/37 passed. `ruff check .` — clean. `mypy .` (strict)
— clean, 20 files. `pytest tools/tests` — 18/18 passed.
`tools/validate_repo_skeleton.py` (7/7), `tools/validate_baseline_binding.py`,
`tools/validate_capability_manifest.py` (both MOD-000 and MOD-001
manifests), `tools/validate_migration_ordering.py` — all PASS.
`knowledge/00-System/verify_baselines.py` — 4/4 governing baselines
still MATCH. `docker ps -a` confirmed no leftover Veyro container after
the run (only unrelated pre-existing containers from other projects on
this machine). Read both new harness modules and the dependency/
STATUS.md/BUG_REGISTRY.md diffs directly — no fabricated claims found.

**The two required negative proofs, both real:** (1) `access_grant`
deliberately broken 5 ways (RLS disabled, permissive policy, NOT
FORCED, nullable `tenant_id`, runtime-owns-table) plus BYPASSRLS/
superuser connections — every one detected by name
(`RLS_NOT_ENABLED`/`RLS_NOT_FORCED`/`TENANT_ID_NULLABLE_OR_MISSING`/
`RUNTIME_ROLE_OWNS_TABLE`/etc.), each exposing the real cross-tenant
leak such a broken fixture would hide; the correct configuration shows
0 of the other tenant's rows visible/updatable/deletable, with
insert/reassign refused by Postgres itself (`new row violates row-level
security policy`). (2) All 13 negative-credential cases rejected, no
session issued, state byte-identical, exactly one `authentication.failed`
audit row per case, raw credential never stored. A 7-mutation kill-check
(each mutation restored + SHA-256-verified after) confirmed the test
suite actually goes red for each — including "the runtime fixture
silently connects as superuser," the exact false-clean failure mode
this role exists to prevent.

**Dependency added:** `psycopg[binary]==3.3.6` (chosen over SQLAlchemy/
Alembic — the harness runs raw SQL as distinct roles, no ORM needed yet;
also SQLAlchemy 2's own future driver, so no throwaway choice), added
to `backend/pyproject.toml`'s real `dependencies` (not `dev` — a DB
driver is a runtime dependency) via the exact `BUG-036` wheel-lock-install
path (2 new lock entries, all 12 prior hashes unchanged, independently
re-diffed by this session). LGPL-3.0 licence flagged for the owner's
awareness (not treated as a material business change by either the
subagent or this session, but neither is a lawyer — owner's call, no
owner approval sought or claimed as obtained).

**`BUG-037` filed, not fixed by the filer:** `knowledge/05-QA/tools/mr_verify.py`
rejects the harness's own genuine Opus transcript
(`claude-opus-5-5`, 127/127 turns) because its family regex only
accepted dot-separated minor versions; also missing the 3 `ADR-005`
agents from its tier map. Correctly not self-fixed (the tool attests the
filer's own tier — fixing it would be self-certification). This means
Slice 5's MR evidence carries raw transcript evidence side-by-side with
the tool's `BLOCKED` verdict, not a tool-attested PASS — disclosed
honestly in both the MR file and here, not smoothed over.

**Durable state updated this chunk:** `backend/tests/harness/` (new),
`backend/tests/integration/{conftest.py,test_tenant_isolation_harness.py,
test_authn_harness.py}` (new), `backend/tests/unit/test_harness_postgres_fail_closed.py`
(new), `backend/pyproject.toml`/`requirements-dev.txt`/
`requirements-dev.lock.txt` (modified), new
`knowledge/03-Modules/MOD-001/evidence/implementation/SLICE-5-gov01-r02-tenant-isolation-auth-harness-2026-09-29.md`,
new `knowledge/03-Modules/MOD-001/evidence/model-routing/CRITICAL_ENGINEER_SLICE5_DISPATCH_2026-09-29.md`,
new `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-037-mr-verify-rejects-current-opus-model-id.md`,
`knowledge/03-Modules/MOD-001/STATUS.md` (Slice 5 entry + corrected R02
progress line), `knowledge/05-QA/BUG_REGISTRY.md` (BUG-037 row + totals
note), this file (chunk 62 compressed/archived per the retention rule
to make room, this chunk added in full).

**Disposition:** MOD-001 remains `IMPLEMENTATION IN PROGRESS`, not
approved. WIP remains 1. MOD-002 not started. No Code Review / Manual
QA / Security / Performance / Gatekeeper phase run this chunk, per the
mission's own explicit instruction. `SCENARIOS.md` not edited — the two
executed-but-unjudged scenarios (SCN-027/067) await independent
`veyro-security-reviewer` judgment before their disposition changes
there; this file and `STATUS.md` record execution, not certification.

**Next legally allowed action — SUPERSEDED, see chunk 65 (which acted on
option (a) below and closed `BUG-037`, still named open in this
paragraph's own last sentence); this paragraph is kept verbatim as this
chunk's historical record, per this file's preserve-history convention
(flagged 2026-09-30, session-restore reconciliation, `BUG-042`):**
commit and push this chunk's changes
(done immediately after this entry was written — see git log for the
commit SHA); then either (a) route an independent fresh-context
`veyro-security-reviewer` to judge SCN-027/067's mechanical PASS
results and to independently re-verify the RLS/authn harness's
anti-false-clean properties (no self-review, per the critical-engineer's
own charter), (b) dispatch the RLS-lint/permission-lint gates
(GOV-01-R04, `ADR-005`'s third critical-engineer slice) as a distinct
future critical slice now that real backend schema exists for gate 1 to
lint against, or (c) continue with further dependency-safe routine
slices (the six domain suite scaffolds/financial-invariant placeholder,
GOV-01-R03/R05/R07/R08). Also open: route `BUG-037` to whoever owns
`mr_verify.py`/DC-17 re-qualification of the current Opus/Sonnet model
ids — every future Opus MR attestation is `BLOCKED` until that lands.
(`BUG-037` is now CLOSED per chunk 65 — this parenthetical is part of
the original chunk-64 text, left unedited for the same reason.)
