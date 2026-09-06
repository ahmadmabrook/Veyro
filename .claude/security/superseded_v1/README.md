# SUPERSEDED — v1 general-normalization Bash guard (2026-09-06)

`bash_guard_v1.py` and `test_bash_guard_v1.py` are the deny-by-enumeration
PreToolUse guard built earlier the same day, preserved here as evidence
per this project's durability discipline — **not deleted, not to be
reactivated.**

## Why superseded

Four independent fresh-context `veyro-security-reviewer` rounds (RR-1
through RR-4) each found new P0-severity bypasses:

| Round | P0 | P1 |
|---|---|---|
| RR-1 | 5 | 5 |
| RR-2 | 5 | 6 |
| RR-3 | 4 | 5 |
| RR-4 | 3 | 3 |

Every mechanically-fixable finding from every round was fixed and
tested (its own test suite grew 95 → 200, all passing at every
checkpoint) — but the pattern across all four rounds was structural, not
coincidental: this design tried to *understand* arbitrary Bash/zsh
syntax well enough to prove a request safe (normalize wrappers, resolve
absolute paths, skip git global options, track a virtual cwd, detect
redirection operators, recognize reserved words) and kept discovering
one more syntactic shape it hadn't modeled — a fresh shell dialect
(zsh vs. the bash the design assumed), a fresh redirection spelling
(`>!`, `&>|`), a fresh wrapper command, a fresh git config key that
executes its value as a shell command. Full round-by-round detail:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md`.

That pattern was treated as an architectural finding, not a queue of
more patches to apply. The replacement (`.claude/security/bash_guard.py`,
current) does not attempt general shell parsing at all: it allowlists a
small set of exact, structurally-validated command shapes and denies
everything else, including every syntactic form this v1 guard tried and
failed to defend against by recognition. See
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_V2_ARCHITECTURE_2026-09-06.md`
for the new design's full record.

## Do not

- Do not restore this file as the active guard.
- Do not delete this file or its test suite — it is the durable evidence
  base for why the v2 design exists.
- Do not treat "v1 passed N tests" as a safety claim; every version of
  v1 passed its own tests at every checkpoint and was still bypassed by
  the next fresh-context review.
