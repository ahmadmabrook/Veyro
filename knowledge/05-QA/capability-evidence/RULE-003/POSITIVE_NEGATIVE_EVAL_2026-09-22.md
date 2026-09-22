---
doc: RULE-003-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-003 Stage-5 Qualification Evidence — `.claude/rules/infra/observability.md`

**Rule ID:** RULE-003
**Source rule file:** `.claude/rules/infra/observability.md`
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
> # Rule: Infra/SRE — Observability, SLO, and DR-Evidence Baseline
> (`infra/**` binding)

**`CAPABILITY_REGISTRY.md` RULE-003 row, `scope` column (quoted verbatim):**
> Governs `infra/**`/`.github/workflows/**` — read/guidance only

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified by reading `.claude/rules/infra/observability.md` lines 1-6
this session: it opens with `<!-- Target path once applied:
.claude/rules/infra/observability.md -->` then the `# Rule: ...` heading
directly — no `---` YAML block, no `paths:`/`scope:` field, unlike
`.claude/rules/global/knowledge-vault-durability.md`'s real `scope: path`
/ `paths: [...]` frontmatter. RULE-003 loads unconditionally regardless
of path.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (`infra/**` or `.github/workflows/**` change) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. `knowledge/**`, `frontend/**`) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** same structural gap as RULE-001/002 — no `paths:` glob
mechanism exists to exercise a matching-vs-non-matching test against.
Recorded honestly as BLOCKED, not fabricated as a pass.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Control under test:** control 1 — the clearest, most central control,
directly governing what CI/infra tooling must emit as evidence.

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

A validator's output: named violation type, offending file, and line —
structured and machine-parseable.

### Negative fixture (deliberately violates)

```
FAIL
```

A validator that prints a bare pass/fail string with no violation type,
no file, and no line.

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text: *"A CI/infra tool... that cannot produce
the structured evidence required above does not count as satisfying
GOV-01-R05 or `RB-GOV-01`... A session that cannot produce the evidence
reports the gap honestly rather than describing the action as complete."*).

**Actual deterministic evaluation (manual/textual — no CI validator
tooling exists yet in this repo to run; `infra/` does not exist, so this
is a reading of the rule's own prose against the two fixtures, not a tool
run):**

- **Positive fixture → ALLOW.** The JSON output names a specific
  violation type (`RLS_NOT_ENFORCED`), the offending file, and line —
  exactly the "named, inspectable failure-evidence artifact" control 1
  requires, matching the standard `IMPLEMENTATION.md` §3's own gate table
  already holds every row to.
- **Negative fixture → DENY.** `FAIL` alone is precisely the excluded
  case control 1 names verbatim: "a bare pass/fail with no named
  violation type or offending file/line."

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

**Rule file's own control 1 clause:** quoted in full in §3 above.
