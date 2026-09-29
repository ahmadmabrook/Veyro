---
doc: MOD-001_SLICE5_INDEPENDENT_SECURITY_REVIEW
status: LIVE
module: MOD-001
updated: 2026-09-29
---

# MOD-001 Slice 5 (GOV-01-R02) — independent security review

**Reviewer:** fresh-context `veyro-security-reviewer` (Opus, model id
`claude-opus-5-5` per this session's own subagent transcript — DC-17
attestation via `mr_verify.py` itself blocked by `BUG-037`; recorded
manually here from the transcript, per the reviewer's own disclosure).
No participation in authoring Slice 5 (`veyro-critical-engineer`
authored it, in a separate dispatch — see
`knowledge/03-Modules/MOD-001/evidence/implementation/SLICE-5-gov01-r02-tenant-isolation-auth-harness-2026-09-29.md`).
Not accepted on the implementer's report alone — see "What was
independently reproduced" below.

## Overall verdict: BLOCKED (P0=0, P1=1, P2=5, Editorial=3)

The harness itself is technically sound: the runtime role is genuinely
non-privileged, FORCE/owner RLS semantics are stated and implemented
correctly, denials come from Postgres (not an application-layer
exception), ground truth comes from an independent superuser observer,
and every safety-critical hand-mutation the reviewer applied turned the
suite red. The one P1 is a **supply-chain governance gap**, not a
harness code defect: the Postgres engine that produces this slice's
Blocker-severity evidence is an unregistered, unqualified third-party
executable capability under this project's own `CAPABILITY_POLICY.md`.
Filed as `BUG-038` (see that file). No harness code change is required
to close the P1 — registration + qualification + independent Opus
approval of the capability itself is.

## Scenario judgments

### SCN-MOD001-027 (AUTHN, Blocker) — invalid/expired credential rejection

**Technically PASS, recorded BLOCKED pending BUG-038.** All 13 negative-
credential cases reject correctly (`session_id=None`, correct reason
code); state (session count, session md5, identity md5) is
byte-identical before/after, read by a structurally independent
superuser observer connection; the 13 cases are genuinely distinct
attack classes, not padded; hand mutations disabling the expiry check,
the signature check, or persisting the credential all turn the suite
red. The "fixture endpoint is a Python callable, not HTTP" gap is
disclosed and acceptable (no FastAPI app exists yet; TSD ADR-009 covers
real auth being a managed provider). The reviewer's own explicit
position: recordable PASS once BUG-038 closes, without needing to
re-run anything — the technical evidence already stands.

### SCN-MOD001-067 (LIFE, Blocker) — cross-tenant denial on `access_grant`

**BLOCKED overall — two independent reasons, one pre-existing and
disclosed, one new from this review.**

1. **Harness half: PASS, reproduced independently.** 0 of tenant B's 3
   rows (observer-confirmed ground truth) visible to the runtime role;
   cross-tenant UPDATE/DELETE affect 0 rows; INSERT-as-B and
   reassign-to-B both rejected by Postgres with the RLS error naming
   `access_grant`, visible in Postgres's own server log; B's data is
   byte-identical afterward; a missing tenant context sees 0 rows; all
   5 deliberately-broken fixture variants are caught, as are the
   BYPASSRLS/superuser self-checks. The reviewer independently verified
   FORCE-RLS semantics against real Postgres behavior (owner vs.
   non-owner, FORCE vs. NO FORCE, direct role vs. INHERIT membership —
   5-row truth table, matches the harness's own claims exactly).
2. **Gate half: BLOCKED, precondition genuinely absent — already
   correctly disclosed as NOT EXECUTED by the implementer, not a new
   finding.** The scenario's negative clause requires "the gate itself
   (not just this scenario)" to catch disabled RLS — that is TSD §24.1's
   RLS-lint gate, GOV-01-R04, out of scope for this dispatch per
   `ADR-005`. It does not exist yet (`tools/validate_architecture_gates.py`
   was never built). Must not be recorded PASS until that gate exists
   and is proven to catch this exact fixture's breakage.
3. **Inherits the same BUG-038 concern** as SCN-027, since its
   Blocker-severity evidence rests on the same unregistered Postgres
   capability.

## Findings

### P1-1 — filed as `BUG-038`: Docker Engine + `postgres:16-alpine` relied on as a Blocker-evidence trust anchor with no `CAPABILITY_REGISTRY.md` entry, no qualification, no independent approval

See `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-038-docker-postgres-capability-unregistered.md` for full detail.

### P2-1 — `psycopg[binary]` is in runtime `[project.dependencies]`, but its only current consumer is the test harness

`backend/pyproject.toml:8-10`. Rationale given was a speculative future
SQLAlchemy adoption. Consequence: an LGPL-3.0 package with bundled
native code (`libpq`) is part of the product's *runtime* dependency
set, not just its test/dev tooling, for no functional reason yet.
Supply-chain mechanics otherwise check out (wheel SHA-256 matches both
the lock and PyPI's published digest for both wheels; lock-checker
passes; OSV returns `{}` for both). **Fix suggested (not applied by
this review — implementation is out of scope for a reviewer):** move to
`[project.optional-dependencies].dev` (or a new `test` extra) until a
real runtime consumer exists.

### P2-2 — the `runtime_owns_table` breakage-and-restore test silently strips `veyro_runtime`'s grants on restore, and the restoration check can't see it

`backend/tests/integration/test_tenant_isolation_harness.py:118-124`
(mutation), `:153` (restoration check). `ALTER TABLE ... OWNER TO
veyro_runtime` and back rewrites the ACL — it does not return to its
original grant set (`veyro_runtime=arwd/veyro_schema_owner` is lost).
The restoration assertion only re-reads *posture* (role/RLS
flags), which does not include privileges, so it passes against a
fixture that no longer has its original grants. The suite is green
today only because this is the last test to touch `access_grant` in
run order; the reviewer independently confirmed that running it first
causes `SCN-067`, `SCN-028`, and the `rls_disabled` breakage test to
fail with `InsufficientPrivilege`. This fails closed (goes red, never
falsely green) — hence P2, not P1. The evidence file's claim
("Restoration is verified by re-reading posture") overclaims what the
check actually covers.

### P2-3 — 3 of 9 posture violation codes have no in-suite negative test

`backend/tests/harness/tenant_isolation.py:172-183`. `ROLE_SWITCHED`,
`RUNTIME_ROLE_HAS_MEMBERSHIPS`, and `NO_RLS_POLICY` all fire correctly
under direct reviewer probing, but none has a `BREAKAGES` entry
exercising it in the committed suite. `RUNTIME_ROLE_HAS_MEMBERSHIPS` is
load-bearing: membership in the owner role combined with NO FORCE is a
real 3-row cross-tenant leak, and the suite's only FORCE-breakage case
runs against a non-owner role, so it cannot currently catch this
specific leak class.

### P2-4 — the audit-integrity properties described in prose are not actually asserted in code

`backend/tests/harness/authn.py:261-264`. The evidence file states the
audited subject is `null` whenever signature verification fails ("an
attacker can't plant a subject") and that the raw credential is never
persisted. Both are true of the current code, but neither is asserted.
Reviewer-authored mutations proved this: auditing an unverified claimed
`sub` on `BAD_SIGNATURE`, and persisting a truncated (not full) raw
credential, both left the suite green (37/37). These are exactly the
"carry-forward contract" properties MOD-007/008 will depend on when
they re-mint this catalog against a real OIDC provider.

### P2-5 — the 13-case negative-credential catalog has no "well-signed token with a missing/malformed `exp`" case

`backend/tests/harness/authn.py:187-211`. The current implementation
correctly rejects missing/malformed `exp` (verified directly by the
reviewer: missing `exp`, missing `iat`, string `exp`, float `exp`, a
non-JSON body, and a non-dict claims object are all correctly rejected;
a boolean `exp` is rejected as `EXPIRED`) — but no catalog case
*exercises* this path, so a future regression here would go undetected
until MOD-007/008 re-mint the catalog.

### Editorial

- **E-1:** the harness's posture violation codes (`RLS_NOT_FORCED`,
  `TENANT_ID_NULLABLE_OR_MISSING`, `RUNTIME_ROLE_OWNS_TABLE`/
  `BYPASSRLS`) use different names than the gate codes RULE-007/SCN-005
  reference (`RLS_NOT_ENFORCED`, `RLS_TENANT_ID_NULLABLE`,
  `RLS_RUNTIME_ROLE_ELEVATED`). If the future R04 gate reuses
  `read_posture()`, map these explicitly rather than assuming the names
  line up.
- **E-2:** commit `5f88936`'s message lists the 5 breakage variants
  including "BYPASSRLS" and omits `permissive_policy`; BYPASSRLS is
  actually a separate self-check, not one of the 5 fixture breakages.
- **E-3:** Postgres does not log RLS read-filtering (only policy
  violations on write). SCN-067's "RLS-denial log citing `access_grant`"
  requirement is satisfied by the INSERT/reassign `WITH CHECK` denials
  in the server log, not by the read path — correct and the only
  possible form, but the evidence file should say this explicitly
  rather than leaving it implicit.

## What was independently reproduced (not taken on the implementer's report alone)

- Full suite: `pytest -v -rP` → 37 passed (raw evidence lines structurally
  match the implementer's, differing only in per-run random UUIDs/md5s,
  as expected). `ruff check .` clean. `mypy .` clean, 20 files. 0
  leftover `veyro-mod001-harness-*` containers after every run.
- Posture of `veyro_runtime` read directly via the reviewer's own SQL
  against the running container: not superuser, no BYPASSRLS,
  NOINHERIT, zero memberships, owns 0 relations/schemas, holds only
  `SELECT,INSERT,UPDATE,DELETE` on `harness.access_grant`, cannot
  `CREATE` in `public`. `access_grant`: owned by `veyro_schema_owner`,
  RLS enabled+forced, `tenant_id NOT NULL`, one `FOR ALL` policy keyed
  on `app.tenant_id` (USING and WITH CHECK both).
- 9 independent self-escalation probes as the runtime role, all denied
  by Postgres: `SET row_security=off`, `SET ROLE` to the owner, `SET
  SESSION AUTHORIZATION`, `DISABLE RLS`, `NO FORCE`, `DROP POLICY`,
  granting itself owner-role membership, `ALTER ROLE ... BYPASSRLS`,
  and `CREATE` in `public`. An INSERT with no tenant context set was
  denied. An extra permissive SELECT policy layered on top was still
  caught behaviourally.
- FORCE-RLS semantics truth table (5 combinations of owner/non-owner ×
  FORCE/NO FORCE × direct-role/INHERIT-membership), independently
  measured against real Postgres, matches the harness's own stated
  claims exactly.
- 6 hand-applied mutations, each restored and SHA-256-verified byte-
  identical afterward, `git diff`/`git status` empty at the end:
  - R1 (`veyro_runtime` made SUPERUSER): **KILLED**, 14 failed/23 passed
    — matches implementer's M1 count.
  - R2 (`_is_expired` always False): **KILLED**, 2 failed — matches M4.
  - R3 (signature check skipped): **KILLED**, 3 failed — matches M5.
  - R4 (raw credential stored as audit subject, reviewer-authored):
    **KILLED**, 12 failed.
  - R5 (truncated credential persisted, reviewer-authored): **SURVIVED**
    — P2-4.
  - R6 (unverified claimed `sub` audited on `BAD_SIGNATURE`,
    reviewer-authored): **SURVIVED** — P2-4.
- Supply chain: local wheel SHA-256 for both `psycopg`/`psycopg-binary`
  wheels matches the lock file and PyPI's own published digest; `OSV.dev`
  returns `{}` for both at 3.3.6; the running container's image
  `RepoDigests` trace to the official `docker.io/library/postgres`
  repository.
- Synthetic-data-only: every identifier is `synthetic-*`; tenant IDs are
  random `uuid4`; no credential-shaped literal is committed; passwords
  and keys are generated per run. The only scan hits were pytest
  decorators and a negative-case assertion string, not real secrets.
- Final state: all 13 slice files byte-identical to the reviewer's own
  pre-review SHA-256 snapshot; `git diff`/`git diff --cached` empty; no
  new untracked files. Probe scripts lived only in the reviewer's
  session scratchpad, never committed.

**Taken on record, not independently re-run:** mutations M2/M3/M6/M7
from the implementer's own kill-check (M2's detection class is
corroborated by the `rls_disabled` breakage companion the reviewer did
re-run; M7 by the passing argv-exposure unit test); the existing
`tools/tests`/`validate_*`/`verify_baselines.py` regression suites.

**Could not verify:** the implementer's exact `mutate_harness.py` script
(not committed, scratch-only, as intended); Linux/CI behavior (CI not
wired yet; the lock is macOS-arm64/CPython-3.14-specific); Docker
Desktop's current subscription terms or whether they apply to this
project's use (flagged inside `BUG-038`, not resolved here — it is a
licensing/spend question, not a security one, and stays owner-reserved
if it turns out to be material); this review's own DC-17 model
attestation (blocked by the very `BUG-037` this session goes on to
remediate next — recorded manually above from the transcript instead).

## Disposition

MOD-001 does **not** proceed to its next critical slice (the R04
RLS-lint/permission-lint gates) until `BUG-038` is remediated (Docker
Engine + the pinned `postgres:16-alpine` image registered in
`CAPABILITY_REGISTRY.md`, qualified, and independently Opus-approved).
The P2/Editorial findings are non-blocking and are left open as tracked
follow-ups, not remediated in this turn (this turn's own scope is the
independent review + BUG-037 + the psycopg qualification check, per
the governing mission — not a Slice-5 remediation pass).
