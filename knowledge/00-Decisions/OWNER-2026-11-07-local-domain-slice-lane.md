# Owner decision — the local-domain-slice lane: product code whose correctness does not depend on the database

**Status: OWNER-DIRECTED DECISION; NOT OPERATIONALLY EFFECTIVE until this exact record receives
independent exact-subject Opus review, first-publication owner attestation under the rule in force,
non-force publication, and successful exact-SHA push CI.** Until all four are done nothing in it is
granted, and once done it validates nothing taken before. It is not module acceptance, not a Ready
judgment, not a capability activation, not a Scenario Review PASS, not a product PASS, and it
approves no DC-16 reserved action.

**No `Covers` or `Actions` header is present, deliberately**, for the reason
`OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` gives for the same omission. An
`OWNER-*` record's `Covers` is read only against the **frozen** set; a controlled path still needs
an accepted ADR, and `tools/governance/governance_check.py` resolves a controlled path through
`CONTROLLED_CHANGE_UNREFERENCED`, which requires an ADR and rejects an `OWNER-*` stem. A `Covers`
list here would be inert for every path this record discusses while reading like a permission. No
`Actions`, because this record approves no `spend-paid-activation`, `production-promotion`,
`material-product-business-change` or `real-member-data`; `governance/registry.json`
`reserved_actions` is unchanged and unnarrowed. **The CI wiring this record conditions the lane on
is a controlled-path change and needs its own accepted ADR** (§5.3).

## 1. Owner source

The directive is the owner's, given directly in the Claude Code session on 2026-11-07 and relayed
to this record by the orchestrating session; it is not checked here against an original message, and
no chat message ID is exposed or invented. The operative statements, quoted:

1. "Proceed with the owner-record development slice."
2. "I authorize you to prepare the smallest valid change to the development-gating policy that
   permits independently testable local product code before production readiness, without requiring
   a new owner decision for every development slice."
3. "Use your existing delegated authority wherever applicable."
4. "Separate local product development from production deployment requirements. Preserve actual
   tenant isolation, authorization correctness, data integrity, meaningful tests, and honest
   acceptance status."
5. "Prepare any genuinely required owner-authenticated amendment as one consolidated action, rather
   than repeated slice-by-slice approvals."
6. "Once effective, immediately implement MOD-004 tenant-domain logic, validation, and
   authorization policy with unit tests."
7. "Do not return to open-ended security research or documentation review loops. Do not mark
   database integration or production readiness as complete without actual evidence."

Statement 2 authorizes the orchestrating session to **prepare** this change; it does not authorize
the session to publish it. Publication of any `OWNER-*` record stays an admin-authenticated act on
the owner's machine, and the attestation requires the owner's own `owner_choice_quote` and a
non-empty `source_prompt_message_id`, which an agent never supplies or infers. That is why §7 asks
for exactly one manual step and nothing else.

From the same owner's standing directive of 2026-11-06, two clauses bind this record and are quoted
in full: "Do not falsely claim that a governance restriction has been lifted when it remains legally
or procedurally effective. If an owner-reserved decision must be changed, follow the already
established owner-authenticated publication mechanism rather than bypassing its controls." And:
"Do not erase failed reviews, rewrite history, fabricate evidence, reset exhausted counters
deceptively, or mark incomplete requirements as complete."

## 2. What this record supersedes, stated in the open

**The provision.** ADR-0002 D12 position 2, quoted in full, all three sentences: "Stdlib-only code
or SQL committed to the S1 paths (`backend/app/tenancy/`, `backend/migrations/`, `infra/db/`,
`backend/tests/integration/tenancy/`) is production implementation of this module. Avoiding
third-party code removes the EIP ¶754 supply-chain issue but not the Ready or Active gate, so it is
not legal before them. Also, stdlib Python cannot exercise PostgreSQL RLS, so S1 evidence needs the
PostgreSQL and driver capabilities anyway." And D12 position 4: "Actual S1 code may not start
before the module is Ready and the D11 manifest is ACTIVE."

That third sentence is the reason §6 of this record exists and is not superseded by it: stdlib
Python cannot exercise RLS, so a slice is never S1 evidence, and this record says so rather than
leaving the sentence out. An earlier revision of this paragraph said "quoted in full" while
omitting it; an independent reviewer caught that, and the omission is recorded rather than silently
repaired.

**This record supersedes positions 2 and 4 for one narrow class of code and for nothing else**,
defined in §3. What bounds that class is §3.4's independent exact-diff review of every slice,
filtered by §3.2's closure check; **the check is not itself the bound**, and §3.2 states plainly
why not. Earlier revisions had it the other way round. The third sentence of position 2 is not
superseded. The owner's statement 2 is the authority. This is stated
here rather than inferred quietly, because an independent review of an earlier session's draft
found that burying such a supersession would leave the owner attesting to a change the record did
not disclose.

