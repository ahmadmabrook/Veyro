# SCN-020 disposable protected target — 2026-10-09

Classification: **MANDATORY_NOW** under existing GOV-01-R04 / SCN-MOD001-020; no new optional work. This is prerequisite setup, **not SCN-020 execution or PASS**. Sole runner operation: `02c25554-39bd-41fa-9130-527a399e383c`.

Using an isolated clean Git worktree at `/tmp/veyro-scn020-02c25554` from pinned public `origin/main` `e516bedabf3d654ad3ae16d948b8f3522739ddc2`, the executor copied only four gate fixture files: `.github/workflows/event-contract.yml`, `tools/validate_architecture_gates.py`, `contracts/events/registry.json`, and `contracts/events/baseline.json`. `git diff --cached --check` and Python compile passed; `gitleaks git --staged --redact=100` returned exit 0. No unrelated dirty worktree file, raw credential evidence, real data, or governing baseline was staged. The exact four-file commit `36457b4dbe309355c5fede5f56c451371bcfd1f6` was pushed **only** to `refs/heads/scn020-protected-base-20261009`; `main` remains unchanged.

The first GitHub branch-protection PUT returned HTTP 422 because the payload supplied the same required check via both `contexts` and `checks`. It made no rule. The corrected PUT used `contexts` alone and returned success. Independent GET readback of the named disposable target showed:

- `protected: true`, commit SHA exactly `36457b4dbe309355c5fede5f56c451371bcfd1f6`;
- required status context exactly `architecture-event-contract`, `strict: true`;
- administrator enforcement `true`; required PR reviews configured with zero approving reviews; unrestricted push actor list `null` but PR requirement applies;
- force pushes and deletions disabled;
- `main` still `protected: false` at its prior `e516bed...` SHA. No main rule, repository visibility, or plan was changed.

Next mandatory step: create a minimal synthetic head branch/PR targeting this protected branch; observe a real `architecture-event-contract` status on the PR, then execute and record each SCN-020(a)-(i) bypass attempt against disposable artifacts. A protected branch and required-context configuration alone do not prove enforcement. The gate-3 independent review remains unconsumed and must wait until required execution/evidence is complete. R1-F14 remains formally CLOSED; gate-2 closure, U1/U2 B HOLD, SCN-070 cap, and MOD-001 exit 0/8 are unchanged.
