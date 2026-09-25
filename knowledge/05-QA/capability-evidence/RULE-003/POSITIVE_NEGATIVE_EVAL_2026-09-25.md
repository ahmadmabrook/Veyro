---
doc: RULE-003-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-003 Stage-5 Qualification Evidence — `.claude/rules/infra/observability.md`

**Rule ID:** RULE-003
**Source rule file:** `.claude/rules/infra/observability.md`
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
forward unchanged from 2026-09-22 (control text unchanged by either owner
patch commit — verified this session by reading the current file).
Path-scope qualification: **PASS** (both matching and non-matching
cases) — a real `paths:` frontmatter mechanism now exists, added in
commit `5ad7d3c` and unchanged by `183acd5`.

## 1. Applicability binding as currently documented

**Rule file's own frontmatter (quoted verbatim, re-read this session):**
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
---
```
Added by `5ad7d3cbb67f0433031850b0e3180f7a4872cccc`, unchanged by
`183acd535e6786f1edc1993a5ef6f13afd13a4ec` (that commit's diff, checked
this session via `git show`, touches only `release.md` and `secrets.md`).

**What this evidence does NOT claim:** whether Claude Code's rule-loader
actually reads and enforces this `paths:` frontmatter at runtime remains
itself unverified by this project. §2 below is textual glob-matching
reasoning, not an observed harness load/skip event.

## 2. Path-scope qualification case (EIP H.5)

**Note on fixture path availability:** unlike RULE-001/005/008/009, this
rule's own content-level fixtures (§3) are validator output samples (a
JSON gate report and a bare `FAIL` string) and a `production`-directory
example is not part of them — neither carries a source file path of its
own. To exercise the glob honestly, this section uses an illustrative
path representative of where this rule's obligations would actually
apply (a CI/infra validator script), labeled as illustrative rather than
drawn from the rule's own recorded fixture, since none exists.

| Case | Expected result | Actual result (textual glob-matching reasoning, not a harness-observed load event) |
|---|---|---|
| Matching path — illustrative `infra/ci/rls_lint_validator.py` (representative of the CI/infra tooling control 1 governs; not itself a rule-recorded fixture path) | Rule loads and applies | **PASS.** `infra/**` matches any path beginning with the literal segment `infra/`; the illustrative path satisfies this trivially. |
| Non-matching path — e.g. `frontend/src/dashboards/StatusPanel.tsx` | Rule does not load / does not apply | **PASS.** First segment `frontend` matches neither `infra` nor `.github`. Correctly excluded. |

**No cross-family false match.** This rule's globs (`infra/**`,
`.github/workflows/**`) share no first path segment with the
backend-family rules' globs (`backend/**/*.py`, `backend/**`) — disjoint
literal segments, so no cross-family false match is possible through
this mechanism.

**Reasoning method, stated explicitly:** manual textual evaluation of the
glob syntax, not an observed harness event and not a test-tool run (none
exists in this repo).

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md`.** This rule's
control text was not touched by either owner patch commit — re-verified
this session by reading `.claude/rules/infra/observability.md` control 1
directly and confirming it matches the quoted text below. The fixture
pair and verdicts are carried forward.

**Control under test:** control 1 (unchanged).

**Control 1 clause (quoted verbatim):**
> CI/infra tooling itself emits structured, machine-parseable output —
> not prose-only pass/fail claims. ... A gate that only prints a bare
> pass/fail with no named violation type or offending file/line does not
> meet this bar.

### Positive fixture (conforms)

```json
{
  "gate": "rls_lint",
  "status": "FAIL",
  "violation": "RLS_NOT_ENFORCED",
  "file": "app/modules/booking/models.py",
  "line": 42,
  "table": "booking.reservations"
}
```

### Negative fixture (deliberately violates)

```
FAIL
```

**Result (carried forward): positive fixture ALLOW; negative fixture
DENY.** The JSON output names a violation type, file, and line — exactly
what control 1 requires. The bare `FAIL` string is precisely the excluded
case control 1 names verbatim. This determination is independent of the
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

**Rule file's own control 1 clause and frontmatter:** quoted in full in
§1 and §3 above.
