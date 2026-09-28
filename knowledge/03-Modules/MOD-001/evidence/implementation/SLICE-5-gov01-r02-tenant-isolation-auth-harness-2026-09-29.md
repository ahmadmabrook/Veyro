---
doc: MOD-001_IMPLEMENTATION_SLICE_5
status: LIVE
module: MOD-001
updated: 2026-09-29
---

# MOD-001 implementation slice 5 — GOV-01-R02 tenant-isolation/RLS harness + authentication negative-credential fixture pattern

## What this slice is

The first critical slice in MOD-001. It covers exactly the two GOV-01-R02
items that `ADR-005` Decision 1 scopes to `veyro-critical-engineer`:

1. The tenant-isolation/RLS test harness, with its fixture schema, roles and
   grants.
2. The authentication negative-credential fixture pattern.

Everything runs against a **real, disposable, local Postgres 16** (Docker),
as a **real non-superuser, non-`BYPASSRLS`, non-owner LOGIN role**. Denials
come from Postgres itself: RLS row filtering, rowcount 0, or SQLSTATE 42501.
They never come from an application-layer exception.

**Explicitly not in this slice** (per the dispatch brief):

- TSD §24.1 RLS-lint and permission-lint gates (GOV-01-R04). No
  `tools/validate_architecture_gates.py` was built.
- The migration-safety harness (GOV-01-R06).
- The six domain suite scaffolds and the financial-invariant placeholder
  (routine, `veyro-implementer` work).
- The DOM-002 concurrency/versioning test pattern. It is also tagged
  GOV-01-R02/CONC in `REQUIREMENTS.md` and `.claude/rules/backend/concurrency.md`,
  but it is not one of ADR-005's named critical slices and is not in this
  dispatch. It is recorded under "Remaining GOV-01-R02 obligations" below so
  it does not get lost.

## Governing requirement

- `REQUIREMENTS.md` GOV-01-R02 (`EIP_MIRROR.md` lines 17545-17549):
  "a tenant-isolation test harness (RLS negative-role fixture); an
  authentication test harness (invalid/expired credential fixtures)."
- Acceptance criterion in scope: "the tenant-isolation harness denies a
  real cross-tenant access attempt under a non-privileged runtime role."
- TSD §24.1 (`TSD_MIRROR.md` lines 11599-11601): "runtime role cannot
  own/bypass. Negative isolation tests run with production-equivalent role."
- `.claude/rules/backend/database.md` (RULE-007) controls 1-5.
- TSD ADR-009 (managed OIDC/passkey provider; Veyro does not implement
  credential cryptography). This is why the authn fixture is explicitly
  *not* product auth.

## Routing and execution mode (EIP §4.1: "Router records whether Opus directly implemented or supervised")

**Implemented directly by `veyro-critical-engineer` (Opus).** No
`veyro-implementer` supervision leg was used. All design and all code in this
slice was written by the critical-engineer dispatch itself, because nearly
every line is load-bearing for the anti-false-clean property: role
attributes, observer/runtime separation, posture re-read, ground-truth
comparison, and the breakage matrix. There was no meaningful routine
remainder to hand off. MR record:
`knowledge/03-Modules/MOD-001/evidence/model-routing/CRITICAL_ENGINEER_SLICE5_DISPATCH_2026-09-29.md`
(`MR-MOD001-20260929-001`).

SCN-MOD001-028 and SCN-MOD001-097 are catalog-routed to
`veyro-implementer`/Sonnet. They were executed here because they are the
positive controls of the same harness, and a harness without its positive
control can't prove its zeros mean anything. No other routine work was
absorbed.

## What was built

