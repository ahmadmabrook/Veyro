---
doc: RULE-007-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-007 Stage-5 Qualification Evidence — `.claude/rules/backend/database.md`

**Rule ID:** RULE-007
**Source rule file:** `.claude/rules/backend/database.md`
**Commit binding:** `5aa5cc5b6b6d041372b83e043febf179d0460fa5` (current HEAD;
no edit was made to any file under `.claude/rules/**` in the course of
producing this evidence)
**Reviewer/model evidence:** veyro-test-author (Sonnet tier per
`DEVELOPMENT_CONSTITUTION.md` model routing — this session's actual model
is `claude-sonnet-5`)
**Timestamp:** 2026-09-22
**Status of this evidence:** `PARTIAL` — content-level positive/negative
recorded (textual evaluation); EIP H.5's path-scope test FAILED/BLOCKED
(see §2). Not `QUALIFIED` (per `CAPABILITY_POLICY.md`, `QUALIFIED` means
"tests ran and passed" — the path-scope test did not pass) and not
`APPROVED`. (Corrected after independent Opus review found the original
`QUALIFIED` label here was not earned, since §2's own result is a FAIL,
not a pass.)

## 1. Applicability binding as currently documented

**Rule file's own heading (quoted verbatim):**
> # Rule: Backend PostgreSQL Tenant Isolation (RLS) and Migration Safety
> (`backend/**` binding)

**`CAPABILITY_REGISTRY.md` RULE-007 row, `scope` column (quoted verbatim):**
> Governs `backend/**` schema/models/migrations — read/guidance only

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified by reading `.claude/rules/backend/database.md` lines 1-6 this
session: it opens with `<!-- Target path once applied:
.claude/rules/backend/database.md -->` then the `# Rule: ...` heading
directly — no `---` YAML block, no `paths:`/`scope:` field, unlike
`.claude/rules/global/knowledge-vault-durability.md`'s real `scope: path`
/ `paths: [...]` frontmatter. RULE-007 loads unconditionally regardless
of path.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (`backend/**` schema/model/migration change) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. `knowledge/**`, `infra/**`) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** same structural gap as the other files in this set — no
`paths:` glob mechanism exists to exercise a matching-vs-non-matching
test against. Recorded honestly as BLOCKED, not fabricated as a pass.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Controls under test:** controls 1 and 2 together — the clearest,
most central pairing (tenant-id nullability and RLS enforcement), which
the rule's own text names as two distinct named lint failure codes
(`RLS_TENANT_ID_NULLABLE`, `RLS_NOT_ENFORCED`) checkable against a single
`CREATE TABLE` fixture.

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

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text: *"A tenant table without `tenant_id NOT
NULL` plus an enforced RLS policy plus `FORCE ROW LEVEL SECURITY`...
does not merge. The RLS lint... [is] CI-blocking."*).

**Actual deterministic evaluation (manual/textual — no
`veyro-critical-engineer`-owned RLS-lint harness exists yet per this
rule's own scope note; `backend/` does not exist, so this is a reading of
the rule's own prose against the two SQL fixtures, not a lint run):**

- **Positive fixture → ALLOW.** `tenant_id uuid NOT NULL` satisfies
  control 1 exactly. `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL
  SECURITY` + a policy scoping rows to `current_setting('app.tenant_id')`
  satisfies control 2's three-part requirement in full.
- **Negative fixture → DENY on two independent grounds.**
  `tenant_id uuid` (no `NOT NULL`) is exactly `RLS_TENANT_ID_NULLABLE`
  (control 1's named failure code). The absence of any `ENABLE`/`FORCE
  ROW LEVEL SECURITY` statement is exactly `RLS_NOT_ENFORCED` (control
  2's named failure code, which the rule states fires specifically on a
  missing `FORCE ROW LEVEL SECURITY`).

**Result: the rule's own text correctly distinguishes the compliant
fixture (ALLOW) from the violating one (DENY), and does so with two
independently-named failure codes on the negative side — consistent with
the rule's own stated mechanical-check granularity.**

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

**Rule file's own controls 1 and 2 clauses:** quoted in full in §3 above.
