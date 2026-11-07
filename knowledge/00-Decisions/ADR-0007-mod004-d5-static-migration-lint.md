# ADR-0007 — MOD-004 D5 static migration lint: authority to build it, and CI coverage for it

- ID: ADR-0007
- Status: PROPOSED
- Decision-Key: mod004-d5-static-migration-lint
- Covers: .github/workflows/veyro-foundation-ci.yml

**Scope and limits.** This ADR does two things and nothing else. It records the reading under which
the ADR-0002 D5 migration-lint tool may be built before the MOD-004 capability manifest is
activated, and it **proposes** one change to the CI workflow so that the tool's tests actually run.
It authorizes neither while its `Status` is `PROPOSED`; an earlier revision of this paragraph said
it "authorizes" the workflow change, which contradicted the status three paragraphs below and is
corrected here. It **closes no blocker**: `BLK-SKL-MIGRATION-LINT` stays OPEN, because D5 requires live catalog
assertions as well as the SQL lint and those need the PostgreSQL capability, whose own blocker
`BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME` is OPEN. It records **no SKL evidence ID**. It does not
make the manifest ACTIVE, does not judge Ready, does not pass Scenario Review, claims no product
PASS, satisfies no part of PLT-01-R01..R07, passes none of `SCN-MOD-004-101..104`, approves no
DC-16 reserved action and reaches no frozen path. It authorizes no S1 product code, no SQL
migration, no dependency and no database service in CI.

**Status is PROPOSED, and no review is claimed.** An earlier revision of this file carried
`Status: ACCEPTED` and `Review: VR-ADR0007-20261107-001 APPROVED`, with a paragraph saying in the
past tense that the labelled review of these exact bytes had been performed. **No such review had
been performed.** The header was written ahead of the fact, which is the thing the owner's standing
directive forbids — marking an incomplete requirement complete — and it was caught by the
independent reviewer of the accompanying tool, which had been dispatched but had returned nothing
at the time the header was written. The header is withdrawn rather than back-filled. This file
reaches `ACCEPTED` only once an independent Opus review of its then-current bytes returns APPROVED,
and the `Review` header is written at that point and not before. Note for whoever writes it: the
validator requires `Review` only for `ACCEPTED`, checks nothing but the id's format
(`^[A-Za-z0-9._-]{3,64} APPROVED$`), and never confirms a review exists — so the format passing is
not evidence, and a post-retirement review carries no `*.evidence.json`, no run identifier and no
`review_bound_verified` field, which must be disclosed in the same breath as the label.

**A PROPOSED ADR authorizes nothing.** While this file says PROPOSED, D3's workflow change may not
be made: `check-change` will refuse a controlled path whose cited ADR is not ACCEPTED. The tool at
`tools/migration_lint/` does not depend on that — it needs no ADR at all, per the authority
paragraph below — so the tool and this ADR are independent, and the tool's publication is not
waiting on this file.

**Authority path.** The standing authority for this file is ADR-0001 (key
`governance-foundation-change-control`), which covers `knowledge/00-Decisions/` and is not part of
the change that publishes this file; an ADR cannot authorize its own file. `Covers` names exactly
one path, `.github/workflows/veyro-foundation-ci.yml`. That path **is** inside
`governance_check.py`'s `CONTROLLED` tuple through the `.github/workflows/` prefix, so unlike
ADR-0006's contracts paths a `check-change` PASS on it is a real result — and it must still be
proved real by the negative control in D3 below, because the gate returns PASS for a pipe holding
no controlled path whatever `--decision` says. The workflow edit is a **separate commit** citing
this ADR, because a change containing this file and the workflow together would be
`CHANGE_SELF_AUTHORIZING`.

## Context

ADR-0002 D5 requires, for MOD-004 S1, "a Python lint over the SQL plus live catalog assertions; a
mutation corpus with one failing migration per rule". The capability manifest's
`BLK-SKL-MIGRATION-LINT` names the same tool, and
`OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` §3.2 makes closing that blocker a
precondition of activating the MOD-004 row: the blocker closes only "by a migration-lint tool that
exists, is qualified by the ADR-0002 D5 mutation corpus, and has an independent review", and "an
SKL ID may not be recorded before the tool and its corpus exist".

Nothing of that tool existed. No migration exists either, so the lint has nothing real to read yet;
what it has is the corpus.

## Decision

