---
doc: GITHUB_REMOTE_PROOF
status: LIVE
date: 2026-09-01
---

# GitHub Remote Configuration Proof

Governed backup/collaboration mirror. Does **not** replace Git + `knowledge/` as the engineering authority — GitHub is an additional durable copy, same governance role as Notion (mirror, not authority).

## Pre-push verification (all passed before any push)

- `git status`: clean HEAD at the required commit; only later, still-uncommitted evidence edits present in the working tree (not part of this push's ref).
- Secrets/tracked-file scan: `git ls-tree -r HEAD --name-only | grep -iE "secret|credential|\.env|\.pem|\.key$|local\.json|token|password"` — zero matches.
- `.gitignore` re-inspected: still correctly excludes secrets/IDE-state/caches/build-artifacts/`settings.local.json` while never touching baselines/`knowledge/`/`.claude/`.
- Governed commit SHA confirmed: `3e6d88fa03ad4569c6e34be57efa72b612fff77f` (matches the required value exactly, no new commit created this chunk).
- All 4 governing baseline hashes re-verified against `PROJECT_INDEX.md`: 3 docx exact match; design-bundle manifest hash `c96f77ab...` exact match.

## Repository creation

- Command: `gh repo create Veyro --private --source=. --remote=origin --description "..."`.
- Result: **https://github.com/ahmadmabrook/Veyro** — confirmed `"isPrivate":true,"visibility":"PRIVATE"` via `gh repo view --json`.
- No GitHub Actions, deployments, environments, secrets, packages, or releases configured — none touched, per instruction.
- No paid service activated — a private repo on the authenticated free/existing plan involves no spend.

## Push

- `git push -u origin main` — new branch, no force, no history rewrite.
- Upstream tracking set: `main` -> `origin/main`.

## Verification (multiple independent checks, all exact matches)

| Check | SHA |
|---|---|
| Local `HEAD` | `3e6d88fa03ad4569c6e34be57efa72b612fff77f` |
| Local `main` | `3e6d88fa03ad4569c6e34be57efa72b612fff77f` |
| `git ls-remote origin main` (server-authoritative) | `3e6d88fa03ad4569c6e34be57efa72b612fff77f` |
| Local `origin/main` tracking ref | `3e6d88fa03ad4569c6e34be57efa72b612fff77f` |
| Fresh clone (`/tmp/veyro_github_clone_verify`, plain `git clone` over HTTPS) `HEAD` | `3e6d88fa03ad4569c6e34be57efa72b612fff77f` |
| Baseline hash inside the fresh GitHub clone | `80f4b381...` (exact match to `PROJECT_INDEX.md`) |

All 6 independent references agree exactly. No divergence, no rewrite.

## Non-blocking note

The separate GitHub **MCP connector** (`plugin:github:github`) remains disconnected ("Authorization header is badly formatted", 400) — unrelated to `gh` CLI auth, which is what was used here and is fully operational. Not a blocker for this task; would need the user to reconnect it in claude.ai connector settings if MCP-mediated GitHub actions are wanted later.

## Durable record

- **Repository identity:** `ahmadmabrook/Veyro`
- **Remote URL:** `https://github.com/ahmadmabrook/Veyro.git`
- **Branch:** `main` (tracking `origin/main`)
- **Pushed commit SHA:** `3e6d88fa03ad4569c6e34be57efa72b612fff77f`
- **Verification timestamp:** 2026-09-01
- **Verification result:** PASS — all 6 checks above agree exactly
