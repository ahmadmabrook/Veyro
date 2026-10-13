---
doc: R04_CRITICAL_SLICE_SECURITY_REVIEW_R2
module: MOD-001
date: 2026-10-02
reviewer: fresh independent veyro-security-reviewer (Claude Opus)
status: BLOCKED (P0=0, P1=2, P2=3, P3=3)
---

# R04 critical-slice security review — Round 2

Fresh read-only ACPX session `veyro-mod001-r04-security-r2-20261002`
(Claude transcript `adbd1545-d745-46c7-a58c-76d458fa5197.jsonl`) reviewed
the post-R1 implementation and ADR-009. Orchestrator-run `mr_verify.py`:
**PASS, 84 turns, 100% `claude-opus-5-5`**. Reviewer changed no repository
files. **Verdict: BLOCKED, P0=0/P1=2/P2=3/P3=3.** The R1 P1s are fixed; the
permission gate resisted the tested under-scan and justification bypasses.
This is not full R04 or module approval.

## Blocking findings

1. **P1-1 — runtime-role non-table RLS bypasses missed.** The gate checks
   SUPERUSER/BYPASSRLS and table ACLs, but returned PASS when
   `veyro_runtime` had the REPLICATION attribute: a real `pg_basebackup`
   copied tenant B's `access_grant` heap bytes. It also PASSED when the role
   could `SET LOCAL ROLE pg_execute_server_program` to read the heap, and
   when it had a direct `GRANT EXECUTE` on `pg_read_binary_file(text)`.
   `pg_read_server_files`/`pg_write_server_files` are related unprobed paths.
   See `tools/validate_architecture_gates.py` role/privilege inspection
   (R2 reviewer cited lines 231–240). `veyro-lead` should decide whether
   the runtime posture is allow-by-construction instead of another deny-list.
2. **P1-2 — schema ownership missed.** After `ALTER SCHEMA harness OWNER TO
   veyro_runtime`, the gate returned PASS; the runtime role then dropped
   `harness.access_grant`, destroying tenant B's rows. The table-owner check
   does not inspect `pg_namespace.nspowner` (reviewer cited lines 242–254,
   438–441). Schema-owner membership and CREATE also need consideration.

## Other findings

- **P2-1:** `pg_get_expr` is deparsed under the inspector's ambient
  `search_path`. A malicious `public.=` operator plus database
  `search_path = public, pg_catalog` made a tautological policy pass while
  the runtime role read 3 cross-tenant rows. Pin `search_path = pg_catalog`
  before catalog collection and test the adversarial case.
- **P2-2:** materialized views/foreign tables are excluded by the `r,p`
  relation-kind scan. Reviewer demonstrated a granted matview that exposed
  3 other-tenant rows while the gate PASSED. Fix or explicitly disclose
  and scenario-track the limitation.
- **P2-3:** top-level `CURRENT_STATE.md` and `CURRENT_HANDOFF.md` still
  placed a superseded 09:37 "ADR-009 unimplemented" note above the newer
  implementation checkpoint. Correct current-order wording.
- **P3:** `security: null` was accepted as explicit for credential-exchange/
  provider-signature operations; an empty security-scheme object was accepted
  for an authenticated operation; the mutation script edits the real tool
  in place (a SIGKILL could leave it mutated). Reviewer recommends fixing.

## Independent execution and disposition

Reviewer ran 57/57 gate unit, 24/24 Colima RLS integration, 75/75 backend,
37/37 mutation kills on a `/tmp` mirror, 44 permission probes, 13 Colima RLS
probes, BUG-048 repro, mypy strict, Ruff, and baseline 4/4. It inspected,
but did not rerun, other governance validators. The permission gate's
ADR-009 cases held: malformed/unsupported/hidden operations fail closed,
non-authenticated classes need matching justified registration, PASS carries
the required inventory, and no exemption path was found. ADR-009 conforms
to TSD §8.4/§24.1 and does not itself need owner approval, but D2 should
consider an ADR/OWN reference for any non-authenticated registry entry;
the existing contract/route-parity residual remains prior-to-real-HTTP.

Reviewer recommended SCN-004/010/011 eligible on their literal proofs;
SCN-067 eligible on its disabled-RLS clause but better promoted with R3;
SCN-005 **not eligible** while P1-1/P1-2 remain. No status was changed.
BUG-048 remains P2 OPEN (order-dependent false failures), to close before
CI wiring. Canonical records retain SCN-067 BLOCKED and the slice BLOCKED.

Next: bounded `veyro-lead` decision on runtime-role posture and remaining
RLS D3/D4 design questions, then the same critical implementation session
remediates P1/P2, then a **fresh** R3 security review and a distinct fresh
code review. The full response/probe trail is in the named ACPX session.
