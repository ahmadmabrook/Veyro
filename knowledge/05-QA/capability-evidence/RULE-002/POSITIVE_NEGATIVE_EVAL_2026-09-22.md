---
doc: RULE-002-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-002 Stage-5 Qualification Evidence — `.claude/rules/infra/secrets.md`

**Rule ID:** RULE-002
**Source rule file:** `.claude/rules/infra/secrets.md`
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
> # Rule: Infra/SRE — Secrets Externalization Baseline (`infra/**` binding)

**`CAPABILITY_REGISTRY.md` RULE-002 row, `scope` column (quoted verbatim):**
> Governs `infra/**`/`.github/workflows/**` — read/guidance only

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified by reading `.claude/rules/infra/secrets.md` lines 1-6 this
session: it opens with `<!-- Target path once applied:
.claude/rules/infra/secrets.md -->` then the `# Rule: ...` heading
directly — no `---` YAML block, no `paths:`/`scope:` field, unlike
`.claude/rules/global/knowledge-vault-durability.md`'s real `scope: path`
/ `paths: [...]` frontmatter. RULE-002 loads unconditionally regardless
of path, same as all 9 files in this set.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (`infra/**` or `.github/workflows/**` change) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. `knowledge/**`, `frontend/**`) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** same structural gap as RULE-001 — there is no `paths:`
glob mechanism to exercise a matching-vs-non-matching test against.
Recorded honestly as BLOCKED, not fabricated as a pass.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Control under test:** control 1 — the clearest, most central control:
"No secret is ever committed to the repository, in any form," with the
rule's own explicit fixture-authoring convention for what a compliant
placeholder looks like.

**Control 1 clause (quoted verbatim):**
> No secret is ever committed to the repository, in any form. This
> covers credentials, API keys, tokens, connection strings with embedded
> credentials, private keys, and signing keys — whether in source,
> config, fixtures, test data, or documentation. ... A fixture or example
> that needs a credential-shaped value uses an explicitly-fake,
> clearly-labeled placeholder (e.g. `EXAMPLE_NOT_A_REAL_KEY`), never a
> plausible-looking real-shaped value.

### Positive fixture (conforms)

```
# infra/environments/qa/.env.example (illustrative — QA tier defaults)
STRIPE_API_KEY=EXAMPLE_NOT_A_REAL_KEY
DATABASE_URL=postgresql://qa_user:EXAMPLE_NOT_A_REAL_PASSWORD@qa-db.internal:5432/veyro_qa
```

### Negative fixture (deliberately violates)

```
# infra/environments/qa/.env.example (illustrative — QA tier defaults)
STRIPE_API_KEY=<an unlabeled value in Stripe's real live-secret-key shape — i.e. the literal prefix Stripe issues, not "EXAMPLE_..." — omitted here to avoid writing a regex-matchable secret-shaped literal into this evidence file itself>
DATABASE_URL=postgresql://qa_user:<an unlabeled plausible-looking real password, not a placeholder>@qa-db.internal:5432/veyro_qa
```

**Note on this fixture's own construction (added after independent Opus
review flagged the original version):** the first draft of this negative
fixture wrote out a literal Stripe-live-key-shaped string and a literal
plausible password directly — which the reviewer correctly identified as
itself a violation of the very control being tested (control 1's "never a
plausible-looking real-shaped value... in fixtures, test data, or
documentation") and a real risk of tripping this repo's own planned
secret-scanning gate. Fixed by describing the violation's *shape* in
prose rather than reproducing a matching literal. The violation under
test is unchanged: an unlabeled, real-shaped credential value present in
a fixture, contrasted with the positive fixture's explicitly-fake
`EXAMPLE_NOT_A_REAL_KEY` label.

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text: *"Any change that would commit a
credential-shaped value... does not merge. If it is unclear whether a
given value is a real secret or a synthetic placeholder, treat it as a
real secret and do not commit it."*).

**Actual deterministic evaluation (manual/textual — no CI secret-scanning
gate is wired into this session's own tooling yet; this is a reading of
the rule's own prose against the two fixtures, not a scanner run):**

- **Positive fixture → ALLOW.** `EXAMPLE_NOT_A_REAL_KEY` and
  `EXAMPLE_NOT_A_REAL_PASSWORD` are exactly the rule's own named example
  pattern for an "explicitly-fake, clearly-labeled placeholder." No
  actual credential-shaped value is present.
- **Negative fixture → DENY.** An unlabeled value in Stripe's real
  live-secret-key shape, and an unlabeled plausible-looking real
  password — neither is labeled as fake, unlike the positive fixture's
  `EXAMPLE_NOT_A_REAL_KEY`/`EXAMPLE_NOT_A_REAL_PASSWORD`. Per the rule's
  own fail-closed instruction ("if it is unclear whether a given value is
  a real secret or a synthetic placeholder, treat it as a real secret"),
  this fixture is denied regardless of whether any specific string is
  actually live.

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
