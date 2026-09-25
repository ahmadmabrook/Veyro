---
doc: RULE-005-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-005 Stage-5 Qualification Evidence — `.claude/rules/backend/architecture.md`

**Rule ID:** RULE-005
**Source rule file:** `.claude/rules/backend/architecture.md`
**Commit binding:** `183acd535e6786f1edc1993a5ef6f13afd13a4ec`. Supersedes
the prior binding to `5aa5cc5b6b6d041372b83e043febf179d0460fa5` in
`POSITIVE_NEGATIVE_EVAL_2026-09-22.md` (retained as historical record, not
deleted). **Correction (Round 5 review, 2026-09-25, P2-1):** the true
current governed HEAD is `8e90680e8e8bcbd86e5136b6181371ac8161eee7` (this
repo's own subsequent commit, which only added the Stage-5 evidence/
registry files and touched nothing under `.claude/rules/**`), not `183acd5`
as this file's binding line above originally claimed — a self-reference
staleness defect. Content-identical: `.claude/rules/backend/architecture.md`
is byte-for-byte unchanged across `183acd5`/`14d1337`/`8e90680` (re-verified
via `shasum -a 256`, `8d05b2844480ea9ccab65b8a557368727c132c6367b259507f587af55d1507ad`,
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
positive/negative content fixtures (§3) both carry the comment
`# app/modules/booking/service.py`. That comment is written relative to
the backend application root, per `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md`
line 426, which names `backend/app/main.py` as the canonical full-repo-path
example of this project's backend surface (i.e. `app/` sits directly
under `backend/`). Read against that topology, the full repository path
of this rule's own fixture is `backend/app/modules/booking/service.py`.

| Case | Expected result | Actual result (textual glob-matching reasoning, not a harness-observed load event) |
|---|---|---|
| Matching path — `backend/app/modules/booking/service.py` (this rule's own recorded fixture path, read against the project's `backend/app/...` topology) | Rule loads and applies | **PASS.** `backend/**/*.py` requires the literal segment `backend/`, then any depth of subpath (`**`), ending in a filename matching `*.py`. `backend/` + `app/modules/booking/` (matched by `**`) + `service.py` (matches `*.py`). Match. |
| Non-matching path — e.g. `infra/environments/qa/database.yaml` or `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` | Rule does not load / does not apply | **PASS.** Neither path's first segment is `backend`, so neither matches `backend/**/*.py`. Correctly excluded. |

**No cross-family false match.** This rule's glob (`backend/**/*.py`)
shares no first path segment with the infra-family rules' globs
(`infra/**`, `.github/workflows/**`) — `backend` versus `infra`/`.github`
are disjoint literal segments, so a change scoped to one family can never
spuriously activate the other family's rule through this mechanism.

**Reasoning method, stated explicitly:** manual textual evaluation of the
glob syntax against the recorded fixture path, not an observed harness
event and not a test-tool run (none exists in this repo; `backend/` does
not exist yet as a real directory).

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md`.** This rule's
controls 1 and 2 text was not touched by either owner patch commit —
re-verified this session by reading `.claude/rules/backend/architecture.md`
directly. The fixture pair and verdicts are carried forward.

**Controls under test:** controls 1 and 2 together (unchanged).

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

**Result (carried forward): positive fixture ALLOW; negative fixture
DENY.** The positive fixture imports only an exported application-service
function; the negative fixture imports another domain's private ORM model
and queries it directly — exactly `CROSS_DOMAIN_SQL_IMPORT`. This
determination is independent of the path-scope frontmatter change and is
not affected by it.

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
