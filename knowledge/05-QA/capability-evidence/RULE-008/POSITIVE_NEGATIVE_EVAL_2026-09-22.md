---
doc: RULE-008-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-008 Stage-5 Qualification Evidence — `.claude/rules/backend/concurrency.md`

**Rule ID:** RULE-008
**Source rule file:** `.claude/rules/backend/concurrency.md`
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
> # Rule: Backend Optimistic Concurrency for Mutable Aggregates
> (`backend/**/*.py` binding)

**`CAPABILITY_REGISTRY.md` RULE-008 row, `scope` column (quoted verbatim):**
> Governs `backend/**` mutable-aggregate persistence — read/guidance only

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified by reading `.claude/rules/backend/concurrency.md` lines 1-6
this session: it opens with `<!-- Target path once applied:
.claude/rules/backend/concurrency.md -->` then the `# Rule: ...` heading
directly — no `---` YAML block, no `paths:`/`scope:` field, unlike
`.claude/rules/global/knowledge-vault-durability.md`'s real `scope: path`
/ `paths: [...]` frontmatter. RULE-008 loads unconditionally regardless
of path.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (`backend/**` mutable-aggregate persistence change) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. `knowledge/**`, `infra/**`) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** same structural gap as the other files in this set — no
`paths:` glob mechanism exists to exercise a matching-vs-non-matching
test against. Recorded honestly as BLOCKED, not fabricated as a pass.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Controls under test:** controls 1 and 2 together — the clearest,
most central pairing (version column existence, and the atomic
version-checked update), which the rule's own "Fail-closed rule" section
explicitly names its own deliberate-violation-fixture convention for:
*"a deliberately-broken version-check fixture must be shown to fail
closed, not silently pass."*

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

The `WHERE` clause omits the version check entirely (`AND version =
:expected_version`), and the statement does not increment `version` —
this is the deliberately-broken version-check case the rule's own
fail-closed text names.

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text: *"A mutable-aggregate table with no
version column, or a mutation path that updates such a table without a
version-checked `WHERE` clause and atomic increment, does not merge."*).

**Actual deterministic evaluation (manual/textual — no
persistence-layer concurrency test suite exists yet in this repo;
`backend/` does not exist, so this is a reading of the rule's own prose
against the two fixtures, not a running test suite):**

- **Positive fixture → ALLOW.** The `version integer NOT NULL DEFAULT 1`
  column satisfies control 1. The `UPDATE` statement's `WHERE id = :id
  AND version = :expected_version` clause combined with `SET ... version
  = version + 1` in the same statement satisfies control 2's atomic
  read-check-increment requirement exactly, and a zero-rowcount result
  raises a typed `ConcurrencyConflictError` rather than being silently
  ignored (control 3, not the primary tested control here but visibly
  satisfied by the same fixture).
- **Negative fixture → DENY.** The `UPDATE` statement's `WHERE id = :id`
  clause has no version predicate and the `SET` clause never increments
  `version` — this is precisely "a mutation that writes to a versioned
  table without a version-checked `WHERE` predicate," which control 2
  states "is a rule violation, whether or not a conflict happens to occur
  in practice." This fixture would silently overwrite a concurrent
  writer's change, the exact lost-update failure mode `DOM-002` and this
  rule exist to prevent.

**Result: the rule's own text correctly distinguishes the compliant
fixture (ALLOW) from the violating one (DENY) — matching the rule's own
named "deliberately-broken version-check fixture must be shown to fail
closed" convention.**

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
