---
doc: CAP008-POST-R16-INDEPENDENT-ASSURANCE
status: LIVE — independent capability-security assurance review, review-only (no code/registry changes made by this review)
module: MOD-001
capability: CAP-008
date: 2026-10-04
dispatching_session: fresh Claude ACP session (orchestrator), independent of the MOD-001 implementation/remediation session
reviewer: veyro-security-reviewer (Opus), fresh context, no prior involvement in any artifact reviewed
---

# CAP-008 — post-round-16 independent capability-security assurance

## Purpose and scope of this review

Round 16 (`knowledge/03-Modules/MOD-001/evidence/security/GOV01-R02-SLICE7-DOMAIN-SCAFFOLDS-FINANCIAL-INVARIANT-SECURITY-REVIEW-ROUND16-2026-10-04.md`)
found CAP-008's technical qualification evidence complete, current, and
verified by execution, but declined to restore `review_status: APPROVED`
on two documentation-only conditions (R16-3, R16-5; see round 16 §18.4).
A retained Sonnet-tier implementation session subsequently claimed to
have corrected both the same day. This review's sole charge: independently
verify whether those corrections actually landed, accurately and
completely, and render an APPROVED/BLOCKED verdict on CAP-008's
`review_status` — without implementing anything, without re-running any
live qualification drill, and without self-certifying (policy separation
per `CAPABILITY_POLICY.md`'s model-routing section).

This record is **review-only**. No code, registry, scenario, or module-status
file was edited by the dispatching session or by the reviewing subagent.

## Dispatch and model-identity verification

- **Dispatched to:** `veyro-security-reviewer` (Opus), via the Agent tool, fresh context, `run_in_background: false`.
- **Subagent agentId:** `aa793a97c80f82668`.
- **Transcript:** `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/93bccff4-1b5b-4896-ade8-f55ebf273ede/subagents/agent-aa793a97c80f82668.jsonl`
- **Agent metadata** (`agent-aa793a97c80f82668.meta.json`): `agentType: "veyro-security-reviewer"`, `requestShape: "foreground"`.
- **Independent model attestation**, run by this orchestrating session (not self-attested by the subagent), per this project's standing `mr_verify.py` convention:

  ```
  $ /opt/homebrew/bin/python3.13 knowledge/05-QA/tools/mr_verify.py \
      ".../subagents/agent-aa793a97c80f82668.jsonl" opus veyro-security-reviewer

  {
    "verdict": "PASS",
    "reason": "70 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
    "models_observed": ["claude-opus-5"],
    "expected_tier": "opus"
  }
  ```

  **PASS, 70/70 turns, 100% consistent, `claude-opus-5`, matching the required Opus tier.** This matches this lineage's own standing convention (every prior round in this bug's history records an equivalent `mr_verify.py` PASS against the real transcript, not a self-attestation).
- **REVIEW_IN_FLIGHT.md**: `current_claim` was already `IN_FLIGHT` at this session's start, claimed by a watchdog at `2026-10-04T02:04:17.462865+00:00` for session `veyro-cap008-r16-assurance-20261004` (`c58baf67-c73e-4bb2-8789-fc236e829c26`), expecting subagent `veyro-security-reviewer` (Opus) — an exact match for this dispatch. No duplicate claim was written. Per the file's own protocol ("clear only after result, model attestation and durable recording"), this report constitutes that recording; the claim is cleared below.

## Verdict

> ## **BLOCKED — `review_status` stays `QUALIFIED`; do NOT restore `APPROVED` yet**
> **P0 = 0 · P1 = 0 · P2 = 2 · P3 = 4**

