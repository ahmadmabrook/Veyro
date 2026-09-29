---
doc: BUG-040
module: MOD-000 (tool: knowledge/05-QA/tools/mr_verify.py)
severity: P2 (defence-in-depth gap; does not itself produce a false PASS — the tool still prints the true resolved model/tier)
status: OPEN (2026-09-29)
filed: 2026-09-29 by veyro-security-reviewer (Opus), final BUG-037 verification review
---

# BUG-040 — `mr_verify.py`'s near-miss label check can be bypassed by a typo, dropped letter, or homoglyph

## Finding

`verify()`'s label-canonicalization logic (added SEC-08, hardened
RR-4) only blocks a caller-supplied label that, once canonicalized
(lowercased, non-alphanumeric stripped), is a **substring or
superstring** of a registered role's canonical form. A label that
differs from a registered role by an internal typo, a dropped letter,
or a homoglyph substitution shares no substring/superstring
relationship and falls straight through to trusting the caller-supplied
tier, uncontested.

Confirmed directly against the 3 `ADR-005` agents added by `BUG-037`:
a Sonnet transcript PASSes as `sonnet` under labels
`veyro-critcal-engineer`, `veyro-critical-enginer`,
`veyro-crit-engineer`, and `veyro-critical-еngineer` (Cyrillic `е`
substituted for Latin `e`) — all of which are meant to reference the
Opus-registered `veyro-critical-engineer` but are silently treated as
unregistered/ad-hoc labels instead. Similarly, an Opus transcript
PASSes as `opus` under `veyro-backnd-engineer` (dropped `e`), meant to
reference the Sonnet-registered `veyro-backend-engineer`.

Also found: the CLI accepts an empty string, `"---"`, or whitespace-only
label, despite SEC-08's docstring claim that "agent_label is
mandatory... tier is taken from `EXPECTED_TIER_BY_AGENT`, never from an
unverified caller-supplied string alone" — an empty/degenerate label
canonicalizes to nothing, matches no registered role, and is treated as
a legitimately-distinct unregistered label rather than rejected outright.

## Why this is P2, not P1/P0

The tool does not produce a false attestation about the *model* — it
still prints the actually-resolved model id and tier verdict truthfully.
The risk is narrower: a caller (human or agent) who intends to attest a
registered role's tier, but mistypes or is fed a homoglyph-altered
label, gets a PASS/BLOCKED verdict computed against the *caller-supplied*
tier instead of the *registered* tier for that role — silently
defeating the entire point of the SEC-08 hardening (a Sonnet transcript
attesting "opus" for a role that's actually Sonnet-registered would be
caught; but under a homoglyph label, a Sonnet transcript attesting
"sonnet" for what should be recognized as the Opus-registered
`veyro-critical-engineer` slips through as a bare unregistered-label
check, not a tier violation, because the mismatch with the *real* role
identity is never detected).

## Suggested fix

- Block verification outright when the canonicalized label is empty.
- For any canonical label that begins with `veyro` (this project's own
  agent-naming convention) but is not an exact match in
  `EXPECTED_TIER_BY_AGENT` and does not hit the existing
  substring/superstring near-miss check either, treat it the same as
  the existing near-miss case (BLOCKED, ambiguous label) rather than
  falling through to an unregistered-label path — or use an explicit
  edit-distance/`difflib.SequenceMatcher` similarity threshold against
  the registered-role list to catch typo/homoglyph variants specifically.
- Add regression tests for the exact bypass strings found above.
