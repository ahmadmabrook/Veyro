---
doc: MOD-001_CAPABILITIES
status: LIVE — DRAFT (planning stage)
module: MOD-001
updated: 2026-09-14
---

# MOD-001 — Capabilities (per-module manifest, capability-gap analysis)

Appendix D field: "Per-module capability manifest: selected §4.3
profiles, exact Rules/Skills/tools, CAP/SKL/RULE IDs, missing capability
blockers and qualification evidence." Per this project's `CAPABILITY_POLICY.md`
9-stage lifecycle and DC-18: reuse approved capabilities first; only
search for new ones on a real, demonstrated gap.

**§4.3 profiles selected: corrected (Scenario Review round 1, P1-9 →
`ADR-005` Decision 2).** The original "none activated yet" conclusion
was wrong — reached inside this module's own capability file with no
ADR, at exactly the module DC-21 names as the activation point, which is
the self-serving-interpretation failure DC-09/DC-14 warn against. The
real, ADR-005-decided position:

- **Infra/SRE/CI — ACTIVATES. MOD-001 *is* this profile's module.**
  `infra/environments/{local,qa,staging}/`, `.github/workflows/`, the
  canary/rollback mechanism, and the release-evidence record are real
  content at this profile's own path scope (`infra/**`, CI,
  observability), matching its named behaviors (IaC review, least
  privilege, reproducible environments, rollback/canary, SLOs, DR) —
  GOV-01-R03/R04/R05 almost verbatim. Agent: `veyro-infra-sre-engineer`
  (Sonnet).
- **Backend — ACTIVATES, bounded.** Real Python under `backend/**`
  (`app/main.py`, `alembic/`, `pyproject.toml`) plus the RLS/
  tenant-isolation harness's fixture schema/roles/grants engage this
  profile's PostgreSQL-constraints/RLS and migration-safety behaviors.
  Bounded: the harness's own critical-slice logic belongs to
  `veyro-critical-engineer` (below), not this profile. Agent:
  `veyro-backend-engineer` (Sonnet).
- **The other eight (Admin Web, Web, Front Desk/POS, KMP Mobile, iOS
  Host, Android Host, Edge, Data/AI) correctly DEFER** — an empty,
  code-free directory shell does not activate a profile (§4.3's rules
  are path-scoped to real source-file globs; H.3 forbids unfalsifiable
  rules over zero lines of code). Each activates when the module that
  first adds real source code under its path scope registers the
  corresponding agent.
- **The deferral is mechanically enforced, not interpretive** — see
  `IMPLEMENTATION.md` §4's `surface_profile_activation` CI check.
  **Corrected (Scenario Review round 2, P1-6): the check is not
  marker-vs-reality alone** — a path prefix with *neither* an
  activated-profile record *nor* a deferral marker also fails closed
  (the fail-open hole a marker-only design left for any §4.3 path with
  no directory yet). See `IMPLEMENTATION.md` §4 gate 7's own text for
  the current, corrected design — not restated here to avoid this file
  going stale relative to that one, exactly as happened with the
  design's first version.
- **Cross-cutting DC-21 controls (Security, Privacy, Tenant Isolation,
  Financial, Access/Life-Safety, Localization/RTL, Accessibility, Load,
  Observability) are additive and ACTIVE for MOD-001 now**, independent
  of surface-profile state — MOD-001's own tenant-isolation harness,
  SAST/secret/dependency scanning, a11y/RTL lints, OBS and PERF work are
  all real instances of these, not idle.

**Also required (`ADR-005` Decision 1): `veyro-critical-engineer`
(Opus)**, bounded to exactly 3 slices (the tenant-isolation/RLS harness,
the authn negative-credential fixture pattern, and the RLS+permission
architecture gates) — see `MODEL_ROUTE.md`.

**Registration:** files exist and the routing integration is live —
see `knowledge/03-Modules/MOD-001/STATUS.md`'s gate checklist for
current status (`BUG-029`/`BUG-030` both closed; not restated here).

## Capability-gap analysis, per MOD-001 workstream

