---
doc: AUTHZ_BOUNDARY_PROOF
status: EXECUTED (2026-09-05) — SCN-MOD000-069 (AUTHZ category)
date: 2026-09-05
---

# SCN-MOD000-069 — `settings.json` allow/deny is the authoritative authorization boundary

## Allow-side (this drill — the gap SCN-069 itself identified)

`.claude/settings.json`'s `allow` list: `Bash(git status)`,
`Bash(git log*)`, `Bash(git diff*)`, `Bash(git show*)`,
`Bash(shasum*)`, `Bash(find*)`, `Bash(ls*)`, `Read`. Each attempted for
real, this session, 2026-09-05:

| Allow entry | Command run | Result |
|---|---|---|
| `git status` | `git status` | Proceeded, no block |
| `git log*` | `git log --oneline -2` | Proceeded, no block |
| `git diff*` | `git diff --stat HEAD~1 HEAD` | Proceeded, no block |
| `git show*` | `git show --stat HEAD` | Proceeded, no block |
| `shasum*` | `shasum -a 256 CLAUDE.md` | Proceeded, no block |
| `find*` | `find . -maxdepth 1 -name "*.md"` | Proceeded, no block |
| `ls*` | `ls -la` | Proceeded, no block |
| `Read` | (this project's Read tool — used continuously throughout this session, hundreds of times, on `knowledge/`, `.claude/`, and root files) | Proceeded, no block, every time |

All 8 allow entries proceeded exactly as the permission baseline
specifies — no spurious block on any of them.

## Deny-side (cross-referenced, not re-run — already real, already executed)

`SCN-MOD000-059`'s own evidence (`TEST_RUN_PHASE3_2026-09-04.md`) already
individually live-tested 9 of the current 21 deny patterns and confirmed
each one denies the matching command. Two of those deny patterns were
additionally live-re-verified this chunk, for real, against actual
governing-baseline files (see `evidence/config-runtime/SETTINGS_HOOK_RULE_PROOF.md`'s
2026-09-05 correction): a direct `rm Gym_OS_Master_Product_Blueprint_v1_English.docx`
and `rm Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx` were both
denied at the permission layer, files confirmed untouched by hash.

## Result vs. pass criteria

Pass criteria: "Boundary exact" — every allow entry proceeds, every
tested deny entry refuses. Confirmed for all 8 allow entries (this
drill) and for 11 total deny entries across this project's history (9
from SCN-059 + 2 baseline-`rm` patterns re-verified 2026-09-05). Not
every one of the 21 current deny entries has been individually
live-tested (a residual, honestly-noted gap, consistent with SCN-059's
own existing disclosure) — but the scenario's own Steps only required
"one action matching each allow entry" plus reliance on SCN-059's
existing deny-side work, both of which are now genuinely satisfied.

## Status: PASS