| File | Purpose |
|---|---|
| `backend/tests/harness/__init__.py` | Test-only harness package, importable by later modules. |
| `backend/tests/harness/postgres.py` | `disposable_postgres()`. One container per pytest session: random name, per-run random superuser password passed via child env (never argv), `127.0.0.1`-only port, image pinned by digest, force-removed on exit. Fails closed without Docker; never mocks. |
| `backend/tests/harness/tenant_isolation.py` | Roles (`veyro_schema_owner` NOLOGIN owner; `veyro_runtime` LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT), with the password sent as a client-computed SCRAM verifier. Fixture DDL (`tenant_id uuid NOT NULL`, ENABLE+FORCE RLS, `tenant_isolation` policy on a transaction-local `app.tenant_id` GUC that fails closed on absence). `read_posture()` re-reads role and table posture *from the connection under test*. `probe_cross_tenant()` runs read/update/insert/reassign/delete attacks, each committed, and compares them against superuser-observer ground truth (row count + md5 fingerprint). `probe_same_tenant()` is the positive control. `visible_without_tenant_context()`. The canonical `access_grant` fixture lives here too. |
| `backend/tests/harness/authn.py` | Fixture credential (`base64url(claims).base64url(HMAC-SHA256)`, per-run random key). `FixtureAuthenticator` (the "fixture endpoint") checks the signature *before* parsing claims and uses constant-time compare. It writes session + audit rows as the runtime role. The runtime role is append-only: INSERT on session/audit, SELECT on identity only. Also here: the 13-case `negative_credentials()` catalog, `assert_rejected_without_side_effects()` / `assert_authenticated()`, and an `Authenticator` Protocol as the plug-in point for MOD-007/008. |
| `backend/tests/integration/conftest.py` | Session fixtures: `pg`, `admin` (superuser: setup + ground truth), `runtime` (the runtime role), `tenants` (fresh A/B pair, 2+3 seeded rows, per test), and `elevated_login` (a deliberately wrong BYPASSRLS role, used only to prove rejection). |
| `backend/tests/integration/test_tenant_isolation_harness.py` | 12 tests (SCN-067 positive + 5 breakage companions, SCN-028, fail-closed context, 3 harness self-checks). |
| `backend/tests/integration/test_authn_harness.py` | 19 tests (SCN-097, SCN-027 × 13 cases, broken-authenticator self-check, 4 append-only-privilege checks). |
| `backend/tests/unit/test_harness_postgres_fail_closed.py` | 2 tests. No Docker means an error, not a skip. The password is never in docker argv (checked by a fake `docker` on PATH). |
| `backend/pyproject.toml`, `backend/requirements-dev.txt`, `backend/requirements-dev.lock.txt` | `psycopg[binary]==3.3.6` added (runtime `dependencies`) and lock regenerated (see "Dependency"). |

### Credential separation (`database.md` rule 3), stated explicitly

- **Superuser was required, and used only for one-time setup and ground
  truth.** The container's default `postgres` superuser (random per-run
  password) creates both roles, creates the schemas (`AUTHORIZATION
  veyro_schema_owner`), issues fixture DDL via `SET ROLE veyro_schema_owner`
  (so the tables really are owned by the distinct NOLOGIN owner role), seeds
  rows, and acts as the ground-truth *observer*. `CREATE ROLE`, and
  especially creating a `BYPASSRLS` role for the self-check, need superuser.
- **The runtime connection under test is never that credential.**
  `veyro_runtime` is a separate LOGIN role with its own per-run password.
  Its live posture, read from its own connection on every probe, is:
  `superuser=false, bypassrls=false, role_memberships=0,
  table_owner=veyro_schema_owner, rls_enabled=true, rls_forced=true,
  policies=1, tenant_id_not_null=true`. Any deviation fails the probe
  (proven below).
- The harness also **refuses an RLS-filtered observer**, because
  ground truth read through RLS would be vacuous. That case is tested too.

## Docker/Postgres capability (discovered and used this session)

- `docker version`: client **29.6.0**, engine **29.7.2**. The dispatch brief
  said "29.6.0", which is the client; the engine is 29.7.2. Recorded as
  observed.
- Image: `postgres:16-alpine`, already pulled locally. It is pinned in code by
  content digest
  `postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`
  (image created 2026-09-17T21:33:33Z), so a moved tag cannot change what
  runs.
- Local-only, zero spend, synthetic rows only. The container is named
  `veyro-mod001-harness-<random>`, uses `--rm`, and is force-removed in a
  `finally`. `docker ps -a --filter name=veyro-mod001-harness` returned **0**
  after every run this session, including all mutation runs. The owner's
  pre-existing, unrelated containers (`fixly_*` etc.) were never touched.
