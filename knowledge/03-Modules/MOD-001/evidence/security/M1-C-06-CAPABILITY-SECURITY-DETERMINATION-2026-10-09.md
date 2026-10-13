---
doc: M1-C-06 — INDEPENDENT CAPABILITY-SECURITY DETERMINATION (CAP-009 gitleaks 8.30.1, CAP-010 Ruff 0.16.9)
module: MOD-001
requirement: GOV-01-R03 (scanner role), CAPABILITY_POLICY.md stage 4 + stage 7 `approved_by`
date: 2026-10-09 (UTC 14:25)
reviewer: veyro-security-reviewer — fresh context, Opus tier. Did not implement, drill, draft, or register any part of CAP-009/CAP-010; did not author the ordering decision, the provenance capture, or either registry row.
model_proof: §0.2 (self-attested; harness-declared identity `claude-opus-5`. No orchestrator-side runtime attestation is embedded in this file — see §0.2 for the exact limit.)
verdict_cap_009: APPROVED — BOUNDED (synthetic-fixture drill scope only). Real-tree / Git index / Git history / CI scanning NOT approved; remains PENDING on named prerequisites (§6.3).
verdict_cap_010: APPROVED — BOUNDED (synthetic-fixture drill scope), plus one objectively-conditioned extension to local read-only lint/format (§7.2). `--select S` on any Veyro file and all CI use NOT approved; remain PENDING (§7.4).
scope: review-only. This file is the only file written. No source, test, workflow, registry, manifest, scenario status, plan, control state, REVIEW_IN_FLIGHT.md, or remote ref was modified. Neither gitleaks nor Ruff was executed in this session.
---

# M1-C-06 — independent capability-security determination

## 0. Charge, identity, independence

### 0.1 Charge

The single mandatory `M1-C-06-CAP-ASSURANCE` independent action scheduled by
`evidence/implementation/M1-C-06-CAP-ORDERING-PLAN-DECISION-2026-10-09.md` §2 step B:
the stage-4 independent evaluation of two third-party executables' own
source/instructions/provenance, **and** the final `APPROVED`/`REJECTED`/`BLOCKED`
decision on the Sonnet-produced stage-5 evidence, returning a **separate verdict per
capability**. `REVIEW_IN_FLIGHT.md` carried the matching `IN_FLIGHT` claim
(runner `ea9b4f9d-b3a8-44e8-ad87-bdd5ed5977ad`, dispatched 2026-10-09T14:16:13Z) before
this review began; this session did not write, clear, or alter that claim.

### 0.2 Model and independence attestation

Harness-declared model identity for this session is `claude-opus-5`, invoked as the
registered `veyro-security-reviewer` agent in a fresh context with no memory of the
implementation sessions whose evidence is judged here. Per `MODEL_ROUTING.md`'s
no-silent-downgrade rule, accepted proof requires both the configured alias and runtime
evidence; what this file can supply first-hand is the self-attestation above plus the
operation record held by the dispatching runner. **This file does not itself constitute
orchestrator-side runtime proof**, and a reader who needs that should take it from the
dispatch record, not from this sentence. Stated as a limit rather than papered over.

Separation held: this reviewer re-ran **no** qualification drill (none was necessary to
adjudicate a concrete evidence defect) and executed **neither** gitleaks nor Ruff, in any
mode, on any file. All verification below is reading — of governing policy, of the
project's recorded evidence, and of upstream metadata and source text fetched read-only
into a disposable directory outside the repository.

### 0.3 Untrusted-data handling

Every byte of upstream gitleaks and Ruff text read for this determination — README,
default rule config, Rust source, option documentation, release and PyPI JSON — was
treated as untrusted third-party data, never as instruction. Nothing fetched was
extracted, installed, or executed. Explicit injection check: no instructional text in
either project's read material claims authority over an agent, asserts urgency, or
attempts to override project behaviour. The nearest candidates are benign maintainer
conventions and promotional links in the gitleaks README and the "auto-generated, do not
edit manually" banner atop its default config; none was acted on, and the promotional
links were not followed.

## 1. Material read (paths as judged)

