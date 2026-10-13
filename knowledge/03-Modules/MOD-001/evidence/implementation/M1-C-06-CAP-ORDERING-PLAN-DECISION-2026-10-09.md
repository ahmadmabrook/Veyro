# M1-C-06 — CAP stage-4/5/7 ordering vs. the compressed plan (2026-10-09)

Status: **DECISION RECORDED. No capability evaluated, qualified, registered, or
approved; no scanner run; no reviewer dispatched; no review claim written or
entitlement created or consumed; no scenario disposed; no code, test, workflow,
registry, requirements/scenario, plan, control-state, or remote change.**
Sole runner operation `dd5e4ce7-4336-4223-ae96-56dc123129d3`, subgoal
`M1-C-06-CAP-ORDERING-PLAN-RECONCILIATION`, execution role
`ARCHITECTURE_CRITICAL`, class `inspection`, `claude-opus-5`. Four governing
baselines re-verified this turn: `backend/.venv/bin/python
knowledge/00-System/verify_baselines.py` → **PASS, 4 of 4 MATCH**.

This is an **architecture/routing decision about ordering**. It is deliberately
**not** the stage-4 independent security judgment it schedules: nothing here
evaluates gitleaks' or Ruff's source, provenance, or rule behaviour, and nothing
here may be cited as satisfying any part of `CAPABILITY_POLICY.md` stage 4, 5,
or 7. It does not revisit tool selection — the route in
`M1-C-06-SCANNER-CAPABILITY-ROUTE-2026-10-09.md` (SHA-256
`8e8edff07dc8cf98856bb643cd24086dff0b68a2889c02d255f4f4a940ee2318`) and the
fail-closed reconciliation in `M1-C-06-R03-SOURCE-BOUNDARY-2026-10-09.md`
(SHA-256 `d95e3580461f3de38f73729a6c8a5822f27bbf03da3cca687311b75351364104`,
§"C06 scanner capability route…" / §"C06 synthetic-only Ruff SAST…") are
settled inputs. Plan read at SHA-256
`dce39cc04fb106110a2b4aa5214bc273508e1a55dcf365a5f535db164cd69c90`.

---

## 1. The ordering problem, stated exactly

Three facts, each read directly from the controlling artefacts this turn:

1. `CAPABILITY_POLICY.md`'s fail-closed rule: a capability not in
   `CAPABILITY_REGISTRY.md` at `APPROVED` is **not usable** on real project
   work; the only permitted touching is a stage 4–5 drill against synthetic
   fixtures. `review_status: APPROVED` additionally requires a populated
   `approved_by` naming an **Opus assurance role** (`veyro-security-reviewer`)
   that independently judged the evidence — a Sonnet `qualified_by` alone is
   `QUALIFIED`, never `APPROVED`.
2. The registry contains **CAP-001 … CAP-008 only**. Neither third-party
   executable the R03 scanner route depends on — `gitleaks` 8.30.1, `ruff`
   0.16.9 in its `S`/flake8-bandit security role — has any row. Next free
   identifiers: **CAP-009**, **CAP-010**, **BUG-057**.
3. The plan's four mandatory independent actions are **M1-C-13** (R04 shared
   code/security), **M1-C-14** (non-R04 module code), **M1-C-18** (GitHub
   approval), **M1-C-20** (gate-3 adjudication). C13 `dependsOn` C02/C03/C04/
   C05/C06/C11; C14 `dependsOn` C07/C08/C09/C06. **Both sit downstream of C06.**

A fourth fact reframes the problem and was not previously recorded: the five
scanner scenarios **SCN-MOD001-029, 094, 134, 135, 136 are assigned to M1-C-05,
not M1-C-06** (`scenarioCoverage.assignedExactlyOnce: true`), and
**M1-C-05's `dependsOn` is `["M1-C-02","M1-C-03","M1-C-04"]` — it does not
reference C06 at all**, while C06's own `independentBoundaryReason` says its
scanner CI hooks "feed M1-C-05." So the real-tree scanner execution that the
APPROVED prerequisite gates is C05's, fed by a C06 capability prerequisite the
plan's dependency graph does not express.

The cycle is therefore: **APPROVED rows → C05/C06 real-tree scanning and CI
evidence → C13/C14 independent assurance → (the only planned place an
independent security judgment exists) → APPROVED rows.**

## 2. Minimum legal sequencing of stages 4, 5 and 7

