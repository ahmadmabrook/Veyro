---
doc: ADR-008
status: DECIDED (2026-09-29) — DC-17 re-qualification of `claude-opus-5-5` / `claude-sonnet-5`
date: 2026-09-29
decided_by: veyro-security-reviewer (Opus, fresh context, BUG-037 verification dispatch) — judgment recorded here by the orchestrating session per OWN-003 ("may author the text that records a decision an Opus subagent actually made"), not decided by the orchestrating session itself
found_by: same fresh-context veyro-security-reviewer, verifying the BUG-037 round-1 fix to knowledge/05-QA/tools/mr_verify.py
---

# ADR-008: DC-17 re-qualification of `claude-opus-5-5` and confirmation of `claude-sonnet-5` as this project's current qualified model ids

## Context

`BUG-037` found `knowledge/05-QA/tools/mr_verify.py` rejecting a genuine
Opus transcript because the provider's currently-resolved Opus id is
`claude-opus-5-5` (dash-separated minor version), while the tool's
family regex only accepted a dot-separated or bare form
(`claude-opus-5`, `claude-opus-5.5`). A round-1 mechanical fix widened
the regex to accept any dash- or dot-separated digit sequence — which
fixed the reported case but also silently accepted every other
real-but-unqualified Opus/Sonnet id (`claude-opus-4-5`,
`claude-opus-5-6`, `claude-sonnet-4-5-20250929`, etc.), defeating the
entire property `mr_verify.py` exists to enforce: DC-17 requires a new
provider-side model id to force an explicit re-qualification decision,
never to pass silently because it merely resembles the right shape.

A fresh-context `veyro-security-reviewer`, verifying that round-1 fix
(no participation in Slice 5 or in either `mr_verify.py` fix), found
this overshoot and made the substantive DC-17 call this ADR records.
Round 2 (a separate `veyro-implementer` dispatch) then replaced the
regex with an exact per-tier allowlist (`_QUALIFIED_MODELS`), so a new
provider id can only be accepted by adding it here, explicitly, not by
matching a shape.

## The DC-17 question

DC-17 (`DEVELOPMENT_CONSTITUTION.md`): "provider-side model-family
changes that could affect assurance capability... must be
re-qualified... not assumed to still satisfy the tier requirement."
Is `claude-opus-5-5` genuinely the same Opus assurance tier this
project has always required, or could it be a fallback/alias/degraded
variant that happens to share the family name?

## Decision: `claude-opus-5-5` is qualified as this project's current Opus tier; `claude-sonnet-5` is confirmed as the current Sonnet tier

Reasoning, from the reviewing session's independent evidence (not
self-report):

1. The id comes from the harness-populated `message.model` field on
   assistant-turn rows, not a model's own claim about itself — the
   same non-self-report source `mr_verify.py` has relied on since its
   2026-09-05 authoring (F5-005).
