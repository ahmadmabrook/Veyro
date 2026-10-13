# M1-C-06 — minimum governed CI execution route for shared R03 NET/PART proofs (2026-10-09)

Status: **DECISION RECORDED; no code, workflow, branch, PR, scenario disposition, review entitlement or plan-operation change.** Sole runner operation `b003e04c-74bc-47ff-b0d8-bea2db5a5067`, subgoal `M1-C-06-TRUSTED-CI-ROUTE`, execution role `ARCHITECTURE_CRITICAL`. Four governing baseline hashes re-verified PASS this turn (`verify_baselines.py`, 4/4 MATCH). This is an architecture-critical routing decision inside the existing compressed M1-C-06/C05 boundary — it is not an independent review, not a scenario verdict, and not an authorization to push, merge, or alter branch protection. SCN-MOD001-030 and SCN-MOD001-031 remain **NOT EXECUTED**; C06 remains W5 0/2 completed with 19 compressed operations remaining.

## 1. Decision

Route the shared R03 NET/PART proofs through a **`pull_request`-triggered, zero-authority drill job on a disposable same-repository head branch**, declared with `permissions: {}`, containing no `secrets.*` reference and no `uses:` action reference, executing only runner-image `python3`/`git`, and **explicitly not claimed as a required status check on any protected base**.

The decision rests on one observation about what SCN-030/031 actually require. Both are *drills* of the CI environment's own failure classification, not gates on candidate content: SCN-030 wants a real timeout against an unreachable host from within a CI job with repository state provably unaffected; SCN-031 wants a degraded/unavailable sandbox dependency to produce a dependency-unavailable failure distinguishable from a test-logic failure. Neither consumes candidate-supplied data, and neither needs a secret, a token scope, a container engine, or a merge decision. The narrowest route is therefore the one carrying the least authority, and the drill's evidential value comes from the inspected run — its logs, exit statuses, elapsed times and pinned head SHA — not from the colour of a check mark.

That separation is load-bearing and is the whole reason the route is safe. A `pull_request` workflow is defined at the candidate head, so a candidate can edit, suppress or same-name-spoof it. That matters only if something treats its conclusion as assurance. Nothing here does.

## 2. Exact trust boundaries

This route has **no trusted executable and no inert candidate data**, and saying so plainly is more honest than borrowing the language of the existing trusted-anchor workflows. Everything the drill runs is candidate-head content; the drill consumes no candidate-supplied input at all, because its only inputs are constants in its own script (the unreachable address, the timeout bounds). The contrast with the already-reviewed pattern is exact:

| Property | `scn020-trusted-event-contract.yml` / `workflow-trust.yml` / `domain-uniqueness.yml` | This NET/PART drill |
|---|---|---|
| Event | `pull_request_target` | `pull_request` |
| Workflow definition source | Default branch, GitHub-enforced | Candidate head (candidate-editable) |
| Executable source | Trusted default-branch snapshot fetched by immutable `github.sha` | Candidate head — **no trusted executable exists in this route** |
| Candidate contribution | Inert DATA only, screened, parsed never run | **None** — no candidate input is read |
| Secrets / privileged context | Present by event definition; the never-execute-candidate-code invariant is what keeps it safe | Absent: `permissions: {}`, no `secrets.*` reference, and no repository secret is configured |
| Trust claim | Required status check on a protected base | **None.** Not a gate, not a required context, not a trust anchor for anything |

The drill is acceptable as candidate-executed precisely because of five conjoined conditions, and it stops being acceptable if any one of them is dropped: `permissions: {}` grants the job no token scope; the file references no `secrets.*`; no repository secret exists to leak (independently recorded in `SCN020-REMAINING-OWNER-BOUNDARY-2026-10-09.md` — "No repository secret/canary was configured or exposed"); the job claims no required-status or gate authority; and its evidence is the inspected run rather than the check conclusion. **No later gate may adopt this drill as a trust anchor, reuse its name, or cite its green conclusion as enforcement.**

