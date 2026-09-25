---
doc: RULE-004-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-004 Stage-5 Qualification Evidence — `.claude/rules/infra/release.md`

**Rule ID:** RULE-004
**Source rule file:** `.claude/rules/infra/release.md`
**Commit binding:** `14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a` (current
governed HEAD, confirmed via fresh `git fetch`/`git rev-parse` to equal
`origin/main`; no edit was made to any file under `.claude/rules/**` in
the course of producing this evidence). **Corrected after an independent
review found this file was first written bound to `183acd535e6786f1edc1993a5ef6f13afd13a4ec`,
which the owner had already superseded by the time this file was
finished — the owner pushed a further commit,
`14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a`, mid-session, and the original
version of this file did not notice.** SHA-256 of `release.md` at this
binding, independently recomputed: `74dc432ec2482a1ae09dfa2cbedc3e50e881c1068a2b675caa06b64db67683a2`.
Supersedes the prior binding to `5aa5cc5b6b6d041372b83e043febf179d0460fa5`
in `POSITIVE_NEGATIVE_EVAL_2026-09-22.md` (retained as historical record,
not deleted).
**Reviewer/model evidence:** veyro-test-author (Sonnet tier per
`DEVELOPMENT_CONSTITUTION.md` model routing — this session's actual model
is `claude-sonnet-5`)
**Timestamp:** 2026-09-25
**Status of this evidence:** content-level qualification: sound, carried
forward unchanged (rollback-trigger control text and its ALLOW/DENY
verdicts are unmodified — see §3). Path-scope qualification:
**PASS-with-new-fixture-case** — this rule's frontmatter gained a third
glob (`backend/**/*.py`) in commit `183acd5`, on top of the `paths:`
mechanism first added in `5ad7d3c`, and §2 below demonstrates a genuinely
new coverage fact: this rule's own negative content fixture is now
actually reachable under the corrected scope, which it was not before. A
further commit, `14d1337`, then corrected the file's own H1 heading to
match — see §1.

## 1. Applicability binding as currently documented

**Rule file's own frontmatter (quoted verbatim, re-read this session):**
```yaml
---
scope: path
paths:
  - "infra/**"
  - ".github/workflows/**"
  - "backend/**/*.py"
---
```

**History of this frontmatter, confirmed this session via `git show` —
three commits, not two:** commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc`
first added a `paths:` block to this file containing only `infra/**` and
`.github/workflows/**`. Commit `183acd535e6786f1edc1993a5ef6f13afd13a4ec`
then added the third entry, `backend/**/*.py` — confirmed directly from
that commit's diff:
```diff
 paths:
   - "infra/**"
   - ".github/workflows/**"
+  - "backend/**/*.py"
 ---
-
 <!-- Target path once applied: .claude/rules/infra/release.md -->
