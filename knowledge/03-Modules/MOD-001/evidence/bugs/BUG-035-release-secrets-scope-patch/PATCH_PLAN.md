---
doc: BUG-035-RELEASE-SECRETS-SCOPE-PATCH-PLAN
status: LIVE
prepared: 2026-09-25
---

# BUG-035 round 4 follow-up — prepared owner patch: correct `release.md`'s and `secrets.md`'s `paths:`/`scope:` metadata

**Not applied.** `.claude/rules/**` remains Edit/Write-denied to every
session (`.claude/settings.json`). This file is the exact patch content
for the owner to apply directly, per this project's established
`BUG-034-patch/`/`BUG-035-paths-frontmatter-patch/` precedent.

## Why this patch, and why now

Round 4's independent `veyro-security-reviewer` (Opus) found the
owner's `paths:`-frontmatter patch (commit
`5ad7d3cbb67f0433031850b0e3180f7a4872cccc`) introduced 2 new P1 scope
gaps: `release.md`'s and `secrets.md`'s new `infra/**`-only scope
excludes surfaces their own already-approved control text and
already-qualified Stage-5 fixtures genuinely govern. This is not new
rule content — the control text and fixtures were already reviewed
clean in rounds 1-3; only the path-scoping metadata added in round 4
was wrong. Per this project's own instruction not to narrow rule
bodies to fit paths, but to fix paths to fit the already-governed
body, this patch corrects exactly that metadata.

## `release.md` — add `backend/**/*.py`

**Current (incorrect) scope:**
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---
```

**Corrected scope:**
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
  - "backend/**/*.py"
---
```

**Justification, from the rule's own body and its already-qualified
Stage-5 evidence (no body-text change, no new claim):**

