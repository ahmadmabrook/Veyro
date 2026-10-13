---
doc: R04_CRITICAL_SLICE_SECURITY_REVIEW_R3
module: MOD-001
date: 2026-10-03
reviewer: fresh independent veyro-security-reviewer (Claude Opus, Task subagent)
status: BLOCKED (incomplete review; P0=0, P1=3 provisional, P2=4, P3=2)
---

# R04 critical-slice security review — Round 3

A fresh parent session (not the implementation session) dispatched the
registered `veyro-security-reviewer` role through Task to review the current
uncommitted R04 diff against ADR-009 and ADR-010 (including A1/A1.7). It ran
as subagent `a2660358346e119cc` in parent session
`a6545de4-eaf3-4a4e-b456-06a05021a375`.

**Model route (orchestrator-run, not self-reported):**
`backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py <transcript> opus veyro-security-reviewer`
returned **PASS: 48 turns, 100% `claude-opus-5-5`** (exit 0).

- Transcript: `~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/a6545de4-eaf3-4a4e-b456-06a05021a375/subagents/agent-a2660358346e119cc.jsonl`
- Transcript sha256: `3bbe455879f64804ffef0c3e16a2434d3040ec2117c77749b3f7d564f1a3b716`
- `meta.json` records `agentType: veyro-security-reviewer`, foreground and non-interactive.

**Verdict: BLOCKED.** This is not R04 approval and not module approval.

## Completeness caveat (read first)

The review did **not** finish as planned. Mid-review, a harness safety
classifier withheld one reviewer response, and tool calls in that response
did not run. The transcript records it as a classifier stop, "not a tool or
API error". It was not a provider or transport failure.

After that stop, the reviewer chose not to run its planned adversarial
database probes. As a result:

- None of the findings below was reproduced by execution.
- The BLOCKED verdict rests on code-reading of the gate against ADR-010 A1/A1.7.
- ADR-010 requires R3 to actually attempt a new privilege path outside the
  D1.4 table. That was not done, so APPROVED was unreachable either way.

If the owner treats a classifier stop the same as a transport failure,
record this round as **no verdict** instead. Either way, the slice stays
BLOCKED and a further fresh review with executed probes is required.

## Findings

All P1/P2 findings are provisional: they come from code-reading and await
executed confirmation. Line numbers refer to `tools/validate_architecture_gates.py`
as reviewed (gate file sha256 prefix `34aa8461…629e91b`).

### P1 (provisional)

1. **A `pg_init_privs` row confers "system" status, and an extension can forge one.**
   - Where: lines 484–494, 605–607, 643–646; ADR-010 A1.2 bullet 1.
   - Path: any object with a `pg_init_privs` row is classified as a system
     object. A superuser migration can create such a row with
     `ALTER EXTENSION … ADD`, and 60+ contrib extensions are available on the
     image (confirmed by catalog query).
   - Effect on a reclassified application object:
     - It is judged only by "subset of initial ACL".
     - It skips the D1.4 allow-table and the D1.6 checks (`security_invoker`,
       matview, foreign table).
     - It is excluded from the SECURITY DEFINER query.
     - A non-stock `information_schema` object reclassified this way yields
       **no token at all**, instead of `NON_STOCK_SYSTEM_OBJECT`.
   - This is an ADR gap as well as an implementation gap.
2. **SECURITY DEFINER review only covers functions the runtime role can EXECUTE.**
   - Where: lines 600–611; ADR-010 D1.4 / N19.
   - TSD §7.3 says the lint rejects SECURITY DEFINER functions unless
     reviewed, with no executability condition.
   - Trigger and event-trigger functions run without a caller EXECUTE check,
     so a definer function with PUBLIC EXECUTE revoked is never reported.
   - ADR gap: ADR-010 narrowed the TSD wording.
3. **D1.4 allows EXECUTE on any non-SECURITY-DEFINER application function, whatever its language.**
   - Where: lines 283–293, 790–793.
   - Functions in `internal`/`c`, or in untrusted PLs (`plperlu`/`plpython3u`,
     both available on the CAP-008 image), are not bound by EXECUTE grants on
     the built-ins they wrap.
   - The R2 P1-1 class (server-file read) is therefore plausibly reachable
     through such a wrapper. ADR gap.

### P2

- **Definer-rights rewrite rules are not inspected.** The gate has no
  `pg_rewrite` collection, and a rule owned by an RLS-exempt role runs with
  that owner's rights. (provisional)
- **The tenant-context default check is case-sensitive.** Line 668 uses
  `s.startswith("app.")`, so a quoted mixed-case `"APP.TENANT_ID"` stored in
  `setconfig` may evade it. Fix: compare `.lower()`. (provisional)
- **A function-level `SET app.tenant_id` (`proconfig`) is not judged.**
  D1.7 covers only `pg_db_role_setting`. ADR gap.
- **OUT_OF_SCOPE splits the identity on the first `.`.**
  - Where: lines 796–798; identities are built unquoted at 509–510.
  - A schema named `"harness.x"` matches a narrowed `--schema harness`, which
    skips D1.6 and also the relations loop (line 818).
  - Affects only `--schema`-narrowed runs. Fix: carry schema and relation as
    separate fields.

### P3