## 3. Event, permissions and branch-protection assumptions

The route assumes, and a future implementer must re-verify rather than inherit: that a `pull_request` workflow present on a same-repository head branch runs without the workflow existing on the default branch (this is why `event-contract.yml` ran on the SCN-020 disposable branches while absent from upstream and fork `main`); that `permissions: {}` yields a token with no scopes; and that no required status context is added for this job on any protected base. It assumes nothing about `main`'s protection, which currently requires one approving review with required status null, and it requires no change to it.

One assumption is deliberately *not* made. A fork-origin `pull_request` run is not relied upon: a genuine fork PR's candidate-only workflow was already observed not to run (`SCN020-H-AND-REMAINING-BOUNDARY-2026-10-09.md`), and no fork-capable second principal is available to this runner. The route is same-repository only.

## 4. Why the alternatives fail or need separate qualified enforcement

**`pull_request_target` with the trusted-anchor pattern.** Technically available and already independently patterned, but strictly over-privileged for this need: it adds secrets-capable privileged context and a default-branch definition to a drill that consumes no candidate data and needs no secret. It is also blocked today — `pull_request_target` takes its definition from the *default* branch, `.github/` is entirely untracked in `HEAD`, and installing it on upstream `main` needs the one approving review that the author-only collaborator set cannot currently produce (`GATE3-R1-P2-4-APPROVAL-ASSURANCE-BOUNDARY-2026-10-09.md`). Adding privileged context to buy nothing, while inheriting that blocker, is the wrong trade.

**Claiming the drill as a required status check.** This is where the risk named in the operation brief actually bites, and it is why the claim is refused rather than mitigated. Because a `pull_request` workflow is defined at the candidate head, a candidate can delete it so the context never reports, or publish a same-named trivially-passing job. The never-reports path is understood to block merge, but the **same-name candidate spoof is explicitly unproven even for the already-reviewed trusted workflow** — `scn020-trusted-event-contract.yml`'s own header records C2/probe N5 as open and instructs that the gate not be recorded as trusted until N5 is run. A route whose safety depends on an unproven negative is not the minimum route. Blocking-gate status for the R03 scanners is therefore a **separate enforcement problem**, requiring the trusted-anchor route plus branch protection plus live N5-class negative proof plus its own qualified assurance — not something this decision grants or this drill supplies.

**`workflow_dispatch`.** GitHub offers dispatch only for workflows present on the default branch, so it carries the same blocked-approval dependency; it is additionally the deliberate SCN-020 bypass class (d) omission.

**`push` to a disposable branch.** Same-repository push events carry secrets and the actor's token, so this has equal candidate-editability to `pull_request` with strictly greater default token authority, and no PR record to anchor evidence to. Narrower in no respect that matters.

**Reusing or copying `event-contract.yml`.** It carries `actions/checkout@v4` and `actions/setup-python@v5` — floating tags, and no GitHub Action holds an APPROVED `CAP-<NNN>` row (the registry contains CAP-001..CAP-008, none an action). It fails `.claude/rules/infra/iac.md` control 5 on both legs simultaneously and is unmergeable as written. The drill must not copy its shape; runner-image `python3`/`git` only, as the three trusted workflows already do for this exact reason.

## 5. SCN-030 (NET) — implementable now, with controls

SCN-030 is achievable on this route with zero third-party installs, zero actions and zero network egress beyond the deliberately unreachable target. Required controls, all of which must be asserted rather than assumed:

