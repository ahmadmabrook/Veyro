# Runtime model proof — SCN-MOD001-070 round-1 remediation (2026-10-04)

Filed per `MODEL_ROUTING.md`'s no-silent-downgrade rule ("Accepted proof of
correct-tier execution requires BOTH the configured agent/model-family alias
AND runtime evidence") and DC-17's requirement that runtime model-proof
evidence live under `knowledge/03-Modules/<MOD>/evidence/model-routing/`.

| MR field | Value |
|---|---|
| Task class | Implementation/test-authoring remediation of an independent review's findings (R1-1 … R1-6) |
| Subject | `tools/validate_migration_ordering.py` + its unit suite (GOV-01-R06, SCN-MOD001-070) |
| Lifecycle role | Implementation tier. **Not** an assurance/judgment role — this session reviewed nothing and promoted nothing. |
| Risk triggers | None of §4.1's critical-slice triggers fire: a static text lint over synthetic YAML records touches no authn/authz, tenant isolation, payments/ledger, booking races, access decisions, privacy/deletion, fiscalization, or crypto boundary. |
| Intended family alias | Opus (per the dispatching brief) |
| Resolved model identity | **`claude-opus-5`** — exact member of `mr_verify.py`'s DC-17-qualified Opus allowlist, not a shape match |
| Consistency | 24/24 assistant turns at verification time, 100% consistent, no mid-task substitution |
| Session id | `fc84a793-79c0-4a6f-b491-b061ea27746f` (`CLAUDE_CODE_SESSION_ID`) |
| Session env | `CLAUDE_CODE_CHILD_SESSION=1`, `AI_AGENT=claude-code_2-1-274_agent`, `CLAUDE_AGENT_SDK_VERSION=0.3.274`, `CLAUDE_EFFORT=high`, `CLAUDE_CODE_ENTRYPOINT=sdk-ts`, `CLAUDE_PID=31229` |
| Execution mode (§4.1) | **Direct** — this session implemented; no `veyro-implementer` was supervised or dispatched, and no subagent was spawned for any part of the work. |
| Verdict | **PASS** (Opus tier runtime-verified) |

## Verification command and output

```
$ backend/.venv/bin/python knowledge/05-QA/tools/mr_verify.py \
    ~/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/fc84a793-79c0-4a6f-b491-b061ea27746f.jsonl \
    opus scn070-remediation-implementation-session
{
  "verdict": "PASS",
  "reason": "24 turn(s), 100% consistent, model 'claude-opus-5' matches required tier 'opus'.",
  "models_observed": [
    "claude-opus-5"
  ],
  "expected_tier": "opus"
}
EXIT=0
```

No self-attestation of model identity was relied on: per `mr_verify.py`'s own
documented finding, no environment variable exposes the resolved model, so the
transcript `model` field is the only real signal, and that is what the command
above reads. The turn count rises as the transcript grows; the invariant to
re-check is the single `claude-opus-5` value.

## Agent label — why not a registered role name

`scn070-remediation-implementation-session` is deliberately a distinct,
accurate description rather than a registered `veyro-*` name. `mr_verify.py`
blocks near-miss labels (its RR-4 hardening) precisely so a session cannot
borrow a registered role's tier attestation, and claiming a spawned agent's
identity for a session that is not that agent would be a false attestation.
The canonical form shares no overlap with any key in
`EXPECTED_TIER_BY_AGENT`, so it correctly falls through to the explicit tier
check — the same pattern as the pre-existing
`main-orchestrating-session-mod000` precedent.

## Routing deviation recorded, not silently taken

The dispatching brief named the **Opus-qualified `veyro-critical-engineer`
role**. That agent's scope is bounded by ADR-005 Decision 1 (and restated in
`MODEL_ROUTING.md`'s critical-slice row and the agent's own frontmatter) to
exactly three MOD-001 slices — the tenant-isolation/RLS harness and fixture
schema, the authentication negative-credential fixture pattern, and TSD
§24.1's RLS-lint + permission-lint architecture gates. **GOV-01-R06's
migration-ordering lint is none of the three.** Both sources state that
extending the role to a new slice requires its own ADR amendment under DC-17's
routing-change sub-clause, with the explicit instruction not to broaden scope
silently.

Resolution taken: the Opus **tier** requirement was honored and
runtime-verified above; the critical-engineer **role** was not invoked.
Executing `tools/**` static-validator work on a runtime-verified Opus session
is an over-tier relative to its standing Sonnet route
(`veyro-implementer`/`veyro-test-author`), not a downgrade, so no assurance
gap is created in either direction, and no `BLOCKED:
MODEL_ASSURANCE_UNVERIFIED` condition arose — Opus was both requested and
runtime-confirmed.

**Open item for the orchestrator/owner:** if GOV-01-R06 lint work is intended
to be critical-engineer scope going forward, that needs an ADR-005 amendment
plus the routing-drill re-run DC-17 requires. This session could not and did
not decide that.

Full remediation record:
`../implementation/SCN070-ROUND1-REMEDIATION-2026-10-04.md`.