- **To recreate:** `cd backend && .venv/bin/pytest tests/integration`. Nothing
  else is needed; the fixture starts and tears down its own container.

## Dependency: `psycopg[binary]==3.3.6` (runtime), and why only this

- **Why a driver at all:** the harness must run raw SQL *as different
  database roles* to prove RLS. There is no stdlib Postgres client.
- **Why psycopg 3, and not SQLAlchemy/Alembic:** no ORM or migration machinery
  is needed to prove a policy decision. SQLAlchemy 2 uses psycopg 3 as its
  `postgresql+psycopg` driver, so the TSD reference stack (Python/FastAPI/
  SQLAlchemy 2/Alembic) can adopt it later without changing driver.
  psycopg also exposes libpq's `PQencryptPasswordConn`, used here to keep
  cleartext role passwords off the server.
- **Why `[binary]`:** it avoids a local libpq/compiler build (wheel-only
  policy, BUG-036 Round 5). The closure is exactly 2 new wheels, `psycopg`
  (pure Python, no runtime deps on 3.14) and `psycopg-binary` (bundles libpq
  **18.0.6**).
- **Acquisition:** the exact BUG-036 Round 5/6 path.
  `pip download --only-binary=:all: -r backend/requirements-dev.txt` resolved
  14 wheels. `tools/generate_requirements_lock.py generate` → `PASS — wrote 14
  package(s)`. `... check` → `PASS — 14 package(s): every wheel appears exactly
  once in the lock, every version and SHA-256 is exact, no extra entries.`
  `git diff` of the lock shows **only 2 added entries** (plus the wheel-dir
  comment line). All 12 pre-existing hashes are byte-identical. Then
  `pip install --require-hashes --no-index --find-links <wheels> -r
  backend/requirements-dev.lock.txt` → `Successfully installed psycopg-3.3.6
  psycopg-binary-3.3.6`. Import check: `psycopg 3.3.6 impl binary libpq 180006`.
  - `psycopg==3.3.6` → `sha256:a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631`
  - `psycopg-binary==3.3.6` → `sha256:5927b7ba63153cd8e9862987290a2b783a5c590daf2a4ef981700cc3569166d4`
