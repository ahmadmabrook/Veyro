---
capability: CAP-002 TestSprite CLI
---

# CAP-002 Scope Note — what is and isn't qualified

**Qualified (APPROVED scope, corrected 2026-09-05 per independent Opus review):** exactly `test scaffold` and `test lint` — both genuinely offline, no network call. `doctor` and `usage` are also approved but are **not** offline — both authenticate to `api.testsprite.com` (read-only, non-billed, confirmed via the credit balance staying at 550 across every use). The previous version of this note claimed `test scaffold`/`test lint` were "by extension" joined by `test create`/`code`/`plan` — **that was an overclaim, struck 2026-09-05.** None of those three commands was ever actually run, positively or negatively, and at least some plausibly reach the cloud API. They are not approved until independently tested.

**NOT qualified:** `test create`/`code`/`plan` (never tested, struck from the "by extension" claim above) and any command that triggers a real run against TestSprite's cloud service (`test run`, `test rerun`, `testlist run`, `project create` against real infra) — these consume the account's existing credit balance (550 remaining, Starter plan). This project's owner-reserved restrictions prohibit incurring spend without explicit approval; consuming a pre-purchased credit balance is spend in effect even though the account itself predates this session.

**Consequence for the Manual QA Capability Drill:** TestSprite cannot be used as a live browser/backend/mobile execution engine in MOD-000 without an explicit owner approval entry in `knowledge/00-System/OWNER_APPROVALS.md` authorizing credit spend. Until that exists, TestSprite remains evidence-input-only via its offline surface, and the Manual QA drill's browser/backend/mobile paths must be proven through other means (Claude Browser tools, iOS Simulator MCP, curl, etc.) rather than TestSprite live runs. This is consistent with the standing rule that TestSprite is never a substitute for real Claude manual QA anyway.

**Owner action available if desired:** approve a bounded credit spend (e.g. "up to N credits for MOD-000 qualification only") in `knowledge/00-System/OWNER_APPROVALS.md` to unlock live TestSprite run qualification. Not requested automatically — this note exists so the option is visible, not to push for it.
