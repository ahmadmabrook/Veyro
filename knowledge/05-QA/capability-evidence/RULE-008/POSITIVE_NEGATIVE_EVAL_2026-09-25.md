---
doc: RULE-008-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-008 Stage-5 Qualification Evidence — `.claude/rules/backend/concurrency.md`

**Rule ID:** RULE-008
**Source rule file:** `.claude/rules/backend/concurrency.md`
**Commit binding:** `183acd535e6786f1edc1993a5ef6f13afd13a4ec`. Supersedes
the prior binding to `5aa5cc5b6b6d041372b83e043febf179d0460fa5` in
`POSITIVE_NEGATIVE_EVAL_2026-09-22.md` (retained as historical record, not
deleted). **Correction (Round 5 review, 2026-09-25, P2-1):** the true
current governed HEAD is `8e90680e8e8bcbd86e5136b6181371ac8161eee7` (this
repo's own subsequent commit, which only added the Stage-5 evidence/
registry files and touched nothing under `.claude/rules/**`), not `183acd5`
as this file's binding line above originally claimed — a self-reference
staleness defect. Content-identical: `.claude/rules/backend/concurrency.md`
is byte-for-byte unchanged across `183acd5`/`14d1337`/`8e90680` (re-verified
via `shasum -a 256`, `f618731725f88d4ea811f6f7420a837614cbaa89b4c8050d2c8f45e03f321f53`,
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
  - "backend/**/*.py"
---
```

**What this evidence does NOT claim:** whether Claude Code's rule-loader
actually reads and enforces this `paths:` frontmatter at runtime remains
itself unverified by this project. §2 below is textual glob-matching
reasoning, not an observed harness load/skip event.

## 2. Path-scope qualification case (EIP H.5)

**Fixture path and this project's topology.** This rule's own recorded
negative content fixture (§3) carries the comment
`# app/modules/booking/service.py — same table, version column present
but unused`. Per `IMPLEMENTATION.md` line 426 (`backend/app/main.py`
named as the canonical full-repo-path example), that comment is relative
to the backend application root, so the full repository path is
`backend/app/modules/booking/service.py`.

| Case | Expected result | Actual result (textual glob-matching reasoning, not a harness-observed load event) |
|---|---|---|
| Matching path — `backend/app/modules/booking/service.py` (this rule's own recorded fixture path, read against the project's `backend/app/...` topology) | Rule loads and applies | **PASS.** `backend/**/*.py` matches: literal `backend/`, then `**` matches `app/modules/booking/`, then `service.py` matches `*.py`. |
| Non-matching path — e.g. `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` | Rule does not load / does not apply | **PASS.** First segment `knowledge` does not match `backend`. Correctly excluded. |

**No cross-family false match.** This rule's glob (`backend/**/*.py`)
shares no first path segment with the infra-family rules' globs
(`infra/**`, `.github/workflows/**`) — disjoint literal segments, so no
cross-family false match is possible through this mechanism.

**Reasoning method, stated explicitly:** manual textual evaluation of the
glob syntax against the recorded fixture path, not an observed harness
event and not a test-tool run (none exists in this repo).

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md`.** This rule's
controls 1 and 2 text was not touched by either owner patch commit —
re-verified this session by reading `.claude/rules/backend/concurrency.md`
directly. The fixture pair and verdicts are carried forward.

**Controls under test:** controls 1 and 2 together (unchanged).

**Control 1 clause (quoted verbatim):**
> Every mutable aggregate's table carries an explicit version column. A
> table supporting in-place mutation of a business-meaningful row (not
> append-only/immutable) has a version/optimistic-lock column (e.g.
> `version integer NOT NULL DEFAULT 1`...). A mutable-aggregate table
> with no such column violates `DOM-002`.

**Control 2 clause (quoted verbatim):**
> Every mutation reads, checks, and increments the version in one atomic
> statement. A mutation includes the version it read in the update's
> `WHERE` clause and increments it as part of the same
> statement/transaction — e.g. `UPDATE ... SET version = version + 1
> WHERE id = :id AND version = :expected_version`. A mutation that writes
> to a versioned table without a version-checked `WHERE` predicate is a
> rule violation, whether or not a conflict happens to occur in practice.

### Positive fixture (conforms)

```sql
-- schema
ALTER TABLE booking.reservations ADD COLUMN version integer NOT NULL DEFAULT 1;
```

```python
# app/modules/booking/service.py
result = await conn.execute(
    "UPDATE booking.reservations SET status = :status, version = version + 1 "
    "WHERE id = :id AND version = :expected_version",
    {"status": status, "id": reservation_id, "expected_version": expected_version},
)
if result.rowcount == 0:
    raise ConcurrencyConflictError(aggregate_id=reservation_id)  # typed, distinguishable conflict (control 3)
```

### Negative fixture (deliberately violates)

```python
# app/modules/booking/service.py — same table, version column present but unused
result = await conn.execute(
    "UPDATE booking.reservations SET status = :status WHERE id = :id",
    {"status": status, "id": reservation_id},
)
```

**Result (carried forward): positive fixture ALLOW; negative fixture
DENY.** The positive fixture's `WHERE`/`SET` clause satisfies the atomic
read-check-increment requirement; the negative fixture's `WHERE id = :id`
clause omits the version predicate entirely and never increments
`version` — exactly the "deliberately-broken version-check fixture" this
rule's own fail-closed text names. This determination is independent of
the path-scope frontmatter change and is not affected by it.

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

**`IMPLEMENTATION.md` line 426 (quoted phrase establishing topology):**
> A source file under a surface's path scope (e.g. `backend/app/main.py`)

**Rule file's own controls 1 and 2 clauses and frontmatter:** quoted in
full in §1 and §3 above.
