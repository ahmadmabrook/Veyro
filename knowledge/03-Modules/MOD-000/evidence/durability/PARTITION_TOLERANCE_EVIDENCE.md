---
doc: PARTITION_TOLERANCE_EVIDENCE
status: EXECUTED (2026-09-05) — SCN-MOD000-073 (PART category)
date: 2026-09-05
---

# SCN-MOD000-073 — Partial MCP-server unavailability doesn't block unrelated MOD-000 work

This scenario's own Steps are retrospective: compile the repeated real
instances of partial MCP unavailability observed across this project's
history and confirm none blocked in-scope work. Compiled 2026-09-05.

## Real, observed instances (this project's own session history)

1. **`claude-flow` — CONNECT_TIMEOUT.** Repeatedly reported as "MCP
   server claude-flow connection timed out after 30000ms" across
   multiple chunks of this project. MOD-000 work (scenario authoring,
   Phase 1-5 execution, all remediation) never used this server and was
   never blocked by its unavailability.
2. **`plugin:github:github` — HTTP 400 "Authorization header is badly
   formatted".** Observed repeatedly this session. Not used for any
   MOD-000 gate (Git operations went through the `git` CLI directly via
   Bash, not this MCP) — zero impact on Phase 1-5 completion.
3. **`claude-design` — HTTP 403 "rejected your claude.ai login".**
   Observed repeatedly this session. Never a dependency of any MOD-000
   scenario or gate — zero impact.
4. **~40 other third-party MCP servers** (e.g. `plugin:data:bigquery`,
   `plugin:engineering:datadog`, `plugin:engineering:pagerduty`,
   `plugin:productivity:asana`, and many more) reported as
   "require authentication before their tools can be used" throughout
   this entire project — none were ever connected, none were ever a
   MOD-000 dependency, and their unavailability has never once affected
   any Phase 1-10 gate.

## Cross-check against durable state: did any of this ever block MOD-000?

No. Phase 1 (deterministic execution), Phase 2 (TestSprite offline),
Phase 3 (negative drills), Phase 4 (reconciliation), and the entirety of
Phase 5's initial review, remediation, second re-review, round-2
remediation, and third capability review all completed — including this
very chunk, executed while `claude-flow`, `plugin:github:github`, and
`claude-design` were simultaneously unavailable per the system's own
reminders. The only capabilities MOD-000 actually depends on (`mcp__notion__*`,
TestSprite CLI, Claude Code harness tools, Browser pane, iOS Simulator
bridge) each connected and worked independently of the unrelated
failures above — a direct demonstration of partition tolerance, not an
inference.

## Result vs. pass criteria

Pass criteria: "Demonstrated repeatedly." Confirmed: at least 3 named,
repeatedly-observed unrelated-server failures, cross-checked against 5
completed phases of unaffected MOD-000 work spanning multiple days.

## Status: PASS
