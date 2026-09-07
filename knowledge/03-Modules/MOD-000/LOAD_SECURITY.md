---
doc: MOD-000_LOAD_SECURITY
status: LIVE — N/A-with-justification for load; Phase 7 security/resilience executed; v1 Bash guard superseded after 4 failed review rounds; v2 allow-by-construction redesign went through its 2-round cap, a final Round 3 (BLOCKED, P0=0/P1=3), a narrowly-scoped remediation, and a fourth independent review — APPROVED FOR OWNER ACTIVATION (P0=0/P1=0) — all 3 bugs (BUG-013/022/023) moved to REMEDIATED — PENDING LIVE ACTIVATION VERIFICATION, NOT closed; owner activation patch drafted, not applied
updated: 2026-09-08
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
v1's four rounds of structurally new findings.

**The owner then separately authorized a narrowly-scoped remediation
pass (2026-09-07, explicitly NOT a Round 4 review) for the 3 named
P1s.** `_grep_readonly`'s flag-membership check now denies every
bundled/long-form `-f`/`--file` spelling, not just the one literal token
Round 2 tested. `_ALLOWED_PYTHON_SCRIPTS` was converted from a bare path
set to SHA-256 content-hash pinning via a new `_script_integrity_ok`
check — tamper *detection* (a tampered file can no longer be executed
through the guard) but not write *prevention* (`.claude/settings.json`
was not touched this pass; that half is a disclosed, separately-tracked
residual). The guard was registered as **CAP-007** in
`CAPABILITY_REGISTRY.md`, honestly at `QUALIFIED — NOT APPROVED` rather
than force-labeled `APPROVED`, since an `APPROVED` verdict requires an
Opus review this remediation pass was explicitly not authorized to run.
20 new regression tests were added (194/194 passing); all validators and
baseline hashes were re-verified clean. Full record:
`evidence/security/BASH_GUARD_V2_ROUND3_P1_REMEDIATION_2026-09-07.md`.

**The owner then authorized one final independent verification pass on
that remediation (2026-09-08) — explicitly not a reopening of the review
loop.** A fourth independent fresh-context `veyro-security-reviewer`
re-inspected the code from scratch, independently re-verified all three
P1 fixes (27 `grep -f` spellings; symlink/tamper/exception-path probing
of the hash-pinning mechanism in an isolated temp tree; a field-by-field
CAP-007 audit against `CAPABILITY_POLICY.md`), re-ran the 194-test
suite, and built ~250 of its own fresh adversarial fixtures across
every historical threat category. **Result: P0=0, P1=0, P2=6,
Editorial=9 — verdict APPROVED FOR OWNER ACTIVATION**, conditional on
the eventual activation patch adding `.claude/security/**`
write-protection — the reviewer's explicit determination is that its
current absence IS certification-blocking for activation (the
trusted-script hash pins live inside the same unprotected file), not a
defect to wave away. The reviewer also determined CAP-007 now has
sufficient independent evidence for `APPROVED` and specified the exact
fields to record; **CAP-007 is now APPROVED** in
`CAPABILITY_REGISTRY.md`. BUG-013/022/023's respective classes were all
independently re-confirmed CLOSED for the Bash surface on the
reviewer's own fresh fixtures, not merely the existing suite.

**Per the owner's exact instruction, none of the three bugs are closed
yet.** All three moved to **REMEDIATED — PENDING LIVE ACTIVATION
VERIFICATION** — closure requires the owner to manually apply the
drafted-not-applied activation patch
(`evidence/security/BUG-013-022-023-OWNER-SETTINGS-PATCH.md`), start a
fresh Claude Code session, and prove live that the hook executes,
destructive fixtures deny, and safe operations remain unaffected. 6 P2
and 9 Editorial findings remain as accepted-known residuals for a
future, separately-authorized pass — not silently dropped. Full record:
`evidence/security/BASH_GUARD_V2_FINAL_VERIFICATION_2026-09-08.md`.
**Phase 7 gate: still BLOCKED, not PASS** — this session applied nothing
to `.claude/settings.json`, and Phase 7 cannot PASS until the three bugs
actually close post-activation. The piecemeal pre-Phase-7 work listed in
the prior version of this note (Phase 3 drills, F5-011, F5-001, the
Notion-scope audit) is superseded as the current record by the formal
Phase 7 pass above, but remains valid supporting evidence, not
retracted.
