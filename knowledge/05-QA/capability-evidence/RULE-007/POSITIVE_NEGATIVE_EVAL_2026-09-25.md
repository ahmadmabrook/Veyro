---
doc: RULE-007-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-007 Stage-5 Qualification Evidence — `.claude/rules/backend/database.md`

**Rule ID:** RULE-007
**Source rule file:** `.claude/rules/backend/database.md`
**Commit binding:** `183acd535e6786f1edc1993a5ef6f13afd13a4ec`. Supersedes
the prior binding to `5aa5cc5b6b6d041372b83e043febf179d0460fa5` in
`POSITIVE_NEGATIVE_EVAL_2026-09-22.md` (retained as historical record, not
deleted). **Correction (Round 5 review, 2026-09-25, P2-1):** the true
current governed HEAD is `8e90680e8e8bcbd86e5136b6181371ac8161eee7` (this
repo's own subsequent commit, which only added the Stage-5 evidence/
registry files and touched nothing under `.claude/rules/**`), not `183acd5`
as this file's binding line above originally claimed — a self-reference
staleness defect. Content-identical: `.claude/rules/backend/database.md`
is byte-for-byte unchanged across `183acd5`/`14d1337`/`8e90680` (re-verified
via `shasum -a 256`, `9483ab4aa9df14ebfe38192b89fecd221d1b0fc9b93839d9579878fe2fbe7e76`,
matching `CAPABILITY_REGISTRY.md`'s recorded hash exactly), so this
evidence's substance is unaffected.
**Reviewer/model evidence:** veyro-test-author (Sonnet tier per
`DEVELOPMENT_CONSTITUTION.md` model routing — this session's actual model
is `claude-sonnet-5`)
**Timestamp:** 2026-09-25
**Status of this evidence:** content-level qualification: sound, carried
forward unchanged from 2026-09-22. Path-scope qualification: **PASS**
(both matching and non-matching cases) — a real `paths:` frontmatter
mechanism now exists, added in commit `5ad7d3c` and unchanged by
`183acd5` (that commit's diff touches only `release.md`/`secrets.md`).

## 1. Applicability binding as currently documented

**Rule file's own frontmatter (quoted verbatim, re-read this session):**
```yaml
---
scope: path
paths:
  - "backend/**"
---
```

**Note this rule's glob is broader than the other four `backend/**/*.py`
rules in this set.** `backend/**` (no `*.py` suffix restriction) matches
any file of any type under `backend/` — SQL migration files, YAML config,
Alembic scripts — not only `.py` source. This is intentional and matches
the rule's own heading and scope note, which govern "schema, models,
migrations," not exclusively Python source files.

**What this evidence does NOT claim:** whether Claude Code's rule-loader
actually reads and enforces this `paths:` frontmatter at runtime remains
itself unverified by this project. §2 below is textual glob-matching
reasoning, not an observed harness load/skip event.

## 2. Path-scope qualification case (EIP H.5)

**Note on fixture path availability:** this rule's own content-level
fixtures (§3) are raw SQL DDL statements with no `# path` comment — no
literal fixture path is recorded to test the glob against. To exercise
the glob honestly, this section uses an illustrative migration file path
representative of where this control actually applies, labeled as
illustrative rather than drawn from the rule's own recorded fixture.

| Case | Expected result | Actual result (textual glob-matching reasoning, not a harness-observed load event) |
|---|---|---|
| Matching path — illustrative `backend/alembic/versions/0007_add_reservations_rls.py` (an Alembic migration file, per this project's `backend/app/...` topology, `IMPLEMENTATION.md` line 426; not itself a rule-recorded fixture path) | Rule loads and applies | **PASS.** `backend/**` matches any path beginning with the literal segment `backend/`, of any depth and any file extension. The illustrative path satisfies this trivially — and, notably, would also satisfy it if it were a non-`.py` file (e.g. a raw `.sql` migration script), which the narrower `backend/**/*.py` glob used by the other four backend rules would not match. This is the concrete effect of this rule's broader glob. |
| Non-matching path — e.g. `infra/environments/qa/database.yaml` | Rule does not load / does not apply | **PASS.** First segment `infra` does not match `backend`. Correctly excluded. |

**No cross-family false match.** This rule's glob (`backend/**`) shares
no first path segment with the infra-family rules' globs (`infra/**`,
`.github/workflows/**`) — disjoint literal segments, so no cross-family
false match is possible through this mechanism.

**Reasoning method, stated explicitly:** manual textual evaluation of the
glob syntax, not an observed harness event and not a test-tool run (none
exists in this repo; `backend/` does not exist yet as a real directory,
and no `veyro-critical-engineer`-owned RLS-lint harness exists yet per
this rule's own scope note).

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md`.** This rule's
controls 1 and 2 text was not touched by either owner patch commit —
re-verified this session by reading `.claude/rules/backend/database.md`
directly. The fixture pair and verdicts are carried forward.

**Controls under test:** controls 1 and 2 together (unchanged).

**Control 1 clause (quoted verbatim):**
> Every tenant-owned table has `tenant_id NOT NULL`. No tenant table may
> leave `tenant_id` nullable — TSD §24.1's RLS lint denies this as
> `RLS_TENANT_ID_NULLABLE`, citing the column.

**Control 2 clause (quoted verbatim):**
> Every tenant-owned table has RLS enabled and forced. Every such table
> carries `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`,
> plus at least one RLS policy that scopes visible/writable rows to the
> resolved tenant context. A table missing `FORCE ROW LEVEL SECURITY`
> fails as `RLS_NOT_ENFORCED`.

### Positive fixture (conforms)

```sql
CREATE TABLE booking.reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    member_id uuid NOT NULL,
    status text NOT NULL
);

ALTER TABLE booking.reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE booking.reservations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON booking.reservations
    USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

### Negative fixture (deliberately violates)

```sql
CREATE TABLE booking.reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid,
    member_id uuid NOT NULL,
    status text NOT NULL
);
-- no ENABLE/FORCE ROW LEVEL SECURITY, no policy
```

**Result (carried forward): positive fixture ALLOW; negative fixture
DENY on two independent grounds** (`RLS_TENANT_ID_NULLABLE` and
`RLS_NOT_ENFORCED`). This determination is independent of the path-scope
frontmatter change and is not affected by it.

## 4. Source citations

**`CAPABILITY_POLICY.md` stage 5 (quoted verbatim):**
> 5. **Qualification** — before first real use:
>    - **Positive test**: capability does the thing it claims, on a
>      synthetic fixture.
>    - **Negative test**: capability correctly fails/refuses on an
>      out-of-scope or malicious input.
>    - Both results recorded as evidence (see below).

**EIP `EIP_MIRROR.md` lines 20809-20825 (the two relevant bullets, quoted
verbatim):**
> Every new Skill/Rule must have at least one success-path eval and one
> failure/negative eval; security-sensitive capabilities also require
> abuse/prompt-injection/permission-negative tests.

> A Rule change must be tested against representative matching and
> non-matching paths so path scoping is correct and does not pollute
> unrelated contexts.

**Rule file's own controls 1 and 2 clauses and frontmatter:** quoted in
full in §1 and §3 above.
