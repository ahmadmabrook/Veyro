---
doc: RULE-006-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-006 Stage-5 Qualification Evidence — `.claude/rules/backend/api.md`

**Rule ID:** RULE-006
**Source rule file:** `.claude/rules/backend/api.md`
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
> # Rule: Backend API Request/Response and Permission Boundaries
> (`backend/**/*.py` binding)

**`CAPABILITY_REGISTRY.md` RULE-006 row, `scope` column (quoted verbatim):**
> Governs `backend/**/*.py` — read/guidance only

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified by reading `.claude/rules/backend/api.md` lines 1-6 this
session: it opens with `<!-- Target path once applied:
.claude/rules/backend/api.md -->` then the `# Rule: ...` heading
directly — no `---` YAML block, no `paths:`/`scope:` field, unlike
`.claude/rules/global/knowledge-vault-durability.md`'s real `scope: path`
/ `paths: [...]` frontmatter. RULE-006 loads unconditionally regardless
of path.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (`backend/**/*.py` change) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. `knowledge/**`, `infra/**`) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** same structural gap as the other files in this set — no
`paths:` glob mechanism exists to exercise a matching-vs-non-matching
test against. Recorded honestly as BLOCKED, not fabricated as a pass.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Control under test:** control 3 — a clean, single-clause, mechanically
distinct control from controls 2 (response-side) and 4/5
(permission-triple), making it the clearest control to isolate for a
single fixture pair.

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

No `model_config` is set, so Pydantic v2's default `extra="ignore"`
behavior applies — an unknown field (e.g. an injected `is_admin: true`)
in the request body is silently dropped rather than rejected.

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text: *"A route handler with... a request
schema that accepts extra fields... does not merge. ... the input/output
data-exposure lint... [is] CI-blocking."*).

**Actual deterministic evaluation (manual/textual — no
`tools/` data-exposure-lint script or `contracts/openapi/` tree exists
yet in this repo; `backend/` does not exist, so this is a reading of the
rule's own prose against Pydantic v2's own documented default behavior
and the two fixtures, not a lint run):**

- **Positive fixture → ALLOW.** `model_config = ConfigDict(extra="forbid")`
  is the exact configuration control 3 names as compliant — an unknown
  field in a request raises a validation error rather than being
  silently accepted.
- **Negative fixture → DENY.** With no `model_config` set, Pydantic v2's
  documented default is `extra="ignore"` — unknown fields are silently
  dropped, not rejected. This is precisely the excluded case control 3
  names: "rather than silently ignoring them."

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

**Rule file's own control 3 clause:** quoted in full in §3 above.
