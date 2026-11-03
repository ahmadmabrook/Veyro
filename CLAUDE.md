# Veyro — project instructions

Claude Code is the development environment for this repository. GitHub Actions does CI/CD and
nothing else: it never starts, authorizes or gates execution.

## Canonical sources

Four owner-selected baselines, pinned by SHA-256 in `PROJECT_INDEX.md`:

| Source | Governs |
|---|---|
| `Gym_OS_Master_Product_Blueprint_v1_English.docx` | product scope |
| `Veyro_Technical_System_Design_v1.4.2_Foundation_Clarification.docx` | architecture and invariants |
| `Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx` | module sequence and gate definitions |
| `veyro-product-experience-design/` | interaction contract |

Verify the relevant hash before writing anything derived from them (`tools/governance/source_baseline.py`);
fail closed on mismatch. These identify owner-selected baselines — they do not prove independent
certification. EIP references to v1.4.1/v1.4.0 and the LF-01 "review candidate" notice are legacy text.

Engineering decisions live in `knowledge/00-Decisions/` (ADR-0001..0005 and the `OWNER-*` records).
Module documents live in `knowledge/03-Modules/`. Read the decision before changing what it covers.

## Module state

- **MOD-000** accepted (Lean Foundation).
- **MOD-001, MOD-002, MOD-003** are **conditional Foundation-scope acceptances, not operative
  module acceptance**, and must not be described as accepted without that qualifier. Each module
  header states its own unmet condition: MOD-001 and MOD-002 record their activation commit's CI as
  not claimed, and MOD-003 is `S1 FOUNDATION ONLY` pending CI, an activation-diff review and a
  verified receipt. MOD-001 and MOD-002 have an `APPROVAL.md`; MOD-003 does not. Never product PASS:
  MOD-002's GOV-02-R01..R08 are `FOUNDATION` with `product_pass: false`.
- **MOD-004** is the current module: **not Ready, not accepted**, at the documents/ADR gate.
  PLT-01-R01, R02 and R04..R07 are OPEN; R03 is "mapped (PostgreSQL only)" with its events, jobs,
  search, storage, telemetry and AI parts OPEN. All seven release-gate isolation layers are
  unevidenced. One narrow slice is published: `backend/app/tenancy_s0.py` plus its tests — pure
  `ProvisionTenant` envelope validation, no I/O, no authorization, no tenant isolation.
- **MOD-005** stays locked until MOD-004 is accepted. MOD-006..MOD-074 not started.

## Development workflow

1. Read the governing decision and the module document first.
2. Smallest reviewable change. Match the surrounding code's naming, idiom and comment density.
3. Run the local checks below.
4. Independent Opus review of the exact diff before it is published.
5. Commit, then push to `main` without force. No history rewrite, no branch deletion.
6. Confirm GitHub Actions is green on the published commit. If it fails, repair forward or revert —
   never force-push — and do not stack more work on a red `main`.

Steps 4 and 6 are **procedural, not mechanical**: branch protection enforces `enforce_admins` and
blocks force-pushes and deletions, but has no required status checks and no required reviews. The
review happening is a discipline, not a gate that stops you.

Owner-reserved (DC-16): `spend-paid-activation`, `production-promotion`,
`material-product-business-change`, `real-member-data`. Never taken by an agent, never inferred.

## Change control

`tools/governance/governance_check.py` treats these ten `CONTROLLED` entries — four directory
prefixes (each covers everything beneath it) and six exact files — as controlled; changing any of
them needs an accepted ADR that `Covers` it:

```
.github/workflows/        governance/        knowledge/00-Decisions/        tools/governance/
tools/mission_runner/{workflow_check.py, runner.py, acceptance_receipt.py, control.py,
                      veyro-ctl, module_catalog.json}
```

