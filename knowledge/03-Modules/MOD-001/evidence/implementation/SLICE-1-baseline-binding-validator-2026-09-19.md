---
doc: MOD-001_IMPLEMENTATION_SLICE_1
status: LIVE
module: MOD-001
updated: 2026-09-19
---

# MOD-001 implementation slice 1 — `tools/validate_baseline_binding.py`

## What this slice is

The first MOD-001 implementation slice, per
`knowledge/03-Modules/MOD-001/REQUIREMENTS.md` §3's "Baseline-artifact
binding schema validation" obligation (tied to GOV-01-R04). Builds
`tools/validate_baseline_binding.py`, the CI-gate generalization of
MOD-000's manual `knowledge/00-System/verify_baselines.py`, covering all
5 fail-closed conditions the EIP mandates for this gate
(`EIP_MIRROR.md` lines 4140-4143, 4253-4263) rather than only the one
`verify_baselines.py` already covers (hash mismatch).

**Why this slice first:** it is the smallest, most clearly dependency-
safe MOD-001 obligation available at implementation start. It lives
under `tools/**`, a known-infrastructure path
(`knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`'s
`repository_paths_surfaces` entry, `profile: null`) — not gated behind
`BUG-034`'s `.claude/rules/backend/**`/`infra/**` content blocker, since
it touches neither `backend/**` nor `infra/**`/CI. It reuses a proven
existing pattern (`verify_baselines.py`) rather than inventing a new
one, and it is required regardless of which later slice comes next.

## Governing requirement / scenario coverage

- `REQUIREMENTS.md` §3, "Baseline-artifact binding schema validation" row.
- `SCENARIOS.md` SCN-MOD001-025 (NEG, Blocker), SCN-MOD001-026 (BND,
  Major, positive control), SCN-MOD001-124 (NEG, Blocker — the 4
  additional fail-closed conditions).

## Routing

Per `MODEL_ROUTE.md`'s existing table ("Routine implementation outside
the two activated surfaces below... validators, `contracts/**`,
`tools/**`" → `veyro-implementer`, Sonnet) — this is routine
implementation, not a critical slice (ADR-005 Decision 1 scopes
`veyro-critical-engineer` to exactly the tenant-isolation/RLS harness,
the authn negative-credential fixture, and the RLS+permission gates —
none of which this tool is) and not Backend/Infra surface work (it
touches neither `backend/**` nor `infra/**`).

Dispatched to `veyro-implementer` (Sonnet, `model: sonnet` explicit on
the dispatch). Ran to completion across two dispatches — the first hit
this session's own rate limit mid-task (an infrastructure interruption,
not an agent failure) and was resumed from where it left off after the
limit reset; the resumed dispatch completed the file and reported back
in full, including the manual trace and disclosed residual below.

## Deliverable

