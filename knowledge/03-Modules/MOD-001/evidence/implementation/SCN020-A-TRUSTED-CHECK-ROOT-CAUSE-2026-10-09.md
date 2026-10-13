# SCN-020(a) trusted-check root cause and minimal correction — 2026-10-09

Bounded root-cause consultation. **No execution, no promotion, no PASS claim.** Nothing was
changed: no product code, tests, workflows, branch protection, PR, or remote state. This file is
this session's only write. Governing baselines re-verified PASS 4/4 (`verify_baselines.py`,
`backend/.venv/bin/python`). Companion record (not edited): `SCN020-A-CONTINUE-ON-ERROR-BYPASS-2026-10-09.md`.

**No independent review entitlement consumed.** `REVIEW_IN_FLIGHT.md` `current_claim` remains
`CLEAR` and was not modified; no reviewer was dispatched. The gate-3 one-off independent review
authorization remains **unconsumed**. Preserved unchanged: F14 formal CLOSED, R04 gate-2 closure,
U1/U2 B HOLD, SCN-070 cap, MOD-001 exit 0/8. SCN-MOD001-020 remains **BLOCKED / NOT PROMOTED**,
1/9 attempts executed, (b)–(i) pending.

## 1. Facts verified this session

Live read-only GitHub API, local git object reads, and GitHub's own documentation.

- **F1** Repo is `ahmadmabrook/Veyro` — **PUBLIC**, personal account (no organization), not a fork,
  default branch `main`.
- **F2** Remote `main` = `e516bed`. Its tree contains **no `.github/` at all**
  (`contents/.github?ref=main` → 404; top-level tree: `.claude`, `.gitignore`, `CLAUDE.md`, the
  three `.docx` baselines, `backend`, `knowledge`, `tools`, `veyro-product-experience-design`).
  `main` is `protected=false`. Repository rulesets: `[]` (none).
- **F3** Protection on `scn020-protected-base-20261009` (tip `36457b4`):
  `required_status_checks.strict=true`, `contexts=["architecture-event-contract"]`,
  `checks=[{context:"architecture-event-contract", app_id: null}]`; `enforce_admins=true`;
  `required_approving_review_count=0`; `require_code_owner_reviews=false`;
  `allow_force_pushes=false`; `allow_deletions=false`; `required_signatures=false`;
  `lock_branch=false`.
- **F4** Commit-level cause, exact: base `36457b4`'s workflow contains no `continue-on-error`;
  head `7b577271b223e7d1598059ad9e1d58380b43a725` adds exactly one line, `continue-on-error: true`,
  at line 22 of `.github/workflows/event-contract.yml`; `3ec7b840c4f1d27fc963f74a2e9ffd91521383b9`
  removes exactly that line (1 file changed, 1 deletion).
- **F5** Runs (immutable; all `event=pull_request`, `path=.github/workflows/event-contract.yml`,
  `run_attempt=1`):
  | run id | head_sha | conclusion | created |
  |---|---|---|---|
  | 37846009727 | `e093da8` | failure | 2026-10-08T21:19:57Z |
  | 37846232136 | `7b57727` | **success** | 2026-10-08T21:21:47Z |
  | 37846315610 | `3ec7b84` | failure | 2026-10-08T21:22:30Z |
- **F6** In run 37846232136, step 4 `Compare candidate events to PR base` conclusion = `success`
  and job conclusion = `success`, despite the step's own `exit 1`. Check run
  `architecture-event-contract` on `7b57727` = `success`, `app=github-actions`, `app_id=15368`;
  on `3ec7b84` the same context = `failure`.
- **F7** PR #1 now: `OPEN`, base `scn020-protected-base-20261009`, head `3ec7b84`,
  `isCrossRepository=false`, `mergeStateStatus=BLOCKED`, `mergeable=MERGEABLE`.
- **F8** Documented `pull_request`: `GITHUB_SHA` = "Last merge commit on the `GITHUB_REF` branch",
  `GITHUB_REF` = `refs/pull/N/merge`. The workflow definition is therefore merge/head-derived.
- **F9** Documented `pull_request_target`, **github.com (fpt/ghec) rendered variant**: the event
  "runs in the context of the **default branch of the base repository**"; table gives
  `GITHUB_SHA` = "Last commit on default branch", `GITHUB_REF` = "Default branch". The older
  "PR base branch" wording survives in the docs source only behind `{% ifversion ghes < 3.20 %}`,
  i.e. GitHub Enterprise Server below 3.20. **For this target, `pull_request_target` would use
  `main`'s workflow, not the protected base's.**