ADR-0002 additionally calls `contracts/engineering/**` a controlled contracts change (accurate, but
not enforced by the validator). `knowledge/03-Modules/MOD-004/MOD-004.md` is **not** controlled.
The frozen baseline — `PROJECT_INDEX.md`, the three `.docx`, `veyro-product-experience-design/` —
changes only under an `OWNER-*` record, and ADR-0001 says standing ADR authority can never
authorize it. Every `knowledge/00-Decisions/OWNER-*` path is frozen too: although ADR-0001 `Covers`
lists the `knowledge/00-Decisions/` directory, the validator unions any such path into the frozen
set and excludes it from the controlled one (its own comment: "never authorizable by an ADR"), so
ADR coverage never applies to it. Piping one with `--decision ADR-0001` returns `BLOCKED` /
`FROZEN_BASELINE_CHANGE` with the detail `--decision must be an OWNER-* record`.

`check --root .` is a static structural check and is **not** a change-control gate. After an ADR is
accepted, run the gate itself before pushing. It reads the changed paths from **stdin**, so it must
be piped — given none it returns `MALFORMED` / `CHANGE_PATHS_EMPTY` and exits 2:

```bash
{ git diff --name-only HEAD; git ls-files --others --exclude-standard; } | \
  python3 tools/governance/governance_check.py check-change --root . --decision <ADR-ID>
```

Both halves matter. `git diff --name-only HEAD` omits untracked files, and the gate judges only
what is piped — so a new file under a controlled path (publishing an ADR is exactly this) would go
unexamined and the gate would report `PASS`. Stage first and use
`git diff --name-only --cached HEAD` if you prefer.

The gate also does nothing for a path that matches no controlled or frozen entry. A pipe holding
only such paths — `CLAUDE.md`, say — returns `PASS` while judging nothing, whatever `--decision`
says: a well-formed but nonsense id such as `NONSENSE-not-a-real-decision` still gives `PASS`, exit
0 (only a malformed id is refused, as `DECISION_INVALID`). Never cite that `PASS` as evidence that a
change was examined. Confirm the pipe actually contained a controlled path, and run a negative
control: repeat with the same pipe and a deliberately wrong `--decision`, which must come back
`BLOCKED`; if it still says `PASS`, nothing was checked.

It blocks with `CHANGE_ADR_NOT_COVERING` when the cited ADR does not cover a controlled path,
`FROZEN_BASELINE_CHANGE` when the change touches the frozen baseline (which needs an `OWNER-*`
record, never an ADR), `CHANGE_SELF_AUTHORIZING` when the cited ADR is itself part of the change,
and `CHANGE_ADR_INVALID` when any ADR in `knowledge/00-Decisions/` has an integrity fault — however
unrelated to your change, a malformed header in an unrelated ADR included: every such fault is
promoted into a block on every controlled change until it is fixed. These four are the ones you
will hit; the list is not closed.

**ADR header trap.** An ADR's header is every `- Word: value` line before the first `## ` heading:
`HEADER_RE` is `^- ([A-Za-z][A-Za-z-]*):[ \t]*(.*?)[ \t]*$` and the parse loop stops only at a line
starting `## `. So a bullet such as `- Note: …` anywhere in that stretch is read as a header and
fails as `unknown header Note`, a repeated header fails, and an empty `Covers:` fails as
`missing header Covers`. Any of these reddens `check --root .` in CI and, through
`CHANGE_ADR_INVALID`, blocks every later controlled change. Write prose between the header block
and `## Context` as bold paragraphs, never `- Word:` bullets. Copy the header block from an
existing ADR; `check --root .` names anything missing or unknown. `Review` is required only for
`Status: ACCEPTED`, must read `<id> APPROVED`, and is **format-checked only**: the validator never
confirms the named review exists.

Amending an **ordinary** ADR is one commit: cite ADR-0001, which covers
`knowledge/00-Decisions/` and is not part of your change. Only **ADR-0001 itself** cannot be cited
for its own file — amending it follows the two-commit bridge-ADR procedure in ADR-0001's own
"Rollback and amendment" section, which requires a bridge ADR with a *different* `Decision-Key`.
Read that section rather than improvising. Separately, where an ADR says to publish itself before
its implementation (ADR-0004 does), that is sequencing within one authority, not this rule.