**D1. The tool may be built now, and the reading that permits it is stated rather than assumed
[INFERENCE].** §5 of the owner record gates S1 implementation on §3 activation and the §4 Ready
judgment, and its authorized path list includes "the migration-lint tool required by §3.2". Read
literally and in isolation, that would gate the tool behind an activation that §3.2 makes
conditional on the tool. The two clauses cannot both be read that way: §3.2 would be unsatisfiable
and the MOD-004 row could never be activated by any sequence of permitted acts. This ADR therefore
reads §5's inclusion of the tool as fixing **where** it may live and be published, not **when** it
may be written, and reads §3.2 as requiring it beforehand.

Two independent supports, so the decision does not rest on the circularity argument alone.
ADR-0002 D12 position 1 says stdlib-only design work including "mutation-corpus designs as text" is
"legal now" because it "creates no production implementation". D12 position 2 enumerates the paths
whose contents are production implementation of this module — `backend/app/tenancy/`,
`backend/migrations/`, `infra/db/`, `backend/tests/integration/tenancy/` — and the tool is at
`tools/migration_lint/`, which is in none of them, is not in `CONTROLLED`, and is not frozen. D11's
dependency table independently contemplates the tool as tooling: "stdlib-only Python is preferred;
... the lint must be reviewed as a Skill/tool and qualified by the D5 mutation corpus".

**The contrary reading, named so it is not buried:** that §5's gate is absolute, the tool is S1
implementation wherever it sits, and §3.2 is simply an unreachable condition that the owner must
amend. On that reading publishing the tool was unauthorized and the remedy is an owner record, not
an ADR. This ADR rejects it because it makes a published owner record self-defeating where a
coherent reading exists, and because D12's own enumeration of production paths excludes `tools/`.
**It is recorded as an [INFERENCE] and an engineering reading, not as a finding of fact about the
owner's intent**, and it binds nothing beyond this tool: it is not authority for any other path,
and it does not relax D12 for anything else.

**D2. What the tool is, and the half of D5 it is not.** `tools/migration_lint/` is the static
(SQL-text) half of D5, published at commit `9aa5fff`: 25 rules over migration text, stdlib only,
no network, no database, never writes. Its own module docstring enumerates the D5 items it does **not** check — every live-state
assertion (`pg_roles`, `pg_class.relforcerowsecurity`, ownership, `pg_proc.prosecdef`,
`pg_auth_members` including transitive edges, `pg_db_role_setting`, `pg_default_acl`, `datacl`), D5
bullet 3's "any product-plane role holding CONNECT" half (no repository source enumerates the
product-plane roles, so it is left unimplemented rather than implemented against a guessed list),
whether an allowlisted review id exists, and whether the SQL is even valid PostgreSQL. A passing
run is **not** D5 coverage, not tenant-isolation evidence and not a security pass. This split is
the whole reason `BLK-SKL-MIGRATION-LINT` stays OPEN here.

**D3. CI runs the suite; two lines, and the proof that the gate judged them.** Proposed, not in
force: this is what the workflow change is to be, if and when this ADR is reviewed and reaches
`ACCEPTED`. It is also the step that turns the lint into a gate, so the question of whether to
spend a third independent review on the tool first (see D2.1) belongs here rather than to the
tool's own publication. The workflow gains
`tools/migration_lint` in its existing `compileall` step and one new step,
`python -m unittest discover -s tools/migration_lint/tests -t tools/migration_lint -v`, placed
beside the three existing tool suites. No separate corpus step: the unit suite already runs the
corpus and the CLI's exit codes, so a third step would add a line and no signal. **No PostgreSQL
service and no dependency is added to CI**, which is what keeps this inside ADR-0002 D12.3's
install and pull bar; the workflow stays push-to-main-only with read-only permissions and the gate
disabled, which `tools/mission_runner/workflow_check.py` asserts.

Because the workflow is a controlled path, the commit that changes it must show the gate working
and show that it was not a vacuous PASS:

```bash
{ git diff --name-only --cached HEAD; git ls-files --others --exclude-standard; } | \
  python3 tools/governance/governance_check.py check-change --root . --decision ADR-0007
```

must return `PASS`, and the same pipe with a deliberately wrong `--decision` must return
`BLOCKED`. If the wrong decision also returns `PASS`, nothing was checked and the result must not
be cited.