The reviewer found R16-5 **accurately and completely corrected, verified by
execution of the actual validator logic** (not by trusting the claim).
R16-3 is corrected in **four of the five locations round 16 named** — the
fifth, `BUG-051`'s own "Root-cause fix" section (lines 150–152), still
asserts the exact mechanism round 16 disproved by execution ("matching what
`--rm` already does on the happy path"), inside the very record that
declares the correction complete and closes the bug on that basis.

Nothing technical is outstanding. The reviewer characterizes the remaining
gap as one sentence plus one set of registry field-accuracy corrections,
and supplies the exact replacement text and field values so that, once
applied, `APPROVED` may be restored with no further review of substance
and no new drill.

## Findings (reviewer's severity convention, matching this lineage's own)

| ID | Sev | Finding | Location | Blocks `APPROVED`? |
|---|---|---|---|---|
| **R17-1** | **P2** | `BUG-051` §3 "Root-cause fix" (lines 150–152) still states `-v` merely "match[es] what `--rm` already does on the happy path" — the exact error-path/happy-path framing round 16 §14.2 disproved by execution. Self-contradicts the same file's own corrected "defect" section 100 lines above, and the file's `status:` field closes BUG-051 on the false premise that this correction was complete in all locations. | `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-051-postgres-harness-anonymous-volume-leak.md:150-152` | **Yes** |
| **R17-2** | **P2** | CAP-008's registry row carries a populated `approved_by`/`approved_date` (the superseded 2026-10-02 approval) and `last_reviewed_at: 2026-10-02` while `review_status` reads "QUALIFIED, not APPROVED" — a mismatch `CAPABILITY_POLICY.md` itself calls "a defect to fix, not a state to leave standing." Also causes `validate_capabilities.py` check 4 to pass vacuously on a non-approved row. | `knowledge/00-System/CAPABILITY_REGISTRY.md:25` (columns 8–12) | Cured automatically if `APPROVED` is restored per §10 below; otherwise must be fixed independently |
| R17-3 | P3 | Stale `postgres.py:189` line-number citation in 3 records; teardown call is now at line 202 | `CAPABILITY_REGISTRY.md:25`, `BUG-051:143`, `VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md:90` | No |
| R17-4 | P3 | `validate_capabilities.py`'s own comment overclaims "generalized to every module… needs no further code change" — `MANIFESTS` is a hardcoded 2-element list; a future MOD-002 manifest would be silently unread unless the list is extended (recreating R16-5's exact gap class). No live gap today (only 2 module manifests exist, both listed). | `knowledge/00-System/validate_capabilities.py:76-81` | No |
| R17-5 | P3 | Regression test retains name `test_error_path_teardown_removes_the_anonymous_volume` for an unconditional (not error-path) mechanism. Disclosed in 3 places; docstring already corrected. Optional rename. | `backend/tests/unit/test_harness_postgres_fail_closed.py:330` | No |
| R17-6 | P3 | CAP-008's registry `evidence` column omits `CAP-008/VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md` (the stage-9 material-change record for the very correction the row describes); no dedicated `capability-evidence/CAP-008/` record yet exists for round 16 §18's re-review or this one (round 16 §18.6 already recommended this). | `CAPABILITY_REGISTRY.md:25` evidence column; `knowledge/05-QA/capability-evidence/CAP-008/` | No |

**Positively confirmed by the reviewer (independent, by execution/direct reading, not by trusting any prior record):**

