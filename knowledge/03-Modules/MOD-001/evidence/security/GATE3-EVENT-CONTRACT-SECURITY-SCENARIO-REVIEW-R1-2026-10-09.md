# Gate-3 event-contract security/scenario independent review — R1, 2026-10-09

Scope: the single owner-authorized fresh independent qualified reviewer for MOD-001
GOV-01-R04 **gate 3** (event contract / trusted required status). Fresh context,
separate from the implementing session.

**Not** a gate-2 re-review, **not** a confidence round, **not** a module
certification. Gate-2 findings F01-F14 were not re-opened. SCN-070 was not decided.
GOV-01-R04 as a whole and MOD-001 are **not** certified by this report. No reviewer
or agent was dispatched. No product code, test, workflow, or any other repository
artifact was modified; no remote mutation of any kind was performed (remote work was
read-only `gh` readback). Owner-reserved absolutes were respected: no paid service or
spend, no real member data (all fixtures synthetic, in `/tmp`), no Production deploy,
no material scope change.

---

## 1. Overall verdict

**PASS-with-findings.**

All thirteen required dispositions — SCN-008, SCN-019, SCN-130, and SCN-020(a)
through (i) — are **SATISFIED** on the pinned artifacts, each on evidence this
reviewer reproduced or read back independently.

**P0 = 0 · P1 = 2 · P2 = 4** (P3 observations listed separately and are optional).

The two P1 findings are fail-open defects **in the gate-3 validator itself**, found by
this reviewer's own adversarial probes, not by any prior record. They do not falsify
the literal scenarios as written, but they do mean the following claim must **not** be
made: that gate 3 enforces TSD §24.1's event-contract clause as that clause is
actually worded. Both P1s must close before any GOV-01-R04 gate-3 certification.
Certification is outside this review's authority either way.

---

## 2. Hash and input-state verification performed by this reviewer

### 2.1 Governing baselines

`backend/.venv/bin/python knowledge/00-System/verify_baselines.py` → **PASS, 4 of 4
MATCH** against `knowledge/00-System/PROJECT_INDEX.md`:

| Baseline | Observed SHA-256 |
| --- | --- |
| `Gym_OS_Master_Product_Blueprint_v1_English.docx` | `80f4b381df26919b358b3e64e209c67beba2ba9224c0f4df3951d3b179d426ef` |
| `Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx` | `0d41c8a1231e5c8680c96a44b3ccc02c4f42cf8984c84d04bf9b60378cc158e8` |
| `Veyro_Engineering_Implementation_Plan_v1.4.1_..._GOVERNING_BASELINE.docx` | `e5b5ec3b08859e27da3689dc3b54d17ea766cba5bf4c4e0007239baa920866b6` |
| `veyro-product-experience-design` | `c96f77abdf4345b231a60b37f832d76ac82cf52fb8b00ae3066f20bb10a36dbb` |

### 2.2 HEAD

`git rev-parse HEAD` → `e481b814a80923849dddfe7a49319112aae7b023`. Matches the
preflight. Confirmed that `.github/` is **untracked** (`git status --porcelain
.github/` → `?? .github/`; `git ls-files .github/` → empty), so the workflow review was
conducted by file hash, as the dispatch required.

### 2.3 The five pinned files — observed values (`shasum -a 256`)

| Path | Observed SHA-256 | Preflight | Match |
| --- | --- | --- | --- |
| `tools/validate_architecture_gates.py` | `28f3c458e2aae6e2243bfc749388e4f1d540dce1c410cc99671d78c9914d0ce4` | same | YES |
| `tools/tests/test_validate_architecture_gates.py` | `de3e64ee9e32fbbafe653a2697fdb91ee9b907b63a2564a1a9ce86c9434e892b` | same | YES |
| `.github/workflows/scn020-trusted-event-contract.yml` | `59858025d4c113ea6c2364cdd3128344d9b3ffda4644455920d863f8849628bf` | same | YES |
| `.github/workflows/event-contract.yml` | `74df304076edef48d77d58b0537107fe2d65972fdac81247ed1ddfc2816e08df` | same | YES |
| `SCN020-NINE-CASE-ASSURANCE-INPUT-2026-10-09.md` | `36fa641d2869f5dffd2e0f780bbd81884d750db2544fc9643e7ac946514c5246` | same | YES |

**Zero drift.** Re-hashed at the end of the review: unchanged, so nothing shifted
underneath this report.

### 2.4 Remote-artifact identity (verification the preflight did not pin, and the
single most load-bearing check in this report)

Because `pull_request_target` reads its definition from a trusted ref, the local
untracked bytes are only meaningful if they are the bytes GitHub actually executed.
This reviewer fetched the default-branch blobs by `ref=f85a17ba...` and hashed them:

