# SCN-MOD001-070 convergence assessment — 2026-10-04

Bounded unit: MOD-001 / GOV-01-R06 migration-ordering lint / SCN-MOD001-070. This is control-plane root-cause analysis, not a fourth review or scenario promotion. DOM-002 remains a separate, closed code-review cycle: four completed reviews/four remediations; interrupted round 5 has no verdict and is non-resumable.

## Reconciliation

Three substantive fresh independent SCN-070 reviews and two substantive remediations are complete. Round 3's report and ACPX final response agree: BLOCKED, P0=0/P1=0/P2=1/P3=3. It independently closed R2-1 symlinked child, R2-2 duplicate keys and R2-3 existing-file path using discriminating pre-fix controls; 29/29 unit tests passed, 11/11 authored mutants killed, four baselines matched. This is material progress, not a no-progress iteration. The single open required P2 is R3-1: a mode-000 directory containing a destructive contract record returns exit 0 and a false vacuous PASS; the same directory readable correctly fails. The reviewer reproduced `rglob` silently returning empty while `iterdir` raised `PermissionError`. No live ACPX/Claude writer or reviewer exists at this assessment. The round-3 durable claim is fulfilled by the completed report and can be cleared. Git HEAD remains e481b814a80923849dddfe7a49319112aae7b023; existing uncommitted work is preserved.

## Semantic classification and root cause

- R2-1/R2-2/R2-3: `NEW_DEFECT` historically, **closed by independent round-3 evidence**. They are not reopened because of a new wording or reviewer.
- R3-1: `ROOT_CAUSE_ARCHITECTURAL` — the same fail-closed exhaustive-discovery invariant as R1-3, R2-1 and R2-3, newly manifested on unreadable directories. Ad-hoc guards around a `Path.rglob` enumerator that suppresses traversal errors cannot prove exhaustive discovery. This is a recurrence of the invariant family, not a distinct clean review budget. Its exact unreadable-directory mechanism is newly evidenced; no claim that the identical individual finding recurred twice after verified remediation.
- R3-2/R3-3/R3-4: `FALSE_POSITIVE_OR_NON_REQUIREMENT` for this bounded scenario gate at P3 only, not blocking promotion by themselves. The report says unknown-key decoys have no ordering bypass, absolute local paths are CI-log hygiene, and CI wiring is future gate work. Carry them without representing them as closed.

## Mandatory budget decision

Three normal reviews have reached the convergence-analysis trigger. `ANALYSIS_REQUIRED` applies during this assessment; do not launch a normal fourth review or a generic patch/retry. The cause is now evidenced at the enumerator abstraction, and a **materially changed strategy** is available: replace glob-driven discovery with explicit error-reporting directory traversal, preserve symlink and record rules, make any unenumerable subtree a named nonzero failure, and add invariant-based readable/unreadable positive-negative tests plus a mutation that removes the traversal-error guard. This addresses the whole failure family instead of adding one more top-level permission check. No DOM-002 dispatch is permitted.

After this completed assessment, `ACTIVE` is warranted solely for one bounded SCN-070 architectural root-cause remediation under the changed strategy. A fourth independent review is *not* pre-authorized by that transition; after remediation, reconcile the exact evidence and separately decide whether a distinct new P2 justifies one exceptional review within the five-review absolute cap. If the remediation does not demonstrably eliminate the root cause or introduces another same-invariant fail-open, mark `NON_CONVERGING` instead of cycling. Scenario stays EXECUTED — PENDING INDEPENDENT REVIEW. No owner-stop condition exists.
