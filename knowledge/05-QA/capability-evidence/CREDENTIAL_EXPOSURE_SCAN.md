---
doc: CREDENTIAL_EXPOSURE_SCAN
status: EXECUTED (2026-09-12) — SCN-MOD000-068
date: 2026-09-12
---

# SCN-MOD000-068 — Capability credentials never logged/exposed in evidence

## What was missing

This scenario had never been formally executed as its own dedicated
artifact — only informally checked (during the original GitHub-push work
and during a Phase 5 commit review), with results noted in passing
rather than captured as this scenario's own required evidence file.

## What was run

Real, repo-wide pattern scans against `knowledge/`, each a single grep
for a real, distinctive credential-format prefix:

| Pattern | What it detects | Hits |
|---|---|---|
| `secret_` | Notion internal integration secret prefix | 0 |
| `ghp_` | GitHub personal access token prefix | 0 |
| `sk-ant-` | Anthropic API key prefix | 0 |
| `AKIA` | AWS access key ID prefix | 0 |
| `TESTSPRITE_API_KEY` | TestSprite credential env-var name | 2 files — both inspected directly |

The two `TESTSPRITE_API_KEY` hits are both the **variable name**, not a
value: `AUTHENTICATION_FAILURE_DRILL.md` line 25 uses a deliberately
invalid scratch credential (`ts_invalid_scratch_credential_00000...`) as
the drill's own negative-test fixture (SCN-095's own evidence — the
credential is fake by design, that is the point of the drill), and
`SCENARIO_CATALOG.md`'s reference to it in prose describing that same
drill. Neither is a real credential.

## Result vs. pass criteria

Pass criteria: 0 credential-shaped strings found in any durable file.
**0 found**, across every pattern checked. The two `TESTSPRITE_API_KEY`
name-only hits are expected and correctly not credential values.

## Status: PASS
