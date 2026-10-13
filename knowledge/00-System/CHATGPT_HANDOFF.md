# CHATGPT_HANDOFF.md

## Purpose

This file is the durable handoff for any new ChatGPT account or session that needs to continue the Veyro project without relying on prior chat history.

The repository is the authoritative source of truth. This file is only a bridge into that durable state.

---

# 1. Project Identity

Project: **Veyro**

Product direction: AI-native, true multi-tenant SaaS operating system for gyms and fitness businesses.

Primary implementation stack and architecture are governed by the repository baselines and must not be re-invented from chat memory.

The following exact artifacts are governing references and their names must be preserved:

- `Gym_OS_Master_Product_Blueprint_v1_English`
- `Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE`
- `Veyro_Technical_System_Design_v1.4.1_English_FINAL`
- Claude Design folder: `veyro-product-experience-design`

The implementation plan contains **75 modules**, from `MOD-000` through `MOD-074`.

---

# 2. Source of Truth

A new ChatGPT account/session must NOT treat this handoff or old conversation history as the authoritative project state.

Always begin by reading the repository bootstrap chain:

- `knowledge/00-System/SESSION_BOOTSTRAP.md`
- `knowledge/00-System/PROJECT_INDEX.md`
- `knowledge/00-System/CURRENT_STATE.md`
- `knowledge/00-System/CURRENT_HANDOFF.md`
- `knowledge/00-System/DEVELOPMENT_CONSTITUTION.md`
- `knowledge/00-System/MODEL_ROUTING.md`

Then read the active module's governing files under:

- `knowledge/03-Modules/<ACTIVE_MODULE>/`

Also inspect:

- current Git `HEAD`
- `git status`
- open bug registry
- capability registry
- active ADRs
- latest evidence/checkpoints

If chat memory conflicts with repository state, **repository state wins**.

---

# 3. Governing Baselines

Technical architecture:
- `Veyro_Technical_System_Design_v1.4.1_English_FINAL`

Engineering governing plan:
- `Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE`
- Document ID: `VEYRO-EIP-1.4.1-20260827`
- SHA-256: `e5b5ec3b08859e27da3689dc3b54d17ea766cba5bf4c4e0007239baa920866b6`

UX baseline:
- approved 170-screen V1 baseline/prototype
- identity: `VEYRO-UX-V1-170-APPROVED`

Source precedence:

1. Master Product Blueprint
2. TSD v1.4.1
3. Approved 170-screen V1 experience baseline/prototype
4. EIP v1.4.1
5. Module Spec + Scenario Catalog
6. Code / evidence

The repository also contains durable mirrors:

- `EIP_MIRROR.md`
- `TSD_MIRROR.md`

Use those when appropriate instead of depending on chat uploads.

---

# 4. Module Execution Model

There are 75 modules:

- Foundation: `MOD-000`–`MOD-015`
- Pilot: `MOD-016`–`MOD-033`
- V1 GA: `MOD-034`–`MOD-049`
- V1.5: `MOD-050`–`MOD-061`
- V2: `MOD-062`–`MOD-068`
- Enterprise: `MOD-069`–`MOD-074`

WIP rule:
- exactly one implementation module may be in Implementation/QA at a time.

Standard lifecycle:

PLAN
→ SPECIFY MODULE
→ WRITE/REVIEW SCENARIOS
→ IMPLEMENT
→ AUTOMATED TESTS
→ TESTSPRITE
→ INDEPENDENT CODE REVIEW
→ FIX
→ CLAUDE ACTUAL MANUAL QA
→ FIX/RETEST
→ LOAD/SECURITY/RESILIENCE
→ CUMULATIVE REGRESSION
→ ARCHIVE EVIDENCE
→ UPDATE KNOWLEDGE
→ MODULE APPROVAL
→ UNLOCK NEXT

Certification gates include:

- `MOD-033` — Pilot certification
- `MOD-049` — V1 GA certification
- `MOD-061` — V1.5 certification
- `MOD-068` — V2 certification
- `MOD-074` — Enterprise certification / program closure

A completed implementation slice is NOT the end of the mission.

---

# 5. Current Execution Policy

The project is operating in **Autonomous Development Mode**.

Relevant durable decisions include:
- `OWN-006`
- `ADR-007`

The old restrictive Bash capability gate (`CAP-007`) was retired.

Local development should proceed autonomously without stopping for ordinary engineering actions.