- Control 1 (the file's own "clearest, most central and most
  security-sensitive control") prohibits a rollback trigger that is
  "an unauthenticated or convenience HTTP endpoint, CLI flag, webhook,
  or manual override callable by a human operator or external system"
  — a description of an exposure *mechanism*, not an infra-only
  concept. In this codebase's actual architecture, an HTTP endpoint is
  backend application code.
- This rule's own already-approved Stage-5 negative fixture
  (`knowledge/05-QA/capability-evidence/RULE-004/POSITIVE_NEGATIVE_EVAL_2026-09-22.md`
  §3) is exactly that: a `POST /admin/rollback` FastAPI route at
  `app/main.py` — `backend/app/main.py` in this project's real
  topology (`knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` line 426
  names `backend/app/main.py` as the canonical backend-surface example
  path). That fixture was authored and content-reviewed clean back in
  round 1 — round 4 only found that the *metadata* added afterward
  didn't cover the surface the evidence had already targeted.
- The compliant counterpart (the positive fixture,
  `infra/pipeline/canary_guardrail.py`) already sits inside the
  existing `infra/**` scope, confirming `infra/**` is still correct and
  necessary — this is an addition, not a replacement.
- No sibling backend rule (`RULE-005`..`009`) covers rollback triggers
  — independently grepped: only `database.md` mentions "rollback," in
  a migration-safety context, not a trigger-exposure context. Adding
  `backend/**/*.py` here is the only way this control's own named
  violation surface is ever actually in context when it matters.
- `backend/**/*.py` (not the broader `backend/**`) matches this
  project's own existing convention for a Python-code-boundary concern
  — the same glob already used by `RULE-005`/`006`/`008`/`009` for
  comparable "governs backend application code" bindings; `RULE-007`
  (`database.md`) is the deliberate exception because its own concern
  spans non-`.py` schema/migration artifacts, which does not apply
  here.
- No other named surface (mobile, admin-web, `tools/**`) appears in
  this rule's own text, `IMPLEMENTATION.md`'s Canary/rollback pipeline
  row (line 348, whose Input column is "Staging environment," not a
  named source path), or `REQUIREMENTS.md` GOV-01-R05 as a place this
  control's mechanism could live — adding scope beyond `backend/**/*.py`
  would not be grounded in any cited source, so none is added.

## `secrets.md` — replace `scope: path`/`paths:` with `scope: global`

**Current (incorrect) scope:**
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---
```

**Corrected scope:**
```yaml
---
scope: global
---
```

**Justification, from the rule's own body (no body-text change, no new
claim):**

- Control 1, the file's own "clearest, most central control," reads:
  "No secret is ever committed to the repository, in any form... This
  covers credentials, API keys, tokens, connection strings with
  embedded credentials, private keys, and signing keys — whether in
  source, config, fixtures, test data, or documentation." This is not
  a scoped claim — "the repository" and "in any form... source,
  config, fixtures, test data, or documentation" together name every
  category of file this repository contains, not an infra-specific
  subset.
- Control 3 explicitly reaches outside `infra/**` in its own text:
  "verify against the repository's existing `.gitignore`" (the
  `.gitignore` file lives at repo root, not under `infra/**`) and
  "never copied into a fixture or evidence file that itself gets
  committed" (evidence files live under
  `knowledge/05-QA/capability-evidence/**` and
  `knowledge/03-Modules/**`, entirely outside `infra/**`).
- An enumerated path list (`backend/**`, `knowledge/**`, `tools/**`,
  `contracts/**`, repo-root dotfiles, …) would be both unwieldy and
  structurally incomplete — the whole point of control 1 is a
  repository-wide invariant with no named exception, so any finite
  enumeration risks missing a future top-level directory the rule's
  own text already covers. `scope: global` is the mechanism this
  project already uses for exactly this shape of rule —
  `.claude/rules/global/owner-reserved-restrictions.md` carries
  `scope: global` with no `paths:` field for the same reason (a
  rule whose own text applies everywhere, by design).
- This is a narrower, more precise fix than reverting to no frontmatter
  at all (which round 3/4 already established fails EIP H.5's
  path-scope test): `scope: global` is itself a real, positive,
  path-scope-mechanism declaration — "this rule's scope is everywhere,
  deliberately" — not an absence of one.

**Consequence for Stage-5 evidence, not acted on this turn:** a
`scope: global` rule has no non-matching path to test against — EIP
H.5's positive/negative path-scope case becomes structurally N/A for
`RULE-002` specifically (the same way it would be N/A for
`owner-reserved-restrictions.md` if that file were ever put through
this qualification pipeline), not a FAIL to be closed by finding a
still-missing negative case. This project's `veyro-test-author` should
record it that way — `N/A (scope: global)`, not `PASS`/`FAIL` — when
Stage-5 evidence is next re-run for this file. Not evaluated or
recorded as evidence this turn, per this turn's explicit scope.

## Files this patch does not touch

`iac.md`, `observability.md`, and the 5 backend rule files
(`architecture.md`, `api.md`, `database.md`, `concurrency.md`,
`performance.md`) are unaffected — round 4 found no scope gap in any
of them, and this patch does not introduce one. Nothing about this
patch changes any rule's substantive control text, relaxes or adds a
control, or touches a DC-16 owner-reserved matter (no spend, no
production, no real member data, no product/pricing/business/
architecture/scope change) — it corrects path-scoping metadata to
match content every prior round already qualified. No ADR or
`OWN-<NNN>` entry is required or proposed, per the same reasoning the
original frontmatter patch (`BUG-035-paths-frontmatter-patch/PATCH_PLAN.md`)
already established for this class of change.

## Once applied

After the owner applies this patch, the next legally allowed action is
(1) a fresh `veyro-test-author` Stage-5 evidence re-run for all 9 rule
files bound to the new commit — `release.md`'s re-run should re-confirm
its already-qualified fixtures now genuinely match/exclude under the
corrected scope, and `secrets.md`'s re-run should record its path-scope
case as `N/A (scope: global)` rather than attempt a now-inapplicable
matching/non-matching test — then (2) a fifth independent qualification
review. `RULE-001` through `RULE-009` remain `BLOCKED` and `BUG-035`
remains `OPEN` until that review returns P0=0/P1=0.