- **Positive control:** a loopback listener (`python3` stdlib `socket` on `127.0.0.1`) must accept a connection within milliseconds, proving the prober can observe success and that the timeout is not an artifact of a broken prober. Self-contained; no egress.
- **Negative controls, both directions:** the drill must fail if the unreachable target unexpectedly *connects*, and must fail if elapsed wall time exceeds the configured bound plus tolerance — the second is what distinguishes a genuine timeout from a hang, which is SCN-030's own stated expectation.
- **State control:** SHA-256 of `git status --porcelain=v1 -uall` captured before and after, matching the method already used in the local probe, proving repository state unaffected.
- **Job-level fail-closed control:** one disposable run with the assertion deliberately inverted must turn the job red, evidencing that no `continue-on-error`, `if: always()` or step-level suppression is present. The run conclusion itself is the evidence.
- **Address choice is a real constraint, not a detail.** The local probe used `10.255.255.1`; RFC 1918 space may be routable inside a hosted runner's own network and would then return a reset (connection-refused class) rather than a timeout, silently changing the fault class the drill claims to prove. Use RFC 5737 TEST-NET-1 (`192.0.2.1`), and assert the *timeout* class explicitly rather than merely asserting non-success. Retaining a corroborating `curl --max-time` observation preserves continuity with the recorded local exit 28, but the primary assertion should be on an explicit stdlib timeout so the proof does not depend on `curl`'s presence or its exit-code mapping.

## 6. SCN-031 (PART) — blocked behind two named technical dependencies

SCN-031 is **not** implementable on this route today, and the reasons are concrete rather than procedural.

**Dependency A — no Linux-installable governed test environment.** `backend/tests/harness/postgres.py` imports `psycopg` at module scope, so the integration stage cannot reach its own fixture without the backend test dependencies installed. The only governed install path is `pip install --require-hashes -r backend/requirements-dev.lock.txt`; that lock carries exactly 14 hashes for 14 packages, one wheel each, generated from a macOS arm64 wheel directory. On `ubuntu-24.04` (linux x86_64) the platform-specific wheels (`psycopg-binary`, `ruff`, `mypy`, `librt`) will not match, so `--require-hashes` fails. A plain `pip install -r backend/requirements-dev.txt` is explicitly forbidden by that file's own header (unhashed, transitive closure unnamed, source-distribution fallback permitted) and is exactly the supply-chain surface R03's dependency scanning exists to control. The exact dependency is therefore: **a Linux-runner hash-locked requirements file, generated via `tools/generate_requirements_lock.py` from real linux wheels, is absent.** Generating it is a distinct supply-chain step with its own provenance obligations, not a step to fold silently into a drill.

Without it the stage would fail at collection with `ModuleNotFoundError: psycopg`. That is genuinely a dependency-unavailable failure distinguishable from a test-logic failure — and recording it as SCN-031 would nonetheless be **mislabeling**, because the unavailable dependency would be the Python package, not the Postgres sandbox the scenario names. This decision declines that substitution.

**Dependency B — the local probe's fault-injection mechanism is inert on Linux, and the fix is not Sonnet-routable.** `postgres.py` hard-pins `TRUSTED_DOCKER_CLI = /opt/homebrew/bin/docker` with a pinned realpath and version, and `_trusted_cli()` is called *before* `DOCKER_HOST` is consulted. On a Linux runner the harness therefore fails at the CLI-resolution check, so the local probe's `DOCKER_HOST=unix:///tmp/...nonexistent.sock` injection would have no effect on the observed fault. The CI fault class would be "approved CLI unresolvable," not "sandbox refuses connections." Whether that still satisfies SCN-031 as written is a scenario-sufficiency judgment belonging to the shared R04/scenario assurance, not to this decision. Changing `postgres.py` to align the CI fault shape is **not available to a Sonnet increment**: `postgres.py` is the GOV-01-R02 tenant-isolation harness, which ADR-005 Decision 1 scopes to `veyro-critical-engineer`.

One genuine simplification is worth recording against future work: the degraded half of SCN-031 needs **no container engine at all**, because no engine is ever contacted. That keeps CAP-008 (approved only for the pinned local Colima binding) out of scope and avoids introducing the hosted runner's ambient Docker as an unregistered engine binding. Any future implementation must pin the fault injection and assert that no engine was contacted, rather than allowing a silent fall back to the runner's ambient Docker. The distinctness contrast SCN-031 requires can likewise be produced without an engine, by contrasting a fixture-ERROR class against a deliberately-failing pure assertion.

