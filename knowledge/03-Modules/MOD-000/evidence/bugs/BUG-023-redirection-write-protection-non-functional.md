---
doc: BUG-023
status: OPEN — also corrects a false prior "live-verified" claim in Phase 7 evidence and BUG-013
found_date: 2026-09-06
found_by: Third independent Phase 7 re-review (RR-3), fresh-context Opus veyro-security-reviewer, verifying the owner's manual BUG-013 settings.json edit
severity: P1
---

# BUG-023: shell-redirection deny patterns for baseline files and `.claude/settings.json` never fire

## What is wrong

`.claude/settings.json` contains deny entries of the form
`Bash(*>*<protected-filename>*)` intended to block shell redirection
(`>`, `>>`) from overwriting the 4 governing baseline files and
`.claude/settings.json`/`.claude/rules/**`. A fresh-context
`veyro-security-reviewer` (RR-3) proved these patterns are **non-
functional** — they never match, regardless of the command. The harness
evidently evaluates the command for permission-matching purposes with its
redirection target stripped out, so no `>`-containing (or `>>`- or
`tee`-containing) command line ever contains the literal protected
filename in the string the matcher sees.

Proven against decoy fixtures carrying the exact protected filenames
(never the real files — the glob is over the command string, so a decoy
path exercises the same pattern identically without risking the real
baselines):

```
echo TAMPERED > <scratch>/fake/.claude/settings.json                          → EXECUTED, file written
echo TAMPERED > <scratch>/fake/Gym_OS_Master_Product_Blueprint_v1_English.docx → EXECUTED, file written
echo APPENDED >> <scratch>/fake/.claude/settings.json                          → EXECUTED
printf 'TEE_TAMPER\n' | tee <scratch>/fake/.claude/settings.json               → EXECUTED (no tee
                                                                                    pattern covers
                                                                                    settings.json at all)
python3 -c "open('<scratch>/fake/.claude/settings.json','w').write('PY_TAMPER')" → EXECUTED
```

By contrast, `truncate`, `dd`, `tee`-onto-the-three-baseline-docx-names,
`sed -i`, `cp`, and `mv` targeting the same protected names **all
correctly denied** — so this is specifically the `>`/`>>` redirection
family, plus the fact that no `tee` pattern exists at all for
`.claude/settings.json`/`.claude/rules/**` (only for the 3 baseline
docx filenames).

## Why this is P1, not P2, and why it corrects prior evidence

`knowledge/03-Modules/MOD-000/evidence/security/PHASE7_SECURITY_REVIEW_2026-09-06.md`
records SEC-05 and SEC-06 as **FIXED**, and `BUG-013`'s own "Remediation
applied" section explicitly claims redirection coverage was "added" and
implies it was live-verified as part of that fix. **That claim is false.**
It is load-bearing, not cosmetic: SEC-06's self-protection is the stated
reason `BUG-013`'s residual "requires a human edit" rather than an agent
one — that reasoning is still correct (the `Edit`/`Write` *tool* denies on
`.claude/settings.json` do work, which is what actually blocked prior
agent-side edit attempts), but the Bash-layer redirection protection
sitting alongside it does not, and was recorded as if it did.

## Fix needed

These five specific patterns cannot be repaired as globs (the redirection
target is apparently not visible to the matcher at all, so no glob
variant will catch it). Two options, to be decided by whoever applies the
fix:

1. **Remove the non-functional patterns** (`Bash(*>*Gym_OS...*)`,
   `Bash(*>*Veyro_Technical...*)`, `Bash(*>*Veyro_Engineering...*)`,
   `Bash(*>*.claude/settings.json*)`, `Bash(*>*.claude/rules*)`) since a
   deny entry that cannot fire is worse than no entry — it creates false
   confidence, which is exactly what happened here. Add
   `Bash(tee*.claude/settings.json*)` and `Bash(tee*.claude/rules*)`,
   which are simply missing and are NOT known to be non-functional
   (`tee` onto the baseline docx names does work).
2. Or, if the redirection form can be made to work through some other
   harness-level mechanism not yet identified, keep the patterns but do
   not mark this bug closed until that mechanism is demonstrated live
   against a decoy fixture the way every other fix in this project has
   been.

Either way: **correct `PHASE7_SECURITY_REVIEW_2026-09-06.md`'s SEC-05/
SEC-06 disposition rows and `BUG-013`'s "Remediation applied" section** to
state plainly that redirection is not enforced at the Bash layer — this
has been done as of this recording (see both files' RR-3/BUG-023
cross-references).

