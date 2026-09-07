---
doc: BUG-022
status: OPEN — requires architectural fix, not closeable by pattern enumeration alone
found_date: 2026-09-06
found_by: Third independent Phase 7 re-review (RR-3), fresh-context Opus veyro-security-reviewer, verifying the owner's manual BUG-013 settings.json edit
severity: P1
---

# BUG-022: absolute-path / command-wrapper invocation bypasses every `.claude/settings.json` Bash deny pattern

## What is wrong

Every deny entry in `.claude/settings.json`'s `permissions.deny` list is
anchored on the bare command token (`git ...`, `rm ...`, `cp ...`,
`mv ...`, `sed -i ...`, etc.). None has a twin that matches the same
binary invoked by absolute path. A fresh-context `veyro-security-reviewer`
(RR-3, re-verifying the owner's manual fix to `BUG-013`) proved this live
against its own disposable fixture:

```
/usr/bin/git -C <fixture-repo> reset HEAD~1 --hard   → EXECUTED.
    Output: "HEAD is now at 6959f54 c1". A real commit (af9d221) was
    destroyed in the fixture repo.
/usr/bin/git -C <fixture-repo> branch -D victimbranch → EXECUTED.
    "Deleted branch victimbranch (was af9d221)."
/bin/rm -rf <scratch-target>                          → EXECUTED, target deleted.
/bin/cp /Users/ahmadmabrouk/Desktop/Veyro/Gym_OS_Master_Product_Blueprint_v1_English.docx <scratch>/abs_probe.docx
                                                       → EXECUTED (198,614 bytes copied out
                                                         of the governing baseline — a real
                                                         file, though the destination was
                                                         disposable scratch, not a tamper of
                                                         the source).
/usr/bin/sed -i '' -e 's/.../.../' <decoy>/.claude/settings.json → EXECUTED.
```

`which -a git` on this host returns only `/usr/bin/git` — this is not an
exotic or hypothetical path, it is the actual resolved binary that a bare
`git` invocation would itself use. The reviewer's harness does correctly
normalize some equivalent forms already — `command git ...` and `env git
...` were both correctly denied — so the gap is specifically the
absolute-path form, not a wholesale lack of normalization.

## Why this is a distinct bug from BUG-013

`BUG-013` is about argument reordering and global-flag injection *within*
the recognized `git`/`rm` command shape. This bug is about the deny
matcher never recognizing the command shape at all once the binary is
addressed by path. Critically, this **re-opens the exact git deny family
`BUG-013`'s owner-applied fix just closed** — the wildcard-between-`git`-
and-subcommand pattern (`Bash(git * reset*--hard*)` etc.) only matches
commands that literally start with the token `git`; `/usr/bin/git` does
not match that glob at all, by design of how the pattern is anchored.

## Fix needed, with an honest limit stated up front

Add path-prefixed twins for each protected command family, e.g.:

```
"Bash(*/git *)",
"Bash(*/rm *)",
"Bash(*/cp *)",
"Bash(*/mv *)",
"Bash(*/sed *)",
"Bash(*/tee *)",
"Bash(*/dd *)",
"Bash(*/truncate *)",
```

**This narrows the hole, it does not close it.** The reviewer was explicit
that glob-on-command-string denial cannot be made complete against a
determined bypass: `$(which git)`, a relative path (`../../../usr/bin/git`),
a shell alias, a copied/renamed binary, or invoking the binary through an
interpreter (`python3 -c "import subprocess; subprocess.run(['rm','-rf',...])"`)
all remain untouched even after the path-prefix patterns above are added.

## Architectural conclusion (recorded here, cross-referenced from BUG-013 and BUG-023)

`permissions.deny` glob-on-command-string matching is not sufficient as
the sole technical enforcement layer for protected Bash operations. The
correct direction — not implemented this chunk, recorded for a future
session — is to **keep deny patterns as defense-in-depth (they are free
and correctly catch the common/accidental case), and add a project-scoped
`PreToolUse` Bash security gate that parses/normalizes the requested
command (resolving the actual binary/subcommand rather than matching
surface text) and fails closed before execution for prohibited
operations.** This is a semantic check, not a string-glob check, and it
is the only approach that can close this class of bypass rather than
adding another enumerable pattern to a list that this bug and `BUG-013`
have now shown is inherently reorderable/spoofable.

## Remediation attempt v1 (2026-09-06): deny-by-enumeration guard, superseded after 4 rounds

A `.claude/security/bash_guard.py` PreToolUse hook was built per the
architectural conclusion above and put through four independent
fresh-context review rounds — each found new P0-severity bypasses,
including absolute-path/wrapper-class gaps directly in this bug's scope
(the guard's own wrapper denylist was found incomplete three times in a
row: round 2 added `nice`/`su`/`awk`/`ssh`/etc., round 3 added zsh
dialect gaps `noglob`/`nocorrect`/`repeat`/`coproc`, round 4 added
`builtin` and fixed case-sensitive command-name matching). Full record:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md`.
That pattern (every round finding something new) was itself treated as
an architectural finding — this whole design was superseded, not patched
a fifth time. Preserved as evidence at `.claude/security/superseded_v1/`.

## Remediation attempt v2 (2026-09-06): allow-by-construction redesign, 2-round cap reached, NOT certified

An entirely different design closes this bug's whole class structurally:
absolute-path/wrapper invocation (`/usr/bin/git`, `/bin/rm`, `env git`,
`RM`, `noglob`, `bash -c`, etc.) simply does not match ANY of v2's
explicit command-family shapes, so every one of them is denied by
construction — no wrapper-recognition code was written for any of them
specifically (confirmed by both review rounds' regression testing
against the full v1-era fixture corpus). Two independent review rounds
(the maximum permitted for this redesign pass) both judged the
architecture itself sound; round 2's residual findings were in different
command families (git refspec syntax, read-family path-traversal), not
in this bug's absolute-path/wrapper class, which held clean across both
rounds. Full record:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md`.
**This bug remains OPEN** — the 2-round cap was reached without a round
returning P0=0/P1=0 overall (even though this bug's specific class was
never the source of either round's findings), so per this project's
standing discipline it is not certified closed.

## Certification impact

**Blocks Phase 7 PASS**, alongside `BUG-013`'s residual and `BUG-023`.
Not fixed this chunk — recording only, per explicit instruction not to
modify `.claude/settings.json` in this session.

## Round 3 (2026-09-07): final owner-authorized review round — still OPEN

`veyro-security-reviewer` returned P0=0, P1=3, verdict BLOCKED. This
bug's class (absolute-path/wrapper/case-variant invocation) was
independently re-confirmed CLOSED for the Bash surface across the full
historical fixture set plus new probes (`env`, `command`, `builtin`,
`nice`, `sudo`, `doas`, `su -c`, `xargs`, `timeout`, `nohup`, `setsid`,
`stdbuf`, `eval`, `exec`, `source`, every shell `-c` form, every inline
interpreter invocation, case variants) — inline interpreter invocation
confirmed genuinely unreachable, not merely unlisted. One of the three
new P1s (`_ALLOWED_PYTHON_SCRIPTS` trusting seven mutable, unhashed
paths with no write protection on `.claude/security/**`) is a residual
of this bug's *class* via a different mechanism — re-entering
wrapper-style arbitrary execution by rewriting a trusted script rather
than wrapping an untrusted command. See
`BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md`. **This bug remains OPEN** —
the owner's gate rule requires overall P0=0/P1=0, not met. No further
review round is authorized. No `.claude/settings.json` edit was made.

## Round 3 P1 remediation (2026-09-07): trusted-script hash pinning fixed the wrapper-class re-entry; write-protection residual disclosed, still OPEN

Round 3's P1-2 (`_ALLOWED_PYTHON_SCRIPTS` trusting mutable, unhashed
paths) was a re-entry into this bug's class via a different mechanism —
rewriting a trusted script rather than wrapping an untrusted command.
Fixed via SHA-256 content-hash pinning: a tampered allowlisted script
can no longer be *executed* through the guard once its hash stops
matching. **Disclosed residual, not silently closed:** this is tamper
*detection*, not write *prevention* — `.claude/settings.json`'s Edit/Write
deny coverage still does not extend to `.claude/security/**`, and this
remediation pass was explicitly instructed not to touch
`.claude/settings.json`. **This bug remains OPEN** — narrowly-scoped
remediation, not an independent review; no Opus evaluation of this fix
has occurred. Full record:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_V2_ROUND3_P1_REMEDIATION_2026-09-07.md`.

## Affected

`.claude/settings.json` (the entire `permissions.deny` list, structurally
— every entry shares this gap), `knowledge/03-Modules/MOD-000/evidence/
security/PHASE7_SECURITY_REVIEW_2026-09-06.md`, `knowledge/00-System/
CURRENT_HANDOFF.md`, `knowledge/03-Modules/MOD-000/evidence/security/
BASH_GUARD_V2_ROUND3_REVIEW_2026-09-07.md`,
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_V2_ROUND3_P1_REMEDIATION_2026-09-07.md`.
