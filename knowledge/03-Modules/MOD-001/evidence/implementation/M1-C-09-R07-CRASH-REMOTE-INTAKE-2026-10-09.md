---
doc: M1-C-09-R07-CRASH-REMOTE-INTAKE
status: IMPLEMENTED — LOCAL VERIFICATION ONLY, NOT INDEPENDENTLY REVIEWED, NO SCENARIO PROMOTION
module: MOD-001
requirement: GOV-01-R07
scenario_anchor: SCN-MOD001-117 (status UNCHANGED — still NOT EXECUTED)
subgoal: M1-C-09-R07-CRASH-REMOTE-INTAKE
operation_id: 37cca86f-be58-4f6b-b635-2d3a96591de6
execution_role: ARCHITECTURE_CRITICAL
agent_model: claude-opus-5
date: 2026-10-09
base_commit: e481b814a80923849dddfe7a49319112aae7b023
---

# M1-C-09 — GOV-01-R07 crash-report intake and rollout-only remote config

The remaining mandatory GOV-01-R07 companion boundary: `SCN-MOD001-117`(a),
(b) and (c), built as real executable code against the already-existing
`backend/app/version_negotiation.py` enforcement contract. Bounded to the
two artifacts named below plus this record; nothing else was touched.

## 1. Governing anchors actually read this session

Read directly this session, not from a secondhand citation:

| Source | What was read |
|---|---|
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md` lines 405-498 | GOV-01-R07 in full, including its security-implications text ("must not be triggerable without the equivalent of an authorized release decision") and its crash-monitoring / remote-config IN-scope integration points. |
| `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §12 (lines 711-880) | The `crash_remote_config_intake.py` specification verbatim (crash ingestion "recorded/surfaced, not silently dropped"; remote-config fetch "rollout-percentage changes only … cannot itself bypass `version_negotiation.py`'s kill-switch block"; "real, executable synthetic endpoints … not a markdown interface description"), plus §12's own ADR-004 obligation (versioned + RFC 7807) on this exact file. |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md` lines 2470-2493 | `SCN-MOD001-117`(a)/(b)/(c), its three expected outcomes, and its explicit "negative/failure behavior IS part (c)'s own subject" clause. |
| `backend/app/version_negotiation.py` (all 495 lines) | The existing signed-decision enforcement being reused: `negotiate`, `parse_release_decision`, `ReleaseAuthorizationVerifier`, `HmacSha256Verifier`, `ProblemDetails`, and the unauthorized problem kind/detail. |
| `mobile/RELEASE_POLICY.md` (all 182 lines) | §2 (three dispositions, blast radius), §4 (authorization and its disclosed HMAC-symmetry limit), §5 ("remote config controls rollout, never the contract", which names `SCN-MOD001-117`(b) as the companion check this slice owes). |
| `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` | Backend profile `ACTIVATED` (bounded, ADR-005 Decision 2) with `path: backend/**` recorded; CAP-010 (ruff) bounds. |
| `knowledge/03-Modules/MOD-001/evidence/implementation/M1-C-09-R07-VERSION-NEGOTIATION-2026-10-09.md` | The sibling slice's own limits, so this record does not re-claim them — in particular its §6.4, which states this file did not exist and that parts (a)/(b)/(c) were owed. |
| `.claude/rules/backend/{architecture,api,performance,database,concurrency}.md`, `.claude/rules/infra/{secrets,release}.md`, `.claude/rules/global/owner-reserved-restrictions.md` | Binding controls for `backend/**/*.py`. |

Baseline integrity verified before any action:
`backend/.venv/bin/python knowledge/00-System/verify_baselines.py` →
**PASS, 4 of 4** governing baselines hash-match `PROJECT_INDEX.md`.

## 2. Artifacts added (2 files, both new, nothing modified)

| Path | Lines | SHA-256 |
|---|---|---|
| `backend/app/crash_remote_config_intake.py` | 1006 | `4ed9bd91be640a5d95c088bbc2425b69975f69f7a4aad6d3e761b2865845216f` |
| `backend/tests/unit/test_crash_remote_config_intake.py` | 852 | `22c2f69911015207dd9b6867b4218477f02fff66b2e4c1325d46509bc8396381` |

