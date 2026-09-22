---
doc: RULE-001-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-22
---

# RULE-001 Stage-5 Qualification Evidence — `.claude/rules/infra/iac.md`

**Rule ID:** RULE-001
**Source rule file:** `.claude/rules/infra/iac.md`
**Commit binding:** `5aa5cc5b6b6d041372b83e043febf179d0460fa5` (current HEAD; this
evidence is bound to the state of the 9 rule files as of this commit — no
edit was made to any file under `.claude/rules/**` in the course of
producing this evidence)
**Reviewer/model evidence:** veyro-test-author (Sonnet tier per
`DEVELOPMENT_CONSTITUTION.md` model routing — this session's actual model
is `claude-sonnet-5`, confirmed from this session's own environment
context, not guessed)
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
> # Rule: Infra/SRE — Infrastructure-as-Code (IaC) Baseline (`infra/**` binding)

**`CAPABILITY_REGISTRY.md` RULE-001 row, `scope` column (quoted verbatim):**
> Governs `infra/**`/`.github/workflows/**` — read/guidance only, no
> execution/filesystem/network scope of its own (a Rule file, not
> executable code)

**No machine-enforced `paths:` frontmatter exists.** Independently
re-verified this session by reading `.claude/rules/infra/iac.md` lines
1-6 directly: the file opens with an HTML comment
(`<!-- Target path once applied: .claude/rules/infra/iac.md -->`) followed
directly by the `# Rule: ...` markdown heading — no `---` YAML block, no
`paths:`/`scope:` field. Confirmed by contrast against
`.claude/rules/global/knowledge-vault-durability.md`, which this session
also read directly and which DOES carry real frontmatter:
```yaml
---
scope: path
paths:
  - "knowledge/**"
  - "Notion:*"
---
```
RULE-001 has no equivalent mechanism. This is the harness feature that
would let Claude Code load a rule only when the current work touches a
matching path; RULE-001 (like all 9 files in this set) has none, and
therefore loads unconditionally regardless of what path the current
session is working in. (Correction after independent Opus review: this
was previously attributed to "the round-3 qualification review's own
empirical observation," but round 3's own text only reports the missing
frontmatter, not a loading observation — the loading behavior is instead
directly confirmed by this evidence-production session and the
independent Opus review session that followed it, both of which had all
9 files present in context at startup despite doing `knowledge/`-only
work, while the path-scoped `knowledge-vault-durability.md` did not
appear until a `knowledge/` file was actually read.)

## 2. Path-scope qualification case (EIP H.5)

| Case | Expected result | Actual result |
|---|---|---|
| Matching path (a change under `infra/**` or `.github/workflows/**`) | Rule loads and applies | **PASSES trivially — loads (but non-discriminating: loads on every path regardless of match, per the negative-case FAIL below)** |
| Non-matching path (e.g. a change under `knowledge/**` or `frontend/**`, unrelated to infra) | Rule does not load / does not apply | **FAIL (directly observed) — this rule file was present in context at the start of this evidence-production session and the independent Opus review session that followed, both of which were doing `knowledge/`-only work; the path-scoped `knowledge-vault-durability.md` did not appear until a `knowledge/` file was actually read. Owner-gated fix (adding `paths:` frontmatter) required; `.claude/rules/**` may not be edited this session.** |

**Reasoning:** EIP H.5 requires testing "representative matching and
non-matching paths so path scoping is correct." That test presupposes a
path-scoping mechanism to exercise. RULE-001 has none — there is no
`paths:` glob to point a matching or non-matching fixture path at, and
(per the round-3 review's direct observation, consistent with what this
session independently confirmed by reading the file) the rule's content
is presented to every session regardless of what path it is working in.
This is recorded honestly as a genuine BLOCKED result, not fabricated as
a pass. Adding the missing frontmatter is out of scope for this
evidence-only session (`.claude/rules/**` is owner-gated).

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Control under test:** control 4 — chosen as the clearest, most central
control per the rule's own text, which names it directly: *"This is DC-16's
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

A config file under the QA tier — not named `production` or an alias,
and (since it is not a production action) requires no `OWN-<NNN>` entry.

### Negative fixture (deliberately violates)

```
infra/environments/production/database.yaml
---
tier: production
database:
  host: prod-db.internal
```

A directory literally named `production` under `infra/environments/`,
created with no corresponding `OWN-<NNN>` row.

**Expected result:** positive fixture ALLOW; negative fixture DENY (per
the rule's own fail-closed text, corrected after independent Opus review
found the version below misquoted a word and elided text without an
ellipsis: *"An `infra/**` or CI-workflow change that cannot satisfy all
five controls above does not merge. A session that reaches a point where
a production directory, secret scope, or deployment workflow appears to
be required reports `BLOCKED: OWNER_APPROVAL_REQUIRED` naming DC-16,
rather than..."*).

**Actual deterministic evaluation (manual/textual — no CI validator
exists for this control yet; `infra/` does not exist in this repo, so
this is a reading of the rule's own prose against the two fixtures above,
not a tool run):**

- **Positive fixture → ALLOW.** `infra/environments/qa/` is not a
  directory named `production` (or an alias of it) and does not target a
  production deployment. Control 4's prohibition does not fire.
  Independently checked `knowledge/00-System/OWNER_APPROVALS.md` this
  session (read in full, corrected count after independent Opus review
  caught the original miscount): its 4 recorded `OWN-<NNN>` rows (OWN-001,
  OWN-002, OWN-003, OWN-005 — no OWN-004 exists, only a prospective
  unrecorded mention) contain no production-infra entry — none is
  needed for this fixture, consistent with ALLOW.
- **Negative fixture → DENY.** `infra/environments/production/` is
  exactly the prohibited directory name, and no `OWN-<NNN>` entry
  naming a production action exists in `OWNER_APPROVALS.md` (independently
  confirmed by reading that file in full this session — its 4 rows cover
  vault migration, an EIP-contradiction adjudication, orchestration-tier
  approval, and a scenario-review process change; none authorizes a
  production infra directory). Control 4's clause is unambiguous that
  creation "requires a recorded `OWN-<NNN>` entry... made *before*" —
  none exists, so the fixture is denied.

**Result: the rule's own text correctly distinguishes the compliant
fixture (ALLOW) from the violating one (DENY).**

**Secondary observation (control 5, not the primary tested control):**
control 5's own text states its check is two-part — SHA-pinning *and* "a
corresponding `APPROVED` `CAP-<NNN>` row" for the specific action —
"a `false` on either check fails this control." Read against the current
`CAPABILITY_REGISTRY.md` (no CAP-<NNN> row exists for any GitHub Action,
e.g. `actions/checkout`), this means *no* workflow — SHA-pinned or not —
could currently pass control 5's registry-approval half. This is an
honest, current-state fact this session is flagging, not a defect
introduced by this evidence: no `.github/workflows/**` exists in this
repo yet, so the gap has no live consequence today, but the first
workflow author will need an `APPROVED` `CAP-<NNN>` row per Action before
control 5 can be satisfied at all.

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

**Rule file's own control 4 clause:** quoted in full in §3 above.