Claude/OpenClaw should continue automatically through the next legally allowed action.

Do not stop merely because:
- a bug closed
- a slice completed
- a review passed
- a checkpoint was reached
- a fresh Claude session is needed
- a test failed
- a local dependency is missing
- Docker/Colima is stopped
- a local tool needs repair
- a normal Git commit/push is required
- a recoverable timeout/rate limit occurred

A completed slice is a continuation point, not a mission-complete condition.

---

# 6. Absolute Owner-Stop Conditions

Interrupt the owner only for:

1. Real Production deployment/promotion.
2. Real paid-service activation or new spend.
3. Use of real customer/member/regulated data.
4. Destructive external/remote actions such as force-push/history rewrite or destructive action outside the Veyro workspace.
5. A genuinely unresolved product/business decision where governing sources do not determine the answer.

Ordinary local engineering is NOT an owner-stop condition.

---

# 7. OpenClaw Architecture

OpenClaw is the autonomous control plane.

Current architecture:

```text
Owner
  ↓
OpenClaw
  ↓
veyro-orchestrator
  ↓
OpenAI GPT-6 Sol
  ↓
plugin-local ACPX CLI
  ↓
Claude Code
  ↓
Veyro repository
  ↓
Claude result
  ↓
OpenAI independent verification
  ↓
next legal action
```

Primary OpenClaw orchestrator:

- agent: `veyro-orchestrator`
- model: `openai/gpt-6-sol`
- workspace: `~/.openclaw/workspace-veyro`

Primary Veyro repository:

`/Users/ahmadmabrouk/Desktop/Veyro`

OpenClaw gateway:
- local gateway
- launchd LaunchAgent
- loopback port `18789`

The Gateway should normally restart with the Mac user session.

---

# 8. Claude Code Connection

Do NOT rely on OpenClaw native:

`sessions_spawn(runtime="acp")`

on the currently established installation unless it is explicitly re-qualified.

On OpenClaw `2026.9.6`, this path repeatedly failed with:

`Unknown agent id "claude"`

The working and verified path is the **plugin-local ACPX CLI**.

ACPX binary:

`/Users/ahmadmabrouk/.openclaw/extensions/acpx/node_modules/.bin/acpx`

Verified ACPX version at setup time:

`0.19.0`

Repository working directory:

`/Users/ahmadmabrouk/Desktop/Veyro`

All Claude ACPX executions must use:

- `--approve-all`
- `--non-interactive-permissions fail`
- `--timeout 1200`

One-shot example:

```bash
/Users/ahmadmabrouk/.openclaw/extensions/acpx/node_modules/.bin/acpx \
  --cwd /Users/ahmadmabrouk/Desktop/Veyro \
  --approve-all \
  --non-interactive-permissions fail \
  --timeout 1200 \
  claude exec "<TASK>"
```

Persistent session flow:

```bash
/Users/ahmadmabrouk/.openclaw/extensions/acpx/node_modules/.bin/acpx \
  --cwd /Users/ahmadmabrouk/Desktop/Veyro \
  --approve-all \
  --non-interactive-permissions fail \
  --timeout 1200 \
  claude sessions ensure --name <SESSION_NAME>
```

Then:

```bash
/Users/ahmadmabrouk/.openclaw/extensions/acpx/node_modules/.bin/acpx \
  --cwd /Users/ahmadmabrouk/Desktop/Veyro \
  --approve-all \
  --non-interactive-permissions fail \
  --timeout 1200 \
  claude -s <SESSION_NAME> "<TASK>"
```

---

# 9. Verified Connectivity

The following loop has already been tested successfully:

```text
OpenAI
→ OpenClaw
→ ACPX
→ Claude Code
→ Veyro repository
→ Claude response
→ OpenAI independent verification
```

Verification included:
- ACPX exit code `0`
- Claude Code executed
- Claude returned the connectivity canary
- Claude read the Veyro repo
- HEAD/branch/module/lifecycle matched OpenAI's independent verification
- no repository changes were caused by the test

---

# 10. Claude Session Policy

Use the SAME Claude session when:
- implementing a coherent slice
- fixing findings from that slice
- bounded remediation
- continued work where independent context is not required

Open a NEW fresh Claude session when:
- independent scenario review is required
- independent code review is required
- security review is required
- Manual QA requires independent context
- Gatekeeper/certification is required
- governance explicitly forbids self-review

Never reuse the implementation session for an independent approval gate.

