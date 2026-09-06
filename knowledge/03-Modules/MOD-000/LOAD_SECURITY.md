---
doc: MOD-000_LOAD_SECURITY
status: LIVE — N/A-with-justification for load; Phase 7 security/resilience executed; a PreToolUse guard built for BUG-013/022/023 has been through FOUR independent review rounds, each finding new P0s, and is NOT yet certified — all 3 bugs remain OPEN
updated: 2026-09-06
---

# MOD-000 — Load/Security (index)

Appendix D field: "Load/performance/security/resilience plans/results."

**Load/performance: N/A-with-justification (unchanged).** MOD-000 is the
control-plane bootstrap — it has no runtime service, no API endpoints, no
user traffic. There is nothing to load-test. This will apply from
MOD-001 onward, once a real backend exists. EIP §21.1's MOD-000 module
card does not list LOAD_SECURITY as mandatory for MOD-000. Phase 7's
performance-assurance work (control-plane tooling performance, not
product load testing) is recorded separately: `knowledge/03-Modules/
MOD-000/evidence/performance/PHASE7_PERFORMANCE_RESILIENCE_2026-09-06.md`
— APPROVED, 0 P0/P1.

**Security: Phase 7 formally executed 2026-09-06.** Fresh-context Opus
`veyro-security-reviewer` ran the full review, covering owner-reserved
controls, Claude project permissions (deny-pattern live testing),
capability supply-chain, prompt-injection resistance, model assurance,
baseline integrity, durable-state integrity, secrets/PII scanning,
Git/GitHub security, and the Notion MCP/BUG-010 re-affirmation. Full
record: `knowledge/03-Modules/MOD-000/evidence/security/
PHASE7_SECURITY_REVIEW_2026-09-06.md`. Initial result: **BLOCKED — 2 P1
found** (11 P2 + 4 Editorial fixed and live-verified same day). A second,
independent fresh-context re-review then found the fixes largely held
but two were narrower than claimed (fixed as a follow-up same day) and
widened `BUG-013`'s residual scope. **BUG-012** (orchestrating session's
model tier) is **CLOSED** — the owner was asked directly and decided
`OWN-003` ("accept Sonnet orchestration with delegated Opus judgment");
see `ADR-004`, `MODEL_ROUTING.md`. The owner then manually hand-edited `.claude/settings.json` to close
`BUG-013`'s git-injection residual. **A third independent fresh-context
re-review (2026-09-06) confirmed the git global-flag-injection family
(`-c`/`-C`/`--no-pager`) is genuinely CLOSED** (16+ variants tested, all
denied) **but found the `rm`-recursive residual (bare `-r`, `-vr`, `-Rv`,
`find -delete`) still OPEN**, untouched by that edit. The same re-review
found **two new P1s**: **`BUG-022`** — absolute-path/wrapper invocation
(`/usr/bin/git`, `/bin/rm`, `/bin/cp`) bypasses the entire deny list,
since every pattern is anchored on the bare command token; proven live
via a real `reset --hard` and `branch -D` against a disposable fixture,
re-opening the git family via a different route. **`BUG-023`** — the
`>`/`>>`/`tee`-onto-`.claude/settings.json`/`.claude/rules` redirection
deny patterns never fire at all, correcting a false prior "live-verified"
claim in the Phase 7 evidence and in `BUG-013` itself. **Architectural
conclusion recorded**: `permissions.deny` glob-on-command-string matching
alone is not a sufficient technical enforcement layer; the recommended
direction, not yet implemented, is a project-scoped `PreToolUse` Bash
security gate that parses/normalizes commands and fails closed
semantically rather than by string pattern.

**A `.claude/security/bash_guard.py` PreToolUse guard was subsequently
built** to implement that direction and put through **four** independent
fresh-context review rounds — every single round found new
P0-severity bypasses (command-segmentation gaps, an incomplete wrapper
denylist, a discovery that this session's actual shell is zsh 5.9 not
bash, zsh-specific redirection operators, case-sensitive command-name
matching). All mechanically-fixable findings were fixed and tested
(suite grew 95→200, all passing). **The guard is explicitly NOT
certified clean** — disclosed, unfixed gaps remain (zsh clobber/append
redirects, heredoc live-expansion, ancestor-directory protection,
`python -m` inline code, more git config keys, protected-path set gaps).
A real incident during the fourth review (a heredoc mishap executed live
commands against the repo) was self-restored by the reviewer and
independently re-verified clean by the orchestrating session. Full
record: `evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md`.

**`BUG-013`, `BUG-022`, and `BUG-023` all remain OPEN.** Baseline hashes,
the scenario-catalog validator, and the evidence-integrity checker were
all independently re-verified clean. **Phase 7 gate: BLOCKED, not PASS**
(P0=0, P1=3) — per this project's standing rule, not self-waived, and
per the structural pattern this effort has now demonstrated four times
running (every review round finds something new), not assumed closed
just because no further round has been dispatched yet. The piecemeal
pre-Phase-7 work listed in the prior version of this note (Phase 3
drills, F5-011, F5-001, the Notion-scope audit) is superseded as the
current record by the formal Phase 7 pass above, but remains valid
supporting evidence, not retracted.
