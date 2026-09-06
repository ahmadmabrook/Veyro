---
doc: ADR-004
status: DECIDED (2026-09-06) — Option A adopted, OWN-003
date: 2026-09-06
---

# ADR-004: What model tier must the MOD-000 orchestrating/lead session run on?

## Context

`knowledge/00-System/MODEL_ROUTING.md` assigns architecture decisions,
ADR authorship, module planning, and dependency/risk decisions to the
`veyro-lead` role at **Opus** tier (DC-17: "Every assurance-tier action
must carry runtime model-proof evidence... No silent downgrade"). A
Phase 7 fresh-context `veyro-security-reviewer` found (SEC-01,
`BUG-012`) that the actual top-level orchestrating session driving
MOD-000 — the one authoring ADRs, making Phase 6 scope determinations,
declaring Phase 1-6 gate verdicts, and self-verifying P1 closures across
multiple Phase 5 review rounds — is not a spawned `veyro-lead` subagent.
It is the raw interactive session itself, and `mr_verify.py` run against
its real transcript confirms: 100% `claude-sonnet-5`, zero
`claude-opus-5`, across every assistant turn (independently reparsed
during the Phase 7 re-review: 3,528 assistant turns as of that check,
growing as the session continues — see `knowledge/03-Modules/MOD-000/
evidence/security/MAIN_SESSION_MR_VERIFY_2026-09-06.json`). (Corrected
2026-09-06, Phase 7 re-review RR-8: an earlier version of this line said
"13,438 turns," conflating the transcript's line count with its
assistant-turn count — real, but the wrong unit.)

Every delegated Opus subagent this session has spawned (veyro-code-
reviewer, veyro-manual-qa, veyro-security-reviewer, veyro-performance-
reviewer, veyro-scenario-reviewer, veyro-gatekeeper) is independently,
technically attested as genuinely Opus. This is not in question. What is
in question is whether `MODEL_ROUTING.md`'s "Architecture, ADRs, module
planning" → Opus row was ever meant to reach the *orchestrating* session
itself, and if so, whether the entire module needs to be re-executed at
that tier, or whether the deviation should be formally accepted.

## Decision needed (owner-reserved — this ADR cannot self-resolve it)

Which model tier governs the orchestrating/lead session for MOD-000 (and
by precedent, future modules)?

**Option A — Formally accept Sonnet-tier orchestration.** Rationale: the
project's actual practice has been "Sonnet orchestrates and delegates
every Opus-reserved *judgment* action (architecture review, code review,
scenario review, manual QA, security/performance review, certification)
to a fresh-context Opus subagent invoked BY the orchestrating session."
Under this reading, the orchestrating session's own role is coordination
and execution — routing work, writing files, running checks — not the
reserved judgment itself, even when it authors the ADR *text* that
records a decision an Opus subagent (or the owner) actually made. This
would require: (1) a correction to `MODEL_ROUTING.md`'s role table to
explicitly distinguish "the session that invokes veyro-lead" from
"veyro-lead itself"; (2) an honest audit of which specific past
decisions (ADR-002, ADR-003, every interim Phase 1-6 gate declaration)
were genuinely delegated-then-transcribed vs. decided directly by the
Sonnet session without Opus input, since those are materially different
under this reading; (3) an `OWN-<NNN>` row in `OWNER_APPROVALS.md`
formally accepting this operating model going forward.

**Option B — Require Opus for the orchestrating/lead session** whenever
it is making an architecture/ADR/gate-verdict-class decision directly
rather than purely delegating and transcribing. This is the stricter
reading of DC-17 and would have real cost/workflow implications (this
session would need to run future architecture-class turns on Opus, or a
`veyro-lead` Opus subagent would need to actually make and author those
specific decisions rather than the orchestrating session doing so
directly).

Neither option is chosen by this ADR. This agent cannot decide which
model tier it is itself invoked as — that is set by the human/owner
starting the session, not a file this agent can edit.

## Consequences if Option A

`MODEL_ROUTING.md` gets more precise language. Past decisions get an
honest retroactive characterization (delegated-then-transcribed vs.
direct). No change to how future MOD-000/future-module work is executed
day to day.

## Consequences if Option B

Future architecture/ADR/gate-verdict-class turns in this project need to
either run on an Opus-invoked session, or be explicitly restructured so a
spawned `veyro-lead` Opus subagent makes and authors the decision itself
(not just reviews one already made). This is a real workflow change, not
a documentation fix.

## Decision (2026-09-06)

**Option A adopted.** The owner, asked directly, chose "Accept Sonnet
orchestration" — recorded as `OWN-003` in
`knowledge/00-System/OWNER_APPROVALS.md`. `MODEL_ROUTING.md` has been
corrected with a new "Orchestrating-session tier vs. delegated-role
tier" section stating this explicitly, and `BUG-012` is closed on this
basis — see that file for the closure record.

## Status

**DECIDED.** Not retroactively re-auditing every past ADR/gate-verdict
decision line-by-line for whether it was genuinely delegated-then-
transcribed vs. decided directly (Option A's consequence #2) — this is
a large undertaking disclosed here as a known limitation of this
decision's scope, not attempted this chunk. Going forward, the
orchestrating session must delegate architecture/ADR/gate-verdict-class
judgment calls per `MODEL_ROUTING.md`'s corrected section, not decide
them unilaterally on Sonnet.