Publishing a **new** `OWNER-*` record has exactly one lane, since such a record can neither be
authorized by an ADR nor cite itself. Pass `--decision` the new record's own `OWNER-*` stem
together with `--first-publish-owner-attestation <file>`, as the only added path in an otherwise
clean tree. The attestation is an owner-and-operator-held JSON file outside the repository; it
requires the owner's own choice quote and chat message id, which an agent never supplies or infers,
so this lane cannot be completed without the owner. The validator's docstring calls it an
operator-held statement, not cryptographic proof, so a `PASS` records that statement and nothing
stronger. Refusals come back `FIRST_PUBLISH_BLOCKED`; `check_first_publication` holds the exact
field and tree-state rules.

## Responsibilities

| Agent | Model | Role |
|---|---|---|
| `veyro-architect` | Opus | planning, architecture, decision drafting — proposes only |
| `veyro-implementer` | Sonnet | implementation and tests inside a stated file allowlist |
| `veyro-reviewer` | Opus | independent exact-diff review; emits a verdict, fixes nothing |

Architecture and acceptance decisions stay with the orchestrating session and the owner. An agent
never decides module acceptance. The architect and reviewer have no `Edit` or `Write` tool, but all
three have `Bash`, so their write-abstinence and the implementer's "never commit or push" are rules
they follow, not limits imposed on them.

