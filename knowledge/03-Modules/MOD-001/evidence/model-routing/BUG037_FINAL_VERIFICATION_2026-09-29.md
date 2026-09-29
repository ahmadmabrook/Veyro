---
doc: BUG037_FINAL_VERIFICATION
status: LIVE
module: MOD-001
updated: 2026-09-29
---

# BUG-037 — final independent verification, round 3

**Reviewer:** fresh-context `veyro-security-reviewer` (Opus). No
participation in Slice 5, the round-1 fix, the round-1 verification
review (which found the round-1 overshoot), the round-2 fix, or
authoring `ADR-008`.

## Verdict: CLOSE BUG-037

All four closure conditions independently confirmed, by direct testing
rather than by re-reading prior reports:

1. **Current critical-engineer MR evidence verifies.** Re-ran the real
   BUG-037 repro transcript
   (`~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/eca6420e-750e-4f5a-8636-1c4a7d0a68db/subagents/agent-a3ead2c53ad28b026.jsonl`)
   through the current `mr_verify.py` with `opus veyro-critical-engineer`:
   **PASS, exit 0, 170 turns, 100% `claude-opus-5-5`.** Confirmed BLOCKED
   under a wrong tier (`sonnet`) and under a Sonnet-registered label
   (`veyro-backend-engineer`) — the tool discriminates correctly, not a
   rubber-stamp.
2. **Unknown/unapproved ids fail closed** — scrutinized hardest, 54
   must-block cases tested through the real `extract_models()` pipeline
   and the CLI, 0 failures: real/plausible unqualified ids (older and
   newer Opus/Sonnet minor versions), the N-9 fabricated id, dot-form
   ids, whitespace/control characters, non-ASCII digit look-alikes,
   case/prefix/suffix wrappers, a qualified id under the wrong tier,
   unknown tier keys, and structural cases (mixed-model transcripts,
   `<synthetic>`-only transcripts, spoofed non-assistant rows). Exact
   `frozenset` membership has no shape-matching surface for any of
   these to exploit.
3. **Wrong-tier agents fail closed.** Label/tier logic untouched by the
   allowlist swap; all 12 registered agents' tiers verified against
   their own frontmatter; near-miss/canonicalization blocking re-tested
   for the 3 new ADR-005 agents specifically.
4. **Regression.** `test_mr_verify.py` 14/14 direct and under pytest;
   `knowledge/05-QA/tools/tests/` + `tools/tests/` 32/32. Beyond the unit
   suite: the current CLI run against all 107 registered-agent subagent
   transcripts in the project (each at its registered tier, its own
   `agentType` label) — 107/107 PASS, 0 regressions against historical
   MR evidence.

F4 (trailing-newline/non-ASCII-digit regex gap) and F5 (unqualified
Sonnet variant) both independently confirmed closed — no regex is used
for membership any more, and the allowlist's Sonnet set is exactly
`{claude-sonnet-5}`, matching every Sonnet id ever observed across 146
project transcripts.

**Did not run** `backend/tests/integration` or anything that starts the
Docker Postgres harness (CAP-008 is unregistered/PENDING per `BUG-038`)
— `mr_verify.py` has no dependency on `backend/`, so this exclusion cost
nothing and a prior round of this same review chain that had run it
self-disclosed the mistake.

## `ADR-008` judgment: sound

Independently re-checked the DC-17 reasoning against the 146-transcript
corpus directly (not taken on the citing reviewer's word): confirmed
the clean `claude-opus-5` → `claude-opus-5-5` cutover timeline, zero
mixed-id transcripts, zero alias/resolved-id disagreement, and
`claude-sonnet-5` as the sole-ever-observed Sonnet id — all matching
`ADR-008`'s claims exactly. The "narrow allowlist bump doesn't need a
full MOD-000-style drill re-run" proportionality argument holds: the
positive half (an opus-requested dispatch resolves to the qualified id
and attests PASS) and negative half (an unknown/downgraded id is
blocked) are both independently demonstrated above, which is what a
drill would otherwise exist to prove for this narrow a change.

Two bookkeeping defects found in `ADR-008` itself, both fixed by the
orchestrating session directly (not requiring a further review round):
a transcript-count arithmetic error (said "5+1=8"; corrected to the
real 7 `veyro-security-reviewer` + 1 `veyro-critical-engineer` = 8, with
all 8 agent ids now listed in a table), and the evidence not having
been linked by id at all (now linked).

## New findings, filed separately, neither blocking this closure

- **`BUG-039`** (P3): the pre-`ADR-008` `RULE_QUALIFICATION_REVIEW_ROUND{3,4,5}`
  records declare "Opus tier" without the specific model id/transcript
  reference; should be backfilled now that `ADR-008` confirms what that
  id was. No false-clean risk (the transcripts are genuinely Opus).
- **`BUG-040`** (P2): the near-miss label-canonicalization check only
  catches separator/substring/superstring variants — a typo, dropped
  letter, or homoglyph inside a role name (e.g. `veyro-critcal-engineer`,
  a Cyrillic look-alike character) matches nothing and falls through to
  trusting the caller-supplied tier uncontested; an empty/whitespace-only
  label is also accepted despite SEC-08's "label is required" claim.
  Weakens defence-in-depth (the tool still prints the true model/tier,
  so it does not itself produce a false PASS) rather than causing a
  false-clean attestation.
- **`BUG-041`** (P3): a JSON row that parses but isn't an object (e.g.
  a bare list/string/null), or one whose `model` field is a non-string
  value, raises a bare Python exception (`AttributeError`/`TypeError`)
  instead of this tool's own `BLOCKED:` convention. Still fails closed
  (non-zero exit, no PASS) but contradicts the docstring's stated
  contract. No real project transcript currently contains such a row.

## Files reviewed

- `knowledge/05-QA/tools/mr_verify.py`
- `knowledge/05-QA/tools/tests/test_mr_verify.py`
- `knowledge/04-Decisions/ADR-008-dc17-requalification-opus-5-5-sonnet-5.md`
- `knowledge/03-Modules/MOD-001/evidence/bugs/BUG-037-mr-verify-rejects-current-opus-model-id.md`
- `knowledge/00-System/DEVELOPMENT_CONSTITUTION.md` (DC-17)
