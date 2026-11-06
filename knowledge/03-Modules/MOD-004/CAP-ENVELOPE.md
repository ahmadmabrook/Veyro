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

| 3 | ADR-0006 drafted to close B7 (D4.3 selection); its independent review | 35 | 209,413 | subagent reported **179,413 tokens exactly**, counted as reported; plus 30,000 estimated and rounded up for drafting and orchestration |

Running total: **100 of 180 minutes, 427,621 of 400,000 tokens.**

## STOPPED — token limit exhausted

**Gap state: `BLOCKED: CAPABILITY_GAP`.** Escalated to the owner at `2026-11-06T07:44:16Z`.

§1.4 of the authorizing record: "The first newly exhausted limit immediately stops qualification
work, returns the gap to `BLOCKED: CAPABILITY_GAP` and escalates to the Opus lead. No renewal,
rollover, silent reset or second candidate set is authorized." The token limit is exceeded by
**27,621**. Qualification work stopped on that line. No counter is reset and no budget is carried
forward.

**What the count rests on, stated so the owner can judge it rather than take it.** Of the 427,621
charged, **297,621 is exactly measured**: the two delegated reviews reported 118,208 and 179,413
tokens themselves. The remaining **130,000 is this session's own orchestration, which has no
per-task counter** and was estimated and rounded up under the method recorded above. Counting only
the measured figures and charging orchestration at zero would give 297,621, inside the limit.

That reading is not taken, for the reason §1.3 and §1.5 give: "Unknown new usage is **not** treated
as zero", and "stop rather than presume remaining budget". Charging orchestration at zero would be
presuming remaining budget from an absence of telemetry, which is the one thing those clauses
forbid. The conservative count governs and the gap is BLOCKED.

**Work in flight when the limit hit, left exactly as it stands.** `ADR-0006` is drafted and staged
but **unpublished**: its independent review returned **CHANGES_REQUESTED** with three blocking
findings, none of which is remediated. They are recorded here so nothing is lost and nothing reads
as closed:

1. The ADR's Context states CAP-EVIDENCE records B2, B3, B4 and B6 "closed", which is stronger than
   that record says. B3 is "VERIFIED in part, CVE applicability OPEN" and B6 is "VERIFIED, with the
   licence question still open". This re-folded the exact misleading summary the B5 reviewer had
   already made this session correct once. §2 condition 1 turns on that position.
2. **An architecture mismatch that would have run an unassessed image.** D1 pins the **linux/arm64**
   manifest and a **macOS arm64** `psycopg-binary` wheel, while D4.2 grants the CI workflow path and
   CI runs on `ubuntu-24.04` (x86_64). Pinning the index digest on an amd64 runner resolves to the
   **amd64** member, which was never verified and carries none of the attestation or SBOM behind the
   139-CVE bookworm position; and the pinned macOS wheel cannot install on that runner at all. So
   literal compliance with D2 in CI would reproduce, across architecture, precisely the hazard D2
   exists to prevent across tags.
3. `Covers: contracts/engineering/` is wider than its stated purpose and is **not** in the
   validator's `CONTROLLED` tuple, so a `check-change` PASS on such a path judges nothing — which the
   ADR does not disclose, though both precedent ADRs disclose the same thing. The prefix also reaches
   `mod004-s0-capability.json`, the S0 forbidden-import closure.

**Therefore B7 is NOT closed.** The selection is drafted, reviewed adversarially, found defective and
not published. `contracts/engineering/module-capabilities.yaml` stays PROVISIONAL with
`gate_eligible: false`; no manifest activation, no Ready-for-S1 judgment and no S1 code follows.

**What a new envelope would buy, if the owner grants one.** Remediating the three findings and one
re-review, then the manifest activation and the Ready-for-S1 judgment with their own review. On
observed costs that is roughly 150,000-250,000 tokens, most of it review. A new envelope is the
owner's own act under the authorizing record's Reserved list; this file grants, resets and
recommends no figure on its own authority.

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
