# M1-C-06 — minimum governed route for the five TSD §24.1 scanners (2026-10-09)

Status: **DECISION RECORDED. No tool activated, no scanner run against project
files, no capability registered or qualified, no scenario disposed, no reviewer
dispatched, no review entitlement created or consumed, no code/test/workflow/
registry/plan/control/remote change.** Sole runner operation
`9f9dc9ed-3146-4a72-be06-c0fab3f11b6a`, subgoal `M1-C-06-SCANNER-CAPABILITY-ROUTE`,
execution role `ARCHITECTURE_CRITICAL`, class `inspection`. Four governing
baselines re-verified this turn: `backend/.venv/bin/python
knowledge/00-System/verify_baselines.py` → **PASS, 4 of 4 MATCH**.

This is an architecture-critical routing decision inside the existing compressed
M1-C-06 operation. It is not an independent review, not a capability
qualification, not a security verdict, and not an authorization to push, merge,
or alter branch protection. All 13 C06 scenarios — SCN-MOD001-126, 030, 031,
032, 033, 039, 040, 043, 065, 068, 069, 122, 123 — and the five scanning
scenarios this decision routes (SCN-MOD001-029, 094, 134, 135, 136) remain
**NOT EXECUTED**. C06 remains W5 0/2 completed; the compressed plan remains at
19 operations; MOD-001 exit remains 0/8.

It extends, and does not revisit, `M1-C-06-TRUSTED-CI-ROUTING-DECISION-2026-10-09.md`
(SHA-256 `af9b97c40b925aae628b5635b9bc9076a96e57a77872a23b32430892e6c5ba5e`),
whose §7 already bound the rest of C06/C05 to three constraints: a drill-route
run never satisfies GOV-01-R04's blocking-gate criterion, every scanner inherits
the no-action/no-secret/runner-image-only constraint, and drill timings are not
full-CI budget results. Those constraints are treated here as settled inputs.

---

## 1. Observed evidence vs inference

Everything in this section was produced by direct execution or direct file read
**this turn**, except where the row says otherwise. The distinction is
load-bearing: the whole reason this decision exists is that the operation brief's
inventory needed confirming rather than inheriting.

### 1.1 Observed — tool availability

`command -v` sweep over 16 candidate scanners:

| Tool | Result |
|---|---|
| `gitleaks` | **PRESENT** — `/opt/homebrew/bin/gitleaks`, version `8.30.1` |
| `trufflehog`, `semgrep`, `bandit`, `trivy`, `grype`, `syft`, `checkov`, `tfsec`, `hadolint`, `pip-audit`, `safety`, `osv-scanner`, `dockle`, `kics`, `snyk` | **ABSENT**, all fifteen |

`backend/.venv/bin/` contains exactly `pip`, `pytest`, `py.test`, `mypy`,
`dmypy`, `mypyc`, `ruff`, `stubgen`, `stubtest`, `pygmentize` and the
interpreters — **no scanner of any kind**.