| Path at upstream default `main` = `f85a17ba28cf55a209b0129ea8e9ceacc6a9edb9` | Observed SHA-256 | vs pinned local |
| --- | --- | --- |
| `.github/workflows/scn020-trusted-event-contract.yml` | `59858025d4c113ea6c2364cdd3128344d9b3ffda4644455920d863f8849628bf` | **byte-identical** |
| `tools/validate_architecture_gates.py` | `28f3c458e2aae6e2243bfc749388e4f1d540dce1c410cc99671d78c9914d0ce4` | **byte-identical** |
| `.github/workflows/event-contract.yml` | **absent (HTTP 404)** | n/a |

Upstream `ahmadmabrook/Veyro`: `default_branch=main`, `visibility=public`,
`fork=false`. The trusted workflow and the executable validator that produced the
required status are therefore **provably** the pinned artifacts, not merely described
as such.

### 2.5 Live protection readback (this reviewer's own `gh api` calls)

Both `ahmadmabrook/Veyro` and `veyro-labs/Veyro`, branch
`scn020-protected-base-20261009`, returned identically:

```
strict=true
contexts=["architecture-event-contract-trusted"]
checks=[{context:"architecture-event-contract-trusted", app_id:15368}]
enforce_admins=true
allow_force_pushes=false
allow_deletions=false
restrictions=null
```

`gh api apps/github-actions` → `{id:15368, slug:"github-actions", name:"GitHub
Actions"}`, so the app pin is GitHub Actions and nothing else.

Both protected bases observed at `36457b4dbe309355c5fede5f56c451371bcfd1f6` —
unchanged, after all nine attempts.

### 2.6 Focused test suite

`backend/.venv/bin/python -m pytest tools/tests/test_validate_architecture_gates.py -q`
→ **548 passed in 5.30s**, in the project venv, reproducing the preflight's
`548/548 PASS` claim first-hand.

---

## 3. Trust-boundary analysis

### 3.1 The candidate-controlled zone versus the trusted required status

| Surface | Which ref supplies it | Candidate can alter? | Required by protection? |
| --- | --- | --- | --- |
| `event-contract.yml` job `architecture-event-contract` | PR **head** ref (`pull_request`) | **Yes, fully** | **No** |
| `scn020-trusted-event-contract.yml` job `architecture-event-contract-trusted` | **default branch** `main` (`pull_request_target`) | No | **Yes** (strict, app 15368) |
| `tools/validate_architecture_gates.py` as executed | fetched by immutable `github.sha` from the same trusted default snapshot | No | — |
| baseline registry + owner-approval root | **protected PR base SHA** | No | — |
| candidate `backend/app/**/*.py`, `contracts/events/registry.json` | PR head ref, as **inert data** | Yes (data only) | — |

### 3.2 `pull_request` versus `pull_request_target`, proven rather than asserted

The trusted workflow's header asserts (F9) that a `pull_request_target` run takes its
definition and `GITHUB_SHA` from the **default** branch, not the PR base branch. That
is a non-obvious claim and this reviewer treated it as a hypothesis. It is **confirmed
empirically**, two independent ways:

1. The PR base branch `scn020-protected-base-20261009` (`36457b4d`) contains **only**
   `event-contract.yml` — the trusted workflow file is **absent** there (contents API
   → 404 / zero bytes). Yet the trusted `pull_request_target` run fired. The definition
   could therefore only have come from the default branch.
2. The live run's own log prints
   `trusted=f85a17ba28cf55a209b0129ea8e9ceacc6a9edb9 head=b76ed1d8a65ab1ead1009f6df21490c3c23b9266 base=36457b4dbe309355c5fede5f56c451371bcfd1f6`
   — `github.sha` is the **default-branch** SHA, not the base (`36457b4d`) and not the
   candidate head.

Consequence, independently established rather than inherited: a candidate cannot
replace, weaken, rename, or suppress the required definition, because the candidate
does not control the ref it is read from. This is the structural basis for (a), (c),
(d), (e), (g) and (i) all at once.

### 3.3 Token and permission scope

Declared: `permissions: contents: read`. The live run's own setup banner confirms the
effective grant was exactly `Contents: read` / `Metadata: read`. The workflow contains
**zero** `secrets.` references and **zero** `environment:` declarations (verified by
grep; the four `uses:` hits in the file are comment prose explaining why no action is
referenced). It uses no `actions/checkout`, so `GITHUB_TOKEN` is never persisted into
a git credential helper at all — stronger than `persist-credentials: false`.

### 3.4 Can the required status name be satisfied by anything other than a genuine
trusted run? — the same-name spoof (root-cause C2/N5)

This is the sharpest residual risk, because **both** the trusted workflow and any
candidate workflow publish check runs under the *same* app (15368). App-ID pinning
therefore does **not** distinguish them. This reviewer verified the live collision
directly rather than trusting the record, and found the ordering detail the record
does not foreground:

On head `df68079cd490e62617d93a586d7c689b274e10d7`, check-runs API returns **two** check
runs with the exact required name `architecture-event-contract-trusted`, both app
`15368`:

