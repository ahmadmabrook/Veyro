---
doc: MOD-000_LOAD_SECURITY
status: LIVE — N/A-with-justification for load; Phase 7 security/resilience executed; v1 Bash guard superseded after 4 failed review rounds; v2 allow-by-construction redesign went through its 2-round cap plus one final owner-authorized Round 3 — all three judged the architecture sound, but Round 3 (the final round) returned P0=0/P1=3, verdict BLOCKED — all 3 bugs (BUG-013/022/023) remain OPEN, no further review round authorized
updated: 2026-09-07
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

**v1 superseded, not patched a fifth time.** Per explicit architectural
instruction, that pattern (four rounds, every one finding something
new) was treated as a design flaw, not a queue of patches. v1 is
preserved as evidence at `.claude/security/superseded_v1/`.

**v2: allow-by-construction, fail closed on ambiguity.** Rather than
recognizing dangerous shell constructs, v2 bans all shell composition/
substitution syntax outright and matches the remaining command against a
small explicit allowlist of command families — anything else denies,
with no silent "defer" outcome. Put through the explicit **2-round
review cap** for this redesign pass: round 1 found 2 P0 + 4 P1 local
implementation gaps (git refspec syntax, `git add` pathspec-magic
evasion, an impossible-to-satisfy commit-message format, routine
read-only shapes wrongly denied, arbitrary-URL fetch/remote), all fixed;
round 2 found 1 P0 + 2 P1 more in a different part of the family set
(read-only file families still on a weaker path check than the mutation
families, most sharply `find . *`'s real-shell-glob-expansion risk), all
fixed. **Both rounds independently judged the architecture itself
sound** — round 2's reviewer explicitly: "a small number of local bugs
in an otherwise-sound design," re-confirmed via 120,000 fuzz cases with
zero fail-open results. Test suite: 111 → 145 → 174. Full record:
`evidence/security/BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md`.

**The owner then authorized exactly one further round (Round 3) as the
final verification round for this architecture, gated on P0=0/P1=0 for
activation.** `veyro-security-reviewer` (Opus, fresh context — available
directly this session, no substitution needed) independently
re-inspected the guard from scratch, re-tested every Round 1/Round 2
finding's remediation, re-ran all historical BUG-013/022/023 bypass
classes, and ran 500,000 fresh adversarial cases against `classify()`.
Result: **P0=0, P1=3, P2=5, Editorial=7 — verdict BLOCKED.** The
architecture held completely (zero fail-open cases across 500,000
probes, every historical fixture denying correctly); the three P1s are
local — a Round-2 `grep -f` fix that closed only its tested spelling,
not the class (`-rf`/`-nf`/`-if`/`--file` variants still leak an
unbounded file read); `_ALLOWED_PYTHON_SCRIPTS` trusting seven mutable,
unhashed script paths that `.claude/settings.json` does not protect from
Edit/Write (the guard's own directory has no write protection); and the
guard itself never having been registered under `CAPABILITY_POLICY.md`.
Per the owner's exact, pre-specified gate rule, any P0/P1 in this round
means: stop, do not patch, do not request Round 4, do not activate, do
not touch `.claude/settings.json`. Recorded verbatim as instructed:
**CURRENT PRETOOLUSE BASH CONTROL NOT CERTIFIABLE UNDER THE APPROVED
REVIEW BUDGET.** **`BUG-013`, `BUG-022`, and `BUG-023` all remain OPEN.**
Baseline hashes, the scenario-catalog validator, and the
evidence-integrity checker were all independently re-verified clean this
chunk. **Phase 7 gate: BLOCKED, not PASS.** Full record:
`evidence/security/BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md`. Across
all three v2 rounds, findings were local and bounded — the design itself
was never re-opened as a question, a materially different pattern from
v1's four rounds of structurally new findings. **No further review round
is authorized under the current review budget** — the next legally
allowed action is an explicit owner decision on a different control
model or on the specific remediations the Round 3 reviewer identified
(fix `grep -f`, pin/hash the trusted-script allowlist and protect
`.claude/security/**`, register the guard in `CAPABILITY_REGISTRY.md`),
not another automatic review iteration. The piecemeal pre-Phase-7 work
listed in the prior version of this note (Phase 3 drills, F5-011,
F5-001, the Notion-scope audit) is superseded as the current record by
the formal Phase 7 pass above, but remains valid supporting evidence,
not retracted.
