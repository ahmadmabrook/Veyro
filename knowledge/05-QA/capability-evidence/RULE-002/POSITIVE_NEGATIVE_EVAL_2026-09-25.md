---
doc: RULE-002-POSITIVE_NEGATIVE_EVAL
status: LIVE
updated: 2026-09-25
---

# RULE-002 Stage-5 Qualification Evidence — `.claude/rules/infra/secrets.md`

**Rule ID:** RULE-002
**Source rule file:** `.claude/rules/infra/secrets.md`
**Commit binding:** `14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a` (current
governed HEAD, confirmed via fresh `git fetch`/`git rev-parse` to equal
`origin/main`; no edit was made to any file under `.claude/rules/**` in
the course of producing this evidence). **Corrected after an independent
review found this file was first written bound to `183acd535e6786f1edc1993a5ef6f13afd13a4ec`,
which the owner had already superseded by the time this file was
finished — the owner pushed a further commit,
`14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a`, mid-session, and the original
version of this file did not notice.** SHA-256 of `secrets.md` at this
binding, independently recomputed: `e61455b487c32a79e2689a1580fdd41fa4cf331e7dcb75cc31b00058d30d1eb1`.
Supersedes the prior binding to `5aa5cc5b6b6d041372b83e043febf179d0460fa5`
in `POSITIVE_NEGATIVE_EVAL_2026-09-22.md` (retained as historical record,
not deleted).
**Reviewer/model evidence:** veyro-test-author (Sonnet tier per
`DEVELOPMENT_CONSTITUTION.md` model routing — this session's actual model
is `claude-sonnet-5`)
**Timestamp:** 2026-09-25
**Status of this evidence:** content-level qualification: sound, carried
forward unchanged from 2026-09-22. Path-scope qualification:
**`N/A (scope: global)`** — explicitly neither `PASS` nor `FAIL` (see §2).

## 1. Applicability binding as currently documented

**Rule file's own frontmatter (quoted verbatim, re-read this session):**
```yaml
---
scope: global
---
```