- **F10** Documented CODEOWNERS: "pull requests use the version of `CODEOWNERS` from the base
  branch of the pull request" — base-trusted, not head-controlled.
- **F11** Ruleset rule "Require workflows to pass before merging" is specified in terms of
  "your organization settings" and org-visibility scoping → organization-level; no organization
  exists here.
- **F12** Ruleset rule "Restrict file paths" is a **push** ruleset rule, and push rulesets
  "block pushes to a **private or internal** repository and that repository's entire fork
  network" → not applicable to this PUBLIC repo.
- **F13** Repo Actions posture: `default_workflow_permissions="read"`,
  `can_approve_pull_request_reviews=false`, `allowed_actions="all"`, `sha_pinning_required=false`.
- **F14** `tools/validate_architecture_gates.py` @ `36457b4` (8254 lines) already exposes
  `--event-source-dir`, `--event-registry`, `--event-baseline`, `--event-approval-root`. Its
  event-source scan uses `ast.parse` (line 1443); the file contains **zero**
  `exec(`/`eval(`/`subprocess`/`runpy` call sites. Pointing it at a candidate tree therefore
  **parses** candidate source, it does not execute it.
- **F15** Citation defect in the companion record: its run URLs are written
  `github.com/ahmadmabrouk/Veyro/...`; the real owner is `ahmadmabrook`. Run IDs and the PR #1
  URL are correct. Recorded here for a future correcting session; that file was not edited.

## 2. Root cause

The required status context is produced by a workflow whose **definition is read from the PR's
merge commit** (F8) — content the PR author controls. `continue-on-error: true` is merely the
cheapest expression of that; the defect is the trust boundary, not the keyword. Three corollaries:

- **C1** Step and job conclusions are author-controlled values, so process exit status and check
  conclusion are decoupled (F6 is the direct proof).
- **C2** Pinning the required check to `app_id` cannot close this under `pull_request`: a candidate
  head can define any job named `architecture-event-contract` that exits 0, and its check run is
  still attributed to app `github-actions`/`15368` (F6). The context is spoofable **by name** under
  `pull_request` regardless of app pinning. `app_id: null` today (F3) is strictly weaker still.
- **C3** Even a base-trusted *workflow definition* would be insufficient while the step executes
  `python3 tools/validate_architecture_gates.py` **from the checked-out candidate tree** — the
  validator is itself candidate code. The current workflow reads only the baseline registry and
  `OWNER_APPROVALS.md` from `$BASE_SHA` via `git show`; the validator and the step body are not.

Therefore: under `pull_request` there is **no base-trusted anchor inside the workflow**, and any
in-workflow self-verification is removable by the same edit that removes the gate. This is not
fixable by YAML hardening, a stricter `set -e`, or a confidence review.

## 3. The three posed questions, answered

**(Q1) Does `pull_request_target` use the protected base workflow or the default-branch workflow
for this target?** The **default-branch** workflow (F9). For this target that is `main`, *not*
`scn020-protected-base-20261009`. Two consequences follow immediately: (i) `main` currently has no
`.github/` at all (F2), so such a workflow would not exist on the anchor, would never trigger, the
required context would never report, and PR #1 would stay `BLOCKED` — fail-closed, but **inert,
not an enforcing gate**; (ii) `main` is unprotected (F2), so even once populated, "trusted" would
mean "writable by direct push to an unprotected branch" — a weaker anchor than the fixture's own
protected base.

**(Q2) Can a trusted status be enforced without candidate spoofing?** Only if the status producer
is anchored outside the candidate's write scope. Under `pull_request`: **no** (C2). Within
free / no-spend / no-new-infrastructure authority, the only such in-Actions anchor is
`pull_request_target` on the default branch. Org-level required workflows are unavailable (F11);
push-ruleset file-path restriction on `.github/workflows/**` is unavailable for a public repo
(F12); an external producer (GitHub App, PAT bot, self-hosted runner) requires credentials and/or
hosting and is owner-reserved.

**(Q3) Exact minimal permissible design** — §4. It is a **proposal**, not an implementation.

## 4. Minimal correction (proposal only; not implemented)

- **D1** Trigger `pull_request_target` (`types: [opened, synchronize, reopened]`), `branches:`
  limited to the protected target.
