---
doc: ADR-005
status: DECIDED (2026-09-14) — both decisions resolved; no owner approval required (see "Authority" below)
date: 2026-09-14
decided_by: veyro-lead (Opus, claude-opus-5, fresh context), delegated by the MOD-001 orchestrating session per OWN-003 / MODEL_ROUTING.md "Orchestrating-session tier vs. delegated-role tier"
found_by: Independent fresh-context veyro-scenario-reviewer (Opus) review of MOD-001's planning set, findings P0-3 and P1-9
---

# ADR-005: MOD-001 critical-slice routing (`veyro-critical-engineer`) and the §4.3 surface-profile activation threshold

Two architecture questions, both raised as DC-14/DC-09 concerns by the
independent MOD-001 Scenario Review, both resolved here. They are
recorded in one ADR because they share a single root cause: MOD-001's
planning set resolved two *pre-recorded, project-authored blocking
conditions* inside the module's own documents, in the project's own
favour, without an ADR. The conditions were genuinely ambiguous; the
silent resolution is what DC-09/DC-14 forbid.

## Authority — why this ADR does not need owner approval

Both decisions below move MOD-001's plan **toward** conformance with the
governing EIP (§4.1, §4.3, Appendix H, DC-17, DC-21), not away from it.
DC-16's owner-reserved category is a *material product, pricing,
business, architecture, or scope change* measured against the baselines;
correcting an under-scoped plan to match a baseline it already binds to
is not such a change. No paid service, real member data, or Production
action is implicated.

The asymmetry is worth recording, because it is itself an argument: the
**rejected** option in Decision 1 (permanently declaring the EIP-named
`veyro-critical-engineer` role unnecessary and discharging it via a
generic agent) *would* be a material deviation from §4.1's execution
contract, and would therefore have required an ADR **plus** owner
approval. The conforming option needs neither. When one branch of a
decision needs owner sign-off and the other does not, that is usually a
signal about which one is the deviation.

Decision 1 is additionally a material change to `MODEL_ROUTING.md`'s
role→agent mapping, which per DC-17's sub-clause and EIP §4.1
("Routing-policy governance") requires an ADR **and** independent review
**and** a re-run of the routing qualification drill **and** MR-linked
evidence before the next assurance gate. This ADR is the first of those
four; the other three are binding conditions listed below, not optional
follow-ups.

---

# Decision 1 — MOD-001's critical-slice work and the unregistered `veyro-critical-engineer` role

## Context

`knowledge/00-System/MODEL_ROUTING.md`'s role→agent table records, for
EIP §4.1's "Critical implementation slices: authn/authz, tenant
isolation/RLS, payments, ledger, entitlements, booking races, access
decisions, privacy/deletion, fiscalization, crypto/security boundaries"
row: agent **not yet registered**, tier Opus, and this note —

> "Real gap, recorded honestly (not papered over)... Until a dedicated
> `veyro-critical-engineer` agent is authored, this role is covered by
> `veyro-lead` (architecture) directing `veyro-implementer` (Sonnet)
> under explicit Opus supervision, per the EIP's own fallback text...
> MOD-000 itself does not contain any critical implementation slices...
> so this gap has not blocked MOD-000 to date, **but must be closed
> before MOD-001+ touches any critical slice**."

Confirmed by direct check: `.claude/agents/veyro-critical-engineer.md`
does not exist. The nine registered agents are `veyro-lead`,
`veyro-implementer`, `veyro-test-author`, `veyro-scenario-reviewer`,
`veyro-code-reviewer`, `veyro-manual-qa`, `veyro-security-reviewer`,
`veyro-performance-reviewer`, `veyro-gatekeeper`.

MOD-001's `REQUIREMENTS.md` GOV-01-R02 requires building "a
tenant-isolation test harness capable of running a query/action as a
non-privileged runtime role and asserting RLS denial" and "an
authentication negative-credential fixture pattern," and states of that
requirement: "this requirement IS a security control (tenant isolation,
authn). Any weakness here undermines every later module's isolation
guarantees — highest-severity requirement in this module."