gitleaks provenance, read directly: `/opt/homebrew/Cellar/gitleaks/8.30.1/LICENSE`
is the **MIT License** (Copyright 2019 Zachary Rice);
`INSTALL_RECEIPT.json` records `tap: homebrew/core`, `spec: stable`,
`built_as_bottle: true`, `installed_on_request: true`. This is Homebrew package
metadata plus the installed LICENSE file — it is **not** the upstream-repository
license verification standard CAP-008 was held to (which required reading each
project's own official upstream `LICENSE`), so it is recorded as a starting
point for a qualification, not as a completed provenance review.

### 1.2 Observed — Ruff already carries a security ruleset

- `backend/.venv/bin/ruff --version` → `ruff 0.16.9`.
- `ruff linter` lists `S flake8-bandit` among its available linters.
- `ruff rule S608` returns real documentation for `hardcoded-sql-expression`,
  "Derived from the **flake8-bandit** linter… Checks for strings that resemble
  SQL statements involved in some form string building operation."
- Root `ruff.toml` (87 bytes) sets **only** `line-length = 100`.
  `backend/pyproject.toml`'s `[tool.ruff]` sets only `line-length` and
  `target-version`. **Neither selects `S`**, so the `S` rules are available but
  currently inert.
- `backend/requirements-dev.lock.txt` hash-pins 14 packages including
  `ruff==0.16.9`, `pytest==9.1.1`, `mypy==2.3.1`, `psycopg`/`psycopg-binary==3.3.6`.
  Its own header records that it was generated from a **macOS** wheel directory
  (`/private/tmp/.../veyro-wheels`), confirming the prior decision's Dependency A.

I deliberately did **not** run `ruff check --select S` over the project tree —
the operation brief prohibits invoking an unapproved scanner against project
files, and `S` is an unselected, never-qualified rule class. Whether the current
tree is `S`-clean is therefore **unknown and unclaimed**.

### 1.3 Observed — missing targets

- `backend/Dockerfile` **does not exist**. No `Dockerfile` exists anywhere at
  depth ≤ 3; no `docker-compose*`/`compose*.yml` either. `IMPLEMENTATION.md`
  line 151 lists `backend/Dockerfile` in its **topology** as "NEW, Scenario
  Review round 11, P1-3 — minimal disposable build scaffold." SCN-135's own
  correction note says the gap was "Fixed by adding a real minimal
  `backend/Dockerfile` scaffold **to the topology** this round" — which is
  literally true of the plan text and **false of the tree**. SCN-135 has no
  real target today.
- `infra/` **does not exist**. `IMPLEMENTATION.md` line 208 lists it as "NEW —
  IaC (exact tool TBD at implementation time)". SCN-136 already discloses this
  and says its own execution must author a synthetic fixture.
- `.github/` is **entirely untracked** — `git ls-files .github` returns nothing.
  Five workflow files exist locally only: `workflow-trust.yml`,
  `domain-uniqueness.yml`, `event-contract.yml`,
  `scn020-trusted-event-contract.yml`, `r03-failure-drill.yml`.

### 1.4 Observed — registry state and one pre-existing gap

`CAPABILITY_REGISTRY.md` contains **CAP-001 … CAP-008 only**. There is no
scanner row, no GitHub Action row — and no row for `ruff`, `pytest`, or `mypy`
either, each of which is a third-party executable already relied upon for
module-gate evidence. Next free identifiers: **CAP-009**, **BUG-057**.

A second observation, found by grep and worth stating plainly rather than
leaving for a reviewer to discover: **gitleaks has already been executed against
project content without a registry row.** `SCN020-SYNTHETIC-PROTECTED-PR-STATUS-2026-10-09.md`
and `SCN020-DISPOSABLE-PROTECTED-TARGET-2026-10-09.md` both record
`gitleaks git --staged --redact=100` returning exit 0 over staged project files.
Under `CAPABILITY_POLICY.md`'s fail-closed rule that is the same defect class as
BUG-038 (Docker/Postgres used for harness evidence while unregistered). I am
recording it, not filing it: filing a bug is a registry/BUG_REGISTRY edit, which
this operation is explicitly barred from making. It is named here as a
**mandatory input** to whoever next touches the registry, because it changes the
CAP-009 question from "may we start using gitleaks" to "we have already used it;
register or stop."

`ruff`/`pytest`/`mypy` being unregistered is the same class and is **also not
filed here**. It matters to §4 below, because it decides whether the SAST gap
costs zero new capability rows or one.

### 1.5 Inference — explicitly not observed

- **GitHub-hosted runner image contents.** Whether `ubuntu-24.04` ships any
  scanner pre-installed cannot be determined from this host. No route below may
  assume a pre-installed scanner; any such claim must come from an actual run's
  log.
- **Linux wheel/binary availability** for any new Python or Go scanner.
- **Reachability of any advisory data source** (OSV, PyPI JSON) from inside a CI
  job.
- Whether the current tree would pass or fail any of the five scanners.

---

## 2. The four layers, which are routinely conflated

The operation brief asks for these to be kept apart, and they must be, because
each has a different blocker and three of the four are not blocked at all.

| Layer | What closes it | Status today |
|---|---|---|
| **(1) Tool selection + availability** | A named free/open-source tool that exists, has a target, and runs | Resolvable now for SAST and secret; resolvable-with-acquisition for dependency; **target-blocked** for container and IaC |
| **(2) Capability qualification — stages 4, 5, 7** | Independent Opus evaluation (4), positive+negative tests on synthetic fixtures (5), an `APPROVED` `CAP-<NNN>` row (7) | **Zero of five scanners has any stage complete.** Stage 5 mechanics are Sonnet-runnable; stage 4/final approval is **not available to this session or any implementation session** |
| **(3) Scanner-runs-in-CI evidence** | GOV-01-R03's acceptance criterion: "every named tool… runs successfully in CI against the current repo state" | Route exists (the §1 drill route of the prior decision) but needs a **disposable branch/PR authorization that does not exist** |
| **(4) Trusted required-status enforcement** | GOV-01-R04's non-bypassable-gate criterion: trusted-anchor workflow on the default branch + branch protection + the unresolved same-name-spoof negative proof | **Blocked**, and not by this decision's scope |

Three separations inside that table are the ones most likely to be lost later:

Layer 2 is not layer 3. A scanner can be fully qualified and registered and
still have never run in CI; a scanner can run in CI on a candidate branch and
still be unqualified. Evidence for one is never evidence for the other.

Layer 3 is not layer 4, which the prior decision already established and §7 of
it already bound. Restated once because it is the single most likely
mis-recording in the whole of C06: **GOV-01-R03's "runs in CI" criterion is
satisfiable on the zero-authority drill route; GOV-01-R04's blocking-gate
criterion is not.** A green check from a `pull_request` workflow defined at the
candidate head is not enforcement, cannot be cited as enforcement, and must not
be adopted as a trust anchor or have its name reused.

Layer 4's blocker is not a tooling problem. Installing any trusted-anchor
workflow requires a commit on the default branch, `main`'s protection requires
one approving review, and the author-only collaborator set cannot produce one
(`GATE3-R1-P2-4-APPROVAL-ASSURANCE-BOUNDARY-2026-10-09.md`). That is a named
authority dependency, unchanged by any scanner choice.

---

## 3. Decision

Route the five TSD §24.1 scanner categories as follows. The headline is the
total governance cost: **two new capability rows for five scanners**, with two
gaps needing none, and two gaps deferred behind targets that do not exist.

| # | Category | Scenario | Route | New CAP rows |
|---|---|---|---|---|
| 1 | SAST | SCN-134 | **Ruff 0.16.9 `S` (flake8-bandit) ruleset**, selected in its own config, invoked as its own stage | 0 (or 1 if the §1.4 `ruff` registry gap must close first) |
| 2 | Dependency | SCN-094 | **Project-authored stdlib OSV-advisory query** over `requirements-dev.lock.txt` | 0 |
| 3 | Secret | SCN-029 | **gitleaks 8.30.1** → `CAP-009` | 1 |
| 4 | Container image | SCN-135 | **DEFERRED** — no `backend/Dockerfile` target exists | 1 later (trivy) |
| 5 | IaC | SCN-136 | **DEFERRED** — no `infra/**` target exists | 0 additional (same trivy row) |

Gaps 4 and 5 share one eventual acquisition deliberately: a single `trivy`
registration would cover both image scanning and `trivy config` IaC scanning, so
deferring them together and acquiring once is strictly cheaper than acquiring
`hadolint` + `checkov` separately. That is a forward note, not an approval, and
trivy's own provenance/license review has not been done.

### 3.1 SAST — Ruff's `S` ruleset

**Candidate A (selected): Ruff 0.16.9 `S`.** It is already installed, already
hash-pinned in the lock file at the exact version, already the project's lint
executable, and `S608` — the documented `hardcoded-sql-expression` check — is
precisely the pattern SCN-134's negative case names ("a hardcoded SQL string
concatenation shaped for injection"). Acquisition cost is zero; no new
dependency, no lock regeneration, no linux-wheel problem, no network.

Four constraints make this honest rather than convenient, and the route is not
acceptable without all four:

1. **Separate invocation, separate failure.** The SAST stage runs its own
   `ruff check` with its own explicit `--select S` configuration, its own report
   artifact, and its own CI job, so a lint pass cannot mask a SAST failure or
   vice versa. One executable serving two TSD §24.1 stages is fine; one
   *invocation* serving both is not.
2. **No vacuous pass.** `tools/validate_sensitive_logging.py` already
   demonstrated this failure mode on this tree — its default on a near-empty
   tree is a disclosed vacuous PASS, needing `--require-log-statements` for a
   non-vacuous result. The SAST stage must assert a non-zero count of files
   actually analysed and fail closed with a named code otherwise.
3. **Capability honesty.** Ruff `S` is a pattern-based reimplementation of a
   subset of bandit. It is **not** taint/dataflow analysis. The evidence claim
   must read "a static-analysis security ruleset ran against the current tree and
   produced a real report," which is exactly what GOV-01-R03's acceptance
   criterion asks for ("the tool working is the evidence, not a finding count"),
   and must not read "full SAST coverage."
4. **Scope-change disclosure.** Using an existing tool in a new security role is
   a `CAPABILITY_POLICY.md` stage-9 material scope change. Since `ruff` has no
   registry row at all (§1.4), the cleanest resolution is one `ruff` row
   covering lint + type-adjacent + SAST use, rather than a silent scope
   extension of an unregistered tool. **Whether that row is required before the
   SAST stage may be cited as evidence is an independent-reviewer call, not
   mine** — which is why §3 records the cost as "0 or 1."

**Candidate B (rejected): bandit.** Rejected on lean grounds, not quality: it
requires a new PyPI dependency, regenerating the hash-locked lock file, a second
Linux-specific lock (the prior decision's Dependency A), and a new CAP row with
full DC-19 provenance review — in exchange for a ruleset substantially
overlapping the `S` rules already installed and pinned. Two candidates
evaluated; discovery closed.

### 3.2 Dependency scanning — project-authored OSV query

This is the gap where the obvious answer is the wrong one, so the reasoning is
stated rather than asserted.

**Candidate A (selected): a project-authored stdlib script** that reads
`backend/requirements-dev.lock.txt`, queries the free OSV API for each
name/version, and reports advisory IDs. Governance cost is genuinely zero new
capability rows: the project's established pattern is exactly this — eight
project-authored `tools/validate_*.py` scripts already carry gate logic, none
needed a CAP row, because `CAPABILITY_POLICY.md` governs acquired capabilities,
not the project's own source. Dependency scanning is a **data-lookup** problem:
the quality lives in the advisory database, not in the client. SCN-094 wants the
CVE ID cited, and OSV supplies CVE aliases directly.

Three mandatory controls:

1. **Fail closed on no advisory source.** No network, non-200, or malformed
   response ⇒ non-zero exit with a named code (e.g. `NO_ADVISORY_SOURCE`), never
   a pass. A dependency scanner that silently passes offline is worse than none.
2. **OSV responses are untrusted input.** Parsed, never executed; no field
   echoed into a report without shape validation — the same discipline BUG-055
   forced on the privacy lint.
3. **SCN-094's fixture is a throwaway lockfile**, per the scenario's own text
   ("a long-since-fixed historical CVE… not a live supply-chain risk"), never the
   real lock file, and the vulnerable pin is never installed.

**Candidate B (named fallback): `pip-audit`.** The PyPA-official tool, and
credibly stronger. It is the fallback rather than the primary because it costs a
new dependency, a Linux lock, a CAP row and a provenance review, and it resolves
advisories from the same OSV data the stdlib client would query. **If an
independent reviewer judges a self-authored advisory client insufficient for a
Blocker-tier scenario, that judgment stands and this gap converts to `pip-audit`
with one more CAP row.** Recording the fallback now means that reversal is a
pre-reasoned switch, not a re-litigation.

### 3.3 Secret scanning — gitleaks as CAP-009

**Candidate A (selected): gitleaks 8.30.1.** Unlike the dependency gap, secret
detection quality lives almost entirely in the rule corpus — hundreds of
provider-specific key shapes — and SCN-029's whole point is detecting a
"fake-but-realistic-shaped" provider key. A hand-rolled regex set would be a
materially weaker claim against a Blocker scenario. gitleaks is MIT, installed,
and — decisively — **already used against project files without a row** (§1.4),
so registration closes an open gap rather than opening one.

Its CI acquisition is the real cost and must not be understated. No marketplace
action may be used (`iac.md` control 5: no action holds an `APPROVED` CAP row),
so the CI job must fetch the pinned linux release asset and **verify a committed
SHA-256 before executing it**, failing closed on mismatch. That fetch is itself a
supply-chain step owed its own provenance record, and the local arm64 binary's
hash does not substitute for the linux asset's. Running gitleaks locally only
would dodge this — and would fail GOV-01-R03's "runs in CI" criterion outright,
so it is not an option.

**Candidate B (rejected): a project-authored regex secret scanner.** Rejected
for this gap for the reason given above, and noted as the correct fallback only
if CAP-009's independent review rejects gitleaks — in which case the weaker
corpus must be disclosed in the scenario evidence, not papered over.

### 3.4 Container image — deferred, target-blocked

Three separate things are missing, and only the first is cheap.

1. **No target.** `backend/Dockerfile` does not exist (§1.3). SCN-135 was
   written on the belief that it does.
2. **No governed build engine.** CAP-008 is approved **only** for the pinned
   local Colima binding. A hosted runner's ambient Docker is a different,
   unregistered engine binding; using it would repeat BUG-038's exact defect. The
   prior decision already made this point for SCN-031 and it applies verbatim
   here. Mitigation worth carrying forward: a daemonless image-tarball scan, or a
   filesystem/Dockerfile-config scan, avoids binding an engine at all.
3. **No scanner.** `trivy`, `grype`, `syft`, `dockle`, `hadolint` all absent.

Deferring is therefore the honest route, and `hadolint` specifically must not be
substituted to appear to close it: Dockerfile linting is not container-image
vulnerability scanning, and recording it as SCN-135 would be the same
mislabeling the prior decision refused for SCN-031.

### 3.5 IaC — deferred, target-blocked, with its residual already disclosed

No `infra/` exists, and `IMPLEMENTATION.md` leaves the IaC vendor genuinely
undecided. SCN-136 already discloses that its fixture is authored by its own
execution and is therefore materially weaker than SCN-135's intended real
target, and already records that the first real `infra/environments/**` file
committed during implementation becomes its real target. Nothing in this
decision improves on that; picking a vendor now against zero content is exactly
the premature decision DC-18/DC-19 forbid. One hard constraint on whoever
authors that first file: **no `infra/environments/production/`, no production
secret scope, no production workflow** (`iac.md` control 4, DC-16).

### 3.6 Alternatives rejected across all five gaps

- **Any marketplace action** (`gitleaks-action`, `trivy-action`,
  `dependency-review-action`, `codeql-action`): blocked by `iac.md` control 5 on
  both legs — floating tags are unreviewable, and no action of any publisher
  holds an `APPROVED` CAP row. Not a preference; unmergeable as written. This is
  also why `event-contract.yml` (carrying `actions/checkout@v4` and
  `actions/setup-python@v5`) must not be copied as a shape.
- **Any paid SaaS** (Snyk, a commercial SAST tier): DC-16 owner-reserved,
  `release.md` control 3, and GOV-01-R03's own "Owner/external gates" text.
  Not pursued, and `SCN-064` is the denial drill proving no such credential is
  configured.
- **GitHub's built-in secret scanning / Dependabot alerts**: repository-settings
  features, not a CI stage with a report artifact, and they would not satisfy
  the "scanner runs in CI, producing a real report" criterion. Enabling
  repository settings is also outside this operation's permitted actions.
- **Declaring any scanner satisfied by a local run**: fails GOV-01-R03's "in CI"
  wording directly. All five local-only observations stay local.
- **A single mega "scan" job**: five named categories need five separately
  identifiable results and failure artifacts (`observability.md` control 1).
  Collapsing them would make a single green check unattributable.

---

## 4. Capability qualification route, and who may approve

For the two gaps that need a row (`CAP-009` gitleaks; the `ruff` row if a
reviewer requires it), `CAPABILITY_POLICY.md`'s own staging applies without
modification:

- **Stage 3 (discovery)** is closed by §1 and §3: at most two candidates per gap,
  named sources only, within the resolution budget.
- **Stage 4 (independent evaluation)** requires an **Opus assurance role** —
  `veyro-security-reviewer`, per EIP §4.2 as cited in `CAPABILITY_POLICY.md`'s
  model-routing section — for any third-party executable. gitleaks is a
  third-party Go binary; it gets **no exemption of any kind**. The first-party/
  harness exemption covers the Claude Code harness and Anthropic first-party
  Skills only.
- **Stage 5 (qualification)** needs a positive test (the scanner detects a
  deliberately planted synthetic secret in a disposable fixture) and a negative
  test (it correctly reports clean on the companion fixture with the pattern
  removed, and fails closed on malformed input). Mechanical execution **may** be
  Sonnet. Strictly synthetic fixtures with explicitly fake, clearly-labelled
  credential-shaped values per `secrets.md` control 1 — never a real-shaped
  plausible value, never the real tree.
- **Stage 7 (registration)** requires a full row before any module may depend on
  it: `provenance`, `version`, `content_hash` (the pinned linux asset's SHA-256,
  not only the local arm64 binary's), `scope`, `review_status`, `qualified_by`/
  `qualified_date`, `approved_by`/`approved_date`, `lifecycle_status`,
  `last_reviewed_at`, `next_review_due`, `rollback_target`, `evidence`.

**Who cannot approve, stated explicitly because the failure mode is cheap:**
a `qualified_by` naming only a Sonnet session with an empty `approved_by` is
`QUALIFIED`, not `APPROVED` — and per the policy's fail-closed rule, `QUALIFIED`
is **not usable for real project work**, only for further stage 4–5 drills. This
session cannot approve either: I am the bounded decision worker for M1-C-06, not
an independent reviewer, and an ARCHITECTURE_CRITICAL routing dispatch confers no
review entitlement. `REVIEW_IN_FLIGHT.md` reads `current_claim: CLEAR` with one
owner-authorized review already consumed at gate-3 round 1; `CLEAR` means no
review is in flight, **not** that a new one is authorized. No claim was written
this turn and no reviewer was dispatched.

Ordering consequence: gitleaks cannot be run against project files again —
including for SCN-029 evidence — until CAP-009 is `APPROVED`. The only touching
permitted before then is a stage 4–5 drill against synthetic fixtures, which is
the carve-out `CAPABILITY_POLICY.md`'s fail-closed rule names.

---

## 5. Immediately legal next increment under WIP=1

**One increment: the SAST (SCN-134) local candidate.** It is the only one of the
five gaps whose entire layer-1 and layer-3-authoring work is legal today with no
new capability, no new authority, no acquisition, no network, and no target that
does not exist:

- Add a SAST-specific Ruff configuration selecting `S`, kept separate from the
  existing lint configuration so the two stages fail independently.
- Add a synthetic insecure fixture under a clearly-labelled fixture path,
  containing an `S608`-shaped hardcoded SQL concatenation, plus its cleaned
  companion — never committed into an import path that real code would execute.
- Add the non-vacuity assertion (files-analysed count > 0, named failure code
  otherwise) and focused tests, so the same assertions run locally per
  `iac.md` control 1.
- Record the flagged/cleaned pair as a **local** observation only.

Routing: `.github/workflows/**` and CI stage wiring are the Infra/SRE/CI surface
profile (ADR-005 Decision 2) → **`veyro-infra-sre-engineer` (Sonnet)**. The Ruff
config and fixture authoring sit in the same increment and the same surface.
This is not a critical slice: it must not touch
`backend/tests/harness/postgres.py` (ADR-005 Decision 1,
`veyro-critical-engineer` only), must not add a required status context, must
not modify branch protection, and must not attempt layer 4.

Boundary: this is an increment **inside** the existing single coherent M1-C-06
operation. It adds no plan operation, no review entitlement, and no scenario
disposition — SCN-134 stays NOT EXECUTED until a real CI run plus shared R04
assurance, since its own criterion is a CI criterion.

Also legal in parallel-but-for-WIP=1, and named so the next session does not
re-derive them: the dependency-scanner script (§3.2) and the `backend/Dockerfile`
scaffold that unblocks SCN-135's target (§3.4, item 1). Under WIP=1 they wait.

---

## 6. Exact missing sources and permissions

Named precisely, so none is mistaken for an inferred owner stop.

**Missing sources (technical, obtainable without owner approval):**

1. `backend/Dockerfile` — planned at `IMPLEMENTATION.md` line 151, absent from
   the tree. Blocks SCN-135 layer 1.
2. The first real `infra/environments/**` file — blocks SCN-136's real target;
   `production/` remains forbidden.
3. A **Linux** hash-locked requirements file generated by
   `tools/generate_requirements_lock.py` from real linux wheels — the prior
   decision's Dependency A. Needed by any CI stage importing backend test
   dependencies, and by `pip-audit` if §3.2 converts to its fallback. Not needed
   by the selected SAST or dependency routes.
4. A committed **SHA-256 pin for the gitleaks linux release asset**. The local
   arm64 binary's hash is not a substitute.
5. Trivy provenance/license material, if and when gaps 4–5 un-defer.

**Missing permissions and authority (cannot be self-granted):**

1. **An authorized fresh-context Opus `veyro-security-reviewer` slot** for
   CAP-009's stage 4 and, if required, the `ruff` row. Without it both gaps stop
   at `QUALIFIED`, which is unusable for real work. This is the single highest-
   leverage missing item: it gates two of five scanners.
2. **A disposable same-repository branch + PR authorization for an R03 drill.**
   `SCN020_SACRIFICIAL_LIVE_AUTHORIZATION_2026-10-09.md` is explicitly scoped to
   SCN-020 and does not cover R03. Blocks every scanner's layer-3 "runs in CI"
   evidence, for all five categories at once.
3. **Default-branch commit capability for any trusted-anchor workflow**, which
   needs `main`'s one approving review that the author-only collaborator set
   cannot produce (`GATE3-R1-P2-4-APPROVAL-ASSURANCE-BOUNDARY-2026-10-09.md`).
   Blocks layer 4 entirely.
4. **Branch-protection required-status configuration** plus the unresolved
   same-name-spoof negative proof (the `scn020-trusted-event-contract.yml`
   C2/N5 residual, still open and untouched here). Blocks layer 4's blocking-gate
   criterion independently of item 3.
5. **Registry/BUG_REGISTRY write authority** to record the two unregistered-use
   gaps of §1.4 (gitleaks; ruff/pytest/mypy). Observed and named here; not filed,
   because this operation may not edit those files.

---

## 7. Residuals and what is explicitly not claimed

No scanner was run against project files. No capability was activated,
qualified, registered, or approved. No CI job was created or run. No workflow,
code, test, fixture, scenario record, registry row, bug record, plan file,
control file, branch, PR, or remote ref was created or modified. No reviewer was
dispatched, no `REVIEW_IN_FLIGHT.md` claim written, no review entitlement
created or consumed, and no new review round inferred from this decision's
existence.

SCN-MOD001-029, 094, 134, 135 and 136 remain **NOT EXECUTED**, as do all 13 C06
scenarios. No GOV-01-R03 or GOV-01-R04 acceptance criterion is closed or
partially credited. The gitleaks runs recorded in the SCN-020 evidence files
remain what they were — unregistered-capability invocations — and are **not**
relabelled here as secret-scanning evidence, SCN-029 progress, or qualification.
The `S`-cleanliness of the current tree is unknown. Runner-image contents,
Linux wheel availability and advisory-source reachability are unverified
inferences, flagged as such in §1.5.

The same-name candidate-check spoof residual (C2/N5) stays open. The SCN-031
fault-shape sufficiency question stays referred to the shared R04/scenario
assurance. Ruff `S`'s pattern-based (non-taint) nature is a disclosed capability
limit, not a defect to remediate. No paid service, real secret, real member
data, Production action, or branch-protection change is involved or implied.

C06 remains W5 0/2 completed; the compressed MOD-001 plan remains 19 operations;
MOD-001 exit remains 0/8; gate-2 F01–F14 remain 14/14 formally CLOSED; the P2-4
approval/assurance hold is preserved unchanged.