**The argument, and the part of it that does not work.** The Capability gate's purpose (EIP ¶753-754)
is to bar *use of an unreviewed capability* for implementation. Code in the §3 class uses no
capability beyond the Python standard library whose availability the S0 slice already
evidenced: no database, no driver, no third-party package, no network, no filesystem, no clock, no
randomness, no process. On that reading ¶754 is **satisfied rather than waived**, and ¶749-750's
"environment/tool access available" is met for such work.

What that argument does **not** dispose of is EIP ¶773, which permits research, documentation or
environment preparation "only if it cannot create production implementation that bypasses the
gate". Code in the §3 class **is** production implementation. This record does not pretend
otherwise and does not claim ¶773 is satisfied. It makes a narrower change: it moves the *timing*
at which this class of production implementation may be written, which is what D12 positions 2 and
4 fix, while leaving every **acceptance** gate standing — Scenario Review, Implementation Complete,
Gatekeeper, module acceptance and the release-gate evidence are untouched, so no slice can reach
approval through this lane. ADR-0002 D12 is itself marked `[INFERENCE]` and records that it adopted
"the stricter one for code timing" of two assessments; this record adopts a narrower reading for
one mechanically-bounded class, on the owner's authority, and leaves D12 in force for everything
else.

**The precedent.** `OWNER-2026-10-19-mod004-s0-only.md` already did this once, for the S0 slice:
its §2 records that the two slice certificates "substitute for the module-wide Ready and
ACTIVE-manifest timing in EIP §8/ADR D12" for S0 alone. `OWNER-2026-11-06-mod004-cap-and-
implementation-authorization.md` §4 and §5 likewise superseded ADR-0002 checklist item 8 and unmet
prerequisite (f). The owner's statement 5 asks for the general form of that act once, instead of
repeating it per slice. **This record generalizes the mechanism; it does not widen what a slice may
contain beyond §3.**

## 3. The lane

A **local domain slice** is product code that satisfies all of the following.

1. **It lives under the lane root.** One root, fixed in `tools/domain_closure/domain_closure.py`
   and not configurable by a slice:

       backend/app/tenancy/domain/**            pure domain logic
       backend/app/tenancy/domain/tests/**      its unit tests, inside the same root

   `backend/app/tenancy/domain/` is deliberately a **sub-root** of the D12 S1 path
   `backend/app/tenancy/`. Code that needs PostgreSQL belongs in the parent directory and **stays
   gated by D12 position 4 exactly as before**.

   **Two revisions of this paragraph claimed more than the tree supported, and the history is kept
   rather than tidied.** It first said the split was structural, "so the two classes cannot be
   mixed up or quietly merged". The split in the *tree* never implied containment in the *import
   graph*, and two routes out were proved: `from ..impure import x` resolves to
   `backend/app/tenancy/` -- this very gated directory -- and a module behind a symlinked directory
   that the walk never enumerated could still be imported by a lane file. Both returned PASS and
   both performed real I/O when run. The paragraph was then corrected to say containment "is now
   enforced". A fourth review found that overstated as well: what is enforced is that every
   *relative* import resolves inside the root and that no symlink is tolerated anywhere beneath it,
   which is a rule about spellings this check can see rather than a property of the import graph.
   The accurate statement is the narrow one -- **the two proved routes out are refused and pinned by
   tests** -- and it is what this record claims.

   **The tests moved inside the root, and the reason is a defect, not a preference.** They were at
   `backend/tests/domain/`, a second lane root. The fourth review proved that with two roots the
   lane's tests **could not import the lane's source at all**: the repository-root spelling is
   refused by the check and raises `ModuleNotFoundError` under CI's own `discover -s tests -t .`;
   the relative spelling is permitted by the check but raises `ImportError: attempted relative
   import beyond top-level package`; the backend-root spelling runs but is refused by the check.
   So §3.3's tests, on which this record rests a slice's entire evidence, were unwritable, and
   three revisions of this record had not noticed. The first fix the orchestrating session proposed
   was worse than the defect -- mapping the repository-root spelling onto the backend root fails
   *open*, because any foreign top-level `app` package earlier on `sys.path` then binds and runs
   instead, and it hard-codes one CI invocation into the import graph -- and the reviewer killed it
   by executing it. One root with the tests inside it needs no mapping: a slice writes
   `from .. import lifecycle`, and `python3 -m unittest discover -s app/tenancy/domain/tests -t .`
   from `backend/` then runs. That was verified against a real slice and is now pinned by a test
   rather than left as a hand check.

   **What is fixed and what is not.** The relative spelling works and the check permits it. The
   backend-root absolute spelling -- `from app.tenancy.domain import lifecycle` -- still **runs**
   and is still **refused by the check**, which is a standing cost recorded in §3.2 rather than a
   gap awaiting a fix, because closing it by rule change is the thing §5.4 forbids. The record does
   not claim the check and the runtime now agree; they agree for one spelling.

   **Two files a first slice must not forget**, recorded because omitting either produces an error
   that reads like a check failure: `backend/app/tenancy/domain/__init__.py` and
   `backend/app/tenancy/domain/tests/__init__.py`. `unittest` discovery requires both -- namespace
   packages are not discoverable since Python 3.11 -- and both are inside the lane root, so §4's
   statement that no file outside `backend/app/tenancy/domain/**` is written under this record
   holds. `backend/app/tenancy/` itself needs no `__init__.py` and works as a namespace portion,
   which is what makes that statement exact rather than approximate; it was checked by execution
   after a reviewer doubted it.

   **This was found by writing the first slice, not by reading the record.** Three revisions
   described the import defect while the prescribed layout still refused the only import a test
   needs, and no reading caught it. That is recorded for the same reason §3.2's table is: the
   failures here have been found by running things, and the record's credibility depends on saying
   which.

2. **It passes the closure check, which is a mistake filter and not a sandbox.** This is the
   paragraph the owner is attesting to, and it claims materially less than earlier revisions did.

   **What the check cannot be.** It reads source files in this repository. Anyone who can write a
   file under the lane root can also write `tools/domain_closure/domain_closure.py`, which is **not
   a controlled path**: no ADR, no owner record and no validator stands between an author and the
   rules that judge them. A boundary whose own subject can edit it does not contain a hostile
   author, and **nothing in this record rests on the claim that it does.** §2's supersession is not
   justified by the check being airtight. It is justified by §3.3's tests, §3.4's independent
   exact-diff review of every slice, and §6's bar on citing a slice as evidence of anything -- with
   the check as the filter that keeps that review from spending itself on mistakes a machine
   catches. Earlier revisions had this the other way round, and that inversion is what four review
   rounds cost.

   **Four rounds, and what each round's remedy cost.** Each row's remedy supplied part of the next
   row's route.

   | Round | Found by | Routes proved | The remedy, and its cost |
   |---|---|---|---|
   | 1 | review 1 | `unittest.case.sys.modules["os"]`; `operator.attrgetter("__globals__")(fn)["__builtins__"]`; `from unittest import mock` | Banned the literal names `sys`, `os`, `modules` -- three instances, not a class. That is what round 2 walked around. |
   | 2 | review 2 | The standard library's own private aliases: `statistics._random` *is* `random`, `collections._sys` *is* `sys`, `enum.bltns` *is* `builtins`, `calendar.datetime` *is* `datetime`, `dataclasses.inspect` *is* `inspect`, `hashlib._hashlib`. Through them the reviewer executed arbitrary code, an outbound TCP connection, a file read, a clock read, entropy consumption and `os.system`. Also: module-level state mutated across calls, and an `if __name__` guard admitting any comparison. | Installed the first property rule -- resolve the module, compare its own `__name__` to the path it was reached by -- plus the module-state rule and an exact guard comparison. The right shape; it **failed open two rounds later**. |
   | 3 | review 3 (two), orchestrating session (one) | A string annotation: `def _rule() -> "print('...') or int"` passes every syntactic rule, and `typing.get_type_hints` then evaluates it against the module's globals, whose builtins table is complete -- arbitrary execution with no forbidden import, name, attribute or dunder. A module behind a symlinked directory, which `Path.rglob` does not descend into, imported as `from .ext.evil import do`. And the out-of-lane relative import of §3.1, which the code positively *permitted* under a comment asserting that "a relative import stays inside the lane". | Refused string constants anywhere inside an annotation as a class; refused symlinks in the walk rather than skipping them; computed every relative import's target. The annotation rule removed strings from annotation *positions*, not from what a checked annotation *evaluates to* -- which is what round 4 used. |
   | 4 | review 4 | The round-2 module rule **failing open**: its resolver returned the same `None` for "not a module, carry on" as for "could not resolve", so `from json import tool` passed unchecked and `tool.argparse.FileType("w")` wrote a file, `argparse.FileType` being `open` under another name. A bare-`Name` annotation evaluating to a module-level string, and functional `TypedDict`/`NamedTuple`, both reaching `get_type_hints` with no annotation string present. A stale hash-based `.pyc` under `__pycache__`, which the walk skipped, running while its `.py` passed. And `decimal.getcontext().prec = 2`, making one pure function return two answers for one input. | The shape changed instead of the rules growing: the resolver fails closed on an unresolved path; the allowlist went from thirty-two modules to **four** -- `__future__`, `dataclasses`, `enum`, `re`, plus `unittest` in the tests root -- which removes `json`, `typing` and `decimal` from the lane altogether rather than naming their exits; `__pycache__` and anything that is not a regular file are refused rather than skipped. Shrinking the list exposed a latent bug: the final import check omitted its tests-only clause and had only ever worked because `unittest` sat in both sets. |

   **The counts have drifted, and the drift is itself a finding.** Earlier revisions of this record
   said nine, then eleven; a comment in the tool said fifteen; the orchestrating session's own count
   of the same artifacts came to seventeen. The totals disagree because "an escape" was never
   defined -- a class demonstrated through six aliases is one route or six depending on the
   counting. **The disagreement is recorded rather than resolved.** No decision in this record turns
   on the number, and a tally of closed escapes invites exactly the reading this section rejects:
   that a high score is evidence of safety. The table above is the honest form, because it shows
   what the fixes cost rather than how many there were.

   **Which of the proved routes a real author could have hit, which is the question that matters
   for a mistake filter.** Four: the out-of-lane relative import, the stale `.pyc` running while its
   `.py` passed, process-wide mutable state inside an allow-listed standard-library module, and the
   import gap that made lane tests impossible. **All four are closed, and each is pinned by a
   named test**, which is stated this precisely because a review of these bytes found the earlier
   form of this sentence true of only three: the relative import by the lane-containment tests;
   the stale `.pyc` by the `__pycache__` refusal test; the stdlib global state by `decimal`'s entry
   in the removed-vehicle table, since what closes it is the allowlist's shortness rather than a
   rule; and the import gap by a test that lays out a real slice, runs the closure check over it
   and then runs the lane's tests through the exact command CI uses. The last two of those pins
   were added in response to that finding; before it, both were hand checks described as pinned.
   The remainder are deliberate constructions -- private aliases, string-target reflection helpers,
   annotations that evaluate to payloads -- that no domain author writes by accident, and the check
   makes no claim to stop an author who writes them on purpose.

   **The rules, as the code now has them.** Imports restricted to the four modules above, matched on
   the top-level package, with every `from X import n` also checked as the module path `X.n`, and
   `unittest` admitted only under `backend/app/tenancy/domain/tests/`; **a path that cannot be
   resolved is refused, not admitted**. Every relative import's target computed from the importing
   file's own position and required to resolve inside the lane root. **Star imports refused**; a
   **bare** relative import (`from . import sibling`) is *permitted* when it resolves inside the
   root, because that is how a slice imports its own siblings and how a lane test imports its
   subject. Two earlier revisions of this list said bare relative imports were refused: the code
   never did refuse them, and the flag that would have done so sat after an unconditional `return`,
   where it could not run. A review found the dead code and the false claim together. The claim is
   corrected and the dead flag removed, rather than the code being changed to match the document --
   had it been, every lane test would have become unwritable, which is the defect §3.1 records. No module reached through another module's attribute unless it is a genuine submodule
   whose own `__name__` equals the path it was reached by -- the one rule that resolves at check time
   rather than matching a spelling. No forbidden builtin named or called. No attribute whose name is
   a forbidden module name or one of the reach primitives (`modules`, `builtins`, `builtin`,
   `attrgetter`, `methodcaller`, `itemgetter`, `getattr`, `setattr`, `delattr`, `globals`, `locals`,
   `vars`, `open`, `eval`, `exec`, `__import__`). No `__dunder__` attribute except `__doc__` and
   `__name__`; no `__dunder__` string literal except `"__main__"`; no definition of a dunder hook
   that could answer for a refused attribute. No string inside any annotation, nested ones included.
   No `async`/`await`, no `global` or `nonlocal`, and no module-level statement other than an import,
   a docstring, an assignment, a `pass`, a `def`/`class` or an `if __name__ == "__main__"` guard
   written exactly that way. The walk refuses any symlink, any `__pycache__` and anything that is not a
   regular file, each with its own violation code. And no file may exist under the lane root at all
   until this record is committed: the check reports `LANE_NOT_EFFECTIVE` rather than examining it.

   **Two rules claim less than their names suggest, stated because a reader would assume otherwise.**
   "No mutation of module-level state" is true of **the slice's own module-level names only**: it
   tests whether a mutated name is module-level in the file being checked, and it does not reach
   state inside an imported module. A review found that it reached less even than that -- the
   collector saw only single-name assignment targets, so `CACHE, SEEN = {}, []` bound two
   module-level names it could not see, and the very mutations it refuses under `CACHE = {}`
   returned PASS. That was an ordinary spelling, not a contrivance, so it was closed in the code
   (tuple, nested and starred targets are now unpacked) and pinned by a test, rather than disclosed
   here as a limit. What covers that now is the shortness of the allowlist -- a
   property of those four modules, not a rule -- which is why widening the allowlist re-opens a
   closed question rather than merely adding a convenience. And the annotation-string rule removes
   the *input* an evaluator would need; it does not name the evaluators, so its protection is only
   as good as the allowlist keeping evaluators out. Its disclosed cost is that `typing.Literal["x"]`
   is refused although it is pure; that cost is presently moot because `typing` is not admitted at
   all, and the rule is kept anyway, cheaply, against the day the allowlist changes.

   **The third cost is the sharpest, and it is a cost rather than a defect.** The check refuses the
   import spelling this repository has taught every author to write. `backend/tests/test_app.py`
   imports `from app.config import ...` and `from app.main import create_app`, and CI's own backend
   step runs `discover -s tests -t .`; so the backend-root absolute form is the house style, it runs
   correctly inside the lane, and the check refuses it anyway -- because it binds whichever
   top-level `app` package is first on `sys.path` and so fails *open* against a foreign package of
   that name, where the relative form cannot. A slice therefore writes `from .. import lifecycle`.
   The next author will reach for the house style first, find it refused, and have an obvious
   cheap escape: add `app` to a four-module allowlist. **That is the one change §5.4 says must not
   be made casually**, and it is named here so that whoever is tempted reads the reason before
   doing it. This is disclosed in the same voice as the `typing.Literal` cost: the boundary costs
   something, and pretending otherwise is how the cost gets paid by widening the boundary.

   **One deliberate hole, and its stated contingency has already materialised.** `compile` is **not**
   refused as an *attribute* name, so that `re.compile` -- which every real slice uses -- keeps
   working; the *builtin* `compile` is refused. The builtin was half of round 2's arbitrary-execution
   route, and what closes that route is the module rule refusing `enum.bltns`, not the absence of
   `compile`. The previous revision of this paragraph warned: "If a future change weakens the module
   rule, this hole reopens." The module rule then failed open in round 4, exactly as written and
   within one round. The hole is still there, and it is disclosed again rather than quietly closed,
   because the thing that guards it is a rule that has already failed once.

   **Property rules and enumerations.** Property rules, which test the thing rather than its
   spelling: the module-reach rule, **two** of the three dunder rules (the attribute rule and the
   string rule), and the module-state rule. Still enumerations, and therefore only as good as their
   lists: the import, attribute-name, reach-primitive, builtin and mutator sets, **and the third
   dunder rule**, which is a ten-name list of hook definitions. An earlier revision of this
   paragraph counted that rule in both groups. The tool's own docstring says the
   same, and says it so that the next author -- who will be tempted to relax a rule to make a slice
   compile -- reads why each rule exists before widening it.

   **A stronger control exists and is not built.** Every rule here reads source; none observes the
   slice running. A `sys.addaudithook` refusing the `exec`, `compile`, `import`, `open`, socket and
   subprocess events would catch by observation what these rules catch by anticipating a spelling,
   and would have caught the annotation route and both import routes without anyone having to think
   of them. Its own limit is that a clock read and entropy consumption raise no audit event. It is
   **not built**, it is recorded in `knowledge/03-Modules/MOD-004/PRE-PRODUCTION-BACKLOG.md`, and
   this record does not claim the benefit of a control that does not exist.

3. **Its unit tests are its whole evidence, and they are real.** Each slice ships unit tests in
   `backend/app/tenancy/domain/tests/**` covering its negative paths, and a negative test must
   actually fail closed rather than merely exist. No mock, fake or in-memory stand-in may be
   presented as evidence of database behaviour, tenant isolation or integration of any kind -- the
   owner's statement 7, and this record does not soften it.

4. **It is reviewed, and the review is the control.** One independent Opus exact-diff review before
   publication, per `OWNER-2026-11-06` §6's review floor, which this record does not lower. Because
   §3.2 is a filter rather than a boundary, this review is not a second opinion on top of a
   guarantee; it is the thing standing between a slice and `main`. A reviewer may not treat a
   passing closure check as evidence that a slice performs no I/O.

5. **It is honest about itself.** Every slice's module docstring states what the code is not: not
   an authenticated principal, not an authorization decision about a real caller, not tenant
   isolation, not a database constraint, not integration evidence.

## 4. What the lane does not permit

The list is not closed, and an item's absence is not permission.

- **No SQL, no migration, no database object.** `backend/migrations/**`, `infra/db/**` and
  `backend/tests/integration/tenancy/**` are **not** lane roots and stay gated by D12 position 4
  and by `OWNER-2026-11-06` §5. Neither is `backend/tests/**`: the lane's tests live inside the
  lane root (§3.1), so no file outside `backend/app/tenancy/domain/**` is written under this
  record at all, and the S0 and MOD-001 tests under `backend/tests/` stay out of reach. Nothing in this record authorizes a migration, a schema, a role, a
  grant, a policy or a function.
- **No capability use, pull or install.** No PostgreSQL, no `psycopg`, no `psycopg_pool`, no
  container, no third-party dependency, and no change to `backend/requirements*.txt` or
  `backend/requirements*.lock`. `OWNER-2026-11-06` §2's pull authority is untouched and its
  condition 1 is unaffected: it is assessed **NOT MET on four limbs** and this record neither
  revisits nor relies on it.
- **No manifest activation and no Ready judgment.** `contracts/engineering/module-capabilities.yaml`
  stays PROVISIONAL with `gate_eligible: false` and the same four OPEN blockers:
  `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME`, `BLK-SKL-MIGRATION-LINT`,
  `BLK-RULE-QUALIFICATION`, `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW`. A slice closes none of them and
  records no CAP, SKL or RULE evidence ID.
- **The lane root sits inside an unqualified Rule's glob, and the S0 precedent did not.** This is
  stated because a reader would otherwise carry the S0 posture forward. `.claude/rules/backend/
  mod004-rls.md` declares `paths: backend/app/tenancy/**`, which covers every lane file on its
  face, and its gates paragraph ends "Without them, S1 code and migrations are not authorized";
  `BLK-RULE-QUALIFICATION` is OPEN and its one-custom-rule-per-gap cap is recorded as reached, so
  the Rule is **promoted but unqualified**. The S0 slice rested on the opposite fact --
  `contracts/engineering/mod004-s0-capability.json` reasons that the S0 paths "are outside both
  path globs" -- so a lane slice is the first MOD-004 code to land **inside** one. The governance
  conclusion, stated rather than left to inference: that Rule's own Authority section says
  "Governing: ADR-0002 ... If this file disagrees with them, they win", so the Rule's bar derives
  from ADR-0002 D12 and is carried by §2's supersession **only to the same extent and no further**.
  Its ten numbered obligations are untouched. Seven of them (1-7) address transaction context,
  RLS, roles, grants, `platform_scope` and cross-tenant leakage, and a pure slice reaches none of
  those surfaces; **obligations 8, 9 and 10 do apply and are not relaxed** -- no invention of
  product behaviour or owner policy, synthetic local data only, and tests are obligations rather
  than evidence. A slice that invents a transition the sources do not state breaches obligation 8
  whatever the closure check says. Nothing here qualifies the Rule, records a RULE evidence ID or
  narrows `BLK-RULE-QUALIFICATION`.
- **No UI-bearing work.** No CON-04, ADM-SET-01, ADM-SET-02 or ADM-SET-06; no screen contract; no
  route. `frontend/**` is not a lane root.
- **No second S0 write.** `backend/app/tenancy_s0.py` and `backend/tests/test_tenancy_s0.py` are
  outside the lane roots and their consumed one-write and one-review limits stand.
- **No acceptance claim of any kind.** See §6.

## 5. Per-slice obligations, and what needs no owner action

**5.1 Repeatable without the owner.** Once this record is effective and §5.3 is done, a slice needs
only: paths inside the lane roots, a passing closure check in CI, the §3.3 tests, the §3.4
independent review, and the ordinary commit, non-force push and green exact-SHA CI. **No further
owner decision, attestation or approval is required for any individual slice**, which is the
owner's statement 5. The orchestrating session selects slices and their order under
`OWNER-2026-11-06` §6's standing delegation of task ordering.

**5.2 The bound is the review, not a counter and not the check.** No slice count, token budget or
attempt allowance is created here, and none is reset. `OWNER-2026-11-06-internal-cap-unmetered.md`
stands as it is. What a slice may contain is a shape -- code whose correctness does not depend on
anything outside its inputs -- and what holds a slice to that shape is §3.4's independent
exact-diff review, with §3.2's check filtering the mistakes first.

An earlier revision of this paragraph claimed flatly that "work that needs the database cannot
enter the lane because the check refuses it". Three independent reviews falsified that claim in
succession, each after it had already been narrowed. **It is not narrowed a fourth time; it is
withdrawn.** The check refuses every route it knows of, over the files its walk enumerated, and
every proved route is closed and pinned by a test -- and that is a statement about a program that
the authors of lane files can edit, not a containment guarantee. **A reviewer of a slice may not
treat a passing closure check as evidence that the slice performs no I/O. The check is the filter;
the review is the finding.**

**5.3 The lane does not open until the check and the slice tests both run in CI.** A filter nobody
runs filters nothing. `.github/workflows/veyro-foundation-ci.yml` must run, on every push to
`main` and before the first slice is written: the closure check over the published tree, the
`tools/domain_closure` unit suite, and the lane's own tests via
`python3 -m unittest discover -s app/tenancy/domain/tests -t .` from `backend/`. The third is not
optional dressing -- §3.3 makes a slice's unit tests its entire evidence, so tests that no
automated run exercises are not evidence. That
is a CONTROLLED path and therefore needs an **accepted ADR** citing ADR-0001 for its own file, with
its own independent review and the `check-change` gate run and shown; it is not authorized by this
record and is the orchestrating session's to publish under its existing delegated authority
(statement 3). Until it is green on an exact SHA, the lane is closed and the check reports any file
under a lane root as `LANE_NOT_EFFECTIVE`.

**5.4 Extension to later modules is delegated to an ADR.** The lane's mechanism is module-agnostic;
this record activates it for **MOD-004 only**. Adding a lane root for another module is an accepted
ADR citing ADR-0001, with its own review, and must keep §3's closure and §4's exclusions
unchanged. **No new owner record is needed per module**, which is the owner's statement 2. An ADR
may not widen §3.2's allowlist, add a lane root that is not a pure sub-root, relocate a lane's
tests outside its own root, or reach any path §4 excludes; doing any of those needs a new owner
record. The allowlist is named here specifically: §3.2 records that the shortness of the four-module
list is doing work no rule does, so adding a module is a change to the boundary and not a
convenience.

## 6. Honest status: what a slice is never evidence of

Stated as its own section because the owner's statement 4 names it and statement 7 bars the
opposite.

- **Not tenant isolation.** Isolation is enforced by PostgreSQL row-level security, which this lane
  cannot write and does not evidence. The D3 trust statement, the D6.6 failure tests (21), the D9
  cross-tenant fuzz and the release-gate isolation layers stay **OPEN and required**. A passing
  slice is not isolation evidence, and may not be described as one.
- **Not authentication or authorization of a real caller.** A slice may implement and test
  authorization *policy evaluation* as a pure function of its inputs. It establishes no
  authenticated principal, satisfies no AAL-3 requirement, and MOD-007 and MOD-008 remain required
  and remain dependencies this record does not resolve.
- **Not data integrity.** Pure validation is not a database constraint. Keys, foreign keys, RLS
  policies and the FORCE RLS requirement stay required.
- **Not database integration.** No slice, and no quantity of slices, may be reported as database
  integration, as Implementation Complete, or as any part of production readiness.
- **Not module acceptance.** MOD-004 is not Ready and is not accepted. MOD-005 stays locked until
  MOD-004 is accepted. MOD-001, MOD-002 and MOD-003 stay conditional Foundation-scope acceptances
  and `GOV-02-R01..R08` keep `product_pass: false`. **Scenario Review stays BLOCKED** by the
  Appendix F ¶8741 count/route/contract lint; OWNER-Q1 and OWNER-Q2 are not answered here.

## Reserved and unchanged

The list is not closed, and an item's absence is not delegation of it.

- **The four DC-16 reserved actions** — `spend-paid-activation`, `production-promotion`,
  `material-product-business-change`, `real-member-data`.
- **Module acceptance for every module, and the MOD-005 unlock.** An agent never decides module
  acceptance.
- **All UI-bearing MOD-004 work**, the D14 screen-ownership mapping review, finding **F3**, and the
  ADM-SET-06 domain-authority conflict. `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW` stays OPEN.
- **The frozen baseline** — `PROJECT_INDEX.md`, the three `.docx` files,
  `veyro-product-experience-design/` — and every `OWNER-*` path.
- **Publication of any `OWNER-*` record, including this one.** The attestation checks in
  `governance_check.py` are not weakened, narrowed or bypassed by this record or by the change that
  publishes it.
- **Amending ADR-0001**, and weakening the validator's Reserved-Action, Owner-Approval,
  frozen-path, self-authorization or first-publication checks.
- **Product security**, binding and unchanged: tenant isolation and RLS, authentication and AAL-3,
  immutable audit, financial integrity, residency and retention, independent product review,
  validation at trust boundaries that fails closed, and negative tests that actually fail closed.
  No test is deleted or weakened because it fails.
- **Regions, data-residency policy and KMS keys; retention durations, deletion approvers and
  quorum; hierarchy cardinalities, brand separation extent and template contents** where the
  Blueprint is silent.
- **Whether the two D16 correction cycles survive the 2026-10-30 infrastructure failure.** Not
  resolved, not re-counted. No root is renamed to obtain a consumed attempt.
- **Credential administration, worker identity and sudoers.**
- **The retired runner.** Not restarted, repaired, rebuilt or replaced. Claude Code stays the sole
  repository writer; GitHub Actions stays CI/CD only and authorizes nothing.
- **Every consumed limit**, including the S0 one-write and one-review limits.

## Preserved

Historical review outcomes stand and are never rewritten, softened, superseded or reinterpreted by
this record: the MOD-004 D16 lineage's four recorded `CHANGES_REQUESTED` reviews, the two
screen-ownership `CHANGES_REQUESTED` reviews, the 2026-11-02 ¶8740 justification review with
findings F1-F8, the two `CHANGES_REQUESTED` reviews recorded during the 2026-11-05 authentication
migration, and the **three `CHANGES_REQUESTED` reviews of the D5 static migration lint** -- the
two recorded in ADR-0007 D2.1, demonstrating 29 false negatives between them, and the 2026-11-07
round-three review recorded in `knowledge/03-Modules/MOD-004/PRE-PRODUCTION-BACKLOG.md` §3b, which
proved four further undisclosed false negatives by execution against the post-remediation bytes,
two of them complete tenant-isolation bypasses. An earlier revision of this sentence said "two"
and called the second remediation unreviewed; both were wrong, and a review of these bytes caught
it. The project record is split on the count -- ADR-0007 D2.1 still says two and the backlog's §3
table still reads "no reviewer has seen" -- and this record takes the **higher** number, because
the Preserved section exists so that no standing outcome is softened. `ADR-0007` stays `PROPOSED`
and `BLK-SKL-MIGRATION-LINT` stays OPEN. The **four
`CHANGES_REQUESTED` review rounds against the closure check** stand as §3.2's table records them,
including that each round's remedy supplied part of the next round's route; none is softened, and
the table is not to be reduced to a count. The
2026-10-30 D16 dispatch stays recorded as consumed on `attempts: 1 / max_attempts: 1`, failed on an
infrastructure fault, producing a draft that was never reviewed and is not an approval. The
exhausted 45-minute / 50,000-token envelope, the recorded 427,621 of 400,000 tokens with its 27,621
overrun, and the UNKNOWN earlier usage stay recorded as history.

## 7. Publication and proof — the one manual step

**Obligation 0, which earlier revisions left out.** **Every other change in the working tree is
committed and pushed first**, so that the tree holds nothing but this record when obligation 4
runs. That is `tools/domain_closure/**` -- not a controlled path, so it needs no ADR -- together
with any other edit outstanding at the time, such as the `PRE-PRODUCTION-BACKLOG.md` correction
published alongside the tool. Two reasons it cannot wait: obligation 4 requires the record to be
the only change in an otherwise clean tree, and `check_first_publication` refuses unless
`git status --porcelain --untracked-files=all` holds exactly one entry -- so an untracked tool
directory *or* a tracked modification elsewhere returns `FIRST_PUBLISH_BLOCKED`; and obligation 2's
`expected_head` is compared against the then-current `HEAD`, so the owner's single manual step must
be taken **after** those commits, against a `HEAD` that already carries the check this record
conditions the lane on. A first review established both by reading the validator; a second caught
that the obligation named only the tool while a tracked edit sat in the same tree, which would have
reproduced the exact block the obligation exists to prevent. The requirement is therefore stated
over the whole tree, not over a list of paths.

Then five obligations, in order; a later one does not substitute for an earlier one. **Only
obligation 2 is the owner's**; the rest are the orchestrating session's.

1. Independent exact-subject Opus review of the exact bytes of this file.
2. **The owner's single manual action.** Once the reviewed bytes are final, the owner writes the
   first-publication attestation outside the repository: a JSON object with exactly the keys
   `schema`, `owner_id`, `source`, `owner_choice_quote`, `source_prompt_message_id`,
   `record_path`, `record_sha256` and `expected_head`, all strings, with
   `schema` = `veyro.owner-attestation/1`, `owner_id` = `gateway-owner`,
   `source` = `owner:direct:admin-attested`, `record_path` =
   `knowledge/00-Decisions/OWNER-2026-11-07-local-domain-slice-lane.md`, `record_sha256` the
   SHA-256 of this file's exact bytes, and `expected_head` the then-current `HEAD`. The file must
   be owned by uid 0 and writable by neither group nor others, so it is written under admin
   authentication. `owner_choice_quote` and `source_prompt_message_id` must be the owner's own; an
   agent never supplies or infers them, which is why this step cannot be delegated.
3. The local checks in `CLAUDE.md`, each as a separate command, with real output reported.
4. `check-change` in first-publication mode: this record staged as the **only** change in an
   otherwise clean tree, its path piped on stdin, `--decision
   OWNER-2026-11-07-local-domain-slice-lane` and `--first-publish-owner-attestation <file outside
   the repository>`. Any result other than PASS stops publication.
5. One commit containing only this file, a non-force push to `main`, and a completed `success`
   push-event CI run on that exact SHA. Then §5.3, which has its own review and CI.

The attestation is an operator-held statement, not cryptographic proof of the owner's message, and
a PASS records that statement and nothing stronger. Any later change to these bytes voids the
review and the attestation and repeats both.

## Not claimed

- Not module acceptance, not module Ready, not a capability activation, not a Scenario Review PASS,
  not a Gatekeeper verdict, not a security PASS, not a product PASS, not manual-QA or TestSprite
  evidence.
- Not satisfaction of EIP ¶773, which is addressed in §2 rather than claimed.
- **Not a sandbox, not execution containment, and not a proof of purity.** The closure check is a
  mistake filter over source files, editable by the same authors it judges, and §3.2 sets out what
  it does and does not reach. No supersession here rests on it being more than that.
- Not a claim that every escape route is known or counted. §3.2 records that the totals in earlier
  revisions disagree and leaves the disagreement standing.
- Not closure of any manifest blocker, and no CAP, SKL or RULE evidence ID.
- Not a finding that `OWNER-2026-11-06` §2 condition 1 is met; it is assessed NOT MET on four limbs
  and this record does not touch it.
- Not authority for any S1 database work, migration, SQL, dependency, pull, install, container, UI
  surface or controlled-path change.
- Not approval of any DC-16 reserved action, and not authority over any frozen path.
- Supersedes no review outcome and resets no counter. The one supersession it makes — ADR-0002 D12
  positions 2 and 4, for the §3 class only — is stated in §2 and is limited to what §2 says.