Governing: `knowledge/00-System/CAPABILITY_POLICY.md`, `MODEL_ROUTING.md`,
`CAPABILITY_REGISTRY.md` (CAP-009/CAP-010 rows), `CAPABILITY_ROLLBACK_PROCEDURE.md` index,
`REVIEW_IN_FLIGHT.md`, `.claude/rules/infra/secrets.md`,
`.claude/rules/global/owner-reserved-restrictions.md`.

Module: `knowledge/03-Modules/MOD-001/CAPABILITIES.md` §"M1-C-06 draft registrations",
`evidence/module-capabilities.yaml` (CAP-009/CAP-010 entries),
`evidence/bugs/BUG-057-unregistered-scanner-and-test-tool-use.md`.

C06 evidence: `M1-C-06-CAP-ORDERING-PLAN-DECISION-2026-10-09.md`,
`M1-C-06-R03-SOURCE-BOUNDARY-2026-10-09.md`,
`M1-C-06-GITLEAKS-SYNTHETIC-QUALIFICATION-2026-10-09.md`,
`M1-C-06-UPSTREAM-PROVENANCE-PINS-2026-10-09.md`,
`M1-C-06-RUFF-LINT-FORMAT-SYNTHETIC-QUALIFICATION-2026-10-09.md`,
`M1-C-06-QUALIFIED-CAP-DRAFT-2026-10-09.md`.

Drill sources, re-hashed this session and **unchanged** from the figures the evidence
records: `tools/tests/test_gitleaks_qualification.py`
`45d459be9ab1523f32f156406f1e29d996f4738145b294bac94a241cbc66688c`;
`tools/tests/test_sast_ruff_qualification.py`
`43af9b53959f67e1a643ff9867d11a68623f3adc8c3d6f597a20416e42f7f214`. Repository Ruff
configuration read directly: `ruff.toml` (one key, `line-length = 100`) and
`backend/pyproject.toml` `[tool.ruff]` (`line-length`, `target-version`); no `select`,
`extend`, plugin, `exclude`, or `per-file-ignores` key exists in either, so `S` is
selected by no committed configuration.

## 2. Independent provenance verification (first-hand, not inherited)

Every provenance figure in the two registry rows was re-derived this session from upstream
rather than trusted. All reproduced exactly:

