# Opus Review Gate (DRAFT, opt-in)

Files: `.github/workflows/veyro-opus-review-gate.yml`, `infra/scripts/opus_review_gate.py`,
tests in `infra/scripts/tests/test_opus_review_gate.py`. The gate files, all of `.github/**`
and every `CODEOWNERS` location are protected by `trusted-pr-guard.sh`, so a PR cannot edit
its own reviewer.

## What it does
`pull_request_target` (opened/synchronize/reopened, plus `edited` only when the base branch
changed) first runs the base snapshot's offline tests (job `gate-selftest`: no environment,
no secrets, scrubbed env, PR head never fetched), then the **base snapshot's** script. The
review job `needs` the self-test. The PR head, from a trusted-author fork PR too, is fetched as
Git objects from `refs/pull/N/head` of this repository and its diff is sent to
`claude-opus-5-5` (`output_config.format` = `json_schema`, `effort` = `high`, no sampling
params, thinking left on). The reviewer account then submits `APPROVE` or `REQUEST_CHANGES`
pinned to the exact `commit_id`. The head is **not** "inert": Git parses attacker-supplied
objects (fsck enabled), and PR content is disclosed to Anthropic. It is never executed.

## Who may trigger a review (external PR policy and spend cap)
Only PRs whose author GitHub classifies (`author_association`) as `OWNER`, `MEMBER` or
`COLLABORATOR` are reviewed. This value comes from GitHub, never from the PR title, body or
labels, which the gate does not read. It is enforced three times: the job `if`, the script
before any git/GitHub/Claude call (env `AUTHOR_ASSOCIATION`), and again from the live PR API
response before any Claude call. Any other author (public fork `CONTRIBUTOR`, `NONE`,
first-timers, unknown or missing) gets **no review and no approval**, so the PR stays blocked
until the owner acts. Accepting an external PR needs an owner decision, e.g. adding the
author as a collaborator or reviewing a trusted re-submission of the change.
On an organization-owned repository, `MEMBER` can include members without write access to
this repository; this association is an API-spend filter, not a repository-permission check.

Spend bound: per run at most 48 review chunks (<=250 KB **diff** per chunk, plus manifest
and prompt overhead; <=16k output tokens per attempt, 10 MB total diff), with up to 2
retries per chunk on transient errors. Runs are serialized per PR but every push by a trusted
author starts a new run, so the real ceiling is set by the owner: before
activation use a dedicated non-default Anthropic workspace and set its monthly spend limit
for the API key (the default workspace does not support workspace limits), then record it in
the `OWNER_APPROVALS.md` entry. Spend-limit enforcement can lag usage; this is not an exact
per-request budget. Not verified from here.

## Protected paths
Independently of whether the trusted PR guard check is required, the script BLOCKS before
any API call if the PR changes anything under `.github/`, `CODEOWNERS`, `docs/CODEOWNERS`,
`infra/scripts`, `trusted-pr-guard.sh`, `opus_review_gate.py` or this gate's test file
(the same list as `trusted-pr-guard.sh`, compared case-insensitively). A test asserts the
two lists stay in sync. Those PRs need the owner, not this gate.

## Activation is opt-in and does not replace anything
The job is skipped unless repo variable `OPUS_REVIEW_GATE_ENABLED=true`. Skipped, failed or
BLOCKED runs submit nothing, so the required approving review stays unsatisfied. Owner
policy: Opus is the independent reviewer, so its approval at the exact head is the review
this gate provides; the trusted PR guard and CI stay mandatory. Enabling makes paid API
calls: record an `OWNER_APPROVALS.md` entry first (owner-reserved: no paid services).
No live API call has been made while building this.

## Large PRs (e.g. PR #10: 433 files, ~7.7 MB)
Per-file diffs are packed, in path order, into chunks of <=250 KB / <=100 files; each file is
in exactly one chunk, each chunk's response must list exactly its paths, and APPROVE needs all
chunks to approve. Hard limits (BLOCKED, never truncated or faked): 1000 files, 10 MB total,
48 chunks, 250 KB for any single file's diff, no binary changes. Each chunk sees the full
manifest (paths and hashes) but only its own diffs, so **cross-chunk interactions are not
analysed** and a change split across chunks could evade it; the review body says so.
PR #10 was checked against the collector locally: it is **BLOCKED**. It changes protected
`.github/` content, deletes four binary `.docx` files, and has five text-file diffs over
250 KB (the largest is about 1.88 MB). Any one of those is sufficient to block it.
No review or cost estimate for PR #10 is claimed. Those changes need a separately designed,
fully covered Opus review path or a smaller reviewed PR before autonomous merge.

## Enforcement the owner must configure (not provable from the repo)
- Provision a dedicated machine-user account (type `User`, **write** access, distinct from any
  PR author). Set variable `OPUS_REVIEWER_LOGIN` to it; the gate BLOCKS unless the token's
  `/user` login equals it, and unless `/collaborators/{login}/permission` is write/maintain/admin.
- Make that account's approval count: add it (or a team) to `.github/CODEOWNERS` for the paths
  it should gate and enable branch protection "Require review from Code Owners". Without this
  its approval is merely one review. There is no CODEOWNERS file yet; the gate does not
  create one (and the gate itself refuses PRs that touch CODEOWNERS).
- Enable "Dismiss stale pull request approvals" and "Require approval of the most recent
  reviewable push" (verify the exact setting names in the GitHub UI).
- Secrets live only in environment `opus-review` (deployment branches limited to `main`).

## Stale-approval race
The review job uses `cancel-in-progress: false`: a new push queues behind the running job
instead of killing it between submitting and verifying a review. The queued run then reviews
the new head; the old run's result is pinned to the old `commit_id` and fails the exact-head
re-check if the head moved.
Between the final head check and the review POST, a push can still land. Mitigations: review is
pinned to `commit_id`; the gate re-reads the head and the review list after posting and BLOCKS
if the head moved or the approval is not the reviewer's latest at the exact head; on that
failure it sends a best-effort dismissal request. **Automatic dismissal is not proven**: the
request needs the token to be allowed to dismiss, was only exercised against a fake, and the
job output states whether GitHub accepted it. Branch protection's stale-approval dismissal is
the real control. A BLOCKED run cannot withdraw an approval left on an older head; only the
settings above do that. A moved `main` between event and fetch also BLOCKS (re-run).

## Residual risks
Prompt injection (mitigated by nonce framing, schema, exact-path coverage, critical findings
overriding APPROVE; not eliminated); API spend (untrusted authors excluded; trusted authors bounded per run by the limits
above and overall only by the owner-set workspace spend limit); the model verdict alone is not a substitute for GitHub-enforced review policy.
