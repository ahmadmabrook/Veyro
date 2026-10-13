---
doc: SESSION_BOOTSTRAP
status: LIVE
---

# Session Bootstrap — Fail-Closed

Read this first, every session, before any action. This file must let a fresh Claude session (zero prior chat context) reconstruct legal next action from disk alone.

## 1. Governing baseline identities (verify before trusting anything else)

Re-hash **all four** artifacts (the 3 docx files, plus the design bundle
manifest) and diff against `PROJECT_INDEX.md`. Also confirm the four
identity strings (`VEYRO-MPB-1.0`, `Veyro TSD v1.4.1`,
`VEYRO-UX-V1-170-APPROVED`, `VEYRO-EIP-1.4.1-20260827`) are present in
`PROJECT_INDEX.md` — a hash match alone does not confirm the artifact's
declared identity/version. If any hash or identity mismatches, STOP —
report `BLOCKED: BASELINE_INTEGRITY_FAILURE` and do not proceed. (Corrected
2026-09-04, Phase 5 F5-013 — this section previously verified only 3 of 4
baselines, silently skipping the design bundle, which is exactly the
artifact BUG-001 was found in.)

**Primary check (corrected 2026-09-30, session-restore reconciliation —
this section previously said the command was "allowlisted by the live
`.claude/security/bash_guard.py` PreToolUse guard (CAP-007, active since
2026-09-08)"; **CAP-007 was RETIRED 2026-09-28** per `OWN-006`/`ADR-007`
— `bash_guard.py` is now an inert, unregistered stub and
`.claude/settings.json` permits unrestricted local Bash execution
(`Bash(*)` allow, empty deny, `defaultMode: bypassPermissions`) for
routine development. Module certification gates, WIP=1, and the 4
owner-reserved absolute restrictions are unaffected by that retirement —
see `.claude/rules/global/owner-reserved-restrictions.md`. There is no
PreToolUse guard to be "allowlisted by" anymore; the command below just
runs directly.**

**Also corrected this session: system `python3` (3.9.6 on this host)
fails this script outright** (`TypeError` on the `str | None` PEP 604
syntax, which needs Python 3.10+) — confirmed by direct execution, not
assumed. Use the project's own venv interpreter instead:

```bash
backend/.venv/bin/python knowledge/00-System/verify_baselines.py
```

If `backend/.venv/` does not exist on a given machine, use any local
Python 3.10+ interpreter; do not use bare `python3` without first
confirming its version. This covers all 4 baselines including the
design bundle manifest — hash-diffed directly against `PROJECT_INDEX.md`.
Prefer this over the raw shell commands below.

**Reference/offline alternative** (run only if `verify_baselines.py`
itself is unavailable or under suspicion; nothing technically prevents
chaining these now that CAP-007 is retired, but running one command at a
time keeps output attributable to a single check):

```bash
shasum -a 256 Gym_OS_Master_Product_Blueprint_v1_English.docx
shasum -a 256 Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx
shasum -a 256 Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx
( cd veyro-product-experience-design && find . -type f ! -name '.DS_Store' -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 )
grep -E "VEYRO-MPB-1.0|Veyro TSD v1.4.1|VEYRO-UX-V1-170-APPROVED|VEYRO-EIP-1.4.1-20260827" knowledge/00-System/PROJECT_INDEX.md
```

Expected values: `knowledge/00-System/PROJECT_INDEX.md` (design bundle
manifest hash also recorded there and in
`knowledge/00-System/DESIGN_BUNDLE_MANIFEST.txt`).

## 2. Active module + current state

Read `knowledge/00-System/CURRENT_STATE.md`. It names the active module, its gate status, and whether WIP=1 is respected.

## 3. Open defects, decisions, approvals

- Defects: `knowledge/05-QA/BUG_REGISTRY.md` (current MOD-001 through MOD-074); historical module-local records are not current gate proof.
- Decisions/ADRs: `knowledge/04-Decisions/`
- External gates: `knowledge/00-System/EXTERNAL_GATES.md` (+ detail records in `knowledge/00-System/external-gates-evidence/`)
- Owner approvals: `knowledge/00-System/OWNER_APPROVALS.md`
- Current module evidence/certificate index: `knowledge/03-Modules/<active MOD>/<active MOD>.md`; verify every claimed gate against its referenced immutable CI/ACP artifact or approved `knowledge/05-QA/` record, stable run/commit identity and SHA-256 where applicable (OWN-008/ADR-009). No module-local `evidence/` directory or routine report Markdown is required for MOD-001 through MOD-074.

## 4. Handoff

Read `knowledge/00-System/CURRENT_HANDOFF.md` for exactly what the previous session left unfinished and the next legally allowed action.

**Before dispatching any fresh independent review round** (security, scenario-catalog, code, or gatekeeper), read `knowledge/00-System/REVIEW_IN_FLIGHT.md` and follow its protocol — check its `current_claim` field, and if `CLEAR`, write an `IN_FLIGHT` claim before the dispatch call returns, not after. If the claim already reads `IN_FLIGHT`, do not dispatch a second review for the same bug/module/round class; follow that file's crash-recovery section instead of assuming either that the claim is live or that it is stale. This exists because round 11 of MOD-001's Slice-7/BUG-050 remediation had exactly this collision — two orchestrating sessions, neither aware of the other, each dispatched the same round-11 review (`knowledge/03-Modules/MOD-001/evidence/implementation/SLICE-7-ROUND11-COLLISION-CHECKPOINT-2026-10-03.md`).

## 5. Fail-closed rule

If any of the above files are missing, unreadable, or contradict each other, do not guess or invent state. Report `BLOCKED: SESSION_RESTORE_FAILURE` with the specific missing/contradictory file and stop.