`MODEL_ROUTE.md` nonetheless states "no new agent, no routing change, no
ADR needed," and `REQUIREMENTS.md` §0 states "no new agent required" —
neither acknowledging the recorded gap.

## The first question: is this actually a critical slice?

Yes. Recorded as a finding, not deferred.

The available counter-argument is that MOD-001 builds *test
infrastructure*, not a product authn/authz feature — MOD-001 is
Foundation/Control and `STATUS.md` correctly records `SOFTWARE_ONLY:
true` with no domain logic. That argument is real but it points the
wrong way. §4.1's trigger list names "tenant isolation/RLS" and
"authn/authz" as subject matter, not as product-feature categories. And
the leverage is *higher* here than in a domain module, not lower:

- A domain module's broken authz check fails one module's scenarios.
- A broken isolation harness — one that connects as a privileged or
  `BYPASSRLS` role, or asserts denial from an application-layer
  exception rather than a database policy decision — **passes**, and
  then silently manufactures false-clean TEN-001/TEN-002 evidence for
  every later module that plugs into it. It is a false-negative
  generator installed at the foundation, and `INV-GOV-01` makes
  tenant-isolation tests release-blocking on exactly that evidence.

A harness whose failure mode is "every downstream isolation proof is
vacuous" is squarely inside the class §4.1 reserves for Opus. Reading it
out of that class on the grounds that it is infrastructure would be
resolving a pre-recorded blocking condition in the project's own favour
— the DC-14 pattern the reviewer named.

**Slices in scope** (bounded deliberately — not all of MOD-001):
1. The tenant-isolation/RLS test harness and its fixture schema, roles,
   and grants (GOV-01-R02).
2. The authentication negative-credential fixture pattern (GOV-01-R02).
3. Two of TSD §24.1's six architecture gates specifically — the **RLS
   lint** gate and the **permission lint** gate (GOV-01-R04) — because
   those two are the mechanical enforcement of tenant isolation and
   authorization respectively, and inherit the same false-clean failure
   mode.

**Explicitly NOT in scope:** the migration-safety harness (GOV-01-R06 /
MIG, DATA — governed by ordinary risk escalation, not §4.1's critical
list), the other four §24.1 gates, and GOV-01-R01/R03/R05/R07/R08. Those
route normally. Over-broad escalation is its own failure — see
`SCN-MOD000-081` (negative: no over-escalation on routine work).

## Options considered

**(a) Formally invoke the EIP's documented fallback** — `veyro-lead`
directs `veyro-implementer` under explicit Opus supervision — and close
MODEL_ROUTING.md's note with that resolution.

**(b) Require `veyro-critical-engineer` be authored before MOD-001 can
proceed.**

**(c) A bounded synthesis** — register the role, scope the blocking
condition to the named slices, and keep §4.1's Opus-led-pair execution
mode available *inside* the registered role.

## Decision: (c)

1. **`.claude/agents/veyro-critical-engineer.md` must be authored and
   registered (`model: opus`) before MOD-001's Definition of Ready is
   declared.** MODEL_ROUTING.md's "not yet registered" note is closed by
   registration, not by invoking the fallback.

2. **Within the registered role, both §4.1 execution modes remain
   available**: Opus implements the slice directly, or Opus fixes the
   critical design and then directs Sonnet implementation. The MR record
   must state which — per §4.1, verbatim: "Router records whether Opus
   directly implemented or supervised." Independent fresh-context Opus
   review still follows either way; §4.1: "No self-review."

3. **Blocking scope is the three named slices**, not all of MOD-001.
   MOD-001's other seven requirements route per `MODEL_ROUTE.md`'s
   existing table, unchanged.

4. **Registration is required at Definition of Ready, not at first line
   of code.** DoR is the gate this project uses to authorize
   implementation start; splitting the precondition finer than the gate
   that enforces it invites exactly the drift this project has caught
   five times in MOD-000's Phase 10 alone. The cost is one agent
   definition file plus one drill.

## Why (c) and not (a)

**(a) reads "must be closed" as "keep doing what we were already
doing."** The fallback was already in effect and was described in the
same sentence as the note. If invoking it were the intended resolution,
the note would not have said the gap "must be closed" — it would have
said the gap is closed. Treating the sentence as self-satisfying is the
DC-14 move in its purest form: a prior session's honestly-recorded
blocking condition, discharged by relabeling.