Reviews performed since the runner's retirement leave no artifact. Unlike the archived 2026-10
runner runs, they produce no `*.evidence.json` and carry no `review_bound_verified` field, so a
review's bytes are verifiable by hash while its performance, its performer and the reviewer's lack
of write tools are only asserted. A `Review:` header id is a document-assigned label unless an
artifact carries it, and must be disclosed as such (ADR-0005's `VR-ADR0005-20261103-001` does).

Claude Code is the sole repository writer. Never start a second one, and never restart or rebuild
the retired runner (below).

## Product security and testing

Binding and unchanged: tenant isolation and RLS, authentication and AAL-3, immutable audit,
financial integrity, residency and retention, and independent product review. Validate input at
trust boundaries and fail closed. Negative tests must actually fail closed, not merely exist.

MOD-004 code beyond the published S0 slice needs the module Ready and the EIP ¶754 capability
manifest ACTIVE. Neither is true: `contracts/engineering/module-capabilities.yaml` is PROVISIONAL
with `gate_eligible: false`, and its CAP, migration-lint, Rule and privileged-console blockers are
OPEN. Documentation and design are legal now (ADR-0002 D12); product code is not. Per
`OWNER-2026-10-29-minimal-local-runner-architecture.md`, **no CAP task is eligible without a new
owner envelope** and the outstanding pre-pull and security decisions — no CAP budget was reset.

Add no third-party dependency. `tools/`, `backend/app/l10n/` and the S0 slice are stdlib-only and
must stay that way; `backend/app/main.py` already uses FastAPI, declared in
`backend/requirements.txt` and pinned in `backend/requirements.lock` — existing approved scope,
not a violation to "fix".
Do not pull or install PostgreSQL, `psycopg` or `psycopg_pool`. The S0 paths enforce the forbidden-import
closure in `contracts/engineering/mod004-s0-capability.json`.

## GitHub CI/CD

One workflow: `.github/workflows/veyro-foundation-ci.yml`, on push to `main`, `contents: read`. It
compiles, checks the workflow shape, runs the mission_runner, governance and trusted_gate suites,
the runner fail-closed and source-binding negative checks, the screen-contract identity check, and
then lints, type-checks, tests and container-smokes `backend/`.

To confirm a push is green, list the runs for that exact SHA and read `conclusion`:

```bash
gh run list --commit "$(git rev-parse HEAD)" --json headSha,databaseId,conclusion,event
```

Look for `event` `push`, `headSha` equal to the commit you pushed and `conclusion` `success`; an
empty list, or a run with no `conclusion` yet, is not green. A green run on a different SHA proves
nothing — not the parent's, not an earlier push's.

Run these locally before asking for review — separate commands, so one failure does not hide the
rest:

```bash
python3 -m compileall -q tools/mission_runner tools/governance
python3 tools/mission_runner/workflow_check.py
python3 -m unittest discover -s tools/mission_runner/tests -t tools/mission_runner
python3 -m unittest discover -s tools/governance/tests -t tools/governance
python3 -m unittest discover -s tools/trusted_gate/tests -t tools/trusted_gate
python3 tools/governance/governance_check.py check --root .
node tools/screen_contracts/screen_contracts.mjs check-identity
(cd backend && python3 -m ruff check .)
(cd backend && python3 -m mypy)
(cd backend && python3 -m unittest discover -s tests -t .)
```

Each `backend` command is a subshell: a bare repeated `cd backend` fails after the first, because
the shell is already there.

The three `backend/` commands need `backend/requirements-dev.lock` installed in the active
interpreter. If `ruff`, `mypy` or `fastapi` is missing, say so and let CI cover them — ask the
owner to provision the environment rather than installing anything yourself. None of the three is installed today, so
CI is their only coverage; the backend `unittest` run errors importing `tests.test_app` until they
are. Check rather than assume: the environment may since have been provisioned.

Known gaps, all deliberate, none waived (other suites also skip in CI as opt-in live probes): `check-complete` for the 1530 per-screen contract
fields is a visible failing gate deferred to the owning product modules by the owner's 2026-10-15
decision; the seven `SeatbeltTests` in `tools/mission_runner/tests/test_runner.py` skip off macOS,
so CI does not cover that OS-boundary isolation path — worker-credential isolation, agent deny-lists
through symlinked spellings, verifier read-only confinement and the planner profile; and
`check-change` is not run by CI.

## Preserved history

Historical review outcomes stand and are never rewritten, softened or reinterpreted. The MOD-004
D16 design lineage carries four recorded `CHANGES_REQUESTED` reviews; the in-repo source is
`OWNER-2026-10-28-mod004-d16-design-admission.md`, which names "the prior four `CHANGES_REQUESTED`
reviews" and leaves them unchanged without enumerating them. That record admitted the single root
`mod004-d16-dual-version-sonnet-20261026` with one design attempt plus at most two materially
distinct correction cycles, counted across both runners. That attempt **was dispatched and
recorded as consumed** (`attempts: 1 / max_attempts: 1`) on 2026-10-30; it failed on an
infrastructure fault, produced a draft that was never reviewed, and is therefore **not an
approval**. The counter's evidence is the `tasks` entry whose `id` is that root in
`~/Veyro-Migration-Archive-20261101/07-worker-owned-preserved/v2-mission-runner-state/v2/state.json`:
`status` `FAILED`, `attempts` 1, `max_attempts` 1, `finished_at` `2026-10-30T10:04:39+00:00` (read
it; never write to that tree). Whether the two correction cycles survive a failure of that kind is
open. **Ask the owner before any further D16 work, and never rename a root to obtain a fresh
attempt.**

`tools/mission_runner/` is tracked, live code under ADR-0001 and ADR-0004, and CI runs its tests —
do not treat it as dead or delete it. What is retired is the runner as an *execution path*: its
launchd services are stopped and disabled, and it must not be restarted, repaired or rebuilt, nor
replaced by a new scheduler, broker, dispatcher or approval framework.

Preserved evidence lives in `/Library/Application Support/Veyro/**`,
`~/Library/Application Support/Veyro/**`, `/Users/Shared/veyroworker/**` and
`~/Veyro-Migration-Archive-*/**`. Read it when you need to verify history; never write to it. It
must stay byte-for-byte intact.
