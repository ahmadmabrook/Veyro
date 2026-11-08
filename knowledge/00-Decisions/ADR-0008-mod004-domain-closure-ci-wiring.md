# ADR-0008 — Run the local-domain-slice closure check and the lane's own tests in CI

- ID: ADR-0008
- Status: ACCEPTED
- Review: VR-ADR0008-20261108-007 APPROVED
- Decision-Key: mod004-domain-closure-ci-wiring
- Covers: .github/workflows/veyro-foundation-ci.yml

**Scope and limits.** This ADR authorizes exactly one controlled-path change: three steps added to
`.github/workflows/veyro-foundation-ci.yml` and two existing steps amended, so that the three
commands `OWNER-2026-11-07-local-domain-slice-lane.md` §5.3 names actually run on every push to
`main`. It is the §5.3 ADR that record says is "the orchestrating session's to publish under its
existing delegated authority", and §5.3 is the only thing it discharges. It authorizes **no product
code**: the lane's authority to write a slice comes from the owner record, not from here, and this
ADR neither widens nor narrows §3's closure, §4's exclusions or §6's bar on citing a slice as
evidence. It closes **no manifest blocker** — `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME`,
`BLK-SKL-MIGRATION-LINT`, `BLK-RULE-QUALIFICATION` and `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW` all
stay OPEN — records no CAP, SKL or RULE evidence ID, does not make
`contracts/engineering/module-capabilities.yaml` ACTIVE, does not judge MOD-004 Ready, is not module
acceptance, is not a Scenario Review PASS, is not a product PASS, satisfies no part of
PLT-01-R01..R07, approves no DC-16 reserved action and reaches no frozen path. It adds no
dependency, no database service, no container and no network call to CI.

**ACCEPTED, and operationally conditional.** This ADR's acceptance takes operational effect only
once its own independent exact-diff review is recorded and the exact-SHA push CI of its publishing
commit succeeds — Next-gate items 2 and 3 — which is the form ADR-0001 and ADR-0005 use for the
same situation. Until then the `ACCEPTED` status states an intent about these bytes and discharges
no part of §5.3, and nothing it authorizes is operative on a red or absent CI run. The exposure that
makes this worth writing rather than assuming, named by a review of the previous bytes:
`check-change --decision ADR-0008` over the workflow returns `PASS` from the moment this file is
`ACCEPTED` on disk, before items 3 and 4 exist, so **the validator will not hold the sequence** —
this paragraph and `CLAUDE.md` step 6 are what do.

**Review header: what it refers to, and what carries no tick.**
**`VR-ADR0008-20261108-007` is a document-assigned label**, not an identifier any artifact carries.
It labels the independent Opus review, commissioned by the orchestrating session on 2026-11-08, of
the exact bytes of this file together with the exact workflow diff it authorizes. The detector half
of that same second commit -- `tools/domain_closure/**`, which needs no ADR -- carried its own
separate independent review on the same date, and both reviews' outcomes will be recorded in
the publishing commit messages rather than in this header, which labels one of them. The label was
written into these bytes **before** that verdict returned, because a review of bytes that do not yet
include their own header is a review of different bytes. What makes that honest rather than a
back-dated claim is a publication rule and not a disclosure: **had the verdict been
CHANGES_REQUESTED these bytes would not exist in history** — the file would have changed, the label
would have taken the next number, and the review would have been repeated.

**Earlier labels are spent, and the review history is not narrated here.** Every earlier label
belongs to a round whose verdict stands recorded rather than erased, including a first round in
which both independent reviews returned **CHANGES_REQUESTED**. **No earlier approval is carried
forward**: each was voided by the edit that followed it, and none was given on these bytes. Every
round's label, subject hashes and outcome, and the defects each round found, will be recorded in the
publishing commit message, which is where history belongs and where a later reader can check it
against bytes rather than against prose.