- R16-5 is genuinely fixed: `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` registers CAP-008 with a `capability_id` key the validator's own regex matches; `validate_capabilities.py`'s `MANIFESTS` list and `main()` were read directly and confirmed to parse both module manifests; the `"approved" in review_status.lower()` substring bypass was confirmed via `git diff` to be replaced with an anchored `^\*{0,2}\s*APPROVED\b` regex in both `validate_capabilities.py` and `tools/validate_capability_manifest.py`, and the reviewer independently probed the new regex against six crafted strings (including the registry's actual current cell text) confirming it correctly rejects "QUALIFIED, not APPROVED" and correctly accepts a properly-written `APPROVED` cell.
- Running the actual (read-only) validators: `validate_capabilities.py` → **FAIL, 1 error** (`BLOCKED: CAPABILITY_NOT_APPROVED` on CAP-008 — the intended, policy-correct state); `tools/validate_capability_manifest.py` against MOD-001's manifest → same single FAIL; `capability_drift_check.py` → **PASS, no drift**, and the reviewer additionally confirmed byte-identical `version`/`content_hash` between the registry's live row and its line-270 snapshot row (so restoring `APPROVED` will not trip the drift gate).
- `backend/tests/harness/postgres.py` read directly: the `-v` fix is live at line 202; the teardown comment (189–201) and the `except RuntimeError` comment (203–207) both now state the corrected, unconditional mechanism accurately. R16-4 item 1 (the false "`--rm` also reaps it" justification) is incidentally closed as a result.
- `backend/tests/unit/test_harness_postgres_fail_closed.py`'s docstring and assertion message for the BUG-051 regression test both state the corrected mechanism accurately.
- `CAPABILITY_REGISTRY.md`'s CAP-008 `scope` field itself (the required supply-chain field R16-3 was about) is accurate, self-citing its own prior error rather than silently rewriting it.
- `VOLUME_LEAK_SCOPE_CORRECTION_2026-10-04.md` is fully corrected, including the §18.4-flagged "remains usable" conflict.
- `MOD-001/CAPABILITIES.md` names CAP-008 and accurately states QUALIFIED-not-APPROVED and its usability consequence.
- No file was mutated, no Docker/Colima command was run, no live qualification drill was re-run, `run_regression.py` was not executed (its own code writes a run-record file on every invocation; the reviewer read the most recent existing record instead). `git rev-parse HEAD` unchanged (`b8edb2629dc359fcbd2aa575349ba6ce2899df9d`) before and after the subagent's work.
- No real member data, no credential, no spend, no owner-reserved restriction approached.

## Exact remediation and registry field values (reviewer's recommendation — not applied by this review)

**R17-1 fix** — replace `BUG-051` lines 150–152 with:

> `-v` removes the container's anonymous volume(s) along with the container on this teardown call. Per the corrected "defect" section above, this call is the *only* teardown route and it runs on every invocation — `--rm` never fires, because the container never exits on its own, so there is no separate happy-path cleanup for this to "match."

**R17-2 / full `APPROVED` restoration** — once R17-1 lands, the reviewer's recommended field values for `CAPABILITY_REGISTRY.md`'s CAP-008 row (line 25):

| column | recommended value |
|---|---|
| `review_status` | `**APPROVED (2026-10-04, third independent fresh-context Opus capability-security review, P0=0/P1=0/P2=0-blocking)**` + explanatory text citing round 16 §14–§18 plus this review, noting no new drill was required, and preserving prior history in place (see full text in the reviewer's report, reproduced in this session's transcript) |
| `qualified_by` | Sonnet (claude-sonnet-5), retained routine-implementation session — 2026-10-04 stage 4-5 re-run |
| `qualified_date` | 2026-10-04 |
| `approved_by` | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, 2026-10-04 — this review; `mr_verify.py` PASS 70/70 `claude-opus-5` as recorded above) |
| `approved_date` | 2026-10-04 |
| `last_reviewed_at` | 2026-10-04 |
| `next_review_due` | 2026-12-31 — unchanged, deliberately not pushed out (R15-5/R12-4's owner disposition is due by this date) |

**Caution the reviewer flagged explicitly:** `review_status` must begin with exactly `**APPROVED` (two asterisks, no third) or the anchored `is_approved()` regex in both validators will reject it and the gate will stay red despite the cell reading as approved to a human. Whoever applies this must re-run `validate_capabilities.py`, `tools/validate_capability_manifest.py --manifest knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`, and `capability_drift_check.py` (with Python ≥3.10, e.g. `/opt/homebrew/bin/python3.13`) after editing, and confirm the first two flip to PASS and the third stays PASS.

## What this review did not do (by design — policy separation)

- Did not edit `CAPABILITY_REGISTRY.md`, `SCENARIOS.md`, any module `STATUS.md`, `BUG-051`, or any other governed file.
- Did not promote SCN-MOD001-132 or SCN-MOD001-133.
- Did not close, reopen, or otherwise edit BUG-050 or BUG-051.
- Did not commit or push.
- Did not run any Docker/Colima command, touch any container or volume, or re-run any live CAP-008/Postgres qualification drill.
- Did not run `run_regression.py` (it writes a run-record file as a side effect of invocation).

## Next legally allowed action

Apply R17-1's one-sentence correction in `BUG-051`, then write the §10 field values into `CAPABILITY_REGISTRY.md`'s CAP-008 row (an orchestrator or routine-implementation action, not requiring a further Opus review of substance per this report's own finding that nothing technical is outstanding), then re-run the three named validators to confirm the gate flips green, then SCN-MOD001-132 may be promoted with no new drill. R17-3 through R17-6 are non-blocking hygiene, recordable at the same time or later. R15-5/R12-4's owner disposition remains separately due by 2026-12-31, untouched by this review.

## REVIEW_IN_FLIGHT.md claim — cleared

Per the file's own protocol ("clear only after result, model attestation and durable recording"), the `IN_FLIGHT` claim for this dispatch (`veyro-cap008-r16-assurance-20261004` / `c58baf67-c73e-4bb2-8789-fc236e829c26`) is cleared as part of this recording — see `REVIEW_IN_FLIGHT.md`'s updated `current_claim` field, dated 2026-10-04, pointing at this report.