**This is a different kind of change from the other 8 files, not just a
wider glob — and it took three commits, not two, to reach internal
consistency.** Commit `5ad7d3cbb67f0433031850b0e3180f7a4872cccc` first
gave this file `scope: path` with `paths: ["infra/**", ".github/workflows/**"]`
— the same shape as the other 8 files at that point. Commit
`183acd535e6786f1edc1993a5ef6f13afd13a4ec` then replaced that entire
block, confirmed directly from that commit's diff:
```diff
 ---
-scope: path
-paths:
-  - "infra/**"
-  - ".github/workflows/**"
+scope: global
 ---
```
The result carries no `paths:` field at all. **At that point, however,
the file was internally inconsistent for one more commit:** its own H1
heading still read "# Rule: Infra/SRE — Secrets Externalization Baseline
(`infra/\*\*` binding)" — the exact same title text as before the scope
change — directly contradicting the frontmatter immediately above it.
Commit `14d13376680cdeba9011f9b1d2d3e9ab1d7c2a7a` fixed this, changing
only the H1 to "(global binding)":
```diff
-# Rule: Infra/SRE — Secrets Externalization Baseline (`infra/**` binding)
+# Rule: Infra/SRE — Secrets Externalization Baseline (global binding)
```
No frontmatter or control text changed in this third commit — confirmed
directly via `git show 14d1337`. The frontmatter/H1 pair is now
internally consistent for the first time across all three commits. The
resulting scope is a deliberate, structural choice (secrets discipline
applies everywhere a fixture, config, or source file might contain a
credential-shaped value — not only under `infra/**`), not an oversight;
the prior version of this evidence file overstated this by calling
`183acd5` itself "not an incomplete patch," which was not accurate at
that specific commit — the H1/frontmatter contradiction at `183acd5` was
exactly the kind of incompleteness a later commit still needed to close.

## 2. Path-scope qualification case (EIP H.5) — disposition: `N/A (scope: global)`

**Disposition: `N/A (scope: global)` — explicitly not `PASS`, not
`FAIL`.**

**Why no matching/non-matching test can be constructed here, stated
plainly:** EIP H.5's path-scope test presupposes a `paths:` glob to point
a matching-path fixture at and a non-matching-path fixture away from. A
`scope: global` rule has no `paths:` field by design — it is declared to
apply to every path unconditionally, so there is no candidate
"non-matching path" to construct: every path is, by the rule's own
declared scope, a matching path. Attempting to force a two-row
matching/non-matching table here (as §2 does for the other 8 files in
this set) would either (a) report both rows as trivially "matches,"
which tests nothing, or (b) invent a fake non-matching case that
contradicts the rule's own declared `scope: global`, which would be
dishonest. Neither is done. This is recorded as a genuine, permanent
disposition for this rule under this scope choice, not a gap to
"eventually" close once a `paths:` field is added — adding one would be a
scope *change*, not a fix to this evidence.

**Existing precedent in this project for a `scope: global` rule never
being put through a matching/non-matching path test, for the identical
structural reason:** `.claude/rules/global/owner-reserved-restrictions.md`,
independently re-read this session:
```yaml
---
scope: global
---
```
That file's own frontmatter carries the same `scope: global`, no
`paths:` shape, and — for the same reason RULE-002 now has none — has
never had a path-scope PASS/FAIL evidence entry produced for it anywhere
in this project's evidence tree. RULE-002's `N/A` disposition here is
consistent with, not an exception to, that existing precedent. **Caveat,
raised by an independent review of this evidence:** `owner-reserved-restrictions.md`
was never itself put through this project's `RULE-<NNN>` capability
qualification pipeline (it has no `CAPABILITY_REGISTRY.md` row and no
evidence directory), so its bare existence shows the same shape is used
elsewhere, not that a reviewer has ever formally endorsed `N/A` as a
qualification-passing disposition. That formal endorsement is a Round 5
judgment, not something this evidence file can establish on its own.

**A second, related caveat the same review raised, also left to Round
5:** EIP H.5's path-scope requirement has two halves — "correct" *and*
"does not pollute unrelated contexts." A `scope: global` rule
mechanically satisfies the first half by construction (there is nothing
to be incorrect about), but the second half is a live question for this
specific rule: controls 2 and 3 name CI/environment-secret-scope and
local-`.env` mechanics specifically, and under `scope: global` those
controls now load in every context, not only where they're actually
actionable. Whether that counts as "polluting unrelated contexts" in a
way that matters, or is simply harmless because an agent reading an
inapplicable control just doesn't act on it, is a content-qualification
judgment this evidence file does not resolve — flagged here for Round 5,
not decided.

**What this evidence does NOT claim:** whether Claude Code's rule-loader
actually treats a `scope: global` rule as always-loaded at runtime (as
opposed to, say, silently requiring a `paths:` field to load at all)
remains itself unverified by this project — the same standing disclosure
that applies to the `paths:` mechanism generally. This section states
what the frontmatter's own declared semantics are, not an observed
harness event.

## 3. Content-level qualification case (`CAPABILITY_POLICY.md` stage 5 / EIP H.5)

**Unchanged from `POSITIVE_NEGATIVE_EVAL_2026-09-22.md`.** This rule's
control 1 text was not touched by any of the three owner patch commits
(`5ad7d3c` and `183acd5` edited only the frontmatter block; `14d1337`
edited only the H1 heading line) — re-verified this session by reading
`.claude/rules/infra/secrets.md` control 1 directly. The fixture pair
and verdicts are carried forward.

**Control under test:** control 1 (unchanged) — "No secret is ever
committed to the repository, in any form."

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

(This negative fixture describes the violation's shape in prose rather
than reproducing a matching literal, for the same reason recorded in the
2026-09-22 evidence: writing out a real-shaped secret literal, even as a
"negative fixture," would itself trip the very control under test.)

**Result (carried forward): positive fixture ALLOW; negative fixture
DENY.** `EXAMPLE_NOT_A_REAL_KEY`/`EXAMPLE_NOT_A_REAL_PASSWORD` are exactly
the rule's own named example of an explicitly-fake, clearly-labeled
placeholder. An unlabeled, real-shaped value is denied per the rule's own
fail-closed instruction ("if it is unclear whether a given value is a
real secret or a synthetic placeholder, treat it as a real secret"). This
determination is entirely orthogonal to the `scope: path` → `scope:
global` frontmatter change — the rule's substantive text governing what
counts as a compliant vs. violating secret-handling fixture is identical
in both scope states.

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

**`.claude/rules/global/owner-reserved-restrictions.md` (quoted
verbatim, cited as this project's existing `scope: global` precedent):**
> ---
> scope: global
> ---

**Rule file's own control 1 clause and frontmatter:** quoted in full in
§1 and §3 above.