`git status --porcelain` confirms both are untracked (`??`) — this slice
does not commit. **No existing file was modified**, including
`backend/app/version_negotiation.py`: the reuse is by import only. The
pre-existing working-tree modifications in this session's opening git
status are not this slice's and were not touched.

Surface-profile gate (TSD §24.1 gate 7) pre-check: `backend/**` is
`ACTIVATED` for the Backend profile in `module-capabilities.yaml`, so
neither path is a `SURFACE_PROFILE_NOT_ACTIVATED` or unknown-surface case.
The gate itself was **not executed** against this change (see §7).

## 3. What the code actually does

Three entry points, one per `SCN-MOD001-117` part, over three
caller-constructed objects (`IntakeJournal`, `CrashReportIntake`,
`RolloutConfigStore`). The module holds **no module-level mutable state**
(asserted by a test), binds no network, opens no socket, reads no
environment variable/file/database, and emits no log line.

**Versioned + RFC 7807** per §12's ADR-004 obligation:
`INTAKE_API_VERSION = "v1"` / `SUPPORTED_INTAKE_API_VERSIONS`, and every
failure returns a `ProblemDetails` (`application/problem+json`, four RFC
7807 members) under this surface's own
`https://veyro.invalid/problems/crash-remote-config-intake/` namespace —
RFC 2606 `.invalid`, so no real Veyro domain is committed to.

### (a) Crash-report intake

`CrashReportIntake.record(api_version, payload) -> ProblemDetails | CrashReportReceipt`.
A submission always produces one of exactly two visible results, plus a
journal entry — there is no code path that accepts a submission and
returns nothing:

- **Accepted** → a receipt (`report_id`, `sequence`, `replayed=False`), the
  report in `intake.recorded`, groupable via
  `reports_with_fingerprint()`, and an `EntryOutcome.RECORDED` journal
  entry.
- **Rejected** → an RFC 7807 problem *and* an `EntryOutcome.REJECTED`
  journal entry.
- **Resubmitted `report_id`** → the original receipt with
  `replayed=True`, recorded exactly once, and an `EntryOutcome.REPLAYED`
  entry, so a recognized duplicate is still visibly handled rather than
  discarded.

Closed 5-field contract (`report_id`, `app_version`, `platform`,
`occurred_at`, `fingerprint`): a missing *or* unrecognized field, a
duplicated JSON key, a non-canonical version, a platform outside
`android`/`ios`, a naive or non-UTC timestamp, a non-64-hex fingerprint, an
oversized (>4096-byte) body, or a non-object body is rejected.
`app_version` is parsed by `version_negotiation.AppVersion`, not a second
parser.

**No free text, so no PII channel.** The contract carries no stack trace,
log excerpt, breadcrumb, device identifier, or user field — only an opaque
client-computed digest, which is all crash grouping needs. Problem
`detail` strings are fixed authored text; unrecognized fields are reported
as a *count*, never echoed (asserted by a test).

**Capacity is refused, never silently absorbed.** Both the recorded-report
bound and the append-only journal bound refuse the *new* write (`503
intake-capacity-exhausted`) rather than evicting an existing record, and
the journal counts refused appends (`refused_appends`) so even a failure it
cannot record stays visible. The journal append happens *before* the
report is stored, so a report is never recorded unaudited.

### (b) Rollout-only remote config

`RolloutConfigStore.publish/fetch` over a closed 2-field document
(`config_version`, `rollout_percentage` 0-100). It is deliberately not a
general key/value config surface — there is no channel a release flag
could be smuggled through. A payload carrying any release-control field
name (`kill_switch`, `forced_update_required`, `minimum_supported_version`,
`decision_id`, …) is refused as `422 rollout-config-field-not-permitted`,
classified distinctly from a generic malformed payload so the *attempt* is
legible in the journal. A non-advancing `config_version` is refused (`409`)
so an old document cannot silently re-take effect.