| Workstream | Capability required | Existing project capability reusable? | Missing capability | Build vs. acquire | Provenance/security review needed | Lifecycle/rollback | Cost/spend |
|---|---|---|---|---|---|---|---|
| Reading governing EIP/TSD docx (planning) | docx text extraction | **No** under CAP-007's Bash guard, as of this session's start | Guard-compliant docx read path | N/A this turn — resolved via owner manual extraction (BUG-028, CLOSED) | Any *standing* fix (guard allowlist extension) would need independent security review; not built this turn | Mirrors are convenience copies, rollback = delete, re-derive from docx | None |
| Test-pyramid harness (GOV-01-R01) | Unit/component/integration/contract/E2E/mobile-UI/exploratory test runners | Partially — MOD-000 has no test runners (it never needed one; CAP-004 "core harness tools" covers Bash/Read/Write/Edit only) | A concrete test-runner stack per layer | **Build/select during implementation, not this planning turn** — TSD does not mandate a specific language/framework beyond "FastAPI"-style backend architecture references seen in Appendix H.3; selecting exact tools (e.g. pytest, a JS/TS test runner, a mobile UI test tool) is an implementation-time decision, not a planning-time one, and doing it now would risk inventing a stack the TSD doesn't actually specify | Standard open-source test tooling — no special review beyond this project's existing DC-19 supply-chain discipline | Standard | None (open-source) |
| CI pipeline execution | A CI runner (GitHub Actions, given this repo's existing GitHub remote — `ahmadmabrook/Veyro` — is already the natural fit, though the TSD mirror text I read does not itself name a CI vendor) | No CI pipeline exists yet | CI vendor selection + credentials | Reuse the existing GitHub remote (no new vendor); GitHub Actions is free for private repos at low usage tiers | DC-19 supply-chain review for any third-party Action used; DC-16 owner approval if usage tier requires payment | Standard | Possibly $0 at MOD-001's expected usage; flag before it isn't |
| SAST/dependency/secret/container/IaC scanning (GOV-01-R03/R04) | Scanning tools | No — none registered | Specific scanner selection | Prefer free/open-source (e.g. the kind of tooling already implied by this project's own `bash_guard.py`-adjacent security discipline) over a paid SaaS | DC-19 review before activation; if paid, DC-16 owner approval | Standard, hash-pin per CAPABILITY_POLICY.md | Free tooling preferred; flag any paid option before use |
| Artifact signing (GOV-01-R04) | Code-signing mechanism | No | A signing key/process | A dev-only/self-signed key is in scope without owner involvement; a real production signing certificate is DC-16 owner-reserved | DC-19 for the signing tool itself | Standard | Dev-only: none. Production: owner-reserved |
| Mobile toolchain (GOV-01-R07) | Kotlin/KMP/Compose/Gradle/Xcode/AGP pinned versions | No — no mobile code exists yet (MOD-006's scope) | A pinned compatibility matrix (document, not infrastructure) | MOD-001 documents the matrix; does not provision Apple/Google developer accounts | N/A for the document itself | N/A | Real store accounts/macOS CI runners are DC-16 owner-reserved spend — explicitly deferred, not decided here |
| Progressive delivery / canary (GOV-01-R05) | Feature-flag consumption + canary rollout mechanism | No | A minimal scripted mechanism (no cloud infra exists yet) | Build minimal/local — do not acquire a commercial feature-flag SaaS (e.g. LaunchDarkly) without a demonstrated gap review, per DC-19 | Required if any third-party service is later proposed | Standard | None if built minimal/local |

**Missing capability blockers this session found:** none that block
MOD-001 *planning*. `BUG-028` (docx read path) blocked *requirement
materialization* specifically and is now CLOSED. No blocker prevents
reaching Definition of Ready in this session, contingent on the
Scenario Review outcome below.

**New capabilities proposed/qualified this turn:** none. Every
workstream above either reuses existing project capability (CAP-004
harness tools, the existing GitHub remote) or is explicitly deferred to
implementation time, where the actual tool selection can be justified
against real, then-current TSD/EIP text rather than guessed now. This is
intentional — DC-18/DC-19 require reuse-first and gap-justified
acquisition, and inventing a CI vendor or test framework during a
planning-only turn (with implementation explicitly out of scope this
turn) would risk exactly the kind of "no material architecture change
without explicit owner approval" violation DC-16/DC-09 warn against.

**No paid service activation, no real member data, no Production
promotion occurred or is proposed by this analysis** — consistent with
`OWNER_APPROVALS.md`'s standing restrictions.