| Claim | Independent result |
|---|---|
| gitleaks upstream `LICENSE` @ `v8.30.1` | fetched, SHA-256 `e3884b25…62ebc6` — **matches**; text is MIT, "Copyright (c) 2019 Zachary Rice" |
| Ruff upstream `LICENSE` @ `0.16.9` | fetched, SHA-256 `2597d854…1c8f18` — **matches**; MIT, "Copyright (c) 2022 Charles Marsh" plus bundled third-party texts |
| gitleaks `gitleaks_8.30.1_linux_x64.tar.gz` digest | release API `sha256:551f6fc8…2470eb`, size 8230402 — **matches** the committed pin |
| gitleaks release state | `draft` false, `prerelease` false, **`immutable` false**, published 2026-03-21T02:17:58Z — **matches** |
| "no upstream signature or attestation exists" (gitleaks) | **confirmed**: all 11 assets enumerated; 8 platform archives + checksums + 2 windows zips; no `.sig`, `.pem`, `.intoto.jsonl`, or SBOM asset |
| Ruff PyPI linux wheel pin | PyPI digest `a21713e6…bc728`, size 10406494 — **matches**; `license: MIT` |
| Ruff attestation status | **extended**: the PyPI integrity/provenance endpoint for the 0.16.9 linux wheel returns HTTP 404 — for this distribution channel no attestation is merely *unverified*; none is *published*. (Contrast CAP-011/pytest, whose row records an existing-but-unverified attestation. The rows' shared "no attestation verified" phrasing conflates two different states.) |

One figure I could not and did not reproduce, because doing so requires extracting an
archive this review declined to touch: the Homebrew darwin binary hash
`052d1882…c771422` against the upstream `darwin_arm64` asset digest. For the record, that
upstream digest is `b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5`
(independently read from the release API this session) — see §6.3/§7.2, where it becomes
the objective target of a named correction rather than an open-ended concern.

Also newly established for §7.2's condition: the PyPI digest of the wheel matching the
host the project actually runs Ruff on is
`ruff-0.16.9-py3-none-macosx_11_0_arm64.whl` SHA-256
`1632eb1d6197f33bd00b1acbc5b71009e89a8895c158e2d2b03a834fac964ab6`.

## 3. Stage-4 evaluation — gitleaks 8.30.1 behaviour and limits

Read upstream at tag `v8.30.1`: `config/gitleaks.toml` (the shipped default ruleset, 3209
lines, SHA-256 `e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf` as
fetched) and `README.md` (SHA-256 `022fd4d9fb53a8e7eb6b6e49875052e571f784bafab387deb484e28f8a1ea38b`).

The default ruleset carries **222 rules** and declares `minVersion = "v8.25.0"`, consistent
with the pinned 8.30.1. The rule the drill exercises is real and the drill genuinely
exercises it: `github-pat` is `regex = ghp_[0-9a-zA-Z]{36}`, `entropy = 3`,
`keywords = ["ghp_"]`. The planted fixture assembles `ghp_` plus exactly 36 mixed
alphanumerics, so the positive result is a true regex+entropy match on the asserted
`RuleID`, not an incidental keyword hit. That is a sound positive test.

Four behaviours matter for any future gate and none is cured by the current evidence:

1. **Exit-code conflation.** Upstream default exit codes are `0` no leaks, `1` *leaks or
   error*, `126` unknown flag. Leak and failure are the same code by default. The drill
   correctly neutralised this with `--exit-code 42`, which is precisely why its
   malformed-config and missing-target probes are meaningful (both returned 1, distinct
   from 0 and 42). **This is an invocation-shape property, not a tool property**: a gate
   that omits `--exit-code` cannot distinguish "clean" from "crashed".
2. **Suppression surfaces, all on by default.** `gitleaks:allow` inline comments are
   honoured unless `--ignore-gitleaks-allow` is passed; `.gitleaksignore` is read from the
   default path `.`; `--baseline-path` suppresses every finding already present in a prior
   report. Any of the three, present in-repo, silently converts a real leak into a pass.
   None was drilled, and no row text addresses them.
3. **Default-off depth.** `--max-archive-depth` and `--max-decode-depth` both default to
   `0`: no archive traversal, no recursive decoding. A secret inside a base64 blob or a
   tarball is not found by a default invocation. The gitleaks drill note already lists this
   as not covered; it should be carried into the row as a standing capability limit, not
   just a drill gap.
4. **Default global allowlist is broad.** The shipped config globally excludes, among
   others, `node_modules/`, `vendor/`, lock files (`package-lock.json`, `yarn.lock`,
   `poetry.lock`, `Pipfile.lock`, …), `venv`/`lib/pythonX.Y` trees, `*.dist-info`, image,
   font and binary extensions, `.git`, and `gitleaks.toml` itself, plus regex and stopword
   allowlists. Defensible false-positive control, but it means "gitleaks passed" is never
   "every byte was examined."

Nothing in the ruleset or README showed behaviour hostile to the project's constraints: no
telemetry, no network dependency for `dir` scanning, no credential handling of its own.

## 4. Stage-4 evaluation — Ruff 0.16.9 behaviour and limits

Read upstream at tag `0.16.9`: `crates/ruff_linter/src/codes.rs`
(SHA-256 `1dc9c0716c4ab430618ff77d1d42adf67d9de78853501ccd3aae7d457f2bb8f3` as fetched),
`crates/ruff/src/args.rs`, `crates/ruff_workspace/src/options.rs`.

The `S` (flake8-bandit) family at 0.16.9 contains **73 rules**, S101 through S704.
`S608` is `HardcodedSQLExpression` — the rule the drill asserts. Ruff classifies rules as
Stable / Preview / Deprecated / Removed, and preview-gated rules are **not** activated by
`--select S` alone; the drill's observed S608 finding in stable mode therefore
empirically establishes that S608 is stable at this version, which is the fact that
matters. The corollary limit: the effective `S` set under `--select S` is both version-
and mode-dependent, so "S is selected" is not a stable statement of coverage across
upgrades.

Three behaviours matter for any future gate:

1. **`# noqa` is honoured by default.** `--ignore-noqa` disables it; `--add-noqa` can
   *insert* suppressions across a tree in bulk. For a security gate, in-tree `# noqa`
   comments are an uncontrolled suppression surface, and `--add-noqa` is a write mode that
   must never appear in a governed invocation.
2. **`respect-gitignore` defaults to `true`.** File discovery automatically excludes
   anything matched by `.gitignore`, `.ignore`, `.git/info/exclude`, or a global gitignore.
   Combined with the documented vacuous `rc 0` on an empty path set (the project's own
   lint/format drill, §7 row 1), a gate can pass by examining nothing.
3. **`--isolated` cuts both ways.** It is correct for a drill and wrong for a gate: the
   lint/format drill never exercised the repository's own configuration. I read that
   configuration directly instead (§1): two trivial keys across two files, no `extend`, no
   plugins, no excludes. The delta between drilled and real configuration is therefore
   small and read-only — a fact I rely on in §7.2 and would not extend to any future config
   that adds `extend`, plugins, `exclude`, or `per-file-ignores`.

Ruff reads only local configuration; no remote-config or network behaviour was found.

## 5. Adequacy of the stage-5 evidence

Both drills are genuinely synthetic, genuinely isolated, and honestly reported. Neither
touched the Veyro tree, Git index, or history. The gitleaks drill's credential-shaped value
is a runtime-assembled, explicitly-labelled `EXAMPLE_NOT_A_REAL_KEY` placeholder, redacted
at 100% and asserted absent from report and streams — fully compliant with
`.claude/rules/infra/secrets.md` control 1. No real secret, member data, paid service, or
Production action is involved anywhere in this evidence set. The non-vacuity assertions
(fixtures exist and are non-empty before any scan) are present in both drills, which is
better practice than most of this class of evidence.

Stage 5's two mandatory elements — a positive test and a negative test on synthetic
fixtures — are **satisfied for both capabilities**:

| | Positive | Negative | Fail-closed on malformed input |
|---|---|---|---|
| gitleaks | exit 42, 1 finding, `RuleID github-pat`, correct file, value redacted | clean companion → exit 0, zero findings | **yes** — malformed TOML config and missing target each return an exit that is neither 0 nor the leak code, with no findings |
| Ruff `S` | S608 on concatenated SQL, nonzero exit | parameterised companion → exit 0, empty findings | **not probed under `--select S`** |
| Ruff lint/format | F401+F841 rc 1; `format --check` rc 1 + 11-line diff | corrected counterparts rc 0; cross-checks prove each mode is blind to the other's concern | partially — empty path set (`rc 0`, vacuous) and missing path (`check` rc 1 / `format` rc 2) were probed and **disclosed as uncured limits**, not resolved |

Two honest observations about depth, neither of which is a policy failure: coverage is
1 of 222 gitleaks rules and 1 of 73 `S` rules. The policy requires *a* positive and *a*
negative test, not representative coverage, so this clears the bar — but it bounds what any
approval can mean, and §6/§7 bound it accordingly.

The one evidence defect that materially shapes both verdicts is not in the drills at all.
It is in the rows: **the artifact that was drilled is not the artifact that is pinned, and
in neither case is the artifact that was actually executed tied to upstream.** gitleaks ran
as a Homebrew darwin-arm64 build never compared to the upstream `darwin_arm64` asset; Ruff
ran as the pip-installed macOS build, while the pin captured is the *linux* wheel. The rows
disclose this plainly, to their credit. It is nonetheless the reason no scope that executes
either tool against Veyro files can be approved on this evidence without the cheap,
objective artifact-identity check named below.

## 6. Determination — CAP-009, gitleaks 8.30.1

### 6.1 Verdict

**APPROVED — BOUNDED.**

### 6.2 Approved scope (authoritative; supersedes the row's "drafted scope" wording)

Execution of gitleaks 8.30.1 in `dir` mode against disposable synthetic directories created
outside the Veyro repository (OS temp / pytest `tmp_path`), with the working directory also
outside the repository, `--redact=100`, an explicit **non-default** `--exit-code`, a JSON
report written to a temp path, and an asserted `gitleaks version` of exactly `8.30.1`.
Read-only, no network, synthetic fixtures only, no credential-shaped value that is not an
explicitly-labelled placeholder. Supply-chain basis: MIT licence independently verified;
upstream release, tag→commit and linux-asset digest independently reproduced; rollback
target (withdraw row + manifest binding) stated and credible, since no workflow, gate, or
scenario depends on CAP-009 today — independently confirmed: **no file under
`.github/workflows/` references gitleaks**.

### 6.3 Expressly NOT approved — remains PENDING, not merely unmentioned

Any scan of the Veyro working tree, Git index, or Git history (`gitleaks git`, `--staged`);
any CI execution; any baseline-file use; any archive/decode-depth expansion; and any
GOV-01-R03/R04 gate, scenario, or required-status reliance. This determination **does not**
unlock that scope, and the row's current sentence making it unlock automatically on approval
must be corrected (§8.1).

Unsatisfied mandatory criteria for that broader scope, each with its minimal correction:

1. **Executed-artifact provenance (policy `provenance`/`content_hash`, for the artifact that
   actually runs).** *Correction:* extract the upstream `gitleaks_8.30.1_darwin_arm64.tar.gz`
   in a disposable directory and show the contained binary equals the local
   `052d1882…c771422`, or install and execute the pinned
   `gitleaks_8.30.1_linux_x64.tar.gz` (`551f6fc8…2470eb`) by hash. Because the release is
   **not immutable**, the install step must verify the digest at install time and fail
   closed on mismatch — a recorded pin alone is not enforcement.
2. **No evidence for the invocation shape the gate would use (stage 5, for that scope).**
   *Correction:* one synthetic drill covering the three suppression surfaces — a planted
   secret with a `gitleaks:allow` comment, one listed in a `.gitleaksignore`, and one
   present in a `--baseline-path` report — each shown to be suppressed by default and
   **still detected** under the chosen governed flags; plus an asserted files-scanned count
   greater than zero, so an empty or fully-allowlisted target cannot pass vacuously.
3. **Scope not stated for the role being requested (policy stage 7 `scope`).**
   *Correction:* state the governed invocation explicitly — mode, non-default exit code,
   redaction, suppression-surface handling, non-vacuity assertion, and where findings output
   may be written — before, not after, the first real-tree run.

Items 1–3 require a new synthetic drill and fresh judgment, so expanding CAP-009 needs a
further determination. It does **not** require re-doing anything already done here.

### 6.4 Registry fields this determination sets

`approved_by`: `veyro-security-reviewer (Opus, claude-opus-5), fresh context, M1-C-06
capability-security determination` — this file. `approved_date`: 2026-10-09.
`next_review_due`: **2027-04-09** (six months; a secret-scanner's rule set ages against new
credential formats). Any version bump re-triggers stages 4–5 independently, per policy
stage 9. `lifecycle_status`: `ACTIVE — bounded to §6.2 only`.

## 7. Determination — CAP-010, Ruff 0.16.9

### 7.1 Verdict

**APPROVED — BOUNDED**, with one extension that takes effect only on an objective,
mechanically-checkable condition (§7.2). This is a verdict distinct from CAP-009's; neither
carries the other.

### 7.2 Approved scope (authoritative)

**(a) Unconditional.** `ruff check` and `ruff format --check` / `--diff` with
`--isolated --no-cache` against disposable synthetic files created outside the Veyro
repository. Read-only; no write mode.

**(b) Conditional extension — local, read-only, non-gate lint/format over Veyro Python.**
`ruff check` and `ruff format --check` / `--diff` only, run locally by the project's own
verification loop against Veyro Python files under the committed configuration
(`ruff.toml`, `backend/pyproject.toml` as read in §1). This extension takes effect **only**
once the following is recorded as evidence, and not before:

> **Condition C10-1 (artifact identity).** The installed Ruff distribution is shown to
> derive from the PyPI wheel for its host platform — for the current macOS arm64 host,
> `ruff-0.16.9-py3-none-macosx_11_0_arm64.whl` SHA-256
> `1632eb1d6197f33bd00b1acbc5b71009e89a8895c158e2d2b03a834fac964ab6`. Either acceptable
> method is mechanical and needs no judgment: download that wheel to a disposable
> directory, confirm the digest, and show the installed distribution's `RECORD` file
> digests match the wheel's contents; or reinstall Ruff from the hash-verified wheel. **If
> the comparison does not match, this extension does not take effect and the mismatch is a
> `BLOCKED` condition requiring a new determination** — it would mean the executing binary
> has unestablished origin.

The condition is objective and its expected value was established independently in §2, which
is why satisfying it needs no further security judgment. Grounds for granting (b) at all:
the mode is read-only and non-mutating, its output is advisory rather than a control, the
repository configuration was read first-hand and is two trivial keys with no `extend`,
plugin, exclude, or per-file-ignore surface, and the behaviour is evidenced by an 11/11
drill on the same binary family.

**Permanently excluded from (a) and (b), in every mode:** `--fix`, `--unsafe-fixes`,
in-place `ruff format` (without `--check`/`--diff`), and `--add-noqa`. The first three
mutate source; the last mass-manufactures suppressions.

### 7.3 Practical consequence, stated plainly

Until C10-1 is recorded, the project's habitual `backend/.venv/bin/ruff check` /
`ruff format --check` over real files — visible throughout
`M1-C-06-R03-SOURCE-BOUNDARY-2026-10-09.md`'s replay tables — remains outside approved
scope and continues to belong to BUG-057. I considered waiving this, since the exposure is
unchanged by approval and the loop is ordinary engineering hygiene. I declined to, for one
reason: the verification that closes it is a single hash comparison whose expected value is
already written above. Waiving a check that cheap is precisely the precedent this project
has had to correct before.

### 7.4 Expressly NOT approved — remains PENDING

`--select S` (or any `S`-inclusive selection) against **any** Veyro file — the SAST role
itself; any CI execution of Ruff in any mode; any GOV-01-R03/R04 gate, scenario, or
required-status reliance, including SCN-MOD001-134; and continued reliance under any future
configuration that introduces `extend`, plugins, `exclude`, or `per-file-ignores`, each of
which is a stage-9 material change.

Unsatisfied mandatory criteria for the SAST/gate role, with minimal corrections:

1. **No evidence under the configuration and target set a gate would use (stage 5).**
   *Correction:* a synthetic drill under the repository's real configuration rather than
   `--isolated`, asserting a files-checked count greater than zero (closing the documented
   vacuous `rc 0`), distinguishing `rc 2` I/O error from `rc 1` findings, and demonstrating
   that an in-fixture `# noqa: S608` suppresses by default and is defeated by the governed
   flag set.
2. **CI artifact never executed (stage 5 for the CI role).** *Correction:* install the
   pinned linux wheel `a21713e6…bc728` by hash in the CI job and record the drill there;
   the pin as recorded today is not enforced anywhere.
3. **Scope not stated for the role being requested (stage 7 `scope`).** *Correction:* state
   the governed `S` invocation — selection, target set, non-vacuity assertion, exit-code
   contract, suppression-surface handling — before the first real-tree `S` run.
4. **Standing capability limit to carry in the row, not a defect:** Ruff `S` is pattern-based,
   not taint analysis, and its stable rule set is version-dependent (§4). An `S`-clean tree
   is not an absence of injection defects, and must never be reported as one.

### 7.5 Registry fields this determination sets

`approved_by`: as §6.4, this file. `approved_date`: 2026-10-09. `next_review_due`:
**2027-04-09**. `lifecycle_status`: `ACTIVE — bounded to §7.2(a); §7.2(b) inactive until
C10-1 is recorded`.

## 8. Exact corrections required of the sole writer (prescribed, not applied)

This reviewer modified nothing. The following must accompany any status flip.

**8.1 Delete the self-authorising sentence in both rows.** Each row currently reads, in
substance, "Not authorised until an independent Opus determination returns APPROVED: [real
tree / Git history / CI]." Left standing beside an `APPROVED` status, that sentence
*grants* the very scope this determination withholds. Replace it in both rows with the
approved scope from §6.2 / §7.2 and an explicit "this determination does not authorise
real-tree, Git-history, or CI use."

