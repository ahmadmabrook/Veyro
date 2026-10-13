---
doc: SCN-MOD001-009-EVIDENCE-RECONCILIATION
module: MOD-001
scenario: SCN-MOD001-009
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic concurrency/versioning
date: 2026-10-04
status: EXECUTED — EVIDENCE CLAUSE SATISFIED BY EXECUTION; SCENARIO NOT PROMOTED
work_unit: SCN-MOD001-009 scenario evidence reconciliation (distinct from the closed DOM-002 code-review cycle)
---

# SCN-MOD001-009 — two-writer outcome evidence reconciliation

## 0. Scope and what this record is not

This is a bounded **scenario-evidence reconciliation** for one scenario. It
is governed by `AUTONOMOUS_CONVERGENCE_STATE.json`'s `ACTIVE` status, which
is scoped to this record unit only.

It is explicitly **not**: a DOM-002 code review, a DOM-002 remediation, a
resumption/retry/replacement of the interrupted round-5 review (which has no
verdict and is non-resumable per
`knowledge/00-System/DOM002-CONVERGENCE-DISPATCH-CONTROL-2026-10-04.md`), or
any R04/ADR-010 work. No review was dispatched and no
`REVIEW_IN_FLIGHT.md` claim was written or needed.

## 1. The exact unresolved requirement

`SCENARIOS.md`'s `SCN-MOD001-009` entry, acceptance text verbatim:

> Steps: a synthetic mutable aggregate updated by two concurrent
> "requests" (simulated, not real load); optimistic-versioning check
> proves the second write detects a version conflict rather than silently
> overwriting (lost-update behavior explicit, per DOM-002). **Evidence: both
> write attempts' outcomes logged; exactly one succeeds, one gets a
> version-conflict error.**

Governing requirement row (`REQUIREMENTS.md` line 590, DOM-002): "Proven by
a concurrency/versioning test pattern in the test-pyramid's persistence
layer | GOV-01-R02; CONC category", with the lost-update resolution for this
fixture recorded there as **reject-and-retry**.

The routing question is already closed: the former "GOV-01-R04, TSD §24.1
gate 2" tag was a catalog error (gate 2 is the module dependency/SQL lint),
corrected to GOV-01-R02/CONC per
`knowledge/00-System/DOM002-CONVERGENCE-ASSESSMENT-2026-10-04.md`. R04/
ADR-010 A2 is therefore **not** a prerequisite for this scenario.

## 2. The gap found, precisely stated

Before this session, `test_concurrent_writers_lost_update_detected`
already proved the *behavior*: writer A committed, writer B raised a typed
`VersionConflict`, writer A's value survived, the version advanced once.
What it did **not** produce was the scenario's own evidence artifact. Two
distinct shortfalls:

1. **No logged outcome record.** The two attempts' outcomes existed only as
   pytest pass/fail plus assertion source an auditor has to read and trust.
   The scenario asks for both outcomes *logged* — a record the outcomes can
   be read off directly. Sibling harnesses in the same suite
   (`test_authn_harness.py`, `test_architecture_gate_rls.py`) already emit
   exactly that, via a `_evidence(tag, payload)` helper printing
   `{TAG}-EVIDENCE <json>`; the concurrency suite was the one GOV-01-R02
   harness that did not.
2. **"Exactly one / exactly one" was structural, not measured.** Writer A's
   success was an unchecked call and writer B's rejection was a
   `pytest.raises` block. That shape cannot observe the two failure modes
   the clause exists to exclude: *two* successes (the lost update itself),
   and a rejection carrying the *wrong* typed error (`RowNotFound` standing
   in for a version conflict — round-1 review P2-1's defect class).

## 3. Change made (minimal, reuses existing architecture)

One file touched: `backend/tests/integration/test_concurrency_harness.py`.
No production code, no harness-module change, no new dependency, no new
mechanism. **No test function was added or removed** — the file collects 5
tests before and after.

- `_evidence(tag, payload)` — byte-for-byte the same helper and
  `{TAG}-EVIDENCE <json>` stdout convention already used by
  `test_authn_harness.py:34` and `test_architecture_gate_rls.py:101`,
  deliberately reused rather than reinvented.
- `_attempt(writer, expected_version, mutate)` — runs one synthetic writer
  and reduces it to a serializable outcome record
  (`outcome`/`rowcount`/`error`). Catches **only** `VersionConflict` and
  `RowNotFound`; any other exception propagates and fails the test exactly
  as before. The typed error's own attributes (`expected_version`,
  `row_id`) are copied into the record, so the pre-existing
  `exc_info.value.expected_version == writer_b_version` check is preserved
  rather than dropped, and now also appears in the logged evidence.