`tools/validate_baseline_binding.py` (470 lines). Implements 5 named
fail-closed error codes: `BASELINE_INTEGRITY_FAILURE` (mismatch, reused
from `verify_baselines.py`'s convention), `UNAPPROVED_CANDIDATE_EIP`,
`MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY`, `MISSING_CONTENT_HASH`,
`BOOTSTRAP_ENFORCEMENT_METADATA_MISSING`. Accepts `--project-index`/
`--bootstrap` path overrides (defaulting to the real files) so negative
fixtures can run against a throwaway copy without ever touching the real
`PROJECT_INDEX.md`/`SESSION_BOOTSTRAP.md`. Read-only against every
governed artifact, always. Exit 0 on full pass, 1 on any denial.

Reuses `verify_baselines.py`'s exact `sha256_file`/`sha256_design_bundle`/
`expected_manifest_hash` procedures verbatim (ported, not imported —
matches `validate_capabilities.py`'s existing self-containment
convention, and avoids coupling to a sibling script whose module-level
code runs a `subprocess` call at import time). Adds a new
row-scoped markdown-table parser (`parse_baseline_table_rows`) so the
tool can tell "no row for this artifact" apart from "row present, hash
field empty" — the original `verify_baselines.py` regex cannot make that
distinction, which this tool's own `MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY`
vs. `MISSING_CONTENT_HASH` split requires.

**Design note found and fixed during authoring:** identity/hash
extraction is deliberately scoped to markdown table rows only (lines
matching `^\|\s*\d+\s*\|`), never a whole-document substring search. The
real `PROJECT_INDEX.md`'s own prose repeats "VEYRO-MPB-1.0" and
"VEYRO-UX-V1-170-APPROVED" outside the table (its "Identity binding
added" paragraph). A naive whole-document approach would have produced a
false `MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY` denial on the real,
correct file. Verified by direct inspection of the real file's current
text before finalizing the design.

## Independent verification this session performed (orchestrating session, not the authoring agent's own say-so)

I (the orchestrating session) read the full 470-line script and manually
re-traced its logic against the real `PROJECT_INDEX.md` content I had
already read in full earlier this session, independently of the
authoring agent's own trace:

- Confirmed `parse_baseline_table_rows` correctly extracts all 4 real
  table rows (lines 24-27) and correctly excludes the header/separator
  rows (first cell not a digit) and the prose repetitions on line 29
  (not table-row-shaped).
- Confirmed the real hash cells are each exactly 64 hex characters
  wrapped in single backticks, matching `_HASH_CELL_RE` exactly (counted
  the Blueprint's hash in 8-character groups: 8×8=64).
- Confirmed the design-bundle row's own `hash_raw` cell ("manifest hash
  below," not an actual hash) is correctly never read for the bundle —
  the tool instead calls `expected_manifest_hash(index_text)` separately
  per the real file's actual structure (a distinct "Manifest hash
  (bundle identity):" line), which I confirmed exists at line 35.
- Confirmed the real EIP row's identity cell text ("currently promoted
  governing EIP — see contradiction note below") contains neither
  "candidate" nor "unapproved" as a substring — traced character-by-
  character against `\b(candidate|unapproved)\b`, confirming
  "contradiction" does not accidentally match "candidate" (no
  case-insensitive substring collision).

This independent re-trace agrees with the authoring agent's own reported
6-case trace (SCN-025 mismatch, SCN-026 positive, SCN-124(a)-(d)). I
found no discrepancy between the two.

## Disclosed execution residual — NOT fabricated test-pass evidence

**This script has not been executed.** `.claude/security/bash_guard.py`'s
`python3` command family (`_python_readonly`) only allows execution of 7
pre-existing, SHA-256-content-hash-pinned scripts
(`_ALLOWED_PYTHON_SCRIPTS`). `tools/validate_baseline_binding.py` is not
on that list, and the guard file itself is both `Edit`/`Write`-denied
(`.claude/settings.json`) and Bash-mutation-denied
(`_is_protected_path`'s `.claude` substring match) to this session — no
session can add itself to its own trusted-script allowlist.

Direct confirmation, not assumption: this session (and, independently,
the authoring agent) attempted `python3 tools/validate_baseline_binding.py`
and `python3 -m py_compile tools/validate_baseline_binding.py`; both
denied `DISALLOWED_FLAG_OR_SHAPE — python3 did not match its
allowlisted read-only shape`.

**This is a precedented, accepted residual in this exact project**, not
a novel blocker — see `knowledge/05-QA/BUG_REGISTRY.md` row `BUG-025`:
a prior tool (`knowledge/05-QA/tools/capability_drift_check.py`) hit the
identical wall and was still recorded `FIXED` with the residual
disclosed rather than treated as blocking ("not yet on `bash_guard.py`'s
trusted-script allowlist, so this session cannot invoke it live...
runnable by the owner/a human terminal today"). `capability_drift_check.py`
remains off the allowlist as of this session — this is a standing,
accepted gap the project has lived with since 2026-09-13, not something
this slice discovered fresh.

No new bug is filed for this residual specifically — it is the same
architectural gap `BUG-025` already discloses, would recur for every new
tool this project builds, and filing a near-duplicate bug per new script
would be registry noise rather than new information. A future session or
the owner may choose to address the underlying allowlist mechanism once,
covering all present and future tools, rather than one script at a time.

**What IS claimed:** the code was written carefully, ported from a
tool with a real, repeated PASS history in this exact project
(`verify_baselines.py`), and hand-traced by two independent readers (the
authoring agent, then this orchestrating session separately) against all
6 SCN-025/026/124 cases with no discrepancy found. **What is NOT
claimed:** that any test was executed, or that the script is free of
defects a live run would catch. Live-executed evidence awaits either an
owner allowlist update (adding this script's path + SHA-256 hash to
`bash_guard.py`'s `_ALLOWED_PYTHON_SCRIPTS`) or a human terminal run
outside this guarded session.

## Traceability

- Requirement: GOV-01-R04 (`REQUIREMENTS.md` §3).
- Scenarios: SCN-MOD001-025, SCN-MOD001-026, SCN-MOD001-124 (all remain
  `NOT EXECUTED` — logic-traced only, per the disclosed residual above;
  this file does not claim otherwise).
- Model route: `veyro-implementer`/Sonnet, explicit `model: sonnet` on
  dispatch. No critical-slice or surface-profile role required.
- Commit: recorded in this slice's own commit (see `CURRENT_HANDOFF.md`
  for the SHA).
