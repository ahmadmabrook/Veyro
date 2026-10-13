---
doc: SCN-MOD001-009-EVIDENCE-INSTRUMENTATION-INDEPENDENT-REVIEW
module: MOD-001
scenario: SCN-MOD001-009
requirement: GOV-01-R02 (CONC category) — DOM-002 optimistic concurrency/versioning
work_unit: SCN-MOD001-009 two-writer outcome instrumentation + run log + scenario disposition
review_type: fresh-context independent scenario-evidence review (single round, bounded)
date: 2026-10-04
reviewer_model: claude-opus-5[1m] (self-reported; see §6)
verdict: PASS
findings: P0=0 / P1=0 / P2=0 / P3=3
---

# SCN-MOD001-009 — independent review of the two-writer outcome evidence unit

## 1. Scope (and what this review is not)

Reviewed, and only this:

- the new instrumentation in `backend/tests/integration/test_concurrency_harness.py`
  (`_evidence`, `_attempt`, the recorder/count/type assertions in
  `test_concurrent_writers_lost_update_detected`, and the mirrored recorder in
  `test_naive_unversioned_update_loses_the_update`);
- the emitted JSON records;
- `evidence/implementation/SCN-MOD001-009-TWO-WRITER-OUTCOME-RUNLOG-2026-10-04.txt`;
- `evidence/implementation/SCN-MOD001-009-EVIDENCE-RECONCILIATION-2026-10-04.md`;
- the `SCENARIOS.md` SCN-MOD001-009 disposition text.

Single question answered: **do these artifacts faithfully prove the exact
SCN-MOD001-009 acceptance clause** — two write attempts, both outcomes
logged, exactly one committed, one rejected with a *version-conflict* error,
and is that result discriminating rather than unconditional?

Explicitly **not** reviewed, per the dispatch boundary and
`AUTONOMOUS_CONVERGENCE_STATE.json`'s adjudication
(`ALLOW_ONE_FRESH_INDEPENDENT_SCENARIO_EVIDENCE_REVIEW_ONLY`): the DOM-002
harness/production code (`tests/harness/concurrency.py`) as a correctness
subject, the round-4 P3 findings, R04/ADR-010 A2, BUG-051/Docker cleanup, or
MOD-001 certification. `tests/harness/concurrency.py` was read and mutated
**only** as an instrument for testing the new assertions' sensitivity, and
restored byte-identical (§3.2). This review does not resume, replace, retry or
substitute for the interrupted DOM-002 round 5, which has no verdict. No
counter in the DOM-002 4+4 history is affected.

## 2. Verdict

**PASS.** P0=0 / P1=0 / P2=0 / P3=3.

The acceptance clause is proven by execution I performed myself, not merely
by the implementing session's claim. The three P3 findings are evidence-
integrity and record-accuracy improvements; none of them makes the clause
unproven, and none blocks promotion on technical grounds.

## 3. Execution performed by this reviewer

Environment: `backend/.venv/bin/python`, Python 3.14.5, pytest 9.1.1, Docker
daemon reachable (one pre-existing unrelated container, untouched).

### 3.1 Independent re-run of the canonical evidence

`.venv/bin/python -m pytest tests/integration/test_concurrency_harness.py -v -s -p no:randomly`
→ **5 passed in 3.99s**, emitting (row ids differ per run, everything else
identical to the committed run log):

```
SCN-MOD001-009-EVIDENCE {"aggregate": "concurrency_harness.versioned_widget",
"attempts": [{"error": null, "expected_version": 1, "outcome": "committed",
"rowcount": 1, "writer": "writer-a"}, {"error": {"conflict_expected_version": 1,
"message": "version conflict on concurrency_harness.versioned_widget:
id=3b7ad391-1f23-4901-bff1-a3d7cbed3ef2 expected_version=1", "type":
"VersionConflict"}, "expected_version": 1, "outcome": "rejected", "rowcount": 0,
"writer": "writer-b"}], "committed_count": 1, "concurrency_shape": "two simulated
sequential writers on one connection ...", "final_row": {"value": "writer-a",
"version": 2}, "lost_update_resolution": "reject-and-retry ...",
"rejected_count": 1, "row_id": "3b7ad391-...", "starting_version": 1}
```

The committed run log **reproduces**. Clause mapped item by item against this
line, read off the artifact rather than the source:

| Clause element | Where it is readable | Result |
|---|---|---|
| two write attempts | `attempts[]`, length 2, uniform shape | MET |
| both outcomes *logged* | each record carries `outcome`/`rowcount`/`error` | MET |
| exactly one succeeds | `committed_count: 1`, **derived** from `len([a for a in attempts if a["outcome"]=="committed"])` at `:193`/`:221` | MET |
| one gets a *version-conflict* error | `error.type == "VersionConflict"`, asserted at `:202`; `conflict_expected_version` equals the stale version, asserted at `:203` | MET |
| second write not silently overwriting | `final_row` = `writer-a` @ version 2, asserted at `:211-212` | MET |
| simulated, not real load | disclosed *inside the record itself* via `concurrency_shape` | MET, honestly qualified |