| Check-run id | Conclusion | Completed | Origin |
| --- | --- | --- | --- |
| `113564928849` | **success** | `2026-10-08T22:07:18Z` | candidate run `37851408930`, event `pull_request`, path `event-contract.yml` |
| `113564923565` | **failure** | `2026-10-08T22:07:17Z` | trusted run `37851406371`, event `pull_request_target`, path `scn020-trusted-event-contract.yml` |

The spoofed success **completed one second later** than the trusted failure, i.e. the
spoof was the most recent check run under the required name — the ordering least
favourable to the gate — and the PR was still observed `BLOCKED` / `mergedAt=null`.
That is a genuine adverse-ordering negative result, not a race the spoof merely lost.
The implementation's own precondition ("Do not record this gate as trusted until N5 is
run") is therefore met.

However, the *mechanism* by which GitHub resolved the collision is not established by
one observation, and the merge-state at that head is no longer re-observable (PR #1 has
since advanced to `45ed3ef3`), so this rests on the captured snapshot plus my
confirmation of the two check runs that still exist. Recorded as **P3-1**, a disclosed
residual — consistent with the evidence record's own refusal to generalize. It does not
alter any (a)-(i) letter, since a same-name spoof is not one of the nine letters.

### 3.5 Candidate data handling in the trusted run

Reviewed line by line and found sound: tree entries screened **before** extraction to
regular blobs only (modes `100644`/`100755`), so symlinks (`120000`) and gitlinks
(`160000`) deny; absolute and `../` paths deny; out-of-scope paths deny; NUL-delimited
listing redirected to a file rather than through `$(...)` (a real fail-open had it been
done the other way, and the comment explaining why is correct); post-extraction
`find -type l` screen; non-`.py` files deleted from the candidate source root;
`python3 -E -s` so `PYTHONPATH`/user site-packages cannot inject; candidate directory
never on `sys.path`; untrusted values passed only via `env:` and never interpolated
into the script body; only SHAs and `github.repository` consumed, never a PR title,
branch name, or author-controlled label; `set -euo pipefail` with an explicit `deny()`
so every abnormal path exits non-zero. The verdict wrapper discriminates on the
report's own `status` field rather than exit code alone, and `NOT_APPLICABLE` /
`INCONCLUSIVE` are never reported as PASS. No fail-open was found in this layer.

---

## 4. Per-scenario and per-letter dispositions

Every row cites what **this reviewer** verified. "Covered by the record" is nowhere
used as evidence.

### 4.1 The three event-contract scenarios

All four CLI cases were **re-executed from scratch by this reviewer** in a disposable
`/tmp` fixture tree against the pinned validator, using the project venv. The live
`knowledge/00-System/OWNER_APPROVALS.md` was never read as an approval root and never
modified; the approval root was my temporary directory.

| Scenario | Disposition | Evidence verified by this reviewer |
| --- | --- | --- |
| **SCN-MOD001-008** (registered literal event → PASS) | **SATISFIED** | My own run: registered literal `emit_event("membership.member-created.v1")` with matching JSON-Schema registry entry → `status=PASS`, exit `0`, `checked=["app/flow.py:1"]`. Matches `GATE3-EVENT-CONTRACT-SHARED-SCENARIO-CAPTURE-2026-10-08.json` case `SCN-MOD001-008-registered`. Gate code path: `validate_architecture_gates.py:1446-1457`. |
| **SCN-MOD001-019** (unregistered referenced event → `UNREGISTERED_EVENT_CONTRACT`) | **SATISFIED on the literal fixture** | My own run: `emit_event("membership.unknown.v1")` → `status=FAIL`, exit `1`, single violation `UNREGISTERED_EVENT_CONTRACT`, `detail="membership.unknown.v1"`, `subject="app/flow.py:1"`. Denial site `validate_architecture_gates.py:1456-1457`. **Capped by P1-1**: the detection predicate is narrower than the scenario's own words "an event referenced in code", so this scenario must not be read as establishing registry coverage for all code-referenced events. |
| **SCN-MOD001-130** (compatibility/classification change without approval → `EVENT_CHANGE_UNAPPROVED`; identical diff with a synthetic disposable `OWN-` row → PASS) | **SATISFIED** | My own runs, both halves. Negative: adding `"required":["id"]` to a baseline-registered event's schema, no `ownerApproval` → `FAIL`, exit `1`, `EVENT_CHANGE_UNAPPROVED`, `subject="membership.member-created.v1"`, `detail="schema changed; missing OWN-NNN approval"`. Positive: identical diff + `ownerApproval:"OWN-999"` + a disposable `OWNER_APPROVALS.md` copy carrying `\| OWN-999 \| membership.member-created.v1 \| ... \|` → `PASS`, exit `0`. I additionally verified the approval binding is not nominal: a row naming a **different** event → `FAIL` (`approval OWN-999 row does not mention 'membership.member-created.v1'`); **duplicate** `OWN-999` rows → `FAIL` (`2 OWNER_APPROVALS rows, need 1`). Sites: `validate_architecture_gates.py:1458-1471`, `resolve_approval` at `:599-628`. Classification-only change also denies (my probe). See **P2-2** on the "diff" wording. |

