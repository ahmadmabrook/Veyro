---
doc: ASSURANCE_TIER_AUDIT
status: LIVE — F5-005 substantially closed (real technical mechanism found, built, and proven); one honest carve-out remains
date: 2026-09-05
---

# F5-005 — Model-tier runtime attestation: investigation, mechanism, and gate

## A. Investigation (per owner instruction: re-read EIP, do not invent a mechanism)

Re-read EIP §4.1 directly from the source docx for this remediation:
"Accepted proof requires the configured agent/model-family alias PLUS
runtime evidence: a hook/invocation record containing agent +
session/run identity and **an observable session transcript/status/
warning record sufficient to detect substitution/fallback**. The
version-controlled `model: opus` declaration alone is insufficient."

Investigated what this Claude Code environment actually exposes:

1. **Environment variables** (`env | grep -i model`): checked directly —
   **no variable exposes resolved model identity.** `CLAUDE_EFFORT`,
   `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, `CLAUDE_AGENT_SDK_VERSION`
   exist, but nothing names Opus vs. Sonnet. Real negative finding, not
   invented.
2. **Hook payloads**: tested empirically — added a temporary, gitignored
   diagnostic `PreToolUse` hook to `.claude/settings.local.json`
   (`cat > /tmp/veyro-hook-payload-test.json`), triggered it, inspected
   the real payload, then removed the hook. Contained `session_id`,
   `transcript_path`, `cwd`, `prompt_id`, `permission_mode`,
   `effort.level`, `hook_event_name`, `tool_name`, `tool_input`,
   `tool_use_id` — **no model field either.**
3. **Session transcript files** (JSONL, one object per turn, path given
   in the hook payload's own `transcript_path` field): **this is the real
   signal.** Every assistant-role message carries a `message.model` field
   (e.g. `"claude-opus-5"`, `"claude-sonnet-5"`) — populated by the
   actual Anthropic API response metadata that produced that message, not
   authored by the model's own output text. A model cannot self-report a
   false value into this field; it is set by the infrastructure that
   dispatched the request. This is exactly the EIP's "observable session
   transcript... record sufficient to detect substitution/fallback."

**Cross-checked across 20 real subagent transcripts from this same
session** (every `veyro-*` agent invoked so far in Phases 3-5): every
single Opus-tier agent (`veyro-lead`, `veyro-code-reviewer`,
`veyro-manual-qa`, `veyro-security-reviewer`, `veyro-gatekeeper`,
`veyro-scenario-reviewer`) shows 100% `claude-opus-5` across every turn
of its own transcript (34-198 assistant turns per task, not just the
first message); every Sonnet-tier agent (`veyro-implementer`,
`veyro-test-author`) shows 100% `claude-sonnet-5`. Zero mixed-tier
transcripts found across the sample.

## B. Mechanism built

`knowledge/05-QA/tools/mr_verify.py` — given a transcript file and an
expected tier, extracts every `message.model` value and verifies: (1) at
least one exists, (2) all values are identical (no mid-task
substitution), (3) the value matches the required tier. Real
positive-path proof, independently for both tiers, this same chunk:

- Opus path: `veyro-security-reviewer`'s BUG-006 review transcript — 37
  turns, 100% `claude-opus-5`, **PASS**.
- Sonnet path: `veyro-implementer`'s fresh-session-restore-proof
  transcript — 30 turns, 100% `claude-sonnet-5`, **PASS**.

Full raw output: `knowledge/03-Modules/MOD-000/evidence/model-routing/ASSURANCE_TIER_AUDIT_2026-09-05_output.txt`.

## C. Fail-closed gate implemented

`mr_verify.py` emits `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` (not a bare
exception, not a silent pass) whenever: no model field is found, the
model value is inconsistent across the transcript, or the resolved model
doesn't match the required tier.

## D. Synthetic gate test (explicitly labeled — this is NOT evidence of a real provider outage)

Six fixture cases, real tool invocations against fabricated JSONL:

| Case | Fixture | Expected | Actual |
|---|---|---|---|
| Correct Opus proof | 2 turns, consistent `claude-opus-5` | accepted | **PASS** |
| Correct Sonnet proof, routine role | 1 turn, `claude-sonnet-5` | accepted | **PASS** |
| Missing proof | empty file | blocked | **BLOCKED: MODEL_ASSURANCE_UNVERIFIED** (no model field) |
| Mismatched tier | `claude-sonnet-5` transcript checked against required `opus` | blocked | **BLOCKED: MODEL_ASSURANCE_UNVERIFIED** (tier mismatch) |
| Malformed proof | non-JSON garbage lines | blocked | **BLOCKED: MODEL_ASSURANCE_UNVERIFIED** (no model field found in the noise) |
| Simulated substitution metadata | turn 1 `claude-opus-5`, turn 2 `claude-sonnet-5` | blocked | **BLOCKED: MODEL_ASSURANCE_UNVERIFIED** (inconsistent values across transcript) |

All 6 exact matches. Full raw output in the same `_output.txt` file
referenced above, clearly separated from the real-transcript section
under a "SYNTHETIC fixture gate test (NOT a real outage — labeled
accurately)" heading. **This synthetic test proves the gate logic works
correctly on fabricated input. It proves nothing about what actually
happens during a genuine Anthropic infrastructure outage or a real
provider-side substitution event** — that remains a separate, narrower,
still-open question (E).

## E. What remains open, honestly (not closed, not fabricated)

**True Opus-infrastructure-unavailability** (the account/API genuinely
cannot serve Opus, mid-session) was **not** safely forced or tested —
consistent with every prior phase's carried-forward position on this
exact point, and consistent with the owner's explicit instruction not to
fake a real outage. What this remediation *does* newly establish: **if**
such an outage occurred and the harness silently substituted a lower
tier, the transcript-based mechanism above would detect it (the
`message.model` field would show the substituted tier, and `mr_verify.py`
would report `BLOCKED: MODEL_ASSURANCE_UNVERIFIED` rather than a silent
pass) — because the detection mechanism doesn't depend on the outage
being real, only on the transcript field being populated by the actual
infrastructure that served each request, which it independently is in
every real transcript checked in section A/B. The gate is proven; a real
outage to trigger it has not been (and should not be) manufactured.

## Retrofit and going forward

MR-ID evidence (`MR-<MOD>-<YYYYMMDD>-<NNN>`, per EIP §4.1) has not been
retrofitted for every prior routed task in this project's history — that
remains a real, separate gap (noted in `knowledge/03-Modules/MOD-000/MODEL_ROUTE.md`).
Going forward, any Opus-assurance-tier task can now have its runtime
identity independently verified via `mr_verify.py` against its own
transcript, closing the technical half of F5-005 for all future routed
work even though historical backfill is not complete.

## Disposition

**F5-005: substantially closed.** A real, working, EIP-compliant runtime
attestation mechanism exists, is proven on both real paths and all 6
synthetic edge cases, and is available for every future routed task.
**Remaining open, explicitly, per instruction (E) not (E-avoidance):**
true infrastructure-outage behavior is unverified (as it has always been,
honestly) and historical MR-ID backfill is incomplete. Neither is a
reason to leave the whole finding "carried forward" as before — the
technical gap the finding was really about (no mechanism existed at all)
is closed.