This rule is important and should be stated explicitly whenever advising the owner about Claude session usage.

---

# 11. OpenAI vs Claude Responsibilities

OpenAI orchestrator:
- read durable state
- determine the next legal action
- decide same-session vs fresh-session execution
- inspect Claude output
- independently verify repo state
- detect contradictions
- decide remediation/review/gate progression
- maintain the autonomous mission loop

Claude Code:
- implementation
- code edits
- tests
- module evidence
- local tooling work
- remediation
- role-specific engineering work

Independent Claude sessions:
- security review
- code review
- scenario review
- Manual QA
- Gatekeeper/certification when governed

---

# 12. Continuous Autonomous Mission Rule

The orchestrator must continuously repeat:

```text
BOOTSTRAP
→ inspect repository state
→ determine next legal action
→ spawn/resume correct Claude session
→ wait for completion
→ independently inspect Git diff/tests/evidence/state
→ remediate findings automatically
→ rerun tests
→ dispatch fresh independent review where required
→ close findings only with evidence
→ commit/push when appropriate
→ determine next slice/gate
→ continue
```

Do not return control to the owner merely because:
- a slice finished
- a bug closed
- a review passed
- the next action is known
- a new Claude session is required

Continue until:
- a true owner-stop condition is reached, or
- the governed Veyro product scope is complete.

---

# 13. Rate Limits and Timeouts

OpenAI orchestrator:
- prefer `GPT-6 Sol` for primary orchestration
- preserve state before retries
- use backoff on provider rate limits
- continue from the durable repository checkpoint after provider recovery

Claude/ACPX:
- timeout: `1200` seconds
- large remediations should be split into bounded batches
- persist checkpoint after each batch
- do not restart already-completed work

If ACPX exits with timeout code `3`:
- treat it as incomplete execution, not project failure
- inspect valid work produced before timeout
- preserve it
- resume where governance permits

If ACPX exits with permission code `5`:
- do NOT treat it as an owner stop
- verify the invocation includes `--approve-all` and `--non-interactive-permissions fail`
- correct and retry autonomously

---

# 14. Authentication Boundaries

ChatGPT account, OpenAI provider auth, Claude Desktop auth, and Claude Code CLI auth are separate concerns.

Important:

- Switching account inside Claude Desktop should not be treated as switching Claude Code CLI auth.
- Do not run `claude auth logout` unless intentionally changing Claude Code credentials.
- If `claude auth status` reports `loggedIn: false`, restore with:
  `claude auth login`

After restore, verify with:

```bash
claude auth status
```

Optionally:

```bash
claude -p "Reply with exactly: CLAUDE_READY"
```

OpenClaw must use the intended **personal OpenAI account/provider authentication** after account migration.

Do not assume changing the ChatGPT website account automatically changes OpenClaw's provider credentials.

---

# 15. Personal ChatGPT Account Migration

The personal ChatGPT account will NOT contain the historical company-account Veyro conversation.

That is expected.

The personal account should continue the project by reading this file plus the repository bootstrap chain.

Recommended first message in the personal account:

```text
This is the Veyro project.

The repository and its durable knowledge files are the authoritative source of truth.

Before answering, planning, or making project decisions, read:

- knowledge/00-System/CHATGPT_HANDOFF.md
- knowledge/00-System/SESSION_BOOTSTRAP.md
- knowledge/00-System/PROJECT_INDEX.md
- knowledge/00-System/CURRENT_STATE.md
- knowledge/00-System/CURRENT_HANDOFF.md
- knowledge/00-System/DEVELOPMENT_CONSTITUTION.md
- knowledge/00-System/MODEL_ROUTING.md

Then inspect the active module's files, Git HEAD/status, open bugs, active ADRs, capability state, and latest evidence/checkpoints.

Do not infer current project state from this chat.
Use repository state.

OpenClaw is the autonomous control plane.
Use the existing veyro-orchestrator workflow and continue the project from the current governed state.
```

---

# 16. User Working Preferences

Important interaction rules:

- Always explicitly state whether the next Claude action should be:
  - **نفس الـsession**
  - **افتح session جديدة**

- Any prompt intended for Claude/OpenClaw should be placed in a copyable code block.
- Preserve exact artifact names.
- Do not restart completed work.
- Do not silently ignore contradictory state.
- Prefer repository truth over chat memory.
- Minimize manual owner intervention.
- Avoid unnecessary repeated audits/review loops after governed convergence criteria are satisfied.
- Do not ask the owner to shuttle prompts or responses between OpenAI and Claude.

