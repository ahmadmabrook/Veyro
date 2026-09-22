---
doc: RULE-005-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-005 Stage-5 Qualification Evidence — `.claude/rules/backend/architecture.md`

**Rule ID:** RULE-005
**Source rule file:** `.claude/rules/backend/architecture.md`
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
> # Rule: Backend Modular-Monolith Architecture Boundaries
> (`backend/**/*.py` binding)

**`CAPABILITY_REGISTRY.md` RULE-005 row, `scope` column (quoted verbatim):**
> Governs `backend/**/*.py` — read/guidance only

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified by reading `.claude/rules/backend/architecture.md` lines 1-6
this session: it opens with `<!-- Target path once applied:
.claude/rules/backend/architecture.md -->` then the `# Rule: ...` heading
directly — no `---` YAML block, no `paths:`/`scope:` field, unlike
`.claude/rules/global/knowledge-vault-durability.md`'s real `scope: path`
/ `paths: [...]` frontmatter. RULE-005 loads unconditionally regardless
of path.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (`backend/**/*.py` change) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. `knowledge/**`, `infra/**`) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** same structural gap as the other 8 files — no `paths:`
glob mechanism exists to exercise a matching-vs-non-matching test
against. Recorded honestly as BLOCKED, not fabricated as a pass.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Controls under test:** controls 1 and 2 together — the clearest,
most central pairing: domain table/model privacy (control 1) and
contract-only cross-domain collaboration (control 2). Testing them
together is necessary because a single fixture pair that violates one
also violates the other (a direct cross-domain ORM import is both a
private-table access and a non-contract collaboration).

**Control 1 clause (quoted verbatim):**
> Each business domain owns exactly one sub-package under
> `app/modules/<domain>/`... A domain's own database tables and ORM
> models are private to that sub-package — no other module may import
> them directly. Violating this is the exact condition the module
> dependency/SQL lint gate (TSD §24.1) denies as
> `CROSS_DOMAIN_SQL_IMPORT`, citing the importing/imported module pair.

**Control 2 clause (quoted verbatim):**
> A module may interact with another domain only through that domain's
> own published application-service interface... or through domain
> events it publishes/consumes — never raw SQL or a direct ORM query
> against another module's tables.

### Positive fixture (conforms)

```python
# app/modules/booking/service.py
from app.modules.membership.service import get_member_status  # exported application-service function

def create_reservation(member_id: str, slot_id: str) -> Reservation:
    status = get_member_status(member_id)  # contract call, not raw ORM/SQL
    if not status.is_active:
        raise MemberNotActiveError(member_id)
    return _persist_reservation(member_id, slot_id)
```

### Negative fixture (deliberately violates)

```python
# app/modules/booking/service.py
from app.modules.membership.models import Member  # another domain's private ORM model, imported directly

def create_reservation(member_id: str, slot_id: str, session) -> Reservation:
    member = session.query(Member).filter(Member.id == member_id).first()  # direct cross-domain ORM query
    if member.status != "active":
        raise MemberNotActiveError(member_id)
    return _persist_reservation(member_id, slot_id)
```

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text: *"A pull request introducing a
cross-domain table/ORM import outside the TSD §6.3 exception... does not
merge. The module dependency/SQL lint gate (TSD §24.1) is CI-blocking,
not advisory."*).

**Actual deterministic evaluation (manual/textual — no
`app/modules/` tree or SQL-lint tooling exists yet in this repo;
`backend/` does not exist, so this is a reading of the rule's own prose
against the two fixtures, not a lint run):**

- **Positive fixture → ALLOW.** `booking/service.py` imports only
  `membership.service.get_member_status`, an exported application-service
  function — exactly "that domain's own published application-service
  interface" control 2 requires. No `membership` ORM model or table is
  imported or queried.
- **Negative fixture → DENY.** `from app.modules.membership.models import
  Member` is a direct import of another domain's private ORM model
  (control 1's exact prohibition), and `session.query(Member)...` is a
  direct ORM query against another module's table (control 2's exact
  prohibition: "never raw SQL or a direct ORM query against another
  module's tables"). This is precisely the `CROSS_DOMAIN_SQL_IMPORT`
  condition control 1 names, citing the `booking`/`membership` module
  pair.

**Result: the rule's own text correctly distinguishes the compliant
fixture (ALLOW) from the violating one (DENY).**

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
