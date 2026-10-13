---
doc: CAP-008_QUALIFICATION_RECORD
capability: CAP-008 — Docker Engine via Colima/Lima (local) + postgres:16-alpine@pinned-digest; original Docker Desktop binding superseded
status: Current (2026-10-02): first Opus capability review BLOCKED P1=2 -> P1-1 harness fix + APPROVED code review -> P1-2 provenance recorded -> Sonnet stage-5 re-qualification PASS -> distinct fresh Opus capability re-review APPROVED P0=0/P1=0. BUG-038 remains separately OPEN.
run_by: Sonnet (claude-sonnet-5), bounded synthetic/read-only qualification session, 2026-10-01 (original); continued 2026-10-02 (Colima rebind, then P1-1/P1-2 re-qualification)
self_approval: NONE — Sonnet only qualified; distinct attested Opus reviewer approved on 2026-10-02; see current approval addendum
---

# CAP-008 — consolidated stage 1-9 qualification record

## Current approval addendum — 2026-10-02 (supersedes pending-review statements below)

After the Sonnet stage-5 re-run, a **distinct fresh-context, read-only Opus
capability-security re-review APPROVED CAP-008, P0=0/P1=0**. Reviewer:
`veyro-security-reviewer`, `claude-opus-5-5`, ACPX session
`veyro-cap008-colima-opus-r2-20261002`; independent `mr_verify.py` check
PASS, 37 turns, 100% expected model. Full gating-closure and P2 record:
`COLIMA_OPUS_R2_APPROVAL_2026-10-02.md`. Registry `review_status` is now
**APPROVED** for the exact pinned Colima/Postgres binding, with
`approved_by`/`approved_date` and 90-day review due date filled. The first
BLOCKED review and prior QUALIFIED-only statements below are dated history,
not the current gate. **BUG-038 remains OPEN** until separately closed;
SCN-027/067 and R04 are not promoted by this capability decision.

The historical Docker Desktop caveat below applies only to the superseded
Desktop binding. The approved Colima binding does not require a Docker
Desktop licence decision. Any Colima/Lima/CLI/Engine/image version or binding
change fails closed and requires stage-9 re-evaluation before use.

Single accurate status artifact per `CAPABILITY_POLICY.md`'s 9-stage
lifecycle, consolidating this folder's `provenance_and_license.md` and
`negative_test.md`. This record is the handoff package for the required
independent Opus review — it does not itself approve anything.

## Dated supersession — 2026-10-01 12:50 UTC (Colima candidate, not an approval)

The historical stage-5 and caveat text below describes the Docker Desktop
binding at ~11:45 UTC. It is **not current host inventory**: a later, separate
synthetic drill installed and started Colima 0.10.3/Lima 2.2.0 as a local
Docker Engine alternative. Its pinned-Postgres positive probe passed; see
`COLIMA_ALTERNATIVE_DRILL_2026-10-01.md`. No Docker Desktop was activated.
This changes neither the registered CAP-008 definition (still Desktop) nor its
`PENDING` review status. The Colima route is a material provenance/runtime
change requiring a revised binding, independent stage-4/5 review, and a fresh
Opus approval before reliance. The earlier statement that this host has no
non-Desktop backend was true when written but is superseded now. Docker
Desktop free-use eligibility remains unestablished; no inference is made
about it. BUG-038 remains OPEN; Slice-5 promotion and R04 remain blocked.

## Stage 5 completed, Colima binding — 2026-10-02 (supersedes the stage-5/caveats text below, not deleting it)

Fresh stage-4 (official upstream LICENSE files: Colima MIT, Lima
Apache-2.0, Docker Engine/CLI both Apache-2.0) and stage-5 positive +
negative drills ran against the live Colima-backed engine — real
`disposable_postgres()` call, loopback `127.0.0.1`, PostgreSQL 16.15,
pinned digest confirmed via `docker image inspect`, zero leftovers
(positive, PASS); isolated unreachable `DOCKER_HOST` with the Colima VM
left running/untouched (negative, PASS). Full raw commands/results:
`COLIMA_REBIND_PROPOSAL_2026-10-02.md` in this folder.

