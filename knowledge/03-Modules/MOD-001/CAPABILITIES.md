---
doc: MOD-001_CAPABILITIES
status: LIVE — DRAFT (planning stage)
module: MOD-001
updated: 2026-10-04 (round 18 remediation 4 — DOM-002 code-review round-4 finding R4-6 reconciled): corrected this file's body text, which still said CAP-008 was "QUALIFIED, not APPROVED" / "not usable for real project work" — stale since round 17 (2026-10-04), which restored review_status to APPROVED in CAPABILITY_REGISTRY.md the same day round 16 wrote the text below. Reconciled via an added paragraph (append, not rewrite) rather than editing the historical claim in place; see the body for detail and re-verification evidence.
prior_updated_round16seg3: 2026-10-04 (round 16 segment 3, finding R16-5 — CAP-008 named in this file's own gap-analysis table update and registered in this module's `module-capabilities.yaml`, closing the "no module manifest names it" gap; QUALIFIED, not APPROVED, correctly so per CAPABILITY_POLICY.md)
prior_updated: 2026-09-19 (Scenario Review round 15, P2-2 — front-matter corrected: this line previously said round 12/2026-09-18 despite carrying a round-14 P2-4 correction in its own body at the Infra/SRE/CI glob line below; no substantive change this round, structural findings landed in IMPLEMENTATION.md/SCENARIOS.md/ADR_CONFORMANCE.md instead)
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
  content at this profile's own path scope (`infra/**`,
  `.github/workflows/**` — **corrected, Scenario Review round 14, P2-4:
  was the non-glob "CI, observability," stale since round 13's P2-5 fix
  to `MODEL_ROUTING.md` corrected the same fact and this file was
  missed**), matching its named behaviors (IaC review, least
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
current status (**corrected, Scenario Review round 10, Editorial-4:
this parenthetical named only `BUG-029`/`BUG-030`, written before
`BUG-031`/`BUG-032` existed; all four are closed — see `STATUS.md`,
not restated here**).

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
| Branch protection / required status checks (GOV-01-R04, the bypass-protection mechanism `IMPLEMENTATION.md` §3 names as primary, underneath Blocker `SCN-MOD001-020`) — added, Scenario Review round 12, P1-5, this workstream was absent from this table entirely | GitHub branch-protection rules with required status checks, on the existing private repo (`ahmadmabrook/Veyro`) | Not yet configured; plan availability on this repo's current GitHub tier not yet confirmed by this session | Confirming the repo's plan permits required-status-check branch protection on a private repo, then configuring it | Reuse the existing GitHub remote — no new vendor. GitHub has offered branch protection (including required status checks) on free private repos since well before this project's founding, but this session has not verified this specific repo's current settings/plan, so treats it as unconfirmed rather than assumed | If confirmation finds it plan-gated, flag as a DC-16 owner-reserved spend dependency before relying on it further | DC-19 does not apply (a GitHub platform feature, not a third-party tool); DC-16 applies only if plan-gated | Expected $0 on the current plan; flag before it isn't — same convention as the CI-runner-minutes row above |

**Updated 2026-10-04 (round 16 segment 3, finding R16-5 — P2): the
"Test-pyramid harness" row above was planning-era and is now stale on
one point.** That row correctly deferred exact tool selection to
implementation time; implementation has since selected `pytest` as the
backend test runner and registered **CAP-008** (Docker Engine via
Colima + Lima + pinned `postgres:16-alpine`) as the concrete third-party
capability backing the GOV-01-R02 tenant-isolation/authn harness's
disposable-Postgres fixture (`backend/tests/harness/postgres.py`) — see
`knowledge/00-System/CAPABILITY_REGISTRY.md`'s CAP-008 row for full
provenance/scope/review-status detail. Round 16 found CAP-008 named in
**zero** module capability manifests (`validate_capabilities.py` reads
only `MOD-000/evidence/module-capabilities.yaml`), so no mechanical gate
evaluated whether MOD-001's live harness depends on an `APPROVED`
capability — a required-before-reliance gap under `CAPABILITY_POLICY.md`
stage 7, now closed: CAP-008 is registered in
`knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`'s new
`capabilities:` section, and `validate_capabilities.py` was extended to
read every module's manifest, not only MOD-000's. At the time of this
round-16 entry, **CAP-008's `review_status` was `QUALIFIED`, not
`APPROVED`** — per `CAPABILITY_POLICY.md`'s fail-closed rule this
correctly made `validate_capabilities.py` report CAP-008 as not
satisfying a module dependency until a fresh Opus capability-security
re-review restored `APPROVED` (round 16 §18.4 named the two now-closed
documentation conditions as the only remaining gap, no new drill
required). This registration was not itself a claim that CAP-008 was
usable for real project work at `QUALIFIED` — it was the opposite:
making that fact mechanically checkable rather than relying on agent
diligence alone.

**Reconciled 2026-10-04 (round 18 remediation 4, DOM-002 code-review
round-4 finding R4-6):** the re-review named above happened the same day
(round 17) and restored `review_status` to `APPROVED` in
`CAPABILITY_REGISTRY.md`, where it has remained through rounds 2/3/4 of
the DOM-002 remediation lineage — each independently re-verified by a
live `validate_capabilities.py` run, most recently round 4's own: "PASS —
8 capability/capabilities, all registered and APPROVED with required
fields present." The `QUALIFIED`/"not usable" text above is this file's
historical record of round 16's own state (append-don't-rewrite), not
CAP-008's current status.

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

