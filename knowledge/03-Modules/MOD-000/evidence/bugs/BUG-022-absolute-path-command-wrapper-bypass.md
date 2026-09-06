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

## Certification impact

**Blocks Phase 7 PASS**, alongside `BUG-013`'s residual and `BUG-023`.
Not fixed this chunk — recording only, per explicit instruction not to
modify `.claude/settings.json` in this session.

## Affected

`.claude/settings.json` (the entire `permissions.deny` list, structurally
— every entry shares this gap), `knowledge/03-Modules/MOD-000/evidence/
security/PHASE7_SECURITY_REVIEW_2026-09-06.md`, `knowledge/00-System/
CURRENT_HANDOFF.md`.