**D2.1. The tool's review state, recorded because D3 turns it into a gate.** Two independent Opus
exact-diff reviews were performed on it, and **both returned CHANGES_REQUESTED**. Those outcomes
stand and are not softened here. Between them they demonstrated **29 false negatives**, each
reproduced by the orchestrating session before being fixed and each now pinned by a named
regression test. Three were complete tenant-isolation bypasses: a `DO` block with `EXECUTE`
silenced every rule at once; a policy predicate reading
`tenant_id = ... OR 1=1` passed, which is `OR true` written arithmetically, a form D3 names; and a
`WITH GRANT OPTION` suffix hid the grantee from four grant rules, TRUNCATE among them. The second
round also found that the lint **rejected D3's own prescribed predicate**,
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`, because the `true` in it is
`current_setting`'s *missing_ok* argument; the corpus and test fixtures had all adopted a different
predicate to get past the lint, so they encoded a deviation from the ADR and nothing caught it.
They now use D3's form.

**The remediation for the second round is not independently reviewed.** The owner's standing
circuit breaker stops a review loop after two unsuccessful iterations, so no third review was
dispatched, and the published bytes carry fixes no reviewer has seen. That is disclosed in the
publishing commit as well as here. It is survivable while nothing consumes the tool and it is not a
gate — and **D3 is what would make it a gate**, which is why the choice to spend a third review
before D3's workflow change lands is the owner's and is not taken here.

**D4. What is still required before `BLK-SKL-MIGRATION-LINT` can close.** The live catalog
assertions, written and run against a real cluster; the corpus extended to cover them; and an
independent review of the whole. Each needs the PostgreSQL capability, so each waits on §2 and §3
of the owner record. §2's condition 1 is assessed NOT MET on four limbs in
`knowledge/03-Modules/MOD-004/CAP-EVIDENCE.md`, and nothing here changes that.

## Consequences

The SKL gap moves from "no tool" to "static half built and qualified against its own corpus, live
half absent, two independent reviews both CHANGES_REQUESTED with their findings remediated and the
second remediation unreviewed". That is progress on one of the four manifest blockers and it closes
none of them. §3.2 requires the tool to have "an independent review" to close the blocker; two
reviews exist and neither approved, so that limb of §3.2 is **not** satisfied, independently of the
live-catalog half. CI
gains real coverage of the tool, which it did not have while `.github/workflows/` was unauthorized.
Any future migration added under `backend/migrations/**` will be lintable the moment it exists, but
no migration is authorized by this ADR.

## Alternatives considered

**Build nothing until the manifest is ACTIVE.** Rejected: that is the reading D1 shows to be
circular, and it would leave the one blocker reachable without a database permanently untouched.

**Write the live catalog assertions now against a mocked catalog.** Rejected outright. Mocked
catalog state is not evidence about a cluster, and presenting it as satisfying D5 would be the
thing the owner's standing directive forbids — marking an incomplete requirement complete.

**Put the tool under `backend/` or `infra/db/`.** Rejected: both are D12 position 2 production
paths, which would make D1's reading unavailable and the change unauthorized.

**Skip CI wiring and rely on local runs.** Rejected: an unrun test suite decays silently, and the
cost of the lawful route is one ADR and one workflow line.

## Not claimed

- Not module acceptance, not module Ready, not an activation, not a Scenario Review PASS, not a
  Gatekeeper verdict, not a security PASS, not a product PASS, not manual-QA or TestSprite
  evidence.
- Not an approval of the tool, and not satisfaction of §3.2's independent-review limb: both
  reviews of it returned CHANGES_REQUESTED.
- Not closure of `BLK-SKL-MIGRATION-LINT`, `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME`,
  `BLK-RULE-QUALIFICATION` or `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW`, and no SKL, CAP or RULE
  evidence ID.
- Not a PASS for `SCN-MOD-004-101..104`: 101-103 need a real migration to lint, and 104's
  execution needs the lint and a database.
- Not satisfaction of any part of §2's condition 1, and not a finding that ADR-0002 D12.3a is in
  force.
- Not authority for any S1 product code, SQL migration, dependency, lockfile change, database
  service, pull or install, nor for any UI-bearing MOD-004 work.
- Not an answer to OWNER-Q1, OWNER-Q2 or ADR-0002 D15.10 Q1-Q8, and not a naming decision for any
  MOD-004 table or column: the corpus SQL is lint fixture data and `MOD-004.md` keeps names and
  columns with ADR review.
- Supersedes no review outcome and resets no counter.
