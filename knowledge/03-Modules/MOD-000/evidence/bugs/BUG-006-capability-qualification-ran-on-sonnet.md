---
doc: BUG-006
status: CLOSED for CAP-002; OPEN for CAP-001 (narrowed, bounded scope — see resolution below)
found_date: 2026-09-04
resolved_date: 2026-09-05 (CAP-002); CAP-001 re-test still pending
found_by: Phase 5 independent review (veyro-code-reviewer, fresh context, Opus) — finding F5-004/F5-003, confirms catalog SCN-MOD000-055's own pre-declared "Expected audit result if run today: FAIL"
severity: P1 (Blocker per SCN-055's catalog severity) for CAP-001; RESOLVED for CAP-002
---

# BUG-006: Capability qualification (CAP-001, CAP-002) ran on Sonnet, not Opus

## What is wrong

`CAPABILITY_POLICY.md` line 48: "Qualification runs (positive/negative
tests, independent evaluation of third-party capability text) are
assurance-tier work -> route to Opus per `DEVELOPMENT_CONSTITUTION.md`."

`CAPABILITY_REGISTRY.md`'s own table (never hidden) records:
- CAP-001 `qualified_by: veyro-implementer (this session, Sonnet)`
- CAP-002 `qualified_by: veyro-test-author (this session, Sonnet)`

Both violate the policy's own routing rule. `SCENARIO_CATALOG.md`'s
SCN-MOD000-055 detail block had already identified this exact defect and
pre-declared "Expected audit result if run today: FAIL" — but it was never
filed as a bug, so it never appeared in the "0 open bugs" count that Phases
1-4 all reported.

## Why it wasn't caught by Phases 1-4

The scenario's own text carried the finding as prose ("this violates
CAPABILITY_POLICY.md's explicit routing... that excuse is struck"), which
every phase's evidence-integrity checking treated as narrative, not as a
tracked defect, because the checker only scans `evidence/bugs/` for bug
counts and never cross-references scenario prose for self-declared FAILs.
(This class of gap is now also filed — see `evidence/bugs/BUG-007-*.md`
for the broader validator/checker weakness.)

## Why it is not yet fixed

No currently-registered agent is both (a) Opus-tier and (b) tooled with
the access needed to actually *perform* a qualification run (Notion MCP
tools for CAP-001, Bash for CAP-002's TestSprite CLI, plus Write to record
evidence) — `veyro-security-reviewer` and `veyro-lead` (the two Opus roles
closest in mandate) are deliberately review-only (Read/Grep/Glob/Bash for
`veyro-security-reviewer`; no Write, no Notion tools), consistent with
role-separation (a reviewer should not also be the implementer performing
the thing it reviews). Fixing this by simply granting those tools to a
reviewer agent would itself reintroduce role-collapsing (see finding
F5-018). The correct fix is either (a) a new, purpose-built Opus-tier
"capability qualifier" agent role, or (b) an owner-recorded deviation
accepting the existing Sonnet-tier evidence with a documented risk
rationale. Both are architecture-level decisions, not a same-turn config
edit — deferred, tracked here, not silently worked around.

## Resolution (2026-09-05, owner decision)

The owner decided the operating model directly rather than leaving it to
an agent's architecture judgment: **Sonnet may execute the mechanical
tests; an existing Opus assurance role (`veyro-security-reviewer` — no
new agent needed, it was already registered with exactly this mandate in
its own description) must independently evaluate that evidence and issue
the final APPROVED/REJECTED/BLOCKED call, without re-running the tests
itself.** Documented in `CAPABILITY_POLICY.md`'s "Model-routing
interaction" section, grounded in a fresh direct re-read of EIP §4.2/§4.1
(not a secondhand citation this time).

`veyro-security-reviewer` (Opus, fresh context) independently reviewed
the existing CAP-001/CAP-002 evidence — did not re-run any test, did not
touch Notion or TestSprite — and returned two different, real verdicts:

**CAP-002 (TestSprite): APPROVED, scope narrowed.** The reviewer found
the evidence genuinely sound (a real malformed-input rejection with 4
structured field errors, a real credit-balance zero-spend proof, a real
independent Phase 2 re-run) but caught a genuine overclaim: the registry
had let `test create`/`code`/`plan` ride in as "by extension" of the
tested commands, never actually tested. Struck. Scope also corrected:
`doctor`/`usage` authenticate to `api.testsprite.com` (read-only,
non-billed) and were previously mis-described as "offline." **Closed for
CAP-002** — `CAPABILITY_REGISTRY.md` updated with `approved_by:
veyro-security-reviewer, approved_date: 2026-09-05`, narrowed scope
recorded, `SCOPE_NOTE.md` and `module-capabilities.yaml` corrected to
match (original `positive_test.md`/`negative_test.md` evidence files
left untouched, per "preserve original historical evidence").