`resolve_client_bootstrap(request, verifier, rollout_store)` is the
companion check as code rather than a comment. Order is the control:

1. `negotiate(request, verifier)` decides. The rollout store is **not**
   passed to it and cannot be — `NegotiationRequest` has no field for it
   (asserted by a field-set test) — so no rollout value is in scope when
   the disposition is formed.
2. The rollout document is read afterwards and attached unchanged.

A negotiation failure returns before any rollout read at all (asserted
with a store stub that fails the test if fetched).

### (c) Kill-switch activation attempt

`request_kill_switch_activation(attempt, verifier, journal)`. Every
authorization step is `version_negotiation`'s, in `negotiate`'s own order —
the injected verifier over the exact received bytes first, then
`parse_release_decision`'s closed contract. This function adds **no
verification, no key, no signing method, and no kill-switch state**:

- `signed_decision is None` **or** a non-matching signature takes the same
  branch and returns `version_negotiation`'s own
  `401 release-decision-unauthorized` body, whose detail text states that a
  forced update or kill switch can only be activated by an authorized
  release decision. A test asserts the returned body is **equal to the body
  `negotiate` itself returns**, so the two surfaces give a caller no
  differing oracle.
- The attempt has **no field** through which it could assert its own
  forced-update flag or reason (asserted by a field-set test);
  `requested_by` is an audit label that is recorded, never consulted for
  authorization, and never echoed into a problem body.
- An authorized decision that requires no forced update is **not promoted**
  into a kill switch (`422 kill-switch-not-authorized-by-decision`).
- An authorized-but-unreserved reason and an authorized-but-malformed
  payload are refused by the *shared* contract, returning
  `version_negotiation`'s own problem types.
- Success returns a `KillSwitchActivationRecord` **derived** entirely from
  the signed decision. Nothing stores it and no negotiation consults it:
  holding it confers nothing, and the authoritative block is still produced
  by `negotiate` when the same signed decision is presented with a client
  version.

## 4. `SCN-MOD001-117` step-by-step correspondence (local run, not a promotion)

| Scenario step | Expected | Test(s) | Result |
|---|---|---|---|
| (a) fabricated crash report received by the integration point | recorded/surfaced, not silently dropped | `test_a_fabricated_report_is_accepted_recorded_and_surfaced`, `test_reports_are_groupable_by_fingerprint`, `test_a_resubmitted_report_id_is_recorded_once_and_visibly_replayed` | receipt `sequence=1`; report in `intake.recorded`; journal entry `{"kind": "crash_report", "outcome": "recorded", …}` asserted field-by-field |
| (a) negative — nothing is dropped silently | refusal is itself surfaced | `test_every_malformed_shape_is_refused_and_journaled` (17 sub-cases), `test_an_unsupported_intake_api_version_is_refused_and_journaled`, `test_recorded_report_capacity_is_refused_rather_than_overwritten`, `test_a_full_journal_refuses_the_report_rather_than_recording_it_unaudited` | every case: RFC 7807 problem **and** a journal entry; `recorded_count` stays 0 |
| (b) remote-config fetch returns a rollout-percentage change and is read | applied and readable | `test_a_published_rollout_percentage_is_readable`, `test_an_advancing_config_version_replaces_the_previous_rollout` | `RolloutConfig(config_version=1, rollout_percentage=25)` published, fetched, journaled |
| (b) **companion check** — a remote-config change alone does NOT bypass 115's kill-switch block | block still holds | `test_the_block_holds_at_every_rollout_percentage` (0/1/50/99/100), `test_an_absent_rollout_document_does_not_change_the_disposition` | at every percentage: `rollout` reads back the published value **and** `negotiation == negotiate(...)` reference outcome, `BLOCKED_FORCED_UPDATE`, `blocked=True`, reason `SECURITY` |
| (b) remote config cannot repair the contract | release-control field refused | `test_a_release_control_field_in_remote_config_is_refused` (8 field names) | `422 rollout-config-field-not-permitted`; `store.current` unchanged (`None`) |
| (c) activation attempted via a path other than an authorized release decision | denied, citing missing authorization | `test_an_attempt_with_no_authorization_at_all_is_denied`, `test_an_empty_signature_is_denied`, `test_a_signature_from_another_key_is_denied`, `test_a_payload_swapped_under_a_genuine_signature_is_denied`, `test_a_requester_label_cannot_substitute_for_authorization` (4 labels) | `401 release-decision-unauthorized`, detail cites the authorized-release-decision requirement; `EntryOutcome.DENIED` journaled |
| (c) no second oracle | same denial as the negotiation surface | `test_the_denial_body_is_identical_to_the_negotiation_surface_denial` | `to_body()` equality asserted |
| (c) no parallel kill-switch state | a record confers no block | `test_an_activation_record_confers_no_block_of_its_own` | after an authorized activation, a client at the minimum is still `ALLOWED` and a separate optional-update decision still yields `ALLOWED_WITH_UPDATE_PROMPT` |