---

# 17. Current Known Snapshot — Non-Authoritative

This is only a historical snapshot from the previous ChatGPT account.

The repository must be checked for newer state before acting.

Recent known state included:
- `MOD-001` active
- R04 / RLS-permission-lint work underway
- `SCN-067` blocked pending R04 completion
- ADR-009 / ADR-010 work during R04 recovery
- at one checkpoint:
  - `56/56` RLS integration tests passed
  - `107/107` backend tests passed
  - gate unit suite had `2` failures
  - Ruff had `12` findings
- provider/auth/rate-limit interruptions were handled through checkpoints

THIS SNAPSHOT MAY BE STALE.

Before continuing:
1. read `CURRENT_STATE.md`
2. read `CURRENT_HANDOFF.md`
3. inspect active module `STATUS.md`
4. inspect latest ADR/evidence/checkpoint
5. run `git status`
6. run `git rev-parse HEAD`
7. inspect open bugs
8. verify baselines

---

# 18. OpenClaw Workspace Files

Primary orchestrator instructions:

`~/.openclaw/workspace-veyro/AGENTS.md`

This file contains:
- ACPX dispatch policy
- autonomous permissions
- same/new Claude session rules
- continuous mission behavior
- failure handling
- owner-stop conditions

A new ChatGPT account should not overwrite `AGENTS.md` casually.

If it proposes changing OpenClaw orchestration behavior:
- inspect current file first
- preserve working ACPX routing
- preserve owner-stop boundaries
- avoid reintroducing broken native `sessions_spawn` routing unless explicitly re-qualified

---

# 19. Repository and Git

Repository:

`/Users/ahmadmabrouk/Desktop/Veyro`

GitHub repo:

`ahmadmabrook/Veyro`

Normal autonomous actions may include:
- local edits
- tests
- local tooling
- dependency setup
- Docker/Colima
- commits
- normal pushes

Do not:
- force-push
- rewrite remote history
- perform destructive external actions
without owner approval.

Always verify when relevant:

```bash
git status
git rev-parse HEAD
git rev-parse origin/main
```

---

# 20. How the New ChatGPT Account Should Behave

When the owner asks about Veyro:

1. Assume the project already exists and is active.
2. Do not rebuild the orchestration architecture from scratch.
3. Read this file and the bootstrap chain.
4. Ground current-state claims in the repo.
5. Treat OpenClaw as the control plane.
6. Treat Claude Code via ACPX as the implementation harness.
7. Preserve continuous autonomous execution.
8. Explicitly state same-session vs fresh-session guidance whenever a Claude action is discussed.
9. Avoid unnecessary owner involvement.
10. Continue from current state, never from an old chat snapshot.

---

# 21. First-Run Checklist for Personal Account

- [ ] Personal ChatGPT subscription is active.
- [ ] Personal account can access the Veyro repo/files needed for project context.
- [ ] `CHATGPT_HANDOFF.md` is present at `knowledge/00-System/CHATGPT_HANDOFF.md`.
- [ ] OpenClaw `veyro-orchestrator` exists.
- [ ] OpenClaw orchestrator model is the intended OpenAI model.
- [ ] OpenClaw provider auth points to the intended personal OpenAI account.
- [ ] OpenClaw Gateway is healthy.
- [ ] ACPX plugin-local CLI exists.
- [ ] Claude Code auth is healthy.
- [ ] Claude connectivity test passes.
- [ ] Veyro bootstrap and all four governing baselines verify.
- [ ] Current Git state/checkpoint is understood before new work begins.

Recommended connectivity test:

```text
Ask Claude Code through ACPX to report:
- current working directory
- current Git branch
- current HEAD
- active module
- lifecycle state

OpenAI orchestrator then independently verifies the same values.

PASS only if:
- ACPX exits 0
- Claude executes successfully
- repository facts match
- no unintended repository modification occurs
```

---

# 22. Final Principle

The project should remain portable across ChatGPT accounts because:

```text
Repository = durable project memory
OpenClaw = autonomous control plane
OpenAI = orchestrator/reviewer
Claude Code = implementation engine
Git + evidence = project truth
ChatGPT account = operator interface
```

A new ChatGPT account should therefore be able to continue Veyro with minimal loss of continuity as long as it can read the repository and follow this handoff.