**The Next-gate checklist below ticks nothing**, deliberately: a `[x]` in this repository's
convention asserts a completed fact with the commit it was done in, and no item of it can be true
before the commit that publishes this file exists. Reviews since the runner's retirement leave no
artifact — no `*.evidence.json`, no run identifier, no `review_bound_verified` field — so the
review's performance, its performer and the reviewer's lack of write tools are **asserted here and
are not independently verifiable**, while the bytes it covered are verifiable by hash at this
file's publishing commit. The governance
validator checks only the id's format (`^[A-Za-z0-9._-]{3,64} APPROVED$`) and never confirms that a
review exists, so the format passing is not evidence. Any later edit to these bytes is new bytes
needing its own review and its own exact-SHA CI, and none is claimed.

**Authority path, and why the publication is split in two.** The standing authority for this file is
ADR-0001 (ACCEPTED, key `governance-foundation-change-control`), which `Covers`
`knowledge/00-Decisions/` and is not part of this change. This ADR cannot authorize its own file:
`check-change` returns `CHANGE_SELF_AUTHORIZING` when the cited ADR is in the pipe. So this file is
published first citing ADR-0001, and the workflow change follows citing ADR-0008. **The split is a
choice, not a mechanical necessity, and the difference matters**: ADR-0001's `Covers` also includes
`.github/workflows/`, so a single commit carrying both paths would pass the gate under
`--decision ADR-0001`. What forces a dedicated ADR is §5.3's own words — the controlled path "needs
an **accepted ADR** citing ADR-0001 for its own file" — and citing ADR-0008 for the workflow is what
makes this file that ADR rather than a document ADR-0001 happened to permit. Publishing an ADR ahead
of its implementation is the ADR-0004 pattern: sequencing inside one authority, not a second
authority.

## Context

**What §5.3 requires.** The lane does not open until the closure check and the slice tests both run
in CI: "A filter nobody runs filters nothing." The record names three commands that
`.github/workflows/veyro-foundation-ci.yml` must run on every push to `main` and before the first
slice is written — the closure check over the published tree, the `tools/domain_closure` unit suite,
and the lane's own tests via `python3 -m unittest discover -s app/tenancy/domain/tests -t .` from
`backend/`. The third is not dressing: §3.3 makes a slice's unit tests its entire evidence, so tests
no automated run exercises are not evidence.

**Why the lane record cannot authorize this itself.** `.github/workflows/` is a `CONTROLLED` prefix
in `tools/governance/governance_check.py`, and a controlled path resolves through
`CONTROLLED_CHANGE_UNREFERENCED`, which requires an ADR and rejects an `OWNER-*` stem. The owner
record says so in its own §5.3 and deliberately carries no `Covers` header for that reason.

**State of the published tree, which is not the state of the working tree.** An earlier revision of
this paragraph described the uncommitted detector as though it were published, and an independent
review falsified it by running the committed one. The published facts: the owner record is committed
(`40cee0d`) with exact-SHA push CI run `42404811130` completed `success`, and its §7 obligations are
recorded in that commit's message, including the first-publication attestation at
`/usr/local/veyro/lane-attestation.json`. At `HEAD` (`0702c6e`) the committed
`tools/domain_closure/domain_closure.py` contains **no wiring detector at all** — no
`REQUIRED_CI_STEPS`, no `_ci_wiring_present`, no `lane_effective()` helper — the bare name is there as
`check()`'s parameter and output key, which is why this sentence names the helper rather than the
name — and reports
`lane_effective: true` on the strength of the record alone. **So the published repository fails open
against §5.3 today**: §5.3 says "Until it is green on an exact SHA, the lane is closed and the check
reports any file under a lane root as `LANE_NOT_EFFECTIVE`", and the published tool would tell a
slice author the opposite. That is a defect in `main`, it is stated here rather than discovered
later, and the commit this ADR authorizes is what closes it.

**Where the detector change lands, and why not earlier.** `tools/domain_closure/**` matches no
`CONTROLLED` or frozen entry, so it needs no ADR and `check-change` judges nothing over it — a
`PASS` on those paths alone is vacuous and is not cited as evidence of anything. It is nonetheless
part of the same commit as the workflow, for a reason a review proved by execution: the suite pins
the real workflow file, so a tree carrying the detector without the wiring has a **latently red**
`tools/domain_closure` suite, invisible only because the step that runs it does not exist yet. Two
commits, each internally consistent, rather than three with a failing suite in the middle. Stating
where an uncontrolled change lands follows the owner record's own §7 obligation 0, which exists
because an unstated edit elsewhere in the tree reproduced the block it was meant to prevent.

