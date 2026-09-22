---
doc: RULE-004-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-004 Stage-5 Qualification Evidence — `.claude/rules/infra/release.md`

**Rule ID:** RULE-004
**Source rule file:** `.claude/rules/infra/release.md`
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
> # Rule: Infra/SRE — Release, Rollback/Canary, and Cost Baseline
> (`infra/**` binding)

**`CAPABILITY_REGISTRY.md` RULE-004 row, `scope` column (quoted verbatim):**
> Governs `infra/**`/`.github/workflows/**` — read/guidance only

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified by reading `.claude/rules/infra/release.md` lines 1-6 this
session: it opens with `<!-- Target path once applied:
.claude/rules/infra/release.md -->` then the `# Rule: ...` heading
directly — no `---` YAML block, no `paths:`/`scope:` field, unlike
`.claude/rules/global/knowledge-vault-durability.md`'s real `scope: path`
/ `paths: [...]` frontmatter. RULE-004 loads unconditionally regardless
of path.

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (`infra/**` or `.github/workflows/**` change) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. `knowledge/**`, `frontend/**`) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** same structural gap as RULE-001/002/003 — no `paths:`
glob mechanism exists to exercise a matching-vs-non-matching test
against. Recorded honestly as BLOCKED, not fabricated as a pass.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Control under test:** control 1 — the clearest, most central and most
security-sensitive control (the rule's own "Why this rule exists" section
names this control's failure mode directly as a denial-of-service
vector).

**Control 1 clause (quoted verbatim):**
> Automated rollback is tied to genuine SLO/guardrail signals — never a
> manually or externally callable endpoint. ... The rollback mechanism's
> only trigger path is the pipeline's own SLO/guardrail evaluation
> crossing a pre-declared threshold — never an unauthenticated or
> convenience HTTP endpoint, CLI flag, webhook, or manual override
> callable by a human operator or external system. ... no carve-out of
> any kind, including an audited one, since no cited source authorizes
> one.

### Positive fixture (conforms)

```python
# infra/pipeline/canary_guardrail.py — invoked only by the deployment
# pipeline's own monitoring loop, never exposed as an HTTP route.
def evaluate_guardrail_and_maybe_rollback(metrics: GuardrailMetrics) -> None:
    if metrics.error_rate_pct > GUARDRAIL_ERROR_RATE_THRESHOLD:
        trigger_automated_rollback(reason="error_rate_guardrail_breached")
```

### Negative fixture (deliberately violates)

```python
# app/main.py — an externally callable HTTP route
@app.post("/admin/rollback")
async def manual_rollback(current_user: AdminUser = Depends(require_admin)):
    trigger_automated_rollback(reason="manual_admin_trigger")
    return {"status": "rollback_triggered"}
```

An admin-authenticated but still externally/manually callable endpoint
that can trigger the rollback mechanism on demand.

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text: *"A canary/rollback mechanism with a
manually-callable trigger... does not ship."*).

**Actual deterministic evaluation (manual/textual — no CI/pipeline
tooling exists yet in this repo; `infra/` does not exist, so this is a
reading of the rule's own prose against the two fixtures, not a running
pipeline):**

- **Positive fixture → ALLOW.** The trigger path is a plain function
  called only from the pipeline's own guardrail-evaluation loop, gated on
  a pre-declared threshold (`GUARDRAIL_ERROR_RATE_THRESHOLD`) — no HTTP
  route, CLI flag, or webhook exists for it.
- **Negative fixture → DENY.** `POST /admin/rollback` is exactly the
  excluded case control 1 names: "an unauthenticated or convenience HTTP
  endpoint... or manual override callable by a human operator." Control
  1's text is explicit that even an *audited* manual override carve-out
  is disallowed ("no carve-out of any kind, including an audited one"),
  so the fact this fixture requires admin authentication (`require_admin`)
  does not rescue it — the clause draws no exception for authenticated
  callers, only for the pipeline's own internal evaluation.

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
