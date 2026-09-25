---
doc: RULE-001-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-001 Stage-5 Qualification Evidence — `.claude/rules/infra/iac.md`

**Rule ID:** RULE-001
**Source rule file:** `.claude/rules/infra/iac.md`
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
forward unchanged from 2026-09-22 (this file's control text did not
change across the two owner patch commits `5ad7d3c`/`183acd5` — verified
this session by reading the current file directly). Path-scope
qualification: **PASS** (both matching and non-matching cases) — a real
`paths:` frontmatter mechanism now exists, added in commit `5ad7d3c` and
unchanged by `183acd5`. This is still not `QUALIFIED` or `APPROVED` — this
file records evidence only; those are separate independent-review
verdicts this session is not making.

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
This frontmatter was added by commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc`
("fix: add path scope metadata to MOD-001 rule family") and is unchanged
by the later commit `183acd535e6786f1edc1993a5ef6f13afd13a4ec`, which only
touched `release.md` and `secrets.md` (confirmed this session via `git
show 183acd535e6786f1edc1993a5ef6f13afd13a4ec`, whose diff lists only
those two files).

**What changed since 2026-09-22:** the 2026-09-22 evidence recorded that
no `---` frontmatter block existed at all. That is no longer true. A real
`paths:` glob mechanism is now present in the file.

**What this evidence does NOT claim:** whether Claude Code's rule-loader
actually reads and enforces this `paths:` frontmatter at runtime is
itself still unverified by this project (see `CURRENT_STATE.md`'s own
standing disclosure). This section, like §2 below, is a textual reading
of the glob syntax against candidate paths — not an observed harness
load/no-load event.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result (textual glob-matching reasoning, not a harness-observed load event) |
|---|---|---|
| Matching path — this rule's own recorded positive content-fixture path, `infra/environments/qa/database.yaml` (§3 below) | Rule loads and applies | **PASS.** The glob `infra/**` matches any path whose first segment is literally `infra` followed by any depth of subpath. `infra/environments/qa/database.yaml` begins with the literal segment `infra/`, so `**` matches the remainder (`environments/qa/database.yaml`). Match. |
| Non-matching path — e.g. `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` or `frontend/src/App.tsx` | Rule does not load / does not apply | **PASS.** Neither candidate path's first segment is `infra` or `.github`, so it matches neither `infra/**` nor `.github/workflows/**`. Correctly excluded. |

**No cross-family false match.** This rule's two globs (`infra/**`,
`.github/workflows/**`) and the five backend-family rules' globs
(`backend/**/*.py`, `backend/**`) share no common first path segment —
`infra`/`.github` versus `backend` are disjoint literal segments, so a
change scoped to one family can never spuriously activate the other
family's rule through this glob mechanism.

**Reasoning method, stated explicitly:** this is a manual textual
evaluation of the glob syntax against two candidate paths, reasoned
through by hand — not an observed Claude Code harness load/skip event,
and not a run of any path-matching test tool (none exists in this repo).
The prior 2026-09-22 evidence's FAIL verdict is superseded because the
underlying fact it was reporting (no `paths:` field existed) is no longer
true; this is not a re-interpretation of the same facts, it is a
different, later state of the file.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md`.** This rule's
control text was not touched by either owner patch commit (`5ad7d3c` only
added the frontmatter block at the top of the file; `183acd5` did not
touch this file at all) — re-verified this session by reading
`.claude/rules/infra/iac.md` control 4's text directly and confirming it
is byte-identical to the quoted text below. The positive/negative
fixture pair and their ALLOW/DENY verdicts from 2026-09-22 therefore
still hold and are carried forward rather than re-derived.

**Control under test:** control 4 (unchanged) — *"This is DC-16's
owner-reserved restriction... applied to this surface directly, and it is
this rule's single most load-bearing constraint."*

**Control 4 clause (quoted verbatim):**
> No `infra/environments/production/` directory, no production secret
> scope, and no production deployment workflow exist without an explicit
> `OWNER_APPROVALS.md` entry. ... Concretely: no directory named
> `production` (or an equivalent alias) under `infra/environments/`; ...
> Creating any of the above requires a recorded `OWN-<NNN>` entry in
> `knowledge/00-System/OWNER_APPROVALS.md` naming the specific production
> action, made *before* the directory/config/workflow is created — not
> backfilled after the fact.

### Positive fixture (conforms)

```
infra/environments/qa/database.yaml
---
tier: qa
database:
  host: qa-db.internal
  reset_policy: every-ci-run
```

### Negative fixture (deliberately violates)

```
infra/environments/production/database.yaml
---
tier: production
database:
  host: prod-db.internal
```

**Result (carried forward): positive fixture ALLOW; negative fixture
DENY.** `infra/environments/qa/` is not a `production`-named directory
and requires no `OWN-<NNN>` entry; `infra/environments/production/` is
exactly the prohibited directory name with no corresponding
`OWN-<NNN>` row in `OWNER_APPROVALS.md`. The rule's own text correctly
distinguishes the two fixtures — this determination is independent of
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

**Rule file's own control 4 clause and frontmatter:** quoted in full in
§1 and §3 above.