- **Approval resolution uses substring containment** (lines 406, 414). A
  DECIDED ADR naming `members.profile.reader` approves
  `members.profile.read`. Use token-bounded matching.
- **`oauth2.flows` contents are not validated** (lines 1029–1030). This is
  within the D5.2 text.

## R2 closure status

| R2 finding | R3 status |
|---|---|
| P1-1 REPLICATION | CLOSED in code (D1.1, lines 762–766); integration suite green |
| P1-1 `pg_execute_server_program`, `pg_read/write_server_files`, other predefined roles | CLOSED in code (D1.2, lines 767–768, closure by MEMBER at 546–551) |
| P1-1 direct GRANT EXECUTE on `pg_read_binary_file` | CLOSED for the direct grant (D1.5). PARTIAL for the class: see P1-1 and P1-3 above |
| P1-2 schema owner, owner membership, CREATE on schema | CLOSED in code (`pg_shdepend` plus `nspowner`/`relowner`/`datdba`, lines 553–571; CREATE is not in the allow-table) |
| P2-1 `search_path` pinning | CLOSED (pin and read-back at 689–693, RR READ ONLY at 694, `pg_depend` closure at 592–597) |
| P2-2 matview, foreign table and view coverage | CLOSED for ordinarily classified relations. PARTIAL: system-classified relations bypass it (P1-1) |
| P2-3 state-doc ordering | NOT VERIFIED (`CURRENT_STATE.md` ordering looks correct; `CURRENT_HANDOFF.md` not audited) |
| P3 `security: null`, empty scheme `{}` | CLOSED in code (lines 999–1004, 1020–1036) |
| P3 in-place mutation script | NOT VERIFIED (script not read) |

## ADR-010 A1 / A1.7 acceptance

- **N1–N26 and P1–P10.** The integration suite (68) and unit suite (52) pass.
  Each acceptance row was not cross-checked against test names.
- **A1.2 system-object definition.** Implemented as written, but the
  definition can be forged through `pg_init_privs` (P1-1).
- **A1.3 per-object pin.** Conforms (lines 729–737).
- **A1.7 H2 token exclusivity: holds by construction.**
  - A `non_stock` grant hits `continue` before the system branch, and a
    `system` grant hits `continue` before the allow-table (lines 781–789).
  - So one grant can never produce both tokens.
  - Residual: exclusivity does not stop a forged reclassification, which
    yields no token instead of `NON_STOCK_SYSTEM_OBJECT` (inferred from code,
    not executed).
- **Adversarial policy predicates** (OR-branches, casts, case and whitespace
  variants, subqueries, schema-qualified look-alikes): **not executed**. By
  code, the exact-deparse match plus `pg_depend` closure should reject them.

## Executed evidence

| Command | Result |
|---|---|
| `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | PASS 4/4 |
| `backend/.venv/bin/python -m pytest -q -p no:cacheprovider tools/tests/test_validate_architecture_gates.py` | 52 passed |
| `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_architecture_gate_rls.py` (Colima PG16) | 68 passed |
| Discovery probe on a disposable harness PG16 with a byte-identical `/tmp` gate mirror | baseline gate PASS; `server_version_num` 160015; languages `internal`/`c`/`sql`/`plpgsql`; contrib incl. untrusted PLs available |

- **Not run:** the full backend suite, mypy, ruff, and all adversarial negative probes.
- **Cleanup:** the reviewer reported that the disposable container was removed
  by the harness context manager and `/tmp/r3` was deleted, with no other roles
  or databases created. The pre-existing, unrelated `tradingview-mcp` container
  was left untouched.

## SCN-067 gate-negative eligibility (separate from the slice verdict)

**ELIGIBLE on its literal clause.**
`test_scn067_gate_catches_rls_disabled_on_access_grant` passed in R3's own run:

- The gate returned FAIL with the single violation
  `RLS_NOT_ENFORCED: ENABLE ROW LEVEL SECURITY missing`.
- A behavioural 3-row cross-tenant leak was also shown.

Eligibility is not promotion. This review changed no scenario status, and
SCN-067 promotion remains a separate governed step.

Other scenarios:

- **SCN-005:** not eligible while the provisional P1s are unrefuted.
- **SCN-004, SCN-010, SCN-011:** not re-assessed in R3.

## Repository integrity

The reviewer's before and after hashes were identical:

- `git status --short`: `09813406…a8e538`
- `git diff`: `827cbaa1…c7aec7a1`
- untracked-file content: `85b99d2d…5411`

The parent independently re-hashed `git status --short` after the review and
got the same value (`09813406dda2a8e1…a8a5e538`). The reviewer changed no
repository files. The parent's only write is this evidence file. Nothing was
committed or pushed.

## Next steps

1. **veyro-lead:** amend ADR-010 so that:
   - a `pg_init_privs` row alone cannot confer system status (A1.2);
   - SECURITY DEFINER review follows the TSD's unconditional wording (D1.4/N19);
   - D1.4 EXECUTE is constrained by function language/owner;
   - rewrite rules and function-level `proconfig` tenant settings are covered.
2. **Same critical implementation session:** remediate, adding an executed
   negative fixture for each provisional P1/P2.
3. **A fresh R4 security review** that executes the adversarial probes R3
   could not run, plus a distinct fresh code review.