## Remediation attempt v1 (2026-09-06): deny-by-enumeration guard, superseded after 4 rounds

A `.claude/security/bash_guard.py` PreToolUse hook was built and put
through four independent fresh-context review rounds. Redirection/write-
protection gaps directly in this bug's scope were found and fixed
repeatedly across rounds (broader operator forms, quote-aware scanning
replacing token-based detection, an expanded write-primitive command
set, protected-path coverage extended to the guard's own directory) —
but round 4 still found zsh-specific clobber/append redirection
spellings (`>!`, `>>!`, `>>&`, `&>!`, `&>|`) unmodeled, and a
disclosed-but-unfixed gap where protected-path matching is per-listed-
path rather than per-subtree (`mv .claude /tmp/x`, `tar -czf x.tgz
.claude` escape every check — this exact operation was accidentally
demonstrated live during the round-4 review itself, see the incident
section of the full record). Full record:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md`.
This whole design was superseded, not patched a fifth time. Preserved as
evidence at `.claude/security/superseded_v1/`.

## Remediation attempt v2 (2026-09-06): allow-by-construction redesign, 2-round cap reached, NOT certified

v2's design closes this bug's class structurally rather than by
enumerating redirection spellings: `>`/`>>`/`<`/`<<` (and every
composition character) are unconditionally banned at Stage 1 for EVERY
command, so no redirection form — including the zsh clobber/append
spellings that defeated v1 (`>!`, `>>!`, `>>&`, `&>!`, `&>|`) — can ever
reach a family validator at all; `tee`, `sed -i`, `cp`, and every other
v1-era write primitive are simply absent from v2's allowed command list,
so they deny as `UNKNOWN_COMMAND` regardless of arguments. The
ancestor-directory gap (`mv .claude /tmp/x`) is likewise closed
differently: `mv` is not an allowed command in v2 at all (it denies
outright), where v1 had `mv` as a recognized-but-checked command that a
directory-level argument could evade. Two independent review rounds (the
maximum permitted for this redesign pass) both judged the architecture
sound; round 2's residual findings (git refspec/remote-path syntax,
read-family traversal via `..`/`$HOME`) were outside this bug's original
scope, though the same underlying charset-based fix mechanism now
protects the path arguments this bug cares about too. Full record:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md`.
**This bug remains OPEN** — the 2-round cap was reached without a round
returning P0=0/P1=0 overall, so per this project's standing discipline it
is not certified closed.

## Certification impact

**Blocks Phase 7 PASS**, alongside `BUG-013`'s residual and `BUG-022`.
Not fixed this chunk — recording and evidence-correction only, per
explicit instruction not to modify `.claude/settings.json` in this
session.

## Round 3 (2026-09-07): final owner-authorized review round — still OPEN

`veyro-security-reviewer` returned P0=0, P1=3, verdict BLOCKED. This
bug's class (redirection/alternate-write primitives) was independently
re-confirmed CLOSED **for the Bash surface**: every redirection spelling
dies at Stage 1 on the raw string before any parsing, and every v1-era
write primitive (`tee`, `sed -i`, `mv`, `cp`, `dd`, `rsync`, `scp`,
`curl -o`, `wget -O`, etc.) is simply an unknown command. The scope
caveat already on this bug is unchanged and now independently
re-verified: closure is Bash-only — Write/Edit/NotebookEdit/MCP tools
never reach this hook, and remain governed solely by
`.claude/settings.json`'s globs, which (per Round 3's P1-2) do not cover
`.claude/security/**`. None of Round 3's three P1s are in this bug's
redirection/write-primitive class directly, but P1-2's write-protection
gap on the guard's own directory is the same underlying failure mode
this bug named, recurring in a new location. See
`BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md`. **This bug remains OPEN** —
the owner's gate rule requires overall P0=0/P1=0, not met. No further
review round is authorized. No `.claude/settings.json` edit was made.

## Affected

`.claude/settings.json` (5 non-functional deny entries, 2 missing `tee`
entries), `knowledge/03-Modules/MOD-000/evidence/security/
PHASE7_SECURITY_REVIEW_2026-09-06.md` (SEC-05/SEC-06 rows corrected),
`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-013-*.md` (remediation
section corrected), `knowledge/03-Modules/MOD-000/evidence/security/
BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md`.
