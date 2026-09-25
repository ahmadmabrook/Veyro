---
doc: BUG-035-PATHS-FRONTMATTER-PATCH-PLAN
status: LIVE
prepared: 2026-09-22
---

# BUG-035 — prepared owner patch: `paths:` frontmatter for RULE-001..RULE-009

**Not applied.** `.claude/rules/**` remains Edit/Write-denied to every
session (`.claude/settings.json`). This file is the exact patch content
for the owner to apply directly, per this project's established
`BUG-034-patch/` precedent (`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-034-patch/`).

## Why this patch, and why now

Round 3 of `BUG-035`'s qualification review found P1-A closed but a new
P1 (P1-Q — no Stage-5 evidence existed). A same-day follow-up produced
that evidence (`knowledge/05-QA/capability-evidence/RULE-<NNN>/`) and, in
doing so, confirmed a real, reproducible gap: none of the 9 rule files
has `paths:` YAML frontmatter, so EIP Appendix H.5's path-scope
qualification test ("A Rule change must be tested against representative
matching and non-matching paths so path scoping is correct and does not
pollute unrelated contexts," `EIP_MIRROR.md` lines 20819-20821) fails for
all 9 — they load unconditionally regardless of path. `EIP_MIRROR.md`
line 20631 separately lists "paths glob" as a required field on every
`RULE-<NNN>` record. This patch closes that specific, confirmed gap.

## Structural reference

`.claude/rules/global/knowledge-vault-durability.md`'s existing
frontmatter is the convention followed exactly:
```yaml
---
scope: path
paths:
  - "knowledge/**"
  - "Notion:*"
---
```
Two other pre-existing rules were also checked for the same convention:
`owner-reserved-restrictions.md` uses `scope: global` (no `paths:` field
— it applies everywhere, by design); `notion-mcp-scope-discipline.md`
and `admin-privileged-console-baseline.md` carry no frontmatter at all
(the first is tool-call-scoped, not path-scoped; the second binds
forward to a module with no surface yet). This confirms `scope: path` +
`paths:` is the correct shape for all 9 files here, since each already
has a real, current path binding (unlike the two frontmatter-less
examples).

## Patch shape (identical mechanic for all 9 files)

Insert the frontmatter block as the new first lines of the file — before
the existing `<!-- Target path once applied: ... -->` comment, which is
otherwise untouched. Nothing else in any file changes: no body rewrite,
no P2/Editorial remediation, no control-text edit.

## Per-file patch

### RULE-001 — `.claude/rules/infra/iac.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---

```
**Derivation:** the file's own heading — `# Rule: Infra/SRE —
Infrastructure-as-Code (IaC) Baseline (`infra/**` binding)` — and
`CAPABILITY_REGISTRY.md`'s RULE-001 `scope` column — "Governs
`infra/**`/`.github/workflows/**`" — agree exactly; `.github/workflows/**`
is included because control 5 (CI-Action supply-chain / SHA-pinning)
specifically governs workflow files.
**Positive (matching) path:** a change under `infra/**` or
`.github/workflows/**` (e.g. `infra/environments/qa/database.yaml`, the
positive fixture in this rule's Stage-5 evidence).
**Negative (non-matching) path:** a change under `knowledge/**` or
`frontend/**` — unrelated to infra.

### RULE-002 — `.claude/rules/infra/secrets.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---

```
**Derivation:** heading — `(`infra/**` binding)` — matches registry
scope "Governs `infra/**`/`.github/workflows/**`" exactly.
**Positive path:** `infra/environments/qa/.env.example` (this rule's own
Stage-5 positive fixture path).
**Negative path:** `knowledge/**`, `frontend/**`.

### RULE-003 — `.claude/rules/infra/observability.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---

```
**Derivation:** heading — `(`infra/**` binding)` — matches registry
scope exactly.
**Positive path:** a change under `infra/**` or `.github/workflows/**`.
**Negative path:** `knowledge/**`, `frontend/**`.

### RULE-004 — `.claude/rules/infra/release.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---

```
**Derivation:** heading — `(`infra/**` binding)` — matches registry
scope exactly.
**Positive path:** a change under `infra/**` or `.github/workflows/**`.
**Negative path:** `knowledge/**`, `frontend/**`.

### RULE-005 — `.claude/rules/backend/architecture.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "backend/**/*.py"
---

```
**Derivation:** heading — `(`backend/**/*.py` binding)` — matches
registry scope "Governs `backend/**/*.py`" exactly.
**Positive path:** a `.py` change under `backend/**` (e.g.
`backend/app/modules/membership/service.py`).
**Negative path:** `knowledge/**`, `infra/**`.

### RULE-006 — `.claude/rules/backend/api.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "backend/**/*.py"
---

```
**Derivation:** heading — `(`backend/**/*.py` binding)` — matches
registry scope exactly.
**Positive path:** a `.py` change under `backend/**`.
**Negative path:** `knowledge/**`, `infra/**`.

### RULE-007 — `.claude/rules/backend/database.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "backend/**"
---

```
**Derivation:** heading — `(`backend/**` binding)`, deliberately broader
than RULE-005/006/008/009's `backend/**/*.py` — this rule's own text
governs "schema, models, migrations," which is not limited to `.py`
files (e.g. raw SQL/DDL fixtures, Alembic env config). Registry scope:
"Governs `backend/**` schema/models/migrations." No narrowing to `*.py`
is warranted; narrowing it would exclude non-`.py` schema/migration
artifacts the rule explicitly covers.
**Positive path:** `backend/app/modules/booking/models.py` or a
migration file under `backend/alembic/versions/**` (this rule's own
Stage-5 positive fixture is a `CREATE TABLE` statement, i.e. schema
content, not necessarily `.py`).
**Negative path:** `knowledge/**`, `infra/**`.

### RULE-008 — `.claude/rules/backend/concurrency.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "backend/**/*.py"
---

```
**Derivation:** heading — `(`backend/**/*.py` binding)` — matches this
file's own stated binding exactly (the registry `scope` column's
"Governs `backend/**` mutable-aggregate persistence" text is broader
prose, but the file's own heading is the more specific, authoritative
per-file binding, consistent with how RULE-005/006/009 are handled).
**Positive path:** a `.py` change under `backend/**`.
**Negative path:** `knowledge/**`, `infra/**`.

### RULE-009 — `.claude/rules/backend/performance.md`

Insert at line 1:
```yaml
---
scope: path
paths:
  - "backend/**/*.py"
---

```
**Derivation:** heading — `(`backend/**/*.py` binding)` — matches
registry scope "Governs `backend/**/*.py`" exactly.
**Positive path:** a `.py` change under `backend/**`.
**Negative path:** `knowledge/**`, `infra/**`.

## Overlap check (requirement: no contradictory bindings)

- `infra/**` (RULE-001..004) and `backend/**` (RULE-005..009) never
  overlap — disjoint top-level directories. No contradiction possible
  between the infra and backend rule sets.
- Within infra: all 4 rules share the identical `infra/**` +
  `.github/workflows/**` binding — by design, since all 4 govern the
  same `infra/**`/CI surface from different angles (IaC, secrets,
  observability, release) exactly as `CAPABILITY_REGISTRY.md`'s existing
  scope column already states for each. This is intentional co-loading,
  not a contradiction — the same pattern MOD-000's own rules already use
  (e.g. `owner-reserved-restrictions.md` and
  `knowledge-vault-durability.md` both load for every `knowledge/**`
  touch, with no conflict, since each governs a distinct concern).
- Within backend: RULE-005/006/008/009 share the identical
  `backend/**/*.py` binding (four distinct concerns — architecture,
  API boundaries, concurrency, performance — over the same Python
  surface, again intentional co-loading). RULE-007 (`backend/**`,
  unrestricted) is deliberately broader, matching its own distinct
  binding (schema/migration files are not all `.py`). No two rules make
  contradictory claims about the same path — every rule that shares a
  path with another governs a genuinely distinct concern over it.

## Consistency with the Stage-5 evidence already on disk

Every positive/negative path pair above matches the exact path language
already recorded in
`knowledge/05-QA/capability-evidence/RULE-<NNN>/POSITIVE_NEGATIVE_EVAL_2026-09-22.md`'s
§2 table for that rule — this patch does not introduce a new binding the
existing evidence didn't already anticipate; it only adds the mechanism
that would make those already-recorded matching/non-matching cases
actually testable.

## No ADR / OWN-<NNN> needed

This patch adds path-scoping metadata to satisfy an already-binding EIP
requirement (`EIP_MIRROR.md` line 20631's "paths glob" field, lines
20819-20821's path-scope test) — it does not change any rule's
substantive content, does not relax or add a control, does not touch any
DC-16 owner-reserved matter (no spend, no production, no real member
data, no scope change), and does not create a new precedent this
project's existing rules don't already establish (2 of the 4
pre-existing `.claude/rules/*.md` files already carry exactly this
frontmatter shape). No ADR or `OWN-<NNN>` entry is required or proposed.

## Once applied

After the owner applies this patch, the next legally allowed action is a
fourth independent fresh-context qualification review (`veyro-security-reviewer`,
Opus) re-running the path-scope case for all 9 files — this time
executable for real, not `NOT EXECUTABLE`/`BLOCKED` — before `RULE-001`
through `RULE-009` may read `APPROVED` and `BUG-035` may close.
`RULE-001` through `RULE-009` remain `BLOCKED` and `BUG-035` remains
`OPEN` until that review returns P0=0/P1=0.
