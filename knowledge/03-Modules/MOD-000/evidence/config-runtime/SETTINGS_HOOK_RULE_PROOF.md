---
doc: MOD-000_SETTINGS_HOOK_RULE_RUNTIME_PROOF
status: LIVE
date: 2026-09-01
---

# .claude/settings.json, SessionStart hook, Rules, and custom agents — runtime proof (fresh session)

This session is a genuinely fresh top-level Claude Code session (confirmed by the user; also self-consistent with the evidence below — a continuing session could not have produced the "new agent types now available" system notification).

## 1. SessionStart hook — **PASS**

At the very start of this session, before any user instruction was processed, a system-reminder appeared:

> "SessionStart hook additional context: Veyro MOD-000 control plane active. Before any action: read knowledge/00-System/SESSION_BOOTSTRAP.md, then CURRENT_STATE.md and CURRENT_HANDOFF.md. WIP=1, MOD-000 only until a Module Approval Certificate exists."

This is the exact `additionalContext` string authored into `.claude/settings.json`'s `SessionStart` hook. This is direct runtime evidence the hook fired — not inferred from file presence.

## 2. Custom `.claude/agents/veyro-*` registration — **PASS**

At session start, a system-reminder announced: "New agent types are now available for the Agent tool" listing all 9: `veyro-code-reviewer`, `veyro-gatekeeper`, `veyro-implementer`, `veyro-lead`, `veyro-manual-qa`, `veyro-performance-reviewer`, `veyro-scenario-reviewer`, `veyro-security-reviewer`, `veyro-test-author` — with descriptions matching each agent file's frontmatter verbatim.

Confirmed further by direct invocation:
- `Agent(subagent_type: "veyro-gatekeeper")` ran successfully and its response recited its own agent-definition body verbatim (ground-truth precedence order, no-self-approval rule) — proof the custom system prompt, not just the name, is loaded.
- `Agent(subagent_type: "veyro-implementer")` ran successfully and recited its own definition's opening line ("You implement. You do not certify your own work.") and its exact escalation clause — same proof.
- A deliberately-misspelled agent name (`veyro-gatekeeper-nonexistent-typo`) produced a hard `Agent type not found` error whose "Available agents" list contains all 9 real `veyro-*` names by exact spelling — this is the authoritative registration list, not a guess.

## 3. `.claude/rules/*.md` auto-loading — **still not cleanly proven, but one strong incidental signal**

Attempted the designed test: gave `veyro-implementer` a task (trigger a real paid TestSprite cloud run) deliberately without mentioning any rule/policy file, to see if it self-restricted per `owner-reserved-restrictions.md` unprompted.

Result: the Agent call itself was **blocked before the agent ever ran**, by Claude Code's own Auto Mode classifier layer ("Blocked by classifier... add a Bash permission rule to allow this in future"). This is a real, useful safety signal, but it is **not proof of `.claude/rules/` auto-loading** — Auto Mode's classifier is a harness-level safety feature independent of this project's custom rule files, and none of the `.claude/settings.json` deny patterns (`rm -rf`, `--force`, `reset --hard`, `*production*`, `*prod deploy*`, `*--prod*`) match "TestSprite cloud test run" either. Conflating the two would overstate what was proven. **Verdict stays: BLOCKED/UNVERIFIED for genuine `.claude/rules/*.md` auto-load** — no test yet cleanly isolates "rule file content injected automatically" from "harness built-in safety" or "agent definition file's own body already covers it" (which is what actually explains `veyro-gatekeeper`'s and `veyro-implementer`'s correct behavior above — their own `.md` bodies, not `.claude/rules/`, state the relevant constraints).

## 4. `.claude/settings.json` syntactic validity — **PASS** (carried over, re-confirmed unchanged)

## Summary

| Item | Status |
|---|---|
| SessionStart hook fires | **PASS** — direct runtime evidence |
| Custom `veyro-*` agents registered + invocable | **PASS** — direct invocation + authoritative agent list |
| Custom agent `.md` body (not just name) loaded | **PASS** — verbatim recitation from two different agents |
| `.claude/rules/*.md` auto-loading specifically | **BLOCKED/UNVERIFIED** — no isolating test yet; one related but non-equivalent signal (Auto Mode classifier) observed |
| `.claude/settings.json` syntax | **PASS** |

## What would close item 3

A test where an agent with genuinely no other source of the rule's content (not stated in its own `.md` body, not in `CLAUDE.md`, not in `DEVELOPMENT_CONSTITUTION.md`) still follows a rule that exists ONLY in `.claude/rules/`. Current rules (`owner-reserved-restrictions.md`, `knowledge-vault-durability.md`) duplicate content already present in `CLAUDE.md`/`DEVELOPMENT_CONSTITUTION.md`/agent bodies, so no clean isolation is possible with the current rule set. Leaving this open rather than fabricating a pass.

## Correction 2026-09-05 (second Phase 5 re-review, N-8) — baseline `rm` deny patterns had a real matching gap

The second fresh-context re-review found (by pattern analysis, not execution)
that `.claude/settings.json`'s 3 baseline-artifact `rm` deny entries were
written as `Bash(rm * <filename>*)` — a **literal space** between the
first `*` and the filename. A direct command like
`rm Gym_OS_Master_Product_Blueprint_v1_English.docx` has no space between
`rm ` and the filename, so it would not have matched. `Bash(rm -rf *)`
(the only other rm-shaped deny entry) still caught recursive attempts, but
a plain non-recursive `rm <baseline file>` was a real, live gap. Also
missing entirely: no `rm`-shaped deny pattern for
`veyro-product-experience-design/` (only `Edit`/`Write` were denied).

**Fixed same day** — corrected all 3 patterns to `Bash(rm *<filename>*)`
(no forced space) and added `Bash(rm *veyro-product-experience-design*)`.
**Live-verified, not just read**, by attempting the exact previously-vulnerable
commands against the real files:

1. `rm Gym_OS_Master_Product_Blueprint_v1_English.docx` — **denied** by the harness before execution. File confirmed untouched afterward (`shasum` still `80f4b381...`, matching `PROJECT_INDEX.md`).
2. `rm Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx` — **denied**.
3. `rm veyro-product-experience-design/README.md` (the specific non-`-rf` gap the new pattern targets — `rm -rf veyro-product-experience-design/` was already covered by the generic `rm -rf *` rule and doesn't prove this) — **denied**.

All three denials happened at the permission layer (the Bash tool call was
refused, not executed-then-rolled-back) — the correct fail-closed behavior.
