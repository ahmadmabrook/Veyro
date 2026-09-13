---
doc: BUG-026
status: FIXED — same day, this chunk (a first fix pass had its own incompleteness caught by independent Gatekeeper re-review, corrected same chunk)
found_date: 2026-09-12
found_by: Phase 9 fresh-session restoration proof (this session), while independently restoring model-routing state from durable sources alone
severity: P2
---

# BUG-026: `MODEL_ROUTE_INDEX.md` was stale since 2026-09-01, contradicting `CURRENT_STATE.md`/`ASSURANCE_TIER_AUDIT.md` about which agents have been runtime-tested

## What was wrong

`knowledge/05-QA/MODEL_ROUTE_INDEX.md` (front matter `updated: 2026-09-01`)
stated, as CURRENT state: `veyro-lead`, `veyro-scenario-reviewer`,
`veyro-code-reviewer`, `veyro-manual-qa`, `veyro-security-reviewer`,
`veyro-performance-reviewer`, `veyro-test-author` are all "Not yet
individually runtime-tested," with only `veyro-implementer` and
`veyro-gatekeeper` qualified.

This directly contradicts other CURRENT durable state:

- `knowledge/03-Modules/MOD-000/evidence/model-routing/ASSURANCE_TIER_AUDIT.md`
  (2026-09-05) already documents cross-checking 20 real subagent
  transcripts across Phases 3-5, finding `veyro-lead`,
  `veyro-code-reviewer`, `veyro-manual-qa`, `veyro-security-reviewer`,
  `veyro-gatekeeper`, and `veyro-scenario-reviewer` each 100%
  `claude-opus-5` across every turn (34-198 turns per task). (Note:
  `veyro-gatekeeper` was already separately QUALIFIED via `RUNTIME_PROOF.md`
  self-report before this audit existed — `MODEL_ROUTE_INDEX.md` cites the
  older, weaker `RUNTIME_PROOF.md` evidence for that row rather than this
  stronger transcript audit, which is conservative, not incorrect, but is
  flagged here as a real minor inconsistency between this bug file's
  narrative and that row's actual citation.)
- `CURRENT_STATE.md`/`CURRENT_HANDOFF.md` narrate dozens of real,
  fresh-context invocations of exactly these agents across Phases 5-8
  (code review rounds 1-5, manual QA Phases 5/6, security reviews
  through Phase 7/8's BUG-024 adjudication), each with `mr_verify.py`-
  attested transcripts.

`MODEL_ROUTE_INDEX.md` was simply never updated after its initial
2026-09-01 authoring, even though the file's own header claims LIVE
status and positions itself as "the durable index of every
model-routing binding and its qualification status."

## Why this matters for Phase 9

Phase 9's restoration proof requires that a fresh session can determine
current model-routing state from durable sources alone, without
contradiction. A fresh session reading only `MODEL_ROUTE_INDEX.md` would
incorrectly conclude 7 of 9 agents remain unverified, when real,
extensively-documented runtime proof exists for 6 of them. This is
exactly the "restoration contradiction" class Phase 9 §14 is designed to
catch — two durable documents disagreeing about current state, not a
historical record being superseded (that's expected and fine).

## Fix applied this chunk (corrected after independent re-review)

`MODEL_ROUTE_INDEX.md` updated to reflect actual current qualification
status for `veyro-lead`, `veyro-code-reviewer`, `veyro-manual-qa`,
`veyro-security-reviewer`, and `veyro-scenario-reviewer`, citing
`ASSURANCE_TIER_AUDIT.md` as evidence, without fabricating per-row MR-ID
evidence that doesn't exist. (`veyro-gatekeeper` was already correctly
QUALIFIED before this fix, via `RUNTIME_PROOF.md` self-report evidence —
unchanged by this bug, not part of what this fix updated.)

**A first version of this fix, produced the same chunk, was itself
incomplete:** it left `veyro-test-author`'s row saying "not yet
individually runtime-tested" even though `ASSURANCE_TIER_AUDIT.md` line
49 explicitly covers it ("every Sonnet-tier agent (`veyro-implementer`,
`veyro-test-author`) shows 100% `claude-sonnet-5`"), and left a stale
"## Note" section below the corrected table still asserting "only 2 of 9
agents have been individually invoked" — directly contradicting the
table above it. An independent fresh-context `veyro-gatekeeper` review of
this restoration proof caught both (its P1-1 and P1-2 findings) before
this bug was marked FIXED. Both corrected in the same chunk:
`veyro-test-author`'s row now reads QUALIFIED citing
`ASSURANCE_TIER_AUDIT.md`; the stale Note section was removed rather than
left to contradict the table.

**`veyro-performance-reviewer` is the one row that genuinely has no
dedicated runtime-tier transcript audit** — `ASSURANCE_TIER_AUDIT.md`'s
20-transcript cross-check names exactly 6 Opus-tier and 2 Sonnet-tier
agents, and `veyro-performance-reviewer` is not among either list. Left
honestly marked as not individually confirmed, rather than inferring
qualification it hasn't specifically been shown to have.

## Certification impact

**P2, non-blocking for Phase 9.** The underlying model-routing
*mechanism* was never in doubt (confirmed working for both tiers since
2026-09-01, reaffirmed by `ASSURANCE_TIER_AUDIT.md`). This was a durable
document going stale, not a live control gap — no task ever actually
relied on a false "unqualified" or "qualified" claim from this specific
file. Fixed same day; no re-run of `mr_verify.py` needed since the
underlying transcripts already exist and were already independently
reviewed in Phase 5.

## Affected

`knowledge/05-QA/MODEL_ROUTE_INDEX.md`.