The `concurrency_shape` disclosure is accurate: `admin`
(`tests/integration/conftest.py:40-42`) is a single autocommit
`psycopg.connect`, so "two simulated sequential writers on one connection" is
a true description, not an understated one. The scenario text itself permits
simulation ("simulated, not real load"), so this is conformance, not deviation.

### 3.2 Independent mutation drills (non-vacuity)

I did not accept the reconciliation record's mutation table; I reproduced both
mutants myself against `tests/harness/concurrency.py`, with a sha256-verified
backup/restore.

Pre-drill sha256: `1adeec69e9e317f96688bc9616f6311674772c189c90ae38ae7af7c0a57118a4`

| Mutant | Change | Observed result |
|---|---|---|
| M1 — lost update reintroduced | `AND version = %s` → `AND version <> %s + 1000000` in `update_versioned`'s `WITH` statement | **KILLED.** `AssertionError: expected exactly one committed write, got [...writer-a committed..., ...writer-b committed...]` / `assert 2 == 1` at `test_concurrency_harness.py:196` |
| M2 — wrong typed error | `raise VersionConflict(table, row_id, expected_version)` → `raise RowNotFound(table, row_id)` | **KILLED.** `AssertionError: assert 'RowNotFound' == 'VersionConflict'` at `test_concurrency_harness.py:202` |

Both die at the **new** assertions specifically, at the exact line numbers the
reconciliation record claims. Post-drill sha256 identical, `diff` empty,
suite re-run **5 passed**. The harness file is in its original state.

This is the load-bearing result: M1 is the lost update itself, and the
pre-instrumentation `pytest.raises` shape could not have seen it. The clause's
"exactly one" is now a measured, sensitive property.

### 3.3 Differential control

The broken-fixture run emits `2 committed / 0 rejected` through the same
recorder, so a `1/1` line is discriminating. Note the scope of what the
differential alone establishes: writer-b there goes through a *different
function* (`update_unversioned_blind`), so the differential proves the
recorder distinguishes a rejecting from a non-rejecting write path. It is
**M1**, not the differential, that proves a *broken `update_versioned`* could
not have produced a `1/1` line. The reconciliation record cites both, so its
overall non-vacuity claim holds; the differential is not independently
sufficient for the sentence it is attached to.

### 3.4 Surrounding claims in the reconciliation record, re-verified

| Record claim | My result |
|---|---|
| focused suite 5/5 PASS | **confirmed** (5 passed) |
| full backend 204/204, count unchanged | **confirmed** (`pytest -q -p no:randomly` → 204 passed in 25.36s) |
| `ruff check .` clean | **confirmed** (All checks passed!) |
| `mypy tests/` strict clean, 28 files | **confirmed** (no issues found in 28 source files) |
| `_evidence` reuses an existing convention, not a new mechanism | **confirmed** — byte-identical helper at `test_authn_harness.py:34` and `test_architecture_gate_rls.py:101`; cited line numbers are correct |
| no test function added or removed | **confirmed indirectly** — 5 collected now; round-4's own run log shows 4 in this file, and round-4 remediation added the 5th (`test_update_versioned_executes_exactly_one_statement`, 203→204). Consistent. Not verifiable from git: the file is untracked (§5) |
| mutants killed at `:196` and `:202` | **confirmed by independent reproduction** (§3.2) |

No overstated claim found in the reconciliation record's execution section.

## 4. Findings

### P3-1 — parts of the emitted record are *declared*, not derived from the observed run
`test_concurrency_harness.py:365-366`

The differential record hardcodes `"committed_count": 2` and
`"rejected_count": 0` as literals, whereas the primary SCN-009 record derives
both from `len(...)` over `attempts` (`:221-222`). The reconciliation record
and `SCENARIOS.md` both rest their non-vacuity argument on the differential
being "the same recorder, same record shape" — but one record reports a
measurement and the other reports a constant. Today this cannot print a false
number, because `assert [a["outcome"] for a in attempts] == ["committed", "committed"]`
(`:344`) runs first and would abort before emission; the defect is latent, not
live. It still weakens the artifact: a reader auditing the differential JSON is
reading an assertion the author made, not an observation the run produced, and
any future weakening of `:344` would decouple the two silently.

Second, smaller instance: `expected_version` in each attempt record
(`:87`, `:102`) is a *parallel argument* to `_attempt`, not a value read from
the mutation call itself, so a call site passing `writer_a_version` to the
recorder while closing over `writer_b_version` in the lambda would log a value
the run did not use. The current two call sites are correct.

Suggested fix: compute the differential counts the same way the primary record
does (`len([a for a in attempts if a["outcome"] == "committed"])`).

### P3-2 — the durable record is emitted only on a passing run
`test_concurrency_harness.py:214`, `:360`

