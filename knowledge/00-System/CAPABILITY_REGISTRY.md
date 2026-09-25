---
doc: CAPABILITY_REGISTRY
status: LIVE
updated: 2026-09-25 (Round 5 — final independent qualification review, P0=0/P1=0, `APPROVED`: fresh-context `veyro-security-reviewer` reviewed all 9 rule files and their Stage-5 evidence, independently re-derived the true current governed HEAD as `8e90680e8e8bcbd86e5136b6181371ac8161eee7` (correcting the dispatch brief's stale `14d1337`), confirmed `RULE-002`'s `scope: global` and `RULE-004`'s backend-scope addition both correct with no overshoot, re-confirmed all 7 prior-round P1 closures unregressed, and declined to promote either of the 2 carried-forward observations to P1 for lack of a present material defect. 3 P2 + 1 Editorial residual found, all disclosed and non-blocking (1 new P2 — stale binding text in 7 of 9 evidence files — fixed same session by the orchestrating session). `RULE-001` through `RULE-009` are now `APPROVED` and `ACTIVE`. `BUG-035` is CLOSED. See `knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`. Prior updates: post-round-4 remediation (owner corrected 2 scope-gap P1s, commits `183acd5`/`14d1337`), round 4 (2026-09-25, P0=0/P1=3), round 3 (2026-09-22, P1-A closed, P1-Q found), round 2 (2026-09-19, P1-A found), round 1 registration (P0=0/P1=4/P2=8/Editorial=7). Earlier: 2026-09-12, Phase 9 restoration proof, second Gatekeeper pass P1-4 — corrected the resolution-budget section's stale CAP-001-through-CAP-006 range to include CAP-007)
---

# Capability Registry

Every row here is a capability this project may depend on. `review_status: APPROVED` requires both `qualified_by` (who ran the tests, may be Sonnet) AND `approved_by` (the Opus assurance role that independently reviewed the evidence and made the final call) populated — a row with only `qualified_by` is at most `QUALIFIED`. This table is the honest current state, not aspirational.

**2026-09-05 update (round 2):** a third, distinct fresh-context `veyro-security-reviewer` invocation (not the same run that downgraded CAP-001 on the earlier 2026-09-05 pass) independently evaluated the CAP-001 bounded re-test evidence and, separately, CAP-005/CAP-006's existing qualification drill. All three closed — see verdicts and binding caveats below. Full reasoning: `knowledge/03-Modules/MOD-000/evidence/bugs/BUG-006-capability-qualification-ran-on-sonnet.md`, `knowledge/03-Modules/MOD-000/evidence/bugs/BUG-009-cap-005-006-not-distinctly-reviewed.md`.

| id | capability | provenance | version | content_hash | scope | review_status | qualified_by | qualified_date | approved_by | approved_date | last_reviewed_at | next_review_due | rollback_target | evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CAP-001 | Notion MCP (`mcp__notion__*`) | **Third-party** hosted MCP (Notion's own server), reached via a user-authorized connector | live server, tools observed 2026-08-31 | N/A (hosted) | **Intended:** the Veyro Engineering Control Plane page tree (9 named databases) only. **Demonstrated 2026-09-05:** page creation outside that tree is NOT technically prevented — a `notion-create-pages` call with no `parent` succeeded (see `BOUNDED_RETEST_2026-09-05.md`). **Inferred, untested:** read/update access to pre-existing non-Veyro workspace content — never actually probed; do not assert this as confirmed. Effective blast radius: the owner's entire personal Notion workspace, enforced only by this project's own behavioral discipline (`.claude/rules/notion-mcp-scope-discipline.md`), not by Notion's permission model. | **APPROVED, scope de-rated, with binding caveats** (2026-09-05) — see BUG-006 §"Bounded re-test executed" and ADR-003 for the full caveat set, which the approval does not hold without | veyro-implementer (Sonnet) | 2026-08-31 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context — third, distinct 2026-09-05 invocation) | 2026-09-05 | 2026-09-05 | 2026-12-04 (90 days) | Revert to `knowledge/`-only operation; the Notion mirror is non-load-bearing | `knowledge/05-QA/capability-evidence/CAP-001/{positive_test,negative_test,BOUNDED_RETEST_2026-09-05}.md` |
| CAP-002 | TestSprite CLI | Third-party CLI, installed on host (`~/.nvm/.../bin/testsprite`) | 0.8.0 | N/A (external binary, not project-controlled) | **Narrowed 2026-09-05** to exactly what was tested: `test scaffold`, `test lint` (offline, no network); `doctor`, `usage` (authenticate to `api.testsprite.com`, read-only, non-billed — corrected from "offline"). `test create`/`test code`/`test plan` and all live-cloud commands (`test run`/`test rerun`/`testlist run`) are explicitly OUT of scope — **not** approved "by extension," they were never tested. | APPROVED (narrowed scope above) | veyro-test-author (Sonnet) | 2026-08-31 | veyro-security-reviewer (Opus, fresh context) | 2026-09-05 | 2026-09-05 | 2026-12-04 (90 days) | Revoke, fall back to manual TestSprite CLI review | `knowledge/05-QA/capability-evidence/CAP-002/{positive_test,negative_test,SCOPE_NOTE}.md` |
| CAP-003 | `docx` skill | Anthropic first-party public skill (`/mnt/skills/public/docx`) | as shipped in this environment | not independently hashed (first-party, trusted by default) | read/create/edit .docx files | APPROVED (first-party default-trust, per policy exemption) | bootstrap session | 2026-08-31 | N/A (exemption clause) | N/A | N/A (exemption) | N/A (exemption) | N/A (harness-native, no rollback needed) | used to read baseline docx during MOD-000 bootstrap |
| CAP-004 | Bash/Read/Write/Edit (core harness tools) | First-party Claude Code harness | N/A | N/A | full project filesystem + shell | APPROVED (first-party/harness exemption) | N/A | N/A | N/A (exemption clause) | N/A | N/A (exemption) | N/A (exemption) | N/A (harness-native, no rollback needed) | N/A |
| CAP-005 | Browser tools (`mcp__Claude_Browser__*`) | First-party Claude Code harness browser pane | as shipped in this environment | N/A (harness-native) | Manual-QA evidence gathering against **public, unauthenticated, stateless** endpoints only. No authenticated sessions, no owner accounts, no credential entry, no real member data into any form. Web page content read via `read_page`/`get_page_text` is untrusted input (prompt-injection surface), never instruction. | **APPROVED** (2026-09-05, distinct fresh-context Opus review; approved under the first-party/harness exemption, no negative test required by policy, but scope caveats above are binding) | veyro-manual-qa (fresh context, Opus) | 2026-09-04 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context — distinct from the 2026-09-04 qualifying run) | 2026-09-05 | 2026-09-05 | 2026-12-04 (90 days) | Fall back to owner-assisted manual QA for Web surfaces | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |
| CAP-006 | iOS Simulator control (`mcp__Claude_Code_iOS_Simulator__*`) | First-party Claude Code harness simulator bridge | as shipped in this environment | N/A (harness-native) | Boot/attach/interact with iOS Simulator, **stock Apple apps only** — may not launch, tap, inspect, or read data from any app not belonging to this project (the simulator carries unrelated third-party apps from another project). Destructive `simctl` operations (erase, device deletion, installing a non-Veyro build) are out of scope. Any environment setting changed during a drill must be reverted and re-verified. | **APPROVED** (2026-09-05, distinct fresh-context Opus review — satisfies stage 5 on its own merits, positive+negative tests both real) | veyro-manual-qa (fresh context, Opus) | 2026-09-04 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context — distinct from the 2026-09-04 qualifying run) | 2026-09-05 | 2026-09-05 | 2026-12-04 (90 days) | Fall back to owner-assisted manual QA for iOS surfaces | `evidence/manual-qa/CAPABILITY_DRILL_PHASE5_RERUN.md` |
| CAP-007 | `.claude/security/bash_guard.py` — PreToolUse Bash security guard, v2 allow-by-construction (registered 2026-09-07; APPROVED 2026-09-08; ACTIVATED and live-verified 2026-09-08) | Project-authored (this project's own sessions); no third-party/external source | v2, Round-3-P1-remediated (2026-09-07); superseded v1 preserved at `.claude/security/superseded_v1/`, not a version of this capability | SHA-256 of `bash_guard.py`: `315df926ff607fb0560f4f1842646d28eeb2a059b771130db5002edb347cc245` (independently recomputed and confirmed exact-match 2026-09-08; recompute and update this cell whenever the file changes — see governance note below) | PreToolUse hook input only: reads one stdin JSON payload, classifies one Bash command string per this file's allow-by-construction rules, prints one JSON allow/deny decision to stdout. Filesystem access limited to SHA-256-hashing the 7 fixed paths in its own `_ALLOWED_PYTHON_SCRIPTS` map (read-only). **Now live and active** — the owner manually applied the drafted `.claude/settings.json` activation patch (`hooks.PreToolUse` registering this guard on the `Bash` matcher, timeout 10; `.claude/security/**`/`CLAUDE.md`/`.mcp.json` deny additions), and a fresh Claude Code session ran the full 14-row live-test matrix from `BUG-013-022-023-OWNER-SETTINGS-PATCH.md` — all 14 rows PASS. See `evidence/security/BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md`. | **APPROVED (2026-09-08, fourth independent fresh-context Opus review — final owner-authorized verification pass on the Round 3 P1 remediation; distinct from the Round 1/2/3 reviewers and from the 2026-09-07 Sonnet remediation session).** Result: P0=0, P1=0, P2=6, Editorial=9. The activation caveat this approval was conditioned on (`.claude/security/**` write-protection) is now satisfied: the owner's applied patch includes it, and live testing (Edit-tool attempt on `bash_guard.py`) confirms it actually denies. The 6 P2 findings (`grep --exclude-from`/similar unchecked-flag-argument gap; a FIFO-at-pinned-path hang bounded but not eliminated by the patch's `timeout: 10`; cwd-vs-REPO_ROOT path-resolution divergence; unchecked `$`/glob expansion in two argument slots; the 5 pre-existing Round 3 P2s) remain accepted-known residuals, not closed, tracked for a future remediation pass; the 9 Editorial findings remain recorded, non-blocking. Full record: `evidence/security/BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md`, `evidence/security/BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md`. | veyro-security-reviewer (Opus, fresh context — 3 prior review rounds, most recently Round 3, 2026-09-07); remediation implemented by this session (Sonnet, 2026-09-07); positive/negative regression evidence re-run and extended by the approving reviewer itself, 2026-09-08; live activation matrix run by this session (Sonnet, 2026-09-08) | 2026-09-07 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context — fourth independent review, distinct from all three Round 1-3 reviewers) | 2026-09-08 | 2026-09-08 | 2026-12-07 (90 days) | Remove the `PreToolUse` key from `.claude/settings.json` and start a fresh session (rollback returns to deny-glob-only enforcement, per `BUG-013-022-023-OWNER-SETTINGS-PATCH.md` Part 6) — no code deletion required | `knowledge/03-Modules/MOD-000/evidence/security/{BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md,BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md,BASH_GUARD_V2_ROUND3_P1_REMEDIATION_2026-09-07.md,BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md,BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md}` |
| RULE-001 | `.claude/rules/infra/iac.md` — Infra/SRE IaC baseline (MOD-001, `ADR-005` Decision 2) | Project-authored (this project's own sessions, via `veyro-infra-sre-engineer`); no third-party/external source | 4 (2026-09-25, round-4 owner patch commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc` — `paths:` frontmatter added, no body-text change; unaffected by the later `183acd5`/`14d1337` commits, which touched only `release.md`/`secrets.md`) | SHA-256: `2cb737ce1b36ec78dab29ee952289d5a666f42b328886f05d9318c4bef912175` (recomputed by this session via `shasum -a 256`, independently confirmed byte-identical by a distinct round-4 `veyro-security-reviewer` hash check) | Governs `infra/**`/`.github/workflows/**` (now machine-enforced via `paths:` frontmatter) — read/guidance only, no execution/filesystem/network scope of its own (a Rule file, not executable code) | **APPROVED** (Round 5, 2026-09-25, fresh-context `veyro-security-reviewer`, P0=0/P1=0 — round-2 P1-A / round-3 stage-5-evidence gap / round-4 scope-gap P1s all re-confirmed genuinely closed and unregressed; frontmatter valid; Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — path-scope PASS, see `knowledge/05-QA/capability-evidence/RULE-001/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-infra-sre-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-001/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |
| RULE-002 | `.claude/rules/infra/secrets.md` — Infra/SRE secrets-externalization baseline (global binding, corrected commit `14d1337`; MOD-001, `ADR-005` Decision 2) | Project-authored, via `veyro-infra-sre-engineer` | 4 (2026-09-25 — `5ad7d3c` added `paths:` frontmatter; `183acd5` replaced it with `scope: global`, fixing round-4's P1-2 scope gap; `14d1337` corrected the file's own H1 heading from "(`infra/**` binding)" to "(global binding)" to match, closing a self-contradiction a later independent review found) | SHA-256: `e61455b487c32a79e2689a1580fdd41fa4cf331e7dcb75cc31b00058d30d1eb1` (recomputed by this session via `shasum -a 256` at commit `14d1337`) | `scope: global` — applies repo-wide by design (secrets discipline is not infra-specific; control 1's own text and control 3's `.gitignore`/evidence-file references are unconditional) — read/guidance only | **APPROVED** (Round 5, 2026-09-25 — `scope: global` confirmed legitimate: control 1's repo-wide no-secret-commit invariant admits no narrower correct path list, and the "does not pollute unrelated contexts" half of EIP H.5 is satisfied (controls 2-3 are inert outside their own applicable contexts, immaterial token cost, same shape as this project's other global rules); `N/A (scope: global)` confirmed a valid Stage-5 disposition; Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — see `knowledge/05-QA/capability-evidence/RULE-002/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-infra-sre-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-002/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |
| RULE-003 | `.claude/rules/infra/observability.md` — Infra/SRE observability/SLO/DR-evidence baseline (MOD-001, `ADR-005` Decision 2) | Project-authored, via `veyro-infra-sre-engineer` | 2 (2026-09-25, round-4 owner patch commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc` — `paths:` frontmatter added, no body-text change; unaffected by the later `183acd5`/`14d1337` commits) | SHA-256: `64ea2816088f625ebd8abe1c6459840fe69e453f1f001907c54377b45c547664` (recomputed by this session via `shasum -a 256`, independently confirmed byte-identical by a distinct round-4 `veyro-security-reviewer` hash check) | Governs `infra/**`/`.github/workflows/**` (now machine-enforced via `paths:` frontmatter) — read/guidance only | **APPROVED** (Round 5, 2026-09-25, P0=0/P1=0 — the `tools/**` validator-tooling gap re-confirmed a non-gating P2 (P2-2), not required to close for approval per EIP §4.3's Infra/SRE scoping and `IMPLEMENTATION.md`'s per-tool evidence binding; Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — path-scope PASS, see `knowledge/05-QA/capability-evidence/RULE-003/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-infra-sre-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-003/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |
| RULE-004 | `.claude/rules/infra/release.md` — Infra/SRE release/rollback/canary/cost baseline (`infra/**`, CI, and backend Python binding, corrected commit `14d1337`; MOD-001, `ADR-005` Decision 2) | Project-authored, via `veyro-infra-sre-engineer` | 5 (2026-09-25 — `5ad7d3c` added `paths:` frontmatter (`infra/**`/`.github/workflows/**`); `183acd5` added a third glob, `backend/**/*.py`, closing round-4's P1-1 scope gap; `14d1337` corrected the file's own H1 heading from "(`infra/**` binding)" to "(`infra/**`, CI, and backend Python binding)" to match, closing a self-contradiction a later independent review found) | SHA-256: `74dc432ec2482a1ae09dfa2cbedc3e50e881c1068a2b675caa06b64db67683a2` (recomputed by this session via `shasum -a 256` at commit `14d1337`) | Governs `infra/**`/`.github/workflows/**`/`backend/**/*.py` (now machine-enforced via `paths:` frontmatter) — read/guidance only | **APPROVED** (Round 5, 2026-09-25, P0=0/P1=0 — backend scope confirmed correct with no overshoot: `backend/**/*.py` reaches the Stage-5-qualified rollback-trigger fixture `backend/app/main.py` and grants no privilege beyond added constraints; round-1 manual-override-carve-out closure re-confirmed unregressed. Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — path-scope PASS across all 3 globs, see `knowledge/05-QA/capability-evidence/RULE-004/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-infra-sre-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-004/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |
| RULE-005 | `.claude/rules/backend/architecture.md` — Backend modular-monolith architecture boundaries (MOD-001, `ADR-005` Decision 2) | Project-authored, via `veyro-backend-engineer` | 3 (2026-09-25, round-4 owner patch commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc` — `paths:` frontmatter added, no body-text change) | SHA-256: `8d05b2844480ea9ccab65b8a557368727c132c6367b259507f587af55d1507ad` (recomputed by this session via `shasum -a 256`, independently confirmed byte-identical by a distinct round-4 `veyro-security-reviewer` hash check) | Governs `backend/**/*.py` (now machine-enforced via `paths:` frontmatter) — read/guidance only | **APPROVED** (Round 5, 2026-09-25, P0=0/P1=0 — round-1 transaction/idempotency/reconciliation coverage (with `api.md`) re-confirmed unregressed; no P1 of its own in any round; Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — path-scope PASS, see `knowledge/05-QA/capability-evidence/RULE-005/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-backend-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-005/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |
| RULE-006 | `.claude/rules/backend/api.md` — Backend API request/response and permission boundaries (MOD-001, `ADR-005` Decision 2) | Project-authored, via `veyro-backend-engineer` | 3 (2026-09-25, round-4 owner patch commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc` — `paths:` frontmatter added, no body-text change) | SHA-256: `1694fb09d14026dcf947d1e425134f7180ca5f5b5cdc592efb79a90e83c0d7b3` (recomputed by this session via `shasum -a 256`, independently confirmed byte-identical by a distinct round-4 `veyro-security-reviewer` hash check) | Governs `backend/**/*.py` (now machine-enforced via `paths:` frontmatter) — read/guidance only | **APPROVED** (Round 5, 2026-09-25, P0=0/P1=0 — round-1 transaction/idempotency/reconciliation coverage (with `architecture.md`) re-confirmed unregressed; no P1 of its own in any round; Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — path-scope PASS, see `knowledge/05-QA/capability-evidence/RULE-006/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-backend-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-006/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |
| RULE-007 | `.claude/rules/backend/database.md` — Backend PostgreSQL tenant isolation (RLS) and migration safety (MOD-001, `ADR-005` Decision 2) | Project-authored, via `veyro-backend-engineer` | 2 (2026-09-25, round-4 owner patch commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc` — `paths:` frontmatter added, no body-text change) | SHA-256: `9483ab4aa9df14ebfe38192b89fecd221d1b0fc9b93839d9579878fe2fbe7e76` (recomputed by this session via `shasum -a 256`, independently confirmed byte-identical by a distinct round-4 `veyro-security-reviewer` hash check) | Governs `backend/**` schema/models/migrations (now machine-enforced via `paths:` frontmatter) — read/guidance only | **APPROVED** (Round 5, 2026-09-25, P0=0/P1=0 — no P1 of its own in any round; Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — path-scope PASS, see `knowledge/05-QA/capability-evidence/RULE-007/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-backend-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-007/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |
| RULE-008 | `.claude/rules/backend/concurrency.md` — Backend optimistic concurrency for mutable aggregates (`DOM-002`) (MOD-001, `ADR-005` Decision 2) | Project-authored, via `veyro-backend-engineer` | 2 (2026-09-25, round-4 owner patch commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc` — `paths:` frontmatter added, no body-text change) | SHA-256: `f618731725f88d4ea811f6f7420a837614cbaa89b4c8050d2c8f45e03f321f53` (recomputed by this session via `shasum -a 256`, independently confirmed byte-identical by a distinct round-4 `veyro-security-reviewer` hash check) | Governs `backend/**` mutable-aggregate persistence (frontmatter now scopes to `backend/**/*.py` specifically — round 4 flagged this as a non-gating P2, since a raw `.sql` schema-adjacent fixture would not match) — read/guidance only | **APPROVED** (Round 5, 2026-09-25, P0=0/P1=0 — no P1 of its own in any round; the `backend/**/*.py`-only glob missing raw `.sql` files re-confirmed a non-gating P2 (P2-3), not required to close for approval; Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — path-scope PASS, see `knowledge/05-QA/capability-evidence/RULE-008/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-backend-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-008/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |
| RULE-009 | `.claude/rules/backend/performance.md` — Backend load-scope and observability baseline (MOD-001, `ADR-005` Decision 2) | Project-authored, via `veyro-backend-engineer` | 2 (2026-09-25, round-4 owner patch commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc` — `paths:` frontmatter added, no body-text change) | SHA-256: `805e669248cc252eec0b5995b9e1702b3e6e6ffd033d70f70407d50e38ad4e5c` (recomputed by this session via `shasum -a 256`, independently confirmed byte-identical by a distinct round-4 `veyro-security-reviewer` hash check) | Governs `backend/**/*.py` (now machine-enforced via `paths:` frontmatter) — read/guidance only | **APPROVED** (Round 5, 2026-09-25, P0=0/P1=0 — no P1 of its own in any round; Stage-5 evidence bound to current governed HEAD `8e90680e8e8bcbd86e5136b6181371ac8161eee7` — path-scope PASS, see `knowledge/05-QA/capability-evidence/RULE-009/`; `BUG-035` CLOSED — see `RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`) | veyro-backend-engineer (Sonnet); stage-5 evidence run by veyro-test-author (Sonnet), independently reviewed by veyro-security-reviewer (Opus) | 2026-09-25 | veyro-security-reviewer (Opus, `claude-opus-5`, fresh context, Round 5, 2026-09-25 — no participation in rounds 1-4 or in producing Stage-5 evidence) | 2026-09-25 | 2026-09-25 | 2026-12-24 (90 days) | Remove file / revert to pre-migration state | `knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`, `knowledge/05-QA/capability-evidence/RULE-009/POSITIVE_NEGATIVE_EVAL_2026-09-25.md` (current) |

**CAP-007 governance notes (added 2026-09-07, updated 2026-09-08 — now ACTIVE):**
- **APPROVED and ACTIVE.** `review_status` is `APPROVED` (fourth independent review, 2026-09-08). The owner then manually applied the drafted activation patch, and a fresh-session live-test matrix (14/14 PASS) confirmed the guard is genuinely enforcing, not merely reviewed-and-inert. See `BUG-013-022-023-OWNER-SETTINGS-PATCH.md` (the patch) and `BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md` (the live proof).
- **`lifecycle_status`:** now instantiated as `ACTIVE` (see the "Lifecycle status" section below), per the approving reviewer's own instruction to set it in the same commit that installs and live-verifies the PreToolUse hook.
- **`qualified_by` accuracy correction (2026-09-08):** the prior entry misattributed test-running to the Opus reviewers; `CAPABILITY_POLICY.md` defines `qualified_by` as the session that ran the positive/negative tests, which was the Sonnet remediation session — corrected above. The Opus reviewers' role (independent evaluation and final decision) is captured in `approved_by`, per policy.
- **`evidence` path convention note:** this row's evidence lives under `knowledge/03-Modules/MOD-000/evidence/security/` rather than `knowledge/05-QA/capability-evidence/CAP-007/` (the location most other capability rows use) — flagged as a minor convention deviation, not moved, since the files are real, current, and correctly linked; a future session may relocate/mirror them if this becomes disruptive.
- **Required module binding:** MOD-000. Now added to `knowledge/03-Modules/MOD-000/evidence/module-capabilities.yaml` as of this activation — MOD-000's Bash surface now genuinely depends on this guard for its security posture.
- **Content-hash update procedure:** recompute `sha256sum .claude/security/bash_guard.py` and update this row's `content_hash` cell in the same commit as any future edit to that file — the same one-line-diff discipline the file's own internal `_ALLOWED_PYTHON_SCRIPTS` map now uses for the 7 scripts it trusts (see that map's own comment in `bash_guard.py` for the parallel governance rule on *those* files).

## Resolution budget (EIP §4.2, added 2026-09-05 — final Phase 5 re-review NF-5)

EIP §4.2 requires: "Before discovery begins, the CAP record must state a
resolution budget: default maximum 45 minutes of active orchestration
and, when runtime token telemetry is observable, 50,000 model tokens."
F5-016's fix added the rule to `CAPABILITY_POLICY.md`'s prose but never
instantiated a per-record field here, which this correction closes:
**every capability row in this registry (CAP-001 through CAP-007) uses
the EIP default resolution budget (45 min / 50,000 tokens) — none has a
registered override.** The enforcement mechanism for this budget is
`knowledge/05-QA/tools/resolution_bound.py` (built and proven 2026-09-05,
see `SCN-MOD000-067`); it is not yet wired into any live capability's
discovery flow, so this budget is currently a stated constraint, not yet
a technically-enforced one, for any row above.

## Lifecycle status (added 2026-09-05 — fourth Phase 5 re-review NF4-4)

`CAPABILITY_POLICY.md`'s supply-chain review-fields table lists
`lifecycle_status` (`ACTIVE`/`DEPRECATED`/`REVOKED`) as required on every
registry entry, but it was never instantiated anywhere — not as a
registry column, not in `CAPABILITY_EVAL_INDEX.md`. Instantiated here
rather than as a 15th column on an already-wide table: **all 16
capabilities (CAP-001 through CAP-007, RULE-001 through RULE-009) are
`ACTIVE`.** CAP-007 joined this list 2026-09-08 upon live activation
verification; RULE-001 through RULE-009 joined 2026-09-25 upon Round 5
`APPROVED` (see below). None is `DEPRECATED` or `REVOKED`.
`CAPABILITY_EVAL_INDEX.md` mirrors this.

**RULE-001 through RULE-009 (added 2026-09-19) are now `ACTIVE` and
`APPROVED` (2026-09-25, Round 5).** History: round 1 (2026-09-19):
P0=0/P1=4; round 2 (2026-09-19): P0=0/P1=1, P1-A found; round 3
(2026-09-22): P0=0/P1=1, P1-A closed but a new P1-Q found — no stage-5
qualification-test evidence existed for the set; a same-day follow-up
produced that evidence and confirmed EIP H.5's path-scope test
genuinely FAILED for all 9 files since none had `paths:` frontmatter.
The owner then applied a `paths:`-frontmatter patch (commit
`5ad7d3cbb67f0433031850b0e3180f7a4872cccc`). Round 4 (2026-09-25):
P0=0/P1=3 — BLOCKED (2 new scope-gap P1s the patch itself introduced,
plus 1 stale-evidence P1). Post-round-4 remediation (same day): the
owner corrected both scope gaps (commits `183acd535e6786f1edc1993a5ef6f13afd13a4ec`,
`14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a`); Stage-5 evidence re-run and
independently spot-checked sound. **Round 5 (2026-09-25, fresh-context
`veyro-security-reviewer`, no memory of rounds 1-4): P0=0, P1=0 —
APPROVED.** 3 P2 + 1 Editorial residual found, all disclosed and
non-blocking, carried forward for a future remediation pass (not
required for `APPROVED`, per the review's own P0/P1-only mandate): a
`tools/**` validator-scope gap in `observability.md` (P2-2, carried from
round 4); a raw-`.sql`-file gap in `concurrency.md`'s `backend/**/*.py`
glob (P2-3, carried from round 4); a real, now-fixed staleness defect
where 7 of the 9 Stage-5 evidence files' binding text still named the
superseded `183acd5` rather than the true current governed HEAD
`8e90680e8e8bcbd86e5136b6181371ac8161eee7` (P2-1, new, fixed same
session by the orchestrating session, not the reviewer); and both
`iac.md`/`observability.md`'s H1 headings omitting `.github/workflows/**`
from their own label despite covering it (Editorial-1, new, not fixed).
`BUG-035` is **CLOSED**. See
`knowledge/03-Modules/MOD-001/evidence/model-routing/{RULE_QUALIFICATION_REVIEW_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND2_2026-09-19,RULE_QUALIFICATION_REVIEW_ROUND3_2026-09-22,RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25,RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25}.md`.
These 9 rows may now be treated as governing/enforced content — the
`backend/**`/`infra/**`/CI implementation gate `ADR-005` Decision 2 named
is cleared.

## Qualification history

- CAP-001 Notion MCP: qualified 2026-08-31. A first independent Opus review (2026-09-05) downgraded it to QUALIFIED pending a bounded 3-item re-test. A second, distinct Opus review (2026-09-05, same day) evaluated that re-test's evidence and approved it with binding caveats — see `BUG-006`, `ADR-003`, `BUG-010` (the residual connector-scope-vs-policy deviation, filed separately, not certification-blocking).
- CAP-002 TestSprite: qualified 2026-08-31, tests re-run/extended 2026-09-01 (Phase 2). Independent Opus review (2026-09-05) confirmed `APPROVED` with the scope narrowed to what was actually tested — see BUG-006 for the specific corrections made.
- CAP-005/CAP-006: qualified 2026-09-04 by a real fresh-context Opus manual-QA run. **Fail-closed note, recorded honestly:** the mandatory §12.1 manual-QA evidence these two capabilities produced (closing SCN-MOD000-061) was gathered while they sat at `QUALIFIED`, not `APPROVED` — a real, if narrow, violation of `CAPABILITY_POLICY.md`'s "no module task may depend on a capability whose review_status is not APPROVED" rule at the time. The underlying evidence itself is sound (independently confirmed by a distinct 2026-09-05 review, including a byte-level Content-Length cross-check on the CAP-005 positive test), so it is not being discarded or re-run — but the sequencing gap is not hidden. Both capabilities were independently re-reviewed and closed APPROVED 2026-09-05 — see BUG-009.

- CAP-007 (`.claude/security/bash_guard.py`): registered 2026-09-07 at `QUALIFIED — NOT APPROVED` (Sonnet-only implementation, no Opus review yet). A fourth independent fresh-context Opus review (2026-09-08, owner-authorized as a final verification pass on the Round 3 P1 remediation) evaluated the fix, ran the existing 194-test suite plus its own ~250 fresh adversarial fixtures, found P0=0/P1=0 (6 P2 + 9 Editorial, none activation-blocking on their own), and **APPROVED** it — conditional on the eventual `.claude/settings.json` activation patch including `.claude/security/**` write-protection, which the reviewer determined is a certification-blocking weakness for activation specifically (not a code defect). See `BASH_GUARD_V2_ROUND3_P1_REMEDIATION_2026-09-07.md` and `BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md`. **Update, same day:** the owner applied the drafted activation patch and a fresh-session live-test matrix (14/14 PASS) confirmed the guard genuinely enforcing — CAP-007 is now `APPROVED` and `ACTIVE`. See `BUG-013-022-023-LIVE-ACTIVATION-VERIFICATION-2026-09-08.md`.

- RULE-001 through RULE-009 (MOD-001's `backend/`/`infra/` rule-family
  content, `ADR-005` Decision 2): drafted by `veyro-infra-sre-engineer`/
  `veyro-backend-engineer` (Sonnet), applied by the owner 2026-09-19
  (commit `3632764e44522376277d96441bee847d148843fa`, `BUG-034` closed on
  the write-access finding). Three independent fresh-context Opus
  qualification reviews have run: round 1 (2026-09-19) **BLOCKED**
  (P0=0, P1=4, P2=8, Editorial=7); round 2 (2026-09-19, after an owner
  remediation) **BLOCKED** (P0=0, P1=1 — P1-A, an unauthorized CI-Action
  publisher carve-out); round 3 (2026-09-22, after a further owner
  remediation closing P1-A) **BLOCKED** (P0=0, P1=1 — P1-Q, no stage-5
  positive/negative qualification-test evidence exists for any of the 9
  files). A same-day follow-up session then produced that missing
  content-level evidence (`veyro-test-author`, Sonnet) and had it
  independently reviewed (`veyro-security-reviewer`, Opus) — 2 real
  defects were found and fixed (a credential-shaped fixture string, and
  a `QUALIFIED` header/table claim not earned since the path-scope half
  had failed), plus 3 accuracy errors in RULE-001's own evidence. **The
  review confirmed, directly and reproducibly, that EIP H.5's path-scope
  test genuinely FAILS for all 9 files: none has `paths:` frontmatter,
  so all 9 load unconditionally regardless of path** — a real,
  owner-gated blocker, since adding that frontmatter requires editing
  `.claude/rules/**`, which no session may do. See `BUG-035`. Registered
  at `BLOCKED`, not `APPROVED`, per `CAP-007`'s own precedent of
  registering a capability before it clears qualification. **The owner
  then applied that `paths:`-frontmatter patch (commit
  `5ad7d3cbb67f0433031850b0e3180f7a4872cccc`); round 4 (2026-09-25, fresh
  independent Opus `veyro-security-reviewer`, no memory of rounds 1-3)
  found the patch itself introduces 3 new P1s** — P1-1 (`release.md`'s
  new `infra/**`-only scope excludes `backend/**`, where its own
  Stage-5-qualified rollback-trigger negative fixture lives, and no
  backend rule covers rollback triggers); P1-2 (`secrets.md`'s new
  `infra/**`-only scope is narrower than its own repo-wide "no secret...
  in any form" control text, and nothing else covers non-infra secrets);
  P1-3 (all 9 Stage-5 evidence files remain bound to the pre-patch
  commit, now stale). **Verdict: P0=0, P1=3 — BLOCKED.** Frontmatter
  validity and all prior-round P1 closures (rollback-override carve-out,
  backend transaction/idempotency/reconciliation coverage, the
  `iac.md` CI-Action no-publisher-carve-out) were independently
  re-verified genuinely unregressed. An owner decision on the P1-1/P1-2
  scope questions, a fresh Stage-5 evidence re-run bound to the current
  commit (P1-3), and a fifth independent qualification review are all
  required before any of the 9 may read `APPROVED`. See `BUG-035`'s
  "Round 4" section and
  `RULE_QUALIFICATION_REVIEW_ROUND4_2026-09-25.md`.

  **Post-round-4 remediation, same day.** The owner corrected both
  scope-gap P1s: commit `183acd535e6786f1edc1993a5ef6f13afd13a4ec` added
  `backend/**/*.py` to `release.md`'s `paths:` and replaced
  `secrets.md`'s `scope: path`/`paths:` with `scope: global`; a further
  commit, `14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a` (**current governed
  HEAD**), corrected both files' own H1 headings (which had briefly still
  read "(`infra/**` binding)" even after the scope changed) to match —
  `release.md` now reads "(`infra/**`, CI, and backend Python binding)",
  `secrets.md` now reads "(global binding)". `veyro-test-author` (Sonnet)
  then re-ran Stage-5 evidence for all 9 rule files bound to `14d1337`,
  writing new `POSITIVE_NEGATIVE_EVAL_2026-09-25.md` files (the
  2026-09-22 files retained as historical record): the 7 files whose
  scope didn't change in this remediation got a refreshed commit binding
  and a path-scope PASS reasoning now that the mechanism is real;
  `RULE-004` got a new third path-scope case proving its own
  Stage-5-qualified rollback-trigger fixture (`backend/app/main.py`) is
  now genuinely reachable under the added `backend/**/*.py` glob;
  `RULE-002` recorded its path-scope disposition as `N/A (scope: global)`
  — explicitly neither `PASS` nor `FAIL`, since a global-scope rule has
  no non-matching path to construct a test against, consistent with
  `.claude/rules/global/owner-reserved-restrictions.md`'s existing
  precedent for the same shape. An independent, fresh-context Opus
  `veyro-security-reviewer` then evaluated this new evidence: 7 of the 9
  files were found sound; `RULE-002` and `RULE-004` were found bound to
  the now-superseded `183acd5` rather than the further `14d1337` commit
  the owner pushed mid-session (a real staleness defect, not a reasoning
  error — the underlying glob-matching and content-level analysis in
  both files was independently confirmed correct once re-bound). Both
  fixed directly by this orchestrating session, re-verified against
  primary sources (`git show`, `shasum -a 256`, direct file reads) rather
  than taken on trust. **All 9 Stage-5 evidence files are now sound and
  bound to the current governed commit `14d1337`.** `RULE-001` through
  `RULE-009` remain `BLOCKED`, not `APPROVED` — no Round 5 qualification
  review was run this session, per explicit instruction; that review is
  the next legally required step, and it should bind to `14d1337`, not
  `183acd5`. See `BUG-035`'s "Round 4 follow-up" sections.

  **Round 5 (2026-09-25, same-day follow-up session): APPROVED —
  P0=0, P1=0.** A fresh, independent `veyro-security-reviewer` (Opus, no
  memory of rounds 1-4) reviewed all 9 files and their Stage-5 evidence
  against the full 8-point check list this project's Round 5 mission
  specified. The reviewer's own bootstrap re-derivation found the true
  current governed HEAD had moved again, to `8e90680e8e8bcbd86e5136b6181371ac8161eee7`
  (this repo's own prior session's evidence/registry commit, which
  touched nothing under `.claude/rules/**`) — corrected from the
  dispatch brief's `14d1337`, independently, before trusting anything
  else. `RULE-002`'s `scope: global` was confirmed to both correctly fit
  its repo-wide control text and satisfy EIP H.5's non-pollution
  requirement; `RULE-004`'s added `backend/**/*.py` glob was confirmed to
  reach its own qualified rollback-trigger fixture with no scope
  overshoot; all 7 prior-round P1 closures were re-confirmed genuinely
  unregressed; the two disclosed carried-forward observations (whether
  `scope: global` pollutes unrelated contexts; whether the rule-loader
  might match a non-root-anchored nested glob) were investigated and
  neither promoted, for lack of a present, material, implementation-
  blocking defect. One new P2 was found (7 of 9 evidence files' binding
  text still named the superseded `183acd5`, not `8e90680` — fixed same
  session by the orchestrating session, not the reviewer, since the
  files were content-identical and the defect was in the binding
  statement, not the underlying evidence) plus 2 carried P2s and 1 new
  Editorial, all disclosed, non-blocking, not required for `APPROVED`.
  **`RULE-001` through `RULE-009` are now `APPROVED` and `ACTIVE`.
  `BUG-035` is CLOSED.** Full record:
  `knowledge/03-Modules/MOD-001/evidence/model-routing/RULE_QUALIFICATION_REVIEW_ROUND5_2026-09-25.md`.

## Version/hash snapshot at approval (added 2026-09-13, Phase 10 readiness, closes BUG-025/SCN-084)

`validate_capabilities.py` checks required fields are non-blank but
never compared a capability's *current* `version`/`content_hash`
against the value recorded *at approval time* — a capability could
change materially with `review_status` left untouched and still report
PASS. This table is the snapshot `knowledge/05-QA/tools/capability_drift_check.py`
compares the live rows above against. **Update this table in the same
commit as any `version`/`content_hash` cell change above** — the two
tables agreeing is what "no drift" means; letting a live cell change
without updating its snapshot row would itself defeat the check.

| id | version (at approval) | content_hash (at approval) |
|---|---|---|
| CAP-001 | live server, tools observed 2026-08-31 | N/A (hosted) |
| CAP-002 | 0.8.0 | N/A (external binary, not project-controlled) |
| CAP-003 | as shipped in this environment | not independently hashed (first-party, trusted by default) |
| CAP-004 | N/A | N/A |
| CAP-005 | as shipped in this environment | N/A (harness-native) |
| CAP-006 | as shipped in this environment | N/A (harness-native) |
| CAP-007 | v2, Round-3-P1-remediated (2026-09-07); superseded v1 preserved at `.claude/security/superseded_v1/`, not a version of this capability | SHA-256 of `bash_guard.py`: `315df926ff607fb0560f4f1842646d28eeb2a059b771130db5002edb347cc245` (independently recomputed and confirmed exact-match 2026-09-08; recompute and update this cell whenever the file changes — see governance note below) |
| RULE-001 | 4 (2026-09-25, `paths:` frontmatter added, unaffected by later commits) | SHA-256: `2cb737ce1b36ec78dab29ee952289d5a666f42b328886f05d9318c4bef912175` |
| RULE-002 | 4 (2026-09-25, `scope: global`, commit `14d1337`) | SHA-256: `e61455b487c32a79e2689a1580fdd41fa4cf331e7dcb75cc31b00058d30d1eb1` |
| RULE-003 | 2 (2026-09-25, `paths:` frontmatter added, unaffected by later commits) | SHA-256: `64ea2816088f625ebd8abe1c6459840fe69e453f1f001907c54377b45c547664` |
| RULE-004 | 5 (2026-09-25, `backend/**/*.py` glob added, commit `14d1337`) | SHA-256: `74dc432ec2482a1ae09dfa2cbedc3e50e881c1068a2b675caa06b64db67683a2` |
| RULE-005 | 3 (2026-09-25, `paths:` frontmatter added, unaffected by later commits) | SHA-256: `8d05b2844480ea9ccab65b8a557368727c132c6367b259507f587af55d1507ad` |
| RULE-006 | 3 (2026-09-25, `paths:` frontmatter added, unaffected by later commits) | SHA-256: `1694fb09d14026dcf947d1e425134f7180ca5f5b5cdc592efb79a90e83c0d7b3` |
| RULE-007 | 2 (2026-09-25, `paths:` frontmatter added, unaffected by later commits) | SHA-256: `9483ab4aa9df14ebfe38192b89fecd221d1b0fc9b93839d9579878fe2fbe7e76` |
| RULE-008 | 2 (2026-09-25, `paths:` frontmatter added, unaffected by later commits) | SHA-256: `f618731725f88d4ea811f6f7420a837614cbaa89b4c8050d2c8f45e03f321f53` |
| RULE-009 | 2 (2026-09-25, `paths:` frontmatter added, unaffected by later commits) | SHA-256: `805e669248cc252eec0b5995b9e1702b3e6e6ffd033d70f70407d50e38ad4e5c` |

**Honest scope note:** for CAP-001/002/003/005/006, "version" is a
descriptive string, not a strict semver — drift detection for these
rows is exact-string-match on whatever value the registry cell holds,
which catches a materially different string (e.g. a real TestSprite CLI
version bump) but would not catch a hosted MCP server changing its
underlying behavior with no version string change at all (CAP-001 has
no version concept beyond "live server" — this is a pre-existing
limitation of the field, not one this check introduces). CAP-007's
`content_hash` is the one row with a real, precise SHA-256 — drift
there is caught exactly.

**Activation gap, disclosed (same pattern as `run_regression.py`):**
`capability_drift_check.py` is not yet on `bash_guard.py`'s
trusted-script allowlist, so an agent session cannot invoke it through
its own governed Bash tool today — that requires an owner-authorized
edit to `.claude/security/**` plus an independent security re-review.
Runnable today by the owner or any human terminal session.

## Rejected / revoked

(none yet)

## Fail-closed reminder

No module task may depend on a capability whose `review_status` is not `APPROVED`, except the qualification drill itself. See `CAPABILITY_POLICY.md`.