**CAP-001 (Notion MCP): downgraded from APPROVED to QUALIFIED, remains
OPEN.** The reviewer found four real problems the original registry
entry didn't disclose: (1) **provenance was wrong** — Notion's MCP server
is third-party (Notion's own hosted server via a user-authorized
connector), not "first-party Anthropic-connected" as the registry
claimed, which matters because the policy's own exemption clause
explicitly excludes exactly this class; (2) the negative test rejected a
*malformed* write (an invalid enum value), not an *out-of-scope* write —
the registry's own qualification-history text overclaimed "out-of-scope
write rejected" when that was never actually attempted; (3) no raw
request/response artifacts exist for the positive test, only prose; (4)
no stage-4 (Independent evaluation) record exists for the Notion MCP's
own instructional text, which the reviewer observed includes a nudge
toward a paid "full version" upgrade card — untrusted third-party text,
correctly never acted on by any session, but never formally logged as
evaluated either. `CAPABILITY_REGISTRY.md` updated: provenance corrected,
`review_status` downgraded to `QUALIFIED`, `approved_by` left empty.

**Bounded re-test now required to close CAP-001 (much narrower than the
original "architecture decision" framing — that part is resolved):**
(a) attempt one genuine out-of-scope write (targeted outside the Veyro
Control Plane page tree) and capture the real refusal or success either
way; (b) capture raw request/response artifacts for a positive-test
re-run; (c) log a stage-4 note on the Notion MCP's own instructional
text, flagging the upgrade-nudge as untrusted data, consistent with how
it has already been handled in practice. All three are `veyro-security-reviewer`
(Opus)-appropriate, bounded, and don't require new infrastructure.

**Also noted, tracked separately, not blocking:** CAP-005/CAP-006 (the
Phase 5 manual-QA capabilities) were qualified by an Opus-context agent,
which is real progress, but the qualifying run and the "independent"
review would currently be the same invocation — left `QUALIFIED` rather
than `APPROVED` until a genuinely distinct fresh-context Opus review
confirms them, for the same reviewer/implementer-separation reason CAP-001
was just downgraded.

## Bounded re-test executed (2026-09-05, second Phase 5 re-review follow-up)

All 3 items from the bounded re-test above were run by the main session
(mechanical execution, per the established operating model). Full raw
evidence: `knowledge/05-QA/capability-evidence/CAP-001/BOUNDED_RETEST_2026-09-05.md`.

- **(a) Genuine out-of-scope write:** executed, and it **succeeded** — no
  refusal. This is a materially worse result than the prior
  `BLOCKED: SCOPE_UNVERIFIED` finding: it's now a **confirmed** absence of
  technical scope enforcement, not an inconclusive probe.
  `evidence/security/NOTION_SCOPE_AUDIT.md` and `CAPABILITY_REGISTRY.md`'s
  CAP-001 row both updated to state this as fact.
- **(b) Raw request/response artifacts:** captured, including a
  read-back fetch confirming persistence.
- **(c) Stage-4 note on Notion MCP's own instructional text:** logged —
  the upsell/upgrade-nudge text observed in `notion-fetch id="self"`
  output, correctly never acted on, now formally recorded as evaluated.

**This bug is not closed by this session's own say-so.** Per the
established operating model, a fresh-context `veyro-security-reviewer`
(Opus) must independently evaluate `BOUNDED_RETEST_2026-09-05.md` and
issue the final APPROVED/QUALIFIED/REJECTED call for CAP-001 — that
review's own record (once it lands) is this bug's actual closing
evidence, not this update.

## Affected

SCN-MOD000-055, SCN-MOD000-030, SCN-MOD000-070, `CAPABILITY_REGISTRY.md`,
`module-capabilities.yaml`, `evidence/CAP-001/`, `evidence/CAP-002/`,
`evidence/CAP-002/SCOPE_NOTE.md`.

**Blocks MOD-000 certification:** NO for CAP-002 (resolved). YES for
CAP-001 (Blocker severity) until the independent Opus review of the
bounded re-test evidence lands and closes it. CAP-005/CAP-006's
`approved_by` gap is filed separately as BUG-009, P2, not independently
certification-blocking on its own.
