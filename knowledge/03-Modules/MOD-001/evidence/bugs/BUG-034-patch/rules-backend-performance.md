<!-- Target path once applied: .claude/rules/backend/performance.md -->

# Rule: Backend Load Scope and Observability Baseline (`backend/**/*.py` binding)

Authored 2026-09-19 (MOD-001, `ADR-005` Decision 2 binding pre-implementation
condition — see `architecture.md` for the shared authority citation, not
restated here). Grounded directly in the EIP card's own bounded "Load /
performance" field (`EIP_MIRROR.md` lines 4230-4231, verbatim: "CI
runner and environment smoke-load; validate no gate is bypassable"),
`IMPLEMENTATION.md` §5 (MOD-001's own planned load scope: a 15-minute
CI-pipeline smoke-load budget, a 10-concurrent-request/2-second
environment health-check smoke-load, and gate-bypass-under-load
validation — explicitly **not** application-scale business load
testing, which `REQUIREMENTS.md` GOV-01-R03 assigns OUT of scope to
later domain modules), and the sensitive-logging lint obligation
(`REQUIREMENTS.md` round 6 P1-1, citing the EIP card's mandatory
Security baseline, `EIP_MIRROR.md` lines 4267-4271: "sensitive
logging") — read directly this session from the owner-produced mirrors
and MOD-001's own planning documents. Per this project's own convention
(`REQUIREMENTS.md` §0), the governing `.docx` wins over this
mirror-sourced text on any conflict.

**Scope note:** this rule does not state an application-scale load
budget — MOD-001 owns no such budget, and inventing one here would be a
material scope change this rule is not authorized to make. The load
obligation below is bounded to exactly what `IMPLEMENTATION.md` §5
already commits MOD-001 to.

## Required controls for `backend/**/*.py`

1. **Load scope is bounded to CI-runner and environment smoke-load.**
   Backend code's load/performance obligation at MOD-001's stage is: the
   full CI pipeline completes within its declared budget on a
   synthetic/trivial repo state, and LOCAL/QA/staging environments
   answer a trivial health-check endpoint within budget under a small
   concurrent-request count (`IMPLEMENTATION.md` §5). This is explicitly
   not application-scale business load testing — that belongs to later
   domain modules under their own SLOs (GOV-01-R03's IN/OUT boundary).

2. **A smoke-load budget regression is a recorded decision, not a
   silent change.** If a backend change measurably pushes the CI-runner
   or environment smoke-load budget past its declared threshold, the
   budget is revisited via an explicit recorded decision — never
   silently loosened or silently ignored.

3. **No gate is skippable under load.** No backend code path may cause
   an architecture gate or CI stage to be silently skipped through a
   timeout, a resource-exhausted CI runner, or a race between concurrent
   pipeline runs — ties to the gate-bypass-under-load validation
   `IMPLEMENTATION.md` §5 already plans.

4. **Log output is structured.** Backend log statements use a
   consistent, field-keyed structured format, not ad hoc string
   interpolation, so log output is machine-parseable by the
   observability tooling this module wires up.

5. **No secret or PII-shaped value appears in a log statement.** No
   backend log statement includes a secret, credential, access token,
   or PII-shaped value (raw member data, a national ID, a full payment
   card number, a password, an API key). Where a value must be logged
   for diagnostic purposes, it is redacted, hashed, or truncated first.
   This is the exact condition the sensitive-logging lint denies as a
   named file/line plus secret- or PII-pattern-class violation.

6. **Real member data never appears in backend code, logs, fixtures, or
   tests.** Synthetic/fixture data only — this follows directly from
   the project's owner-reserved restriction on real member data
   (`.claude/rules/global/owner-reserved-restrictions.md`) and is
   restated here because it is also a concrete, checkable logging/
   observability constraint, not only a policy statement.

## Fail-closed rule

A backend change that regresses a declared CI-runner or environment
smoke-load budget without a recorded decision, or a log statement
matching a secret/PII pattern, does not merge. The smoke-load checks
(`IMPLEMENTATION.md` §5) and the sensitive-logging lint
(`REQUIREMENTS.md` round 6 P1-1) are both CI-blocking.
