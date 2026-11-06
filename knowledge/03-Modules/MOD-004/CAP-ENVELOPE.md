# MOD-004 — CAP envelope metering, gap BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME

Required by `OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` §1.2, which
requires that before the first qualification action this session record the effective publication
SHA and CI evidence, the start time, and zero new-envelope use, separately from the unchanged
historical counters. This file is that record. It is not evidence for any CAP blocker, closes
nothing, and claims no qualification.

## Envelope

Granted by §1 of that record: **at most 180 active orchestration minutes and 400,000 model
tokens**, for this one gap and the one fixed candidate set in
`contracts/engineering/capability-records/CAP-001-mod004-d123a-prepull.md`.

## Effective start

| Field | Value |
|---|---|
| Record | `knowledge/00-Decisions/OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` |
| Record SHA-256 | `431d609d616cbad70514884950fb2c4dff1240d12278219cb895f187f1e6ba71` |
| Publication commit | `e8bf2602440066552b6adbcdca67d4d8381465ad` |
| Exact-SHA push CI | run `42178930388`, event `push`, completed, conclusion `success` |
| Attestation SHA-256 | `cbccc046057db6c22d0bf2ca60364f0d0395e1976fbd8b303e6a580d4a9d8f5c` (as recorded by `first_publish_audit`, basis "operator attestation, not cryptographic proof") |
| Effective start (UTC) | `2026-11-06T07:12:40Z` |
| New-envelope minutes used at start | **0** |
| New-envelope model tokens used at start | **0** |

## Historical counters, unchanged

The prior envelope of 45 active orchestration minutes and 50,000 model tokens
(`OWNER-2026-10-19-mod004-cap-budget-exception.md`) stays recorded as **exhausted**
(`OWNER-2026-10-19-mod004-s0-only.md`). Earlier attempt use for this gap stays recorded as
**UNKNOWN**, not zero. Nothing above resets, reconciles or supersedes any historical counter, and
this file adds no budget.

Work done before the effective start above is outside this envelope by definition, because §1.2
meters from that start. That specifically includes drafting, reviewing and publishing the
authorizing record itself, which was not gap qualification work: its two review rounds are
recorded in that record's own history and are not charged here. Nothing is charged here
retroactively and nothing earlier is re-characterised as free.

## Metering method, and what it cannot do

§1.3 requires counting all gap-specific active orchestration time and model tokens, evidence
gathering and review included, and §1.5 requires stopping rather than presuming remaining budget
where telemetry is unavailable or new usage cannot be reconciled. Both limits are stated here
rather than discovered later.

**What is measurable.** Delegated subagent work reports its own exact token count on completion,
so every independent review and every delegated evidence task is counted exactly. Wall-clock time
is measurable from timestamps.

**What is not.** This session has no cumulative per-task model-token counter for its own
orchestration. The per-turn budget counter resets each turn, and context-window occupancy measures
how full the conversation is, not tokens consumed, and is not attributable to one gap. Account plan
telemetry reports only percent-used of 5-hour and weekly windows for the whole account, which is
not task-attributable.

**Therefore the count below is deliberately conservative and rounds up.** Orchestration tokens are
estimated from context growth attributable to this gap's work and rounded up to the nearest 10,000;
subagent tokens are counted exactly as reported; minutes are rounded up to the nearest whole
minute. Overcounting satisfies §1.5's purpose, which is to prevent presuming remaining budget: an
overcount stops work early and never late. Where an amount cannot be attributed at all it is
recorded as unknown and charged at the conservative upper bound, never at zero.

**Stop rule.** The first limit reached under this conservative count stops qualification work,
returns the gap to `BLOCKED: CAPABILITY_GAP` and escalates. No renewal, rollover or reset follows,
and no second candidate set is authorized.

## Ledger

| Entry | Activity | Minutes (rounded up) | Tokens | Basis |
|---|---|---|---|---|
| 0 | Envelope start; no qualification action yet | 0 | 0 | this record |
| 1 | B2 free-runtime terms; B4 wheel and transitive hashes against PyPI; B3 image digest and attestation binding by rehash; Colima start and context move; pull of the pinned image by digest; B6 wheel inventory, embedded OpenSSL version, OpenSSL advisory enumeration and the one-High reachability judgment; writing [CAP-EVIDENCE.md](CAP-EVIDENCE.md) | 40 | 80,000 | wall clock from the effective start to `2026-11-06T07:20:56Z`, rounded up; tokens estimated from this session's per-turn budget deltas across the turns doing this work, rounded up to the nearest 10,000 as the method above requires |

| 2 | B5 independent fetch verification (delegated); correcting the B6 contradiction it found and folding in its three understatements | 25 | 138,208 | subagent reported **118,208 tokens exactly**, counted as reported; plus 20,000 estimated and rounded up for this session's orchestration of the dispatch and the corrections |

Running total: **65 of 180 minutes, 218,208 of 400,000 tokens.** Remaining: **115 minutes,
181,792 tokens.**

The B5 charge came in well under the ~200,000 feared above, at 118,208, because the brief was
written as eleven specific claims to verify rather than an open re-derivation. That is the pattern
to keep for the remaining reviews: the manifest activation and the Ready-for-S1 judgment each need
one, and together they must fit inside what is left.

Entry 1 includes a recorded sequencing deviation: the image pull and the wheel fetch preceded
conditions 2 (B5) and 4 (B7/D4.3), contrary to §2's "Nothing is pulled until conditions 1-6 …
hold". See the deviation section of [CAP-EVIDENCE.md](CAP-EVIDENCE.md). The work is charged
normally; a breach is not made cheaper by being disclosed.

The token figure is an estimate under the stated method, not a telemetry reading, and is rounded
up. It is not offered as an exact count. The largest single remaining charge is expected to be the
B5 independent fetch review, since observed independent reviews in this project have cost on the
order of 200,000 tokens each; that is the reason the B5 brief is written narrowly rather than as a
full re-derivation.
