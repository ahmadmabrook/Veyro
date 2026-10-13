# M1-C-06 — CAP-009 / CAP-010 QUALIFIED-only draft registration (2026-10-09)

Status: **DRAFT REGISTERED AT `QUALIFIED`. NOT APPROVED. Independent Opus determination PENDING.**
Operation `2b91f76e-21fb-441d-bf1b-5a54c134ae48`, subgoal `M1-C-06-QUALIFIED-CAP-DRAFT`, class
`implementation`, `claude-sonnet-5-5` (configured routing). Implements step C / §7 item 3 of
`M1-C-06-CAP-ORDERING-PLAN-DECISION-2026-10-09.md`. Read for this task: `CAPABILITY_POLICY.md`,
that decision, `M1-C-06-GITLEAKS-SYNTHETIC-QUALIFICATION-2026-10-09.md`,
`M1-C-06-UPSTREAM-PROVENANCE-PINS-2026-10-09.md`.

## What changed

| File | Change |
|---|---|
| `knowledge/00-System/CAPABILITY_REGISTRY.md` | Two rows, `CAP-009` (gitleaks 8.30.1) and `CAP-010` (Ruff 0.16.9: lint/format plus `S`), inserted directly after `CAP-008`. All 15 columns present. CAP-001..CAP-008, the lifecycle prose and the version/hash snapshot table are untouched. |
| `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` | Two `capability_id` entries appended to the existing `capabilities:` list, so the mechanical validators evaluate them (the R16-5 lesson). CAP-008 entry and every other field untouched. |
| `knowledge/03-Modules/MOD-001/CAPABILITIES.md` | One appended section; no existing text edited. |
| this note | New. |

## Field values (only what was verified)

| Field | CAP-009 gitleaks | CAP-010 Ruff |
|---|---|---|
| `review_status` | `QUALIFIED — NOT APPROVED`, determination PENDING | same, separate verdict |
| `approved_by` / `approved_date` | empty | empty |
| `next_review_due` | `NOT SET` (no date invented) | `NOT SET` |
| `qualified_by` / date | Sonnet `claude-sonnet-5-5`, 2026-10-09 | same |
| version | 8.30.1 | 0.16.9 |
| pin | linux x64 asset SHA-256 `551f6fc8…2470eb` (local = upstream checksum file = release-API digest) | PyPI linux x64 wheel SHA-256 `a21713e6…bc728` (local = PyPI digest) |
| licence | MIT, upstream `LICENSE` SHA-256 `e3884b25…62ebc6` | MIT, upstream `LICENSE` SHA-256 `2597d854…1c8f18` |
| tag commit | `83d9cd68…8e` | `0be08a20…b4f1d` |
| drill | `tools/tests/test_gitleaks_qualification.py`, 6 pass | `tools/tests/test_sast_ruff_qualification.py`, 4 pass |

Drill tests re-run this turn: `10 passed in 0.29s`; `ruff 0.16.9` and `gitleaks 8.30.1` version reads
match the pins. Test file SHA-256 `45d459be…6688c` and `43af9b53…f214` are unchanged from the
earlier notes. The Ruff wheel hash is already appended to the provenance note; nothing was added there.

## Validators — expected hold versus structural error

Run with `backend/.venv/bin/python`.

| Check | Before | After |
|---|---|---|
| `knowledge/00-System/validate_capabilities.py` | PASS, 8 capabilities | **FAIL, 6 errors**, 10 ids, no duplicates |
| `tools/validate_capability_manifest.py --manifest …/MOD-001/evidence/module-capabilities.yaml` | not run before | **FAIL, 6 errors**, same set |
| `knowledge/05-QA/tools/capability_drift_check.py` | PASS | **PASS**, 10 checked; CAP-009/010 reported "not yet approved — no approval baseline" |
| `test_capability_drift_check.py` | — | 21 passed |

The 6 errors are the same for CAP-009 and CAP-010 (3 each): `CAPABILITY_NOT_APPROVED`, no named
`approved_by`, and `next_review_due` not a parseable date. **All six are the intended fail-closed hold
and one cause**: QUALIFIED rows with no independent approval and no invented due date. They are not
structural errors, evidence of which is that both rows parsed (15 cells), both ids were found in the
manifest and registry (no `CAPABILITY_UNREGISTERED`, no duplicates), no existing capability regressed,
and the drift check passed. The validators will keep failing for MOD-001 until the independent
determination returns APPROVED for both, or the manifest bindings are removed; that is by design and
is the signal that blocks any reliance.

## Not done / not claimed

- No stage 4, no APPROVED, no ACTIVE reliance. No reviewer dispatched, no `REVIEW_IN_FLIGHT.md` claim,
  no review entitlement created or consumed.
- No scanner ran on the real tree, Git index/history, or CI. The only scanner invocations were the two
  existing synthetic tests (disposable `tmp_path` fixtures) and version reads.
- Ruff has **no dedicated lint/format drill**; only `--select S` was drilled. `S` is pattern-based, not
  taint analysis, and the tree's `S`-cleanliness is unknown. The installed macOS Ruff wheel and the
  Homebrew gitleaks binary are not the pinned linux artifacts. No upstream signature or attestation
  was verified for either project.
- BUG-057 (pre-existing unregistered gitleaks `git --staged` use; unregistered ruff/pytest/mypy) is not
  filed here. The version/hash snapshot table gets no CAP-009/010 rows (it is a snapshot *at approval*).
- The manifest's `missing_capability_blockers` was reconciled after draft verification to name
  both pending CAP-009/CAP-010 approval holds; BUG-034/035 remain historically CLOSED. The
  registry's historical lifecycle count prose was left unchanged.
- Scenarios (SCN-MOD001-029, 094, 134, 135, 136 and the 13 C06 scenarios) remain NOT EXECUTED; no
  scenario status, review counter, plan, workflow, or remote changed; MOD-001 exit remains 0/8.
- No paid service, real secret, or real member data involved.

## Next legal step

One fresh-context Opus `veyro-security-reviewer` dispatch (separately authorised, claim written first
per `REVIEW_IN_FLIGHT.md`) returning a **separate** APPROVED/REJECTED/BLOCKED verdict for CAP-009 and
for CAP-010 on this evidence. Rows may then be updated by the sole writer with `approved_by`,
`approved_date`, `next_review_due` and a snapshot row.
