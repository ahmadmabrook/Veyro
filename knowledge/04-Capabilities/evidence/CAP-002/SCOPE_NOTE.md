---
capability: CAP-002 TestSprite CLI
---

# CAP-002 Scope Note — what is and isn't qualified

**Qualified (APPROVED scope):** offline plan authoring and validation — `test scaffold`, `test lint`, and by extension `test create`/`code`/`plan` up to the point a real execution/`test run` is triggered. Safe to use with zero spend risk.

**NOT qualified, deliberately not attempted this chunk:** any command that triggers a real run against TestSprite's cloud service (`test run`, `test rerun`, `testlist run`, `project create` against real infra) — these consume the account's existing credit balance (550 remaining, Starter plan). This project's owner-reserved restrictions prohibit incurring spend without explicit approval; consuming a pre-purchased credit balance is spend in effect even though the account itself predates this session.

**Consequence for the Manual QA Capability Drill:** TestSprite cannot be used as a live browser/backend/mobile execution engine in MOD-000 without an explicit owner approval entry in `knowledge/03-ExternalGates/` authorizing credit spend. Until that exists, TestSprite remains evidence-input-only via its offline surface, and the Manual QA drill's browser/backend/mobile paths must be proven through other means (Claude Browser tools, iOS Simulator MCP, curl, etc.) rather than TestSprite live runs. This is consistent with the standing rule that TestSprite is never a substitute for real Claude manual QA anyway.

**Owner action available if desired:** approve a bounded credit spend (e.g. "up to N credits for MOD-000 qualification only") in `knowledge/03-ExternalGates/` to unlock live TestSprite run qualification. Not requested automatically — this note exists so the option is visible, not to push for it.