## 7. Constraint this route imposes on later R03 scanner and load wiring

The drill route buys execution, not enforcement, and that boundary propagates. Three constraints follow and should be treated as binding on the rest of C06/C05 rather than revisited per tool.

First, **no R03 scanner may be recorded as satisfying GOV-01-R04's non-bypassable-gate criterion on the strength of a drill-route run.** GOV-01-R03's acceptance criterion ("every named tool runs successfully in CI against the current repo state") is a *runs-in-CI* criterion and the drill route can satisfy it; GOV-01-R04's blocking-gate criterion is a different criterion requiring the trusted-anchor route, branch protection, and the unresolved same-name-spoof negative proof. Evidence for the first must never be presented as evidence for the second.

Second, **every R03 scanner on this route inherits the no-action, no-secret, runner-image-only constraint** from `iac.md` control 5. Until some action carries an APPROVED `CAP-<NNN>` row, no scanner may be wired via a marketplace action, which in practice means the free/open-source scanners must be invoked as pinned Python or runner-image tooling. Any scanner needing third-party Python packages inherits Dependency A above.

Third, **the bounded smoke-load work inherits the same ceiling.** `IMPLEMENTATION.md` §5's 15-minute full-CI budget and the 10-concurrent/2-second environment health check cannot be measured meaningfully against a drill job that is not the full pipeline. A drill-route timing observation is a lower bound on one job, not a full-CI budget result, and must not be recorded as the latter.

## 8. Minimal next implementation increment

One increment, routed to **`veyro-infra-sre-engineer` (Sonnet)** — `.github/workflows/**` is the Infra/SRE/CI surface profile under ADR-005 Decision 2, not routine implementation:

Author one new `pull_request` drill workflow implementing **SCN-030 only**, with `permissions: {}`, no `secrets.*`, no `uses:`, runner-image `python3`/`git` only, plus the shared prober script and its focused tests so the same assertions run locally (the `iac.md` control 1 local-equivalent requirement). Include all five SCN-030 controls from §5. Do not touch `backend/tests/harness/postgres.py`. Do not add a required status context, modify branch protection, or attempt SCN-031.

Authoring and local-equivalent proof need no new authority. **Live CI execution does, and the dependency is exact:** the drill needs a disposable same-repository branch and PR, and the existing `SCN020_SACRIFICIAL_LIVE_AUTHORIZATION_2026-10-09.md` is explicitly scoped ("Do not ... broaden beyond SCN-020"), so it does not cover an R03 drill branch. That is a named technical/authority dependency, **not an inferred owner stop** — the workflow and prober can be authored and locally proven now, and other mandatory C06 R03 foundations remain executable under WIP=1 meanwhile.

## 9. Residuals and what is explicitly not claimed

No CI job has been created or run. SCN-MOD001-030 and SCN-MOD001-031 remain **NOT EXECUTED**, as do all 13 C06 scenarios. The local curl exit-28 timeout and the local unavailable-Docker fixture ERROR recorded in `M1-C-06-R03-SOURCE-BOUNDARY-2026-10-09.md` remain local observations and are not relabelled here as CI evidence, R03 completion, scanner certification, or assurance of any kind. No R03/R04 acceptance criterion is closed. The same-name candidate-check spoof residual (C2/N5) stays open and is untouched by this decision, which deliberately avoids depending on it. The SCN-031 fault-shape question and the sufficiency of a CLI-unresolvable classification are referred to the shared R04/scenario assurance, not answered here.

No reviewer was dispatched and no review entitlement was consumed or created. No plan operation was incremented: this is the single coherent M1-C-06 operation, W5 0/2 completed, 19 compressed operations remaining. No paid service, real secret, real member data, Production action, or branch-protection change is involved or implied. MOD-001 exit remains 0/8; gate-2 F01-F14 remain 14/14 formally CLOSED; the P2-4 approval/assurance hold is preserved unchanged.
