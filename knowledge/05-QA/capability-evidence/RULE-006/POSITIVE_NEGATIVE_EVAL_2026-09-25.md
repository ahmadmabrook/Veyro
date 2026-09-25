---
doc: RULE-006-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-006 Stage-5 Qualification Evidence — `.claude/rules/backend/api.md`

**Rule ID:** RULE-006
**Source rule file:** `.claude/rules/backend/api.md`
**Commit binding:** `183acd535e6786f1edc1993a5ef6f13afd13a4ec` (current
governed HEAD, confirmed this session to equal `origin/main`; no edit was
made to any file under `.claude/rules/**` in the course of producing this
evidence). Supersedes the prior binding to `5aa5cc5b6b6d041372b83e043febf179d0460fa5`
in `POSITIVE_NEGATIVE_EVAL_2026-09-22.md` (retained as historical record,
not deleted).
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

**Note on fixture path availability:** this rule's own content-level
fixtures (§3) are bare Pydantic model definitions with no `# path`
comment — unlike RULE-005/008/009, no literal fixture path is recorded to
test the glob against. To exercise the glob honestly, this section uses
an illustrative path representative of where this control actually
applies (a FastAPI route module under the booking domain), labeled as
illustrative rather than drawn from the rule's own recorded fixture.

| Case | Expected result | Actual result (textual glob-matching reasoning, not a harness-observed load event) |
|---|---|---|
| Matching path — illustrative `backend/app/modules/booking/api.py` (representative FastAPI route module location per this project's `backend/app/...` topology, `IMPLEMENTATION.md` line 426; not itself a rule-recorded fixture path) | Rule loads and applies | **PASS.** `backend/**/*.py` matches: literal `backend/`, then `**` matches `app/modules/booking/`, then `api.py` matches `*.py`. |
| Non-matching path — e.g. `frontend/src/api/booking.ts` | Rule does not load / does not apply | **PASS.** First segment `frontend` does not match `backend`. Correctly excluded. |

**No cross-family false match.** This rule's glob (`backend/**/*.py`)
shares no first path segment with the infra-family rules' globs
(`infra/**`, `.github/workflows/**`) — disjoint literal segments, so no
cross-family false match is possible through this mechanism.

**Reasoning method, stated explicitly:** manual textual evaluation of the
glob syntax, not an observed harness event and not a test-tool run (none
exists in this repo).

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md`.** This rule's
control 3 text was not touched by either owner patch commit — re-verified
this session by reading `.claude/rules/backend/api.md` directly. The
fixture pair and verdicts are carried forward.

**Control under test:** control 3 (unchanged).

**Control 3 clause (quoted verbatim):**
> Request schemas reject extra/undeclared fields. Every request model is
> configured to reject unknown fields (e.g. Pydantic's `model_config =
> ConfigDict(extra="forbid")` or the equivalent) rather than silently
> ignoring them — this closes the hidden-field-injection path the
> data-exposure lint's request-schema half checks for.

### Positive fixture (conforms)

```python
from pydantic import BaseModel, ConfigDict

class CreateBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: str
    slot_id: str
```

### Negative fixture (deliberately violates)

```python
from pydantic import BaseModel

class CreateBookingRequest(BaseModel):
    member_id: str
    slot_id: str
```

**Result (carried forward): positive fixture ALLOW; negative fixture
DENY.** `model_config = ConfigDict(extra="forbid")` is the compliant
configuration control 3 names; with no `model_config` set, Pydantic v2's
documented default (`extra="ignore"`) silently drops unknown fields
rather than rejecting them. This determination is independent of the
path-scope frontmatter change and is not affected by it.

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

**Rule file's own control 3 clause and frontmatter:** quoted in full in
§1 and §3 above.
