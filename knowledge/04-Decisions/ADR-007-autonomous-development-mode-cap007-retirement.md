---
doc: ADR-007
status: DECIDED (2026-09-28) — autonomous development mode adopted, OWN-006
date: 2026-09-28
---

# ADR-007: Autonomous development mode — CAP-007 Bash guard retired for local dev friction, module gates unchanged

## Context

- `BUG-036` (open since 2026-09-22, 5 rounds) blocked all local Python
  tooling execution (venv creation, `pip install`, `pytest`/`ruff`/`mypy`)
  because `bash_guard.py`'s Tier-1 allowlist never covered these
  commands, and extending it required its own security-review cycle each
  time. Multiple rounds of tooling were built
  (`tools/generate_requirements_lock.py`, etc.) but never executed
  in-session for this reason — every round deferred real execution to
  "the owner's own machine, outside Claude Code."
- CAP-007 (`bash_guard.py` + its `.claude/settings.json` `PreToolUse`
  wiring) carries a heavy compliance history: v1 superseded after 4
  independent security-review rounds (each found a new P0 bypass); v2
  approved 2026-09-08 after a capped Round 3 + P1 remediation + a
  14-point live-activation test matrix. It functioned as designed for
  over 3 weeks.
- On 2026-09-28 the owner committed `058ed27` ("chore: enable autonomous
  development mode"), replacing `bash_guard.py`'s ~797-line
  allow-by-construction classifier with an inert stub, removing the
  `PreToolUse` hook registration entirely, and narrowing
  `.claude/settings.json`'s permission block to `Bash(*)` / `allow`,
  `deny: []`, `defaultMode: bypassPermissions`. This was done without a
  same-commit `OWNER_APPROVALS.md` row — a gap against this project's own
  logging rule ("any session that receives explicit owner approval...
  must add a row here... in the same commit"). Caught by this session
  (2026-09-28) on being asked to continue MOD-001 work under an
  "autonomous development mode" instruction; the owner confirmed (via
  this session's checkpoint question) to log the decision and continue,
  rather than leave the gap or revert.

## Decision

The owner is exercising standing authority over their own repository and
local Bash execution environment to retire CAP-007's enforcement layer,
in favor of unrestricted local Bash/tool permissions for this project —
removing agent-operational friction (permission prompts, allowlist gaps
like `BUG-036`) for routine local development. This ADR records that
decision after the fact, closing the logging gap; it does not undo or
relitigate CAP-007's own review history, which remains valid evidence of
what was built and why.

**In scope (relaxed):**

- In-session Bash execution: any command, no `PreToolUse` gate, no
  permission prompt (`defaultMode: bypassPermissions`).
- Edits under `.claude/**`, including previously write-protected paths,
  when routine development work requires it.
- Resolving implementation blockers (env setup, dependency installs,
  test runs) without stopping to ask, for ordinary MOD-001 dev work.

**Out of scope — unchanged, still require explicit owner confirmation
in-chat** (per the instruction that enabled this mode, and per
`.claude/rules/global/owner-reserved-restrictions.md`, which this ADR
does not amend):

- Real Production deployment/promotion.
- Real paid-service activation/spend.
- Use of real regulated/member/customer data.
- Destructive actions outside the Veyro workspace.
- Destructive remote git operations (force-push, history rewrite).

**Also unchanged:** WIP=1 discipline and module certification gates
(Scenario Review, Code Review, Manual QA, Security/Performance Review,
Gatekeeper certification). MOD-001 still requires its normal gates
before an Approval Certificate is issued; MOD-002+ remain locked. This
decision relaxes agent execution friction, not the certification bar.

## Consequences

- **CAP-007 is RETIRED**, not erased from history: the reviewed v2
  source is preserved in git history (commit `e971523` and earlier), and
  `.claude/security/superseded_v1/` remains on disk unchanged.
  `CAPABILITY_REGISTRY.md` updated to reflect RETIRED status with a
  pointer to this ADR.
- `BUG-036`'s structural blocker (no allowlist entry for
  `pip`/`pytest`/`ruff`/`mypy`) is now moot — those commands execute
  directly in-session. See `BUG-036`'s evidence file, Round 6 section,
  for the real execution this unblocked.
- **Rollback path:** restore CAP-007 by reverting `058ed27`'s two file
  changes (`git revert 058ed27` or manual restoration from
  `git show e971523:.claude/security/bash_guard.py` and the pre-`058ed27`
  `.claude/settings.json`), then re-verify the 194-test guard suite and
  baseline hashes. No other project state depends on the guard's
  absence.
- This ADR does not retroactively bless `058ed27`'s own process gap (no
  `OWN` row at commit time) — it closes that gap now, honestly dated
  after the fact, rather than backdating it.

## Alternatives considered

- **Extend `bash_guard.py`'s Tier-1 allowlist** for just
  `pip`/`pytest`/`ruff`/`mypy` (`BUG-036` Round 2's own draft) and keep
  the guard active: rejected — the owner's actual instruction called for
  full autonomous local Bash, not a narrower allowlist extension, and a
  guard extension would still require its own independent security
  review cycle before use, reintroducing the friction being removed.
- **Leave the gap unlogged:** rejected — violates this project's own
  `OWNER_APPROVALS.md` rule and would leave a false "no owner decision
  recorded" audit trail for a real, already-executed decision.