```
**Correction (an earlier version of this evidence file said "no other
line in this file changed in that commit" — false even for `183acd5`
itself):** that commit also deleted the blank line previously separating
the closing `---` from the following HTML comment — a whitespace-only
change, not a content change, but the diff above includes it rather than
omitting it as the prior version of this file did.

At this point the file was still internally inconsistent for one more
commit: its own H1 heading still read "(`infra/**` binding)" — the exact
pre-patch title — even though the frontmatter above it now named three
globs. Commit `14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a` fixed this,
changing only the H1:
```diff
-# Rule: Infra/SRE — Release, Rollback/Canary, and Cost Baseline (`infra/**` binding)
+# Rule: Infra/SRE — Release, Rollback/Canary, and Cost Baseline (`infra/**`, CI, and backend Python binding)
```
No frontmatter or control text changed in this third commit — confirmed
directly via `git show 14d1337`. The frontmatter/H1 pair is now
internally consistent for the first time across all three commits.

**Why the third glob matters, stated plainly:** this rule's own negative
(violating) content fixture (§3) is a Python file under `app/main.py` —
i.e., per this project's `backend/app/...` topology
(`IMPLEMENTATION.md` line 426), `backend/app/main.py`. Before this
commit, this rule's scope (`infra/**`, `.github/workflows/**`) did not
cover that path at all — a real gap the prior qualification round found:
the rule's own qualified violation fixture was, under the pre-patch
frontmatter, outside the rule's own applicability. The third glob closes
that gap.

**What this evidence does NOT claim:** whether Claude Code's rule-loader
actually reads and enforces this `paths:` frontmatter at runtime remains
itself unverified by this project. §2 below is textual glob-matching
reasoning, not an observed harness load/skip event.

## 2. Path-scope qualification case (EIP H.5) — three cases

This rule now carries three globs, so this section demonstrates all
three path relationships explicitly, rather than a single
matching/non-matching pair.

### Case 1 — matching infra path (this rule's own positive content fixture)

**Path:** `infra/pipeline/canary_guardrail.py` (the file-path comment on
this rule's own recorded positive fixture in §3).

**Reasoning:** `infra/**` matches any path beginning with the literal
segment `infra/`. `infra/pipeline/canary_guardrail.py` begins with
`infra/`, so `**` matches the remainder (`pipeline/canary_guardrail.py`).

**Result: PASS (matches `infra/**`).**

### Case 2 — matching backend rollback-trigger path (this rule's own negative content fixture) — the case this patch was made for

**Path:** this rule's own recorded negative fixture carries the comment
`# app/main.py — an externally callable HTTP route`. `IMPLEMENTATION.md`
line 426 gives `backend/app/main.py` as *an* example (not the only
named one) of a source file under the backend surface's path scope —
independently confirmed this session by reading that line directly. This
is corroborated, not contradicted, by `architecture.md` and `api.md`,
which independently place `app/main.py`-shaped application files under
`backend/**` in their own fixtures. Taken together, `backend/app/main.py`
is the full repository path of this fixture (`app/` sits directly under
`backend/`).

**Reasoning:** `backend/**/*.py` requires the literal segment `backend/`,
then any depth of subpath (including a single intervening directory,
consistent with standard `**` glob semantics where `a/**/b` matches both
`a/b` and `a/x/b`), ending in a filename matching `*.py`.
`backend/app/main.py` decomposes as `backend/` (literal) + `app/`
(matched by `**`) + `main.py` (matches `*.py`) — no single-directory
trap, since `**` matching exactly one path segment is standard glob
behavior, not an edge case. Match.

**Before vs. after this patch, stated explicitly:** before commit
`183acd5`, this rule's frontmatter carried only `infra/**` and
`.github/workflows/**` — neither of which `backend/app/main.py` matches
(its first segment is `backend`, not `infra` or `.github`). This rule's
own qualified negative fixture therefore fell **outside** the rule's
scope entirely under the pre-patch frontmatter: a real coverage gap the
prior qualification round identified. After this patch, the third glob
`backend/**/*.py` brings `backend/app/main.py` into scope, so the
fixture the rule's own control text was written to deny is now actually
reachable by the rule that denies it.

**Result: PASS (matches `backend/**/*.py`) — this is the new fixture case
this evidence file exists to add.**

### Case 3 — non-matching path

**Path:** e.g. `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` or
`frontend/src/App.tsx`.

**Reasoning:** neither path's first segment (`knowledge`, `frontend`) is
`infra`, `.github`, or `backend` — matches none of the three globs.

**Result: PASS (correctly excluded from all three globs).**

**No cross-family false match introduced by the third glob.** The added
`backend/**/*.py` glob is identical in form to the glob already governing
RULE-005/006/008/009 — it does not create any new overlap with the
`infra/**`/`.github/workflows/**` globs this rule also carries (still
disjoint first path segments), it simply means this one rule (RULE-004)
now also activates on backend Python files, in addition to infra/CI
files — which is the deliberate point of this patch, not an accidental
widening.

**Reasoning method, stated explicitly:** manual textual evaluation of the
glob syntax against the rule's own recorded fixture paths, not an
observed harness event and not a test-tool run (none exists in this
repo; neither `infra/` nor `backend/` exist yet as real directories).

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md` — not
reinterpreted.** This rule's control 1 text, and both fixtures' own
content, were not touched by any of the three owner patch commits
(`5ad7d3c` and `183acd5` edited only the frontmatter block; `14d1337`
edited only the H1 heading line) — re-verified this session by reading
`.claude/rules/infra/release.md` control 1 directly and confirming it
matches the quoted text below. §2 above only adds a new *reachability*
fact about the existing negative fixture; it
does not change what the rule's control text says or how it evaluates
either fixture.

**Control under test:** control 1 (unchanged) — the rule's own
"Why this rule exists" section names this control's failure mode
directly as a denial-of-service vector.

**Control 1 clause (quoted verbatim):**
> Automated rollback is tied to genuine SLO/guardrail signals — never a
> manually or externally callable endpoint. ... The rollback mechanism's
> only trigger path is the pipeline's own SLO/guardrail evaluation
> crossing a pre-declared threshold — never an unauthenticated or
> convenience HTTP endpoint, CLI flag, webhook, or manual override
> callable by a human operator or external system. ... no carve-out of
> any kind, including an audited one, since no cited source authorizes
> one.

### Positive fixture (conforms) — path: `infra/pipeline/canary_guardrail.py`

```python
# infra/pipeline/canary_guardrail.py — invoked only by the deployment
# pipeline's own monitoring loop, never exposed as an HTTP route.
def evaluate_guardrail_and_maybe_rollback(metrics: GuardrailMetrics) -> None:
    if metrics.error_rate_pct > GUARDRAIL_ERROR_RATE_THRESHOLD:
        trigger_automated_rollback(reason="error_rate_guardrail_breached")
```

### Negative fixture (deliberately violates) — path: `backend/app/main.py`

```python
# app/main.py — an externally callable HTTP route
@app.post("/admin/rollback")
async def manual_rollback(current_user: AdminUser = Depends(require_admin)):
    trigger_automated_rollback(reason="manual_admin_trigger")
    return {"status": "rollback_triggered"}
```

**Result (carried forward, verdicts unchanged): positive fixture ALLOW;
negative fixture DENY.** The positive fixture's trigger path is a plain
function called only from the pipeline's own guardrail-evaluation loop —
no HTTP route, CLI flag, or webhook exists for it. The negative fixture's
`POST /admin/rollback` is exactly the excluded case control 1 names: an
unauthenticated-or-convenience HTTP endpoint / manual override callable
by a human operator. Control 1's text draws no exception for
authenticated callers ("no carve-out of any kind, including an audited
one"), so `require_admin` does not rescue the fixture. What is new in
this evidence file is not this verdict — it is that, per §2 Case 2, this
negative fixture's own path is now demonstrably inside the rule's scope,
which was not true of the 2026-09-22 evidence's frontmatter state.

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

**Rule file's own control 1 clause and frontmatter:** quoted in full in
§1 and §3 above.