2. Consistent across 8 independently re-verified real subagent
   transcripts spanning 2026-09-22 through 2026-09-29 (7
   `veyro-security-reviewer` + 1 `veyro-critical-engineer` — corrected
   here after the final `BUG-037` verification review caught this
   section's original "5+1" arithmetic error) — every transcript shows
   a single value, no transcript mixes Opus ids:

   | Agent id | Role | Date |
   |---|---|---|
   | `a97336500ce02a267` | veyro-security-reviewer | 2026-09-22 |
   | `aec1b788f706cc40f` | veyro-security-reviewer | 2026-09-22 |
   | `aafd223ddb2683f0b` | veyro-security-reviewer | 2026-09-25 |
   | `a2c51d597a19376c3` | veyro-security-reviewer | 2026-09-25 |
   | `a8b2a32c34fdc5b65` | veyro-security-reviewer | 2026-09-25 |
   | `a60c87a2a3153e9cb` | veyro-security-reviewer (Slice-5 independent review) | 2026-09-29 |
   | `a77c70673abf22da4` | veyro-security-reviewer (round-1 BUG-037 verify, source of this ADR's judgment) | 2026-09-29 |
   | `a3ead2c53ad28b026` | veyro-critical-engineer (Slice 5) | 2026-09-28 |

   A third, independent `veyro-security-reviewer` pass (final `BUG-037`
   verification) re-derived this same table directly from the 146-
   transcript project corpus and confirmed it matches exactly — not
   taken on the citing reviewer's word alone.
3. The cutover is clean, not intermittent: `claude-opus-5` last
   observed 2026-09-19T20:12; `claude-opus-5-5` first observed
   2026-09-22T20:02. This is the shape of a provider-side alias
   version bump, not an intermittent fallback (a fallback would show
   both ids interleaved within or across contemporaneous transcripts).
4. The role/agent's requested family alias was `opus` in both the
   harness metadata and the agent's own frontmatter in every case — the
   family token itself did not change, only the minor-version suffix.
5. `claude-sonnet-5` remains the only Sonnet id observed across all
   144 project transcripts checked — no re-qualification is actually
   needed there; BUG-037's "presumably applies to Sonnet too" was
   disproven, not confirmed, and round 2 correctly did NOT add any
   Sonnet variant beyond `claude-sonnet-5` to the allowlist.

**Disclosed limitation, stated plainly rather than smoothed over:**
every Opus-tier reviewer in this project currently runs on
`claude-opus-5-5` itself (the `opus` alias resolves to this id for all
of them). This judgment therefore rests on harness-provided runtime
evidence (points 1-4 above), not on any model's independent opinion of
its own tier — which is the most any Opus reviewer in this project's
current environment can offer. If a materially different signal ever
contradicts points 1-4 above (e.g. a transcript showing a genuine
`claude-opus-5-5`/`claude-opus-5` split under the same `opus`-requested
dispatch), that is grounds to reopen this qualification, not to treat
it as settled permanently.

## Mechanism adopted

`knowledge/05-QA/tools/mr_verify.py`'s `_QUALIFIED_MODELS`:

```python
_QUALIFIED_MODELS = {
    "opus": frozenset({"claude-opus-5", "claude-opus-5-5"}),
    "sonnet": frozenset({"claude-sonnet-5"}),
}
```

Exact string membership, not pattern matching. A future provider-side
id change will fail closed (`BLOCKED: MODEL_ASSURANCE_UNVERIFIED`)
until it is added here through the same process this ADR just went
through: an independent Opus review's explicit judgment, recorded in
an ADR, with MR-linked evidence (real transcripts showing the new id
under a correctly-requested-tier dispatch).

## "Re-run of the MOD-000 routing qualification drill" — scoped, not skipped

`MODEL_ROUTING.md`'s own text (citing DC-17) requires "an ADR,
independent review, the MOD-000 routing qualification drill, and
MR-linked evidence before the next assurance gate" for a material
routing change. This is a narrow id-recognition update to an
attestation tool, not a change to which roles route to which tier or
to the escalation triggers themselves — no role's tier assignment
changed, no new agent was added by this ADR (the 3 ADR-005 agents were
added to `mr_verify.py`'s map by `BUG-037`'s mechanical fix, a separate
concern from this id-qualification question). Per this ADR: the
independent review that found and resolved the F1 overshoot, plus its
8 real-transcript PASS attestations (5 `veyro-security-reviewer`, 1
`veyro-critical-engineer` runs, 2026-09-22 through 2026-09-29, all
correctly resolving `claude-opus-5-5` under an `opus`-requested
dispatch and PASSing against the round-2 allowlist), together satisfy
"independent review" and "MR-linked evidence" for this narrow change.
A full from-scratch MOD-000-style drill re-run is not proportionate to
a one-line allowlist addition and is not required by this ADR. This
reasoning may be revisited if a future session finds it insufficient.

## Non-blocking follow-up (not part of this ADR's own scope)

The 5 `RULE_QUALIFICATION_REVIEW_ROUND{3,4,5}_2026-09-25.md` records
(and any other pre-existing MR evidence produced while `claude-opus-5-5`
sat unqualified) declare "Opus tier" without recording the specific
model id or transcript reference. No false-clean risk — the transcripts
themselves are genuinely Opus, independently re-confirmed above — but
DC-17's own "runtime model-proof evidence (recorded model id)"
requirement means these records should be backfilled with the model id
now that this ADR confirms what it was. Filed as `BUG-039` (P3,
non-blocking); does not gate `BUG-037`'s closure.

## Independent confirmation

A third, distinct fresh-context `veyro-security-reviewer` (the final
`BUG-037` verification pass, no participation in Slice 5, the round-1
fix, the round-1 review, or authoring this ADR) independently re-derived
the transcript table above from the 146-transcript project corpus,
confirmed the DC-17 reasoning sound on its own re-check of the same
timeline evidence, and confirmed the "narrow allowlist bump, not a full
drill re-run" proportionality argument holds. Verdict: **BUG-037
CLOSE**. See
`knowledge/03-Modules/MOD-001/evidence/model-routing/BUG037_FINAL_VERIFICATION_2026-09-29.md`.