## Decision

**D1. Three steps added, two amended.** In the single `veyro-foundation-ci` job, which keeps
`permissions: contents: read` and its `push` to `main` trigger unchanged:

1. **Amended** — `tools/domain_closure` appended to the existing `python -m compileall -q` step.
2. **Added** — `python tools/domain_closure/domain_closure.py check --root .`, placed with the other
   governance checks and before any dependency install, because the tool is stdlib-only.
3. **Added** — `python -m unittest discover -s tools/domain_closure/tests -t tools/domain_closure -v`,
   immediately after it.
4. **Added** — the lane's own tests, `working-directory: backend`, as
   `python -B -m unittest discover -s app/tenancy/domain/tests -t . -v`.
5. **Amended** — `-B` added to the existing "Backend focused tests" step, for the reason in D2.

**D2. `-B` is required, and it is a strictening beyond §5.3.** §5.3's literal command omits it.
Without it, a `discover` run over the lane writes `__pycache__` into the lane root, and the closure
check refuses `__pycache__` as `PYCACHE_IN_LANE`. **Where that bites is local runs and the
detector's own requirement, not a single CI run**: each CI run is a fresh checkout and the closure
check executes before the lane-test step, so within one run the step could not fail the check that
admits the slice. An earlier revision of this paragraph claimed it could, and a review corrected it
by reading the step order. `tools/domain_closure/domain_closure.py` therefore requires a
bytecode-suppression spelling on every line carrying the lane command, and accepts a deliberately
narrow two-entry list (`" -B "`, `"PYTHONDONTWRITEBYTECODE=1"`); correct spellings it refuses —
clustered `-Bm`, the quoted `="1"`, and `=2`, `=yes`, `=true`, `=-1` — close the lane rather than
open it. Step 5 exists because the backend step runs **after** the closure check and, once a slice
exists, a backend test importing a lane module would write `__pycache__` into the lane behind an
already-passed check. Clean checkouts make that local-only; it costs two characters to close and is
closed. Three immaterial departures from §5.3's literal text, named so they are not found later as
discrepancies: `python` rather than `python3` (the `setup-python` interpreter), `-v`, and `-B`.

**D3. The lane-test step is guarded on the directory existing, and that is a deviation stated rather
than hidden.** `unittest discover` on a missing start directory exits non-zero, so an unguarded step
would redden `main` on this very commit, before any slice exists — and the obvious way to green it
again would be deleting the step. The step therefore runs the command when
`backend/app/tenancy/domain/tests` is a directory and prints a line saying the lane is empty
otherwise. What keeps the guard from becoming a hole is not this ADR and not the closure check: the
`tools/domain_closure` **suite** fails when lane source exists with its tests removed, naming §3.3
verbatim, and that suite is wired unconditionally. Verified by execution in a throwaway clone by two
independent reviews and by the orchestrating session; the closure check alone returns `PASS` on that
state and does not catch it.

**D4. Nothing else in the workflow changes.** No new trigger, no permission widening, no secret, no
service container, no `continue-on-error`, no job. The existing known gaps stay as they are: the
`SeatbeltTests` in `tools/mission_runner/tests/test_runner.py` still skip off macOS so CI does not
cover that OS-boundary isolation path, `check-complete` for the 1530 per-screen contract fields
stays a visible failing gate deferred to the owning product modules by the owner's 2026-10-15
decision, and `check-change` is still not run by CI.

## Consequences

**What a green run of these steps proves, stated narrowly.** That the closure check returned PASS
over the files its walk enumerated in the published tree; that the `tools/domain_closure` suite
passed; and, once a slice exists, that the slice's own unit tests passed under the command §5.3
names. Nothing more.