- **D2** `permissions: contents: read` at workflow level; reference **no secrets** at all.
- **D3** `actions/checkout` at its default ref (= the default branch) with
  `persist-credentials: false` → trusted workflow definition **and** trusted validator.
- **D4** Materialize the candidate as **inert data only**: fetch
  `refs/pull/${{ github.event.pull_request.number }}/head` and the base ref, then export via
  `git archive <head_sha> | tar -x -C "$cand"`. Never install from, never run anything in, `$cand`.
- **D5** Invoke the trusted validator against that data using the flags that already exist (F14):
  `--event-source-dir "$cand/<source root>"`, `--event-registry "$cand/contracts/events/registry.json"`,
  with `--event-baseline` and `--event-approval-root` materialized from the **base** SHA via
  `git show`. F14 is what makes this safe: the scan is `ast.parse`, not import.
- **D6** Keep the job name exactly `architecture-event-contract` so the pinned context (F3) still
  matches, and pin `app_id: 15368` on the required check — a narrowing, **not sufficient alone**
  (C2).
- **D7** Compensating control, independent of D1–D6 and available today: a `CODEOWNERS` file on the
  protected base covering `/.github/workflows/**` and `/tools/validate_architecture_gates.py`, with
  `require_code_owner_reviews: true`. Base-trusted per F10. This does not make the check trusted;
  it makes the weakening edit require an owner review.

## 5. Blockers — precise, not approximated

- **B1 (topology/authority).** D1–D6 cannot be realized for this target without committing the
  gate workflow to `main` and protecting `main`. Both are outside this task's constraints, and
  `main` is explicitly to remain untouched. The sound fixture topology is a **separate disposable
  public repository whose default branch is the trusted anchor** — this keeps Veyro's `main`
  untouched and costs nothing (public repo, free tier), but it is still a remote-state change
  requiring owner authority. **Not performed.**
- **B2 (governing-criterion conflict — `BLOCKED: OWNER_APPROVAL_REQUIRED`).** `REQUIREMENTS.md`
  GOV-01-R04's acceptance criterion requires the gate to resist "(i) `pull_request_target` running
  base-branch workflow code with secrets" **outright**. Adopting `pull_request_target` as the gate
  mechanism is in literal tension with that criterion. Separately, that criterion's and
  SCN-020(i)'s shared premise — "base-branch workflow code" — is **factually stale for github.com**
  (F9). Correcting a governing acceptance criterion and reconciling it with the remediation is a
  material change and is **not this consultation's call**; it is recorded as requiring owner
  adjudication, deliberately unresolved here.
- **B3 (single-account review control).** D7 needs `required_approving_review_count >= 1`, which
  the sole account cannot satisfy — GitHub does not permit approving one's own pull request.
  Operationalizing D7 requires a second trusted reviewer account: an owner decision, and it must
  involve no spend.

No sound path exists that is both technically correct and executable under this session's
authority. The correct disposition is to hold SCN-020 at BLOCKED pending B1/B2 (and B3 for D7),
not to apply a partial workflow edit that would leave C2 and C3 open while appearing remediated.

## 6. Negative verification plan for (a) — design only, pre-conditioned on B1/B2 clearance

- **N0** Preconditions: anchor branch is the default branch *and* protected; Veyro `main` untouched;
  synthetic fixtures only; no secrets; forward-only reverts, no force push (as `3ec7b84` was handled).
- **N1** Positive control: candidate head carrying a *registered* event → required context SUCCESS,
  PR CLEAN. This is also the first empirical confirmation of A2.
- **N2** Negative control, must reproduce the original denial: candidate re-introduces
  `emit_event("SCN020_SYNTHETIC_UNREGISTERED")` → `UNREGISTERED_EVENT_CONTRACT`, required context
  FAILURE, PR BLOCKED.
- **N3** The (a) probe proper: on top of N2, add `continue-on-error: true` to the gate step in the
  **candidate's own** `.github/workflows/event-contract.yml` → expected: no change at all to the
  reported context, because the run is driven by the anchor's workflow and the candidate's file is
  never evaluated. Assert by reading the run's `path`, `head_sha`, `head_branch` and confirming the
  candidate's edit produced no run of its own that reports the required context.
- **N3b** Validator-tampering variant (closes C3, untested by the original (a)): candidate rewrites
  `tools/validate_architecture_gates.py` to exit 0 unconditionally → required context must still
  report FAILURE.
- **N4** Deletion probe: candidate deletes its own `.github/workflows/event-contract.yml` entirely →
  required context must still report FAILURE, not "missing".
