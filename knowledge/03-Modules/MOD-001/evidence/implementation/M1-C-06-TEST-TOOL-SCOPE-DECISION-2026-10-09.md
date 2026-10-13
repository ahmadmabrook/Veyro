---
doc: M1-C-06-TEST-TOOL-SCOPE-DECISION
module: MOD-001
date: 2026-10-09
type: ARCHITECTURE_CRITICAL decision (narrow)
requirement: GOV-01-R03, GOV-01-R04, DC-19
related: BUG-057, CAP-009 (gitleaks), CAP-010 (Ruff)
status: DECISION RECORDED — NOT AN AUTHORIZATION
---

# M1-C-06 — test-tool capability scope decision

Scope of this record: two governance questions only. Sources consulted:
`knowledge/00-System/CAPABILITY_POLICY.md` (lines 9, 28–34, 59, 63–91) and
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-057-unregistered-scanner-and-test-tool-use.md`
(lines 14–39). No other files were read; no tool was run against the project
tree; no registry, plan, or code file was edited; no review was dispatched.

## Decision 1 — pytest and mypy are separate third-party executable capabilities

**Yes.** pytest and mypy each require their own exact-scope registry row,
their own synthetic positive/negative qualification, and their own independent
Opus approval before any new governed project reliance.

Grounds:

1. `CAPABILITY_POLICY.md` line 9 puts every Skill, Rule, Plugin, MCP server,
   hook, **or script** in scope. A third-party Python executable invoked
   against project files is squarely inside that set.
2. Line 28–30's first-party/harness exemption reaches only harness-native
   capabilities (Bash/Read/Write/Edit, Browser pane, iOS Simulator bridge) and
   Anthropic first-party public Skills. pytest and mypy are neither. The
   clause closes explicitly: third-party capabilities "get no exemption of any
   kind." Invoking pytest *through* the exempt Bash tool does not transfer the
   exemption to pytest — Bash is the transport, pytest is the capability.
3. Line 59 defaults third-party executables to `review_status: PENDING` and
   non-usable on real work until independently evaluated and qualified. Line
   34's fail-closed rule makes any unregistered capability not usable and
   requires `BLOCKED: CAPABILITY_UNREGISTERED` rather than proceeding;
   unapproved capabilities may be touched only in a synthetic qualification
   drill. BUG-057 lines 38–39 already records pytest and mypy as separately
   unregistered and states that the filing does not silently qualify them.
4. They cannot share one row. Line 58 forbids granting any capability broader
   scope than its specific gap requires, and a row's `scope` field is a
   per-capability field. A test runner that executes arbitrary project code
   and a static type checker that reads it are different gaps with different
   blast radii; one combined "test tooling" row would be exactly the blanket
   scope line 58 prohibits.

**Ruff lint/format:** covered by CAP-010's exact scope only to the extent
CAP-010's recorded scope and its actually-executed synthetic drills evidence
those invocation modes. This decision deliberately makes no finding about what
that evidence contains — it was not re-read here. If the drills evidence only
the `S` (security-rule) role, then lint and format are outside CAP-010's exact
scope, and extending the row to cover them is a scope change that triggers
stage 9's mandatory return to stages 4–5 before continued reliance, not a
registry-text edit. BUG-057 lines 34–37 records the project-file Ruff
lint/format and pytest invocations during C06 preparation as disclosed uses
under the defect, explicitly not excused by the synthetic `S` and gitleaks
drills. Nothing here infers or asserts a historical PASS for any of those
invocations; their technical output is not evaluated by this decision, and
line 37–38's bar on further real-tree use of gitleaks, Ruff, pytest and mypy
remains in force.

## Decision 2 — one independent action may carry four individual verdicts

**A single fresh independent capability-security action is permissible; a
separate action per capability is not mandatory by policy** — subject to four
conditions, all of which must hold.

Policy requires one *independent Opus assurance decision per capability*
(lines 76–86: an Opus assurance role must independently evaluate the evidence
and make the final `APPROVED`/`REJECTED`/`BLOCKED` call, and no capability
becomes `APPROVED` from a Sonnet run alone). It does not require one dispatch
per capability. Lines 88–94 make the unit of record the registry *row*
(`approved_by`, `approved_date` per row), not the review session.

Conditions on a batched action:

1. **Evidence complete first.** Stage 5 precedes stages 6–7: each of CAP-009,
   CAP-010, pytest and mypy must already have its own recorded synthetic
   positive and negative test results before the action is authorized. A
   capability whose drill has not been run cannot be inside the batch.
2. **Individually reasoned verdicts.** Four separate verdicts, each with its
   own grounds, its own exact scope statement, and its own `approved_by` /
   `approved_date` / `last_reviewed_at` / `next_review_due` /
   `rollback_target`. One capability's verdict may not be inherited by, or
   reasoned jointly with, another's. A collective verdict is a blanket
   approval and is non-compliant regardless of how many rows it names.
3. **Reviewer/implementer separation preserved.** Fresh context,
   `veyro-security-reviewer`, reviewing Sonnet-produced evidence and never
   re-running the drills itself (lines 79–82).
4. **Separate authorization.** This decision is not that authorization, and
   BUG-057 line 45 already states a planned review action is a requirement,
   not dispatch authority.

## Residual dependency

The determination above is conditional on evidence this session did not
inspect and must not assume:

1. Whether CAP-010's recorded exact scope and executed drills cover Ruff
   lint/format, or only the `S` role. Unresolved here; resolves Decision 1's
   Ruff clause either way without changing it.
2. Whether complete synthetic positive/negative qualification evidence exists
   for pytest and for mypy. Per BUG-057 lines 38–39 they are unregistered, so
   the working assumption is that it does not yet exist; until it does,
   Decision 2's condition 1 excludes them from any batch, leaving CAP-009 and
   CAP-010 as the only batch-eligible rows.
3. Authorization for the independent action itself remains owner/dispatch
   business, outside this decision.

No approval was granted, no review dispatched, no registry/plan/code edited,
no project tool run, and no historical PASS inferred by this record.