`CAPABILITY_REGISTRY.md`'s CAP-008 row and its "Version/hash snapshot"
row have been updated accordingly: provenance/version/content_hash now
describe Colima 0.10.3 / Lima 2.2.0 / Docker Engine 29.5.2 / Docker CLI
29.6.0 (pinned Postgres digest unchanged); `review_status` is now
**`QUALIFIED`** (`qualified_by`: Sonnet, this session; `qualified_date`:
2026-10-02) — **not `APPROVED`**. `approved_by`/`approved_date` are
explicitly left blank/pending a fresh independent Opus capability-security
review, per `CAPABILITY_POLICY.md`'s model-routing section (a
`qualified_by`-only row is at most `QUALIFIED`, never `APPROVED`, "no
capability may become `APPROVED` solely from a Sonnet implementation
run"). `BUG-038` remains OPEN and is not touched by this qualification —
bug closure and capability qualification are separate authorities. Slice
5's SCN-MOD001-027/067 remain unpromoted; SCN-067's R04 gap is untouched.

Everything below this section describing the Docker-Desktop-era stage 5
("NOT RUN — blocked", "this machine has no non-Desktop engine backend")
is **historical** — true when written, superseded by the above, kept
for the record rather than deleted.

## Colima stage status at Sonnet re-qualification (historical, before later Opus approval)

| Stage | Current status | Evidence / remaining gate |
|---|---|---|
| 1–3 inventory, gap, bounded discovery | Complete | `BUG-038`, `provenance_and_license.md`, `COLIMA_REBIND_PROPOSAL_2026-10-02.md`. |
| 4 evaluation / 9 material-change re-evaluation | Complete for the current binding | Colima/Lima/Engine/CLI and VM image provenance recorded in `COLIMA_VM_PROVENANCE_2026-10-02.md` (includes the per-tag `docker-v29.5.2` Moby licence correction and the cached VM image SHA-512 match). First independent Opus capability review (`COLIMA_OPUS_REVIEW_2026-10-02.md`) returned **BLOCKED, P0=0/P1=2** against the pre-remediation harness (P1-1 harness-routing gap; P1-2 provenance gap, since closed by the file above). |
| 5 positive/negative qualification | **PASS, re-run against the P1-1-remediated harness** | P1-1 was directly implemented by `veyro-critical-engineer` (`.../implementation/CAP008-P1-1-colima-binding-harness-remediation-2026-10-02.md`) and independently code-reviewed **APPROVED, P0=0/P1=0** (`.../code-review/CAP008-P1-1-colima-binding-code-review-2026-10-02.md`). This session (Sonnet) then re-ran the full reproducible drill script against that reviewed code: 8/8 PASS, exit 0 — positive, unreachable-socket negative, wrong-engine/Desktop-identity negative (safe synthetic endpoint, zero container-create requests reached it), and ambient-Desktop-substitution resistance all confirmed real, raw output in `SONNET_REQUALIFICATION_2026-10-02.md`. Focused unit suite 16/16, full backend suite 51/51, ruff/mypy clean. |
| 6 install/create | N/A | Local infrastructure, not a Skill/Rule install. |
| 7 registration | `QUALIFIED`, not `APPROVED` | `CAPABILITY_REGISTRY.md` names the Colima binding, pinned VM image provenance, and this stage's PASS evidence. `qualified_by`/`qualified_date` populated (Sonnet); `approved_by`/`approved_date` explicitly blank. |
| 8 progressive use | Not unlocked | Only synthetic qualification drills; no R04 or Slice-5 promotion. |