- **N5** Spoof probe (closes C2): candidate adds a second workflow with a job named exactly
  `architecture-event-contract` that exits 0. **Outcome deliberately not predicted here.** This is
  the probe that decides whether anchor + `app_id` pinning is sufficient; if a candidate's
  same-named check can satisfy the required context, the design is insufficient and the blocker is
  restated rather than patched.
- **N6** Evidence per probe, matching the immutable set used in F5/F6: run id, event, path,
  head_sha, run_attempt, step and job conclusions, check-run name/conclusion/`app_id`, and PR
  `mergeStateStatus`.

## 7. Implications for (c), (e), (i)

**(c) edit the gating workflow in the same PR.** Same root cause; (a) is its minimal instance, so
(c) at the workflow-YAML layer is already demonstrated in principle and should **not** be re-run as
a separate live bypass before remediation — it would only re-prove the same defect. But (c) has a
facet neither (a) nor the companion record covers: tampering with
`tools/validate_architecture_gates.py` or the step body rather than the YAML keywords. Under the
current design the validator executes from the candidate tree (C3), so that facet is **untested and
not closed** by removing `continue-on-error`. D3/D5 are what would close it; N3b is its probe.

**(e) fork PR.** Under `pull_request` from a fork, secrets are withheld, but the workflow definition
still comes from the merge commit (F8), so (e) **inherits (a)'s defect unchanged** and its expected
"gate still blocks" cannot hold pre-remediation. Post-remediation, fork PRs are precisely the case
`pull_request_target` is designed for and would be gated by the anchor workflow — so (e)'s outcome
is remediation-dependent. (e) should be re-sequenced to after remediation; running it now would
only re-measure (a).

**(i) `pull_request_target` with secrets.** Its premise is factually wrong for this host (F9:
default-branch, not base-branch, workflow code), and its expected "denied/inert" collides with
using `pull_request_target` as the remediation (B2). (i) needs a scenario-text correction plus
owner adjudication before it can be executed meaningfully. Any (i) attempt must also be measured
against the actual current posture (F13: `default_workflow_permissions="read"`,
`can_approve_pull_request_reviews=false`), not an assumed one.

## 8. Assumptions — explicitly not verified this session

- **A1** That workflow-level `permissions:` scopes only the `GITHUB_TOKEN` and does **not** withhold
  repository *secrets* from a `pull_request_target` run. No documentation statement either way was
  located this session. D2 is deliberately designed so the gate references no secrets, making A1
  non-load-bearing.
- **A2** That a `pull_request_target` workflow on the default branch triggers for a PR whose base is
  a **non-default** branch (with `branches:` matching that base). Consistent with F9 and the
  documented `branches:` filter semantics, but not empirically confirmed here; N1 is its first probe.
- **A3** That branch-protection required contexts match purely on context name (plus `app_id` when
  pinned). Consistent with F3/F6, but name-collision behavior is exactly what N5 exists to measure
  and is **not** assumed resolved.
- **A4** F9's applicability rests on the rendered github.com docs variant. If this project ever
  targeted GHES < 3.20, F9 inverts to "PR base branch" and §4's design changes accordingly.

## 9. Runtime model attestation and lean disposition

`knowledge/05-QA/tools/mr_verify.py` on the completed Claude ACP transcript
`/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/3892dca1-7343-4bd6-9467-bf2173cc42d5.jsonl`
returned **PASS, 72/72 turns, `claude-opus-5`**, for the
`veyro-critical-engineer` Opus tier. This was bounded critical-engineering
analysis, not an independent review or scenario verdict.

The trusted-status correction is **MANDATORY_NOW** if GOV-01-R04/SCN-020 is to
close; B1/B2 are current exact dependencies, not authority to change `main` or
create a new repository. F15's incorrect URL owner is **DEFERRED** to the
MOD-001 evidence-reconciliation owner after the SCN-020 authority boundary is
resolved; it does not change the observed run IDs or live security outcome.

Operator reconciliation: **B1 alone is the present execution stop** under the
owner's disposable-branch-only scope. B2 is recorded as an interpretation
ambiguity, not an adjudicated governing change: the detailed criterion names
`pull_request_target` *with secrets*, while the proposed design references
none. A later contract refresh must distinguish that wording from the same
paragraph's broader "resists (i) ... outright" summary before treating B2
as an additional owner decision. No dispatch or remote change follows this
analysis.