- `test_concurrent_writers_lost_update_detected` — both writers now run
  through that same recorder (neither privileged by its call shape), the
  one-success/one-conflict property is asserted as a **count** over the two
  records plus an error-type assertion, and the pair is emitted via
  `_evidence("SCN-MOD001-009", ...)`. All pre-existing assertions retained.
- `test_naive_unversioned_update_loses_the_update` — same recorder, same
  record shape, emitted as
  `SCN-MOD001-009-DIFFERENTIAL[unversioned-control]`. This is what makes
  the logged evidence non-vacuous: on the deliberately-broken fixture the
  record reads **2 committed / 0 rejected**, so a `1/1` evidence line could
  not have been produced by an implementation missing its version
  predicate.
- The file's stale "Scope note" docstring paragraph (which still described
  the gate-2 mislabeling as an open discrepancy) was corrected to the
  resolved routing and the actual remaining blocker.

## 4. Executed outcomes — exact results

Interpreter: `backend/.venv/bin/python`, Python 3.14.5. Docker: Colima
(CAP-008, APPROVED). All runs this session, 2026-10-04.

### 4.1 Focused scenario suite — the evidence itself

`python -m pytest tests/integration/test_concurrency_harness.py -v -s -p no:randomly`
→ **5 passed in 1.46s**. Full raw log:
`SCN-MOD001-009-TWO-WRITER-OUTCOME-RUNLOG-2026-10-04.txt` (same directory).

The scenario's two-outcome record, verbatim from that run (`row_id`
is per-run; everything else is invariant):

```
SCN-MOD001-009-EVIDENCE {"aggregate": "concurrency_harness.versioned_widget",
"attempts": [{"error": null, "expected_version": 1, "outcome": "committed",
"rowcount": 1, "writer": "writer-a"}, {"error": {"conflict_expected_version":
1, "message": "version conflict on concurrency_harness.versioned_widget:
id=28d0dab6-448f-490a-91d3-6f57a9bfb31c expected_version=1", "type":
"VersionConflict"}, "expected_version": 1, "outcome": "rejected", "rowcount":
0, "writer": "writer-b"}], "committed_count": 1, "concurrency_shape": "two
simulated sequential writers on one connection (see
tests/harness/concurrency.py 'Known ceiling')", "final_row": {"value":
"writer-a", "version": 2}, "lost_update_resolution": "reject-and-retry
(REQUIREMENTS.md DOM-002 row)", "rejected_count": 1, "row_id":
"28d0dab6-448f-490a-91d3-6f57a9bfb31c", "starting_version": 1}
```

Read directly off that line, against the acceptance clause: both attempts
present (2 records), `committed_count` 1, `rejected_count` 1, the rejection
is typed `VersionConflict` at the stale version 1, and the surviving row is
writer A's at version 2.

Differential control, same run:

```
SCN-MOD001-009-DIFFERENTIAL[unversioned-control]-EVIDENCE {... "attempts":
[{"error": null, ... "outcome": "committed", "writer": "writer-a"}, {"error":
null, ... "outcome": "committed", "writer": "writer-b"}], "committed_count":
2, "final_row": {"value": "writer-b", "version": 2}, "rejected_count": 0 ...}
```

2 committed / 0 rejected on the broken fixture — the correct path's 1/1 is
therefore a discriminating result, not a shape the logger would print either
way.

### 4.2 Mutation sensitivity of the *new* assertions

Both mutants applied to `backend/tests/harness/concurrency.py`, run, then
the file restored and confirmed **byte-identical** to its pre-drill copy
(`diff` empty).

| Mutant | Change | Result |
|---|---|---|
| M1 | version predicate made always-true (`AND version = %s` → `AND version <> %s + 1000000`), reintroducing the lost update with a well-formed statement | **KILLED** by the new count assertion: `expected exactly one committed write, got [...writer-a committed..., ...writer-b committed...]` / `assert 2 == 1`, at `test_concurrency_harness.py:196` |
| M2 | `raise VersionConflict(...)` → `raise RowNotFound(...)` on the conflict branch | **KILLED** by the new type assertion: `assert 'RowNotFound' == 'VersionConflict'`, at `test_concurrency_harness.py:202` |

A first M1 attempt (deleting the predicate *and* its placeholder) was
ill-formed and died on a psycopg placeholder-count error rather than
semantically; it is recorded here as discarded, and M1 above is the
well-formed replacement that actually exercises the lost-update path.

### 4.3 Regression and required checks

