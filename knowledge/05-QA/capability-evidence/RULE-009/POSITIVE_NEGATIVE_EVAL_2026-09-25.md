---
doc: RULE-009-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-009 Stage-5 Qualification Evidence — `.claude/rules/backend/performance.md`

**Rule ID:** RULE-009
**Source rule file:** `.claude/rules/backend/performance.md`
**Commit binding:** `183acd535e6786f1edc1993a5ef6f13afd13a4ec`. Supersedes
the prior binding to `5aa5cc5b6b6d041372b83e043febf179d0460fa5` in
`POSITIVE_NEGATIVE_EVAL_2026-09-22.md` (retained as historical record, not
deleted). **Correction (Round 5 review, 2026-09-25, P2-1):** the true
current governed HEAD is `8e90680e8e8bcbd86e5136b6181371ac8161eee7` (this
repo's own subsequent commit, which only added the Stage-5 evidence/
registry files and touched nothing under `.claude/rules/**`), not `183acd5`
as this file's binding line above originally claimed — a self-reference
staleness defect. Content-identical: `.claude/rules/backend/performance.md`
is byte-for-byte unchanged across `183acd5`/`14d1337`/`8e90680` (re-verified
via `shasum -a 256`, `805e669248cc252eec0b5995b9e1702b3e6e6ffd033d70f70407d50e38ad4e5c`,
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
`# app/modules/billing/service.py`. Per `IMPLEMENTATION.md` line 426
(`backend/app/main.py` named as the canonical full-repo-path example),
that comment is relative to the backend application root, so the full
repository path is `backend/app/modules/billing/service.py`.

| Case | Expected result | Actual result (textual glob-matching reasoning, not a harness-observed load event) |
|---|---|---|
| Matching path — `backend/app/modules/billing/service.py` (this rule's own recorded fixture path, read against the project's `backend/app/...` topology) | Rule loads and applies | **PASS.** `backend/**/*.py` matches: literal `backend/`, then `**` matches `app/modules/billing/`, then `service.py` matches `*.py`. |
| Non-matching path — e.g. `infra/environments/qa/database.yaml` | Rule does not load / does not apply | **PASS.** First segment `infra` does not match `backend`. Correctly excluded. |

**No cross-family false match.** This rule's glob (`backend/**/*.py`)
shares no first path segment with the infra-family rules' globs
(`infra/**`, `.github/workflows/**`) — disjoint literal segments, so no
cross-family false match is possible through this mechanism.

**Reasoning method, stated explicitly:** manual textual evaluation of the
glob syntax against the recorded fixture path, not an observed harness
event and not a test-tool run (none exists in this repo).

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md`.** This rule's
control 5 text was not touched by either owner patch commit — re-verified
this session by reading `.claude/rules/backend/performance.md` directly.
The fixture pair and verdicts are carried forward.

**Control under test:** control 5 (unchanged).

**Control 5 clause (quoted verbatim):**
> No secret or PII-shaped value appears in a log statement. No backend
> log statement includes a secret, credential, access token, or
> PII-shaped value (raw member data, a national ID, a full payment card
> number, a password, an API key). Where a value must be logged for
> diagnostic purposes, it is redacted, hashed, or truncated first. This
> is the exact condition the sensitive-logging lint denies as a named
> file/line plus secret- or PII-pattern-class violation.

### Positive fixture (conforms)

```python
# app/modules/billing/service.py
logger.info(
    "payment_processed",
    extra={"member_id": member_id, "card_last4": card_number[-4:], "amount_cents": amount_cents},
)
```

`member_id` here is an opaque internal UUID identifier used only to
correlate log lines to an account, not raw directly-identifying member
data (per the 2026-09-22 evidence's own clarifying note, carried forward
unchanged).

### Negative fixture (deliberately violates)

```python
# app/modules/billing/service.py
logger.info(f"payment processed for card {card_number}, member {member_id}")
```

**Result (carried forward): positive fixture ALLOW; negative fixture
DENY.** `card_number[-4:]` is a truncated value — the rule's own named
remediation; the negative fixture interpolates the full raw card number
into the log message with no redaction — exactly "a full payment card
number" appearing in a log statement, the excluded case control 5 names.
This determination is independent of the path-scope frontmatter change
and is not affected by it.

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

**Rule file's own control 5 clause and frontmatter:** quoted in full in
§1 and §3 above.
