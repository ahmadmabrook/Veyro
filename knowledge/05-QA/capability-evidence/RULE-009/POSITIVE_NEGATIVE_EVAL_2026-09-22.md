---
doc: RULE-009-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-009 Stage-5 Qualification Evidence — `.claude/rules/backend/performance.md`

**Rule ID:** RULE-009
**Source rule file:** `.claude/rules/backend/performance.md`
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
> # Rule: Backend Load Scope and Observability Baseline
> (`backend/**/*.py` binding)

**`CAPABILITY_REGISTRY.md` RULE-009 row, `scope` column (quoted verbatim):**
> Governs `backend/**/*.py` — read/guidance only

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified by reading `.claude/rules/backend/performance.md` lines 1-6
this session: it opens with `<!-- Target path once applied:
.claude/rules/backend/performance.md -->` then the `# Rule: ...` heading
directly — no `---` YAML block, no `paths:`/`scope:` field, unlike
`.claude/rules/global/knowledge-vault-durability.md`'s real `scope: path`
/ `paths: [...]` frontmatter. RULE-009 loads unconditionally regardless
of path.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (`backend/**/*.py` change) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. `knowledge/**`, `infra/**`) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** same structural gap as the other 8 files in this set — no
`paths:` glob mechanism exists to exercise a matching-vs-non-matching
test against. Recorded honestly as BLOCKED, not fabricated as a pass.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Control under test:** control 5 — the clearest, most central and most
security-sensitive control in this file (this rule's own "Scope note"
explicitly disclaims an application-scale load budget, so the
logging/PII control is the file's most concretely, mechanically
checkable claim — named as a lint the rule states denies "a named
file/line plus secret- or PII-pattern-class violation").

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

**Clarifying note (added after independent Opus review flagged this as
worth stating explicitly):** `member_id` here is an opaque internal UUID
identifier, not raw member data itself (control 5 names "raw member
data" as one example of a PII-shaped value to redact — a bare surrogate
ID used only to correlate log lines to an account is not the same thing
as logging a name, address, or other directly-identifying attribute).
This positive fixture's ALLOW verdict rests on that distinction, stated
here rather than left implicit.

### Negative fixture (deliberately violates)

```python
# app/modules/billing/service.py
logger.info(f"payment processed for card {card_number}, member {member_id}")
```

The full raw payment card number is interpolated directly into the log
message with no redaction, hashing, or truncation.

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text: *"a log statement matching a
secret/PII pattern, does not merge. ... the sensitive-logging lint...
[is] CI-blocking."*).

**Actual deterministic evaluation (manual/textual — no sensitive-logging
lint tool exists yet in this repo; `backend/` does not exist, so this is
a reading of the rule's own prose against the two fixtures, not a lint
run):**

- **Positive fixture → ALLOW.** `card_number[-4:]` is a truncated value
  (last 4 digits only) — exactly the rule's own named remediation
  ("redacted, hashed, or truncated first"). No full card number,
  password, or API key appears anywhere in the log call.
- **Negative fixture → DENY.** `card_number` is interpolated into the log
  message in full, with no truncation, redaction, or hashing applied —
  this is precisely "a full payment card number" appearing in a log
  statement, the exact excluded case control 5 names.

**Result: the rule's own text correctly distinguishes the compliant
fixture (ALLOW) from the violating one (DENY).**

**Secondary observation (control 4, not the primary tested control):**
the negative fixture also independently fails control 4 ("Log output is
structured... not ad hoc string interpolation") since it uses an f-string
rather than a structured, field-keyed call — consistent with the two
controls' failure modes compounding in a realistic violation rather than
being mutually exclusive.

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

**Rule file's own control 5 clause:** quoted in full in §3 above.