## M1-C-06 draft registrations: CAP-009 (gitleaks) and CAP-010 (Ruff lint/format + `S`) — 2026-10-09

Drafted by op `2b91f76e-21fb-441d-bf1b-5a54c134ae48` per `CAPABILITY_POLICY.md` stage 7 and
`evidence/implementation/M1-C-06-CAP-ORDERING-PLAN-DECISION-2026-10-09.md` §2 step C/§7 item 3. Both
are the third-party executables the GOV-01-R03 scanner route depends on; both are registered in
`knowledge/00-System/CAPABILITY_REGISTRY.md` and bound in `evidence/module-capabilities.yaml`.

**Status of both: `QUALIFIED`, NOT `APPROVED`.** `approved_by`/`approved_date` are empty; no
`next_review_due` is set (none is invented). Stage 5 synthetic drills passed (gitleaks 6/6, Ruff `S`
4/4) and upstream provenance/pins are recorded, but stage 4 — one fresh-context Opus
`veyro-security-reviewer` determination returning a **separate** verdict per capability — has not
happened. Per the fail-closed rule neither is usable for real project work: no scan of the Veyro
tree, Git index or history, and no CI execution, may rely on either. `validate_capabilities.py` is
expected to fail closed on both until then; that is the intended hold, not a structural error.

Disclosed limits (see the registry rows): Ruff's lint/format roles have a dedicated synthetic drill
(2026-10-09, `evidence/implementation/M1-C-06-RUFF-LINT-FORMAT-SYNTHETIC-QUALIFICATION-2026-10-09.md`,
11/11 expected outcomes, qualification only, not approval) in addition to the `S` drill; Ruff
`S` is pattern-based, not taint analysis; the installed macOS Ruff wheel and the Homebrew gitleaks
binary are not the pinned Linux artifacts; no upstream signature/attestation was verified; BUG-057
(pre-existing unregistered gitleaks/ruff/pytest/mypy use) is OPEN (P1 proposed). The manifest's existing
`missing_capability_blockers: []` field is deliberately untouched and does not reflect this pending
determination.

## M1-C-06 draft registration: CAP-011 (pytest 9.1.1) — 2026-10-09

Drafted by op `d77d0542-a80c-45aa-a5ab-271b318a1b09` per `CAPABILITY_POLICY.md` stage 7 and
`evidence/implementation/M1-C-06-TEST-TOOL-SCOPE-DECISION-2026-10-09.md` Decision 1 (pytest is a
separate third-party executable capability, not covered by CAP-009/CAP-010 or any exemption).
Registered in `knowledge/00-System/CAPABILITY_REGISTRY.md` and bound in `evidence/module-capabilities.yaml`.

**Status: `QUALIFIED`, NOT `APPROVED`.** `approved_by`/`approved_date` are empty; no `next_review_due`
is set (none is invented); `lifecycle_status` is not ACTIVE. The stage-5 synthetic drill passed
(`evidence/implementation/M1-C-06-PYTEST-SYNTHETIC-QUALIFICATION-2026-10-09.md`) and the PyPI wheel pin
(SHA-256 `37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c`, equal to
`backend/requirements-dev.lock.txt`) was recorded, but stage 4 — a fresh-context Opus
`veyro-security-reviewer` determination with a verdict separate from CAP-009/CAP-010 — has not happened.
Per the fail-closed rule, pytest must not be run on any Veyro test, conftest, import or pytest config, and
no CI job may rely on it, for governed work. `validate_capabilities.py` is expected to fail closed on
CAP-011 until then; that is the intended hold. The registered invocation requires `--rootdir` and
`-p no:cacheprovider` in addition to `-c /dev/null --confcutdir` (otherwise rootdir becomes `/dev`).