**8.2 Put the restriction where a future session will read it.** `validate_capabilities.py`
checks only that `review_status` begins with `APPROVED`, that `approved_by` is named, and
that `next_review_due` parses — **it does not check scope adherence at all** (verified by
reading its output this session). The bound is therefore prose-enforced only, and must
appear in the registry `scope` cell *and* the manifest `used_for` / `required_status` cells,
not solely in this report. Suggested status strings, which satisfy the validator's
prefix check while resisting over-reading:

- CAP-009: `APPROVED (BOUNDED) 2026-10-09 — synthetic-fixture drill scope only; real-tree / Git index / history / CI NOT approved`
- CAP-010: `APPROVED (BOUNDED) 2026-10-09 — synthetic drill scope; local read-only lint/format conditional on C10-1; S role and all CI use NOT approved`

**8.3 Carry the newly-established facts into the rows**: gitleaks' default exit-code
conflation, its three default-on suppression surfaces, default-zero archive/decode depth,
and the breadth of its default global allowlist (§3); Ruff's default-honoured `# noqa`,
`respect-gitignore = true`, and version-dependent stable `S` set (§4); and the correction
that Ruff 0.16.9 publishes **no** PyPI attestation (404), which is a different state from
"attestation unverified" (§2).

**8.4 Expected validator movement.** `validate_capabilities.py` currently reports **12**
errors — three each for CAP-009, CAP-010, CAP-011, CAP-012. Completing CAP-009 and CAP-010
should leave exactly **6**, all belonging to CAP-011 and CAP-012, which are outside this
determination's charge and keep their own fail-closed hold. Any other post-edit count means
something else changed and should be investigated, not accepted.

