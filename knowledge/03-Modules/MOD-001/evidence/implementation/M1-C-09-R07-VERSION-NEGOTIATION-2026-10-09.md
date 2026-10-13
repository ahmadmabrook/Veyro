---
doc: M1-C-09-R07-VERSION-NEGOTIATION
status: IMPLEMENTED — LOCAL VERIFICATION ONLY, NOT INDEPENDENTLY REVIEWED, NO SCENARIO PROMOTION
module: MOD-001
requirement: GOV-01-R07
scenario_anchor: SCN-MOD001-115 (status UNCHANGED — still NOT EXECUTED)
subgoal: M1-C-09-R07-VERSION-NEGOTIATION
operation_id: 018dd31a-b79f-4102-af5f-3817d2f85e0e
execution_role: ARCHITECTURE_CRITICAL
agent_model: claude-opus-5
date: 2026-10-09
base_commit: e481b814a80923849dddfe7a49319112aae7b023
---

# M1-C-09 — GOV-01-R07 backend version negotiation and release policy

Minimum implementation of GOV-01-R07's version-negotiation enforcement and
its policy document. Bounded to the three artifacts named below; nothing
else was touched.

## 1. Governing anchors actually read this session

Read directly, not from a secondhand citation:

| Source | What was read |
|---|---|
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md` lines 413-498 | GOV-01-R07 in full, including its security-implications text: forced-update/kill-switch "must not be triggerable without the equivalent of an authorized release decision." |
| `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` §12 (lines 711-874) | The `mobile/RELEASE_POLICY.md` / `backend/app/version_negotiation.py` policy-vs-enforcement split, and §12's own ADR-004 obligation (versioned + RFC 7807) on this exact file. |
| `knowledge/03-Modules/MOD-001/SCENARIOS.md` lines 2446-2468 | `SCN-MOD001-115`'s three negotiation outcomes and its named failure case. Lines 2470-2493 (`SCN-MOD001-117`) read to establish what is *not* in this slice. |
| `knowledge/00-System/TSD_MIRROR.md` lines 11670-11700 | TSD §24.3 in full. |
| `knowledge/03-Modules/MOD-001/ADR_CONFORMANCE.md` | ADR-004's obligation on this file, and its namespace disambiguation (EIP/Appendix-I ADR-004, *not* `knowledge/04-Decisions/ADR-004-orchestrating-session-model-tier.md`, which was also read and confirmed unrelated). |
| `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` | Backend profile `ACTIVATED`; `mobile/*.md` recorded `profile: null`, naming `RELEASE_POLICY.md` explicitly; CAP-010 (ruff) bounds. |
| `.claude/rules/backend/{architecture,api,performance,database,concurrency}.md`, `.claude/rules/infra/{secrets,release}.md`, `.claude/rules/global/owner-reserved-restrictions.md` | Binding controls for `backend/**/*.py`. |

Baseline integrity verified before any action:
`backend/.venv/bin/python knowledge/00-System/verify_baselines.py` →
**PASS, 4 of 4** governing baselines hash-match `PROJECT_INDEX.md`.

## 2. Artifacts added (3 files, all new, nothing modified)

| Path | Lines | SHA-256 |
|---|---|---|
| `backend/app/version_negotiation.py` | 493 | `0f3757f307648c0ae06225d3c04e939914b9619124392375eec4e3676127588e` |
| `backend/tests/unit/test_version_negotiation.py` | 413 | `85dbe7b4f0210dde673dffd5b12c0f6eab614e557a667564a4ae56d607e9e7e9` |
| `mobile/RELEASE_POLICY.md` | 181 | `b5beea6c28010de82aa31c2e86dbe25041960cd275e7819694f340422c61a48f` |

`git status --porcelain` confirms all three are untracked (`??`) — this
slice does not commit. No existing file was modified; the pre-existing
working-tree modifications listed in this session's opening git status are
not this slice's and were not touched.

Surface-profile gate (TSD §24.1 gate 7) pre-check:
`backend/**` is `ACTIVATED` for the Backend profile and
`mobile/*.md` is a recorded known-infrastructure path (`profile: null`)
that names `RELEASE_POLICY.md` by name, so neither path is a
`SURFACE_PROFILE_NOT_ACTIVATED` or unknown-surface case. The gate itself
was **not executed** against this change (see §6).

## 3. What the enforcement contract actually does

`negotiate(request, verifier) -> NegotiationOutcome | ProblemDetails`, a
pure decision function. Step order is itself the control:

1. **Versioned surface.** `API_VERSION = "v1"` / `SUPPORTED_API_VERSIONS`;
   an unsupported version is refused *before* authorization is consulted
   (proven by a verifier stub that fails the test if called at all).
2. **Authorization over the exact received bytes.** `SignedReleaseDecision`
   holds the raw bytes as received plus a hex HMAC-SHA256; verification
   runs over those bytes before any parsing, so no untrusted field is ever
   trusted and no canonicalization-mismatch gap exists. Failure returns
   RFC 7807 `401 release-decision-unauthorized` — **not** a downgrade to an
   optional-update prompt and **not** a default-allow.
3. **Closed decision contract.** Exactly four fields; a missing *or*
   unrecognized field, a duplicated JSON key, a non-boolean for
   `forced_update_required`, an oversized payload (>4096 bytes), or a
   non-object body is rejected.
4. **Client version**, strict canonical `MAJOR.MINOR.PATCH`.
5. **Disposition** — the three `SCN-MOD001-115` enumerates, and only those.

Security properties implemented, each with a test:

- **Verify-only interface.** There is deliberately no `sign` method.
  This does not prevent a process holding the symmetric HMAC verification
  key from computing signatures; production signer/verifier separation
  remains unproven. The test computes a synthetic signature itself.
- **Injected key, no key-loading path.** `HmacSha256Verifier(key=...)` is
  constructed by the caller. The module has no default key and reads no
  environment variable, file, or other key source, so it cannot be wired
  to a real secret by omission (`.claude/rules/infra/secrets.md` control
  1). An empty key is refused at construction.
- **Constant-time comparison** via `hmac.compare_digest`; a non-ASCII
  signature returns `False` rather than raising.
- **Forced update is a closed two-reason set** (`security`,
  `critical_incompatibility`), matching TSD §24.3's reservation. An
  authorized decision asserting a forced update with no reason or an
  unreserved reason is refused (`422`), not relaxed.
- **A forced update cannot block a client at or above the minimum** — the
  blast radius is the below-minimum population only, so a release decision
  cannot be used to block the whole fleet.
- **No oracle**: absent and non-matching authorization produce byte-identical
  problem bodies (asserted by comparing the two bodies).
- **Remote config is structurally absent.** There is no rollout/remote-config
  parameter to read, and the signed payload's field set is closed, so a
  rollout-flavoured field cannot ride along inside a decision (TSD §24.3).
  Tested: a correctly-signed payload carrying `rollout_percentage` is
  rejected, not ignored.
- **No logging at all**, so `.claude/rules/backend/performance.md` controls
  4-5 (structured logs, no secret/PII in logs) cannot be violated here; the
  RFC 7807 `detail` strings are fixed authored text that never echo
  untrusted input, a key, or a signature.

`ProblemDetails.to_body()` emits the four RFC 7807 members
(`type`/`title`/`status`/`detail`) with `content_type`
`application/problem+json`; `type` URIs use the RFC 2606 non-resolvable
`.invalid` base so no real Veyro domain is committed to by a synthetic
slice.

## 4. `SCN-MOD001-115` step-by-step correspondence (local run, not a promotion)

The scenario's three synthetic client versions, each against a minimum of
`2.0.0`:

| Scenario step | Expected | Test | Result |
|---|---|---|---|
| Within the minimum-supported range | Normal operation | `test_within_minimum_operates_normally`, `test_exactly_at_minimum_operates_normally` | `Disposition.ALLOWED`, `blocked=False` |
| Below minimum, optional-update policy only | Operates with a prompt, not blocked | `test_below_minimum_with_only_an_optional_update_operates_with_a_prompt` | `ALLOWED_WITH_UPDATE_PROMPT`, `blocked=False` |
| Below minimum, kill switch active for security/critical | Blocked, citing the forced-update requirement | `test_below_minimum_with_an_authorized_security_forced_update_is_blocked`, `..._critical_incompatibility_...` | `BLOCKED_FORCED_UPDATE` with `ForcedUpdateReason.SECURITY` / `.CRITICAL_INCOMPATIBILITY` |
| **Named failure case:** a below-minimum client NOT blocked while the kill switch is active | Must not happen | the two blocked-case tests above assert the block directly | Not reproducible by these inputs |

Synthetic negative authorization cases (GOV-01-R07's security-implications
text; the same control `SCN-MOD001-117`(c) will own end-to-end):

| Negative case | Result |
|---|---|
| Authorization absent (empty signature) | `401 release-decision-unauthorized` |
| Payload swapped under a genuinely-issued signature for a *different* decision | `401` |
| Signature tampered (one hex character flipped) | `401` |
| Signature issued under a different key | `401` |
| Non-ASCII signature | `401` (no exception) |
| Unauthorized request also carrying a malformed payload and version | `401` only — no pre-authorization input feedback |

## 5. Checks actually run

All commands run locally on this macOS arm64 host.

| Check | Command | Result |
|---|---|---|
| Baseline integrity | `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | **PASS** — 4/4 match |
| Focused stdlib unit tests | `cd backend && .venv/bin/python -m unittest tests.unit.test_version_negotiation` | **OK — 33 tests, 0 failures, 0 errors** |
| Ruff lint | `backend/.venv/bin/ruff check backend/app/version_negotiation.py backend/tests/unit/test_version_negotiation.py` | **All checks passed** (exit 0) |
| Ruff format (read-only) | `backend/.venv/bin/ruff format --check <same two files>` | **2 files already formatted** (exit 0) |
| Byte-compile | `backend/.venv/bin/python -m py_compile <same two files>` | exit 0 |
| Whitespace/conflict markers | `git diff --check` (and again with the three paths `git add -N`, then `git reset` to restore untracked state) | exit 0, no output, both times |

Tool identities: `backend/.venv/bin/python` 3.14.5, `backend/.venv/bin/ruff`
0.16.9 (the version CAP-010 registers).

**CAP-010 compliance.** Only bound (b) was exercised: local, read-only,
non-gate `ruff check` and `ruff format --check` over Veyro Python under the
committed config. **`ruff format` was never run in write mode**, and
`--fix`, `--unsafe-fixes`, `--add-noqa` and `--select S` were never used —
CAP-010 forbids all of these on Veyro files. The formatter's `--diff`
output was read and the six wrapping changes were applied **by hand** via
edits, then re-verified with `--check`. No gate, required-status check, or
scenario relies on CAP-010 here.

## 6. Limits — what this slice does NOT establish

Stated plainly, because each is a thing a reader could otherwise assume:

1. **No scenario is promoted.** `SCN-MOD001-115` remains **NOT EXECUTED**
   in `SCENARIOS.md`; its status was not edited. Its own routing is
   `veyro-security-reviewer`/Opus in a fresh context, which is not this
   session. The §4 table above is a local implementation run by the
   implementing session, which is *not* scenario execution evidence.
   `SCN-MOD001-119`(a) likewise has not run, so **ADR-004 conformance
   stays PLANNED, not proven**, exactly as `ADR_CONFORMANCE.md` records.
2. **No independent review.** No reviewer was dispatched, no
   `REVIEW_IN_FLIGHT.md` claim was written, and no review entitlement was
   consumed. This code has had zero fresh-context review.
3. **No HTTP endpoint exists.** This is a decision function, not a FastAPI
   route: no router, no network binding, no `app/main.py` wiring. The
   versioned surface and RFC 7807 bodies are satisfied at the *contract*
   level; the path/header binding, the Pydantic request/response models,
   and the `action`/`resource`/`scope` permission triple that
   `.claude/rules/backend/api.md` controls 1-5 require of a route handler
   are **not** created here and remain owed by whichever slice adds the
   route. (Those controls bind route handlers; this slice adds none.
   Pydantic is also not a current backend dependency — `psycopg` is the
   only one — so the closed-field-set validation is hand-written rather
   than a `ConfigDict(extra="forbid")` model.)
4. **`SCN-MOD001-117` is untouched.** `backend/app/crash_remote_config_intake.py`
   does not exist; crash-report intake, remote-config fetch, and the
   end-to-end "remote config alone does not bypass the kill-switch block"
   companion check are not implemented. This slice only makes remote-config
   influence *structurally impossible at this function's boundary*.
5. **`mobile/TOOLCHAIN_MATRIX.md` does not exist**, so GOV-01-R07's pinned
   toolchain matrix, its `whitelabel_release_metadata` /
   `shared_module_version` fields, `tools/validate_toolchain_matrix.py`,
   and `SCN-MOD001-127`/`128`/`129` are all still open. Creating `mobile/`
   for `RELEASE_POLICY.md` did **not** create the three
   `mobile/{shared,iosApp,androidApp}/.profile-pending` markers that
   `module-capabilities.yaml` references; those sub-directories still do
   not exist. That gap pre-dates this slice and was left alone as
   out-of-scope, not fixed silently.
6. **No CI wiring.** No workflow, no gate row, no required-status check,
   and no architecture-gate run (including gate 7) was executed against
   this change. The §2 gate-7 statement is a read of
   `module-capabilities.yaml`, not a tool result.
7. **The signing authority is undecided.** Neither TSD §24.3 nor
   `REQUIREMENTS.md` fixes who holds the release-decision signing key or
   in what custody. A real signing authority (managed KMS, code-signing
   CA) is DC-16 owner-reserved spend, which GOV-01-R07's own
   "Owner/external gates" row names. This slice therefore proves the
   control with a **synthetic key injected by a test** and leaves custody
   open rather than inventing policy. HMAC-SHA256 is a symmetric choice
   adequate for a synthetic fixture; a real deployment may need an
   asymmetric scheme so verifiers cannot sign — the injected-verifier
   `Protocol` is what makes that substitutable without changing the
   decision logic, but that substitution has not been made.
8. **No concrete minimum supported version is set anywhere.** The
   authoritative minimum travels inside each signed decision. Pinning a
   number in the policy document would create a second, unsigned source of
   truth for the one value the authorization exists to protect, and would
   be fiction while MOD-006 owns the app and no client build exists.
9. **The Veyro pytest suite was not run**, per this operation's explicit
   instruction. The tests are `unittest.TestCase`-based (so stdlib-runnable
   and still pytest-collectable later), but their behaviour under the
   project's own `tools/run_scoped_pytest.py` wrapper is unverified. No
   mypy run either — only `ruff check`, `ruff format --check`, `py_compile`
   and the focused tests were required and run.
10. **Routing note, disclosed not resolved.** ADR-005 Decision 1 registers
    three critical slices for MOD-001 and GOV-01-R07 is not among them;
    Decision 2 routes bounded `backend/**` work to
    `veyro-backend-engineer` (Sonnet). This slice was executed directly by
    an `ARCHITECTURE_CRITICAL` Opus worker on the dispatching runner's
    instruction, recorded in the operation budget with
    `executionRole: ARCHITECTURE_CRITICAL`, `agentModel: claude-opus-5`.
    Whether that constitutes a routing deviation requiring an ADR
    amendment is a governance judgment this session does not make for
    itself; it is flagged here for the orchestrating session.

## 7. Owner-reserved restrictions

No paid service and no spend. No real member data — every value is
synthetic, and the keys are explicitly labeled `EXAMPLE_NOT_A_REAL_KEY-*`
per `.claude/rules/infra/secrets.md` control 1. No deploy or promotion to
Production; no store action of any kind; no remote configuration was read
or written. No material product, pricing, business, architecture, or scope
change: the policy document restates only what TSD §24.3 and
`REQUIREMENTS.md` GOV-01-R07 already state, and explicitly declines to
invent the values they leave open (§6.7, §6.8).

## 8. Operation budget checkpoint

Recorded after the durable code change:

```
operation_budget.py checkpoint --operation-id 018dd31a-b79f-4102-af5f-3817d2f85e0e \
  --kind code --file backend/app/version_negotiation.py \
  --subgoal M1-C-09-R07-VERSION-NEGOTIATION
```

Accepted: `currentSubgoal: M1-C-09-R07-VERSION-NEGOTIATION`,
`filesMateriallyChanged: ["backend/app/version_negotiation.py"]`,
`status: RUNNING`.

## Independent parent correction and replay
Corrected a false security assertion in the new source/policy/evidence: a verify-only HMAC *interface* does not prevent a process holding the symmetric verification key from computing signatures. This local synthetic proof makes no production signer/verifier-separation claim; key custody remains unresolved and no real activation is authorized. The table hashes above are the post-correction bytes. Independent replay: `cd backend && .venv/bin/python -m unittest tests.unit.test_version_negotiation` 33/33 PASS; `.venv/bin/ruff check` and `.venv/bin/ruff format --check` on source/tests PASS; `py_compile` PASS; no Veyro pytest or CI.