**The substantive objection to (a) is evidentiary, not nominal.** The
fallback's operative phrase — "under explicit Opus supervision" — has no
mechanical definition anywhere in this project. No artifact proves
supervision occurred. Under (a), the MR record for the critical-design
step has **no agent to name**, which collides directly with two
requirements the project already treats as binding:

- §4.1: "Router records whether Opus directly implemented or supervised."
  Under (a) there is no router entry to record it in.
- §4.1's no-silent-downgrade rule and DC-17: accepted proof of
  correct-tier execution requires the configured agent/model-family
  alias **plus** runtime evidence (resolved model identity, agent and
  session id). A supervision relationship between two agents neither of
  which is the critical-slice role produces no such record for the
  slice.

`veyro-lead`'s charter is architecture, ADRs, module planning, and
dependency/risk decisions. Stretching it to cover critical *implementation*
is the same category error as (in Decision 2 below) letting
`veyro-implementer` stand in for the named surface engineers. Rejecting
one and accepting the other would be inconsistent, and the inconsistency
would fall on the side of less evidence.

## Why (c) and not (b) as literally worded

(b) says "before MOD-001 can proceed," which would block all eight
requirements on a gap that touches three slices. That is over-broad, and
over-escalation is a real defect in this project's own routing
scenarios, not a safe default.

## The cost objection, addressed honestly

DC-18/DC-19 require reuse-first and creating capability only on a
demonstrated gap. The gap is demonstrated: the EIP names the role, the
role is unregistered, and MOD-001's highest-severity requirement is
inside its trigger list. The marginal cost is one agent definition file
against a proven nine-agent pattern, plus one routing drill — small
against MOD-001's total scope, and it buys a runtime attestation that
cannot otherwise be produced.

## An EIP internal tension, recorded rather than resolved silently

EIP §4.1's role table names `veyro-critical-engineer` as the automatic
execution contract for the critical-slice task class. Appendix H.2's
"Default Project Capability Layout" agent list does **not** name it — it
lists `veyro-lead`, the ten §4.3 surface engineers, and "assurance
agents from §4.1."