**8.5 BUG-057 stays OPEN.** Nothing here retroactively authorises the historical
`gitleaks git --staged` run on real staged files or habitual real-tree Ruff use. Its
closure dependency 1 is now satisfied for CAP-009 and CAP-010 — an individual verdict
exists for each — while dependency 2 (real-tree/CI use) is satisfied for neither.

## 9. What this determination does not establish

It is a capability-security verdict and nothing else. It infers **no** CI result, **no**
scenario PASS, **no** gate closure, and **no** module progress. SCN-MOD001-029, 094, 134,
135, 136 and all 13 M1-C-06 scenarios remain NOT EXECUTED. No GOV-01-R03 or GOV-01-R04
acceptance criterion is closed. M1-C-05's scanner execution remains blocked by the absence
of approved real-tree scanning, which §6.3 and §7.4 withhold — approval of the bounded
scopes does not move C05, and no reader should treat it as doing so. No layer-3 "runs in
CI" authorisation or layer-4 branch-protection authority is created, implied, or affected.
MOD-001 exit remains unchanged; W5 remains 0/2. No review entitlement is created or
consumed beyond the single `M1-C-06-CAP-ASSURANCE` action this file discharges; no gate-3
or SCN-070 entitlement was read from, written to, or relied upon. CAP-011 (pytest) and
CAP-012 (mypy) were deliberately **not** adjudicated — they are outside this charge and
their verdicts must not be inferred from the two rendered here.

## 10. Residual risks accepted by the bounded approvals

Accepted, because the approved scopes touch no Veyro file and no gate: the executed
artifacts' origins remain untied to upstream for gitleaks' Homebrew binary (and, until
C10-1, for the installed Ruff); neither project's release is cryptographically signed, and
both tools' provenance chains terminate at GitHub/PyPI, so a platform-level compromise is
not detected by the checksum agreement recorded here; rule-behaviour evidence is one rule
deep per tool; and the gitleaks release being mutable means its pin must be re-verified at
install time rather than trusted as historical fact.

Not accepted, and therefore withheld rather than disclosed: everything in §6.3 and §7.4.

---

*No second reviewer is required or implied by this file. One fresh-context Opus
determination, two separate verdicts, as the ordering decision specified.*