**Summary of the review chain, stated precisely so no step is implied that did not happen:** first Opus capability-security review → **BLOCKED, P1=2**. Harness code review of the P1-1 fix → **APPROVED, P0=0/P1=0** (code only, not the capability). P1-2 VM/engine provenance → **recorded** (`COLIMA_VM_PROVENANCE_2026-10-02.md`, by the orchestrator, not erased or duplicated here). Sonnet stage-5 re-qualification against the reviewed harness → **PASS** (this file + `SONNET_REQUALIFICATION_2026-10-02.md`). **Later superseded by the distinct Opus capability approval in the current addendum above.** This paragraph records the Sonnet checkpoint, when CAP-008 was only QUALIFIED.

## Historical Docker Desktop stage-by-stage status (superseded)

| # | Stage | Status | Evidence |
|---|---|---|---|
| 1 | Inventory | **Done** | No existing `APPROVED` capability covers this gap; CAP-008 confirmed non-duplicate. `provenance_and_license.md` §Stage 1. |
| 2 | Gap detection | **Done** | Re-cited from `BUG-038`'s original filing, not re-derived. `provenance_and_license.md` §Stage 2. |
| 3 | Discovery (bounded) | **Done** | Two named sources only (Docker Engine/Desktop official vendor; official `docker.io/library/postgres` digest). No unbounded source fetched. `provenance_and_license.md` §Stage 3. |
| 4 | Independent evaluation | **Done** (see below) | Harness code audited + image behavior independently verified against real Postgres by Slice-5 `veyro-security-reviewer` (6 hand-mutations, 3 matching implementer kill-counts; FORCE-RLS semantics confirmed) — `knowledge/03-Modules/MOD-001/evidence/security/SLICE5-INDEPENDENT-REVIEW-2026-09-29.md`. Image provenance (`RepoDigests`-traced to official repo) also from that review, not re-run this session (would require daemon up). |
| 5 | Qualification — **positive** test | **NOT RUN — blocked** | Requires Docker daemon running; this session was explicitly instructed not to activate Docker Desktop. Blocker: Docker Desktop license-eligibility category unestablished for this project/owner (`provenance_and_license.md` §License provenance — Docker Desktop). `docker context ls` confirms this machine has no non-Desktop engine backend (`desktop-linux` is the only configured context) — there is no way to run the real capability here without Desktop. |
| 5 | Qualification — **negative** test | **PASS** | Run twice, same result both times (2026-10-01 ~11:37 UTC and ~11:40 UTC, this session): `disposable_postgres()` invoked directly against the real harness with the daemon confirmed down; clean `RuntimeError`, no mock/fallback, zero leftover containers each time. `negative_test.md`. |
| 6 | Install-or-create | **N/A to this capability** | CAP-008 is infrastructure already in use by the harness (pre-existing), not a Skill/Rule being installed. No `ACTIVE` install claim is made. |
| 7 | Registration | **Partial** | Registry row exists (`PENDING`, added 2026-09-29); this session added a dated `updated:` entry and evidence cross-links. `review_status` deliberately left at `PENDING` — registration is not complete until stage 5 (positive) finishes and stage 9's approval runs. |
| 8 | Use progressively | **N/A yet** | Not invoked for real module work this session; qualification drills only, per the fail-closed rule's own stage-4/5 exemption. |
| 9 | Re-evaluate | **N/A yet** | No material change since registration to re-evaluate against. |

## Stage 4 detail — why "independent evaluation" is satisfied without new work here

`CAPABILITY_POLICY.md` stage 4 asks whether the capability's own
instructions/source were read before trusting it, and flags any
instructional text trying to claim authority/override behavior. Docker
Engine and the official `postgres:16-alpine` image are not
instruction-bearing capabilities in the prompt-injection sense (no Skill
description, no MCP tool-result text, no plugin manifest claiming
authority over this session) — the relevant "source" to evaluate is the
harness code that drives them and the image's actual runtime behavior.
Both were independently audited by a fresh-context Opus role (Slice-5
`veyro-security-reviewer`, 2026-09-29): the harness's FORCE-RLS/role
logic was hand-mutated and re-verified against the real running container,
and the image's digest was traced to the official upstream repository.
This session did not repeat that work (it would require the daemon up,
out of scope here) — it formally cites it under stage 4 for the first
time, closing a documentation gap (the citation existed under "mitigating
factors" in `BUG-038` but had not been mapped onto the policy's own
stage numbering until now).