**What it does not prove, and the tool says so in its own output.** The detector's
`lane_effective_basis` is a substring test over the committed workflow with line-leading comment
lines dropped. It does **not** verify that the three commands sit in steps that run, nor that a
failure of them gates: a step carrying `if: false`, an unreachable job, an `echo` of the same string
and a trailing `#` comment on a `run:` line all match without running, and a trigger changed away
from push-to-main, `continue-on-error: true` on every step and a workflow that is not valid YAML at
all match without gating. It does **not** verify that any CI run of them was green on an exact SHA.
Establishing reachability needs a YAML parser and a judgment; establishing a green run needs the
network, which the tool must not touch. `workflow_check.py` is what independently pins the
push-to-main and read-only shape, and D4 is what bars `continue-on-error`. Both halves stay human
obligations discharged per commit by reading `gh run list --commit <sha>`. `pass_means` in every
result keeps the sharper limit in view: a PASS is evidence that an author did not make one of the
mistakes the rules cover, **not** evidence that a file performs no I/O, and never evidence of
correctness, tenant isolation, authentication, authorization, data integrity or database
integration.

**§5.3 is discharged for two of its three commands, and for the third only in part.** §5.3 asks for
the lane's tests to run "on every push to `main` **and before the first slice is written**". D3's
guard makes the second half unreachable: until a slice exists there is nothing to discover, so the
third command's first real execution is the first slice's own commit. The detector cannot tell a
guarded step from an unguarded one, because it is a substring test. So the lane opens on the wiring
commit on the strength of the first two commands running and the third being wired, and this ADR
claims that and not full discharge. An earlier revision claimed discharge flat; a review caught it.

**A green lane step is not evidence that a slice is tested.** The suite's §3.3 guard tests that a
file named `test*` **exists** under the tests root, not that it exercises anything: a stub whose
only assertion is `assertTrue(True)` satisfies both the guard and the lane step. §3.4's per-slice
independent review is the stated control for that, and D3's claim is about *deleted* evidence, which
holds. Recorded so that no one later cites a green lane step as evidence of coverage.

**The check's own file is not controlled, and this ADR does not change that.**
`tools/domain_closure/**` matches no `CONTROLLED` or frozen entry, so no ADR, owner record or
validator stands between a slice's author and the rules that judge them. The owner record's §3.2
says this plainly and rests its supersession on §3.3's tests and §3.4's per-slice independent review
instead. Wiring the check into CI makes it harder to bypass silently — a weakening edit now shows up
as a diff in a run everyone sees — and that is the whole of the improvement claimed. The detector
change in this commit also closes a loosening the first review round found in it: both of its git
reads were spelled `HEAD:<path>`, which git resolves against the repository top level, so any
`--root` below that level read an ancestor's commits and reported the lane **open** for a tree where
neither the record nor the workflow existed. Both are now `HEAD:./<path>`, and a test pins it.

**Scope creep this ADR refuses.** Adding a lane root for another module, widening §3.2's four-module
allowlist, relocating a lane's tests outside its own root, or reaching any path §4 excludes are each
outside this ADR; the first is a later ADR under §5.4 and the other three need a new owner record.

## Next-gate checklist

Nothing here is ticked. Each item is a gate, and the evidence for one goes in the commit message
that discharges it, in the form `OWNER-2026-11-07`'s §7 and ADR-0005's checklist use.

1. [ ] This file published citing ADR-0001 and not itself, with real output: the pipe under
   `--decision ADR-0008` must return `BLOCKED` / `CHANGE_SELF_AUTHORIZING`, the publishing pipe must
   cite ADR-0001 and return `PASS`, and a negative control on a deliberately wrong accepted ADR must
   return `BLOCKED`.
2. [ ] Independent Opus review of these exact bytes and the exact diff they authorize, returning
   APPROVED under the label in the `Review` header. Performance and performer asserted, not
   evidenced; see the review paragraph under Scope and limits.
3. [ ] Non-force publication of this file and a `success` push-event CI run on its exact SHA.
4. [ ] Non-force publication of the workflow and detector change citing ADR-0008, and a `success`
   push-event CI run on **that** exact SHA. A green run on this ADR's own SHA proves nothing about
   the wiring, which is not in it.
5. [ ] After item 4, `domain_closure.py check --root .` reports `lane_effective: true` with the
   basis naming both halves, and the §5.3 fail-open recorded above under "State of the published
   tree" is closed. Until then, any file under a lane root is `LANE_NOT_EFFECTIVE`.