| Check | Command | Result |
|---|---|---|
| Order-independence regression | `pytest tests/integration/test_concurrency_harness_order_independence.py -v -p no:randomly` | **3 passed in 5.67s** |
| Full backend suite | `pytest -q -p no:randomly` | **204 passed in 25.14s** (same count as before the change — no test added/removed) |
| Lint | `ruff check .` | **All checks passed!** |
| Types | `mypy tests/` (strict, `python_version = 3.13`) | **Success: no issues found in 28 source files** |
| Container/volume leak (BUG-051 class) | `docker ps -aq`/`docker volume ls -q` before and after | **1 container / 2 volumes both before and after — stable** |
| Baselines | `knowledge/00-System/verify_baselines.py` | **PASS — all 4 governing baseline hashes match** |
| Aggregate regression | `knowledge/05-QA/tools/run_regression.py` | **FAIL (3/4 passed, 1 N/A)** — the single failure is the pre-existing `evidence_integrity_check.py` `CURRENT_HANDOFF.md` staleness artifact (last *commit* 2026-09-29 vs later-dated evidence commits), already tracked and not caused by this change; nothing is committed in this session. Run record: `knowledge/05-QA/tools/regression-runs/RUN_20261004T093926Z.txt` |
| Capability manifest | `tools/validate_capability_manifest.py --manifest knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` | **PASS — 10 capability/Rule IDs, all registered and APPROVED** |
| Capability drift | `knowledge/05-QA/tools/capability_drift_check.py` | **PASS — 8 capabilities, no drift** |

`ruff format --check` reports this file among 10 tree-wide files it would
reformat. That is **pre-existing, not introduced here**: the reported diff
includes untouched code (`test_single_writer_succeeds_and_increments_version`
at line ~150), and `ruff format` is not an enforced gate on this project
(`ruff check` + `mypy --strict` are). New code follows the surrounding file's
existing style rather than reformatting unrelated lines.

## 5. Disposition and justification

**`SCN-MOD001-009`: EXECUTED — EVIDENCE CLAUSE SATISFIED BY EXECUTION;
NOT PROMOTED.**

Satisfied, by execution recorded above:

- the scenario's steps (synthetic mutable aggregate, two simulated writers,
  optimistic-versioning check, lost-update behavior explicit);
- its evidence clause in full — both write attempts' outcomes are now
  durably logged, with exactly one success and exactly one typed
  `VersionConflict`, shown non-vacuous by the differential control and by
  two killed mutants;
- its routing (GOV-01-R02/CONC), with the former R04/gate-2 prerequisite
  established as a catalog error, so ADR-010 A2 / R04's own
  `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` state does not gate it.

Not promoted, for one reason only:

- **DC-06 — no self-approval.** The instrumentation in §3 was written by
  this implementing session. Promotion requires a fresh-context
  independent review of *this* change, which this session cannot grant
  itself. Round-4's PASS (P0=0/P1=0/P2=0/P3=6) covered an earlier snapshot
  and cannot retroactively cover code written after it.

Promotion is also **not** unblockable by simply dispatching that review
now: `AUTONOMOUS_CONVERGENCE_STATE.json` records
`normalDom002ReviewOrRemediationAllowed: false` and
`anotherReviewCurrentlyAllowed: false`, and the governing dispatch control
denies DOM-002 review/remediation dispatch. Whether a review of *this
scenario-evidence instrumentation* is a distinct work unit from the closed
DOM-002 code-review cycle — and therefore dispatchable — is a governance
decision this session is not authorized to make for itself.

## 6. Remaining blockers (honest statement)

1. **`BLOCKED: INDEPENDENT_REVIEW_REQUIRED`** — a fresh-context review of
   the `test_concurrency_harness.py` instrumentation is the only technical
   gap between the current state and promotion.
2. **`BLOCKED: GOVERNANCE_DECISION_REQUIRED`** — whether that review may be
   dispatched at all, given the convergence state's standing denial of
   further DOM-002 review dispatch, needs an explicit governed decision
   (owner or a separately governed adjudication). This session did not
   dispatch one and did not assume entitlement to.
3. Unchanged and out of this unit's scope: R04/ADR-010 A2 remains
   `BLOCKED: MODEL_ASSURANCE_UNVERIFIED`; MOD-001 module certification is
   untouched; the pre-existing `CURRENT_HANDOFF.md` evidence-integrity
   staleness artifact persists because nothing was committed.

Nothing was committed or pushed. All other uncommitted work in the tree was
left untouched; the only files changed by this session are
`backend/tests/integration/test_concurrency_harness.py` and the records
listed in the handoff.
