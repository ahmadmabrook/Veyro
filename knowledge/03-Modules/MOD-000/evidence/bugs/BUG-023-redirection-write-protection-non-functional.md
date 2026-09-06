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

## Certification impact

**Blocks Phase 7 PASS**, alongside `BUG-013`'s residual and `BUG-022`.
Not fixed this chunk — recording and evidence-correction only, per
explicit instruction not to modify `.claude/settings.json` in this
session.

## Affected

`.claude/settings.json` (5 non-functional deny entries, 2 missing `tee`
entries), `knowledge/03-Modules/MOD-000/evidence/security/
PHASE7_SECURITY_REVIEW_2026-09-06.md` (SEC-05/SEC-06 rows corrected),
`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-013-*.md` (remediation
section corrected).