Disclosed limits: attestation signature unverified; drill on macOS/Python 3.14.5, not a CI interpreter;
two tiny fixtures; wrapper must treat rc 4/5 as errors; BUG-057 (pre-existing unregistered pytest use) is
OPEN (P1 proposed). mypy remains unregistered and unqualified. No scenario PASS is claimed.

**Scope correction (2026-10-09, op `7fa75e8b-afef-4f35-a938-9d24b4b9bc1b`):** CAP-011's drafted scope is now stated as the
**INTENDED future** local/CI use of pytest 9.1.1 on the Veyro `backend/tests` tree (synthetic fixtures only, no real
data), still **QUALIFIED — NOT APPROVED**, not ACTIVE, `approved_by`/`approved_date` blank, `next_review_due` unset;
no real-tree or CI use is authorised. A project-shaped synthetic analogue
(`evidence/implementation/M1-C-06-PYTEST-TARGET-SCOPE-SYNTHETIC-2026-10-09.md`, no Veyro file touched) passed all
expected outcomes and found two limits the invocation must cover: pytest runs an explicit outside-root path (and its
conftest) despite `--rootdir`/`--confcutdir`, and a missing `testpaths` directory with no path argument falls back to
cwd. Required rules: clean env, `-c backend/pyproject.toml --rootdir=backend --confcutdir=backend -p no:cacheprovider`,
plugin autoload off, no third-party plugins, an explicit `realpath`-checked path under `backend/tests`, rc 4/5 as errors.
Remaining dependencies: independent determination and APPROVED fields, an unwritten path-allowlist wrapper, a CI
install by the `requirements-dev.lock.txt` hashes (not enforced anywhere yet), CI-interpreter evidence and review of the
Veyro test code itself. mypy is separately registered as CAP-012 below, still QUALIFIED only.

## M1-C-06 draft registration: CAP-012 (mypy 2.3.1) — 2026-10-09

Drafted by op `d3beb424-457b-432d-9db0-cb6237218773` per `CAPABILITY_POLICY.md` stage 7 and
`evidence/implementation/M1-C-06-TEST-TOOL-SCOPE-DECISION-2026-10-09.md` Decision 1 (mypy is a separate third-party
executable capability, not covered by CAP-009/010/011 or any exemption). Registered in
`knowledge/00-System/CAPABILITY_REGISTRY.md` and bound in `evidence/module-capabilities.yaml`.

**Status: `QUALIFIED`, NOT `APPROVED`.** `approved_by`/`approved_date` empty, `next_review_due` NOT SET, not ACTIVE. The
drill used only a disposable OS-temp tree (removed); mypy was never run on any Veyro source, test, config or import
(`evidence/implementation/M1-C-06-MYPY-SYNTHETIC-QUALIFICATION-2026-10-09.md`, final pass 36/36; pass 1 had two
driver-script defects, fixed and re-run). INTENDED future scope: `backend/app` only, `python -I -m mypy --config-file
pyproject.toml --cache-dir=/dev/null --no-color-output app` in a cleared env, config key set exactly
`python_version`+`strict`, wrapper-realpath-checked target, rc 0 plus expected source-file count. The drill found limits
the wrapper must cover: vacuous packages exit 0, config `files=` selects targets, outside-root/symlink targets run,
`# type: ignore` and config overrides hide errors, plugins execute code.

Open gaps: no upstream provenance fetched (network out of bounds); the lock's single hash per platform-specific compiled
wheel is unverified against any artifact; no CI install by hash; no wrapper; real nested `backend/app` layout and CI
interpreter unevidenced; a repo-root `.mypy_cache/` from earlier unregistered use is disclosed (BUG-057 OPEN). Independent
Opus determination (separate verdict) has not occurred and is not dispatched here. `validate_capabilities.py` and
`tools/validate_capability_manifest.py` are expected to fail closed on CAP-012 until then. No scenario PASS is claimed.

**Read-only provenance follow-up (2026-10-09):**
`evidence/implementation/M1-C-06-MYPY-LOCK-PLATFORM-RECONCILIATION-2026-10-09.md`
matches the lock's mypy, ast-serialize and librt hashes to macOS arm64 wheels
in PyPI's exact-version release metadata, not Linux x86-64/Python 3.13 wheels.
The intended CI platform and a byte-verified platform-specific lock remain
mandatory dependencies; CAP-012 remains QUALIFIED only.