Per §3 ("Conflicts are escalated upward; Claude must not choose the
easier interpretation silently") this is recorded. It is resolved by
reasoning rather than escalated, on the ground that H.2's list is
**explicitly partial**: its final entry is an incorporation-by-reference
("assurance agents from §4.1"), so it does not purport to enumerate
every governed agent, and an omission from a partial list cannot
override §4.1's specific, normative execution contract for the task
class. A future session that disagrees with this reading should reopen
it here rather than act on the other reading silently.

## Governance note: agents are not CAP-registry capabilities in this project

`CAPABILITY_POLICY.md`'s scope sentence covers "every Skill, Rule,
Plugin, MCP server, hook, or script" — agents are not named — and
`CAPABILITY_REGISTRY.md` carries no rows for the nine existing agents
(CAP-001..007 are Notion MCP, TestSprite, the `docx` skill, harness
tools, browser tools, the iOS Simulator bridge, and `bash_guard.py`).
Registering `veyro-critical-engineer` therefore does **not** require a
new CAP row; that would be inventing a convention the project does not
use. Agents are governed by `MODEL_ROUTING.md` plus the routing
qualification drill. This asymmetry between DC-21's "agent/rule/skill
profile" language and CAPABILITY_POLICY's agent-free scope is a real
documentation gap, flagged here, not fixed by this ADR.

## Binding conditions on Decision 1

All five required before MOD-001's Definition of Ready:

1. `.claude/agents/veyro-critical-engineer.md` authored, `model: opus`,
   with a charter naming exactly the three slices scoped above and
   stating that it holds no reviewer, Manual-QA, or Gatekeeper authority
   (§4.3's standing constraint on implementation specialists).
2. **Independent fresh-context Opus review of the agent definition**
   (DC-17 sub-clause; EIP §4.1 "Routing-policy governance"). The session
   that authors it may not approve it.
3. **Routing qualification drill re-run** — the `SCN-MOD000-080`
   (positive: escalation to the critical-slice role fires on a
   critical-slice task) and `SCN-MOD000-081` (negative: no
   over-escalation on routine work) pattern, re-executed against the new
   role. **Record the evidence under
   `knowledge/03-Modules/MOD-001/evidence/model-routing/`, not inside
   MOD-000's approved evidence tree.** DC-17 requires re-running MOD-000's
   drill *procedure*; it does not require mutating an APPROVED module's
   evidence, and doing so would sit badly with WIP=1.
4. **MR-linked evidence** in `MR-MOD001-<YYYYMMDD>-<NNN>` form, carrying
   resolved model identity and agent/session id.
5. `MODEL_ROUTING.md`'s critical-slice row updated from "not yet
   registered" to the registered agent, with the fallback text rewritten
   to describe an execution mode *inside* the role rather than a
   substitute for it — and `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`
   naming the role under Appendix H.1's "required agent roles" field.

If a session reaches any of the three named slices with the role
unregistered or not runtime-attestable, the correct report is
`BLOCKED: MODEL_ASSURANCE_UNVERIFIED` per DC-17's no-silent-downgrade
rule — never proceed on the fallback.

---

# Decision 2 — does an empty directory shell activate a §4.3 surface profile?

## Context

DC-21 states the ten surface-specific engineering profiles under EIP
§4.3/Appendix H "become binding starting MOD-001."

`knowledge/03-Modules/MOD-001/CAPABILITIES.md` currently states: "§4.3
profiles selected: **none activated yet**... MOD-001 *establishes* the
profile scaffolding... it does not itself need a domain-surface profile
(it is Foundation/Control, not a Backend/Admin/Mobile/etc. surface)."

`IMPLEMENTATION.md` §1 nonetheless has MOD-001 creating `backend/`,
`admin-web/`, `frontdesk-web/`, `mobile/`, and `infra/` trees — five
surfaces DC-21 names — as empty shells, and scaffolding all eleven
Appendix H.2 rule families as empty directories.

The reviewer's finding (P1-9): deciding "an empty shell doesn't count"
inside the module's own capability file, with no ADR, at exactly the
module DC-21 names as its activation point, is the self-serving
interpretation DC-09/DC-14 warn against.

## Decision, in three parts

### Part 1 — The general rule: an empty, code-free shell does NOT activate a surface profile

Creating a placeholder package/module boundary with no source code
inside it does not activate the corresponding §4.3 profile. Grounded in
§4.3's own text, not convenience:

- §4.3's opening line: "Surface agents are **implementation
  specialists** beneath the lifecycle governance in §4.1." An empty
  shell involves no implementation.
- Every profile's rules are **path-scoped to source-file globs**:
  `backend/**/*.py`, `web/**/*.{ts,tsx}`, `mobile/**/commonMain`,
  `mobile/iosApp/**` and `iosMain`, `edge/**`. A directory containing no
  files of those types matches nothing.
- Every "required engineering behavior" §4.3 lists **presupposes code to
  constrain**: FastAPI/Pydantic boundaries, business logic outside
  routers, explicit transaction boundaries, design-system reuse before
  new components, permission-aware states, no business truth in UI,
  strict commonMain/platform boundaries, immutable presentation state.
  None has an instance in an empty shell.
- H.3 forbids the alternative directly: "Rules are not allowed to encode
  vague slogans... They must state concrete, **testable** constraints...
  and avoid overengineering." Ten profiles authored against zero lines
  of code produce unfalsifiable rules.
- §4.2 stage 8 forbids it from the other side: "Avoid context bloat; no
  blanket loading of every capability."

Activating all ten profiles over empty shells would be profile theater —
the same failure class DC-14 warns about, approached from the opposite
direction. The honest objection to MOD-001's current position is not
that the interpretation is wrong. It is Parts 2 and 3.

**Corollary — shell *shape* is an architecture decision, not a profile
decision.** The shape of `mobile/shared/src/commonMain` vs.
`iosApp`/`androidApp` does encode an architectural commitment the mobile
profile would otherwise govern ("strict commonMain/platform
boundaries"). That decision belongs to §4.1's `veyro-lead` (Opus) and to
the TSD reference stack — where MOD-001's plan already correctly sources
it — not to a Sonnet-tier surface implementation agent. Profiles govern
how code is written, not whether a directory boundary is well chosen.

### Part 2 — MOD-001's "none activated" conclusion is wrong: two profiles activate now

This is the real finding beneath P1-9, and the part CAPABILITIES.md must
change.

**Infra / SRE / CI — ACTIVATES. MOD-001 *is* this profile's module.**
§4.3's path scope is "`infra/**`, CI and observability" and its named
behaviors are: "IaC review; least privilege; secrets externalized;
reproducible environments; rollback/canary; cost tags/budgets; OTel;
SLOs; DR; no Production action without owner approval." That is a
description of GOV-01-R03/R04/R05 almost verbatim. MOD-001 authors real
content at those paths: `infra/environments/{local,qa,staging}/`,
`.github/workflows/`, the per-environment secret-scoping design in
`IMPLEMENTATION.md` §2, the canary/rollback mechanism, the
release-evidence record. "MOD-001 is Foundation/Control, not a surface"
is true of Backend/Admin/Mobile and **false** of Infra/SRE/CI —
Foundation/Control infrastructure is precisely this profile's surface.

**Backend — ACTIVATES, bounded.** MOD-001 authors real Python under
`backend/**`: `app/main.py`, `alembic/`, `pyproject.toml`, and
critically the RLS/tenant-isolation harness with its fixture schema,
roles, and grants. The Backend profile behaviors that have actual
subject matter here are **PostgreSQL constraints/RLS**, **migration
safety**, and **clean, testable layers**. Activation is bounded to the
scaffold and harness code MOD-001 actually writes; the profile's
per-aggregate behaviors (transaction boundaries, idempotent externally
retryable mutations, domain ownership) have no instances yet and are
inherited by MOD-002+.

**The other eight DEFER** — Admin Web, General Web, Front Desk/POS, KMP
Mobile, iOS Host, Android Host, Edge, Data/AI — to whichever module
first adds real source code under their path scope.

**The dividing line for build/toolchain files** (the case that decides
`admin-web/package.json`, Gradle files, and GOV-01-R07's pinned
KMP/Compose/Gradle/Xcode/AGP matrix): **build, toolchain, and CI
configuration for a surface is Infra/SRE/CI-profile work; the surface's
own profile activates when the surface's own source code appears.** The
mobile profile's behaviors are about shared-by-default architecture,
immutable state, offline sync, design-system reuse, RTL/a11y — a pinned
toolchain version matrix engages none of them, while "reproducible
environments" and "release readiness" engage Infra/SRE/CI directly.

### Part 3 — The deferral must be mechanically enforced, not interpretive

This is what actually answers the reviewer. A deferral recorded as prose
inside the deferring module's own capability file is self-certification,
regardless of whether the reasoning is sound — and this project has
repeatedly found that the difference between a legitimate deferral and a
drifting one is whether anything fails closed when it is violated.

MOD-001 is **already required** to build a capability-manifest validator
(`REQUIREMENTS.md` §3, "Capability-governance validation gates";
Appendix H.1). Two additions, both binding:

1. **A `surface_profile_activation` check inside MOD-001's
   capability-governance CI gate.** It maps §4.3's path globs to profile
   IDs and **fails closed** when a surface path acquires its first
   source file of that surface's file types while the owning module's
   `module-capabilities.yaml` row lacks the corresponding activated
   profile. Blocking, with a deliberate-violation fixture proving it
   denies — the same discipline `IMPLEMENTATION.md` §4 already applies to
   the six architecture gates.
2. **Every deferred empty shell carries a marker file** naming the §4.3
   profile that must activate before code lands there, and the check
   reads that marker rather than an inferred mapping. This makes the
   deferral a declared, checkable contract rather than an absence.

With these, "we judged the shell doesn't count" becomes "the shell
cannot silently gain code without the profile," which is the property
the reviewer was actually asking for.

### Part 4 — DC-21's cross-cutting controls are NOT deferred

DC-21: "Cross-cutting Security, Privacy, Tenant Isolation, Financial,
Access/Life-Safety, Localization/RTL, Accessibility, Load and
Observability controls are **additive, never replaced** by a surface
profile." §4.3's own last table row says the same.

These attach to MOD-001 **now**, independent of surface profiles, and
MOD-001's work is full of their subject matter: the tenant-isolation
harness, SAST/secret/dependency scanning, the a11y and RTL lints, OBS,
PERF. `CAPABILITIES.md`'s current "none activated yet" reads as though
the cross-cutting set is idle too, which is materially wrong. It must
state the cross-cutting controls as active and additive.

## Consequences of Decision 2 — a real, disclosed cost increase

Activating two profiles means, per DC-21 ("agent/rule/skill profile")
and Appendix H.2:

- `.claude/agents/veyro-infra-sre-engineer.md` (Sonnet) and
  `.claude/agents/veyro-backend-engineer.md` (Sonnet) authored.
- `.claude/rules/infra/{iac,secrets,observability,release}.md` and
  `.claude/rules/backend/{architecture,api,database,concurrency,performance}.md`
  authored with **real content** meeting H.3's content standards — not
  the empty scaffolds `IMPLEMENTATION.md` §1 currently plans. The other
  nine families stay scaffolded/empty.
- `IMPLEMENTATION.md` §1's "MOD-001 adds no new agents (existing 9-role
  set covers it)" becomes wrong on three counts (this decision's two,
  plus `veyro-critical-engineer` from Decision 1) and must be corrected.

Letting `veyro-implementer` stand in for the two named surface engineers
is rejected for the same reason Decision 1 rejects `veyro-lead` standing
in for `veyro-critical-engineer`. Applying the standard in one place and
not the other would be inconsistent in the project's own favour. Both
new surface agents are Sonnet-tier per §4.3, so neither requires
assurance-tier qualification — the cost is low and this ADR is their
routing-change record.

**Timing, and why it differs from Decision 1.** Decision 1's condition
lands at Definition of Ready because it governs *who is permitted to
make a decision* — no critical-slice code should exist before the role
that authorizes it is attestable. Decision 2's artifacts are *module
deliverables*, inside MOD-001's own implementation scope, enforced by
MOD-001's own capability-governance gate. So:

- **At Definition of Ready:** `CAPABILITIES.md` and
  `module-capabilities.yaml` must record the correct profile selection —
  Infra/SRE/CI and Backend activated, the other eight explicitly
  deferred with markers, cross-cutting controls active — and the Part 3
  enforcement check must be specified in `IMPLEMENTATION.md`.
- **Before implementation work begins at `infra/**`, CI, or
  `backend/**`:** the two profiles' agents and rule families must exist
  with real content.

## MODEL_ROUTING.md has a third, related gap

`MODEL_ROUTING.md`'s role→agent table covers §4.1's lifecycle roles and
contains **no rows at all** for §4.3's ten surface agents. It therefore
cannot record which surface profiles are registered, which are
activated, or which are deferred. It needs a new "§4.3 surface-profile
agents" section listing all ten with honest registration status — the
same way its critical-slice row honestly recorded "not yet registered"
rather than omitting the role. Recorded here as a consequence; authoring
it is the orchestrating session's follow-up.

---

## Status

**DECIDED.** Both decisions are actionable without owner approval.
Decision 1 carries five binding pre-DoR conditions (ADR + independent
review + routing drill + MR evidence + MODEL_ROUTING/manifest update);
Decision 2 carries a DoR condition (correct profile selection recorded
+ enforcement check specified) and a pre-implementation condition (the
two profiles' agents and rules authored).

**Known limitations of this ADR, disclosed:**

1. It was authored from `EIP_MIRROR.md` and `TSD_MIRROR.md`, the
   owner-produced pandoc extracts, not from the governing `.docx`
   directly (BUG-028's capability gap persists for this session). Every
   §4.1/§4.3/Appendix H/DC-21 quotation above should be re-verified
   against the source docx by a session that can read it — the same
   caveat `.claude/rules/admin-privileged-console-baseline.md` and
   `CAPABILITY_POLICY.md` already carry. The mirrors were independently
   verified by the MOD-001 planning session (`BUG-028`), which is why
   they were relied on here; that is verification of identity, not of
   every clause.
2. The §4.1-vs-Appendix-H.2 tension over `veyro-critical-engineer` is
   resolved by reasoning (H.2's list is explicitly partial), not
   escalated. A session that reads it differently should reopen this
   ADR rather than act on the other reading.
3. The CAPABILITY_POLICY-scope-vs-DC-21 gap (agents governed by
   MODEL_ROUTING, not the CAP registry, while DC-21 speaks of
   "agent/rule/skill profile") is flagged, not fixed.

## Addendum (2026-09-14, after both binding-condition gaps closed) — Decision 1 condition 4's disposition

Binding condition 4 required "MR-linked evidence... carrying resolved
model identity and agent/session id." The corrected routing drill
(`knowledge/03-Modules/MOD-001/evidence/model-routing/ROUTING_DRILL_2026-09-14.md`)
supplies agent/session ids for all three dispatches but cannot supply
resolved model identity — the same `BUG-027`-class gap MOD-000's own
certification disclosed and accepted (a file-based transcript-isolation
limitation of `mr_verify.py`-style tooling, not something a single
dispatch can work around).

**Formal disposition, recorded here rather than left as an open
question in a status file:** this residual is **ACCEPTED AS A
DISCLOSED, NON-BLOCKING LIMITATION**, on the same terms MOD-000's
`BUG-027` set: the compensating controls are (a) the explicit
non-default `model` parameter set on every dispatch (`opus` for
`veyro-critical-engineer`, `sonnet` for the routing-drill dispatches to
`veyro-implementer`), and (b) Opus-tier-depth behavioral evidence where
the dispatch target was Opus — though per the independent review's own
P1-1/P1-2 findings, that behavioral evidence must not be overstated as
proof of *independent reasoning* beyond what the charter itself already
states; its evidentiary weight is limited to confirming the dispatch
executed and produced a charter-consistent result, not to attesting
model tier on its own. Condition 4 is therefore satisfied to the same
standard MOD-000 was certified under — not fully closed, but formally
and honestly disposed of, not silently left ambiguous.

## Affected

- `knowledge/00-System/MODEL_ROUTING.md` — critical-slice row (close the
  "not yet registered" gap; rewrite the fallback as an in-role execution
  mode); new §4.3 surface-profile agents section.
- `knowledge/03-Modules/MOD-001/MODEL_ROUTE.md` — remove "no new agent,
  no routing change, no ADR needed"; add `veyro-critical-engineer`,
  `veyro-infra-sre-engineer`, `veyro-backend-engineer`; cite this ADR.
- `knowledge/03-Modules/MOD-001/REQUIREMENTS.md` — §0's "no new agent
  required"; GOV-01-R02's routing statement.
- `knowledge/03-Modules/MOD-001/CAPABILITIES.md` — replace "§4.3
  profiles selected: none activated yet" with the two-activated /
  eight-deferred / cross-cutting-active position.
- `knowledge/03-Modules/MOD-001/IMPLEMENTATION.md` — §1's "adds no new
  agents" claim; `.claude/rules/{backend,infra}/` need real content, not
  empty scaffolds; add the Part 3 `surface_profile_activation` check and
  its deliberate-violation fixture to §4's gate plan.
- `knowledge/03-Modules/MOD-001/STATUS.md` — gate checklist gains the
  pre-DoR conditions above.
- `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` —
  required agent roles and activated profiles.
- New: `.claude/agents/veyro-critical-engineer.md`,
  `.claude/agents/veyro-infra-sre-engineer.md`,
  `.claude/agents/veyro-backend-engineer.md`.
- `knowledge/03-Modules/MOD-001/SCENARIOS.md` — **not touched by this
  ADR**; the Scenario Review's own disposition of these findings, and any
  scenarios needed for the new routing drill and the
  `surface_profile_activation` gate, belong to the Scenario Review
  workflow, not here.
- `knowledge/00-System/OWNER_APPROVALS.md` — **no new OWN row required**
  (see "Authority" above). Recorded explicitly so a future session does
  not read the absence as an omission.