- **Provenance/licence/CVE:** official PyPI projects (author Daniele
  Varrazzo, https://psycopg.org/). `License-Expression: LGPL-3.0-only` for
  both. OSV.dev query for both at 3.3.6 returned `{}` (no known
  vulnerabilities, 2026-09-29).
  - **Licence flag for owner awareness:** LGPL-3.0 is a copyleft licence.
    Here it is used as an unmodified, dynamically imported library in a
    server-side/test context. In my reading that is not a material business
    change, and it is the de-facto standard Postgres driver. But I am not a
    lawyer, and licence acceptance for a commercial product is ultimately the
    owner's call. Recorded here rather than silently assumed.
- **Platform scope:** `psycopg-binary` is a platform wheel
  (`cp314-macosx_11_0_arm64`), so the lock stays macOS/arm64/CPython-3.14-
  specific. That is the same disclosed limitation BUG-036 Round 5 already
  carries; a Linux CI lock is a separate future step.

## Real execution (this session — every result below was actually run)

### Full backend suite

```
$ cd backend && .venv/bin/pytest -v
... (37 items: 4 scaffold + 2 unit fail-closed + 31 integration harness)
============================== 37 passed in 2.18s ==============================
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/mypy .
Success: no issues found in 20 source files
```

The first integration run passed 32/32. It was **not trusted on that basis**,
which is why the mutation check below exists. `ruff`/`mypy` initially found 4
real issues in the new code, all fixed:

- a too-broad `Composable` type on `_attempt_write`;
- implicit string concatenation in a tuple;
- a missing explicit `check=False`;
- nested `with` statements.

While reading them I also found and fixed 3 **credential-exposure defects**
in my own first draft:

- The container superuser password was in `docker run` argv. Argv is echoed
  by `CalledProcessError`/`TimeoutExpired` messages, so it would have landed
  in pytest output on any Docker failure (`performance.md` control 5). It now
  goes via child env, and error messages carry no argv.
- `CREATE ROLE ... PASSWORD '<cleartext>'` would have logged the cleartext
  server-side if the statement ever errored. It now sends a client-computed
  SCRAM verifier.
- The `DisposablePostgres` repr would have printed the password in
  tracebacks. The field is now `repr=False`.

### SCN-MOD001-067 (positive): cross-tenant access to `access_grant` denied under the runtime role

Structured evidence from the real run (UUIDs are per-run random):

```
RUNTIME-POSTURE-EVIDENCE {"bypassrls": false, "policies": 1, "rls_enabled": true, "rls_forced": true, "role": "veyro_runtime", "role_memberships": 0, "session_role": "veyro_runtime", "superuser": false, "table": "harness.access_grant", "table_owner": "veyro_schema_owner", "tenant_id_not_null": true}

SCN-MOD001-067-EVIDENCE {"deleted_other_rows": 0, "insert_as_other": "DENIED_BY_RLS: new row violates row-level security policy for table \"access_grant\"", "other_fingerprint_after": "2e7d0c6ca53f0d5ed66ad6eca2f7ae0c", "other_fingerprint_before": "2e7d0c6ca53f0d5ed66ad6eca2f7ae0c", "other_rows_after": 3, "other_rows_before": 3, "other_tenant": "9b7a7611-9d17-4a63-8fbc-0e0f6a7db3f7", "own_rows_before": 2, "own_tenant": "df40819b-4c2a-41da-807d-6bed8094e017", "posture_violations": [], "reassign_own_to_other": "DENIED_BY_RLS: new row violates row-level security policy for table \"access_grant\"", "role": "veyro_runtime", "table": "harness.access_grant", "updated_other_rows": 0, "visible_other_rows": 0}
```

Reading it plainly:

- Ground truth, read by the superuser observer: tenant B has 3 rows. So the
  runtime role's `visible_other_rows: 0` is a real filter, not an empty table.
- Update and delete of B's rows: rowcount 0.
- Insert as B, and reassigning A's own rows to B: both rejected by Postgres
  with the RLS policy error naming `access_grant`.
- B's rows are byte-identical afterwards (same md5 fingerprint).

**RLS-denial log citing `access_grant` by name, from Postgres's own server
log** (not harness output). The test asserts the count increased by at least
2 across the probe:

```
SCN-MOD001-067-SERVER-LOG-EVIDENCE ["2026-09-28 21:47:20.802 UTC [61] ERROR:  new row violates row-level security policy for table \"access_grant\"", "2026-09-28 21:47:20.804 UTC [61] ERROR:  new row violates row-level security policy for table \"access_grant\""]
```

(Timestamps are the container's UTC clock. The host's `date -u` at the final
run was `Mon Sep 28 21:51:20 UTC 2026`, i.e. 2026-09-29 local.)

Also proven (`test_missing_tenant_context_sees_no_rows`): with 5 rows in the
table (observer count), the runtime role with **no** tenant context sees
**0**. It fails closed, never open.

### SCN-MOD001-067 (negative / required companion): a deliberately broken `access_grant` is caught — the harness distinguishes correct from broken

Each breakage is applied to the **same** `access_grant` table, probed as the
runtime role, then restored. Restoration is verified by re-reading posture:
`violations == []`. The test **fails if the harness passes the broken
fixture**.

| Breakage | Posture violation raised | Behavioural leak observed | Harness verdict |
|---|---|---|---|
| `rls_disabled` (`DISABLE ROW LEVEL SECURITY`, the scenario's literal case) | `RLS_NOT_ENABLED` | read 3, update 3, insert allowed, reassign allowed (2), delete 6, B's rows changed | **FAIL (correct)** |
| `permissive_policy` (`USING (true) WITH CHECK (true)`) | *none* (posture looks perfect) | read 3, update 3, insert/reassign allowed, delete 6 | **FAIL (correct)** — only the behavioural probe catches this |
| `rls_not_forced` (`NO FORCE`) | `RLS_NOT_FORCED` | none (runtime isn't owner) | **FAIL (correct)** |
| `tenant_id_nullable` | `TENANT_ID_NULLABLE_OR_MISSING` | none | **FAIL (correct)** |
| `runtime_owns_table` | `RUNTIME_ROLE_OWNS_TABLE` | none (FORCE still on) | **FAIL (correct)** |

Full evidence line for the scenario's literal case:

```
SCN-MOD001-067-NEGATIVE[rls_disabled]-EVIDENCE {"deleted_other_rows": 6, "failures": ["POSTURE:RLS_NOT_ENABLED", "CROSS_TENANT_READ:3", "CROSS_TENANT_UPDATE:3", "CROSS_TENANT_INSERT:ALLOWED rowcount=1", "CROSS_TENANT_REASSIGN:ALLOWED rowcount=2", "CROSS_TENANT_DELETE:6", "OTHER_TENANT_ROWS_CHANGED"], "insert_as_other": "ALLOWED rowcount=1", "other_rows_after": 0, "other_rows_before": 3, "posture_violations": ["RLS_NOT_ENABLED"], "reassign_own_to_other": "ALLOWED rowcount=2", "role": "veyro_runtime", "table": "harness.access_grant", "updated_other_rows": 3, "visible_other_rows": 3, ...}
```

**Harness self-checks: the charter's exact failure mode.** A harness that
silently connects as a privileged role must report itself broken:

```
HARNESS-SELF-CHECK[bypassrls]-EVIDENCE {"failures": ["POSTURE:RUNTIME_ROLE_BYPASSRLS", "CROSS_TENANT_READ:3", ...], "role": "veyro_bypass_probe_f45fd2", "visible_other_rows": 3, ...}
HARNESS-SELF-CHECK[superuser]-EVIDENCE {"failures": ["POSTURE:RUNTIME_ROLE_SUPERUSER", "POSTURE:RUNTIME_ROLE_BYPASSRLS", "CROSS_TENANT_READ:3", ...], "role": "postgres", "visible_other_rows": 3, ...}
```

Both show the real leak (3 of B's rows visible) that such a harness would
otherwise have hidden, and both are rejected.

### SCN-MOD001-028 (positive companion): same-tenant request permitted

```
SCN-MOD001-028-EVIDENCE {"insert_own": "ALLOWED rowcount=1", "posture_violations": [], "role": "veyro_runtime", "rows_ground_truth": 3, "table": "harness.access_grant", "updated_rows": 3, "visible_rows": 3, ...}
```

This proves the negative probe's zeros come from the policy, not from missing
grants or a table that hides everything.

### SCN-MOD001-097 (positive): valid credential issues a session and is audited

```
SCN-MOD001-097-EVIDENCE {"audit": [["authentication.succeeded", "synthetic-member-0001", "OK"]], "session": ["synthetic-member-0001", "2030-03-17 17:46:40+00", "2030-03-17 18:01:40+00"], "session_id": "e233fd34-4ea8-4288-86d6-f0c11ba09a08"}
```

The session row was read back by the observer, the session count went up by
exactly one, and there is exactly one `authentication.succeeded` audit row.
The clock is fixed at epoch 1 900 000 000, which is why the dates are 2030.

### SCN-MOD001-027 (negative): invalid/expired credentials rejected, no session, state unaffected

13 cases were run, all PASS:

- `expired`
- `expires_exactly_now` (boundary)
- `not_yet_valid`
- `wrong_signing_key`
- `tampered_claims` (payload swapped, original signature kept)
- `signature_stripped`
- `extra_segment`
- `garbage`
- `empty`
- `non_ascii`
- `wrong_audience`
- `unknown_subject`
- `disabled_subject`

Every case gives the same result: `session_id is None`, the expected reason
code, and session + identity state md5 byte-identical before/after (observer
read). Each also writes exactly one `authentication.failed` audit row with the
reason, and the raw credential never appears in the audit. The subject is
recorded as `null` whenever the signature didn't verify, so an attacker can't
plant a subject in the audit log. Sample:

```
SCN-MOD001-027[expired]-EVIDENCE {"audit": [["authentication.failed", "synthetic-member-0001", "EXPIRED"]], "case": "expired", "reason": "EXPIRED", "state_unchanged": true}
SCN-MOD001-027[tampered_claims]-EVIDENCE {"audit": [["authentication.failed", null, "BAD_SIGNATURE"]], "case": "tampered_claims", "reason": "BAD_SIGNATURE", "state_unchanged": true}
SCN-MOD001-027[wrong_signing_key]-EVIDENCE {"audit": [["authentication.failed", null, "BAD_SIGNATURE"]], "case": "wrong_signing_key", "reason": "BAD_SIGNATURE", "state_unchanged": true}
SCN-MOD001-027[garbage]-EVIDENCE {"audit": [["authentication.failed", null, "MALFORMED"]], "case": "garbage", "reason": "MALFORMED", "state_unchanged": true}
SCN-MOD001-027[disabled_subject]-EVIDENCE {"audit": [["authentication.failed", "synthetic-member-0002", "DISABLED_SUBJECT"]], "case": "disabled_subject", "reason": "DISABLED_SUBJECT", "state_unchanged": true}
```

**Authn harness self-check.** An authenticator deliberately broken to accept
expired credentials is caught by the same assertion:

```
AUTHN-HARNESS-SELF-CHECK[accepts_expired]-EVIDENCE "negative credential 'expired' not cleanly rejected: ['SESSION_ISSUED', 'REASON:OK!=EXPIRED', 'SESSION_OR_IDENTITY_STATE_CHANGED', \"AUDIT:[('authentication.succeeded', 'synthetic-member-0001', 'OK')]\"]"
```

The runtime role also can't read back or rewrite auth state: `SELECT` on
audit/session and `UPDATE`/`DELETE` on audit all raise Postgres
`InsufficientPrivilege: permission denied` (4 tests).

### Mutation check: the tests go red when the harness is actually broken

Scratch script `mutate_harness.py`, not committed. Each mutation injects one
real defect into the harness or fixture code, runs the full backend suite,
and restores the file. Restoration was SHA-256-verified: all files OK and 0
containers left after each run. Final-code run:

```
M1 runtime fixture silently connects as superuser: KILLED (exit=1) :: 14 failed, 23 passed
M2 fixture table created without ENABLE/FORCE RLS: KILLED (exit=1) :: 6 failed, 31 passed
M3 no ground truth for other tenant (vacuous 0-rows): KILLED (exit=1) :: 8 failed, 29 passed
M4 authenticator skips expiry check:                 KILLED (exit=1) :: 2 failed, 35 passed
M5 authenticator skips signature check:              KILLED (exit=1) :: 3 failed, 34 passed
M6 authenticator issues session before rejecting:    KILLED (exit=1) :: 13 failed, 24 passed
M7 superuser password put back into docker argv:     KILLED (exit=1) :: 1 failed, 36 passed
```

7/7 killed. M1 is the charter's named failure mode, a harness that silently
connects as a privileged role. It turns SCN-067, SCN-028, the posture test,
every breakage companion, and the append-only-privilege tests red. M3 proves
"0 rows" can't pass without seeded ground truth.

### Regression (existing validators and suites, real exit codes)

```
$ backend/.venv/bin/python3 -m pytest tools/tests/ -q            -> 18 passed, exit=0
$ tools/validate_baseline_binding.py                              -> PASS, exit=0
$ tools/validate_capability_manifest.py --manifest MOD-000/...    -> PASS (7 IDs), exit=0
$ tools/validate_capability_manifest.py --manifest MOD-001/...    -> PASS (9 IDs), exit=0
$ tools/validate_migration_ordering.py                            -> PASS, exit=0
$ tools/validate_repo_skeleton.py                                 -> PASS (7/7), exit=0
$ python3 knowledge/00-System/verify_baselines.py                 -> PASS, 4/4 [MATCH], exit=0
```

## Scenario traceability and disposition

None of these are self-certified. The critical engineer holds no reviewer or
Gatekeeper authority, and `SCENARIOS.md` status lines were not edited; that is
for the orchestrating session after independent review.

| Scenario | Tier/owner (catalog) | This slice |
|---|---|---|
| SCN-MOD001-067 (LIFE, Blocker) | veyro-security-reviewer/Opus (judgment) | **Executed.** Mechanical result PASS for the denial and for the harness-level negative companion. **Awaiting independent `veyro-security-reviewer` judgment.** The negative clause's other half, "the gate itself (not just this scenario) must catch it" (the R04 RLS-lint gate), is **NOT EXECUTED**: that gate is out of scope for this dispatch. |
| SCN-MOD001-027 (AUTHN, Blocker) | veyro-security-reviewer/Opus | **Executed**, 13/13 cases mechanical PASS. **Awaiting independent judgment.** The "fixture endpoint" is a Python callable, not HTTP (see gaps). |
| SCN-MOD001-097 (AUTHN, Major) | veyro-implementer/Sonnet | **Executed**, PASS (evidence above). |
| SCN-MOD001-028 (AUTHZ, Major) | veyro-implementer/Sonnet | **Executed**, PASS (evidence above). |

## Disclosed scope gaps and known ceilings

1. **Tenant-context trust boundary.** `app.tenant_id` is a transaction-local
   GUC the app sets after server-side resolution (TEN-002). Postgres can't
   tell who set it, so SQL injection in app code could switch tenants. The
   harness proves the *database* half; the resolver/injection half is
   MOD-004's design. Recorded in the module docstring.
2. **"Production-equivalent" is defined here, not inherited.** No production
   (or QA/staging) runtime role exists yet. This harness pins the attribute
   set (`NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION
   NOINHERIT`, no memberships, owns nothing). Future `infra/**` role
   provisioning must match it, and `read_posture()` can be pointed at the
   real role to check.
3. **The authn fixture is not product auth.** It uses an HMAC fixture token,
   not OIDC (TSD ADR-009). MOD-007/008 must re-mint the same 13 case names in
   their provider's real token format and swap in their own state/audit
   queries. The assertion pattern and catalog are what carry forward.
4. **No HTTP transport.** FastAPI is not a dependency yet (no `app/main.py`
   exists), so the "fixture endpoint" is the `Authenticator.authenticate()`
   callable. HTTP binding belongs to whichever slice first adds FastAPI.
5. **Not wired into CI.** GOV-01-R04 CI wiring is still blocked on
   GitHub-Actions-per-Action capability qualification, the same gap Slices 3
   and 4 disclose. GitHub-hosted Linux runners have Docker, so the fixture
   design is CI-compatible, but that is unproven until wired. It will also
   need a Linux lock (platform-specific `psycopg-binary`).
6. **`access_grant` has no `version` column (DOM-002).** It is a test-only
   fixture, and the probes' unversioned writes are adversarial attack
   simulations, not application mutation paths. The DOM-002
   concurrency/versioning pattern is a separate GOV-01-R02 obligation (below).
7. **Postgres major version.** Pinned to 16 because that is the image the
   brief named and had pre-pulled. Not a production-version decision.
8. **LGPL-3.0 licence** of the new dependency, flagged for owner awareness
   (see "Dependency").
9. **MR attestation tool defect found: `BUG-037`** (see MR record). It does
   not affect this slice's code or test results.

## Remaining GOV-01-R02 obligations (not in this dispatch, still open)

- Migration-safety harness ("detects a deliberately broken rollback").
- Six empty-but-wired domain suite scaffolds (membership/booking/payment/
  ledger/POS/access).
- Financial-invariant placeholder harness.
- DOM-002 concurrency/versioning test pattern (CONC).
- The R04 RLS-lint/permission-lint gates, which are GOV-01-R04 but complete
  SCN-067's gate half.

## Not done this session

No Code Review, Manual QA, Security Review, Performance Review, or Gatekeeper
was run. No git add/commit/push. `CURRENT_STATE.md` / `CURRENT_HANDOFF.md`
not edited. MOD-001 remains **IMPLEMENTATION IN PROGRESS**, not Approved.