## Historical Docker Desktop scope (superseded by current Colima registry row)

Loopback-only (`127.0.0.1`), synthetic fixture data only, `--rm`/
force-removed disposable containers, zero real member data, zero network
beyond loopback, zero spend. No broader scope is requested or implied by
this record.

## Rollback target (unchanged from registry row)

If this capability must be removed: the harness has no mock/fallback path
by design and would need the GOV-01-R02 tenant-isolation/RLS tests either
retired or re-pointed at a different qualified Postgres substrate — "fall
back to no local Postgres" is the documented rollback, not a silent skip.

## Historical Docker Desktop caveats (superseded by Colima approval above)

The following statements describe the former, unapproved Desktop binding, not current CAP-008. Its licence eligibility and historical spend implications are undetermined owner facts; current approved Colima use is governed by the registry row.

- Docker Desktop license eligibility is an **owner fact**, not inferable
  from repository contents. Until stated, this capability cannot complete
  stage 5's positive leg or proceed toward `QUALIFIED`.
- Even once `QUALIFIED` (both positive and negative evidence present),
  `review_status` may read **at most `QUALIFIED`**, never `APPROVED` —
  `CAPABILITY_POLICY.md`'s model-routing section reserves the
  `APPROVED`/`REJECTED`/`BLOCKED` call for an Opus assurance role in a
  fresh context, reviewing Sonnet-produced evidence, never re-running the
  tests itself.
- A full "runtime attestation" (the positive drill's actual recorded
  output — role/query behavior inside the container, teardown
  confirmation) does not exist yet and is not claimed to exist here.

## Approval chain — current state as of 2026-10-02 (historical text above predates the Colima binding)

- **Self-approval: none.** This session (Sonnet) does not and cannot mark
  `APPROVED` — and did not.
- `review_status` in `CAPABILITY_REGISTRY.md` is now **`QUALIFIED`**
  (Colima binding, `qualified_by`: Sonnet/claude-sonnet-5,
  `qualified_date`: 2026-10-02) — both stage 5 legs (positive and
  negative) now have real passing evidence, which is what moved it past
  the earlier `PENDING` state. It is explicitly **not** `APPROVED`.
- Independent Opus review of the full evidence package (this file +
  `provenance_and_license.md` + `negative_test.md` +
  `COLIMA_ALTERNATIVE_DRILL_2026-10-01.md` +
  `COLIMA_REBIND_PROPOSAL_2026-10-02.md`) **ran and returned BLOCKED,
  P0=0/P1=2**; see `COLIMA_OPUS_REVIEW_2026-10-02.md`. `approved_by`/
  `approved_date` remain blank. The changed harness and VM provenance
  require fresh qualification evidence and an independent re-review.
- Runtime attestation (positive drill) **has now run** against the
  Colima binding (see "Stage 5 completed" above) — the historical "has
  not run" statement below this section described the Docker-Desktop-era
  attempt only.

## Explicitly unaffected by this record

- `BUG-038` remains **OPEN**. Nothing here closes it — bug closure routes
  through its own filer/reviewer chain, not evidence-gathering.
- Slice 5's scenarios (`SCN-MOD001-027`, `SCN-MOD001-067`) are **not**
  promoted to PASS. Both remain BLOCKED pending `BUG-038`'s closure.
  `SCN-MOD001-067` carries an **additional, separate** blocker: the R04
  RLS-lint/permission-lint gates do not exist yet and were not built,
  touched, or implemented by this session.
- No commit or push occurred. No Docker Desktop activation occurred at
  any point. (Historical note: at the time this sentence was first
  written, `docker context ls` showed `desktop-linux` as the only engine
  context on this machine; that was true then and is superseded by the
  Colima binding above — Docker Desktop itself was still never
  activated, in either period.)