`_evidence(...)` is the final statement of each test, after every assertion.
I observed this directly during §3.2: **neither mutant run emitted any
`SCN-MOD001-009-EVIDENCE` line at all** — the auditor gets a pytest assertion
message instead, which is precisely the thing the instrumentation's own
docstring says it exists to replace ("a record an auditor reads the outcomes
off, not an assertion they must trust the source of"). The acceptance clause
concerns the proving run and is satisfied, so this is not a failure of the
clause. But the logged evidence can only ever show the green case, which is the
weaker half of what such a record is usually worth. Emitting from a `finally`
block (or before the assertion stanza) would make the record cover failures
too, at no cost to the assertions.

### P3-3 — stale present-tense claims retained inside the live `SCENARIOS.md` entry
`knowledge/03-Modules/MOD-001/SCENARIOS.md`, "Historical round-18 disclosure" paragraph

The entry's trailing paragraph still asserts, in the present tense, several
things the entry above it has since made false: "This entry's tag is left
unchanged here (a future Scenario Review round owns correcting the catalog
itself)" — the header tag now reads `GOV-01-R02, DOM-002`; "its own header
still names an R04/gate-2 prerequisite" — it no longer does; "3/3 passing" and
`harness.versioned_widget` — the suite is 5 tests against
`concurrency_harness.versioned_widget`; and "promoting this specific scenario
entry is a decision for whoever next reconciles the gate-2 mislabeling" — that
reconciliation has happened.

Mitigating, and the reason this is P3 rather than P2: the paragraph is
explicitly prefixed "**Historical round-18 disclosure (superseded by routing
correction above)**", and every authoritative statement above it is correct, so
a careful reader is warned. It is flagged anyway because this is the same
stale-present-tense-live-claim family the convergence state already tracks as
recurring (`DOM002-RECORD-ACCURACY`; Slice-7 rounds 7/8/9 NR7-2/NR8-1/NR9-1),
and the honest reading is that an append-only history paragraph written in the
present tense keeps regenerating this finding. A one-line past-tense rewrite
("round 18 left the tag unchanged; it was corrected on 2026-10-04") would
retire the class for this entry.

## 5. Scope limitations and caveats on this review

1. **No git baseline.** `backend/tests/integration/test_concurrency_harness.py`
   is **untracked** (`git status` → `??`), as is the whole MOD-001 backend
   work. I could not diff the instrumentation against a pre-instrumentation
   revision, so "minimal change, nothing else touched" is corroborated only by
   reading the current file, the round-4 report's run inventory, and the
   reconciliation record — not proven from version control. This also means
   nothing I reviewed is protected from silent later modification by a commit
   hash.
2. **No content hash on the run log.** The committed run log carries no
   checksum or provenance signature. I re-ran it and it reproduces, which is a
   stronger check than a hash — but the artifact itself is not tamper-evident.
3. **Single reviewer, single round, no second opinion**, by the governing
   adjudication's own terms.
4. **Harness correctness not assessed.** `update_versioned`'s own correctness,
   the round-4 P3s, the TOCTOU fix and the Docker/cleanup machinery were out of
   scope and are not endorsed by this verdict.
5. **Governance observation, outside my lane, not a finding against the
   evidence unit:** `knowledge/00-System/REVIEW_IN_FLIGHT.md`'s `current_claim`
   reads `CLEAR` and refers to the round-5 OAuth failure; no claim was written
   for *this* review before dispatch, which that file's own Protocol §1
   requires for "any role this project treats as independent/fresh-context".
   The orchestrating session owns that record; I did not edit it.

## 6. Model identity evidence

Self-reported reviewer identity: **`claude-opus-5[1m]`** ("Opus 5 (1M
context)"), consistent with the Opus assurance tier
`DEVELOPMENT_CONSTITUTION.md` model routing requires for independent code
review.

This is a *self-report* and is not independent attestation. The project's
established mechanism — `knowledge/05-QA/tools/mr_verify.py`, run by the
orchestrator against the reviewer's actual transcript, as was done for DOM-002
rounds 1-4 (104/104, 102/102, 130/130, 107/107 `claude-opus-5`) — cannot be run
by the reviewed session on itself. **If this verdict is to carry the same
weight as rounds 1-4, the orchestrating session must run `mr_verify.py` against
this review's transcript and append the result here.** Until it does, treat the
model attestation as pending, not satisfied.

**Orchestrator attestation, 2026-10-04:** `mr_verify.py` independently checked
the matching reviewer transcript
`~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/32116569-91a5-4a0b-abe9-26c6080ddd1c.jsonl`
with expected tier `opus` and agent label `veyro-code-reviewer`: **PASS,
51/51 turns, resolved model `claude-opus-5`**. The report path occurs in this
transcript. Model assurance for this verdict is satisfied.

## 7. Disposition

- **Verdict: PASS**, P0=0/P1=0/P2=0/P3=3, for the SCN-MOD001-009 evidence unit
  only.
- The scenario's acceptance clause is proven by execution independently
  reproduced in §3, including both mutation kills.
- **This review does not promote the scenario and takes no promotion action.**
  Promotion remains an orchestrator/governance decision; the three P3s above do
  not block it, and the `mr_verify.py` attestation in §6 is outstanding.
- No implementation file was edited. `tests/harness/concurrency.py` was mutated
  for two drills and restored byte-identical (sha256 verified, §3.2). No other
  working-tree file was modified. Nothing committed, nothing pushed.