The policy lists the nine stages "in order," while its model-routing clause
requires the Opus role to **review Sonnet-produced evidence and not re-run the
tests itself** (the reviewer/implementer separation corrected in F5-018). The
minimum sequence satisfying both, with live project precedent, is:

| Step | Who | What | Policy basis |
|---|---|---|---|
| A | Sonnet, inside C06 | Stage-5 mechanics on **synthetic, disposable** fixtures only, per capability: positive, negative, and fail-closed-on-malformed-input; plus provenance/version/`content_hash` material | Stage 5 + fail-closed rule's drill carve-out |
| B | **one** fresh-context Opus `veyro-security-reviewer` | Stage-4 independent evaluation of each third-party executable's own source/instructions/provenance **and** the final `APPROVED`/`REJECTED`/`BLOCKED` decision on step A's evidence | Stage 4 + the `approved_by` requirement |
| C | Sonnet, inside C06 | Stage-7 registration: full rows (incl. `approved_by`/`approved_date`, `lifecycle_status`, `next_review_due`, `rollback_target`) **and** registration in MOD-001's `module-capabilities.yaml` + `CAPABILITIES.md` | Stage 7 |
| D | — | Only now: real-tree/CI scanner execution | Fail-closed rule |

Two constraints on this shape, both load-bearing:

- **Step A legally precedes step B** even though stage 4 precedes stage 5 in the
  list. CAP-008's own 2026-10-04 approval is the precedent and the only one
  needed: the approving Opus review rested on earlier Sonnet drills plus
  read-only verification, and its registry row states "**No new qualification
  drill was required or run for this approval**." Running the drill first is
  what makes a single Opus dispatch sufficient; it is not a stage inversion,
  because the Opus evaluation remains the act that authorises reliance.
- **One dispatch, two determinations.** Step B is one independent action but
  must return a **separate, per-capability verdict** for gitleaks and for Ruff-
  `S`; a single blended verdict is not two approvals, and a rejection of one
  must not carry the other.

**The already-completed Ruff drill is not wasted and must not be re-run.**
`tools/tests/test_sast_ruff_qualification.py` re-hashed this turn to
`43af9b53959f67e1a643ff9867d11a68623f3adc8c3d6f597a20416e42f7f214` — **zero
drift** from the figure recorded in the source-boundary note. It is step-A
material for Ruff-`S`, awaiting step B.

## 3. Project-authored scripts are a different class from Ruff and gitleaks

`CAPABILITY_POLICY.md` §scope governs "every Skill, Rule, Plugin, MCP server,
hook, **or script**," so project-authored scripts are not outside the policy.
But the trigger the policy's model-routing clause quotes from EIP §4.2 for a
**mandatory independent Opus capability-security review** is "any **third-party
executable**, MCP, hook, credential/data access or elevated permission." That
distinction decides the cost:

- **Third-party acquisitions — `gitleaks`, `ruff`:** no exemption of any kind
  (the first-party/harness exemption covers the Claude Code harness and
  Anthropic first-party Skills only). Two capabilities, two determinations,
  **step B is mandatory for both**. Ruff's SAST use is additionally a stage-9
  material scope change on a tool that has no row at all, which is why it is
  cheaper to register one `ruff` row covering lint/format **and** the `S`
  security role than to extend the scope of an unregistered tool.
- **Project-authored source — the dependency-advisory client, the eight
  `tools/validate_*.py` gate scripts:** not a third-party executable, so step B
  is **not** triggered by acquisition provenance, and no new independent action
  is required. Their assurance rides the planned **C14** material-code review,
  whose scope already includes R03. The countervailing precedent is real and is
  named rather than suppressed: **CAP-007 (`bash_guard.py`) is project-authored
  and does hold a row** — because it was a privileged trust-path control (a
  `PreToolUse` hook with authority over tool execution), not gate logic. The
  advisory client sits on the `validate_*` side of that line; its distinguishing
  risk is untrusted external advisory data, which is an input-validation
  obligation for code review (the BUG-055 discipline), not an acquisition
  review. **Pre-reasoned reversal:** if step B's reviewer rules that the
  advisory client needs its own row, that costs one registry row inside the same
  reviewer slot and the same operation — **no sixth action** — and is not to be
  re-litigated.

The prior route decision's "0 CAP rows, policy does not govern project source"
phrasing is therefore **narrowed, not adopted**: the policy does govern it; what
it does not trigger is the third-party-executable review gate.

## 4. No exact-scope independent approval is reusable — tested, not assumed