TSD §24.1 gate-3 text read directly at `knowledge/00-System/TSD_MIRROR.md` lines
11610-11612: "Event contract lint: every event referenced by flow/code exists in
AsyncAPI/JSON Schema registry; compatibility and classification changes require owner
approval." Both normative halves are exercised by the three scenarios above; see
P1-1/P1-2 for where the implementation falls short of that text's actual reach.

### 4.2 SCN-020, all nine letters

Shared facts verified by this reviewer for every row: protection as in §2.5; upstream
PR #1 `state=open, merged=false, mergeable_state=blocked`, head repo
`ahmadmabrook/Veyro`, head `45ed3ef3`; upstream PR #2 `state=open, merged=false,
mergeable_state=blocked`, head repo **`veyro-labs/Veyro`** (genuine cross-namespace
fork), head `b76ed1d8`; fork-local `veyro-labs/Veyro` PR #1 `open/blocked/unmerged`;
both protected bases at `36457b4d`. Every run id below was re-read via
`gh api .../actions/runs/<id>` and its `name`/`event`/`conclusion`/`head_sha`/`path`
confirmed.

| Letter | Attack | Disposition | Evidence this reviewer verified |
| --- | --- | --- | --- |
| **(a)** | `continue-on-error: true` on the gate step in the same PR | **SATISFIED** | Head `10ab7e23`: candidate run `37850953256` (`pull_request`, `event-contract.yml`) = **success**; trusted run `37850950695` (`pull_request_target`, `scn020-trusted-event-contract.yml`) = **failure**. The suppressed check is not the required context. Same shape still live on current head `45ed3ef3`: check-runs = `architecture-event-contract` success (app 15368) + `architecture-event-contract-trusted` failure (app 15368); PR #1 `mergeable_state=blocked` (my own readback). |
| **(b)** | `[skip ci]` commit-message token | **SATISFIED** | Head `10113e39`: check-runs API returns **exactly one** check run — `architecture-event-contract-trusted`, **failure**, app `15368`. The token did suppress the candidate `pull_request` workflow entirely, and the trusted `pull_request_target` required check still ran and still failed. Trusted run `37851224895` (`pull_request_target`, trusted path) = failure. A stronger result than the record states. |
| **(c)** | Candidate edits the gating workflow file itself | **SATISFIED** | Head `6853998f`: candidate run `37851311165` (`pull_request`, `event-contract.yml`, reduced to a no-op) = **success**; trusted run `37851306085` (`pull_request_target`, trusted path) = **failure**. The edited candidate definition is not the required definition; per §3.2 the candidate cannot reach the ref the required definition is read from. |
| **(d)** | `workflow_dispatch` bypassing the PR-triggered path | **SATISFIED as a bypass denial** | Head `3b71e1ff`: manual run `37851695064`, `event=workflow_dispatch`, `conclusion=success`, name `architecture-event-contract` — i.e. a green **non-required** context. Trusted run `37851690109` (`pull_request_target`) = **failure**. Dispatch itself succeeded (it is not forbidden); it cannot satisfy the pinned required context. Independently consistent with the trusted workflow declaring **no** `workflow_dispatch` trigger (file read, `on:` block lines 55-59). |
| **(e)** | Equivalent PR from a fork | **SATISFIED** | Upstream PR #2 head repo is `veyro-labs/Veyro` — a true cross-namespace fork (`fork=true`, `parent=ahmadmabrook/Veyro`), not a same-repo branch. Trusted run `37854269848` (`pull_request_target`, trusted path, head `db04cecf`) = **failure**; and for head `b76ed1d8`, run `37857138121` = **failure** with log `UNREGISTERED_EVENT_CONTRACT` / `DENY (exit=1 status=FAIL ...)`. PR #2 `mergeable_state=blocked` on my own readback. Also verified fork-local run `37856026555` on `veyro-labs/Veyro` = failure. |
| **(f)** | Repository-admin "bypass required status checks" override | **SATISFIED** (as the stricter of the two branches the criterion permits) | `enforce_admins=true` verified by me on **both** upstream and fork protection, with `allow_force_pushes=false`, `allow_deletions=false`, `restrictions=null`. The pinned merge attempt `PUT /repos/veyro-labs/Veyro/pulls/1/merge` returned **HTTP 405**: `Required status check "architecture-event-contract-trusted" is failing.` Both bases unchanged at `36457b4d` and all PRs unmerged on my readback. GOV-01-R04's recording criterion is met by durable evidence: `SCN020-REMAINING-OWNER-BOUNDARY-LIVE-SNAPSHOT-2026-10-09.json` records `authenticatedLogin: "ahmadmabrook"`, `authenticatedRepositoryAdmin: true`, `restrictions: null` — the hatch's holder is named, not assumed away. **Honest limit:** the merge call was executed against the fork, not upstream; the upstream conclusion rests on independently verified identical protection fields, not on an executed upstream attempt. See P3-2. |
| **(g)** | Rename the gating job so the required check name no longer matches | **SATISFIED** | Verified at source, not from the record: candidate head `45ed3ef3` **does** carry its own copy of `.github/workflows/scn020-trusted-event-contract.yml` with `name: architecture-event-contract-renamed` (line 1), `on: pull_request_target` (lines 3-4), and job/job-name `architecture-event-contract-renamed` (lines 13-14). That definition produced **no check run**: check-runs on `45ed3ef3` are exactly `architecture-event-contract` (success) and `architecture-event-contract-trusted` (failure), both app `15368` — no `...-renamed` check exists. Trusted run `37851803573` still reported under the **original** required name and failed; candidate run `37851806602` emitted only the non-required name. Per §3.2 this is structural: candidate bytes cannot rename the default-branch definition. See P3-3 on the fail-closed-on-absence sub-point. |
| **(h)** | Direct / force push to the protected branch | **SATISFIED** | Normal fast-forward direct push to upstream `scn020-protected-base-20261009` → `GH006 Protected branch update failed ... Changes must be made through a pull request ... Required status check "architecture-event-contract-trusted" is expected`, `pushExitCode=1`, `before == after == 36457b4d`, `branchUnchanged=true`. Non-fast-forward `--force-with-lease` against the fork's protected base → `[remote rejected] (protected branch hook declined)` + `GH006 ... Cannot force-push to this branch`, exit 1. My own readback: both protected bases still `36457b4d`. Configuration basis independently verified: `allow_force_pushes=false`, `allow_deletions=false`, `enforce_admins=true`. |
| **(i)** | `pull_request_target` workflow running base-branch workflow code **with repository secrets** against a fork PR's ref | **SATISFIED** (reasoned determination in §5) | §5. |

---

## 5. SCN-020(i): reasoned determination

**Determination: SATISFIED on the pinned artifacts.** Not "satisfied by equivalence",
and not promoted past what the evidence supports. The reasoning, with the
environment-versus-repository secret question decided rather than deferred:

**(i) decomposes into two distinct claims, and only one of them was ever
secret-dependent.**

**Claim 1 — a candidate-head `pull_request_target` workflow definition must not
execute.** Observed, twice, on a genuine cross-namespace fork. On fork heads
`db04cecf` and `b76ed1d8`, the candidate-only workflow
`.github/workflows/scn020-fork-candidate-only.yml` — which requests
`pull_request_target`, names the test environment, reads
`secrets.SCN020_TEST_ONLY_CANARY`, and checks out
`github.event.pull_request.head.sha` — produced **no run and no check run**. My own
readback of head `b76ed1d8` returns exactly two check runs,
`architecture-event-contract` and `architecture-event-contract-trusted`, both app
`15368`, and the upstream default-branch workflow inventory contains **only**
`scn020-trusted-event-contract.yml`.

Decisive point on the secret-scope question: **the observed inertness is
mechanism-independent of secret scope.** The candidate workflow did not run because
`pull_request_target` reads its definition from the default branch — which I proved
independently in §3.2 from the trusted workflow's **absence** from the PR base branch
combined with `github.sha = f85a17ba...` in the live log. A repository-wide secret
instead of a branch-restricted environment secret would not have changed which ref
supplies the definition, and therefore could not have made that workflow run. For
Claim 1, the environment-scoped observation and the repository-scoped claim **are**
equivalent, and I decline to discount it on a distinction that is not load-bearing
here.

**Claim 2 — the *trusted* (default-branch) `pull_request_target` workflow must not
hand secrets to a fork ref.** This is the real `pull_request_target` escalation, where
the dangerous actor is the trusted workflow, not the candidate. In the pinned artifact
the hazard is **absent by construction**, verified in the bytes and in the live run:
the trusted workflow contains **zero** `secrets.` references and **zero**
`environment:` declarations, so it could not read `SCN020_TEST_ONLY_CANARY` or any
repository-wide secret even if one existed; its token grant was observed in the run's
own banner as exactly `Contents: read` / `Metadata: read`; and it never places
candidate content in executable position (candidate paths are materialized as screened
inert data, non-`.py` files deleted, `python3 -E -s`, candidate dir never on
`sys.path`, validator fetched by immutable SHA from the trusted snapshot). There is no
secret for a fork ref to capture and no candidate code path that could capture one.

**What is genuinely not established, stated plainly.** The evidence does **not**
establish that repository-wide secrets are *unavailable* to a `pull_request_target`
run on a fork PR. On GitHub they generally **are** available — that is precisely why
the trigger is dangerous. The project's defence is therefore **abstention** (the
trusted workflow chooses to reference no secret and to execute no candidate code), not
**unavailability** and not **enforcement**. That abstention is fully verified on these
pinned bytes, which is what this review is scoped to judge, so (i) is SATISFIED here.
But nothing mechanically prevents a future default-branch workflow edit from combining
`secrets.*` with a checkout of `github.event.pull_request.head.*` and reintroducing the
exact hazard. That gap is recorded as **P2-4**, against the *standing control set*,
not against (i)'s disposition on this snapshot.

I also decline to let the environment-secret observation stand in for a
repository-secret **execution** claim, and no such claim is needed: the assurance
input's own caveat ("it does not prove how a default-branch workflow that actually
checked out a fork head and referenced a repository-wide secret would behave") is
correct, and the answer is that no such workflow exists in the pinned artifact. Had one
existed, (i) would have been BLOCKED, not UNVERIFIED.

**Smallest concrete dependency that would settle the residual** (for P2-4, not to
change (i)'s disposition): a standing, CI-blocking lint over `.github/workflows/**`
that denies any workflow which simultaneously (1) triggers on `pull_request_target`,
(2) references `secrets.` other than `GITHUB_TOKEN`, and (3) checks out or executes
anything derived from `github.event.pull_request.head.*`. This is a pure static check
over committed workflow files, needs **no** new secret, **no** new environment, **no**
remote mutation, and **no** owner-scope expansion — and it converts the current
abstention into enforcement, which makes the untested repository-secret execution path
moot rather than merely unobserved. This is strictly smaller and safer than the
alternative (provisioning a synthetic repository-wide secret on a disposable repo to
observe that `pull_request_target` can read it), which would confirm a documented
GitHub behaviour at the cost of creating a repository-scoped secret — not worth it, and
arguably an owner-scope question.

---

## 6. Blocker findings

### P1-1 — Aliased or wrapped event emitters escape the gate, and the gate reports PASS

**Severity: P1.** **Location:** `tools/validate_architecture_gates.py:1446-1457`
(detection), with the false reassurance at `:1383-1385`.

The matcher accepts only `ast.Name` with `id == "emit_event"` or `ast.Attribute` with
`attr == "emit_event"`. A one-line import alias defeats it. Reproduced by this
reviewer:

```
# app/sneaky.py
from veyro.bus import emit_event as publish
publish("membership.totally.unregistered.v1")
```

Alone in the tree → `status=INCONCLUSIVE`, `EVENT_CONTRACT_GATE_VACUOUS`, `checked=0`.
**Placed alongside one legitimate `emit_event("membership.member-created.v1")` call →
`status=PASS`, `violations=[]`, `checked=["app/flow.py:1"]`.** The unregistered event
is simply invisible, and because `checked` is non-empty the vacuity note never fires,
so the trusted workflow's `NOT_APPLICABLE` guard never engages either and the required
check reports **PASS**.

**Concrete failure scenario:** a module adds `from ... import emit_event as publish`
and emits an unregistered event. Gate 3 passes. TSD §24.1's "every event referenced by
flow/code exists in ... registry" is violated with a green required status. Note also
that the source comment at `:1383-1385` asserts non-canonical calls "fail closed" —
that is **false** for an aliased literal call: it does not fail, it is not seen.

**What would close it:** detect aliases by resolving `import`/`from ... import ... as`
bindings of `emit_event` within each module and treating any call to a bound alias as
an emitter; and make an unresolvable or dynamic emitter-shaped call a **violation**
rather than an omission. Correct the `:1383-1385` comment so it no longer overstates
the guarantee.

### P1-2 — Removing an event from the registry is a breaking compatibility change that requires no approval and raises no violation

**Severity: P1.** **Location:** `tools/validate_architecture_gates.py:1458-1471`.

The change-detection loop iterates `registry.items()` and looks up
`baseline.get(event_id)`. An event present in the **baseline** but **absent** from the
candidate registry is therefore never examined. Reproduced by this reviewer: baseline
containing `membership.member-created.v1`, candidate registry containing only an
unrelated event, no approval anywhere → **`status=PASS`, zero violations**.

Deleting a published event is the maximal compatibility break — every consumer of that
contract breaks — and TSD §24.1 requires owner approval for "compatibility and
classification changes". The trusted workflow wrapper does not catch it either: with
`status=0`, `gate_status=PASS` and `bootstrap=false`, the wrapper reports **PASS**
(`scn020-trusted-event-contract.yml:247-249`).

**Concrete failure scenario:** a PR drops an event from `contracts/events/registry.json`
and also drops its emitter from `backend/app/**`. No `UNREGISTERED_EVENT_CONTRACT`
(no emitter remains) and no `EVENT_CHANGE_UNAPPROVED` (the event is not in the
registry to be iterated). Required check green, published contract silently withdrawn
with no owner approval.

**What would close it:** iterate the union of baseline and registry keys, and treat
`event_id in baseline and event_id not in registry` as an `EVENT_CHANGE_UNAPPROVED`
(or a dedicated `EVENT_REMOVED_UNAPPROVED`) violation unless a matching `OWN-NNN`
approval resolves for that event.

### P2-1 — Registry "schema" is not validated as a JSON Schema, and no AsyncAPI document exists

**Severity: P2.** **Location:** `tools/validate_architecture_gates.py:1391-1405`.

`_event_entries` requires only that `entry["schema"]` be a non-empty `dict`. An entry
such as `{"schema": {"x": 1}, "classification": "internal"}` is accepted as a valid
"JSON Schema object". TSD §24.1 says events must exist in an "AsyncAPI/JSON Schema
registry"; the gate currently enforces registry **membership**, not schema validity,
and there is no AsyncAPI artifact in the picture at all. SCN-008's literal fixture did
carry a genuine JSON Schema, so this does not change its disposition. **Closes by:**
validating each `schema` against the JSON Schema meta-schema (or an explicit,
documented reduction of the clause with the residual disclosed).

### P2-2 — `EVENT_CHANGE_UNAPPROVED` names the changed field but does not cite the diff

**Severity: P2.** **Location:** `tools/validate_architecture_gates.py:1460-1471`.

Observed detail: `"schema changed; missing OWN-NNN approval"`. Both SCN-130
(`SCENARIOS.md:984-987`) and `IMPLEMENTATION.md` §4 row 3 require denial "citing the
event and the unapproved **diff**". The event is cited (as `subject`) and the changed
field is named, but the diff itself — old versus new — is not. This is an
evidence-quality shortfall against the gate's own stated contract and against
`.claude/rules/infra/observability.md` control 1's "named violation type + offending
file/line" standard applied to this gate. **Closes by:** including a bounded
representation of the before/after values (or their hashes) in the violation detail.

### P2-3 — `event-contract.yml` violates `.claude/rules/infra/iac.md` control 5 on both limbs

**Severity: P2.** **Location:** `.github/workflows/event-contract.yml:14` and `:18`.

```
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
```

Both are **floating tags**, not 40-character commit SHAs, and neither action carries an
`APPROVED CAP-<NNN>` row. I verified the registry independently: it holds CAP-001
through CAP-008 (Notion MCP, TestSprite CLI, `docx` skill, core harness tools, Browser
tools, iOS Simulator, `bash_guard.py`, Docker/Colima) and **no** GitHub Action; a
case-insensitive search for `actions/checkout` or `setup-python` in
`CAPABILITY_REGISTRY.md` returns **0** hits. `iac.md` control 5 carries no
publisher-based carve-out, and `CAPABILITY_POLICY.md`'s harness exemption does not
reach a GitHub-published action. Under `iac.md`'s fail-closed clause this file does not
merge in its current form.

Mitigating facts, verified: the file is **absent from upstream default `main`** (404)
and is **untracked** locally, and it is **not** the required context — it is precisely
the candidate-controlled check whose weakness cases (a)/(c) exist to demonstrate. The
trusted workflow, by contrast, reasons about this exact rule in its own header
(`:43-51`) and carries **no** `uses:` line at all, which I verified. It is however
present on the protected disposable base `36457b4d` (the only workflow there), so a
control-5-noncompliant workflow does sit on a protected ref.

**Closes by:** not promoting this file to `main` or any non-disposable branch in its
current form — either delete it with the disposable fixture, or pin both actions to
40-character SHAs **and** take each through the `CAPABILITY_POLICY.md` lifecycle to an
`APPROVED CAP-<NNN>` row first.

### P2-4 — No standing control prevents a future trusted workflow from combining secrets with a fork-head checkout

**Severity: P2.** **Location:** absent control over `.github/workflows/**`; current
safe state at `scn020-trusted-event-contract.yml` (no `secrets.`, no `environment:`,
no executable candidate checkout).

GOV-01-R04's acceptance criterion requires the gate to resist (i)
`pull_request_target` **outright**. On the pinned artifact it does — by abstention, as
reasoned in §5. But abstention is a property of the current bytes, not an enforced
invariant: a future default-branch edit adding `secrets.*` plus a checkout of
`github.event.pull_request.head.*` would reintroduce the full escalation with nothing
to stop it, and `pull_request_target` edits on the default branch do not pass through
the gate they define. **Closes by:** the static workflow lint described at the end of
§5 (deny `pull_request_target` + non-`GITHUB_TOKEN` `secrets.` reference + fork-head
checkout/execution, in one workflow), run as a blocking CI gate.

---

## 7. P3 observations (optional, not blockers)

- **P3-1 — same-name spoof resolution mechanism is unexplained.** §3.4. The single
  live collision denied in the ordering least favourable to the gate (spoof completed
  last and still did not unblock), which is a real result, but GitHub's resolution rule
  for two same-name, same-app check runs on one SHA is not documented or tested here.
  The merge state at head `df68079c` is no longer re-observable. Keep as a disclosed
  residual; do not restate it as a proven structural property.
- **P3-2 — (f) executed against the fork, not upstream.** §4.2. The upstream admin-
  override conclusion rests on independently verified identical protection fields
  (`enforce_admins=true` etc.), not on an executed upstream merge attempt. Reasonable,
  and correctly the safer choice, but worth stating in the scenario record.
- **P3-3 — (g)'s literal fail-closed-on-absence behaviour was never demonstrated.**
  What was tested, and denied, is that a *candidate* cannot induce name drift. The
  scenario's own Expected text additionally asserts that a required context which
  *never reports* leaves the PR permanently non-mergeable. No live state with the
  required context absent was ever produced, so that assertion still rests on
  documented GitHub behaviour rather than on this project's evidence. It does not
  change (g)'s disposition, since the attempted bypass was denied and §3.2 shows the
  candidate cannot reach the definition at all.
- **P3-4 — the trusted gate is installed only for the disposable base.** The trigger is
  `pull_request_target` with `branches: [scn020-protected-base-20261009]`
  (`scn020-trusted-event-contract.yml:56-59`), so the gate does not fire for PRs
  targeting `main`. This is correct for a bounded demonstration and the assurance input
  is honest about it; noted only so no later record reads these nine denials as an
  installed production gate on `main`.
- **P3-5 — adding a brand-new event to the registry needs no approval.** Verified; I
  judge this correct, since TSD §24.1 scopes approval to "compatibility and
  classification changes" and a new event changes no existing contract. Recorded so the
  decision is explicit rather than incidental.

---

## 8. Runtime attestation

Reported from values this reviewer could actually read at runtime. Where something was
not observable, that is stated rather than guessed.

**Observed directly:**

- Model identity, from this session's own environment block: **Opus 5 (1M context)**,
  exact model ID **`claude-opus-5[1m]`**. Knowledge cutoff stated as May 2026.
- `CLAUDE_CODE_SESSION_ID` = **`b3ffd224-4850-45f9-b7d4-45f9d0cb018f`** (corroborated
  by the live session directory
  `/Users/ahmadmabrouk/.claude/projects/-Users-ahmadmabrouk-Desktop-Veyro/b3ffd224-4850-45f9-b7d4-45f9d0cb018f/`).
- `CLAUDE_CODE_CHILD_SESSION` = `1` — i.e. a **child/sub-agent session**, consistent
  with being dispatched by an orchestrating session, which is the required separation
  from the implementing session.
- `CLAUDE_CODE_SESSION_ATTENDED` = `0` (unattended).
- `AI_AGENT` = `claude-code_2-1-274_agent`; `CLAUDE_AGENT_SDK_VERSION` = `0.3.274`;
  `CLAUDE_CODE_ENTRYPOINT` = `sdk-ts`; `CLAUDECODE` = `1`; `CLAUDE_PID` = `55552`;
  `CLAUDE_EFFORT` = `high`.
- Parent harness identifier, visible in my environment but **not mine**:
  `CODEX_SESSION_ID` = `01a11d24-4c1c-7021-8b49-8aeba09a83e7`, with
  `CODEX_HOME=/Users/ahmadmabrouk/.openclaw/agents/veyro-orchestrator/agent/codex-home`.
  Recorded as the dispatching context, not as this reviewer's identity.
- Platform `darwin` / Darwin 27.0.0; shell `zsh`; working directory
  `/Users/ahmadmabrouk/Desktop/Veyro`; review date 2026-10-09.

**Could not be observed, stated plainly:**

- **No runtime value names the project agent role.** Nothing in my environment exposes
  a subagent type or the string `veyro-security-reviewer`. I can attest that I am a
  child Claude Code session running `claude-opus-5[1m]` in a fresh context with the
  gate-3 review mandate; I **cannot** self-attest the named project role from runtime
  data, and I have not invented a plausible-looking value for it. Whoever records this
  review's role binding must take it from the dispatch/authorization record, not from
  this report.
- No per-request/API request id, no operation id, and no reviewer-entitlement token
  were readable from my runtime.

**Mutation attestation.** The only file this review wrote is this report. The five
pinned artifacts were re-hashed after all analysis and are **unchanged** (§2.3).
`git rev-parse HEAD` is still `e481b814a80923849dddfe7a49319112aae7b023`. All
adversarial fixtures were created under `/tmp` (`/tmp/g3rep`, `/tmp/gate3chk`) and
never inside the repository; the live `knowledge/00-System/OWNER_APPROVALS.md` was
never used as an approval root and never modified. All remote interaction was read-only
`gh api` / `gh run view`; no push, no PR change, no protection change, no workflow
re-run, no secret or environment created or read.

---

## 9. Verdict restated

**PASS-with-findings. P0 = 0, P1 = 2, P2 = 4.**

SCN-008, SCN-019, SCN-130 and SCN-020(a)-(i) are each **SATISFIED** on the pinned
artifacts, on independently reproduced or independently read-back evidence. The trusted
required-status boundary holds, and its central non-obvious claim — that
`pull_request_target` reads definition and `github.sha` from the default branch — was
proven here rather than accepted. SCN-020(i) is SATISFIED for the reasons in §5, with
the environment-versus-repository secret distinction decided rather than deferred: it
is not load-bearing for the observed inertness, and the trusted-workflow half of the
hazard is absent by construction.

Two P1 fail-open defects in the gate-3 validator (aliased emitters; unapproved registry
removal) must close before gate 3 can be described as enforcing TSD §24.1's
event-contract clause as worded. Nothing in this report promotes any scenario,
certifies GOV-01-R04, or certifies MOD-001; those remain for the authorities that own
them.
