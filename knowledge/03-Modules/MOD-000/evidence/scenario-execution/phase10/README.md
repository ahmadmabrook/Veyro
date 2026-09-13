---
doc: PHASE10_CERTIFICATION_ROUNDS_README
status: LIVE
date: 2026-09-13
---

# Standing rule: every certification round authors its own evidence file

Instituted 2026-09-13 after the fifth independent MOD-000
certification-scope `veyro-gatekeeper` round (P1-3) found that rounds 1
through 4 had each, in turn, found the round immediately before it
lacked a dedicated evidence file — a defect that recurred four
consecutive times because each remediation authored the *prior*
round's missing file without establishing a rule that the *current*
round also needs one.

**The rule, going forward:** the session remediating a certification
round's findings must author, in this same directory, an evidence file
for that same round — named `CERTIFICATION_ROUND_` followed by the
round's number and the date, in the same commit as the rest of that
round's remediation — not deferred to whenever the next round happens
to notice its absence. This file exists to make that obligation
explicit and discoverable, not to be a fifth place the round count
itself is stated (it deliberately names no current round number — see
`knowledge/00-System/CURRENT_STATE.md`'s front matter for that).

Each round's file should contain, at minimum: the verdict line, P0/P1/P2/Editorial
counts, per-P0/P1 finding detail and required remediation, and a
disposition note pointing to where remediation landed.