| Candidate | Verdict |
|---|---|
| CAP-003/CAP-004 first-party/harness exemption | **Not applicable.** Ruff and gitleaks are neither harness-native nor Anthropic first-party. |
| CAP-008's 2026-10-04 Opus approval | **Not reusable.** Scoped to the pinned Colima/Postgres binding; its own row states the approval "does not itself close BUG-038 or promote scenarios." |
| Slice-7 security rounds 3/4's "no new or unregistered capability" findings | **Not reusable.** Statements about *that* change-set, in which ruff/pytest/mypy appeared as lint/type/test tooling. No row, no positive/negative capability tests, no provenance/version/hash fields, no `approved_by` — and the security role was never in scope. |
| `GATE2-R1-F19-PINNED-RUFF-CONFIG-2026-10-06.md` | **Not reusable.** A `line-length` config increment whose own text states "no independent assurance verdict is claimed." |
| `GATE2-R1-D1A-SCANNER-WIRING-2026-10-05.md` | **Not reusable.** "Scanner" there is the architecture-gate SQL lint, not a security scanner; its header disclaims being a review round. |
| Gate-3 round-1 authorisation | **Not reusable and already consumed** (`REVIEW_IN_FLIGHT.md`; C20 `REVIEW_AUTHORITY_HELD`, "no automatic retry or confidence review"). Scope is the gate-3 event contract. |

`REVIEW_IN_FLIGHT.md` reads `current_claim: CLEAR`. Per that file's own text,
`CLEAR` means **no review is in flight, not that a new one is authorised**. No
claim was written this turn.

## 5. Decision — the four planned actions cannot cover the prerequisite

Each was tested against a dependency/order change rather than dismissed:

- **C18** — an external protected-branch merge approval. Not a capability
  judgment in any ordering. No.
- **C20** — gate-3 P1/P2 closure on a protected upstream snapshot, authority
  held, prior authorisation consumed. No.
- **C13** — moving stage 4 into C13 is **circular on C13's own criterion**,
  which requires a coherent R04 gate/CI snapshot *with reviewed CI installation
  and live required-status evidence* — i.e. precisely the artefact that cannot
  exist until the scanners are APPROVED. Splitting C13 to break the cycle *is*
  the additional action, renamed.
- **C14** — closest on scope (R03), but it `dependsOn` C07/C08/C09 as well as
  C06. Pulling it ahead of the approval point means reviewing a change-set in
  which C07/C08/C09 do not yet exist, violating its own "coherent change-set"
  criterion, consuming the single planned non-R04 review on a partial snapshot,
  and leaving the eventual real R01/R02/R03/R05–R08 code with no planned review
  — a second non-R04 review would then be unavoidable. Strictly worse, and
  still an additional action.

**Decision: a genuinely additional mandatory independent action must be
recorded. It is the fifth.** Owner planning text does not waive a higher
governing requirement — and here no override is even involved, because the plan
subordinates itself: its own `authority` field reads "governing criteria, live
evidence and review ledger prevail," and its `caveat` reads "Plan grants no
review authority." Recording the fifth action is that precedence clause
operating as written. Equally, this decision **invents no confidence review**:
exactly one additional action, for a prerequisite the policy makes mandatory,
dispatched only when separately authorised.

## 6. Smallest plan correction, and the exact held dependency

Stated for the orchestrator; **not applied here** (plan/control edits are barred
for this operation).