This table is a **local implementation run by the implementing session**,
which is *not* scenario execution evidence (§7.1).

## 5. Checks actually run

All commands run locally on this macOS arm64 host.

| Check | Command | Result |
|---|---|---|
| Baseline integrity | `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | **PASS** — 4/4 match |
| Focused stdlib unit tests | `cd backend && .venv/bin/python -m unittest tests.unit.test_crash_remote_config_intake` | **OK — 40 tests, 0 failures, 0 errors** |
| Sibling-suite regression | `cd backend && .venv/bin/python -m unittest tests.unit.test_version_negotiation` | **OK — 33 tests**, unchanged by this slice |
| Ruff lint | `backend/.venv/bin/ruff check <both new files>` | **All checks passed** (exit 0) |
| Ruff format (read-only) | `backend/.venv/bin/ruff format --check <both new files>` | **2 files already formatted** (exit 0) |
| Byte-compile | `backend/.venv/bin/python -m py_compile <both new files>` | exit 0 |
| Whitespace/conflict markers | `git diff --check`, re-run with both paths `git add -N` (then `git reset` to restore untracked state) | exit 0, no output, both times |

Tool identities: `backend/.venv/bin/python` 3.14.5, `backend/.venv/bin/ruff`
0.16.9 (the version CAP-010 registers).

**CAP-010 compliance.** Only bound (b) was exercised: local, read-only,
non-gate `ruff check` / `ruff format --check` over Veyro Python under the
committed config. **`ruff format` was never run in write mode**, and
`--fix`, `--unsafe-fixes`, `--add-noqa` and `--select S` were never used.
The lint/formatter findings (one `I001` import-order plus five `TRY004`
findings in the source, one `I001` in the tests, and seven
line-wrapping findings across the two files over two read-only
`format --check` runs) were read from the output and fixed **by hand**:
import-order by moving the aliased import, `TRY004` by introducing a typed
`MalformedIntakePayload(ValueError)` — which is also the idiom
`version_negotiation.MalformedReleaseDecision` already uses — and the
wrapping by applying the printed diff manually, then re-verifying with
`--check`. No gate, required-status check, or scenario relies on CAP-010
here.

## 6. Rule-by-rule position (binding `.claude/rules/` controls)

- **`infra/secrets.md` control 1** — no credential-shaped value. The only
  key material is `EXAMPLE_NOT_A_REAL_KEY-*` in the test, and the module
  has no key, no default key, and no key-loading path; the verifier is
  injected.
- **`backend/performance.md` controls 4-6** — the module emits no log
  statement at all, so no secret/PII-shaped value can appear in one;
  `JournalEntry.to_record()` is the field-keyed structured shape an
  observability sink would consume. All data is synthetic.
- **`backend/concurrency.md` control 5** — the journal is append-only and
  never mutated in place, so the version-column requirement does not
  apply; there is no table and no migration in this slice at all.
- **`backend/architecture.md`** — the file sits at `backend/app/`, the same
  cross-cutting level as `version_negotiation.py`; it adds no
  `app/modules/<domain>/` content and performs no cross-domain import.
- **`backend/api.md`** — stated as **owed, not satisfied**: see §7.3. This
  slice adds no route handler, so controls 1-6 and the control-8
  idempotency contract bind whichever slice adds one.
- **`infra/release.md` control 1** — nothing here is a rollback trigger;
  the rollout document is read-only data and the activation path is
  authorization-gated, not a convenience endpoint.
- **`global/owner-reserved-restrictions.md`** — see §8.

## 7. Limits — what this slice does NOT establish

Stated plainly, because each is a thing a reader could otherwise assume:

1. **No scenario is promoted.** `SCN-MOD001-117` remains **NOT EXECUTED**
   in `SCENARIOS.md`; its status was not edited. Its routing is
   `veyro-security-reviewer`/Opus in a fresh context, which is not this
   session. `SCN-MOD001-119`(a) likewise has not run, so **ADR-004
   conformance stays PLANNED, not proven**, exactly as
   `ADR_CONFORMANCE.md` records — this slice satisfies the versioned/RFC
   7807 obligation at the *contract* level only.
2. **No independent review.** No reviewer was dispatched, no
   `REVIEW_IN_FLIGHT.md` claim was written, and no review entitlement was
   consumed. This code has had zero fresh-context review.
3. **No HTTP endpoint exists.** §12 calls these "intake endpoints"; what
   exists is the in-process integration *point*. There is no FastAPI
   route, no router, no `app/main.py` wiring, no Pydantic request/response
   model, and no declared `action`/`resource`/`scope` permission triple —
   all of which `.claude/rules/backend/api.md` controls 1-5 require of a
   route handler, and all of which remain owed by whichever slice adds the
   route. Pydantic is still not a backend dependency (`psycopg` is the
   only one), so the closed-field validation is hand-written rather than a
   `ConfigDict(extra="forbid")` model.
4. **No persistence.** The journal, the recorded reports, and the current
   rollout document are in-memory objects owned by the caller. Nothing
   survives a process restart, there is no table, no migration, no RLS
   policy, and no `tenant_id` — so this slice proves nothing about
   tenant isolation or durable crash retention. A real crash store would
   be a tenant-owned table subject to
   `.claude/rules/backend/database.md` in full.
5. **The crash contract is a digest, not an SDK payload.** A real crash
   SDK sends stack traces, breadcrumbs, device metadata and session
   identifiers. This contract deliberately accepts none of those — which
   is what makes it PII-free, but also means the privacy/redaction design
   for a *real* crash payload (and MOD-006's client-side SDK choice) is
   untouched and still owed.
6. **Replay handling is not the 6-element idempotency contract.** The
   `report_id` replay check returns the original receipt and records once;
   it is not `.claude/rules/backend/api.md` control 8's scoped key tuple,
   24-hour retention window, stored request hash, `409
   IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD` response, `command_id`
   propagation, or provider-derivative field. A resubmission under the
   same `report_id` with a *different* body currently returns the original
   receipt rather than a 409 — a deliberate, disclosed simplification for
   an in-memory synthetic intake, not a satisfied contract.
7. **HMAC symmetry is unchanged and still disclosed.** This module adds no
   signing method, but it reuses the symmetric
   `HmacSha256Verifier`: a process holding the verification key could
   compute signatures. **No production signer/verifier separation is
   claimed or established.** Who holds the signing key and in what custody
   remains undecided in the governing baseline, and a real signing
   authority (managed KMS, code-signing CA) is DC-16 owner-reserved spend
   per GOV-01-R07's own "Owner/external gates" row.
8. **One private cross-module import, deliberately.**
   `version_negotiation._UNAUTHORIZED_DETAIL` is imported so the denial
   text has exactly one source of truth; restating it would create a
   second. A test asserts body equality between the two surfaces, so the
   coupling is checked rather than assumed. A reviewer may prefer that
   constant be made public in `version_negotiation.py` instead — this
   slice was instructed not to modify that file, so it did not.
9. **No CI wiring and no gate execution.** No workflow, no gate row, no
   required-status check, and no architecture-gate run (including gate 7)
   was executed against this change. The §2 gate-7 statement is a read of
   `module-capabilities.yaml`, not a tool result.
10. **The rest of GOV-01-R07 is still open.**
    `mobile/TOOLCHAIN_MATRIX.md` still does not exist, so the pinned
    toolchain matrix, its `whitelabel_release_metadata` /
    `shared_module_version` fields, `tools/validate_toolchain_matrix.py`,
    the isolated-PR qualification gate, the capability-adapter smoke-test
    stage, the CI runner-assignment convention, the common-code
    dual-platform regression path filter, and
    `SCN-MOD001-127`/`128`/`129` are all untouched by this slice.
11. **The Veyro pytest suite was not run**, per this operation's explicit
    instruction. The tests are `unittest.TestCase`-based (stdlib-runnable
    and still pytest-collectable later), but their behaviour under
    `tools/run_scoped_pytest.py` is unverified. No mypy run either — only
    `ruff check`, `ruff format --check`, `py_compile` and the focused
    tests were required and run. (Note for a later mypy pass: a
    `datetime.utcoffset()` call in the tests is used without an explicit
    `None` guard, which strict mode would flag.)
12. **Routing note, disclosed not resolved.** ADR-005 Decision 1 registers
    three critical slices for MOD-001 and GOV-01-R07 is not among them;
    Decision 2 routes bounded `backend/**` work to
    `veyro-backend-engineer` (Sonnet). This slice was executed directly by
    an `ARCHITECTURE_CRITICAL` Opus worker on the dispatching runner's
    instruction, recorded in the operation budget with
    `executionRole: ARCHITECTURE_CRITICAL`, `agentModel: claude-opus-5`.
    Whether that constitutes a routing deviation requiring an ADR
    amendment is a governance judgment this session does not make for
    itself; it is flagged here for the orchestrating session, as the
    sibling slice's record also did.

## 8. Owner-reserved restrictions

No paid service and no spend. No real member data — every crash report,
fingerprint, release decision, rollout document and key is synthetic, and
the keys are explicitly labeled `EXAMPLE_NOT_A_REAL_KEY-*` per
`.claude/rules/infra/secrets.md` control 1. No deploy or promotion to
Production; no store action; no real crash backend or remote-config
backend was contacted, and the module cannot contact one (no network code
exists in it). No material product, pricing, business, architecture or
scope change: the contracts implement what TSD §24.3,
`REQUIREMENTS.md` GOV-01-R07 and `IMPLEMENTATION.md` §12 already state,
and decline to invent what they leave open (§7.7).

## 9. Operation budget checkpoint

Recorded after the durable code change:

```
operation_budget.py checkpoint --operation-id 37cca86f-be58-4f6b-b635-2d3a96591de6 \
  --kind code --file backend/app/crash_remote_config_intake.py \
  --subgoal M1-C-09-R07-CRASH-REMOTE-INTAKE
```

Accepted: `currentSubgoal: M1-C-09-R07-CRASH-REMOTE-INTAKE`,
`filesMateriallyChanged: ["backend/app/crash_remote_config_intake.py"]`,
`status: RUNNING`, `executionRole: ARCHITECTURE_CRITICAL`,
`agentModel: claude-opus-5`.

## 10. Remaining integrated boundary for GOV-01-R07/`SCN-MOD001-117`

What a following session still owes for this scenario specifically, beyond
§7's general limits: an HTTP binding (route + Pydantic models + permission
triple + idempotency contract) if the scenario's reviewer reads "endpoint"
as requiring one; durable persistence for recorded crash reports under
`.claude/rules/backend/database.md`'s tenant/RLS controls; and the fresh-context
`veyro-security-reviewer`/Opus execution of `SCN-MOD001-117` itself, which
is the only thing that can move it off NOT EXECUTED.
