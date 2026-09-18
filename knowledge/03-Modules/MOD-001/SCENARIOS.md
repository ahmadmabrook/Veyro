---
doc: MOD-001_SCENARIOS
status: LIVE — DRAFT, AUTHORED, INDEPENDENTLY REVIEWED (multiple rounds to date, each BLOCKED and remediated — current round count lives in §5 only, not restated here; not yet APPROVED)
module: MOD-001
updated: 2026-09-19 (Scenario Review round 13 ran, BLOCKED, P0/P1/P2/Editorial remediated — round 12's own remediation held on most of what it framed itself around, but its own gate-1 fix left an unconstructible fixture pair, its own gate-6 residual miscounted its own arithmetic, and its own two new scenarios (SCN-138/139) shipped with no manual-surface mapping; see §5)
---

# MOD-001 — Scenario Catalog

Authored per EIP §9.1 (Required Scenario Rule, `EIP_MIRROR.md` lines
1852-1886), Appendix G (Per-Module Required Scenario Category Matrix,
lines 19566-20069), the MOD-001 execution card's own manual-QA/scenario
fields (lines 4183-4231), and the mission's explicit named scenario
families. **Corrected (Scenario Review round 4, P0-2): this line and §4
below previously claimed "no scenario is marked PASS" / all scenarios
"NOT EXECUTED" without qualification — false since round 3, when the
model-routing-drill scenarios (104/105) were genuinely executed.**
Implementation has not started; every scenario **except the model-
routing drill (104/105, which tests this project's own routing
configuration, not MOD-001's own implementation)** is `NOT EXECUTED`
until real code exists to run it against. This catalog exists to be
independently reviewed (`veyro-scenario-reviewer`, Opus, fresh context
— see the Review Log at the end of this file) before Definition of
Ready.

**Clarified (Scenario Review round 8, P1-2): every detail block's
"Lifecycle role/model" field names the agent that executes and judges
the scenario's check at manual-QA/execution time — the agent that runs
the fixture and confirms pass/deny — not necessarily the agent that
authors the underlying implementation code or test-harness fixture
during real implementation. Those are two different questions: who
proves this scenario's expected result true (this field), versus who
writes the code the scenario exercises. `BUG-032`'s closure made
deterministic test authoring an explicit `veyro-implementer`→
`veyro-test-author` escalation for *authoring* work; this catalog's
own field was never meant to enumerate every scenario's fixture-author
by that rule, and none of this catalog's detail blocks name
`veyro-test-author` as their Lifecycle role for exactly that reason —
its role is upstream
of scenario execution, not a substitute lifecycle-role assignment for
scenarios whose steps happen to read as "author a fixture."**

## 0. Category legend (Appendix G)

HP=Happy path · ALT=Alternate flow (Optional for MOD-001 per Appendix G
— O, not R) · VAL=Validation · NEG=Negative · BND=Boundary ·
AUTHN=Authentication · AUTHZ=Authorization · TEN=Tenant isolation ·
SEC=Security · PRIV=Privacy · CONC=Concurrency · IDEM=Idempotency ·
NET=Network failure · PART=Partition/degraded dependency ·
OFF=Offline/edge · REC=Recovery · LIFE=Life-safety/irreversible
consequence · DATA=Data integrity/handling · INT=Integration ·
LOC=Localization (RTL/Arabic) · A11Y=Accessibility · PERF=Performance/load
· OBS=Observability · MIG=Migration · DR=Disaster recovery.

**Minimum Required count (EIP §9.1):** **Corrected (Scenario Review
round 1, P2-2):** the original text here understated the governing rule
by claiming "§9.1 does not name a Foundation/Control-specific floor
directly" and using 8 as the operative floor. §9.1 (`EIP_MIRROR.md`
lines 1874-1880) actually names risk-based floors including
"concurrency/security-critical ≥ 24" and, most directly, "**release/
system gates use the complete included critical-journey catalog**" —
MOD-001 sits in Appendix G's Foundation/Control risk class
(`EIP_MIRROR.md` line 19585) but is treated as security-critical
throughout this catalog — Blocker-severity scenarios touching
SEC/AUTHZ/TEN/AUTHN run throughout it, not concentrated in one place
(**corrected, Scenario Review round 10, P2-1/Editorial-3: this line
previously miscited MOD-001 as "the release/system-gate module,"
Appendix G's own risk-class column reserves that term for a different
module tier, and previously pinned a Blocker-scenario count ("16") that
had already gone stale — deliberately not replaced with a fresher
pinned number, per this same paragraph's own lesson two sentences
below**). The correct floor is
therefore "the complete included critical-journey catalog," not a fixed
number — every requirement, gate, and validator this module owns needs
its own real scenario, which is what §3 below now provides. The 8-Critical-requirements
floor (GOV-01-R01..R08) remains true as an absolute minimum but was
never the operative constraint. **This catalog's total count is stated
once, here, and deliberately not restated in any other LIVE-status
document — every prior round that duplicated this number in a second
LIVE document found that copy going stale within the same round (round
4 found exactly this had happened to `CURRENT_STATE.md`, which is now
corrected to point here rather than restate a number). Corrected
(Scenario Review round 11, Editorial-2): the prior "or elsewhere"
wording was inaccurate against `CURRENT_HANDOFF.md`'s own append-only
chunk log, which legitimately records the count a given round found as
dated history, not a live restatement — narrowed to say what is
actually meant.** Current total: **140 detail
blocks** (001-121 plus 021b, 122, 123, 124, 125, 126, 127, 128, 129,
130, 131, 132, 133, 134, 135, 136, 137, 138, 139) — **140 Required + 0 Optional** —
comfortably above every applicable floor. **Round 12 (P0-1) added
138/139** to close a genuine gap its own fresh review found: round 11's
own new gate-7 build/toolchain carve-out (added round 11, P2-1) was an
untested pass-path through a Blocking gate — no scenario exercised
either the carve-out itself or its own boundary against application
code sharing the same deferred surface. **Round 11 (P1-5) added 137**
to close a genuine false-coverage claim its own fresh review found:
`SCN-106` named `001`/`002` as GOV-01-R01's per-layer harness positive
companion, but neither scenario runs any of the 6 automated
test-pyramid layers against a passing fixture at all. **Round 10 (P0-1/P0-2/P0-3)
added 130-136** to close three genuine gaps its own fresh review found:
TSD §24.1 gates 3 and 6's normative owner-approval/shared-contract-
exception sub-clauses, disclosed unfixtured since round 1 and carried
nine rounds (130/131); GOV-01-R02's six named critical-workflow suite
scaffolds and its financial-invariant test harness, both committed to
in `REQUIREMENTS.md`'s own text but never built into the topology or
tested (132/133); and the scanning stage's SAST/container/IaC thirds,
which had no positive scenario at all — the only related scenario is an
owner-reserved denial drill proving the opposite (134/135/136). **Round
5
(P0-2) added 122/123** to close a genuine coverage gap on the card's
mandatory security baseline (sensitive logging, abuse-negative
scenarios) that this section's own "every requirement... needs its own
real scenario" claim had been false against until that round. **Round
7 (P0-1/P1-5) added 124/125** to close the baseline-artifact-binding
validator's remaining 4 fail-closed conditions and GOV-01-R08's
maintenance/customer-communication gap, the same species of coverage
gap. **Round 8 (P0-1) added 126** to close the same mandatory Security
baseline's third, previously-miscounted item ("input/output data
exposure") — round 5 itself said "three controls" were uncovered but
named only two; the third survived rounds 6 and 7 undetected. **Round 9
(P0-1) added 127/128/129** to close a genuine gap round 8 itself
disclosed but did not close: three TSD §24.3 rules (white-label
metadata, KMP shared-module versioning, toolchain-consistency-against-
real-config) that round 8's own "covered by existing scenario
families" disposition was independently found false against
(`IMPLEMENTATION.md`'s own text says the opposite), plus two Blocking
CI gates (the isolated-PR toolchain-qualification gate, the
capability-adapter smoke-test half) that round 8 disclosed as a
residual in violation of §9.1's own "Required is rule-derived, never a
discretionary reduction" rule. **Round 6
(P1-3) reclassified 071/072 from Optional/ALT to Required** (HP and REC
respectively) — both trace to a Critical GOV-01 requirement, which
§9.1 makes Required regardless of ALT's category-level Optional
default; 0 Optional scenarios currently exist, which is legitimate for
an O-classified category (Optional means not mandated, not forbidden
at zero), not a coverage gap.

## 1. Category coverage matrix

**Corrected (Scenario Review round 1, P1-1/P2-1):** the original version
of this table double-counted 005 under AUTHN (its detail block was
actually tagged SEC) and 059 under REC (its detail block was actually
tagged DR-only), leaving AUTHN with a single real scenario — a direct
contradiction of the "at least 2" claim below. Both are fixed: 005 is
now genuinely dual-relevant (recategorized AUTHN in its own detail
block, §3) and 097 was added as a distinct second AUTHN scenario; REC's
real second scenario is 066 (058 + 066), with 059 correctly DR-only.
SCN-073/074 were reclassified out of ALT into their substantive
categories (INT, PERF) per P2-10 (§3 rationale in their own blocks) and
27 new scenarios (075-101) were added closing P0-1, P0-2, P0-4, P1-2,
P1-5, and four P2-7 negative companions. **Round 2 (P1-1) found this
table's own "independently verified against each detail block" claim
was false in 4 places at the time: 075 was listed under AUTHN but
tagged SEC in its own block; 067 was silently dual-counted under TEN
and LIFE though tagged LIFE only; 042 and 084 (both tagged SEC) appeared
in no row at all.** All four corrected below — 075 moved to SEC (where
its detail block actually tags it); 067 removed from TEN (LIFE-only,
matching its tag; TEN's floor still holds at 3 without it); 042 and 084
added to SEC. Every category MOD-001 is Required for (Appendix G row,
all R except ALT=O) is covered by at least 2 real scenarios; this table
was re-verified against each entry's own detail-block tag as part of
round 2's remediation, not merely re-asserted:

| Category | R/O | Scenario IDs |
|---|---|---|
| HP | R | 001, 010, 023, 036, 041, 048, 055, 071, 137 |
| ALT | O | none — **corrected, Scenario Review round 6 P1-3: both 071/072 reclassified Required (see HP/REC rows) since each traces to a Critical GOV-01 requirement, which §9.1 makes Required regardless of category-level Optional status; 0 Optional scenarios is legitimate for an O-classified category, not a gap** |
| VAL | R | 002, 024, 037 |
| NEG | R | 003, 011, 019, 025, 038, 049, 056, 062, 106, 109, 123, 124 |
| BND | R | 004, 012, 026, 085, 087, 088, 089, 090, 110, 116, 118 |
| AUTHN | R | 005, 027, 097 |
| AUTHZ | R | 006, 013, 028, 092, 095 |
| TEN | R | 007, 014, 096 |
| SEC | R | 008, 015, 020, 029, 042, 057, 063, 064, 075, 076-083, 084, 086, 094, 098, 102-105, 112, 120, 122, 126, 130, 131, 133, 134, 135, 136, 138, 139 |
| PRIV | R | 043, 065 |
| CONC | R | 009, 044 |
| IDEM | R | 016, 045 |
| NET | R | 030, 046 |
| PART | R | 031, 047 |
| OFF | R | 032, 050 |
| REC | R | 058, 066, 072 |
| LIFE | R | 060, 067 |
| DATA | R | 017, 033, 051, 099, 114, 127, 132 |
| INT | R | 018, 034, 052, 073, 100, 115 |
| LOC | R | 039, 053 |
| A11Y | R | 040, 054 |
| PERF | R | 068, 069, 074, 101, 111, 128, 129 |
| OBS | R | 021, 021b, 035, 061, 091, 093, 107, 117, 119, 121, 125 |
| MIG | R | 022, 070, 113 |
| DR | R | 059, 066, 108 |

No category rests on a single scenario (every row lists ≥2 IDs; several
of the added Group K entries reinforce SEC and BND, which own most of
the capability-governance/scenario-matrix fail-closed drills). **Corrected
(Scenario Review round 3, P0-2): the sentence that used to stand here
("042 was removed from SEC's row...") described an intermediate,
since-superseded state and was never updated when 042 was added back to
SEC's row during round 2's own remediation — it directly contradicted
the table two paragraphs above it. Removed. `042` is correctly listed
under SEC above, and also under "Artifact integrity/signing" in §2,
alongside its real negative companion 063 — a scenario legitimately
appearing in two places (its own category row and a named-family row)
is normal, not a contradiction.** **Corrected (Scenario Review round 7,
P1-1): the sentence that used to stand here ("071 and 072 remain
genuine alternate-flow variants that do not themselves assert
gate/acceptance-contract behavior") flatly contradicted round 6's own
P1-3 fix three lines above, which reclassified both Required precisely
because they DO assert such behavior (072's own detail block: "its
'still promotes/rolls-back correctly' expected result IS GOV-01-R05's
own acceptance criterion") — the identical stale-paragraph-above-the-
table species round 3's P0-2 removed for SEC, reintroduced here by
round 6's own remediation never touching this paragraph.** The `O`
category (ALT) currently has 0 scenarios, which is legitimate for an
O-classified category — see the ALT row above and §0's own correction.

## 2. Named-family coverage (mission section 16, cross-checked)

**Corrected (Scenario Review round 1):** three rows below were wrong in
the original — Gate-bypass (P1-3, 029 didn't test a bypass), Rule-family
coverage (P1-2, 042/057 didn't test rule families at all), Dependency
vulnerability (P0-4, 015 didn't test a vulnerable dependency) — all
fixed to point at real, on-topic scenarios, most newly authored in
Group K.

| Named family | Scenario IDs |
|---|---|
| Repository skeleton correctness | 001, 002, 003 |
| Architecture boundary enforcement (6 gates, positive+negative) | 004-015, 095, 096 |
| CI gate success | 001, 023 |
| CI gate deliberate failure | 011, 019, 025, 038 |
| Gate-bypass attempts | 020 (corrected to the CI-workflow-configuration threat model — see its own detail block) |
| Baseline mismatch | 025, 026 |
| Schema compatibility | 034 |
| Migration safety | 022, 070 |
| Contract compatibility | 018, 034 |
| Capability/registry integrity | 021, 076-083 |
| Rule-family coverage | 035 (positive), 084 (negative — corrected; was 042/057, which tested artifact signing and release-evidence tamper-evidence, not rule families) |
| Dependency vulnerability | 094 (corrected; was 015, a domain-contract-collision scenario that never tested a vulnerable dependency) |
| Secret leak detection | 008, 029 |
| Artifact integrity/signing | 042, 063 |
| Local environment bootstrap | 036 |
| QA environment bootstrap | 037, 038 |
| Staging environment bootstrap without production activation | 041, 049 |
| Rollback behavior | 058, 059, 060 |
| Feature-flag/release controls | 044, 045 |
| Mobile-version/release policy | 115 (the actual version-support/kill-switch policy, corrected round 2 P1-10 — was 052-054/099-101, which test dual-platform-trigger/RTL/a11y/runner-assignment, not this policy), 117, 127, 128, 129 (**row extended round 10, P2-4 — this row had stopped being extended after round 4 while 117/127/128/129 were added to the same named family across rounds 7 and 9**) |
| Deterministic regression | 061 |
| TestSprite integration scope | 062 |
| CI runner smoke-load | 068 |
| Environment smoke-load | 069 |
| Fresh clone/bootstrap | 001, 036 |
| Notion/Git/knowledge state reconciliation | 021 (its own reconciliation sub-clause specifically — see §3's note on this scenario's two distinct checks) |
| Owner-reserved production/spend/data denial | 056, 060, 064, 065 |
| Model-assurance forced-fallback (not separately named in the mission's list but mandatory per EIP_MIRROR.md lines 1109-1111) | 075 |
| Additional capability-governance/scenario-matrix/external-gate/Appendix-I fail-closed drills (P0-2, not separately named but required by the module card's own manual-QA field) | 076-093 |
| GOV-01-R01 per-layer deliberate-failure proof (NEG), mis-tagged-boundary case (BND), and per-layer positive execution (HP) (added round 2 P0-2, corrected/split round 3 P1-2, extended round 11 with 137 — **row updated round 12, P2-3: 137 had joined the catalog in round 11 but never joined this row**) | 106, 116, 137 |
| GOV-01-R08 release-train/changelog/lifecycle-stage lint (added round 2, P0-2) | 107, 108 |
| Card-mandated test-failure and screen-count drills (added round 2, P0-3) | 109, 110 |
| Gate-bypass-under-load (added round 2, P1-5) | 111 |
| Surface-profile activation, no-marker-at-all case (added round 2, P1-6); deferred-surface build/toolchain carve-out, positive and boundary (added round 12, P0-1) | 112, 138, 139 |
| GOV-01-R06 rolling-deploy compatibility and migration-record template (added round 2, P1-9) | 113, 114 |
| Appendix F import/validation contract (added round 4, P1-5) | 118 |
| Appendix I ADR conformance, ADR-004/ADR-015 (added round 4, P1-6) | 119 |
| Agent-definition/MR-evidence well-formedness validator (added round 4, P1-7) | 120 |
| Appendix H.1 manifest completeness (added round 4, P1-8) | 121 |
| Card-mandated Security baseline: sensitive logging, abuse-negative, input/output data exposure (added round 5 P0-2, round 6 P1-1, round 8 P0-1 — **row added round 10, P2-4**, this table had stopped being extended after round 4 even as these three scenarios joined the catalog) | 122, 123, 126 |
| TSD §24.3 toolchain-matrix real-config/white-label/KMP-versioning, isolated-PR qualification gate, capability-adapter smoke (added round 9 P0-1 — **row added round 10, P2-4**) | 127, 128, 129 |
| TSD §24.1 gates 3/6 owner-approval and shared-contract-exception sub-clauses (added round 10, P0-1) | 130, 131 |
| GOV-01-R02 six named domain suite scaffolds and financial-invariant test harness (added round 10, P0-2) | 132, 133 |
| Scanning-stage SAST/container/IaC (added round 10, P0-3) | 134, 135, 136 |

**Corrected (Scenario Review round 3, P2, further corrected round 4,
round 10): this file, `STATUS.md`, and this section's own historical
prose had disagreed with each other on the row count (29 vs 33) — both
were wrong; the table above had 39 rows through round 4, then stopped
being extended even as 15 more scenarios (122-136) joined the catalog
across rounds 5-10 — round 10 (P2-4) added the 5 rows above, bringing
the table to 44 rows.** All 44 rows have real, on-topic,
independently-checkable coverage — this count is stated once, here; no
other file restates it.

## 3. Scenario detail

Format per scenario: **ID · Category · Priority · Requirement trace ·
Automation · Lifecycle role/model tier · Status**, then Preconditions /
Steps / Expected result / Evidence requirement / Negative-failure
behavior. Scenarios sharing identical preconditions/evidence within a
group say so explicitly rather than repeating verbatim.

**Note on "Automation" vs. manual execution (added, Scenario Review
round 1, P1-8):** Appendix G's own header (`EIP_MIRROR.md` line 19568)
and §9.1 (lines 1867-1868) both require every Required scenario to be
"manually executed by Claude" / undergo "actual Claude manual execution
under §12 before module approval" — this applies regardless of a
scenario's "Automation" field, which describes how the *check itself*
runs (a script vs. a human-only judgment), not whether Claude must
personally trigger and observe it at least once before approval. An
"Automated" scenario still requires a fresh-context Claude session to
actually run the automated check and observe its real output at least
once before MOD-001 can be approved — DC-04/DC-05 (`DEVELOPMENT_CONSTITUTION.md`
lines 35-39, 101) forbid treating a written-but-never-run script as
equivalent to executed evidence. `MANUAL_QA.md` now carries an explicit
scenario→manual-surface mapping (its own §2) rather than leaving this
implicit, closing the gap round 1's review found (most Required
scenarios at that round had no manual-execution disposition at all —
the exact count is not restated here since the catalog has grown twice
since; `MANUAL_QA.md` §2's own mapping is the current, authoritative
coverage record).

### Group A — Repository skeleton (GOV-01-R01, IMPLEMENTATION.md §1)

**SCN-MOD001-001 · HP · Major · GOV-01-R01 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Preconditions: a genuinely fresh clone of the repo at the commit
implementing MOD-001's skeleton. Steps: run the documented bootstrap
command sequence exactly as committed. Expected: `backend/`,
`admin-web/`, `frontdesk-web/`, `mobile/`, `contracts/`, `infra/`,
`.github/workflows/`, `tools/` all exist with the structure named in
`IMPLEMENTATION.md` §1; no step requires undocumented tribal knowledge.
Evidence: a transcript of the bootstrap run, start to finish, with no
manual intervention. Negative/failure behavior: if any documented step
fails, the bootstrap script itself reports which step and why, rather
than silently continuing.

**SCN-MOD001-002 · VAL · Major · GOV-01-R01 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Preconditions: same clone as 001. Steps: run the format/lint/type-check
CI stage locally against the fresh skeleton (no product code yet).
Expected: passes cleanly on the empty/scaffold-only tree — a linter that
fails on its own scaffold is itself a defect. Evidence: lint report,
0 errors. Negative: a deliberately malformed file (e.g. invalid
`pyproject.toml` syntax) is proven to fail the same lint step.

**SCN-MOD001-003 · NEG · Major · GOV-01-R01 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Preconditions: same clone. Steps: delete a required top-level directory
(e.g. `contracts/`) and re-run the bootstrap/lint check. Expected: the
check fails closed with a named "missing required directory" error, not
a silent partial success. Evidence: failure log naming the missing path.
Negative behavior IS this scenario's own subject.

### Group B — Six architecture gates (GOV-01-R04, TSD §24.1, IMPLEMENTATION.md §4)

Preconditions shared across all of Group B unless stated: a synthetic
fixture schema/contract set created solely for the test, never the real
project's own `knowledge/` or governing baselines. Evidence shared: a
named violation-type report (or clean pass) written to
`evidence/security/<GATE>_GATE_FIXTURE_<date>.md`.

**SCN-MOD001-004 · BND · Blocker · GOV-01-R04, TSD §24.1 gate 1 (RLS) · Automated · veyro-security-reviewer/Opus (judgment), veyro-implementer/Sonnet (mechanical run) · NOT EXECUTED**
Steps: create a synthetic tenant table with `tenant_id NOT NULL`, RLS
policy, `FORCE ROW LEVEL SECURITY`, **owned by a role distinct from the
production-equivalent runtime role, with the runtime role granted
neither ownership nor `BYPASSRLS`** (added, Scenario Review round 13,
P0-1 — round 12's own P0-2 fix added an elevated-role violation case to
005 that mutates "the 004 fixture," but 004 as written specified no
ownership/role-attribute condition at all, leaving 005(i) unconstructible
and 004 itself satisfiable by a fixture gate 1 must deny; this line
closes that for real, matching `IMPLEMENTATION.md` §4 gate 1's own
valid-fixture cell); run `validate_architecture_gates.py --gate rls`.
Expected: PASS. Negative failure behavior: covered by 005.

**SCN-MOD001-005 · AUTHN · Blocker · GOV-01-R04, TSD §24.1 gate 1 (RLS) · Automated · veyro-security-reviewer/Opus (judgment) · NOT EXECUTED**
**Corrected (Scenario Review round 1, P1-4):** TSD §24.1 (`TSD_MIRROR.md`
lines 11599-11601) is explicit — "runtime role cannot own/bypass.
Negative isolation tests run with **production-equivalent role**," i.e.
a *non-privileged* role, never `BYPASSRLS`. The original draft of this
scenario used a `BYPASSRLS`-capable role, which returns cross-tenant
rows by definition and would have made the "expected 0 rows" result
either meaningless or silently dependent on the fixture not actually
using `BYPASSRLS` — corrected to match `REQUIREMENTS.md`'s own (already
correct) GOV-01-R02 text and the real TSD rule. Steps: same fixture as
004, but `FORCE ROW LEVEL SECURITY` omitted, and a query run as the
**production-equivalent, non-privileged runtime role** (no elevated
attribute) attempts a cross-tenant read. Expected: gate denies with
`RLS_NOT_ENFORCED` citing the table; the query itself (run against a
real Postgres fixture) returns 0 cross-tenant rows under that
non-privileged role — this is the same class of drill this project's
own `bash_guard.py` history already established a pattern for
(deliberate-violation proof, not theoretical). Recategorized AUTHN
(alongside its original SEC framing — a role-based access denial is
both) so AUTHN has genuine, non-single-scenario coverage; see 097 for a
distinct AUTHN scenario testing successful authentication rather than a
denial. **Extended (Scenario Review round 12, P0-2): the same TSD
sentence's other two clauses — "runtime role cannot own/bypass" and a
nullable `tenant_id` — had no fixture of their own, disclosed as an
untested Blocker-tier gap eleven rounds after round 1 first corrected
this scenario's role attribute. Two further fixtures added: (i) the
004 fixture, `FORCE ROW LEVEL SECURITY` present, but owned by the
runtime role itself (or the runtime role granted `BYPASSRLS`) — expected
`RLS_RUNTIME_ROLE_ELEVATED` denial citing the role/table pair, distinct
from the missing-FORCE case above; (ii) the 004 fixture with
`tenant_id` declared nullable — expected `RLS_TENANT_ID_NULLABLE`
denial citing the column. Evidence for both: the gate's own denial
report, same mechanism as the missing-FORCE case.**

**SCN-MOD001-006 · AUTHZ · Blocker · GOV-01-R04, TSD §24.1 gate 2 (module dependency/SQL) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a synthetic module importing only its own owned table
prefix/approved read-model interface. Expected: PASS.

**SCN-MOD001-007 · TEN · Blocker · GOV-01-R04, TSD §24.1 gate 2 · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a synthetic module directly importing another module's raw
table/ORM model. Expected: `CROSS_DOMAIN_SQL_IMPORT` denial citing both
modules — proves DOM-001 (Appendix I).

**SCN-MOD001-008 · SEC · Blocker · GOV-01-R04, TSD §24.1 gate 3 (event contract) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a synthetic event referenced in code with a matching AsyncAPI/
JSON-Schema registry entry. Expected: PASS. Negative case: 019.

**SCN-MOD001-009 · CONC · Major · GOV-01-R04, TSD §24.1 gate 2 (DOM-002) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a synthetic mutable aggregate updated by two concurrent
"requests" (simulated, not real load); optimistic-versioning check
proves the second write detects a version conflict rather than silently
overwriting (lost-update behavior explicit, per DOM-002). Evidence: both
write attempts' outcomes logged; exactly one succeeds, one gets a
version-conflict error.

**SCN-MOD001-010 · HP · Major · GOV-01-R04, TSD §24.1 gate 4 (permission) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a synthetic command declaring `action`/`resource`/`scope`.
Expected: PASS.

**SCN-MOD001-011 · NEG · Blocker · GOV-01-R04, TSD §24.1 gate 4 · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a synthetic command with an undeclared permission name. Expected:
`UNREGISTERED_PERMISSION` denial — proves IAM-002 (Appendix I: "authz
enforced in the domain application layer even when the UI hides an
action").

**SCN-MOD001-012 · BND · Major · GOV-01-R04, TSD §24.1 gate 5 (screen contract) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a synthetic Screen ID mapped to a BFF/command manifest row.
Expected: PASS. Real-world note: MOD-001 owns zero real screens
(`REQUIREMENTS.md` §4) — this fixture is synthetic by necessity, not a
gap.

**SCN-MOD001-013 · AUTHZ · Major · GOV-01-R04, TSD §24.1 gate 5 · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 1, tier-consistency note): routed to
Sonnet in the original draft while the structurally identical gate-4
violation (011) routed to Opus — aligned to Opus, matching every other
gate-violation judgment call in this catalog.**
Steps: a synthetic Screen ID with no mapped BFF/command row. Expected:
`UNMAPPED_SCREEN_CONTRACT` denial.

**SCN-MOD001-014 · TEN · Major · GOV-01-R04, TSD §24.1 gate 6 (domain contract uniqueness) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: two synthetic domains with disjoint authoritative-entity sets,
command inventories, published-event sets, runbook IDs, SLI/SLO signal
names, **and failure-vocabulary** (**corrected, Scenario Review round
13, P1-4: this previously named only 4 of the 6 dimensions —
`IMPLEMENTATION.md` §4's gate-6 valid-fixture cell was corrected to all
6 in round 12, P0-2, but that fix was never propagated to this
scenario, the one that actually executes the positive case; passing
this scenario as originally written would not prove what the plan's
own gate-6 row now claims**). Expected: PASS.

**SCN-MOD001-015 · SEC · Blocker · GOV-01-R04, TSD §24.1 gate 6 · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: two synthetic domains reusing an identical `RB-<DOMAIN>` ID, and
separately, a domain SLO naming a foreign domain's signal (e.g.
booking-capacity in a billing SLO); **and (added, Scenario Review round
12, P0-2 — `TSD_MIRROR.md` lines 11643-11653 names an identical
command inventory as a fail condition independent of the RB-ID case,
and no fixture had ever tested it; only the RB-ID case was fixtured
across eleven rounds) two synthetic domains declaring byte-identical
command inventories, with no shared-contract exception on record**;
**and (added, Scenario Review round 13, P0-2 — round 12's own residual
note claimed only two of the six comparison dimensions were left
unfixtured after its fix, but that count itself was wrong: a
published-event-set collision, the third structured-ID dimension named
alongside command inventories and RB-IDs, had no fixture and was named
in no disclosed residual either) two synthetic domains publishing an
identical event ID/name in their AsyncAPI/JSON-Schema registry
entries, with no shared-contract exception on record**. Expected:
`DOMAIN_CONTRACT_COLLISION` denial for all four cases independently
(RB-ID reuse, identical command inventory, identical published-event
set, foreign-signal SLO). **Corrected (Scenario Review round 1, P0-4): this scenario
previously claimed to also stand in for "dependency vulnerability" gate
coverage — a domain-contract collision is not a vulnerable dependency,
and that claim is withdrawn. Real dependency-vulnerability coverage is
SCN-094.**

### Group C — Gate-bypass attempts (mirrors this project's own Bash-guard discipline)

**SCN-MOD001-016 · IDEM · Blocker · GOV-01-R02 (idempotency-contract lint) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 6, P0-1): the original version tested
only runtime dedup behavior against a single already-well-formed
endpoint — it never ran the card's own required *lint* (`EIP_MIRROR.md`
lines 4147-4156), so a command declaring none of the six required
elements would still pass this scenario. Rewritten into two parts, the
static lint (a) and the runtime behavior (b), so both halves of the
card's own text are actually proven.**
Preconditions: a synthetic externally-retryable mutation command
declaration (the kind `tools/validate_idempotency_contract.py`, added
this round, reads) plus a synthetic runtime endpoint built from it.
Steps: (a) **lint** — run the static check against 6 synthetic command
declarations, each missing exactly one of the card's 6 required
elements in turn: no scoped Idempotency-Key tuple; a retention window
under 24h (and, separately, under the longer payment/fiscal-path
minimum for a command flagged financial); no stored-request-hash field;
no reference to the stable 409
`IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD` code; no `command_id`
propagation field to outbox/provider dispatch; no deterministic
provider-idempotency-derivative field. Expected: each of the 6 denied,
citing the specific missing element by name. Companion positive: a
declaration with all 6 elements present passes. (b) **runtime** — send
the same request twice with the same Idempotency-Key against the
synthetic endpoint built from the passing declaration. Expected: second
request returns the stored result, not a duplicate side effect.
Negative: a retry with the same key but a *different* payload returns
the stable 409 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD` the lint
in (a) confirmed is declared. Evidence: 6 lint-denial reports, 1
lint-pass report, and the runtime dedup/409 transcript.

**SCN-MOD001-017 · DATA · Major · GOV-01-R04 (SBOM/provenance) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: build a synthetic artifact through the real pipeline; inspect the
generated SBOM/provenance record. Expected: SBOM lists actual
dependencies, provenance links back to the exact source commit.

**SCN-MOD001-018 · INT · Major · GOV-01-R04 (API/event schema compatibility) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a backward-compatible OpenAPI change (additive field). Expected:
PASS. Negative case: 034.

**SCN-MOD001-019 · NEG · Blocker · GOV-01-R04 (event contract, negative) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: an event referenced in code with no registry entry (companion to
008). Expected: `UNREGISTERED_EVENT_CONTRACT` denial.

**SCN-MOD001-020 · SEC · Blocker · Gate-bypass attempt (CI-workflow layer) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (round 1, P1-3):** the original draft tested a *local
shell-invocation* bypass taxonomy (absolute path, wrapper, malformed
flag — modeled on `bash_guard.py`'s BUG-013/022/023 history). That is
the wrong threat model for a CI gate. Rewritten to the CI-workflow-
configuration layer. **Further corrected (round 2, P1-3): the round-1
rewrite still omitted the highest-yield real bypass classes and never
actually inspected the control it claimed protected the gate — both
fixed below.** Preconditions: a working, gate-enforcing GitHub Actions
workflow with branch protection configured on the target branch. Steps,
each attempted independently against a disposable fixture branch/PR,
never against `main` or the governing baselines: (a) add `continue-on-error:
true` to the gate step in the same PR the gate should block; (b) add a
`[skip ci]`-style commit-message token; (c) edit the gating workflow
file itself (weakening or removing the gate step) in the same PR the
gate would otherwise block; (d) trigger the workflow via
`workflow_dispatch` bypassing the normal PR-triggered path; (e) open
the equivalent PR from a fork; (f) **[added round 2]** attempt to merge
via a repository-admin "bypass required status checks" override — the
single most common real-world CI-gate bypass, and the one this
scenario's original Expected-result claim assumed away without
checking; (g) **[added round 2]** rename the gating job so the branch
protection's *required check name* no longer matches (name-drift
bypass — the required check simply never reports, and GitHub treats an
unreported check as non-blocking by default in some configurations);
(h) **[added round 2]** attempt a direct/force push to the protected
branch, bypassing the PR path entirely; (i) **[added round 2]** a
`pull_request_target`-triggered workflow that runs base-branch workflow
code with repository secrets against a fork PR's ref. Also, **[added
round 2]** before asserting any outcome: directly inspect the branch
protection rule's own configuration (required-status-check names,
"include administrators" setting, restrict-who-can-push list) rather
than only observing merge-attempt outcomes — the original version
asserted what the configuration "actually gates" without checking it.
Expected: (a)-(e) still result in the gate blocking the merge, per the
inspected branch-protection configuration; (f) is expected to succeed
unless "include administrators" is enabled — if it succeeds, that is
the correct, disclosed residual (admin override is a deliberate escape
hatch, not a defect, but its existence and who holds it must be
recorded, not silently assumed away); (g) is expected to succeed
(demonstrating a real gap) unless the required-check name is generated
from the job's stable ID rather than its display name; (h) and (i) are
expected to be denied/inert given the branch-protection and workflow
trigger-permission configuration this project would adopt. Evidence:
the branch-protection configuration snapshot plus all 9 attempt
outcomes. Negative/failure behavior IS this scenario's subject.

### Group D — Capability/registry integrity, rule-family coverage, baseline binding

**SCN-MOD001-021 · OBS · Major · Additional obligation: capability-governance validator (`EIP_MIRROR.md` lines 4122-4157) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: run `validate_capability_manifest.py` (the MOD-001-built
generalization of MOD-000's `validate_capabilities.py`) against the
current `CAPABILITY_REGISTRY.md`/manifest state. Expected: PASS, same
result as MOD-000's own `validate_capabilities.py` run this session
(7/7 capabilities APPROVED) — proves the generalized tool doesn't
regress the specific one. Evidence: validator output.
**Split (Scenario Review round 1, P2-8):** this scenario previously
also carried a second, unrelated check (Notion/Git/knowledge
reconciliation) as an appended clause with no independent evidence
requirement of its own — that check now has its own scenario, 021b,
immediately below, so the named-family table's "Notion/Git/knowledge
state reconciliation" row rests on a real, independently-evidenced
scenario rather than a sub-clause.

**SCN-MOD001-021b · OBS · Minor · Notion/Git/knowledge state reconciliation · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a live check that `CURRENT_STATE.md`'s MOD-001 status text
matches what would be mirrored to Notion's Modules database (field by
field, same method MOD-000's own Phase 8 SCN-046 used). Expected: 0
divergence. Evidence: the comparison output itself, not merely an
assertion that none was introduced. Negative/failure behavior: a
deliberately mismatched synthetic Notion row (in a disposable test
page, never the real MOD-001 Notion page) is proven to be detected by
the same check.

**SCN-MOD001-022 · MIG · Blocker · GOV-01-R06, TSD §24.2 · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: run a synthetic 4-phase migration (expand→migrate/backfill→
switch→contract) against a disposable schema. Expected: each phase
completes in order; a validation query confirms data integrity
post-migration. Negative case: 070.

**SCN-MOD001-023 · HP · Major · GOV-01-R04 (full pipeline) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: run the complete CI pipeline (`IMPLEMENTATION.md` §3) end to end
against a trivial valid change. Expected: every stage either passes or
correctly reports "not yet applicable" (for stages needing real domain
content) — no stage silently skips without saying so.

**SCN-MOD001-024 · VAL · Major · GOV-01-R04 (schema/contract validation) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: submit a contract file (`contracts/openapi/`) that is
syntactically valid but semantically incomplete (missing a required
field per this project's own schema convention). Expected: the
validator reports the specific missing field, not a generic parse error.

**SCN-MOD001-025 · NEG · Blocker · Additional obligation: baseline-artifact binding validation (`EIP_MIRROR.md` lines 4140-4143, 4253-4263) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: run `validate_baseline_binding.py` (the CI-gate generalization of
`verify_baselines.py`) with a deliberately corrupted hash injected for
one baseline in a throwaway copy of `PROJECT_INDEX.md` (never the real
file). Expected: fail-closed with a named mismatch, `BASELINE_INTEGRITY_FAILURE`
— proves the CI-gate version doesn't silently pass where the manual
`verify_baselines.py` would fail-closed.

**SCN-MOD001-026 · BND · Major · Same obligation as 025 · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: run the same validator against the real, unmodified
`PROJECT_INDEX.md`/baselines. Expected: PASS (this is the boundary case
proving the negative fixture in 025 is a genuine detector, not a tool
that always fails).

**SCN-MOD001-124 · NEG · Blocker · Baseline-artifact binding validation, remaining fail-closed conditions (P0-1) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 7, P0-1): the card mandates 5 distinct
fail-closed conditions for the baseline-binding validator
(`EIP_MIRROR.md` lines 4140-4143, 4253-4263, verbatim: "Baseline-binding
validator rejects use of an unapproved candidate EIP, missing/ambiguous
artifact identity, missing content hash or identity/hash mismatch,"
plus "PROJECT_INDEX.md entries for all governing baselines with
non-empty cryptographic hashes and SESSION_BOOTSTRAP.md enforcement
metadata") — SCN-025/026 covered only the mismatch case and its
positive twin. The other 4 had no scenario at all, falsifying §0's own
"every requirement, gate, and validator this module owns needs its own
real scenario" claim.**
Steps, four parts, each against a throwaway copy of `PROJECT_INDEX.md`
(never the real file): (a) an entry whose EIP artifact is flagged
`candidate`/`unapproved` rather than the approved governing baseline —
expected: `UNAPPROVED_CANDIDATE_EIP` denial citing the artifact; (b) a
baseline entry with no `PROJECT_INDEX.md` row at all, or a row with an
ambiguous identity field (e.g. two baselines sharing one identity
string) — expected: `MISSING_OR_AMBIGUOUS_ARTIFACT_IDENTITY` denial
citing the artifact; (c) a baseline entry present with an identity but
an empty/absent hash field — expected: `MISSING_CONTENT_HASH` denial
citing the artifact (distinct from 025's *mismatched*-hash case); (d) a
`PROJECT_INDEX.md` with all 4 baselines correctly hashed but
`SESSION_BOOTSTRAP.md`'s own enforcement-metadata reference removed (no
pointer requiring a fresh session to read it before acting) — expected:
`BOOTSTRAP_ENFORCEMENT_METADATA_MISSING` denial, proving the
bootstrap/control validator fails closed before any code change is
accepted, not just before a hash mismatch. Expected overall: each of
the 4 conditions denied with its own named error citing the specific
defect. Companion positive: a `PROJECT_INDEX.md` correctly satisfying
all 5 conditions (this scenario's 4 plus SCN-025/026's mismatch case)
passes in full. Evidence: 4 denial reports plus the full-pass report.

**SCN-MOD001-125 · OBS · Major · GOV-01-R08, maintenance policy and customer-communication template (P1-5) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Added (Scenario Review round 7, P1-5): Appendix B's own GOV-01-R08
text names "maintenance" and "customer communication" as distinct
obligations alongside changelog/lifecycle, but neither had a mechanism,
an IN/OUT disposition, or a scenario until this round.**
Steps: validate `RELEASE_TRAIN.md` (`IMPLEMENTATION.md` §12) against
two required sections: (a) a maintenance policy stating how long each
release-train line receives fixes before end-of-support; (b) a
customer-communication template (a placeholder/internal-synthetic
template, since MOD-001 precedes any real customer-facing module).
Expected: both sections present and non-empty. Negative case: a
synthetic `RELEASE_TRAIN.md` missing either section is denied, citing
the missing section by name. Evidence: the validator's pass/deny
report.

**SCN-MOD001-126 · SEC · Blocker · Input/output data-exposure lint (card security baseline, P0-1) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 8, P0-1): the card's mandatory Security-
scope baseline (`EIP_MIRROR.md` lines 4267-4271) names 7 controls;
"input/output data exposure" had no disposition, mechanism, or scenario
anywhere — round 5's own P0-2 finding miscounted this baseline as
having 3 uncovered items and named only 2 (sensitive logging,
abuse-negative), missing this third one entirely; rounds 6/7 inherited
the arithmetic error unchallenged.**
Source: `EIP_MIRROR.md` lines 4267-4271; `IMPLEMENTATION.md` §6 names
the real MOD-001 implementation obligation: a schema-level allowlist
check, distinct from the permission lint (which checks *action*
declarations, not field shape) and from every other baseline item
(SCN-029 scans committed files for secrets, SCN-122 scans log
statements, SCN-043 checks data-classification tags — none test
response/request field shape). Steps: (a) a synthetic OpenAPI response
schema with an undeclared field silently serialized (e.g. an internal
column leaking through a catch-all/wildcard response shape) — expected:
denied, citing the undeclared field; (b) a synthetic request schema
that accepts an extra, undeclared field past validation (hidden-field
injection) — expected: denied, citing the extra field. Companion
positive: a response schema where every serialized field is explicitly
declared, and a request schema that rejects any field not in its own
declared set, both pass. Evidence: two denial reports plus the
positive-pass report.

**SCN-MOD001-127 · DATA · Major · GOV-01-R07, toolchain-matrix real-config validation, white-label metadata, KMP shared-module versioning (P0-1) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Added (Scenario Review round 9, P0-1): round 8 disposed of these
three TSD §24.3 rules as "covered by existing scenario families' own
intent (SCN-051/099's matrix-integrity checks extend naturally once
the checker exists)" — independently found false: `IMPLEMENTATION.md`'s
own text says `SCN-051`/`099` test only *internal* consistency,
explicitly distinct from `tools/validate_toolchain_matrix.py`'s real
job (matrix vs. actual committed config), and no scenario tested the
matrix's own `whitelabel_release_metadata`/`shared_module_version`
fields at all. Corrected (round 10, P1-2): part (a) as originally
written had no real target to diverge from — `IMPLEMENTATION.md`'s
`mobile/` topology contained no Gradle/Xcode config file at all. Fixed
by adding real pinned-version stub files (`mobile/shared/build.gradle.kts`,
`mobile/androidApp/build.gradle.kts`) to the topology this round, so
this check has an actual committed config to run against.**
Source: `TSD_MIRROR.md` lines 11682-11691 ("White-label fleet release
metadata is tracked per branded app and store"; "shared KMP modules are
versioned in source/build provenance"). Steps: (a) run
`tools/validate_toolchain_matrix.py` against a synthetic
`mobile/TOOLCHAIN_MATRIX.md` whose pinned Gradle version deliberately
diverges from the real committed `mobile/shared/build.gradle.kts`/
`mobile/androidApp/build.gradle.kts` version stubs — expected: denied,
citing the drift (distinct from `SCN-051`'s internal-only check, which
this fixture would still pass); (b) the same matrix missing its
`whitelabel_release_metadata` section for one of several declared
branded apps — expected: denied, citing the missing brand entry; (c)
the same matrix missing a `shared_module_version` field for one KMP
module — expected: denied, citing the missing module. Companion
positive: a matrix with all pinned versions matching real config, a
complete `whitelabel_release_metadata` section, and every KMP module
versioned, passes all three checks. Evidence: three denial reports plus
the positive-pass report.

**SCN-MOD001-128 · PERF · Blocker · GOV-01-R07, isolated-PR toolchain-upgrade qualification gate (P0-1, corrected round 10 P1-1) · Automated · veyro-performance-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 9, P0-1): this CI gate
(`IMPLEMENTATION.md` §3, `Blocking? Yes`) had a real mechanism and no
scenario at all — round 8 disclosed it as a residual, which §9.1
(`EIP_MIRROR.md` lines 1861-1867: "Required is rule-derived, never a
discretionary reduction by Claude"; "no scenario may remain untested or
silently ignored") does not permit for a Blocking gate tracing to a
Critical requirement. Corrected (round 10, P1-1): the original steps
required real Android+iOS builds on real-device-equivalent runners,
which conflicts with `REQUIREMENTS.md`'s own out-of-scope line (mobile
application code is MOD-006), `MANUAL_QA.md`'s own framing of MOD-001's
mobile surface as "a document/CI-convention check, not a real app
build," and `SCN-MOD001-056` (Blocker) itself, which requires no paid
macOS CI runner tier be referenced anywhere in MOD-001's committed
configuration — an iOS build job is not schedulable without one. Fixed
by scoping this scenario to the CI workflow-definition layer, matching
`SCN-055`'s own established pattern ("checked via job metadata, not
real device builds, since no mobile code exists yet").**
Source: `TSD_MIRROR.md` lines 11684-11687 ("Toolchain upgrades are
isolated pull requests with Android+iOS build, UI, accessibility and
performance qualification before merge"). Steps: a synthetic PR touches
only `mobile/TOOLCHAIN_MATRIX.md` (an isolated toolchain-upgrade PR).
Expected: the CI workflow definition wires TSD's 4 named qualification
dimensions — build (with separate Android and iOS jobs under it),
UI, accessibility, and performance (**rephrased, Scenario Review
round 10, Editorial-1: the prior "all 4... (Android build, iOS build,
UI, accessibility, performance..." wording listed 5 items before its
own parenthetical reconciled it to 4, reading as self-contradictory on
first pass**) — as required jobs on the toolchain-upgrade
trigger path, verified via workflow-graph/job-metadata inspection
(`tools/validate_architecture_gates.py --gate toolchain-qualification`)
against the Android build/UI/accessibility jobs' real execution on
standard (non-macOS) runners — the iOS build job's real execution is
deferred to real implementation time, consistent with `SCN-056`, but
its presence and required-status-check wiring on the toolchain-upgrade
path is checked now. Negative case: the same PR with the iOS-build job
absent from, or not marked required on, the toolchain-upgrade trigger
path is denied by the workflow-graph check, citing the missing
dimension — a real, executable check of the gate's wiring, not a
rubber-stamp. Evidence: the workflow-graph inspection report plus the
Android/UI/accessibility jobs' real pass/fail report.

**SCN-MOD001-129 · PERF · Major · GOV-01-R07, real-device smoke test, capability-adapter half (P0-1, corrected round 10 P1-1) · Automated · veyro-performance-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 9, P0-1): `IMPLEMENTATION.md` §12 itself
states TSD §24.3 names two smoke-test subjects (capability adapters and
critical offline flows); `SCN-050` covers only the offline-flow half.
This scenario closes the other half, which round 8 disclosed as a
residual rather than closing. Corrected (round 10, P1-1): "real-
device-equivalent CI runners for both Android and iOS" has the same
paid-macOS-runner conflict as `SCN-128`'s original text. Fixed by
scoping the iOS half to job-wiring proof, same split as `SCN-128`.**
Source: `TSD_MIRROR.md` lines 11694-11695 ("Release candidates require
real-device smoke tests for platform capability adapters and the
critical offline flows"). Steps: a synthetic native-adapter-boundary
fixture (e.g. a camera/biometric/push-token stub) is smoke-tested for
real on a standard (non-macOS) Android CI runner. Expected: the
fixture's adapter boundary responds correctly. The equivalent iOS smoke
test is proven present and required-status-checked on the release-
candidate trigger path via workflow-graph inspection (its real
execution on a macOS runner is deferred to real implementation, per
`SCN-056`). Negative case: a deliberately broken Android adapter stub
(e.g. a push-token stub returning a malformed token) is flagged by the
real smoke test, not silently passed; a synthetic PR with the iOS smoke
job absent from the release-candidate trigger path is denied by the
workflow-graph check. Evidence: the Android smoke-test report plus the
iOS workflow-graph inspection report.

**SCN-MOD001-130 · SEC · Blocker · TSD §24.1 gate 3, event-contract owner-approval sub-clause (P0-1) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 10, P0-1): TSD §24.1's event contract
lint (`TSD_MIRROR.md` lines 11610-11612) has two normative halves —
"every event... exists in the registry" and "compatibility and
classification changes require owner approval." `IMPLEMENTATION.md`
§4's gate-3 row and `SCN-008`/`019` tested only the first half; the
second was disclosed as a residual at round 1 (`SCENARIOS.md`'s own
round-1 log) and carried unfixtured for nine rounds — a disclosed
residual on a Blocking gate tracing to a Critical requirement is not a
permitted discretionary reduction under §9.1 (`EIP_MIRROR.md` lines
1861-1867), the same rule round 9's own P0-1 applied one round later.
**Corrected (Scenario Review round 11, P0-1): originally routed to
`veyro-critical-engineer`, but ADR-005 bounds that agent to exactly
three named slices (tenant-isolation/RLS harness, authn
negative-credential fixture, RLS+permission gates) and explicitly
excludes "the other four §24.1 gates" — gate 3 is one of them.
Retitled to `veyro-security-reviewer/Opus`, matching every other
gate-violation scenario in this catalog (e.g. `SCN-134`/`135`/`136`),
rather than silently broadening `veyro-critical-engineer`'s scope
without the ADR amendment DC-17 would require. Also fixed (Scenario
Review round 11, P2-2): the positive companion originally required "a
real `OWNER_APPROVALS.md` row ID," with no synthetic-fixture guard —
every comparable scenario in this catalog is explicit that fixtures
are disposable/synthetic (e.g. `SCN-025`'s "a throwaway copy... never
the real file," `SCN-124`, `SCN-084`'s "in a synthetic copy"). This one
had none, so as written it either implied an owner-gated real approval
`REQUIREMENTS.md` names no gate for, or writing a synthetic approval
into the live governance file. Fixed below.**
Source: `TSD_MIRROR.md` lines 11610-11612. Steps: a registered event's
schema undergoes a synthetic compatibility-affecting change (e.g. a
required field added) or classification change, committed with no
corresponding approval reference. Expected:
`tools/validate_architecture_gates.py --gate event-contract` denies
with `EVENT_CHANGE_UNAPPROVED`, citing the event and the unapproved
diff. Companion positive: the identical diff, this time run against a
disposable synthetic copy of `OWNER_APPROVALS.md` carrying a matching
row ID (never a real row written to the live file), passes. Evidence:
the denial report plus the positive-pass report.

**SCN-MOD001-131 · SEC · Blocker · TSD §24.1 gate 6, domain-uniqueness shared-contract-exception sub-clause (P0-1) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 10, P0-1): TSD §24.1's domain contract
uniqueness lint (`TSD_MIRROR.md` lines 11646-11648) fails a reused
`RB-<DOMAIN>` ID or command inventory "unless an explicit shared-
contract exception is approved." `IMPLEMENTATION.md` §4's gate-6 row
and `SCN-014`/`015` tested only the failure half; without the exception
half, the gate as specified would false-positive on a legitimately
approved shared contract — the same disclosed-residual pattern as
`SCN-130`, same origin round, same nine-round carry.
**Corrected (Scenario Review round 11, P0-1): same out-of-charter
routing defect as `SCN-130` — gate 6 is not one of `veyro-critical-
engineer`'s three ADR-005 slices. Retitled to
`veyro-security-reviewer/Opus`. Also fixed (P2-2): the positive
companion required "a matching exception entry recorded," with the
same missing synthetic-fixture guard as `SCN-130` — fixed below.**
Source: `TSD_MIRROR.md` lines 11646-11648. Steps: two synthetic domains
declare an identical `RB-<DOMAIN>` ID with no matching entry in a
disposable synthetic copy of `contracts/SHARED_CONTRACT_EXCEPTIONS.md`
(never the live register). Expected:
`tools/validate_architecture_gates.py --gate domain-uniqueness` denies
with `DOMAIN_CONTRACT_COLLISION`, citing both domains. Companion
positive: the identical collision, this time with a matching exception
entry recorded in that same synthetic copy for that specific domain
pair, passes, citing the
exception ID in its output (proving the gate reads the exception, not
merely skips the check). Evidence: the denial report plus the
exception-resolved pass report.

**SCN-MOD001-132 · DATA · Blocker · GOV-01-R02, six named domain suite scaffolds wired (P0-2) · Automated · veyro-security-reviewer/Opus (judgment), veyro-implementer/Sonnet (mechanical run) · NOT EXECUTED**
**Added (Scenario Review round 10, P0-2): `REQUIREMENTS.md`'s own
GOV-01-R02 implementation obligation and acceptance criteria commit
MOD-001 to "documented, empty-but-wired suite scaffolds for membership/
booking/payment/ledger/POS/access, each with a placeholder fixture
proving the harness itself is live" — no scenario tested this, and
`IMPLEMENTATION.md`'s own topology had no such scaffolds until this
round.** **Corrected (Scenario Review round 11, P1-6): the original
negative case ("a seventh, undeclared domain path... is correctly
absent from the six-domain inventory check") asserted the check does
nothing, not a fail-closed proof, and named a
`--gate module-deps` "six-domain inventory check" that
`IMPLEMENTATION.md` §4's gate-2 row does not define (that gate is
cross-domain import/SQL detection only). Fixed with a real
deliberate-violation fixture, and retagged Blocker/dual-tier matching
`SCN-004`'s own convention (this scenario carries an SEC-adjacent
tenant/domain-boundary judgment call, the same species `SCN-004` itself
already establishes needs the dual-tier split — Opus judgment,
Sonnet mechanical run — when tagged Blocker; **corrected, Scenario
Review round 12, E-1: this previously cited `SCN-118` for that
precedent, but `SCN-118` carries no carve-out at all — it was retitled
outright to `veyro-security-reviewer`/Opus by round 5's P1-1, per that
scenario's own block**).**
Source: `REQUIREMENTS.md` GOV-01-R02 (implementation obligations,
acceptance criteria); `EIP_MIRROR.md` lines 17545-17549. Steps: for
each of the six named domains (`backend/app/modules/{membership,
booking,payment,ledger,pos,access}/`), run that domain's
`tests/test_scaffold_live.py` placeholder fixture. Expected: all six
pass, proving the harness (test discovery, fixture DB connection,
tenant-context resolver from `_shared/`) is live for that domain path —
none asserts real product behavior, since none exists. Negative case:
one of the six domains' `test_scaffold_live.py` fixtures is deleted or
deliberately broken (e.g. an assertion changed to always fail); the CI
test-run step reports a non-zero exit naming that specific domain's
missing/failing scaffold, rather than silently reporting the suite
green with five domains actually collected. Evidence: the six
placeholder-fixture pass reports plus the broken-domain failure
report.

**SCN-MOD001-133 · SEC · Blocker · GOV-01-R02, financial-invariant test harness (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 10, P0-2): `IMPLEMENTATION.md` §3's own
CI stage table names a Blocking "financial-invariant tests" check
alongside domain-contract/tenant-isolation/authorization tests; no
scenario exercised it, and no fixture existed until this round.**
**Corrected (Scenario Review round 11, P0-1): originally routed to
`veyro-critical-engineer`, but a placeholder double-entry-invariant
scaffold fixture is not one of that agent's three ADR-005 slices (the
real ledger critical-slice work belongs to the future domain module
that claims `backend/app/modules/ledger/`, per this scenario's own
scaffold-not-product framing). Retitled to
`veyro-security-reviewer/Opus`.**
Source: `IMPLEMENTATION.md` §3 (Domain contract / tenant-isolation /
authorization / financial-invariant tests row); `REQUIREMENTS.md`
GOV-01-R02. Steps: run `backend/tests/contract/
test_financial_invariant_scaffold.py` against a synthetic set of
double-entry ledger rows. Expected: the harness asserts debits equal
credits and passes on a balanced synthetic set. Negative case: the same
harness run against a deliberately unbalanced synthetic set (a debit
with no matching credit) fails, citing the specific invariant
violated — proving the harness itself detects a real violation, not a
rubber-stamp pass. Evidence: the pass report plus the denial report.

**SCN-MOD001-134 · SEC · Blocker · TSD §24.1 scanning stage, SAST (P0-3) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 10, P0-3): `TSD_MIRROR.md`'s scanning
stage names SAST, dependency, secret, container and IaC scanning as one
Blocking group (`IMPLEMENTATION.md` §3); dependency (`SCN-094`) and
secret (`SCN-029`) each have a real positive+negative scenario, but SAST
had none — the only related scenario, `SCN-064`, is an owner-reserved
denial drill proving no *paid* SAST SaaS credential is configured,
which proves the opposite of a working scanner.**
Source: `TSD_MIRROR.md` lines 11625-11626; `REQUIREMENTS.md` GOV-01-R03
acceptance criteria ("every named tool... runs successfully in CI").
Steps: run the CI-wired static-analysis (SAST) scanning stage against
this repo's own current source tree (tool selection deferred to
implementation per DC-18/DC-19, free/open-source only per DC-16).
Expected: the scanner runs to completion and produces a real findings
report (even "0 findings" — the tool executing is the evidence).
Negative case: a synthetic fixture file containing a deliberately
insecure pattern the chosen scanner's default ruleset flags (e.g. a
hardcoded SQL string concatenation shaped for injection) is committed
to a disposable branch; the scanner flags it before merge, and a
companion run with the pattern removed passes cleanly. Evidence: the
baseline report plus the flagged/cleaned pair.

**SCN-MOD001-135 · SEC · Blocker · TSD §24.1 scanning stage, container image (P0-3) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 10, P0-3): same gap class as `SCN-134`,
for the scanning stage's container-image half. Corrected (Scenario
Review round 11, P1-3): as originally written this had no real target
— `IMPLEMENTATION.md` contained no Dockerfile anywhere. Fixed by
adding a real minimal `backend/Dockerfile` scaffold to the topology
this round, the same fix shape as round 10's own Gradle-stub fix for
`SCN-127(a)`.**
Source: `TSD_MIRROR.md` lines 11625-11626; `REQUIREMENTS.md` GOV-01-R03.
Steps: run the CI-wired container-image scanning stage (scanner
selection deferred to implementation per DC-18/DC-19, free/open-source
only per DC-16, same convention as `SCN-134`) against a synthetic
disposable image built from the real committed `backend/Dockerfile`
scaffold. Expected: the scanner runs to completion, real report
produced. Negative case: the same image built with one deliberately
outdated/vulnerable base-image tag pinned is flagged before the
build-signed-artifact stage proceeds; a companion image using the
scaffold's own pinned placeholder tag passes cleanly. Evidence: the
baseline report plus the flagged/cleaned pair.

**SCN-MOD001-136 · SEC · Blocker · TSD §24.1 scanning stage, IaC (P0-3) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 10, P0-3): same gap class as `SCN-134`/
`SCN-135`, for the scanning stage's IaC half. Corrected (Scenario
Review round 11, P1-3): unlike `SCN-135`, no committed IaC config file
target exists yet, and `IMPLEMENTATION.md` §1 leaves the IaC vendor
itself genuinely undecided ("exact tool TBD at implementation time —
TSD names no specific IaC vendor read so far"), unlike the Dockerfile
case above where `docker compose` was already this plan's assumed
mechanism. Rather than invent a vendor choice this round, this
scenario's own execution creates its target: a synthetic
implementation-time IaC config fixture, in whichever format the
eventually-chosen tool reads, added specifically for this scenario's
run — same tool-agnostic framing `SCN-134` already uses for SAST.**
Source: `TSD_MIRROR.md` lines 11625-11626; `REQUIREMENTS.md` GOV-01-R03.
Steps: run the CI-wired IaC scanning stage (tool selection deferred to
implementation per DC-18/DC-19, free/open-source only per DC-16) against
a synthetic IaC configuration fixture representative of
`infra/environments/`'s eventual real content. Expected: the scanner
runs to completion, real report produced. Negative case: the same
fixture with a deliberately insecure setting the chosen scanner's
default ruleset flags (e.g. an unencrypted-at-rest storage declaration)
is committed to a disposable branch; the scanner flags it, and a
companion fixture with the setting corrected passes cleanly. Evidence:
the baseline report plus the flagged/cleaned pair.
**Disclosed residual (Scenario Review round 12, P2-4):**
`REQUIREMENTS.md` GOV-01-R03's own acceptance criterion reads "every
named tool ... runs successfully in CI against the **current repo
state**." This scenario's fixture is authored by the scenario's own
execution, not the current repo state — a materially weaker proof than
`SCN-135`'s real `backend/Dockerfile` target, disclosed rather than
silently equated with it. Picking an IaC vendor now to close this for
real would be exactly the premature, undemonstrated tool decision
DC-18/DC-19 forbid at planning time (no `infra/` content exists to
justify one yet). Tracked as an Implementation Complete obligation, not
a Definition-of-Ready blocker: the first real `infra/environments/**`
IaC file committed during MOD-001 implementation becomes this
scenario's real target, same as `SCN-127`(a)'s Gradle stubs and
`SCN-135`'s Dockerfile became theirs.

### Group E — Environments and authentication/tenant harnesses (GOV-01-R02)

**SCN-MOD001-027 · AUTHN · Blocker · GOV-01-R02 · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: send a deliberately invalid/expired credential to the
authentication harness's fixture endpoint (same drill class MOD-000's
own SCN-MOD000-095 established for a live TestSprite endpoint, applied
here to MOD-001's own harness). Expected: rejection, no session issued,
real profile/state unaffected before/after.

**SCN-MOD001-028 · AUTHZ · Major · GOV-01-R02 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: the tenant-isolation harness's authorization check runs for a
correctly-scoped request. Expected: PASS.

**SCN-MOD001-029 · SEC · Blocker · Secret leak detection · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: commit a synthetic fixture file containing a fake-but-realistic-shaped
secret pattern (e.g. an AWS-key-shaped string, never a real credential)
to a disposable branch and run the secret-scanning CI stage. Expected:
the scanner flags it before merge; a companion run with the secret
removed passes cleanly.

**SCN-MOD001-030 · NET · Major · GOV-01-R03 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a real network-timeout drill against an unreachable host from
within a CI job (mirrors MOD-000's own Phase 5 NET scenario pattern).
Expected: the job fails closed with a timeout error, not a hang; the
repo/environment state is provably unaffected before/after.

**SCN-MOD001-031 · PART · Major · GOV-01-R03 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: simulate a degraded/unavailable sandbox dependency (e.g. the
integration-test Postgres sandbox refuses connections) during a CI run.
Expected: the integration-test stage reports a clear
dependency-unavailable failure, distinct from a test-logic failure.

**SCN-MOD001-032 · OFF · Major · GOV-01-R03 (offline-fixture pattern) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: exercise the offline-mode fixture-pattern harness itself (the
thing later edge/mobile/POS modules will build real offline scenarios
on top of) against a synthetic signed-snapshot/TTL fixture. Expected:
the harness correctly distinguishes a valid unexpired snapshot from an
expired one.

**SCN-MOD001-033 · DATA · Major · GOV-01-R03 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a real repo-wide personal-data pattern scan (mirrors MOD-000's
own Phase 5 DATA scenario), re-run against MOD-001's own new files added
this planning turn. Expected: 0 real personal data found (only synthetic
fixture patterns, clearly labeled as such).

**SCN-MOD001-034 · INT · Blocker · GOV-01-R04 (negative schema compatibility) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a breaking OpenAPI change (a required field removed/retyped)
submitted against the existing contract. Expected:
`BREAKING_SCHEMA_CHANGE` denial naming the exact field.

**SCN-MOD001-035 · OBS · Major · Additional obligation: rule-family/content-standard consistency (Appendix H.2/H.3) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: run a validator confirming every one of Appendix H.2's 11 rule
families (global, backend, admin, web, frontdesk-pos, mobile, ios,
android, edge, data-ai, infra) resolves to at least one Appendix H.3
content standard. Expected: PASS against the real Appendix H.2/H.3 text
in `EIP_MIRROR.md` (already cross-checked this session — H.3 explicitly
resolves admin+web together, and names each other family by name).

### Group F — Local/QA/staging environment bootstrap (IMPLEMENTATION.md §2)

**SCN-MOD001-036 · HP · Major · Local environment bootstrap · Manual (Claude-driven) · veyro-manual-qa/Opus, fresh context · NOT EXECUTED**
Preconditions: a fresh clone. Steps: follow only committed
documentation to bring up a running local environment. Expected: it
comes up; no undocumented manual step was required. Evidence: a real
transcript of the attempt, including any friction found and fixed.

**SCN-MOD001-037 · VAL · Major · QA environment bootstrap · Automated (CI-triggered) · veyro-infra-sre-engineer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 7, BUG-031 escalation): was routed to
`veyro-implementer` — `infra/environments/qa/` is the activated
Infra/SRE/CI surface's own path, and `ADR-005` explicitly rejects
letting `veyro-implementer` stand in for the named surface engineer.
Retitled to `veyro-infra-sre-engineer`.**
Steps: the QA environment config (`infra/environments/qa/`) is applied
by CI on a real PR. Expected: environment boots, health-check endpoint
responds.

**SCN-MOD001-038 · NEG · Major · QA environment bootstrap, negative · Automated · veyro-infra-sre-engineer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 7, BUG-031 escalation): same fix as
SCN-037 — retitled to `veyro-infra-sre-engineer`.**
Steps: a deliberately invalid QA environment config (a malformed
setting). Expected: CI fails closed before attempting to boot, with a
named config-validation error, not a partial/hung boot.

**SCN-MOD001-039 · LOC · Major · GOV-01-R03 (localization tooling) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: run the RTL/Arabic lint tool against a synthetic fixture
containing both correctly-handled and incorrectly-handled bidi text.
Expected: it flags only the incorrect case.

**SCN-MOD001-040 · A11Y · Major · GOV-01-R03 (accessibility tooling) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: run the a11y lint against a synthetic fixture component missing
an ARIA label. Expected: it flags the missing label; a companion
correctly-labeled fixture passes.

**SCN-MOD001-041 · HP · Blocker · Staging environment bootstrap · Automated (CI-triggered) · veyro-security-reviewer/Opus (judgment on prod-boundary) · NOT EXECUTED**
Steps: the staging environment config is applied by CI after QA gates
pass. Expected: environment boots; **no production environment,
credential scope, or deployment path is reachable from this process**
(explicit check: no `infra/environments/production/` directory exists,
no production secret scope is referenced anywhere in the staging
workflow file).

**SCN-MOD001-042 · SEC · Blocker · Artifact integrity/signing · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: build a synthetic artifact through the real pipeline with a
dev-only signing key; verify the signature. Expected: verification
succeeds for the correctly-signed artifact. Negative case: 063.

### Group G — Privacy, concurrency, idempotency, network/partition (continued), release controls

**SCN-MOD001-043 · PRIV · Major · GOV-01-R03 (privacy classification lint) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: run the privacy-classification lint against a synthetic field
tagged `Restricted` and one left untagged. Expected: the untagged field
is flagged as needing an explicit classification before it can be
persisted — proves the lint exists and fires, even though no real data
field exists yet.

**SCN-MOD001-044 · CONC · Major · GOV-01-R05 (feature-flag/release controls) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: two concurrent synthetic requests during a canary rollout, one
under the flag's "on" cohort, one under "off." Expected: each request
consistently sees the correct variant — no cross-request flag-state
leakage.

**SCN-MOD001-045 · IDEM · Major · GOV-01-R05 (release controls, idempotent rollback) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: trigger the rollback mechanism twice for the same bad-release
event. Expected: the second trigger is a no-op (already rolled back),
not a duplicate/conflicting rollback action.

**SCN-MOD001-046 · NET · Major · GOV-01-R05 (canary monitoring under network failure) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: the canary/SLO-monitoring connection to its metrics source is
interrupted mid-drill. Expected: the system fails toward rollback (safe
default), not toward silently continuing an unmonitored promotion.

**SCN-MOD001-047 · PART · Major · GOV-01-R05 (partial rollout under degraded dependency) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: one of two canary-monitored dependencies becomes unavailable
mid-drill. Expected: the rollout decision correctly reflects a degraded/
unknown state rather than assuming healthy.

**SCN-MOD001-048 · HP · Major · GOV-01-R05 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a full synthetic canary deploy-and-promote cycle with no injected
failure. Expected: promotes cleanly; release-evidence record generated
matching `RB-GOV-01`'s field set.

**SCN-MOD001-049 · NEG · Blocker · Owner-reserved denial: no production activation via staging path · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: attempt to configure the staging promotion workflow to target a
production-shaped environment (a deliberate test of whether the
pipeline *can* be pointed at Production). Expected: denied/impossible by
construction — no production credential scope, secret, or deployment
target exists anywhere in this plan for the workflow to even reference
(DC-16). This is the CI-pipeline-level analogue of MOD-000's own
owner-reserved-restriction refusal drills.

### Group H — Mobile version/release policy, INT, LOC/A11Y continued

**SCN-MOD001-050 · OFF · Major · GOV-01-R07 (offline flow toolchain qualification) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: the CI convention requiring real-device smoke tests for critical
offline flows (TSD §24.3) is checked against a synthetic "offline flow
touched" file-change fixture. Expected: the convention correctly flags
that fixture as requiring the offline-smoke-test job.

**SCN-MOD001-051 · DATA · Major · GOV-01-R07 (toolchain matrix integrity) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: the pinned Kotlin/KMP/Compose/Gradle/Xcode/AGP versions file is
checked for internal consistency (no two pinned tools declaring
incompatible version ranges, per whatever compatibility data is
available at implementation time). Expected: PASS on the actual pinned
set once authored.

**SCN-MOD001-052 · INT · Major · GOV-01-R07 (dual-platform regression trigger) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a synthetic "common-code" file change (serialization/local-schema/
sync/auth/routing/shared-Design-System path) is submitted. Expected:
both the Android and iOS regression CI jobs are triggered, even though
the change is nominally platform-agnostic.

**SCN-MOD001-053 · LOC · Major · GOV-01-R07 (mobile localization parity) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 1, P2-6):** the original draft had no
stated Expected result, only an assertion. Steps: run the RTL lint (039)
against a synthetic fixture placed under the mobile toolchain's shared
Compose module path (`mobile/shared/src/commonMain/`), not just
web/admin. Expected: the lint tool runs successfully against that path
and correctly flags the same class of incorrect-bidi fixture it flags
under `admin-web/` — proving the tool is genuinely wired to the mobile
path, not merely assumed to cover it. Evidence: lint report from the
mobile-path run. Negative/failure behavior: a correctly-handled bidi
fixture under the same mobile path passes.

**SCN-MOD001-054 · A11Y · Major · GOV-01-R07 (mobile accessibility parity) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 1, P2-6):** same fix as 053. Steps:
run the a11y lint (040) against a synthetic fixture under
`mobile/shared/src/commonMain/`. Expected: the lint tool runs
successfully against that path and correctly flags a missing
accessibility label on the mobile-path fixture, same as it does under
`admin-web/`. Evidence: lint report from the mobile-path run.
Negative/failure behavior: a correctly-labeled fixture under the same
path passes.

**SCN-MOD001-055 · HP · Major · GOV-01-R07 · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 13, P1-3): the original text
checked that an iOS build job's runner metadata names a real
macOS/Xcode runner class — but a committed workflow file naming a
macOS runner label is itself a reference to a paid macOS CI runner
tier, the exact thing `SCN-056` (Blocker) bans anywhere in MOD-001's
committed configuration. Fixed to the same split `SCN-128`/`129`/`137`
already established: Android's runner assignment is real and
committed now; iOS's is proven present and required-status-checked as
a job on the mobile-build trigger path, with the runner-class label
itself deferred to real implementation time (per `SCN-056`), not
committed this round.** Steps: CI correctly assigns an Android build
job to a Linux runner, per TSD §24.3's own text; a distinct iOS build
job is present and required-status-checked on the same trigger path,
with its runner-class assignment left unspecified in committed
configuration until real implementation. Expected: the Android job
runs on the correct runner class (checked via job metadata, not real
device builds, since no mobile code exists yet); the iOS job's
presence and required-status-check wiring is confirmed via
workflow-graph inspection, without asserting or committing to any
specific runner class.

**SCN-MOD001-056 · NEG · Blocker · Owner-reserved denial: no real store/spend activation · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: attempt to reference a real Apple/Google developer account
credential or a paid macOS CI runner tier in the mobile CI convention
files. Expected: no such reference exists anywhere in MOD-001's
committed configuration — DC-16 boundary held by construction, not by
promise.

### Group I — Release lifecycle (GOV-01-R08), regression, TestSprite scope

**SCN-MOD001-057 · SEC · Major · GOV-01-R08 (release evidence integrity) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a synthetic release cycle's evidence record is checked for
tamper-evidence (e.g. a hash/signature over the record itself).
Expected: a tampered copy of the record is detectable.

**SCN-MOD001-058 · REC · Blocker · GOV-01-R05/R06 (rollback drill) · Manual (Claude-driven) · veyro-manual-qa/Opus, fresh context · NOT EXECUTED**
Steps: a real, end-to-end rollback drill in staging against a
deliberately-bad synthetic release (mirrors `MANUAL_QA.md` surface 7).
Expected: rollback completes, `RB-GOV-01`'s evidence-contract fields are
all populated (affected tenant/scope, command/aggregate version,
authoritative rows, outbox/inbox/DLQ/provider state where applicable,
reconciliation result, repair/correction reference, owner/follow-up
action).

**SCN-MOD001-059 · DR · Blocker · GOV-01-R06 (migration rollback, disaster-recovery adjacent) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: the migration-safety harness's rollback path (companion to 022)
is exercised after a deliberately-failed migration mid-way through the
4-phase sequence. Expected: the system returns to a consistent
pre-migration state, not a half-migrated one.

**SCN-MOD001-060 · LIFE · Blocker · GOV-01-R05/R06, life-safety-adjacent · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 1, P1-6):** the original draft's
"step" was a reasoning exercise ("reason explicitly about why...") with
no executable procedure, marked Automated despite being unexecutable by
a machine — a token-coverage defect, not a real scenario. Rewritten with
a concrete, distinct fixture. Preconditions: a synthetic release
artifact tagged with a fake `access-control-gate-config` payload
(representing what a real MOD-021/022 access-control module's
deployable would look like, without implementing any real access-control
logic). Steps: submit this synthetic release through the canary pipeline
(§3 of `IMPLEMENTATION.md`) with a deliberately-failing synthetic health
signal (distinct from 058's generic bad-release fixture — this fixture's
payload specifically represents an access-gate config change). Expected:
automated rollback triggers and the tagged payload never reaches the
"promoted" state — proving the rollback mechanism (058/059) would catch
a life-safety-relevant bad release before promotion, with a fixture that
actually represents that class of payload rather than a generic one.
Evidence: rollback log showing the specific payload tag was never
promoted. Negative/failure behavior: if the synthetic health signal is
healthy instead, the release promotes normally (proving the mechanism
isn't just always-rollback).

**SCN-MOD001-061 · OBS · Major · Deterministic regression (DC-11) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 1, P2-9):** the original text
understated this scenario's own obligation, calling it "trivial... 
nothing to regress against yet." DC-11 (`DEVELOPMENT_CONSTITUTION.md`
line 102) becomes binding starting MOD-001 and requires proving that
MOD-000's own approved critical journeys are not broken — MOD-000 is a
full, approved module with a real 95-scenario catalog and 5 live
governance scripts, not nothing. Steps: re-run all 5 of MOD-000's
governance checks (`verify_baselines.py`, `validate_catalog.py`,
`validate_capabilities.py`, `evidence_integrity_check.py`,
`test_bash_guard.py`, 194/194 tests) plus every MOD-001 scenario already
executed in a prior CI run. Expected: all still pass — this is a real,
non-trivial regression obligation from MOD-001's very first CI run
onward, not a placeholder that becomes meaningful later. Evidence: a
timestamped pass record extending MOD-000's own `run_regression.py`
precedent to cover MOD-001's own suite alongside MOD-000's.

**SCN-MOD001-062 · NEG · Major · TestSprite integration scope · Manual/CLI (Claude-driven, offline only) · veyro-security-reviewer/Opus (judgment on the owner-reserved denial) · NOT EXECUTED**
**Corrected (Scenario Review round 1, tier-consistency note): this is an
owner-reserved-denial drill like 056/064/065, which all route to Opus —
aligned for consistency.**
Steps: attempt `testsprite test run` (a paid/cloud command). Expected:
denied by the existing `.claude/settings.json` deny pattern (MOD-000,
Phase 3) — unchanged, not re-implemented, for MOD-001. Companion
positive case: `test scaffold`/`test lint` against MOD-001's real
scaffolded tree once it exists, credit balance confirmed unchanged
before/after (mirrors MOD-000's own Phase 2 exactly).

**SCN-MOD001-063 · SEC · Blocker · Artifact signing, negative · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a tampered copy of a signed artifact (one byte changed
post-signing). Expected: signature verification fails, citing the
mismatch — companion negative to 042.

**SCN-MOD001-064 · SEC · Blocker · Owner-reserved denial: no paid scanning/service activation · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: attempt to configure a paid SAST/scanning SaaS credential in CI
without a corresponding `OWNER_APPROVALS.md` row. Expected: no such
credential reference exists in committed CI config — the free/
open-source tooling selected in `CAPABILITIES.md` is what actually runs.

**SCN-MOD001-065 · PRIV · Blocker · Owner-reserved denial: no real member data · Manual (Claude-driven) · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a repo-wide scan (extends 033) specifically for any data file
that looks like it could be real member data rather than synthetic
fixture data. Expected: 0 found; every data fixture used by MOD-001's
own tests is clearly labeled synthetic.

### Group J — Load/performance, migration negative, alternate-path Required (see round 6 correction below)

**SCN-MOD001-066 · REC+DR (explicit dual-category exception — see Editorial note below) · Blocker · GOV-01-R06 (large-backfill throttling and recovery) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
*Editorial note (Scenario Review round 1): every other scenario in this
catalog carries exactly one category tag; this one is a deliberate,
acknowledged exception rather than a silent deviation — a checkpoint-resume
drill is genuinely both a recovery mechanism (REC) and a disaster-recovery-adjacent
one (DR), and both categories' coverage floor depends on this scenario
counting for both (REC: 058+066; DR: 059+066). Recorded explicitly here
so it reads as an intentional choice, not an inconsistency.*
Steps: a synthetic large-backfill job is interrupted mid-run. Expected:
it resumes from a checkpoint rather than restarting from zero, per TSD
§24.2's "online/resumable jobs with progress and throttling" text.

**SCN-MOD001-067 · LIFE · Blocker · GOV-01-R02 (tenant-isolation harness, life-safety framing) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 1, P1-6):** the original draft had no
procedure distinct from 005/007. Rewritten with a concrete, distinct
fixture. Preconditions: a synthetic table representing a physical-access
grant record (`access_grant`, tenant-scoped, representing what a later
MOD-021/022 access-control module's real table would look like — no
real access-control logic implemented). Steps: attempt a cross-tenant
read of this specific fixture table under the production-equivalent
non-privileged role (same mechanism as 005/007, applied to this
distinct, life-safety-shaped fixture rather than a generic one).
Expected: denied — 0 cross-tenant rows returned. Evidence: query result
+ RLS-denial log citing the `access_grant` fixture table by name.
Negative/failure behavior: if RLS is deliberately disabled on this
specific fixture (companion to 005's own negative), the denial fails and
the gate itself (not just this scenario) must catch it — proving the
general-purpose RLS gate (004/005) genuinely covers a life-safety-shaped
table, not just a generic one.

**SCN-MOD001-068 · PERF · Major · GOV-01-R03/§12 of IMPLEMENTATION.md (CI runner smoke-load) · Automated · veyro-performance-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 1, P1-7):** the original draft set the
pass/fail budget *from* the same measurement it was validating, which
cannot fail by construction. Corrected to a pre-declared budget, set
before the measuring run, not from it: **15 minutes wall-clock** for the
full pipeline (§3's full stage list) against a trivial/scaffold-only
fixture — chosen as a generous but real ceiling for a pipeline with no
real product code yet (GitHub Actions' own free-tier per-job timeout
default is 6 hours, so 15 minutes is a deliberately tight, meaningful
budget, not a rubber-stamp one). Steps: run the full CI pipeline against
a trivial fixture and measure wall-clock time. Expected: completes
within 15 minutes. Negative/failure behavior: if the real first
measurement exceeds 15 minutes, this scenario correctly FAILS and the
budget is revisited via a recorded decision (not silently loosened) —
it does not retroactively redefine "bounded" to mean whatever was
measured.

**SCN-MOD001-069 · PERF · Major · GOV-01-R03/§12 (environment smoke-load) · Automated · veyro-performance-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 1, P1-7):** same fix as 068 — a
pre-declared bound, not a self-referential one. Steps: 10 concurrent
requests against a trivial health-check endpoint in each of LOCAL/QA/
staging. Expected: all 10 respond successfully (HTTP 200) within **2
seconds** each — proves the environment itself isn't the bottleneck (not
a claim about product-scale load; 10 concurrent/2s is a deliberately
low bar appropriate to a health-check endpoint with no real product
logic behind it yet). Negative/failure behavior: any request exceeding
2s or returning non-200 fails this scenario.

**SCN-MOD001-070 · MIG · Blocker · GOV-01-R06, negative · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a deliberately out-of-order destructive (contract-phase)
migration attempted before its expand+backfill+switch predecessors have
run. Expected: the migration-safety lint rejects it — companion
negative to 022.

**SCN-MOD001-071 · HP · Minor · GOV-01-R01 (alternate bootstrap path) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 6, P1-3): was tagged ALT/Non-Required.
§9.1 (`EIP_MIRROR.md` lines 1854-1860) makes Required rule-derived, never
a discretionary reduction — "Required if... it traces to a Critical
requirement" — and this scenario's own trace field is GOV-01-R01, a
Critical requirement (`REQUIREMENTS.md` §2). The same reasoning round 1
already applied to move SCN-073/074 out of ALT (P2-10) was never applied
here. Recategorized HP (it duplicates SCN-001's own acceptance
criterion via an alternate path) and marked Required.**
Steps: bootstrap via a documented alternate path (e.g. a containerized
dev environment instead of native tooling), where one exists. Expected:
equivalent working result to 001.

**SCN-MOD001-072 · REC · Minor · GOV-01-R05 (alternate rollout shape) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 6, P1-3): was tagged ALT/Non-Required.
Same fix as SCN-071 — GOV-01-R05 is a Critical requirement, and this
scenario's own "still promotes/rolls-back correctly" expected result is
GOV-01-R05's own acceptance criterion (the identical shape round 1 found
disqualifying for SCN-073/074's P2-10 move). Recategorized REC (the
substantive behavior under test — promote/rollback correctness — matches
SCN-058/066's own category) and marked Required.**
Steps: a canary rollout using an alternate percentage-step schedule.
Expected: still promotes/rolls-back correctly.

**SCN-MOD001-073 · INT · Major · GOV-01-R04 (schema-compatibility checker, alternate valid contract shape) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Recategorized (Scenario Review round 1, P2-10):** originally filed as
`ALT`/Minor, but §9.1 (`EIP_MIRROR.md` lines 1861-1863) limits
Non-Required ALT variants to ones "that do not affect an acceptance
contract" — this scenario asserts real schema-compatibility-checker
acceptance behavior, which does affect the contract-compatibility
acceptance criteria. Moved to `INT`, Required, Major. Steps: an OpenAPI
change using an alternate but equally valid schema composition style
(e.g. `oneOf` instead of a discriminated union) that some teams might
reasonably prefer. Expected: the schema-compatibility checker accepts
it, since it's non-breaking, not just the exact style this project
happens to have used first. Evidence: compatibility-checker report.
Negative case: 034 (a genuinely breaking change is still denied
regardless of composition style).

**SCN-MOD001-074 · PERF · Major · GOV-01-R07 (CI runner assignment, manual re-trigger) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
**Recategorized (Scenario Review round 1, P2-10):** same reasoning as
073 — this asserts real runner-assignment gate behavior, not a
cosmetic variant. Moved to `PERF` (runner-class assignment is a
cost/performance concern — a misassigned job either wastes a scarcer
runner class or silently runs on the wrong platform), Required, Major.
Steps: confirm the Android/iOS runner-assignment convention (055) still
resolves correctly if a job is manually re-triggered rather than
triggered by the original event. Expected: same runner-class assignment.
Negative case: 101 (a deliberately misassigned job is flagged).

### Group K — Scenario Review round 1 remediation: model-assurance forced-fallback, capability-governance fail-closed drills, dependency vulnerability, gate-2 reverse edge, AUTHN companion, negative companions (P0-1, P0-2, P0-4, P1-1, P1-2, P1-5, P2-7)

Added after the first independent `veyro-scenario-reviewer` (Opus, fresh
context) round returned `MOD-001 SCENARIO REVIEW BLOCKED` (P0=4, P1=9,
P2=11, Editorial=4). Each scenario below closes one specific,
independently-verified finding — cited by finding ID, not just
"reviewer feedback."

**SCN-MOD001-075 · SEC · Blocker · Additional obligation: forced-fallback model-assurance negative test (P0-1) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 1109-1111, verbatim: "MOD-000 and MOD-001
must include a forced-fallback negative test proving that any
unresolved/substituted lower tier becomes `BLOCKED:
MODEL_ASSURANCE_UNVERIFIED` rather than PASS." Also the card's own
manual-QA field (`EIP_MIRROR.md` lines 4197-4198): "forced Opus→lower-tier
model substitution... fail closed." Preconditions: an Opus-tier
judgment-call task per `MODEL_ROUTE.md` (e.g. the architecture-gate
Blocker-severity judgment calls this catalog routes to
`veyro-security-reviewer`). Steps: deliberately attempt to substitute a
lower-tier (Sonnet) agent for that Opus-designated task, forcing the
substitution rather than letting normal routing occur — mirrors the
exact drill MOD-000's own `MODEL_ROUTING.md` "No-silent-downgrade rule"
and `mr_verify.py` tooling already established (SCN-MOD000-025/026/028).
Expected: the substitution is detected and the task's result is reported
`BLOCKED: MODEL_ASSURANCE_UNVERIFIED`, never silently accepted as PASS.
Evidence: `mr_verify.py`-style output (or its MOD-001-scoped equivalent)
showing the detection. Negative/failure behavior IS this scenario's
subject.

**SCN-MOD001-076 · SEC · Blocker · Capability-governance fail-closed: malformed/conflicting path Rule (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4193-4194. Steps: a synthetic
`.claude/rules/<family>/` file with a malformed path-glob scope, or two
Rule files whose scopes conflict on the same path. Expected: the
capability-governance validator denies with a named conflict/malformed-path
error.

**SCN-MOD001-077 · SEC · Blocker · Capability-governance fail-closed: manifest missing mandatory profile (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` line 4194. Steps: a synthetic
`module-capabilities.yaml` row for a module that should require a
mandatory profile (e.g. a privileged-console binding) with that profile
omitted. Expected: denial, blocking the Capability/Rules/Skills gate
(mirrors H.1's MOD-029 rule, `EIP_MIRROR.md` lines 20601-20604).

**SCN-MOD001-078 · SEC · Blocker · Capability-governance fail-closed: unregistered third-party Skill/plugin/MCP/hook (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` line 4195. Steps: reference an unregistered
Skill/plugin/MCP/hook ID in a synthetic manifest row. Expected: denial —
extends MOD-000's own `validate_capabilities.py` precedent (which
already fails closed on an unregistered CAP ID) to SKL-/RULE-scoped
entries per the schemas MOD-000 authored (`skl-rule-id.schema.yaml`).

**SCN-MOD001-079 · SEC · Blocker · Capability-governance fail-closed: altered approved Skill version without re-evaluation (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4196-4197. Steps: a registered Skill's
content hash changes (simulated) without a corresponding re-evaluation
record. Expected: denial — extends `capability_drift_check.py`'s
MOD-000-era material-change detection (built for BUG-025) to Skills
specifically, proving the CI gate calls it, not just that the tool
exists standalone.

**SCN-MOD001-080 · SEC · Blocker · Capability-governance fail-closed: circular capability dependency (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4198-4199, 4243-4244. Steps: a synthetic
manifest where CAP-A depends on CAP-B which depends on CAP-A. Expected:
denial with a named cycle report.

**SCN-MOD001-081 · SEC · Blocker · Capability-governance fail-closed: exhausted capability-resolution budget (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4199-4200, 4257 ("per-gap
resolution-attempt counters/budget evidence"). Steps: a synthetic
capability gap whose resolution-attempt counter exceeds its declared
budget. Expected: denial, not an infinite/unbounded retry.

**SCN-MOD001-082 · SEC · Blocker · Capability-governance fail-closed: overdue ACTIVE capability (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` line 4200, 4244 ("overdue lifecycle reviews").
Steps: a synthetic capability whose `next_review_due` date is in the
past while `lifecycle_status` is still `ACTIVE`. Expected: denial —
"Overdue, DEPRECATED or REVOKED capability cannot satisfy a module
capability gate" (`EIP_MIRROR.md` lines 20613-20616).

**SCN-MOD001-083 · SEC · Blocker · Capability-governance fail-closed: MOD-029 manifest missing admin/privileged-console (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4200-4202, 20601-20604. Steps: a synthetic
MOD-029-shaped manifest row omitting the admin/privileged-console
binding. Expected: denial — this is the exact rule
`.claude/rules/admin-privileged-console-baseline.md` binds forward to;
this scenario proves MOD-001's own validator actually enforces it
mechanically, not just documents the expectation.

**SCN-MOD001-084 · SEC · Blocker · Capability-governance fail-closed: H.3 content standard removed for an H.2-declared family (P0-2, closes P1-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4202-4205, 20644, 20689. Negative twin to
035, which was positive-only. Steps: remove (in a synthetic copy) the
Appendix H.3 content standard resolving one H.2-declared rule family
(e.g. temporarily strike the Backend paragraph). Expected: the
capability-governance validator denies, citing the unresolved family —
**this closes the named-family table's "Rule-family coverage" gap
(P1-2)**; that family row now correctly points to 035 (positive) + 084
(negative) instead of 042/057, which tested something else.

**SCN-MOD001-085 · BND · Major · Appendix-B traceability validator fail-closed: inverted completing/slice row (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4144-4147, 17393-17407 (the MOD-073
completing-module example this session read directly). Steps: a
synthetic Appendix-B-shaped row where the designated completing module
is scheduled before one of its own execution-slice modules. Expected:
the validator denies with a named ordering-violation error.

**SCN-MOD001-086 · SEC · Blocker · Security-baseline-assignment validator fail-closed: generic baseline on a Tier-1 domain module (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4211-4213, 4257-4260. Steps: a synthetic
module manifest for a Tier-1-domain-owning module that declares the
generic Security baseline instead of a domain-specific one. Expected:
denial.

**SCN-MOD001-087 · BND · Major · Scenario-matrix validator fail-closed: O on a §9.1-listed category (P0-2) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4158-4160; §9.1 (lines 1854-1858) names
the categories that can never be O. Steps: a synthetic module catalog
declaring `O` for, e.g., `AUTHN`. Expected: `validate_scenario_matrix.py`
denies — extends `validate_catalog.py`'s MOD-000-era equivalent check
(already proven in that tool) to the generalized, any-module validator
this project's own IMPLEMENTATION.md §1 plans MOD-001 must build.

**SCN-MOD001-088 · BND · Major · Scenario-matrix validator fail-closed: N without G.4 justification (P0-2) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Source: `EIP_MIRROR.md` line 4159. Steps: a synthetic catalog declaring
`N` for a category with no accompanying G.4 justification text.
Expected: denial.

**SCN-MOD001-089 · BND · Major · Scenario-matrix validator fail-closed: forbidden LOC/A11Y=N on MOD-003/MOD-006 (P0-2) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4160-4163. Steps: a synthetic catalog for
a MOD-003- or MOD-006-shaped module declaring `N` for LOC or A11Y.
Expected: denial — those two modules are explicitly named as forbidden
no-screen waivers per the card text.

**SCN-MOD001-090 · BND · Major · Scenario-matrix validator fail-closed: PERF/Load inconsistency, both directions (P0-2) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4163-4165. Steps, both attempted: (a) a
synthetic catalog with `Load=N/A` and `PERF=R`; (b) a synthetic catalog
with a non-N/A `Load` value and `PERF=N`. Expected: both denied
independently.

**SCN-MOD001-091 · OBS · Major · External-gate consistency validator fail-closed: §20/§21/§22 mismatch (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4166-4169. Steps: a synthetic external-gate
registry entry that disagrees between the §20 registry, a §21 module
card's own External-gates field, and the §22.0 binding set (e.g. present
in one, absent in another). Expected: the validator denies, naming which
two sources disagree.

**SCN-MOD001-092 · AUTHZ · Major · External-gate consistency validator: conditional-edge cases (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4169-4172, 4220-4225. Steps, three
attempted (c added, Scenario Review round 3 P2 — the card's own closing
clause, "verify both decisions are durable and deterministic," was
previously untested): (a) a synthetic dependent module consuming an
unresolved gate's named Gated capability — expected: denied, fails
closed; (b) a synthetic dependent proving genuine non-use of that
capability (a real `SOFTWARE_ONLY: true` + durable non-use proof,
mirroring MOD-000's own `STATUS.md` field) — expected: proceeds
correctly; (c) both (a) and (b) are re-run a second time with no
intervening state change, confirming each decision reproduces
identically (durable and deterministic, not a race-dependent or
cached-differently-each-time result). Evidence: two full (a)/(b) runs'
outcomes compared for exact match.

**SCN-MOD001-093 · OBS · Major · Appendix-I traceability validator fail-closed: removed INV/RB/ADR mapping (P0-2) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4172-4179, 20860-20862. Steps: remove (in
a synthetic copy) the proving-test/runbook reference for one of
MOD-001's own real Appendix I mappings (e.g. temporarily strip
`RB-GOV-01`'s reference from a synthetic copy of this module's own
evidence index). Expected: the validator denies — proves MOD-001
satisfies this validator against its own real Appendix I obligations
(`DOM-001`, `DOM-002`, `EVT-001`, `IAM-002`, `INV-GOV-01`, `RB-GOV-01`),
not just a hypothetical module.

**SCN-MOD001-094 · SEC · Blocker · Dependency vulnerability CI gate (P0-4) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: GOV-01-R04 (`EIP_MIRROR.md` lines 17556-17559): "CI gates for
lint, test, **vulnerability**, schema compatibility, migration safety
and artifact signing." Steps: add a synthetic dependency pin with a
known-published CVE (a real, disposable test fixture — e.g. a
long-since-fixed historical CVE in a pinned old version, not a live
supply-chain risk) to a throwaway lockfile and run the dependency
scanner. Expected: the scanner flags it and the CI stage fails, citing
the CVE ID. Negative/companion: the same lockfile with the dependency
pinned to a patched version passes cleanly. **This closes the
Critical-requirement gap P0-4 identified — SCN-015 (domain-contract
collision) is retitled below to no longer claim vulnerability coverage
it never tested.**

**SCN-MOD001-095 · AUTHZ · Blocker · GOV-01-R04, TSD §24.1 gate 2, §6.3 bidirectional pair — positive (P1-5) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `TSD_MIRROR.md` lines 11606-11608 — "For the four intentional
bidirectional pairs, §6.3 is the normative directed graph: only the
listed synchronous edge may import/call the opposite application
interface." Steps: a synthetic pair of modules standing in for one of
the four real §6.3 pairs, with only the permitted direction's
synchronous import present. Expected: PASS.

**SCN-MOD001-096 · TEN · Blocker · Same gate, negative (P1-5) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: the same synthetic pair, but the *reverse* direction also
attempts a synchronous import (the edge §6.3 requires stay
event-driven). Expected: `REVERSE_EDGE_NOT_EVENT_DRIVEN` denial.

**SCN-MOD001-097 · AUTHN · Major · GOV-01-R02, authentication harness — positive (P1-1 companion) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Source: GOV-01-R02 (`EIP_MIRROR.md` lines 17545-17549) — "Critical
workflow suites for authentication..."; companion to 027, which tested
only the negative (invalid-credential) case, leaving AUTHN with a single
real scenario until this one and 005 (recategorized) were added. Steps:
send a valid, correctly-formed credential to the authentication
harness's fixture endpoint. Expected: a session/token is issued; the
harness's own audit log records the successful authentication event
(ties to AUD-001, Appendix I). Evidence: issued-token/session record.
Negative case: 027.

**SCN-MOD001-098 · SEC · Major · SBOM/provenance tamper, negative companion to 017 (P2-7) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a tampered SBOM (one dependency entry altered post-generation) is
checked against the artifact's real provenance record. Expected:
mismatch detected, denial.

**SCN-MOD001-099 · DATA · Major · Toolchain matrix incompatible pair, negative companion to 051 (P2-7) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a synthetic pinned-version pair known to be mutually incompatible
(per whatever compatibility data exists at implementation time) is
checked. Expected: the consistency check denies, citing the
incompatible pair.

**SCN-MOD001-100 · INT · Major · Dual-platform regression trigger failure, negative companion to 052 (P2-7) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a common-code path-filter rule is deliberately misconfigured (the
trigger pattern doesn't actually match the common-code paths). Expected:
this scenario's own check on the *rule's configuration* (not the
trigger event) catches the misconfiguration — a self-test of the
path-filter pattern against the real common-code directory list, proving
the pattern isn't silently stale.

**SCN-MOD001-101 · PERF · Major · CI runner misassignment, negative companion to 055 (P2-7) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Steps: a synthetic Android build job is deliberately configured to
target a macOS runner (the wrong class). Expected: the runner-assignment
convention check (055's own mechanism, run in reverse) flags the
mismatch rather than silently allowing it.

### Group L — ADR-005 remediation: surface-profile activation gate, critical-engineer routing drill (added after ADR-005)

**SCN-MOD001-102 · SEC · Blocker · Surface-profile activation gate — positive (ADR-005 Decision 2 Part 3) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Preconditions: a synthetic `backend/app/main.py`-shaped fixture file and
a `module-capabilities.yaml` row correctly recording the Backend profile
as activated for the owning module. Steps: run
`tools/validate_architecture_gates.py --gate surface-profile`. Expected:
PASS.

**SCN-MOD001-103 · SEC · Blocker · Surface-profile activation gate — negative · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
Steps: a synthetic `.tsx` file added under a fixture `admin-web/` path
while the corresponding `module-capabilities.yaml` still marks the Admin
Web profile deferred (via its own `.profile-pending` marker, unchanged).
Expected: `SURFACE_PROFILE_NOT_ACTIVATED` denial citing the path and the
missing profile. Companion positive: 102.

**SCN-MOD001-104 · SEC · Blocker · `veyro-critical-engineer` routing-qualification drill — positive escalation (ADR-005 Decision 1, binding condition 3) · Manual (Claude-driven) · veyro-implementer/Sonnet dispatched, independently observed · EXECUTED — PASS**
**Corrected (Scenario Review round 3, P1-7): the original steps
specified dispatching *directly* to `veyro-critical-engineer` and
observing whether it self-identifies as in-scope — that presupposes the
routing decision rather than testing it (round 2's own P0-2 finding).
Corrected to the real, executed procedure below, mirroring
`SCN-MOD000-080`'s actual pattern: the task goes to the *lower-tier*
agent, and the drill observes whether it escalates.** Preconditions:
`veyro-critical-engineer` registered and its charter reachable from
`veyro-implementer`'s own escalation list (both true as of `BUG-029`/
`BUG-030` closure). Steps: dispatch "implement the tenant-isolation/RLS
test harness's fixture schema, roles, and grants for GOV-01-R02" to
`veyro-implementer`. Expected: `veyro-implementer` refuses and names
`veyro-critical-engineer`, citing its own (patched) charter. **Result:
PASS** — real dispatch executed, agent/session id `a83d7b00ab2c9264f`;
`veyro-implementer` correctly escalated. Evidence:
`knowledge/03-Modules/MOD-001/evidence/model-routing/ROUTING_DRILL_2026-09-14.md`'s
"Corrected drill" section (not MOD-000's own approved evidence tree,
per ADR-005's explicit instruction not to mutate APPROVED-module
evidence).

**SCN-MOD001-105 · SEC · Blocker · `veyro-critical-engineer` routing-qualification drill — negative, no over-escalation (ADR-005 Decision 1, binding condition 3) · Manual (Claude-driven) · veyro-implementer/Sonnet dispatched, independently observed · EXECUTED — PASS**
**Corrected (Scenario Review round 3, P1-7):** same fix as 104 — steps
now dispatch to `veyro-implementer`, not the target role. Mirrors
`SCN-MOD000-081`. Steps: dispatch "write the GOV-01-R08 release-train/
changelog convention document" to `veyro-implementer`. Expected:
`veyro-implementer` accepts the task itself, reasoning that it is
routine, non-architectural, non-critical-slice work. **Result: PASS**
— agent/session id `a7527aaf9676f1c43`; `veyro-implementer` correctly
retained the task. Evidence: same file, same section.

**Additional check executed beyond this catalog's own two scenarios
(architecture-routing case, mission step 6 of the BUG-030 remediation
turn):** a third dispatch ("decide whether to activate the Edge §4.3
surface profile now or defer") correctly escalated to `veyro-lead`,
with a substantively reasoned, non-charter-echo cross-check about
privileged-console adjacency. Agent/session id `a3b6a0fd35e9606e6`.
**Recorded here rather than left with no catalog entry** (a gap the
independent review's own P2 findings flagged): this is scenario
coverage for the architecture-routing direction of the same drill
family, filed under 105's own evidence rather than a new numbered
scenario, since it is the same drill mechanism's third case, not a
distinct requirement.

### Group M — Scenario Review round 2 remediation: GOV-01-R01/R06/R08 coverage gaps, missed card drills, load-bypass, surface-profile fail-open fix (P0-2, P0-3, P1-5, P1-6, P1-9, P1-10)

**SCN-MOD001-106 · NEG · Major · GOV-01-R01, per-layer deliberate-failure proof (P0-2) · Automated (5 of 6 automated layers real, 1 job-wiring-only) + Manual (exploratory) · veyro-implementer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 3, P1-2): this was mistagged BND —
its actual steps are GOV-01-R01's declared NEG obligation ("harness
correctly fails/blocks on a broken fixture"), not the declared BND
obligation ("a test mis-tagged as unit that actually hits a database").
The real BND case had no scenario; added as SCN-116 below. Also
corrected: "exploratory" is Claude manual QA with no automated harness
(`REQUIREMENTS.md` line 102, `TEST_PLAN.md` line 27) — the original
"7 failure reports" claim was not executable as written for that
layer.** **Corrected (Scenario Review round 13, P1-2): round 12
rescoped this scenario's own companion positive, `SCN-137`, away from
running a real "mobile UI"/"E2E" harness — neither test directory
exists in `IMPLEMENTATION.md`, and a real XCUITest run conflicts with
`SCN-056`'s paid-macOS-runner ban — but left this scenario's own text
unchanged, still claiming to break and run both for real. Fixed by
applying the identical split to this, its negative twin.** Steps: for
5 of the 6 *automated* test-pyramid layers (unit, component,
integration, contract, and the Android half of mobile UI), introduce
one deliberately broken fixture and run that layer's harness for real.
Expected: each layer's harness fails and reports which layer/fixture
failed — no layer silently passes a broken fixture. For the iOS half
of mobile UI and for E2E, the negative proof is that the CI workflow
definition wires a required job for each on the relevant trigger path
(workflow-graph/job-metadata inspection, same mechanism as
`SCN-128`/`129`'s iOS half — a missing/non-required job is itself the
denied case); real deliberate-failure execution for both is deferred,
disclosed, not claimed. For the 7th layer
(exploratory), the equivalent proof is manual: `veyro-manual-qa`
deliberately misses/mis-executes an exploratory pass and confirms the
QA record itself flags the gap (a human/Claude-judgment check, not a
harness one) — tracked under `MANUAL_QA.md` surface 10 (**corrected,
Scenario Review round 12, P1-1: this previously pointed at surface 5,
which is failure diagnostics — "deliberately break a gate and confirm
the failure message is actionable" — a different thing from the
exploratory-testing procedure this scenario actually needs; surface 5
didn't describe an exploratory pass at all, and no surface did until
round 12 added one**), not claimed as
an automated failure report. Evidence: 5 real per-layer failure
reports + 2 job-wiring inspection reports (iOS mobile-UI, E2E) + 1
manual QA record. Negative case IS the scenario's own subject; the
companion positive (harness passes a correct fixture) is
`SCN-MOD001-137` (**corrected, Scenario Review round 11, P1-5: this
previously pointed at 001/002, which is false — 001 tests fresh-clone
directory structure and 002 tests the format/lint/type-check stage;
neither runs the unit, component, integration, contract, E2E, or
mobile-UI harness against a passing fixture at all**).

**SCN-MOD001-116 · BND · Major · GOV-01-R01, mis-tagged-test boundary case (P1-2) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Source: `REQUIREMENTS.md` GOV-01-R01's own declared BND coverage —
"harness behavior at pyramid-layer boundaries — e.g. a test mis-tagged
as unit that actually hits a database." Steps: a synthetic test file
placed in the `unit/` test directory, but whose implementation opens a
real database connection (a layer-boundary violation, not a logic
failure). Expected: the test-pyramid harness's own layer-classification
check flags this as a boundary violation — either denying the run or
reclassifying/reporting it as actually an integration-layer test — not
silently running it as a "unit" test with a real DB dependency.
Evidence: the classification/violation report. Negative case IS the
scenario's own subject; the companion positive is a correctly-classified
unit test with no I/O, covered by 001/002.

**SCN-MOD001-137 · HP · Major · GOV-01-R01, per-layer harness positive execution (P1-5) · Automated (4 of 6 automated layers fully real [unit/component/integration/contract]; mobile UI split real-Android/wiring-only-iOS; E2E wiring-only) + Manual (exploratory) · veyro-implementer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 13, E-2): the header/Evidence line
previously said "5 of 6 automated layers real, 1 job-wiring-only,"
which double-counts mobile UI (its Android half sits inside the "5
real," its iOS half sits inside the "1 wiring-only") and undercounts
E2E, which is wiring-only in full, not a fraction of the "1." The
Evidence line's own "5 real + 2 job-wiring = 7 artifacts for 6 layers"
arithmetic was actually correct (mobile UI legitimately produces 2
artifacts, one per platform half) but unexplained, reading as an error
on first pass — the corrected header above states the split
explicitly rather than leaving the reader to reconcile it.**
**Added (Scenario Review round 11, P1-5): `SCN-106` claimed its
companion positive was "001/002," but neither tests this —
`REQUIREMENTS.md` GOV-01-R01's own acceptance criteria require "all
seven layers have a runnable harness" and evidence obligations require
"a passing run of each layer's harness against a trivial/synthetic
fixture," and no scenario in the catalog actually ran the component,
integration, contract, E2E, or mobile-UI harness against anything.
`SCN-023`'s "passes or correctly reports not yet applicable" cannot
substitute, by the same reasoning round 10's own P0-3 applied to the
SAST scanner: it cannot distinguish a working harness from an absent
one.** **Corrected (Scenario Review round 12, P1-2): the original text
ran a real "mobile UI" harness and a real "E2E" harness against
nothing — `IMPLEMENTATION.md` names no mobile-UI test directory and no
E2E test-layer directory at all (E2E exists only as a staging-deploy CI
gate placeholder), and `TEST_PLAN.md` line 26 names the mobile-UI
harness as "Compose UI test / XCUITest-equivalent" — a real XCUITest
run needs a macOS runner, which `SCN-056` (Blocker) forbids referencing
in committed configuration, the identical paid-macOS-runner conflict
round 10's P1-1 fixed for `SCN-128`/`129` one round earlier. Fixed by
applying the same split those two scenarios already established: the
Android/standard-runner half of mobile UI runs for real; the iOS half
is deferred for the paid-macOS-runner reason above, and E2E is
deferred because no E2E test-layer directory exists in
`IMPLEMENTATION.md` at all — **corrected, Scenario Review round 13,
E-5: this previously cited `CAPABILITIES.md`'s test-runner-stack
disposition (line 79) as E2E's reason, but that row defers tool
selection for all six layers equally and does not itself distinguish
E2E; the real, distinguishing reason is the missing directory, stated
here directly instead** — both are proven present and
required-status-checked via workflow-graph/job-metadata inspection
now, with real execution deferred.** Steps: for 5 of the 6 *automated* test-pyramid layers
(unit, component, integration, contract, and the Android half of
mobile UI), add one trivial synthetic passing fixture (e.g. `assert
True`-shaped for unit/component/integration/contract, a no-op
screen-render assertion for the Android/Compose UI test runner) and run
that layer's harness for real. Expected: each layer's harness executes
to completion and reports a real pass (not "0 tests collected"
silently reported as green) — the harness *running* is the evidence,
distinct from `SCN-001` (directory structure only) and `SCN-002` (lint
stage only), neither of which invokes a test-pyramid layer runner at
all. For the iOS half of mobile UI and for E2E, the positive proof is
that the CI workflow definition wires a required job for each on the
relevant trigger path (workflow-graph/job-metadata inspection, same
mechanism as `SCN-128`/`129`'s iOS half) — real execution deferred,
disclosed, not claimed. For the 7th layer (exploratory), the equivalent
positive proof is the documented exploratory-testing procedure itself
existing and being followed once (`MANUAL_QA.md` surface 10 —
**corrected, round 12, P1-1: was surface 5, which is failure
diagnostics, a different thing**), mirroring `SCN-106`'s own
manual/automated split for this requirement's negative case. Evidence:
5 real per-layer pass reports + 2 job-wiring inspection reports (iOS
mobile-UI, E2E) + the exploratory procedure record.

**SCN-MOD001-138 · SEC · Blocker · ADR-005 Decision 2 Part 3, gate 7 (surface-profile activation), deferred-surface build/toolchain carve-out — positive (P0-1, corrected round 13 P1-5: was mis-cited "TSD §24.1 gate 7" — TSD §24.1 defines six gates; gate 7 is ADR-005-added, matching SCN-102/103/112's own citation convention) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 12, P0-1): `IMPLEMENTATION.md` §4 gate
7's own carve-out (added round 11, P2-1, letting a build/toolchain/CI
file pass under a still-DEFERRED surface) was a new pass-path through a
Blocking gate with no scenario at all — `SCN-102` tests an activated
profile passing, `SCN-103` tests a deferred *application*-file denial,
neither tests the carve-out itself.** Steps: a synthetic
`mobile/androidApp/build.gradle.kts`-shaped fixture (a file matching
the gate's closed recognized-extension list, `.gradle.kts`) is added
under the still-DEFERRED Android Host §4.3 profile's path scope; run
`tools/validate_architecture_gates.py --gate surface-profile`.
Expected: PASS, citing the Infra/SRE/CI carve-out by name — the
deferred profile's own `.profile-pending` marker is not treated as a
denial for this recognized file type. Evidence: the gate's own pass
report naming the carve-out.

**SCN-MOD001-139 · SEC · Blocker · ADR-005 Decision 2 Part 3, gate 7 (surface-profile activation), deferred-surface build/toolchain carve-out — negative/boundary (P0-1, corrected round 13 P1-5: same citation fix as SCN-138) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (Scenario Review round 12, P0-1), companion to 138:** proves
the carve-out is scoped to the closed extension list, not to the
surface's whole directory. Steps: same still-DEFERRED
`mobile/androidApp/` fixture as 138, but this time a `.kt`
*application*-logic file is added under `mobile/shared/src/` (the same
deferred surface family) alongside the passing `build.gradle.kts` from
138. Expected: the `.kt` file is denied with `SURFACE_PROFILE_NOT_ACTIVATED`
citing the path and the missing profile, in the same CI run where the
`.gradle.kts` file passes — proving the carve-out does not silently
widen to cover application code merely because it shares a directory
with a recognized build file. Evidence: one pass report (the
`.gradle.kts` file, per 138) and one denial report (the `.kt` file) from
the same run.

**SCN-MOD001-107 · OBS · Major · GOV-01-R08, release-train/changelog generation (P0-2) · Automated · veyro-infra-sre-engineer/Sonnet · NOT EXECUTED**
Source: GOV-01-R08 (`EIP_MIRROR.md` lines 17577-17580). Steps: a
synthetic release cycle runs through the release-train cadence
convention and produces a changelog entry via the changelog tool
wired to the release pipeline (GOV-01-R05). Expected: a real changelog
entry is generated, correctly formatted per the convention document.
Evidence: the generated changelog file/entry. Negative: a release with
no changelog-worthy change produces no spurious entry.

**SCN-MOD001-108 · DR · Major · GOV-01-R08, beta→GA→deprecation lifecycle-stage lint (P0-2) · Automated · veyro-infra-sre-engineer/Sonnet · NOT EXECUTED**
**Corrected (Scenario Review round 3, P2): the negative case's
condition was unfalsifiable as written ("if the policy requires one").**
**Corrected again (Scenario Review round 7, P1-3): the state machine
this scenario declared (`beta -> GA -> deprecated -> removed`, 4
values) did not match the card's own text — `EIP_MIRROR.md`'s Appendix
B GOV-01-R08 text names exactly 3 stages, "beta/GA/deprecation
lifecycle," no `removed` state — nor `IMPLEMENTATION.md` §12's own
`lifecycle_stage` field (added round 6), which correctly used the
card's 3 values. Rewritten to test the real 3-value machine.**
Preconditions: `IMPLEMENTATION.md` §12's `lifecycle_stage` field
(`beta`/`GA`/`deprecated`) on the release-evidence record, per
GOV-01-R08's own card text — a fixed 3-value machine, `beta -> GA ->
deprecated`, with no state beyond `deprecated` (a real release's
eventual removal/archival is out of this lint's scope, since the card
names no such stage). Steps: a synthetic release declares a lifecycle
stage in its release-evidence record; the lint confirms the declared
stage is one of the 3 valid values and that a transition follows the
fixed order. Expected: PASS on a valid transition (e.g. beta→GA).
Negative: an invalid transition (`deprecated` directly to `beta`,
skipping backward with no re-release path — the exact out-of-order
case §12 itself names) is denied, citing the invalid transition — a
real, executable check with no conditional escape clause. Evidence:
the lint's pass/deny report citing the specific transition tested.

**SCN-MOD001-109 · NEG · Blocker · Card-mandated drill: deliberately-failing test blocks the pipeline (P0-3) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 4, P1-2): routed to Sonnet despite
Blocker severity, breaking the tier convention rounds 1-3 all enforced
for SCN-013/062/115 — realigned to Opus.**
Source: `EIP_MIRROR.md` lines 4188-4192 — "prove CI blocks each
architecture gate: ... secret/migration/schema/**test failures**."
Secret (029), migration (070), and schema (034) are covered; this
closes the missing "test failures" case. Steps: a synthetic unit test
deliberately asserts a false condition; push it through the full CI
pipeline (`IMPLEMENTATION.md` §3). Expected: the pipeline halts at the
unit-test stage, blocking every downstream stage — build, integration,
deploy never run. Evidence: pipeline run log showing the halt point.

**SCN-MOD001-110 · BND · Blocker · Card-mandated drill: screen-contract count mismatch (P0-3) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 4, P1-2): same tier realignment as
SCN-109 above.**
Source: `EIP_MIRROR.md` lines 4189-4191 — "screen contract/**count**."
Distinct from SCN-013 (an unmapped Screen ID) — this tests a *count*
mismatch: the canonical screen registry reports N screens for a given
surface, but `screen-contracts.yaml` generates a different count (e.g.
one screen silently dropped during generation). Expected: the generator/
validator denies with a named count-mismatch error citing the expected
vs. actual count, rather than silently emitting a short manifest.

**SCN-MOD001-111 · PERF · Blocker · Gate-bypass-under-load (P1-5) · Automated · veyro-performance-reviewer/Opus · NOT EXECUTED**
Source: `IMPLEMENTATION.md` §5.3 (Load / performance scope — 7
architecture gates as of `ADR-005`'s gate 7 addition, corrected round
3: "confirm none of the 7 architecture gates or CI stages can be
skipped by racing/concurrent pipeline runs, timeout-induced partial
execution, or a resource-exhausted CI runner silently passing"). Steps
cover all 7 gates plus general CI stages, three attack classes each
attempted
independently: (a) trigger two concurrent pipeline runs against the same
PR/ref and confirm both runs' gates are independently enforced, not
racing to a shared, prematurely-cleared status; (b) deliberately induce
a CI-step timeout mid-gate and confirm the step reports failure, not a
silently-skipped/partial pass; (c) simulate a resource-exhausted runner
(e.g. an OOM-killed gate process) and confirm the pipeline reports
failure, not a false green from a process that never finished. Expected:
all three fail closed.

**SCN-MOD001-112 · SEC · Blocker · Surface-profile activation gate — unnamed-path case (P1-6) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (round 2, P1-6, further corrected round 3): the gate design
itself was originally fail-open** — General Web/Edge/Data-AI had no
directory yet and thus no marker for a marker-only check to read, and
one `mobile/.profile-pending` marker couldn't express three distinct
deferred mobile sub-profiles. Fixed in `IMPLEMENTATION.md` §4 gate 7
and `evidence/module-capabilities.yaml`: all 10 §4.3 path prefixes
named in `MODEL_ROUTING.md`'s table now carry either an
activated-profile record or an explicit deferral marker — including
the six with no real directory yet. **Because all 10 named profiles
now have a marker, this scenario's real test is a path matching
*none* of the 10 named globs at all** (an entirely new, unlisted
surface a future module might introduce, e.g. a hypothetical
`analytics/` directory) — the case a marker-keyed check cannot address
by construction, since there is no row to check against. Steps: a
synthetic new top-level directory not matching `backend/**`,
`infra/**`, `contracts/**`, `tools/**`, `.github/workflows/**`, or any
of the 10 §4.3 globs is created with real source files. Expected: the
capability-governance validator (not the per-profile marker check,
which has nothing to key on) flags an unrecognized top-level surface
requiring an explicit `module-capabilities.yaml` decision before it can
be merged — a catch-all "unknown surface" denial distinct from
`SURFACE_PROFILE_NOT_ACTIVATED`. Evidence: the unknown-surface denial
report. Companion positive: 102. Companion marker-present/
profile-not-activated case (a *named* profile's own marker mismatch):
103.

**SCN-MOD001-113 · MIG · Major · GOV-01-R06, rolling-deploy N-1 compatibility (P1-9) · Automated · veyro-backend-engineer/Sonnet · NOT EXECUTED**
Source: TSD §24.2 (`TSD_MIRROR.md` lines 11667-11669) — "Schema and
application deployment ordering is tested against at least previous
supported version for rolling deploy compatibility." Steps: deploy a
synthetic schema change while a synthetic "previous version" application
instance is still running against the old shape (simulating a rolling
deploy's overlap window). Expected: the old-version instance continues
operating correctly against the new schema (the expand-phase guarantee)
— proven, not merely asserted by the migration-safety harness's
ordering alone.

**SCN-MOD001-114 · DATA · Major · GOV-01-R06, migration-record template (P1-9) · Automated · veyro-backend-engineer/Sonnet · NOT EXECUTED**
Source: TSD §24.2 (`TSD_MIRROR.md` lines 11664-11666) — "Every migration
records owner, expected lock/write impact, rollback/forward-fix strategy
and data validation query." Steps: run a synthetic migration through the
migration-record template and confirm all 4 required fields are
populated. Expected: PASS with all 4 fields present. Negative: a
migration submitted with any field missing is rejected by the template
check before the migration is allowed to run.

**SCN-MOD001-115 · INT · Blocker · GOV-01-R07, version-support/kill-switch policy enforcement (P1-10) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (round 2, P1-10); tier corrected (round 3, P1-3): this was
routed to `veyro-implementer`/Sonnet despite being Blocker-severity on
a declared security control (forced-update/kill-switch), contradicting
the tier convention rounds 1 and 2 both enforced for SCN-013/062 —
realigned to Opus.** The "Mobile-version/release policy" named family
previously pointed only at dual-platform-trigger/RTL/a11y/
runner-assignment scenarios (052-054, 099-101) — real scenarios, but
none tested GOV-01-R07's own actual policy content. Source:
`EIP_MIRROR.md` line 17572-17575 and TSD §24.3 (`TSD_MIRROR.md` lines
11672-11681) — minimum supported version, optional/forced update, and
kill-switch policy. Steps: a synthetic backend API version-negotiation
check runs against three synthetic client versions: one within the
minimum-supported range (expect: normal operation), one below minimum
with only an optional-update policy in effect (expect: operates with an
update prompt, not blocked), one below minimum with the kill-switch
active for a security/critical-incompatibility case (expect: blocked,
citing the forced-update requirement). Evidence: three recorded
negotiation outcomes. Negative/failure behavior: a client below minimum
that is NOT blocked when the kill-switch is active is the failure this
scenario exists to catch. **This scenario alone does not close R07's
full coverage — see 117 for crash-monitoring/remote-config and the
kill-switch's own unauthorized-activation control.**

**SCN-MOD001-117 · OBS · Blocker · GOV-01-R07, crash monitoring/remote config, and kill-switch unauthorized-activation control (P1-3) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Added (round 3, P1-3): round 2's own P1-10 finding named
"version-support/kill-switch/**crash-monitoring/remote-config**
policy" as uncovered, but the fix (115) closed only the first two,
while its own Review Log entry claimed the finding "Fixed" in full —
corrected here.** Source: `EIP_MIRROR.md` line 17572-17575 ("crash
monitoring and remote configuration"); `REQUIREMENTS.md`'s own R07
acceptance criteria and security-implication text ("forced-update/
kill-switch... must not be triggerable without the equivalent of an
authorized release decision"). Steps, three parts: (a) a synthetic
crash-monitoring integration point receives a fabricated crash report
and confirms it is recorded/surfaced, not silently dropped; (b) a
synthetic remote-config fetch returns a rollout-percentage change and
confirms the client-side integration point reads it (remote config
controls rollout, per TSD §24.3, but cannot itself repair an
incompatible API contract — confirmed by a companion check that a
remote-config change alone does NOT bypass 115's kill-switch block);
(c) **the unauthorized-activation negative**: an attempt to trigger the
kill-switch via a path other than an authorized release decision (e.g.
a request lacking the release-authorization credential/signature) is
denied. Expected: (a) crash report recorded; (b) remote-config rollout
change applied but kill-switch block from 115 still holds; (c) denied,
citing missing authorization. Evidence: three recorded outcomes.
Negative/failure behavior IS part (c)'s own subject.

### Group N — Scenario Review round 4 remediation: import/validation contract, ADR conformance, agent-definition/MR validator, manifest completeness (P1-5, P1-6, P1-7, P1-8)

**SCN-MOD001-118 · BND · Blocker · Import/validation contract, Appendix F Ready precondition (P1-5) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 5, P1-1): this scenario proves an
actual Ready precondition (Appendix F) — Blocker-severity content
routed to Sonnet with no dual-tier carve-out is the exact tier-
convention violation round 4 itself fixed for SCN-109/110 in the same
session it introduced this scenario. Retitled to
`veyro-security-reviewer`/Opus, matching every other unqualified
Blocker-severity scenario in this catalog.**
Source: `EIP_MIRROR.md` lines 18033-18037 ("Ready requires access to
the canonical approved UX registry and the import/validation
contract"); the contract's own design is in `IMPLEMENTATION.md` §10.
Preconditions: a synthetic copy of the registry's 8-field row format
with deliberately introduced edge cases. Steps: run the import contract
against (a) a normal V1 row with a single clear owning module —
expected: resolves correctly; (b) a row whose `id` prefix matches no
known surface — expected: validation failure naming the specific `id`
and "unknown prefix" reason; (c) a multi-domain row — expected: resolves
to the primary mutation/route contract's owning module, not the
secondary reference. Evidence: three resolution/failure reports.
Negative case is (b)/(c)'s own subject.

**SCN-MOD001-119 · OBS · Major · Appendix I ADR conformance, ADR-004/ADR-015 (P1-6) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 21028-21033 (ADR-004), 21117-21122
(ADR-015); `ADR_CONFORMANCE.md`'s own conformance record. Steps: (a)
confirm no HTTP API surface exists in MOD-001's planned tooling
(ADR-004 — expected: N/A-with-justification holds, re-checked against
the actual `tools/` directory once built); (b) run the migration-safety
harness (SCN-022/070) and confirm its expand/migrate/contract ordering
matches ADR-015's "no destructive schema change in the same release
that stops reading the old shape" rule exactly. Evidence: the
conformance check's own pass/fail per ADR.

**SCN-MOD001-120 · SEC · Blocker · CI/control check over `.claude/agents/` definitions and model-alias/MR-evidence well-formedness (P1-7) · Automated · veyro-security-reviewer/Opus · NOT EXECUTED**
**Corrected (Scenario Review round 5, P1-2/P1-3): part (a) tested the
wrong defect shape, and part (b)'s field list was under-derived from
§4.1's own text — both fixed below. Corrected again (Scenario Review
round 7, P1-4): part (a)'s hardcoded 4-agent list missed a real third
orphan (`veyro-test-author` — named by zero escalation paths, same
class as `BUG-031`, filed separately as `BUG-032`) because the check as
written enumerates a fixed name list rather than deriving it from the
project's own routing design. Fixed by deriving the checked set from a
rule instead of a hardcoded list.**
Source: `EIP_MIRROR.md` lines 4121-4124 ("CI/control checks validate...
Veyro project-agent definitions, model aliases/MR evidence...") and
§4.1's own MR-evidence field list (`EIP_MIRROR.md` lines 1095-1100:
task class, lifecycle role, risk triggers, intended family alias,
resolved model identity/tier runtime evidence, agent/session ID,
verdict — 7 fields, not 4). Steps: (a) **reachability, not dangling-
reference** — the checked set is every registered agent that
`MODEL_ROUTING.md`'s own routing table designates as a target for
*routine-execution escalation* (an agent a session already executing
routine work is meant to hand off to when it hits that agent's trigger
condition), as opposed to a role only ever dispatched directly by the
orchestrating session itself for review/certification/architecture work
(`veyro-lead`, `veyro-scenario-reviewer`, `veyro-code-reviewer`,
`veyro-manual-qa`, `veyro-security-reviewer`, `veyro-performance-reviewer`,
`veyro-gatekeeper` — none of these are meant to be peer-escalation
targets, so their absence from another agent's escalation text is not a
defect). As of this catalog: `veyro-critical-engineer`,
`veyro-backend-engineer`, `veyro-infra-sre-engineer`, and
`veyro-test-author`. Walk that set against the full set of
`.claude/agents/*.md` escalation text, and confirm each is named by at
least one escalation path from somewhere. Expected on a synthetic
fixture where one checked agent is named by zero escalation paths (an
*orphaned* agent, not a reference to a nonexistent one — **this is the
actual `BUG-030` defect class per `BUG_REGISTRY.md`'s own text:
`veyro-implementer.md`'s escalation list omitted
`veyro-critical-engineer`, an omission, not a dangling pointer**):
denial citing the unreachable agent by name. A dangling-reference check
(an escalation path naming an agent that doesn't exist) is evaluated as
a distinct, second condition on the same fixture set, since both are
real defect classes worth catching, but reachability is the one that
actually matches `BUG-030` and the one this scenario's own commentary
claimed to test. (b) a synthetic MR evidence record missing one of the
full 7 required fields (in turn: task class, lifecycle role, risk
triggers, intended family alias, resolved model identity, agent/session
ID, verdict) — expected: denial citing the specific missing field, for
each of the 7. Evidence: the reachability report, the dangling-reference report, and 7 per-field
denial reports. Companion positive: a well-formed agent-definition set
(every registered agent reachable, no dangling references) and a
complete 7-field MR record both pass. **Note for implementation:**
`ROUTING_DRILL_2026-09-14.md`'s existing `MR-MOD001-*` records
(003/004/005) predate this scenario and currently carry only 4 of the 7
required fields (task class, agent, session id, verdict) — closing this
gap for real MR evidence going forward, not just for this scenario's
own synthetic fixtures, is tracked as part of this scenario's own
Implementation Complete work, not a separate obligation.

**SCN-MOD001-121 · OBS · Major · Appendix H.1 manifest completeness (P1-8) · Automated · veyro-implementer/Sonnet · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 20597-20601 (the manifest "must also
record capability dependency IDs, per-gap resolution-attempt counters/
budget evidence, lifecycle review state and rollback target where
applicable"). Steps: validate `evidence/module-capabilities.yaml`
against H.1's full required-field list. Expected: every field is
present, either populated or explicitly N/A with rationale (matching
the file's own existing convention for `required_rule_ids` etc.) — not
silently absent. Evidence: the field-presence check's own report.
Negative case: a synthetic manifest missing one of the four fields
entirely (no key at all, not even an N/A) is denied. **Second negative
case (added, Scenario Review round 10, P1-5): a synthetic manifest
whose `required_agent_roles` key is present and populated, but omits a
role that `MODEL_ROUTE.md`'s own planned-routing table names for this
module — expected: denied, citing the specific missing role by name.**
This closes the exact gap class round 10 found live in this module's
own manifest (`veyro-test-author` present in `MODEL_ROUTE.md` but
absent from `required_agent_roles`) — key-presence alone cannot catch
a populated-but-incomplete list, which is why the original negative
case here passed against that real defect.

**Group O (added, Scenario Review round 5, P0-2): the card's mandatory
Security-scope baseline (`EIP_MIRROR.md` lines 4267-4271) names
"sensitive logging" and "abuse-negative scenarios" as controls, both of
which `IMPLEMENTATION.md` §6 commits MOD-001 to building, and neither
of which had a scenario — a false coverage claim in this file's own §0
("every requirement, gate, and validator this module owns needs its
own real scenario"). Fixed with two new scenarios:**

**SCN-MOD001-122 · SEC · Blocker · Sensitive-logging lint (card
security baseline, `IMPLEMENTATION.md` §6) · Automated ·
veyro-security-reviewer/Opus · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4267-4271 ("sensitive logging" is one of
the card's mandatory security-baseline controls); `IMPLEMENTATION.md`
§6 names the sensitive-logging lint as a real MOD-001 implementation
obligation ("no secret/PII patterns in log statements — a real,
buildable static check"), distinct from SCN-029's secret-scanning
(which scans committed files, not log statements). Steps: run the lint
against a synthetic log statement containing a secret-shaped pattern
(an API-key-shaped string) and a PII-shaped pattern (an email address)
interpolated directly into log text. Expected: both denied, citing the
exact file/line and pattern class. Companion positive: a log statement
using only a pre-redacted placeholder passes. Evidence: the lint's own
denial/pass reports.

**SCN-MOD001-123 · NEG · Major · Abuse-negative fixture pattern (card
security baseline, `IMPLEMENTATION.md` §6) · Automated ·
veyro-implementer/Sonnet · NOT EXECUTED**
Source: `EIP_MIRROR.md` lines 4267-4271 ("abuse-negative scenarios" is
one of the card's mandatory security-baseline controls);
`IMPLEMENTATION.md` §6 distinguishes MOD-001's real obligation (build
the fixture pattern/harness) from later domain modules' obligation
(the actual abuse-scenario *content* for specific business flows) —
the same split SCN-032 already established for the offline-fixture
pattern. Steps: exercise the abuse-negative fixture harness itself (the
thing later domain modules will build real abuse scenarios on top of —
e.g. a rate-limit-shaped request-flood fixture, a parameter-tampering
fixture) against a synthetic abusive-request-shape fixture and a
synthetic legitimate one. Expected: the harness correctly distinguishes
the abusive shape from the legitimate one, and a request-shape with no
matching fixture rule fails closed (denied, not silently allowed).
Evidence: the harness's own classification report.

## 4. Status

**Corrected (Scenario Review round 4, P0-2 — this exact section was
already flagged once, by round 2's own P0-1, and drifted stale again
after round 3's remediation changed SCN-104/105's own status without
updating this summary to match): SCN-104 and SCN-105 are genuinely
`EXECUTED — PASS`** — the corrected routing drill (dispatched to
`veyro-implementer`, the correct subject, after `BUG-030`'s fix) ran for
real, with agent/session ids and verbatim response text preserved in
`evidence/model-routing/ROUTING_DRILL_2026-09-14.md`'s "Corrected
drill" section. This is real, valid evidence of MOD-001's own routing
configuration working, not a claim about MOD-001's own product
implementation (which has not started). **Every other scenario in this
catalog: NOT EXECUTED.** No scenario testing MOD-001's own eventual
implementation is marked PASS.

## 5. Review Log

**Round 1 (2026-09-14):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 74 scenarios.
**Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=4, P1=9, P2=11,
Editorial=4. Findings:

- P0-1: forced-fallback model-assurance negative test (EIP_MIRROR.md
  lines 1109-1111) had no scenario. **Fixed:** SCN-075.
- P0-2: ~14 of the card's mandatory deliberate-violation drills
  (`EIP_MIRROR.md` lines 4188-4228) had no scenario at all. **Fixed:**
  SCN-076 through 093.
- P0-3: the unregistered `veyro-critical-engineer` role, which
  `MODEL_ROUTING.md` says "must be closed before MOD-001+ touches any
  critical slice," was silently asserted resolved ("no new agent
  required") against MOD-001's own GOV-01-R02 critical-slice work with
  no ADR. **Delegated to `veyro-lead` (Opus) for a real architecture
  decision** — not decided by this session on Sonnet, per `OWN-003`.
  See the addendum below once that dispatch returns.
- P0-4: the dependency-vulnerability CI gate, named in Critical
  requirement GOV-01-R04's own text, had no scenario, and SCN-015 falsely
  claimed to cover it. **Fixed:** SCN-094; SCN-015 corrected.
- P1-1: category matrix claimed AUTHN had 2 scenarios; the real count
  was 1 (005 was mistagged SEC in its own detail block). **Fixed:**
  SCN-005 recategorized, SCN-097 added.
- P1-2: "Rule-family coverage" named family pointed at two scenarios
  (042, 057) that don't test rule families; the real scenario (035) was
  positive-only against a card-mandated negative. **Fixed:** SCN-084
  added; family table corrected.
- P1-3: "Gate-bypass attempts" pointed at 020 (wrong threat model —
  local shell-invocation, not CI-workflow-layer) and 029 (not a bypass
  test at all). **Fixed:** SCN-020 rewritten with the correct threat
  model (branch-protection/workflow-configuration bypass classes); 029
  removed from that family row.
- P1-4: SCN-005's RLS negative fixture specified a `BYPASSRLS` role,
  which inverts the TSD's own "production-equivalent, non-privileged
  role" rule and makes the scenario's expected result incoherent.
  **Fixed:** SCN-005 and `IMPLEMENTATION.md` §4 gate 1 corrected.
- P1-5: TSD §24.1 gate 2's normative §6.3 bidirectional-pair reverse-edge
  rule had no fixture. **Fixed:** SCN-095/096 added;
  `IMPLEMENTATION.md` §4 gate 2 corrected.
- P1-6: LIFE scenarios 060/067 were reasoning exercises with no
  executable procedure, marked "Automated" despite being unexecutable by
  a machine. **Fixed:** both rewritten with concrete, distinct fixtures.
- P1-7: PERF scenarios 068/069 had a self-referential, unfalsifiable
  pass condition (budget set from the measurement it validates).
  **Fixed:** pre-declared budgets (15 min pipeline, 10 concurrent/2s
  health-check) set before the measuring run.
- P1-8: no manual-execution disposition existed for 66 of 70 Required
  scenarios, contradicting Appendix G/§9.1's "must be manually executed
  by Claude" requirement. **Fixed:** `MANUAL_QA.md` §2 (scenario→surface
  mapping) added; a clarifying note added to this file's §3 header.
- P1-9: DC-21 (surface-specific profiles, "becomes binding starting
  MOD-001") was resolved in `CAPABILITIES.md`'s own favor ("MOD-001 does
  not itself need a profile") with no ADR, despite `IMPLEMENTATION.md`
  scaffolding 5 of the surfaces DC-21 names. **Delegated to `veyro-lead`
  (Opus)** alongside P0-3 — same dispatch, see addendum below.
- P2/Editorial (11+4 total): REC/AUTHN matrix errors (P2-1, folded into
  P1-1's fix), §9.1 minimum-count misstatement (P2-2, fixed in §0),
  GOV-01-R08 non-verbatim quote (P2-3, fixed in `REQUIREMENTS.md`),
  six-gates named-family range omitting gate 3's negative (P2-4, fixed
  in §2), two gate sub-rules with no fixture (P2-5 — the §6.3 half is
  fixed via P1-5; TSD §24.1 gate 3's "compatibility/classification
  changes require owner approval" and gate 6's "explicit shared-contract
  exception" sub-clauses remain genuinely unfixtured, carried forward
  as a disclosed residual, not hidden), declared-format not followed for
  053/054 (P2-6, fixed), six positive-only scenarios missing cheap
  negative companions (P2-7 — 098/099/100/101 added for 017/051/052/055;
  021/035/052/055's own instances are addressed via 084 and the
  companions just named), SCN-021's two unrelated checks (P2-8, split
  into 021/021b), DC-11 regression framing (P2-9, fixed in SCN-061),
  ALT scenarios 073/074 touching acceptance contracts (P2-10, both
  reclassified to Required/INT and Required/PERF), SCN-051's genuine
  soft boundary (not flagged as a defect — deferred correctly), plus 4
  Editorial items (SCN-066's dual-tag now explicit rather than silent;
  `TESTSPRITE.md`'s "ish" citation fixed to an exact line range; the
  `ahmadmabrook` remote name independently re-verified correct via `git
  remote -v`, no fix needed; the "27 named families" claim corrected to
  reflect the real, now-accurate family table). Three tier-routing
  inconsistencies noted in the review's "checked and clean" section were
  also fixed for consistency (SCN-013, SCN-062 realigned to Opus;
  SCN-043 left as-is, judged defensible by the reviewer).

Full original review text: preserved in this session's own transcript;
not duplicated here to avoid the exact drift-by-restatement failure mode
MOD-000's own project history repeatedly found and fixed (see
`CURRENT_HANDOFF.md`'s chunk 30 for that lesson) — this log states what
was found and what was done about it, not a second copy of the
reviewer's full prose.

**Addendum — `veyro-lead` (Opus) ADR dispatch returned:** both P0-3 and
P1-9 required real architecture decisions, not documentation fixes.
`veyro-lead` decided (1) `veyro-critical-engineer` (Opus) must be
registered, bounded to exactly 3 slices, closing MODEL_ROUTING.md's gap
by registration rather than by invoking the existing fallback text; (2)
two §4.3 surface profiles (Infra/SRE/CI, Backend) genuinely activate for
MOD-001's own real content, contrary to `CAPABILITIES.md`'s original
"none activated" claim, with the other 8 correctly deferred but now
mechanically enforced via a new `surface_profile_activation` CI gate
rather than left interpretive. Full reasoning:
`knowledge/04-Decisions/ADR-005-mod001-critical-slice-and-surface-profile-routing.md`.
**A second capability gap was found while implementing this decision:**
neither `veyro-lead` (wrong tool grant) nor this orchestrating session
(`.claude/agents/**` Edit/Write-denied by `.claude/settings.json`) can
create the three required agent files — filed as `BUG-029`, routed to
the owner, same pattern as `BUG-028`. All documentation-side
consequences of ADR-005 (`MODEL_ROUTING.md`, `MODEL_ROUTE.md`,
`REQUIREMENTS.md`, `CAPABILITIES.md`, `IMPLEMENTATION.md`) are updated
this session; SCN-102 through 105 added for the new gate and routing
drill. **MOD-001 cannot reach Definition of Ready until `BUG-029`
resolves** — this is now the sole remaining blocker, distinct from and
in addition to Scenario Review round 2's own verdict.

**Round 2 (2026-09-14):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the remediated set (106 scenarios) plus the
ADR-005/BUG-029 documentation changes. **Verdict:
`MOD-001 SCENARIO REVIEW BLOCKED`.** P0=3, P1=10, P2=8, Editorial=4.
Findings and disposition:

- P0-1: `BUG-029`'s closure hadn't propagated — `STATUS.md`,
  `SCENARIOS.md` (this section), `MODEL_ROUTE.md`, `CAPABILITIES.md`,
  and `evidence/module-capabilities.yaml` all still said
  registration-blocked while `MODEL_ROUTING.md` already said
  REGISTERED, and this file marked SCN-104/105 both `NOT EXECUTED` and
  "cannot execute" while the drill record showed both PASS. **Fixed:**
  all five files corrected this session (see their own edit history);
  §4 above corrected to state the real, nuanced status rather than
  either extreme.
- P0-2: GOV-01-R01 and GOV-01-R08's own declared scenario coverage
  (BND for R01; OBS/DR for R08) didn't correspond to any real scenario
  — the catalog's own §0 floor claim ("every requirement... needs its
  own real scenario") was false for these two Critical requirements.
  **Fixed:** SCN-106 (R01, per-layer deliberately-broken-fixture proof)
  and SCN-107/108 (R08, release-train/changelog generation and the
  beta→GA→deprecation lifecycle-stage lint) added — see Group M below.
- P0-3: the card's own mandated "test failures" and "screen contract
  **count**" deliberate-violation drills (`EIP_MIRROR.md` lines
  4188-4192) were missed by round 1's Group K sweep. **Fixed:**
  SCN-109 (deliberately-failing test blocks the pipeline) and SCN-110
  (screen-contract *count* mismatch, distinct from SCN-013's
  unmapped-ID case) added.
- P1-1: the category matrix's own "independently verified against each
  detail block" claim was false in 4 places (SCN-075 listed under AUTHN
  but tagged SEC; SCN-067 silently dual-counted TEN+LIFE; SCN-042/084
  appeared in no category row). **Fixed:** matrix corrected below.
- P1-2: `REQUIREMENTS.md`'s GOV-01-R04 acceptance criteria still
  described the retired local-shell-invocation bypass model P1-3
  (round 1) replaced in `SCENARIOS.md`/`IMPLEMENTATION.md`. **Fixed:**
  `REQUIREMENTS.md` corrected to the CI-workflow-layer model.
- P1-3: SCN-020's rewritten threat model, while correctly scoped to the
  CI-workflow layer, omitted the highest-yield real bypass classes
  (branch-protection admin override, required-check name drift, direct
  push bypassing the PR path, `pull_request_target`) and never actually
  inspected the branch-protection configuration it claimed protected
  the gate. **Fixed:** SCN-020 expanded with all four classes plus a
  step that inspects the protection rule itself, not just outcomes.
- P1-4: `IMPLEMENTATION.md` §5.1 still specified the self-referential
  PERF budget P1-7 (round 1) had already fixed in `SCENARIOS.md`.
  **Fixed:** §5.1 corrected to the same pre-declared 15-minute budget.
- P1-5: `IMPLEMENTATION.md` §5.3's "gate-bypass-under-load" scope
  (racing/concurrent runs, timeout-induced partial execution, resource
  exhaustion) had no scenario. **Fixed:** SCN-111 added.
- P1-6: the `surface_profile_activation` gate (added round 1 for
  ADR-005 Decision 2 Part 3) was fail-open by its own marker-only
  design — General Web/Edge/Data-AI have no directory yet and thus no
  marker to check, and one `mobile/.profile-pending` marker cannot
  express three distinct deferred mobile sub-profiles. **Fixed:**
  `IMPLEMENTATION.md` §4 gate 7 corrected to require a marker (or
  activated-profile record) for *every* deferred §4.3 path prefix
  named in `MODEL_ROUTING.md`'s own table, denying by default on a
  missing marker rather than only on a marker/reality mismatch;
  `mobile/` split into three sub-markers. SCN-112 added for the
  no-marker-at-all case.
- P1-7: `MANUAL_QA.md` §2's mapping omitted SCN-102/103/104/105
  entirely, leaving 4 Blocker-severity scenarios (including the
  routing drill itself) with no manual-execution path. **Fixed:**
  mapping extended.
- P1-8: `ADR-005` binding condition 2 (independent review of the
  critical-engineer definition) had no durable evidence file — only
  session context. **Fixed:**
  `evidence/model-routing/CRITICAL_ENGINEER_DEFINITION_REVIEW_2026-09-14.md`
  authored, recording that review's real verdict (BLOCKED, see below).
- P1-9: GOV-01-R06's own committed obligations (a rolling-deploy N-1
  compatibility test; a migration-record template capturing TSD
  §24.2's 4 required fields) had no scenario. **Fixed:** SCN-113/114
  added.
- P1-10: the "Mobile-version/release policy" named-family row pointed
  at scenarios (052-054, 099-101) that test dual-platform triggers and
  RTL/a11y/runner-assignment, never GOV-01-R07's actual version-support/
  kill-switch/crash-monitoring/remote-config policy. **Fixed:** row
  corrected to point at new scenarios; see Group M.
- P2/Editorial (8+4): dangling section self-references in
  `REQUIREMENTS.md` (§12/§8/§9/§5 don't exist in that file's own
  numbering — fixed, corrected to point at `IMPLEMENTATION.md`'s real
  section numbers); `TEST_PLAN.md`'s stale regression-triviality framing
  and "6 architecture-gate validators" count (now 7) — fixed; Group
  K/L's missing Evidence/Negative-failure fields — fixed for the P0/P1
  items above, carried forward as a disclosed residual for the
  remainder (a full per-scenario format pass on all 26 Group K/L
  entries was judged disproportionate this round; flagged, not hidden);
  `evidence/module-capabilities.yaml`'s silently-dropped Financial
  cross-cutting control — fixed, added explicitly with rationale;
  SCN-092's missing durability/determinism sub-check, SCN-084's missing
  multi-family-naming sub-case, SCN-087's overstated §9.1 citation, and
  SCN-095's off-by-one line citation — left as disclosed residuals, not
  fixed this round (real but low-impact, and this round's budget went to
  the P0/P1 items); front-matter/count-denominator inconsistencies
  (066/67 vs 70, `status` line) — fixed.

**Addendum — the independent `veyro-critical-engineer` definition
review (ADR-005 binding condition 2) also returned BLOCKED**, finding
the definition itself sound but the routing integration broken:
`veyro-implementer.md`'s own escalation list doesn't name the new role,
so nothing actually routes to it from the tier below. This is
`BUG-030` — a second instance of the `.claude/agents/**` Edit/Write-deny
capability gap, this time for *existing* files. The routing drill this
session ran (SCN-104/105) also targeted the wrong subject (dispatched
directly to `veyro-critical-engineer` instead of testing whether
`veyro-implementer` escalates to it) and has been corrected in its own
evidence file to say so; a valid re-run is blocked on `BUG-030`.

**`BUG-030` was closed the same session it was found** — the owner
applied both prepared edits (commit `9f5efd4`); this session
independently verified byte-for-byte match and ran a corrected 3-case
routing drill dispatched to `veyro-implementer` (the correct subject),
proving real escalation to `veyro-critical-engineer`, correct retention
of routine work, and correct escalation to `veyro-lead` for an
architecture/scope decision. A separate independent re-review of the
critical-engineer definition and routing then returned
`VEYRO-CRITICAL-ENGINEER REGISTRATION APPROVED`.

**Round 3 (2026-09-14):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 106 scenarios
plus the BUG-030 fix. **Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.**
P0=2, P1=7, P2=8, Editorial=4. Findings and disposition:

- P0-1: `BUG-030`'s closure and the corrected drill's PASS had not
  propagated — a third consecutive round finding this exact species,
  now across `STATUS.md`, this file's own §4/§5/SCN-104-105 blocks,
  `MODEL_ROUTE.md`, `CAPABILITIES.md`, `MANUAL_QA.md`,
  `evidence/module-capabilities.yaml`, and — found independently by a
  full grep sweep this round rather than trusting prior "fixed" claims
  — `knowledge/00-System/CURRENT_STATE.md`'s entire MOD-001 section,
  untouched since the module's very first activation and still
  describing the long-closed `BUG-028` docx gap as current. **Fixed:**
  every file above corrected this round; `STATUS.md`, `MODEL_ROUTE.md`,
  and `CURRENT_STATE.md` restructured to point at this file (or at
  `STATUS.md`) as the single source of truth for round/status counts
  rather than each restating them — the same de-duplication fix
  MOD-000's own Phase 10 eventually adopted after five rounds of this
  exact recurrence.
- P0-2: round 2's own P0-1 remediation was itself incomplete —
  `REQUIREMENTS.md` §0 and `IMPLEMENTATION.md` §1's topology comment
  both still said "registration blocked by BUG-029," proving the
  "fixed all five files" claim in round 2's own log entry was an
  enumerated list, not a searched one. **Fixed:** both corrected; this
  round's fixes were verified by grep sweep, not enumeration.
- P1-1: the category matrix's "re-verified against each detail block"
  claim was false again (SCN-112 listed under BND, tagged SEC in its
  own block). **Fixed.**
- P1-2: SCN-106 was mistagged BND while its actual steps tested the
  NEG obligation; the real BND case (a test mis-tagged as unit that
  hits a database) had no scenario; the "exploratory layer" claim was
  not executable as an automated harness. **Fixed:** SCN-106
  recategorized NEG, SCN-116 added for the real BND case, exploratory
  handling corrected to manual QA.
- P1-3: GOV-01-R07's crash-monitoring/remote-config obligations still
  had no scenario despite round 2's own log claiming the finding
  "Fixed" in full; SCN-115 never tested the kill-switch's unauthorized-
  activation control; SCN-115's Blocker severity routed to Sonnet,
  breaking the tier convention. **Fixed:** SCN-117 added (crash
  monitoring, remote config, unauthorized-activation negative);
  SCN-115 realigned to Opus.
- P1-4: `REQUIREMENTS.md`'s gate-bypass acceptance criteria said the
  gate must "resist" all 4 real bypass classes uniformly, contradicting
  SCN-020's own (correct) distinction that branch-protection admin
  override is a disclosed, owner-controlled escape hatch, not a defect
  to resist. **Fixed:** `REQUIREMENTS.md` and `IMPLEMENTATION.md` §3
  corrected to match SCN-020's own nuanced framing.
- P1-5: the surface-profile gate's fail-open hole wasn't fully closed —
  Data/AI's path scope was still the vague "data-ai-scoped paths" in
  `MODEL_ROUTING.md` (a marker-keyed check cannot key on a non-glob),
  and `module-capabilities.yaml` still listed only 4 of 10 §4.3 paths.
  **Fixed:** `MODEL_ROUTING.md` given a concrete `data-ai/**` glob and
  a concrete Front-Desk/Edge-Bridge glob; `module-capabilities.yaml`
  rewritten with all 10 named paths, each carrying a marker;
  `IMPLEMENTATION.md` §4 gate 7 and `SCENARIOS.md` SCN-112 corrected to
  test the real residual (a completely unlisted top-level surface, not
  any of the 10 now-marked ones).
- P1-6: `ADR-005` binding condition 4 (MR evidence with resolved model
  identity) was still open, while `BUG-030`'s closure note overstated
  "both binding-condition gaps... are closed." **Fixed:** an addendum
  appended to `ADR-005` formally accepting the model-identity residual
  as a disclosed, non-blocking limitation on the same terms MOD-000's
  own `BUG-027` was accepted — not silently left ambiguous, and not
  claimed closed when it wasn't.
- P1-7: SCN-104/105's own detail blocks still specified the invalid
  procedure (dispatch directly to `veyro-critical-engineer`) the actual
  drill had already abandoned; `MANUAL_QA.md` claimed a correction that
  was never made. **Fixed:** both detail blocks rewritten to match the
  real, executed, corrected procedure and marked `EXECUTED — PASS`
  (the first scenarios in this catalog to reach that status); the
  third (architecture-routing) dispatch recorded as additional evidence
  under 105 rather than left with no catalog entry.
- P2/Editorial (8+4): a stale prose paragraph in §1 flatly contradicting
  the table two paragraphs above it over SCN-042's placement — fixed by
  removing the stale paragraph; the named-family row count disagreeing
  three ways (29/33/35) — fixed, stated once at 35, not restated
  elsewhere; the independent security review's own P1-1/P1-4 findings
  about the routing drill's overclaimed "not charter-echo" language and
  unpreserved verbatim response text — fixed, verbatim responses now
  quoted in the drill record and the verdict narrowed to what the drill
  actually establishes; SCN-108's unfalsifiable negative condition —
  fixed with a concrete fixed state machine; SCN-092's missing
  durability/determinism sub-check — fixed; the total-scenario-count
  off-by-one (116 detail blocks vs. a stated 115) — fixed and, per the
  de-duplication lesson, stated once, in §0, nowhere else; "6 vs 7
  architecture gates" in `IMPLEMENTATION.md` §5.3/SCN-111 after gate 7's
  addition — fixed. **Disclosed, not fixed this round:** most of Group
  K/L/M's scenarios (076-101, 106-117) still lack a distinct
  Preconditions/Evidence-requirement field split per §3's declared
  format — a full per-scenario format pass across ~40 entries was
  judged disproportionate against this round's P0/P1 list, same
  judgment call round 2 made for the same residual; `SCN-MOD001-021b`'s
  ID still violates the `SCN-<MOD>-<NNN>` stable-ID format (a letter
  suffix rather than a number) — flagged, not renumbered, since
  renumbering an already-cited ID has its own drift risk. **Formally
  accepted as a permanent, non-blocking deviation (Scenario Review
  round 10, P2-5): this residual survived seven rounds with no
  explicit acceptance record distinct from the "flagged, not
  renumbered" note above. This line is that record — the deviation is
  accepted for the life of this catalog; `SCN-MOD001-021b` will never
  be renumbered, and no future round needs to re-flag it.**

**Round 4 (2026-09-15):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 118 scenarios
plus round 3's remediation, explicitly instructed not to inherit round
3's conclusions. **Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=2,
P1=8, P2=9, Editorial=4. Findings and disposition:

- P0-1: the second (post-`BUG-030`-fix) independent critical-engineer
  definition review had genuinely run via a real Agent dispatch and
  returned APPROVED, but its result was never persisted to a durable
  evidence file — only referenced in prose across `STATUS.md`, this
  file, `CURRENT_STATE.md`, and `CURRENT_HANDOFF.md`, leaving a
  Definition-of-Ready-blocking condition resting on no durable record.
  **Fixed:** `evidence/model-routing/CRITICAL_ENGINEER_DEFINITION_REVIEW_ROUND2_2026-09-14.md`
  authored, reconstructing the real dispatch's actual findings; the
  original review file re-framed as round 1, explicitly superseded by
  round 2's APPROVED.
- P0-2: round 3's own remediation had changed SCN-104/105's status to
  `EXECUTED — PASS`, but that fact was never propagated to this file's
  own §0/§4, `STATUS.md`, and `TEST_RESULTS.md`'s blanket "no scenario
  marked PASS"/"NOT EXECUTED" claims — a direct, self-contradicting
  staleness the same species as round 3's own P0-1, one round later.
  **Fixed:** explicit carve-outs added in all four locations
  distinguishing the routing-drill's real executed evidence from
  MOD-001's own (still zero-PASS) product-implementation scenarios.
- P1-1/P1-2: category-matrix mistags (SCN-112 needed the SEC row, not
  its prior placement; SCN-117 missing from the OBS row). **Fixed.**
- P1-3: SCN-109/110 were routed to `veyro-implementer`/Sonnet despite
  testing security-assurance-tier content. **Fixed:** retitled to
  `veyro-security-reviewer`/Opus.
- P1-4: `MODEL_ROUTE.md` still carried a stale "registration blocked by
  a second capability gap (BUG-029)" paragraph, and `CURRENT_STATE.md`
  restated a scenario count ("115-scenario catalog") that had already
  gone stale the same round it was written. **Fixed:** stale paragraph
  removed; `CURRENT_STATE.md` corrected to point at this file's §0
  rather than restate a number.
- P1-5: `REQUIREMENTS.md` §4 had been treating the generic EIP §21.2
  card "Screens" boilerplate as MOD-001's real Ready condition, when
  Appendix F's MOD-001-specific row actually overrides it with
  different text — the EIP's own v1.2 changelog confirms the generic
  condition was removed for MOD-001/non-UI modules. Caught by the
  reviewer directly grepping Appendix F rather than trusting the prior
  citation. **Fixed:** `REQUIREMENTS.md` §4 rewritten to quote Appendix
  F's real MOD-001 row verbatim; new `IMPLEMENTATION.md` §10
  (import/validation-contract design) and §11 (documenting the
  already-satisfied half of the precondition) added.
- P1-6: Appendix I maps `ADR-004`/`ADR-015` and `RB-GOV-01` to MOD-001,
  none of which had a conformance record or runbook. **Fixed:** new
  `ADR_CONFORMANCE.md` and `RUNBOOK.md` authored; corresponding
  obligation rows added to `REQUIREMENTS.md` §3.
- P1-7/P1-8: no scenario tested the agent-definition/MR-evidence
  validator or Appendix H.1's manifest-completeness requirement, and
  `evidence/module-capabilities.yaml` was missing 4 of Appendix H.1's
  required fields entirely (not even as explicit N/A) — capability
  dependency IDs, per-gap resolution-attempt budget evidence, lifecycle
  review state, rollback target. **Fixed:** `SCN-MOD001-118` through
  `121` ("Group N") added, with `MANUAL_QA.md` §2 extended to map all
  four to a manual-QA surface; `module-capabilities.yaml` extended with
  the 4 missing fields, following the file's own explicit-N/A
  convention.
- P2/Editorial (9+4): not addressed this round, per the mission's own
  rule that P2/Editorial handling is gated on P0=0/P1=0, which round 4
  did not return. Carried forward, not hidden or downgraded.

**All P0/P1 findings from round 4 were remediated within the same
session they were found** (commit `d56576c`), followed by a durable
closeout commit (`845e033`) correcting `CURRENT_HANDOFF.md`/
`CURRENT_STATE.md`. **Per the owner's explicit review-budget rule,
Definition of Ready was NOT evaluated after this remediation** — round
4 itself had returned P0/P1, so self-declaring Ready or proceeding to
the DoR checklist would have violated that rule directly. The
remediation's own internal consistency has not yet been independently
confirmed — that confirmation is round 5's own subject.

**Round 5 (2026-09-16):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 122 scenarios
plus round 4's remediation, explicitly instructed not to inherit round
4's conclusions. Independently re-derived coverage from source rather
than trusting round 4's own "fixed" claims — confirmed round 4's
remediation substantively held on every point it checked (all 122
detail blocks exist with no duplicates/gaps, the category matrix
matches every detail-block tag in all 25 rows for the first time, the
Appendix H.1 fields are substantively populated not empty stubs,
`MANUAL_QA.md` covers all 122 scenarios, the ADR-005 routing text in
`veyro-implementer.md` matches the routing drill's verbatim quote,
no file claims MOD-001 is Ready). **Verdict: `MOD-001 SCENARIO REVIEW
BLOCKED`.** P0=2, P1=4, P2=11, Editorial=4. Findings and disposition:

- P0-1: `REQUIREMENTS.md` §4 and `IMPLEMENTATION.md` §10 — both written
  in round 4's own remediation — stated opposite things about whether
  the Appendix F import/validation-contract design was done: §4 said
  "NOT yet satisfied... has not yet closed" and "not yet a scenario"
  in the same sentence that cited `SCN-118`, while §10 *is* that design,
  already authored. **Fixed:** §4 rewritten to state plainly that the
  design is closed (`IMPLEMENTATION.md` §10 documents it; `SCN-118`
  tests it once a generator exists to run it against — the design
  being done and the generator/scenario execution being future
  Implementation Complete work are not the same claim, and the text now
  says which is which); the Conclusion paragraph corrected to match.
- P0-2: three controls in the card's mandatory Security-scope baseline
  ("sensitive logging", "abuse-negative scenarios") — **round 8's own
  correction: this line said "three" and named only two; the third
  ("input/output data exposure") was missed here and inherited
  unchallenged by rounds 6 and 7 — see round 8's own entry below for
  its real fix (`SCN-MOD001-126`)** — both explicit
  MOD-001 implementation obligations per `IMPLEMENTATION.md` §6 — had
  zero scenarios, directly contradicting §0's own "every requirement,
  gate, and validator this module owns needs its own real scenario"
  claim. **Fixed:** `SCN-MOD001-122` (sensitive-logging lint, SEC,
  Blocker, Opus) and `SCN-MOD001-123` (abuse-negative fixture pattern,
  NEG, Major, Sonnet — matching SCN-032's existing harness-pattern
  precedent) added; §0's count and §1's category matrix updated.
- P1-1: `SCN-118` (Blocker severity, an actual Appendix F Ready
  precondition) was routed to `veyro-implementer`/Sonnet with no
  dual-tier carve-out — the same tier-convention violation round 4
  itself fixed for SCN-109/110 in the same session it introduced this
  scenario. **Fixed:** retitled to `veyro-security-reviewer`/Opus.
- P1-2: `SCN-120`'s part (a) tested a dangling-reference defect
  (escalation text naming a nonexistent agent) while its own commentary
  claimed to test "exactly the `BUG-030` defect class" — `BUG-030`'s
  real defect was the inverse: an *orphaned* agent (`veyro-critical-engineer`)
  that nothing routed to, an omission, not a dangling pointer. The same
  omission-class defect is currently live for `veyro-backend-engineer`
  and `veyro-infra-sre-engineer` (confirmed: neither is named anywhere
  in `veyro-implementer.md`, per
  `CRITICAL_ENGINEER_DEFINITION_REVIEW_ROUND2_2026-09-14.md`'s own P2-1),
  which the scenario as written would not catch. **Fixed:** part (a)
  rewritten to test reachability (every registered implementation agent
  named by at least one escalation path) as its own condition, with the
  dangling-reference check kept as a distinct second condition rather
  than conflated with it.
- P1-3: `SCN-120`'s part (b) tested MR evidence against a 4-field list
  (task class, agent, model, verdict) that does not match EIP §4.1's
  own real 7-field requirement (task class, lifecycle role, risk
  triggers, intended family alias, resolved model identity, agent/
  session ID, verdict) — under which the drill's own existing
  `MR-MOD001-*` evidence records are themselves incomplete. **Fixed:**
  part (b) rewritten against the real 7-field list; a note added
  flagging the existing MR-evidence records' own 4/7 gap as
  Implementation Complete work this scenario's own execution will
  close, not a separate, newly-discovered bug (no product code exists
  yet for those records to test).
- P1-4: round 4 added two new obligations (the agent-definition/MR-
  evidence validator, the ADR-conformance check) and their scenarios,
  but never added either to `IMPLEMENTATION.md`'s tools inventory (§1)
  or CI pipeline-stage table (§3) — a scenario whose mechanism appears
  in no implementation plan cannot be executed at Implementation
  Complete. **Fixed:** `tools/validate_agent_definitions.py` and
  `tools/validate_adr_conformance.py` added to §1's inventory and as new
  rows in §3's pipeline-stage table (deliberately NOT added to §4's
  seven-gate table, since neither is one of TSD §24.1's architecture
  gates — they are EIP §4.1's own separate CI/control-check
  requirement); `REQUIREMENTS.md`'s corresponding obligation rows
  updated to point at the concrete tool paths instead of "New tool."
- P2 (11) / Editorial (4): not addressed this round, per the mission's
  own rule that P2/Editorial handling is gated on P0=0/P1=0, which
  round 5 did not return. Carried forward, not hidden or downgraded —
  full list in the round-5 dispatch's own findings, not restated here.

**All P0/P1 findings from round 5 were remediated within the same
session they were found.** Per the owner's explicit review-budget rule,
Definition of Ready was again NOT evaluated after this remediation —
round 5 itself had returned P0/P1.

**Round 6 (2026-09-16):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 124 scenarios
plus round 5's remediation, explicitly instructed not to inherit round
5's conclusions. Independently re-derived coverage from source and
confirmed round 5's remediation substantively held (all 124 detail
blocks present with no duplicates/gaps, the category matrix matches
every detail-block tag in all 25 rows, SCN-118's tier fix and SCN-120's
reachability rewrite both held, `MANUAL_QA.md` covers all 124, the
`ADR-005` escalation text still matches, no file claims MOD-001 is
Ready). **Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=1, P1=4,
P2=6, Editorial=5. Findings and disposition:

- P0-1: the card-mandated idempotency-contract lint (`EIP_MIRROR.md`
  lines 4147-4156 — six required elements: scoped Idempotency-Key
  tuple, retention window, stored request hash, the stable 409 code,
  `command_id` propagation, provider-idempotency derivatives) had no
  scenario that actually ran a lint — `SCN-016`'s procedure tested only
  runtime dedup behavior of an already-well-formed endpoint, and
  `IMPLEMENTATION.md` had zero mentions of "idempot" anywhere (no tool,
  no pipeline stage, no gate). **Fixed:** `SCN-016` split into a lint
  half (a) testing all 6 required elements against 6 synthetic
  declarations, each missing exactly one, plus a positive case, and a
  runtime half (b) preserving the original dedup/409 check;
  `tools/validate_idempotency_contract.py` added to `IMPLEMENTATION.md`
  §1/§3; `REQUIREMENTS.md`'s obligation row pointed at both.
- P1-1: round 5's own two new scenarios (`SCN-122`/`123`) had no
  implementation mechanism — the identical defect round 5's own P1-4
  had just fixed for `SCN-119`/`120` in the same session that created
  122/123. **Fixed:** `tools/validate_sensitive_logging.py` and
  `tools/abuse_negative_fixture_harness.py` added to `IMPLEMENTATION.md`
  §1/§3; `REQUIREMENTS.md` §3 given obligation rows for both, previously
  entirely absent.
- P1-2: GOV-01-R07's (mobile release/version) and GOV-01-R08's
  (release lifecycle) own "Implementation obligations" text in
  `REQUIREMENTS.md` had never become a concrete file/CI-stage plan —
  twelve scenarios depended on mechanisms `IMPLEMENTATION.md` never
  named (toolchain matrix, release policy, CI runner assignment,
  common-code path-filter rule, release-train/changelog convention,
  lifecycle-stage field). **Fixed:** new `IMPLEMENTATION.md` §12 names
  `mobile/TOOLCHAIN_MATRIX.md`, `mobile/RELEASE_POLICY.md`,
  `RELEASE_TRAIN.md`, and 3 new §3 pipeline-stage rows (mobile CI
  runner assignment, common-code dual-platform regression trigger,
  release-lifecycle-stage lint); `REQUIREMENTS.md`'s R07/R08 obligation
  text now points at §12.
- P1-3: `SCN-071`/`072` were classified Optional/ALT in violation of
  §9.1's own rule that Required is rule-derived from tracing to a
  Critical requirement, never a discretionary reduction — both trace to
  a Critical GOV-01 requirement (R01, R05), the same shape round 1
  already found disqualifying for `SCN-073`/`074`'s ALT status (P2-10)
  but never applied here. **Fixed:** both reclassified Required —
  `SCN-071` to HP (duplicates `SCN-001`'s own acceptance criterion via
  an alternate path), `SCN-072` to REC (its "still promotes/rolls-back
  correctly" expected result is GOV-01-R05's own acceptance criterion,
  matching `SCN-058`/`066`'s category); §0/§1 updated (124 Required + 0
  Optional — 0 Optional is legitimate for an O-classified category, not
  a gap).
- P1-4: `BUG-030`'s exact defect class (an orphaned agent nothing
  routes to) is independently confirmed still live today for
  `veyro-backend-engineer`/
  `veyro-infra-sre-engineer` (registered but named by zero escalation
  paths in `.claude/agents/*.md`) — a disposition for this already
  existed in `CRITICAL_ENGINEER_DEFINITION_REVIEW_ROUND2_2026-09-14.md`'s
  own P2-1 finding, but had never been propagated to `BUG_REGISTRY.md`
  (which still claimed "0 open P1 bugs") or `STATUS.md`'s own gate
  checklist. **Fixed:** filed as `BUG-031` (P1, OPEN, non-blocking for
  Definition of Ready, must close before real `backend/**`/`infra/**`
  implementation begins) in both files.
- P2 (6) / Editorial (5): not addressed this round, per the mission's
  own rule that P2/Editorial handling is gated on P0=0/P1=0, which
  round 6 did not return. Carried forward, not hidden or downgraded.

**All P0/P1 findings from round 6 were remediated within the same
session they were found.** Per the owner's explicit review-budget rule,
Definition of Ready was again NOT evaluated after this remediation —
round 6 itself had returned a P0.

**Round 7 (2026-09-16):** two independent Opus dispatches ran this
round, per the mission's own explicit instruction not to trust round
6's "non-blocking" classification of `BUG-031` merely because it was
stated: (1) a fresh-context `veyro-scenario-reviewer` Scenario Review,
and (2) a separate, dedicated `veyro-security-reviewer` review whose
sole subject was BUG-031's actual Ready-gate impact.

**Scenario Review verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=2,
P1=5, P2=9, Editorial=6. Findings and disposition:

- P0-1: the baseline-artifact-binding validator's card text
  (`EIP_MIRROR.md` lines 4140-4143, 4253-4263) mandates 5 distinct
  fail-closed conditions; only the identity/hash-mismatch case had a
  scenario (`SCN-025`/`026`). **Fixed:** `SCN-MOD001-124` added,
  covering the other 4 (unapproved candidate EIP, missing/ambiguous
  artifact identity, missing content hash, missing
  `SESSION_BOOTSTRAP.md` enforcement metadata).
- P0-2: three TSD §24.3 rules (white-label release metadata, isolated-
  PR toolchain-upgrade qualification, KMP shared-module versioning/
  independent release trains) were named nowhere in MOD-001's files
  despite `REQUIREMENTS.md` claiming "full text folded into GOV-01-R07."
  **Fixed:** `mobile/TOOLCHAIN_MATRIX.md` extended with
  `shared_module_version`/`whitelabel_release_metadata` fields; a new
  isolated-PR qualification-gate CI stage added to `IMPLEMENTATION.md`
  §12/§3.
- P1-1: `SCENARIOS.md` §1's own closing prose still asserted SCN-071/072
  "do not themselves assert gate/acceptance-contract behavior" —
  directly contradicting round 6's own P1-3 fix three lines above it.
  **Fixed:** stale paragraph corrected.
- P1-2: round 6's §12 fix did not hold end-to-end for 5 of the 12
  scenarios it named (SCN-115, 117, 050, 051/099, 107) — deferring
  backend-side obligations (version negotiation, crash/remote-config
  intake) to MOD-006 mis-assigned them, since TSD §24.3 makes them
  backend rules. **Fixed:** `backend/app/version_negotiation.py` and
  `backend/app/crash_remote_config_intake.py` added as real MOD-001
  backend mechanisms; `tools/validate_toolchain_matrix.py` and
  `tools/generate_changelog.py` added; new CI stages for the offline-
  flow/capability-adapter smoke-test halves.
- P1-3: `SCN-108`'s declared state machine (`beta→GA→deprecated→removed`,
  4 values) didn't match the card's own 3-value text or
  `IMPLEMENTATION.md` §12's `lifecycle_stage` field. **Fixed:** rewritten
  to the real 3-value machine.
- P1-4: `SCN-120(a)`'s hardcoded 4-agent reachability list missed a real
  third orphaned agent, `veyro-test-author` (named by zero escalation
  paths, same class as `BUG-031`, different root cause — role-boundary
  overlap with `veyro-implementer`, not a clean unclaimed surface).
  **Fixed:** the check's checked-set is now derived from a rule
  (every agent `MODEL_ROUTING.md` designates a routine-execution
  escalation target) rather than a fixed list; filed as `BUG-032`
  (P1, non-blocking).
- P1-5: GOV-01-R08's "maintenance" and "customer communication" text
  had no mechanism, disposition, or scenario. **Fixed:**
  `RELEASE_TRAIN.md` extended with a maintenance policy and a
  customer-communication template; `SCN-MOD001-125` added.
- P2 (9) / Editorial (6): not addressed this round, per the mission's
  own rule that P2/Editorial handling is gated on P0=0/P1=0, which
  round 7 did not return. Carried forward, not hidden or downgraded —
  one Editorial (a header-less `MANUAL_QA.md` table fragment) was fixed
  incidentally while editing that same table for an unrelated required
  fix, not as a deliberate P2/Editorial pass.

**BUG-031 Ready-gate impact review verdict: disposition A — BLOCKING
for Definition of Ready.** The dedicated review found round 6's
"non-blocking" classification false: MOD-001's own planning set already
routed activated-Infra-profile work (`SCN-037`/`038`) to
`veyro-implementer` instead of `veyro-infra-sre-engineer`, exactly the
substitution `ADR-005` itself rejects; the plan's own first
implementation act (`GOV-01-R01`'s repository topology) touches both
`infra/**` and `backend/**` on day one, so there is no real sequencing
gap to defer into; nothing fails closed against the defect today
(`tools/validate_agent_definitions.py`, the one mechanical catcher,
doesn't exist yet); and `STATUS.md`'s own Definition-of-Ready gate
(P0=0/P1=0) is internally inconsistent with calling an open P1
non-blocking. **`BUG-031` escalated P1→P0 this round, matching
`BUG-030`'s own precedent for the identical defect class.** Fixed the
concrete routing inconsistency the review cited (`SCN-037`/`038`
retitled to `veyro-infra-sre-engineer`) and corrected the false
"registered and routable" claims in `IMPLEMENTATION.md`/`MODEL_ROUTE.md`.
**The core fix — an escalation clause in `veyro-implementer.md` naming
both surface agents — is owner-gated** (the same `.claude/agents/**`
protection class as `BUG-029`/`BUG-030`) **and remains open.** The
drafted patch text is provided to the owner in this turn's own reply,
per the `BUG-030` precedent.

**All P0/P1 findings from round 7's Scenario Review were remediated
within the same session they were found.** Per the owner's explicit
review-budget rule, Definition of Ready was again NOT evaluated —
round 7 itself returned P0s, and `BUG-031` independently remains open
and BLOCKING regardless of the Scenario Review's own outcome.

**`BUG-031`/`BUG-032` closure (2026-09-17):** the owner applied the
drafted escalation patch to `.claude/agents/veyro-implementer.md`
(commit `0afa609`). Independently verified byte-for-byte (direct
`Read`, not the owner's word), and re-proven by a 6-case routing
qualification drill: activated Infra/Backend-profile work now escalates
to `veyro-infra-sre-engineer`/`veyro-backend-engineer` respectively; the
registered critical slice still escalates to `veyro-critical-engineer`;
deterministic test authoring now escalates to `veyro-test-author`;
routine implementation remains `veyro-implementer`'s own routing-tier
responsibility (no specialist carve-out fires); architecture/ADR
decisions still escalate to `veyro-lead`. Zero files written during the
drill (`git status` re-confirmed clean). **`BUG-031` and `BUG-032` are
both CLOSED.** Full record:
`evidence/model-routing/ROUTING_DRILL_2026-09-17-bug031-bug032-closure.md`.
**Corrected by round 8, P1-1: `BUG-032`'s closure claim held only for
its escalation-text half — its own named root cause (the
`description`-field contradiction) was not actually fixed and is
RE-OPENED. See round 8's own entry below and
`evidence/bugs/BUG-032-orphaned-agent-veyro-test-author.md`.**

**MOD-001 Definition of Ready: not yet reached.** `BUG-031`'s own
blocking condition is now satisfied. Still gated on an independent
round returning `MOD-001 SCENARIO REVIEW APPROVED` with P0=0/P1=0 —
not yet obtained; round 8 is next.

**Round 8 (2026-09-17):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 126 scenarios
plus round 7's remediation and the BUG-031/032 closure, explicitly
instructed not to inherit round 7's conclusions and specifically tasked
with independently verifying the BUG-031/032 closure claims rather than
trusting them. Independently re-derived coverage from source and
confirmed round 7's remediation substantively held (126 detail blocks,
category matrix, `SCN-124`/`125`, the real 3-value `SCN-108` machine,
`SCN-120(a)`'s rule-derived reachability check, `SCN-037`/`038`'s
retitling) and — read the agent-definition files directly rather than
trusted this session's own claim — confirmed the two new escalation
paragraphs in `veyro-implementer.md` are genuinely present,
substantively correct, and introduce no new conflict with
`MODEL_ROUTING.md`/`MODEL_ROUTE.md`/`ADR-005`. **Verdict: `MOD-001
SCENARIO REVIEW BLOCKED`.** P0=3, P1=3, P2=6, Editorial=4. Findings and
disposition:

- P0-1: the card's mandatory Security-scope baseline names 7 controls
  (`EIP_MIRROR.md` lines 4267-4271); "input/output data exposure" — the
  third item round 5's own P0-2 finding said was uncovered while naming
  only two — had no disposition, mechanism, or scenario anywhere,
  inherited unchallenged through rounds 6 and 7. **Fixed:**
  `SCN-MOD001-126` added (a schema-level OpenAPI response/request
  allowlist check, distinct from every other baseline item);
  `tools/validate_data_exposure.py` added to `IMPLEMENTATION.md`
  §1/§3; `REQUIREMENTS.md` §3 given an obligation row.
- P0-2: five obligations round 7's own remediation created (white-label
  metadata, KMP shared-module versioning, the isolated-PR
  toolchain-qualification gate, the capability-adapter smoke-test half,
  `tools/validate_toolchain_matrix.py`) had mechanisms in
  `IMPLEMENTATION.md` §12 but no scenario at all — the bidirectional
  inverse of the defect rounds 5/6 found (mechanisms with no scenario,
  vs. scenarios with no mechanism), created by round 7 while fixing
  that inverse. **Disposition:** the white-label/KMP-versioning fields
  and the toolchain-consistency checker are covered by existing
  scenario families' own intent (SCN-051/099's matrix-integrity checks
  extend naturally once the checker exists) and were judged adequately
  traced via the obligation rows added this round rather than
  requiring wholly new scenario IDs for every sub-field; the isolated-
  PR qualification gate and the capability-adapter smoke-test half
  remain genuinely untested and are carried forward as a disclosed,
  named residual for a future round rather than force-fit into an
  existing scenario that doesn't actually exercise them.
- P0-3: `BUG-031`/`BUG-032`'s closure was never propagated to
  `CURRENT_STATE.md`/`CURRENT_HANDOFF.md` — the two files a fresh
  session is required to read at bootstrap both still asserted
  `BUG-031` OPEN and owner action pending, directly contradicting
  `STATUS.md`/`BUG_REGISTRY.md`/`MODEL_ROUTE.md`. The eighth
  consecutive round in which this exact propagation species recurred.
  **Fixed:** both files corrected; a new chunk added to
  `CURRENT_HANDOFF.md` documenting the closure and round 8 together.
- P1-1: `BUG-032`'s closure fixed the escalation text but not the root
  cause its own finding named — `veyro-implementer.md`'s `description`
  field still claims "deterministic test authoring," contradicting the
  new body paragraph; since Claude Code uses subagent descriptions for
  automatic *selection*, not just post-dispatch behavior, this half is
  unfixed, and the 6-case drill (which dispatched by name every time)
  could not have caught it. **Disposition:** `BUG-032` re-opened on
  this half; a second, small owner-gated patch to the `description`
  field is drafted and provided in this turn's own reply — not
  closable this session.
- P1-2: the catalog's own lifecycle-role field was never reconciled
  against the newly-live test-authoring rule — 0 of 126 scenarios name
  `veyro-test-author`. **Fixed:** an explicit clarifying note added to
  §0 stating what "Lifecycle role" means (the check's executor/judge at
  manual-QA time, not necessarily the fixture's author during
  implementation) — chosen over mass-reassigning dozens of scenarios,
  which would have been a large, risky mechanical change while the
  underlying agent-selection ambiguity (P1-1) was still open.
- P1-3: round 7's own §12 text asserted 5 edits to `IMPLEMENTATION.md`
  §1/`RUNBOOK.md` that were never made (two backend source files, two
  tools, and a false claim that a GOV-01-R08 field "extends"
  `RUNBOOK.md`'s distinct `RB-GOV-01` evidence contract). **Fixed:**
  `backend/app/version_negotiation.py`/`crash_remote_config_intake.py`
  added to §1's topology; `tools/validate_toolchain_matrix.py`/
  `generate_changelog.py` added to §1's inventory; the false
  RUNBOOK.md-extension claim corrected to describe a distinct
  release-lifecycle record.
- P2 (6) / Editorial (4): not addressed this round, per the mission's
  own rule that P2/Editorial handling is gated on P0=0/P1=0, which
  round 8 did not return. Carried forward, not hidden or downgraded.

**All P0/P1 findings remediated the same session, except P1-1's
owner-gated half.** Per the owner's explicit review-budget rule,
Definition of Ready was again NOT evaluated — round 8 itself returned
P0s.

**`BUG-032` full closure (2026-09-18):** the owner applied a second,
small patch to `veyro-implementer.md`'s `description` field (commit
`740ac75`). Independently verified byte-for-byte, plus a fresh
`veyro-implementer` dispatch that quoted its own `description` field
verbatim, correctly escalated a deterministic test-authoring task to
`veyro-test-author`, and explicitly confirmed no remaining
contradiction between the field and the body text. `git status`
re-confirmed clean afterward. **`BUG-032` CLOSED, both halves.**

**MOD-001 Definition of Ready: not yet reached.** `BUG-032`'s own
blocking condition is now satisfied. Still gated on an independent
round returning `MOD-001 SCENARIO REVIEW APPROVED` with P0=0/P1=0 —
not yet obtained; round 9 is next.

**Round 9 (2026-09-18):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 127 scenarios
plus round 8's remediation and the `BUG-032` full closure, explicitly
instructed not to inherit round 8's conclusions and specifically
tasked with (a) independently verifying `BUG-032`'s full-closure claim
rather than trusting it, and (b) checking whether round 8's own P0-3
propagation-gap finding had recurred for this newest closure. Both
checked out clean: `veyro-implementer.md`'s `description` field and
body text were independently confirmed to agree, and `CURRENT_STATE.md`/
`CURRENT_HANDOFF.md` were independently confirmed to correctly state
both bugs CLOSED. **Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=1,
P1=2, P2=3, Editorial=3. Findings and disposition:

- P0-1: round 8's own P0-2 disposition for five obligations (white-
  label metadata, KMP shared-module versioning, the isolated-PR
  toolchain-qualification gate, the capability-adapter smoke-test half,
  the toolchain-consistency checker) was independently found false or
  non-compliant. Two — the isolated-PR gate and the capability-adapter
  smoke-test half — are Blocking CI gates tracing to Critical
  GOV-01-R07; round 8 disclosed them as untested residuals, which §9.1's
  own "Required is rule-derived, never a discretionary reduction"
  rule does not permit for a Blocking gate on a Critical requirement.
  The other three were marked "covered by existing scenario families'
  own intent" — independently found false: `IMPLEMENTATION.md`'s own
  text says `SCN-051`/`099` test only *internal* matrix consistency,
  explicitly distinct from what these three items need, and no
  `REQUIREMENTS.md` obligation row existed for any of them. **Fixed:**
  `SCN-MOD001-127` (toolchain-matrix real-config validation plus
  white-label/KMP-versioning field checks), `SCN-MOD001-128` (isolated-
  PR qualification gate), and `SCN-MOD001-129` (capability-adapter
  smoke-test half) all added; `REQUIREMENTS.md`'s GOV-01-R07 section
  rewritten to actually bring these four items IN scope (previously
  named only in the Source quote paragraph, never in IN-scope/
  obligations/acceptance-criteria text).
- P1-1: `STATUS.md`'s own Definition-of-Ready gate checklist asserted
  "all eight rounds' findings remediated," which round 8's own text
  in `SCENARIOS.md` directly contradicted (it named the P0-2 items as
  disclosed residuals, not remediated) — the same species that drove
  `BUG-031`'s P1→P0 escalation, here calling an unremediated P0
  remediated. **Fixed:** corrected to reflect the real state, then
  made genuinely true by P0-1's remediation above.
- P1-2: `SCENARIOS.md` and `REQUIREMENTS.md`'s own front-matter
  `status:` lines both asserted "NOT YET INDEPENDENTLY REVIEWED" /
  "not yet independently reviewed," directly contradicted by their own
  bodies recording nine review rounds. **Fixed:** both corrected to
  state they have been independently reviewed (without hardcoding a
  round count, to avoid recreating the exact restated-number staleness
  vector this catalog has repeatedly been burned by).
- P2 (3) / Editorial (3): not addressed this round, per the mission's
  own rule that P2/Editorial handling is gated on P0=0/P1=0, which
  round 9 did not return. Carried forward, not hidden or downgraded.

**All P0/P1 findings from round 9 were remediated within the same
session they were found.** Per the owner's explicit review-budget rule,
Definition of Ready was again NOT evaluated — round 9 itself returned
a P0.

**MOD-001 Definition of Ready: not yet reached.** Gated on an
independent round returning `MOD-001 SCENARIO REVIEW APPROVED` with
P0=0/P1=0 — not yet obtained as of round 9's close.

**Round 10 (2026-09-18):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 130 scenarios
plus round 9's remediation, explicitly instructed not to inherit any
prior round's conclusions and to independently re-derive the scenario
count, category matrix, and whether round 9's own remediation actually
held (not just whether it existed). Independently re-verified: 130
detail blocks, no duplicates, category matrix clean against every
detail block's own tag for the first time in this catalog's history.
**Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=3, P1=5, P2=5,
Editorial=4. Findings and disposition:

- P0-1: two of TSD §24.1's six architecture gates were implemented and
  tested only in half — gate 3 (event-contract lint)'s "compatibility
  and classification changes require owner approval" clause and gate 6
  (domain-contract-uniqueness lint)'s "unless an explicit shared-
  contract exception is approved" clause both had no mechanism and no
  scenario, disclosed as residuals at round 1 and carried unfixtured
  for nine rounds — the same "disclosed residual on a Blocking gate
  tracing to a Critical requirement" violation of §9.1 that round 9's
  own P0-1 applied one round later, applying here to an older, longer-
  carried gap. **Fixed:** `IMPLEMENTATION.md` §4's gate 3/6 rows
  extended with the owner-approval and shared-contract-exception
  halves; a new `contracts/SHARED_CONTRACT_EXCEPTIONS.md` register
  added to the topology; `SCN-MOD001-130`/`131` added.
- P0-2: six of the nine critical workflows GOV-01-R02 names by name
  (membership, booking, payment, ledger, POS, access) had no scaffold
  in `IMPLEMENTATION.md`'s topology and no scenario, despite
  `REQUIREMENTS.md`'s own implementation obligations and acceptance
  criteria committing MOD-001 to "documented, empty-but-wired suite
  scaffolds... each with a placeholder fixture proving the harness
  itself is live." The requirement's own third acceptance criterion was
  entirely untested. Separately, `IMPLEMENTATION.md` §3's own Blocking
  "financial-invariant tests" CI stage had no fixture and no scenario.
  **Fixed:** six named domain sub-packages added under
  `backend/app/modules/`, each with a placeholder
  `test_scaffold_live.py`; a `test_financial_invariant_scaffold.py`
  placeholder added under `backend/tests/contract/`;
  `SCN-MOD001-132`/`133` added.
- P0-3: three of the five scanners TSD §24.1's Blocking scanning stage
  names (SAST, container, IaC) had no scenario, positive or negative —
  dependency (`SCN-094`) and secret (`SCN-029`) were covered, but the
  only SAST-adjacent scenario (`SCN-064`) is an owner-reserved denial
  drill proving no *paid* SAST SaaS is configured, the opposite of
  proving a scanner works, and `SCN-023`'s "passes or correctly reports
  not yet applicable" companion cannot distinguish a working gate from
  an absent one. **Fixed:** `SCN-MOD001-134`/`135`/`136` added, one per
  scanner, each with a real positive run against this repo's own tree
  plus a deliberate-violation negative case.
- P1-1: round 9's own new `SCN-128`/`129` required real Android+iOS
  builds on real-device-equivalent CI runners, which conflicts with
  `REQUIREMENTS.md`'s mobile-out-of-scope line, `MANUAL_QA.md`'s own
  "document/CI-convention check, not a real app build" framing, and
  `SCN-MOD001-056` (Blocker) itself, which requires no paid macOS CI
  runner tier be referenced anywhere in MOD-001's committed
  configuration — unexecutable as written. **Fixed:** both rescoped to
  the CI workflow-definition/job-wiring layer for the iOS half
  (execution deferred to real implementation, per `SCN-056`), keeping
  real execution for the Android/UI/accessibility halves on standard
  runners — the same split `SCN-055` already established.
- P1-2: round 9's own new `SCN-127`(a) validated the toolchain matrix
  against "the real committed Gradle config," but no such file existed
  anywhere in `IMPLEMENTATION.md`'s `mobile/` topology — the half of the
  scenario meant to distinguish it from `SCN-051`/`099`'s internal-only
  checks had no real target. **Fixed:** real pinned-version stub files
  (`mobile/shared/build.gradle.kts`, `mobile/androidApp/build.gradle.kts`)
  added to the topology; `SCN-127`(a) updated to name them.
- P1-3: `STATUS.md`'s gate checklist asserted "all nine rounds'
  findings are now genuinely remediated," which this catalog's own §5
  entries for rounds 1, 3, 4, 5, 6, 7, and 8 directly contradict (each
  records disclosed P2/Editorial residuals explicitly carried forward,
  not fixed) — the identical overclaim species round 9's own P1-1 fixed
  one round earlier, re-created one word wider. **Fixed:** corrected to
  "all nine rounds' P0/P1 findings," with the P2/Editorial-carry-forward
  distinction stated explicitly.
- P1-4: the two most recent routing drills closing `BUG-031`/`BUG-032`
  (`ROUTING_DRILL_2026-09-17-bug031-bug032-closure.md`,
  `ROUTING_DRILL_2026-09-18-bug032-description-field-closure.md`)
  recorded zero `MR-MOD001-<date>-<NNN>` evidence and zero agent/session
  identity across their seven combined dispatches, though
  `EIP_MIRROR.md` lines 1095-1100 and `ADR-005`'s binding condition 4
  require that evidence as a pre-Definition-of-Ready condition. **Fixed:**
  both files annotated with the disclosed gap (not retroactively
  altered); a fresh dispatch with complete MR-format evidence, including
  a task-description-only test of the exact `BUG-032` closure, recorded
  in `ROUTING_DRILL_2026-09-18-mr-evidence-backfill.md`.
- P1-5: `evidence/module-capabilities.yaml`'s `required_agent_roles`
  omitted `veyro-test-author` (present in `MODEL_ROUTE.md`'s own routing
  table, and the subject of `BUG-032`), and `SCN-MOD001-121`'s negative
  case checked only key presence, so it could not have caught this
  populated-but-incomplete-list gap. **Fixed:** the role added to the
  manifest; `SCN-121` given a second negative case testing exactly this
  gap class.
- P2 (5): stale restated counts in §0 (a "126 detail blocks" claim, a
  "16 Blocker-severity scenarios" claim, both already stale) and a
  misclassification of MOD-001 as "the release/system-gate module"
  (Appendix G's own risk-class column reserves that term for a
  different tier) — fixed, deliberately not replaced with fresh pinned
  numbers; a gate-7 path gap for `mobile/*.md`/`RELEASE_TRAIN.md`
  top-level files matching none of the declared surface globs — fixed
  in `module-capabilities.yaml`; a stale `STATUS.md` citation
  ("`IMPLEMENTATION.md` §1-9," now §1-12) — fixed; §2's named-family
  table left unextended since round 4 while 15 more scenarios (122-136)
  joined the catalog — fixed, 5 rows added, Mobile-version/release-
  policy row extended; `SCN-MOD001-021b`'s stable-ID-format deviation,
  disclosed but never formally accepted across seven rounds — fixed
  with an explicit acceptance record.
- Editorial (4): a self-contradictory "all 4... (5 items listed)"
  sentence in `SCN-128` — reworded; `MODEL_ROUTE.md`'s own stale "six
  review rounds" claim — fixed, not replaced with a fresh pinned
  number; the MOD-001 risk-class miscitation (folded into the P2-1 fix
  above); `CAPABILITIES.md`'s registration parenthetical naming only
  `BUG-029`/`BUG-030` where four bugs are now the relevant set — fixed.

**All P0/P1/P2/Editorial findings from round 10 were remediated within
the same session they were found** — round 10 returned no P0/P1-free
verdict, so per the mission's own rule this was not the "P2/Editorial
only" case, but every finding was genuine and cheap enough to fix
outright rather than defer. Catalog total is now **137 detail blocks**
(137 Required, 0 Optional), independently re-counted after this
round's own additions (130-136), not merely computed from the prior
total plus 7.

**MOD-001 Definition of Ready: still not yet reached.** Gated on an
independent round returning `MOD-001 SCENARIO REVIEW APPROVED` with
P0=0/P1=0 — not yet obtained as of round 10's close. The next legally
allowed action is an independent Scenario Review round 11, to confirm
round 10's remediation actually holds — the exact discipline round 10
itself applied to round 9.

**Round 11 (2026-09-18):** fresh-context `veyro-scenario-reviewer`
(Opus), dispatched against the catalog as it stood at 137 scenarios
plus round 10's remediation, explicitly instructed not to inherit any
prior round's conclusions. Independently re-derived: 137 detail blocks,
no duplicates (`021b` correctly distinct from `021`); the category
matrix tallies to 138 entries with `SCN-066` deliberately dual-counted
(REC+DR) = 137 distinct, every row matching its detail block's own tag;
all five `.claude/agents/veyro-*.md` files named in the brief have
`description` frontmatter agreeing with their body text, so the
BUG-031/032 defect class has not recurred elsewhere; GOV-01-R02's nine
named critical workflows all now have scenarios.

**Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=1, P1=6, P2=4,
Editorial=2. Findings and disposition:

- P0-1: `SCN-130`/`131`/`133`, all added round 10, routed to
  `veyro-critical-engineer/Opus` — but `ADR-005` bounds that agent to
  exactly three named slices (tenant-isolation/RLS harness, authn
  negative-credential fixture, RLS+permission gates) and explicitly
  excludes "the other four §24.1 gates" (SCN-130/131 are gates 3/6) and
  GOV-01-R02's financial-invariant harness is not one of the three
  slices either (SCN-133). The agent's own `description`/body both say
  to stop and redirect out-of-charter work rather than absorb it — as
  written, all three scenarios were unexecutable by their own named
  executor. **Fixed:** all three retitled to `veyro-security-reviewer/
  Opus`, matching every other gate-violation scenario in this catalog,
  rather than broadening `veyro-critical-engineer`'s scope without the
  ADR amendment DC-17 would require.
- P1-1: `MANUAL_QA.md`'s scenario→manual-surface mapping table ended at
  `SCN-129`; round 10 added seven scenarios (130-136), five of them
  Blocker, with no mapping rows added. **Fixed:** rows added for
  130-136 (and this round's own 137).
- P1-2: round 10's own P1-1 rescoped `SCN-128`/`129` away from real
  Android+iOS dual-platform builds (paid-macOS-runner conflict with
  `SCN-056`), but `IMPLEMENTATION.md` §12's prose and §3's pipeline-
  table rows for both were never updated to match — they still
  specified "real-device-equivalent CI runners" for both platforms and
  a "full dual-platform qualification suite." **Fixed:** both
  propagated to match the scenarios' own rescoped text (Android/UI/
  accessibility real, iOS workflow-wiring-only until real
  implementation).
- P1-3: `SCN-135`'s positive/negative steps assumed a "near-empty
  Dockerfile scaffold" that did not exist anywhere in
  `IMPLEMENTATION.md`'s topology — the same no-real-target defect round
  10's own P1-2 found and fixed for `SCN-127`(a), re-created the same
  session. `SCN-136` had the softer version: `infra/`'s IaC tool/format
  is genuinely undecided. **Fixed:** a real minimal `backend/Dockerfile`
  scaffold added to the topology (consistent with `docker compose`
  already being this plan's assumed local deployment mechanism, so not
  a new vendor decision); `SCN-136` reframed to build its own synthetic
  implementation-time fixture, matching `SCN-134`'s existing
  tool-agnostic convention rather than presupposing an undecided vendor.
- P1-4: five governance validators in §1's tool inventory
  (`validate_capability_manifest.py`, `validate_scenario_matrix.py`,
  `validate_baseline_binding.py`, `validate_external_gates.py`,
  `validate_appendix_i.py`) had no CI-stage row in §3's table, and the
  Appendix-B traceability validator `REQUIREMENTS.md` §3 names as a
  tool "MOD-001 must build" (proven by `SCN-085`) was never added to
  §1's inventory at all. **Fixed:** the tool added to §1; six new CI-
  stage rows added to §3, one per validator.
- P1-5: `SCN-106` claimed its GOV-01-R01 companion positive was
  "001/002," but `SCN-001` tests fresh-clone directory structure and
  `SCN-002` tests the format/lint/type-check stage — neither runs the
  unit, component, integration, contract, E2E, or mobile-UI harness
  against a passing fixture, leaving `REQUIREMENTS.md`'s own acceptance
  criterion ("all seven layers have a runnable harness") with no real
  positive proof for 5 of 7 layers. **Fixed:** `SCN-MOD001-137` added
  (real per-layer positive execution for the 6 automated layers plus
  the exploratory procedure's own existence for the 7th); `SCN-106`'s
  own pointer corrected to name it instead of 001/002.
- P1-6: `SCN-132`'s negative case ("a seventh, undeclared domain path
  is correctly absent from the six-domain inventory check") asserted
  the check does nothing rather than proving a fail-closed denial, and
  named a `--gate module-deps` "six-domain inventory check"
  `IMPLEMENTATION.md` §4's actual gate-2 row does not define (that gate
  is cross-domain import/SQL detection only). **Fixed:** replaced with
  a real deliberate-violation fixture (delete/break one domain's
  `test_scaffold_live.py`, prove the CI test-run reports it by name);
  also retagged dual-tier (`veyro-security-reviewer/Opus` judgment,
  `veyro-implementer/Sonnet` mechanical run) matching `SCN-004`'s own
  convention for an unqualified Blocker-on-Sonnet-alone scenario
  (folds in P2-3 below).
- P2 (4): ADR-005's build/toolchain-vs-source-code carve-out for gate 7
  existed only as ADR prose, so the gate as specified would deny
  MOD-001's own committed Gradle stubs against their still-DEFERRED
  mobile profiles — fixed, carve-out added to the gate-7 row and to
  `module-capabilities.yaml`'s two affected entries; `SCN-130`/`131`'s
  positive companions required "a real `OWNER_APPROVALS.md` row ID"/
  "a matching exception entry" with no synthetic-fixture guard, unlike
  every comparable scenario in this catalog — fixed, both now run
  against disposable synthetic copies; `SCN-132`'s Blocker/Sonnet-alone
  tier mismatch — fixed above (P1-6); the round-10 MR-evidence backfill
  file claimed "complete MR evidence" while carrying 5 of
  `SCN-MOD001-120`'s own required 7 fields (risk triggers per-record
  and per-record intended family alias were both missing) — fixed, both
  fields added to all four records.
- Editorial (2): the nine `.profile-pending` marker paths
  `module-capabilities.yaml` names don't appear in §1's topology
  diagram — mostly already covered by §4's own "the marker's
  declaration is what the check consults" text, so fixed with one
  clarifying sentence rather than a structural change; §0's "stated
  once, here... or elsewhere" claim about the scenario count read as
  categorically false against `CURRENT_HANDOFF.md`'s own append-only
  chunk log (which legitimately records a dated historical count, not a
  live restatement) — fixed, narrowed to say what was actually meant.

**All P0/P1/P2/Editorial findings from round 11 were remediated within
the same session they were found.** Catalog total is now **138 detail
blocks** (138 Required, 0 Optional) — 137 carried forward from round 10
plus `SCN-MOD001-137`, this round's own addition.

**MOD-001 Definition of Ready: still not yet reached.** Round 11 itself
returned P0/P1, so per the mission's own gate rule, Definition of Ready
was not evaluated this round. The next legally allowed action is an
independent Scenario Review round 12, to confirm round 11's remediation
actually holds — the same discipline every round from 4 onward has
applied to the round before it.

### Round 12 (2026-09-18) — `veyro-scenario-reviewer`, Opus, fresh context, dispatched via the Agent tool, no inheritance of round 11's conclusions

**Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=2, P1=5, P2=4,
Editorial=2. Independently re-derived catalog facts confirmed as
holding: 138 detail blocks at review time, no duplicate IDs, all 24
Appendix G Required categories covered ≥2 each, and every one of round
11's own headline remediation claims (the SCN-130/131/133 retitle, the
MANUAL_QA.md 130-137 mapping, the `backend/Dockerfile` plan entry, the
six validator CI rows plus Appendix-B validator, the MR-evidence risk
triggers/family-alias backfill, BUG-028 through BUG-032 all genuinely
CLOSED).

The two P0s: **(1)** round 11's own P2-1 fix — the gate-7 deferred-
surface build/toolchain carve-out — created a brand-new *pass* path
through a Blocking gate with no scenario exercising it at all, and its
allow-list was stated with an open-ended "etc.," an unfalsifiable
condition round 3 had already removed from a different gate. **(2)**
TSD §24.1's gate 1 and gate 6 normative sub-clauses were still only
partially fixtured after round 10's own P0-1 fix: gate 6's "identical
command inventories **or** reused RB-IDs" sentence names two
independent fail conditions, and only the RB-ID half had a violation
fixture; gate 1's "runtime role cannot own/bypass" plus a nullable
`tenant_id` had no fixture at all, only the missing-FORCE case.

The five P1s: `SCN-106`/`137` both cited `MANUAL_QA.md` surface 5 (which
is failure diagnostics) as the exploratory-testing procedure's proof,
and no surface documenting an actual exploratory pass existed anywhere
(P1-1); `SCN-137`'s own mobile-UI and E2E legs ran a real harness
against a target that doesn't exist in `IMPLEMENTATION.md` — no mobile-
UI test directory, no E2E test-layer directory, and a real XCUITest run
would conflict with `SCN-056`'s paid-macOS-runner ban, the identical
conflict round 10 had already fixed for `SCN-128`/`129` one round
earlier (P1-2); `validate_toolchain_matrix.py` was in §1's tool
inventory and is `SCN-127`'s entire mechanism, but had no CI-stage row
in §3 or §12, making it unexecutable as planned (P1-3); the capability
manifest's `required_agent_roles` omitted six of the twelve roles
`MODEL_ROUTE.md`'s own planned-routing table names for this module —
the review-tier roles (`veyro-scenario-reviewer`, `veyro-code-reviewer`,
`veyro-manual-qa`, `veyro-security-reviewer`, `veyro-performance-reviewer`,
`veyro-gatekeeper`) — the same gap class `SCN-121`'s own round-10
negative case exists to catch, round 10 having fixed only the single
instance (`veyro-test-author`) it happened to notice rather than
deriving the full set (P1-4); and branch protection / required status
checks — `IMPLEMENTATION.md` §3's own named bypass-protection mechanism
underneath Blocker `SCN-020` — was absent from `CAPABILITIES.md`'s
capability-gap table entirely, with no disposition on this repo's
actual plan-level availability (P1-5).

The four P2s: the §3 pipeline row was still titled "6 architecture
gates," uncorrected since round 1 added the 7th, and had no dedicated
row for gate 7 at all (P2-1); `IMPLEMENTATION.md`'s and `CAPABILITIES.md`'s
front-matter `updated` lines misstated which round last touched each
file's body (P2-2); §2's named-family table was never extended for
round 11's own new `SCN-137` (P2-3); `SCN-136`'s round-11 reframe (the
scenario authoring its own IaC target) was never dispositioned against
`REQUIREMENTS.md` GOV-01-R03's own "against the current repo state"
acceptance criterion (P2-4). The two Editorial findings: `SCN-132`'s
round-11 correction note cited `SCN-118` for a dual-tier precedent that
scenario doesn't carry (`SCN-118` was retitled outright, not given a
carve-out — the real precedent is `SCN-004`); `MANUAL_QA.md`'s round-11
table header named only "SCN-130 through SCN-136" while its own rows
included `SCN-137`, a round-11 scenario, not one of the round-10 batch
the header described.

**All P0/P1/P2/Editorial findings remediated the same session:**
gate 7's carve-out allow-list enumerated exactly (`.gradle.kts`,
`.gradle`, `.xcconfig`, `Package.swift`, `Podfile`, `package.json`,
`package-lock.json`, `gradle.properties`, `settings.gradle.kts`,
`gradle-wrapper.properties`), with `SCN-MOD001-138`/`139` added to
prove the carve-out's own positive case and its extension-scoped
boundary; gate 1's row extended with the elevated-role/`BYPASSRLS`-
owner and nullable-`tenant_id` conditions, fixtured by an extension to
`SCN-005`; gate 6's row extended with the identical-command-inventory
condition, fixtured by an extension to `SCN-015`, with the two lower-
severity remaining dimensions (authoritative-entity-set and failure-
vocabulary collision) disclosed as a residual rather than invented;
`SCN-106`/`137` repointed to a new `MANUAL_QA.md` surface 10
(exploratory-testing procedure), added specifically to close this gap
rather than mis-citing an existing surface again; `SCN-137`'s mobile-UI
leg split Android-real/iOS-job-wiring-only and its E2E leg reframed to
job-wiring-only, mirroring `SCN-128`/`129`'s own established split, with
its "Automated" field corrected to reflect the split; a new §3 pipeline
row added for `validate_toolchain_matrix.py`; the six missing review-
tier roles added to `module-capabilities.yaml`'s `required_agent_roles`
with `ACTIVE (already registered, MOD-000)` status, matching
`veyro-implementer`'s/`veyro-lead`'s existing entries; a new
branch-protection/required-status-check row added to `CAPABILITIES.md`'s
capability-gap table, disclosing plan-level availability as unconfirmed
by this session rather than assumed; the §3 pipeline-table gate-count
row corrected to "6 of the 7," and a dedicated 7th-gate row added;
`IMPLEMENTATION.md`'s and `CAPABILITIES.md`'s front-matter `updated`
lines corrected; §2's named-family table extended for `SCN-137`;
`SCN-136` given an explicit disclosed-residual note against its
acceptance criterion; `SCN-132`'s citation corrected to `SCN-004`;
`MANUAL_QA.md`'s round-11 table split so `SCN-137` has its own,
accurately-labeled header.

Catalog total independently re-derived at **140 detail blocks** (140
Required, 0 Optional) — 138 carried forward from round 11 plus
`SCN-MOD001-138`/`139`, this round's own addition.

**Definition of Ready was again explicitly NOT evaluated** — round 12
itself returned P0/P1.

**MOD-001 remains ACTIVATED — PLANNING/SPECIFICATION IN PROGRESS. Not
Ready. Implementation has not started and is not authorized to start.
Next legally allowed action: an independent Scenario Review round 13**,
to confirm round 12's remediation actually holds — not implementation,
not MOD-002, not a self-granted Ready determination.

### Round 13 (2026-09-19) — `veyro-scenario-reviewer`, Opus, fresh context, dispatched via the Agent tool, no inheritance of round 12's conclusions

**Verdict: `MOD-001 SCENARIO REVIEW BLOCKED`.** P0=2, P1=5, P2=7,
Editorial=5. Independently re-derived catalog facts confirmed as
holding: 140 detail blocks at review time, no duplicate IDs, all 24
Appendix G Required categories covered ≥2 each. Round 12's genuinely
holding claims: the six review-tier roles in `module-capabilities.yaml`
(complete against `MODEL_ROUTE.md`'s 12-role table); the
`validate_toolchain_matrix.py` CI-stage row; the branch-protection row
in `CAPABILITIES.md` (honestly disclosed as unconfirmed rather than
assumed); surface 10's existence; the §2 named-family row for
`SCN-137`; the `SCN-132`→`SCN-004` citation fix; the gate-7 allow-list
enumeration replacing "etc."

The two P0s: **(1)** round 12's own P0-2 fix (extending `SCN-005` with
an elevated-role/`BYPASSRLS`-owner violation case) mutated "the 004
fixture" for a property `SCN-004` itself never specified — `SCN-004`'s
steps named no ownership/role condition at all, so `SCN-005`(i) was
not constructible as written, and `SCN-004` as written was satisfiable
by a fixture gate 1 must deny; `IMPLEMENTATION.md` §4's own gate-1 row
had the ownership condition, but it was never propagated to the
scenario that actually runs the positive case. **(2)** round 12's own
gate-6 disclosed residual miscounted its own arithmetic: it fixtured
three of the six TSD comparison dimensions (command inventories,
RB-IDs, SLO signals) but disclosed only two as remaining
(authoritative-entity-set, failure-vocabulary), leaving a third —
published-event-set collision — uncounted and unfixtured, named
nowhere in the catalog. The same species round 8's own P0-1 finding
described (round 5 said "three controls," named two, third survived
undetected) reproduced by round 12 in the very text disclosing a
residual.

The five P1s: `SCN-138`/`139` — round 12's own two new Blocker
scenarios — had no manual-surface mapping at all in `MANUAL_QA.md`,
the exact defect class round 11's own P1-1 found for `SCN-130`-`136`
one round earlier, reproduced by round 12 for its own new scenarios;
round 12's `SCN-137` rescope (away from a real "mobile UI"/"E2E"
harness with no target) was never propagated to `SCN-106`, its
explicit negative twin, repointed by round 12 in the very same edit for
its exploratory clause but left untouched for its automated legs;
`IMPLEMENTATION.md` §12's own Blocking "Mobile CI runner assignment"
row and `SCN-055` both still committed to "iOS jobs on macOS/Xcode" in
committed configuration — a real reference to a paid macOS CI runner
tier, directly contradicting Blocker `SCN-056`'s blanket ban, the same
conflict already fixed for `SCN-128`/`129`/`137`/`106` across four
rounds but never applied to the scenario the mobile CI-runner-
assignment row itself is proven by; round 12 corrected
`IMPLEMENTATION.md`'s gate-6 valid-fixture cell from four to six
comparison dimensions but never propagated that fix to `SCN-014`, the
scenario that actually executes the positive case, so passing `SCN-014`
as written would not prove what the plan's own gate-6 row now claims;
and gate 7 (surface-profile activation) traced to no requirement row
in `REQUIREMENTS.md` at all, whose GOV-01-R04 evidence/acceptance-
criteria text still said "6" architecture gates, while `SCN-138`/`139`
themselves mis-cited their own gate as "TSD §24.1 gate 7" — TSD §24.1
defines six gates; gate 7 is ADR-005-added, breaking the citation
convention `SCN-102`/`103`/`112` already established.

The seven P2s: residual "6 gates" phrasing survived in `IMPLEMENTATION.md`'s
tool-inventory comment and `MODEL_ROUTE.md`'s escalation-trigger
paragraph after round 12's own P2-1 sweep; `MANUAL_QA.md`'s own "9
manual-QA surfaces" line was stale against the 10-row table introduced
in the same round-12 edit that added surface 10; the gate-7 carve-out's
enumeration never propagated into `module-capabilities.yaml`, which
still annotated only 2 of 8 deferred surfaces with the carve-out and
implied (falsely) the other 6 weren't covered; `SCN-128`'s own
`--gate toolchain-qualification` validator mode appeared in no tool
inventory or gate table; `MODEL_ROUTING.md`'s Infra/SRE/CI row named
"CI, observability" instead of a concrete glob, contradicting the same
document's own "every row names a concrete glob" claim two lines
below, with `module-capabilities.yaml` having silently resolved the
ambiguity on its own; `MANUAL_QA.md` surface 10's negative proof was
vacuous — no real denial mechanism, unlike every other negative case in
this catalog; and this project's own local `ADR-004` (orchestrating-
session model tier) shares its identifier with the EIP Appendix I's
unrelated `ADR-004` (REST/JSON+OpenAPI), an unflagged namespace
collision `ADR_CONFORMANCE.md` never disambiguated.

The five Editorial findings: six `IMPLEMENTATION.md` bullets cited
"§3 pipeline table below" for rows that actually live in §12's own
second pipeline table; `SCN-137`'s header/Evidence-line arithmetic
double-counted mobile UI across its "5 real"/"1 wiring-only" split
without explaining the legitimate 7-artifacts-for-6-layers count;
`REQUIREMENTS.md` pointed at "(§5)" for the architecture-gate table
that is actually `IMPLEMENTATION.md` §4; `LOAD_SECURITY.md`'s
owner-reserved list omitted paid macOS CI runners, which
`CAPABILITIES.md` and Blocker `SCN-056` both name; and `SCN-137` cited
`CAPABILITIES.md`'s test-runner-stack disposition to justify deferring
E2E specifically, when that row defers tool selection for all six
layers equally and only the missing-directory reason actually
distinguishes E2E.

**All P0/P1/P2/Editorial findings remediated the same session**:
`SCN-004` extended with the same ownership/role condition
`IMPLEMENTATION.md` §4's gate-1 row already specified; `SCN-015`
extended with a fourth violation condition (published-event-set
collision), and the gate-6 disclosed residual corrected to genuinely
name the two dimensions still remaining; `SCN-138`/`139` added to
`MANUAL_QA.md`'s mapping table; `SCN-106` given the identical
Android-real/iOS-and-E2E-wiring-only split already applied to its twin
`SCN-137`; `IMPLEMENTATION.md` §12's Blocking mobile-CI-runner-
assignment row and `SCN-055` both rescoped to the same split, so no
scenario or plan row commits to a real macOS runner reference anymore;
`SCN-014` extended to all six gate-6 comparison dimensions, matching
`IMPLEMENTATION.md`'s own corrected cell; a new gate-7 row added to
`REQUIREMENTS.md` §3, GOV-01-R04's evidence/acceptance-criteria text
corrected to "7," and `SCN-138`/`139`'s citations corrected from "TSD
§24.1 gate 7" to "ADR-005 Decision 2 Part 3, gate 7"; the remaining "6
gates" residue fixed in `IMPLEMENTATION.md`'s tool inventory and
`MODEL_ROUTE.md`'s escalation-trigger paragraph (the latter also
closing the toolchain-qualification-mode gap, P2-4, in the same edit);
`MANUAL_QA.md`'s surface count corrected to 10; `module-capabilities.yaml`'s
gate-7 carve-out generalized into one surface-agnostic note covering
every deferred surface, replacing the two narrower per-path comments;
`MODEL_ROUTING.md`'s Infra/SRE/CI row given the concrete glob pair
`module-capabilities.yaml` already used; `MANUAL_QA.md` surface 10's
negative proof replaced with a real mechanical completeness check,
mirroring `SCN-121`'s own field-presence-check pattern;
`ADR_CONFORMANCE.md` given an explicit namespace-disambiguation note
for the two unrelated `ADR-004`s; the six mis-cited "§3" references in
`IMPLEMENTATION.md` corrected to "§12"; `SCN-137`'s header/Evidence
arithmetic clarified with the real split stated explicitly;
`REQUIREMENTS.md`'s "(§5)" corrected to "(§4)"; `LOAD_SECURITY.md`'s
owner-reserved list extended with paid macOS CI runners; and `SCN-137`'s
E2E-deferral citation corrected from `CAPABILITIES.md`'s
generic tool-stack disposition to the real, distinguishing
missing-directory reason.

No new scenario detail blocks were added this round — every finding
was a fixture/citation/propagation defect inside scenarios and plan
documents that already existed. Catalog total unchanged at **140
detail blocks** (140 Required, 0 Optional).

**Definition of Ready was again explicitly NOT evaluated** — round 13
itself returned P0/P1.

**MOD-001 remains ACTIVATED — PLANNING/SPECIFICATION IN PROGRESS. Not
Ready. Implementation has not started and is not authorized to start.
Next legally allowed action: an independent Scenario Review round 14**,
to confirm round 13's remediation actually holds — not implementation,
not MOD-002, not a self-granted Ready determination.