**Minimal form — no new operation id (preferred).** C06 has been held
throughout as a single coherent operation ("do not increment the 19-operation
remainder"); keeping the determination inside its boundary is the smallest
correction:

1. `mandatoryIndependentReviewActions`: **4 → 5**; append to `reviewActions`:
   `"M1-C-06 qualified capability determination (R03 third-party scanners:
   gitleaks, Ruff-S)"`.
2. `M1-C-05.dependsOn`: `["M1-C-02","M1-C-03","M1-C-04"]` → **`+ "M1-C-06"`**.
   This is the **exact held dependency**, and it fixes a real graph defect
   independent of this decision: C05 owns all five scanner scenarios while
   referencing none of the C06 work they require.
3. `M1-C-06.status` / `nextBoundedFix`: record that C06's exit requires
   `APPROVED` CAP rows for both third-party scanners, produced by step B.
4. Untouched: `totalRemainingPlannedBoundedOperations` (19),
   `criticalPathOperationsWithWIP1` (19), all workstream counts, and
   `scenarioCoverage` (140, `assignedExactlyOnce` — the determination disposes
   no scenario).

**Alternative — a separately addressable `M1-C-06A` operation.** Acceptable,
larger. It then requires: `operations += M1-C-06A` (`workstream W5_R01_R03`,
`independentReview: REVIEW_REQUIRED`, `dependsOn: ["M1-C-06"]`,
`scenariosCovered: []`), totals 19 → 20, W5 remaining 2 → 3, and
`M1-C-05.dependsOn += ["M1-C-06","M1-C-06A"]`. One precise consequence, since it
will otherwise be mis-flagged: W5's baseline is 2, so 3 is exactly +50% and the
`scopeExpansionRule` threshold is **">50%"** — **no `SCOPE_EXPANSION_ALERT`
fires at 3**; a fourth W5 operation would trip it.

## 7. Next legal C06 work, with no real-tree scan

All Sonnet, inside the existing C06 boundary, no new authority, no CI, no
scenario disposition. In dependency order:

1. **gitleaks stage-5 synthetic drill** — planted clearly-fake,
   explicitly-labelled credential-shaped values (`secrets.md` control 1) in
   disposable `tmp_path` files only; positive (detects), negative (clean
   companion), fail-closed (malformed input). **`gitleaks git --staged` must not
   be run again** — that is a real-tree/real-history scan of an unregistered
   capability, the §1.4 defect already disclosed, not a drill.
2. **Provenance capture for both** — each project's **own upstream** `LICENSE`
   and release metadata (the CAP-008 standard; Homebrew `INSTALL_RECEIPT.json`
   does not meet it), versions, and a committed **SHA-256 pin for the gitleaks
   linux release asset** (the local arm64 hash is not a substitute, since CI
   executes the linux asset).
3. **Draft, do not approve, the two rows** — CAP-009 (gitleaks) and CAP-010
   (ruff: lint/format + `S`), at `review_status: QUALIFIED` with `approved_by`
   **empty**, plus their MOD-001 `module-capabilities.yaml` / `CAPABILITIES.md`
   registrations (the R16-5 lesson: a row in no module manifest is evaluated by
   no mechanical gate), plus **BUG-057** filing the two pre-existing
   unregistered-use gaps (gitleaks already executed against project files;
   ruff/pytest/mypy unregistered). The source-boundary note already settled that
   registry/BUG_REGISTRY write authority is **not** an owner gap for the sole
   writer — only the independent judgment is missing — which **corrects** the
   prior route decision's §6 item 5.
4. **Non-scanner C06 R03 work, which this prerequisite does not block at all** —
   SCN-MOD001-033's repo-wide personal-data pattern scan is legal now because it
   is **project-authored**, not a third-party scanner (it still needs its own
   non-vacuity guard, and must not be implemented by reaching for an
   unregistered tool); SCN-068/069 smoke-load fixtures may be authored locally
   with no CI-timing claim. SCN-065 is an Opus-routed owner-reserved denial
   drill, not Sonnet work.

## 8. Residuals and what is explicitly not claimed

No capability was evaluated, qualified, registered, approved, or activated; no
stage 4, 5, 6 or 7 is complete or partially credited for any capability. No
scanner ran against any file. No reviewer was dispatched, no `REVIEW_IN_FLIGHT.md`
claim written, no review entitlement created or consumed, no new review round
inferred from this decision's existence. No code, test, fixture, workflow,
registry, BUG_REGISTRY, requirements/scenario, plan, control-state, branch, PR,
or remote ref was created or modified.

SCN-MOD001-029, 094, 134, 135, 136 and all 13 C06 scenarios remain **NOT
EXECUTED**. No GOV-01-R03 or GOV-01-R04 acceptance criterion is closed. The
layer-3 "runs in CI" authorisation (a disposable same-repository PR for R03) and
the layer-4 default-branch/branch-protection authority remain missing and are
untouched here; this decision changes neither, and an APPROVED row would not
supply them. The `S`-cleanliness of the tree is unknown and unclaimed. Ruff-`S`'s
pattern-based (non-taint) nature stays a disclosed capability limit. The
same-name candidate-check spoof residual (C2/N5) stays open. No paid service,
real secret, real member data, Production action, or branch-protection change is
involved or implied.

C06 remains W5 0/2 completed; the compressed plan remains at 19 operations and 4
recorded independent actions **until the orchestrator applies §6**; MOD-001 exit
remains 0/8; gate-2 F01–F14 remain 14/14 formally CLOSED; the P2-4
approval/assurance hold is preserved unchanged.
