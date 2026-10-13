---
doc: M1-C-06 — INDEPENDENT CAP REAL-TREE/CI SCOPE-EXTENSION DETERMINATION (CAP-009 gitleaks 8.30.1, CAP-010 Ruff 0.16.9)
module: MOD-001
requirement: GOV-01-R03 (SAST/secret-scanning role), CAPABILITY_POLICY.md stages 4–5 (re-evaluation of a scope change) + stage 7 `scope`
date: 2026-10-09 (UTC 14:59)
reviewer: veyro-security-reviewer — fresh context, Opus tier. Second, independent determination; a different session from the 2026-10-09T14:25Z determination it adjudicates against. Did not implement, drill, draft, register, author, or execute any part of CAP-009/CAP-010, the governed-shape tests, the identity note, or the CI workflow.
model_proof: §1.2 (self-attested; harness-declared identity `claude-opus-5`. No orchestrator-side runtime attestation is embedded in this file — see §1.2 for the exact limit.)
verdict_cap_009: BLOCKED — real-tree / Git index / Git history / CI scope extension NOT granted. Prior synthetic-only bounded approval unchanged and still unrecorded in the registry.
verdict_cap_010: BLOCKED — real-tree `--select S` (SAST) and CI-gate scope extension NOT granted. Separately: the prior determination's §7.2(b) condition C10-1 is independently verified SATISFIED, which activates the already-granted local read-only lint/format extension; that is not a new extension and is not a SAST or CI authorisation.
scope: review-only. This file is the only file written. No source, test, workflow, registry row, manifest, scenario status, plan, control state, `REVIEW_IN_FLIGHT.md`, or remote ref was modified. Neither gitleaks nor Ruff was executed in this session, in any mode, against any file.
---

# M1-C-06 — independent CAP real-tree/CI scope-extension determination

## 1. Charge, identity, independence

### 1.1 Charge

A single bounded outcome: a `CAPABILITY_POLICY.md` stage-4/5 **scope-extension**
verdict, rendered **separately** for CAP-009 (gitleaks 8.30.1, secret-scanning
role) and CAP-010 (Ruff 0.16.9, SAST/CI role), on the correction evidence produced
after the 2026-10-09T14:25Z determination. The question is narrow and specific:
does that correction evidence now support extending either capability from the
synthetic-fixture-only scope it already holds to **real-tree and/or CI** scope.

Deliberately not done, per charge: no implementation; no scan of the Veyro working
tree, Git index, or Git history; neither scanner run against any real project file;
no registry or manifest edit; no R03 scenario disposition; no review of CAP-011
(pytest) or CAP-012 (mypy); no reopening of R04 gate-2, gate-3, or SCN-070. This
file is a judgment, not a product edit.

`REVIEW_IN_FLIGHT.md` (read at session start) carried the matching claim before this
review began — `IN_FLIGHT — MOD-001 M1-C-06 CAP-009/CAP-010 real-tree/CI
scope-extension mandatory independent review, claimed by sole runner operation
9a911340-552c-4eeb-9f55-ead37aac0d68, dispatched 2026-10-09T14:53:07.738421+00:00.
Expected reviewer: fresh veyro-security-reviewer/Opus via guarded ACPX.` That
claim names this review and this reviewer role. This session did not write, clear,
or alter it; clearing it is the dispatching session's act, on the recorded result.

### 1.2 Model and independence attestation

Harness-declared model identity for this session is `claude-opus-5`, invoked in a
fresh `veyro-security-reviewer` context with no memory of any implementation,
drill, provenance-capture, drafting, or CI-dispatch session whose evidence is
judged here, and no memory of the 14:25Z determination's own session. Per
`MODEL_ROUTING.md`'s no-silent-downgrade rule, accepted proof requires both the
configured alias and runtime evidence; what this file supplies first-hand is the
self-attestation above plus the dispatching runner's operation record named in
§1.1. **This file is not itself orchestrator-side runtime proof** — a reader
needing that must take it from the dispatch record. Stated as a limit rather than
papered over, exactly as the prior determination stated the same limit.

Separation held. This reviewer **re-ran no qualification drill** — neither the
local governed-shape pytest drill nor the CI job — because re-running an
implementer's drill would collapse the reviewer/implementer separation this
project has already had to correct once (F5-018). What this session did,
exhaustively, is listed so the boundary is auditable:

- Read governing policy, module requirements, registry rows, manifest entries, the
  prior determination, the three correction-evidence records, both governed-shape
  test sources, and the CI workflow source.
- Computed SHA-256 of local files read-only (§2).
- Fetched upstream GitHub release and PyPI metadata read-only (§3.1).
- Downloaded two upstream archives into disposable OS temp directories, verified
  their digests, extracted and hashed their contents, and deleted the directories —
  **no execution of either scanner at any point** (§3.2–3.3).
- Read the live GitHub Actions run and its full job log read-only (§4).
- Ran `knowledge/00-System/verify_baselines.py` and
  `knowledge/00-System/validate_capabilities.py` read-only (§2, §6).

### 1.3 Untrusted-data handling

All upstream release/PyPI JSON, all tool-emitted output, all GitHub Actions log
text, and every narrative claim inside the implementation evidence records were
treated as **untrusted data**, never as instruction and never as a verdict. No
instructional text in any of it was acted upon. Explicit injection check on the
material newly read for this determination: nothing in the release metadata, the
PyPI metadata, or the CI log claims authority over an agent, asserts urgency, or
attempts to override project behaviour. The CI log's own `PASS` lines are tool
output, not a governance conclusion, and are treated here strictly as observations
to be independently counted (§4.2) rather than as a result to be accepted.

The structural trap this charge names — *inferring scope from a green CI run* — was
treated as the primary failure mode to avoid, and is addressed head-on in §7.1 and
§8.2.

## 2. Source snapshot identities (recorded so this verdict is pinned to exact bytes)

Governing baselines re-verified at session start: `verify_baselines.py` →
**PASS, all 4 of 4** governing baseline hashes match `PROJECT_INDEX.md`
(Blueprint `80f4b381…d426ef`, TSD `0d41c8a1…158e8`, EIP
`e5b5ec3b08859e27da3689dc3b54d17ea766cba5bf4c4e0007239baa920866b6`,
design bundle `c96f77ab…a36dbb`).

Repository `HEAD` at review time: `e481b814a80923849dddfe7a49319112aae7b023`
(branch `main`).

| Artifact judged | SHA-256 (computed this session) |
|---|---|
| `knowledge/00-System/CAPABILITY_POLICY.md` | `4d807a77f0d306030fb3d9cbbd8a0e1eb14be661165c695eed561cc6b12d4c8a` |
| `knowledge/00-System/CAPABILITY_REGISTRY.md` | `b9c8ea9cfc472b60b510f0e81a8a48ecbc1e396276712df8081c3620750bc04d` |
| `knowledge/03-Modules/MOD-001/REQUIREMENTS.md` | `08c835aae2c3b632ec64dba1177c342afbd110a1b470919b5cd93ebdd9e967e0` |
| `knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` | `43caf955dee7dcc5facc1d84470376ab1766742ee86356affa9bdae1701ba05c` |
| prior determination `…/security/M1-C-06-CAPABILITY-SECURITY-DETERMINATION-2026-10-09.md` | `1d9a9102858b9e281ae1dedcb3c92769b3f42ddd5486874276cae991ad9e215a` |
| `…/implementation/M1-C-06-EXECUTED-ARTIFACT-IDENTITY-2026-10-09.md` | `a931483bfb4d25460194e530952c2048eaf2b047dcf1bea71feedc3a8ba5cb7b` |
| `…/implementation/M1-C-06-GOVERNED-SHAPE-SYNTHETIC-QUALIFICATION-2026-10-09.md` | `165bff856d3ef9935dc2db2a91fae8863292a58f785df45a3af49983e0a4b54d` |
| `…/implementation/M1-C-06-LINUX-SYNTHETIC-CI-LIVE-2026-10-09.md` | `89032400b65036f69aa586b6bfbcb64ed2b94a8596d6c29c74caf428c59b84a8` |
| `tools/tests/test_gitleaks_governed_qualification.py` | `cb82662f75bb9327408e6a1d0d7deb4d7f1390055d3199f1c154557b0f8a5725` |
| `tools/tests/test_ruff_s608_governed_qualification.py` | `0d431e3a0b368acf88be25557c373b6f9a12fe705e0cfec9a67aaf7dfbef35fe` |
| `.github/workflows/c06-synthetic-scanner-qualification.yml` | `1de2c02455724aef94ce3f06f6aaf357de3782bb6a681a2787993269a5016c1c` |
| `ruff.toml` | `81c6492e759cb6a3a622e29d7996de6fb8f590190110b36ad993bf2b534c9743` |
| `backend/pyproject.toml` | `039332c96ab93d82de930d1c84e3351a160829604126868da3a2a8fdfdd40695` |

**Both governed-shape test-file hashes equal the figures the governed-shape
evidence record states** (`cb82662f…a5725`, `0d431e3a…f35fe`) — the judged sources
are the recorded sources, unmodified.

**Material snapshot fact, load-bearing below:** the entire `.github/` tree is
**untracked** in the authoritative repository (`git status --porcelain .github` →
`?? .github/`; `git ls-files .github` → empty). The CI workflow judged here exists
in the governing repo only as an uncommitted working-tree file; it was committed
solely to the disposable fork branch. See §5.3 and §9.

## 3. First-hand provenance verification (re-derived, not inherited)

Nothing in this section is taken from the implementation evidence or from the prior
determination. Each figure was obtained independently this session.

### 3.1 Upstream metadata, read-only

| Claim under test | Independent result |
|---|---|
| gitleaks `gitleaks_8.30.1_linux_x64.tar.gz` digest/size | release API `sha256:551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`, 8230402 bytes — **matches** the workflow pin and the registry pin |
| gitleaks `gitleaks_8.30.1_darwin_arm64.tar.gz` digest/size | release API `sha256:b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5`, 7897593 bytes — **matches** the identity note's download pin |
| gitleaks release mutability | `draft: false`, `prerelease: false`, **`immutable: false`** — **re-confirmed today.** The release remains mutable; a recorded pin is therefore not enforcement, and install-time digest verification is mandatory on every run |
| Ruff linux wheel pin | PyPI `ruff-0.16.9-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`, `a21713e629d3e5bdb2f5c2def1cc7f04f47fa8e1a7eb0571b4a28e1da64bc728`, 10406494 bytes — **matches** the workflow pin |
| Ruff macOS wheel pin (C10-1's expected value) | PyPI `ruff-0.16.9-py3-none-macosx_11_0_arm64.whl`, `1632eb1d6197f33bd00b1acbc5b71009e89a8895c158e2d2b03a834fac964ab6`, 9892940 bytes — **matches** the prior determination §2's independently-established figure |

Inherited, **not** re-verified by this reviewer and flagged as such: the prior
determination's §2 finding that the PyPI integrity/provenance endpoint returns HTTP
404 for the Ruff 0.16.9 linux wheel (no attestation *published*, as distinct from
*unverified*). I did not re-query that endpoint; the distinction it draws still
belongs in the registry row per the prior §8.3.

### 3.2 gitleaks executed-artifact identity — the Homebrew mismatch is CONFIRMED, not cured

Performed in a disposable OS temp directory, deleted afterward; the archive was
downloaded, digest-verified, extracted and hashed. **The binary was never executed.**

| Object | SHA-256 (this session) |
|---|---|
| upstream `gitleaks_8.30.1_darwin_arm64.tar.gz` | digest check **OK** against `b40ab0ae…aeb6a5` |
| binary contained in that archive | `ba52fb1bfabbcde42f032afad3d6e0b19dff8ed105229a16e7caa338bbc0e84f` |
| `/opt/homebrew/bin/gitleaks` | `052d18829513f92eb683b63cd15b34d845f9a7adec761fe26cd462eb3c771422` |
| `/opt/homebrew/Cellar/gitleaks/8.30.1/bin/gitleaks` | `052d18829513f92eb683b63cd15b34d845f9a7adec761fe26cd462eb3c771422` |

**The Homebrew executable is definitively not the upstream artifact.** The identity
note's "Mismatch" conclusion is accurate and is now independently re-derived. The
charge's standing instruction holds with full force: any eligible broader scope must
bind to the **hash-verified upstream artifact** — the Linux tarball `551f6fc8…2470eb`
or the darwin-contained binary `ba52fb1b…bc0e84f` — and may **never** assume local
Homebrew identity. The local governed-shape drill correctly enforces exactly this by
pinning `ba52fb1b…bc0e84f` and failing closed otherwise (its own record documents
the Homebrew binary producing `7 failed`).

### 3.3 Ruff condition C10-1 — independently verified SATISFIED

C10-1 is a single mechanical hash comparison whose expected value the prior
determination fixed in advance. I performed it first-hand rather than accepting the
identity note's result: the macOS arm64 wheel was downloaded to a disposable temp
directory, its digest verified **OK** against `1632eb1d…64ab6a`, and the contained
`ruff-0.16.9.data/scripts/ruff` entry read and hashed.

| Object | SHA-256 (this session) |
|---|---|
| wheel-contained `ruff-0.16.9.data/scripts/ruff` (21698768 bytes) | `8b799e53434b026a3e80aef658c06c3c98f9fb4cfc4eae379a16313936509e57` |
| installed `backend/.venv/bin/ruff` | `8b799e53434b026a3e80aef658c06c3c98f9fb4cfc4eae379a16313936509e57` |

**Equal.** The executing Ruff binary on this host derives from the hash-verified
PyPI wheel for its platform. **C10-1 is satisfied**, on this reviewer's own
arithmetic, for the current macOS arm64 host. Its consequence is confined in §8.1:
it activates an extension the prior determination already granted, and it is neither
a SAST authorisation nor a CI authorisation.

### 3.4 §7.2 configuration premise — re-verified directly

Read first-hand at the hashes in §2: `ruff.toml` contains exactly one key
(`line-length = 100`); `backend/pyproject.toml` `[tool.ruff]` contains exactly
`line-length` and `target-version`. No `select`, `extend`, plugin, `exclude`, or
`per-file-ignores` key exists in either. The prior determination's §7.2 premise
holds at this snapshot, and both drills' own config-key guard asserts the same
invariant — correctly, since that premise is what makes `--config <repo file>`
a faithful stand-in for "the repository configuration."

## 4. The CI evidence, independently read

### 4.1 What the workflow actually does (read from source, not from its own summary)

`c06-synthetic-scanner-qualification.yml` (hash in §2) triggers only on push to
`ci/c06-qual-20261009`, declares `permissions: contents: read`, and contains **no
`uses:` line and no `secrets.` reference** — verified by direct grep of the file.
`.claude/rules/infra/iac.md` control 5 (every `uses:` SHA-pinned *and* carrying an
`APPROVED` `CAP-<NNN>` row) is therefore satisfied by abstention for this workflow.
I did **not** adjudicate any other workflow file in `.github/workflows/`; they are
outside this charge.

Its four substantive steps: a tokenless sparse `git fetch` of the exact push SHA
supplying only `ruff.toml` and `backend/pyproject.toml` (with ref, 40-hex-SHA,
checkout-SHA, and regular-file/non-symlink assertions, each `exit 1` on failure under
`set -euo pipefail`); `curl` of the two pinned Linux artifacts with
`sha256sum -c -` **before** extraction and asserted `gitleaks version` / `ruff
--version`; then two synthetic drills whose every target is generated under
`RUNNER_TEMP`.

Two properties I verified in the source and consider decisive:

1. **The two repository config files are consumed via `--config` only, never as a
   scan target.** The Ruff drill's targets are all `tempfile.mkdtemp(dir=RUNNER_TEMP)`
   trees.
2. **Both CI wrappers structurally refuse checkout paths.** The gitleaks wrapper
   raises `Refused("target inside checkout")` and the Ruff wrapper raises
   `Refused("path inside checkout")` whenever `RUNNER_TEMP/head` is the path or an
   ancestor. The job therefore **cannot** have scanned a Veyro file, by construction
   — which is correct for a synthetic drill and is also precisely why it establishes
   nothing about real-tree scanning (§7.1).

### 4.2 The live run, read-only

Run `37946867580` and job `113875289239` on `veyro-labs/Veyro` are live-accessible
and were read read-only. Both concluded **success**, 11s job duration, push event.
Independently counted from the full job log:

- **33 emitted `PASS` result lines; 0 emitted `FAIL` result lines.** (A naive grep
  returns 35/2; two of those hits are the echoed script line
  `print(("PASS " if ok else "FAIL ") + name)` inside the heredoc, carrying terminal
  escape sequences. Excluding echoed source yields exactly 33 and 0 — so the
  evidence record's "33 `PASS`, zero `FAIL`" claim is **accurate**, and the arithmetic
  is now independently reproduced rather than accepted.)
- `failures: 0` emitted by **each** of the two drills (log lines 239 and 388).
- `gitleaks.tar.gz: OK`, `ruff.whl: OK`, `artifacts verified and versions asserted`,
  and `pinned sha: f684831372af4e9f25da37ab2e420857e0a122a8` — install-time digest
  verification genuinely executed, before extraction, against the digests I
  independently re-derived in §3.1.
- **The synthetic placeholder token appears nowhere in the log** (zero occurrences of
  the fixture value). `--redact=100` plus the drill's own "finding secret is fully
  redacted" assertion held in the live environment. `.claude/rules/infra/secrets.md`
  control 1 is satisfied: the value is a runtime-assembled, explicitly-labelled
  `EXAMPLE_NOT_A_REAL_KEY` placeholder, not a plausible real-shaped credential.
- Both Ruff configs are exercised as parametrized cases (`[head/ruff.toml]` and
  `[backend/pyproject.toml]` tags on 9 checks each, including the config-key guard).

**Conclusion of this section:** the Linux CI drill is real, it executed the pinned
Linux artifacts under verified digests, it passed, and its payload was entirely
synthetic. All three of those facts are now first-hand. None of them is an
authorisation; §7 explains why.

## 5. Are the prior §§6.3 / 7.4 named corrections actually satisfied?

The charge requires this stated explicitly, item by item. "Satisfied" below means
the named minimal correction was actually performed, not merely addressed.

### 5.1 CAP-009 — prior §6.3 items

| Prior item | Named minimal correction | Status |
|---|---|---|
| **1. Executed-artifact provenance** | show the upstream darwin archive's contents equal the local Homebrew binary, **or** install and execute the pinned `gitleaks_8.30.1_linux_x64.tar.gz` by hash with install-time verification failing closed | **SATISFIED — via the second branch only.** The first branch was attempted and **failed**: Homebrew `052d1882…` ≠ upstream-contained `ba52fb1b…` (§3.2, re-derived). The second branch was performed in CI and verified by me (§4.2): digest checked before extraction, version asserted, `set -euo pipefail` failing closed, against a release I re-confirmed is still mutable. **Satisfied for the pinned Linux artifact executed in CI. NOT satisfied for any local macOS execution** — the only hash-established local artifact is the extracted upstream darwin binary, which is not the binary on `PATH`. |
| **2. Gate-shape stage-5 evidence** | one drill covering the three suppression surfaces (inline `gitleaks:allow`, `.gitleaksignore`, `--baseline-path`), each shown suppressed by default and **still detected** under the governed flags; **plus an asserted files-scanned count greater than zero, so an empty or fully-allowlisted target cannot pass vacuously** | **PARTIALLY SATISFIED.** Suppression half: fully satisfied, locally and in CI, each surface with an unsuppressed control proving the fixture is a genuine detection — and a *fourth* surface was honestly discovered (a target-root `.gitleaksignore` is defeated by no flag, so the wrapper refuses rather than passes). Non-vacuity half: **not satisfied as written.** gitleaks emits no scanned-file count, so the drill substitutes a wrapper-side pre-check (target is a directory holding ≥1 non-empty file). That closes the *empty* case and leaves the **fully-allowlisted** case — the clause's second, explicitly-named half — untouched. See §5.2. |
| **3. Scope stated for the requested role** | state the governed invocation — mode, non-default exit code, redaction, suppression handling, non-vacuity assertion, findings-output location — **before** the first real-tree run | **NOT SATISFIED for the real-tree role.** A complete governed invocation *is* stated, and it is a good one. But it is a **synthetic-target** shape by construction: both the local wrapper (`REPO_ROOT == path or REPO_ROOT in path.parents → GovernedScanRefused`) and the CI wrapper refuse any repository/checkout path. No governed invocation whose target is a Veyro path has been stated, and none could be executed by the qualified wrappers. Separately, `gitleaks git` / `--staged` — the mode a repository secret-scanning gate normally uses, and the mode BUG-057's disclosed historical use involved — has **no evidence in any record, in any environment**; only `dir` mode exists. |

### 5.2 The allowlist non-vacuity gap, stated concretely

This is the one substantive new finding of this determination, and it is the reason
§5.1 item 2 cannot be read as closed.

The prior determination §3 item 4 established that the shipped default ruleset
globally excludes, among others, `node_modules/`, `vendor/`, lock files
(`package-lock.json`, `yarn.lock`, `poetry.lock`, `Pipfile.lock`, …),
`venv`/`lib/pythonX.Y` trees, `*.dist-info`, image/font/binary extensions, `.git`,
and `gitleaks.toml` itself, plus regex and stopword allowlists — hence its own
warning that "gitleaks passed" is never "every byte was examined." §6.3 item 2 then
required the non-vacuity assertion to cover a **fully-allowlisted** target, not only
an empty one.

The wrapper's actual check is `[p for p in target.rglob("*") if p.is_file() and
p.stat().st_size > 0]`. A target consisting **entirely** of globally-allowlisted
paths passes that check and then returns rc 0 with zero findings — a vacuous pass
produced by the allowlist rather than by emptiness, and indistinguishable at the exit
code from a genuinely clean scan. **No drill, local or in CI, exercises the global
allowlist at all.**

This is not hypothetical for the target that matters. The Veyro working tree contains
exactly the path species the default allowlist excludes — `backend/.venv/`,
`.mypy_cache/`, `*.lock` files, `.git` — so a real-tree `dir` scan reporting
"0 findings" would carry an unquantified exclusion set, and the governed shape has no
assertion that separates "examined and clean" from "excluded and therefore silent."
Closing this needs one cheap synthetic case, not a redesign (§10.1).

### 5.3 CAP-010 — prior §7.4 items

| Prior item | Named minimal correction | Status |
|---|---|---|
| **1. Evidence under the real configuration** | a synthetic drill under the repository's real configuration rather than `--isolated`, asserting files-checked > 0, distinguishing rc 2 (I/O/config error) from rc 1 (findings), and showing an in-fixture `# noqa: S608` suppresses by default and is defeated by the governed flag set | **SATISFIED**, and done well. `--isolated` dropped; both repo configs supplied via `--config` and parametrized; non-vacuity enforced by a `--show-files` pre-check requiring a non-empty file list *and* that every explicit target yield at least one checked file; `rc 2` vs `rc 1` asserted distinct; `# noqa: S608` shown rc 0 by default and `S608` at rc 1 under `--ignore-noqa`; `respect-gitignore` discovery behaviour probed; `invalid-syntax` disambiguated from `S608`. Verified live in CI for both configs (§4.2). One residual, below. |
| **2. CI artifact never executed** | install the pinned linux wheel `a21713e6…bc728` by hash in the CI job and record the drill there | **SATISFIED.** Verified live (§4.2): wheel digest OK before extraction, script extracted from the verified zip with `python3 -I`, `ruff 0.16.9` asserted, drill executed under both real configs. I independently re-derived the PyPI digest and size (§3.1). |
| **3. Scope stated for the requested role** | state the governed `S` invocation — selection, target set, non-vacuity assertion, exit-code contract, suppression handling — **before** the first real-tree `S` run | **PARTIALLY SATISFIED.** Selection, non-vacuity mechanism, exit-code contract and suppression handling are all stated and drilled. The **target set is not stated**, and — as with CAP-009 — both qualified wrappers refuse any path inside the repository/checkout by construction. No `S` run against any Veyro path has occurred or been specified. |
| **4. Standing capability limit to carry in the row** | record that Ruff `S` is pattern-based, not taint analysis, and its stable `S` set is version-dependent | **NOT SATISFIED** — a documentation action for the sole writer; the CAP-010 registry row is unchanged at the snapshot hash in §2. |

**Residual on item 1 (condition, not a blocker):** the wrapper's per-target
assertion requires only that *some* checked file lie under each explicit target. For
a **directory** target containing a mix of tracked and gitignored `.py` files, the
ignored ones are silently skipped while the wrapper still passes — partial vacuity,
not total. For a real-tree gate this must be tightened to an enumerated expected
file count (the same discipline CAP-012's drafted scope already imposes with its
"`Success: no issues found in N source files` where N equals the expected count"
rule), or to explicit file lists rather than directory targets.

**Structural condition applying to both capabilities:** every fail-closed property
that makes these shapes safe — non-vacuity, root-`.gitleaksignore` refusal,
no-baseline, repo-path exclusion, per-target coverage — is **wrapper-side, not
tool-side**. The governed-shape record says so itself: the wrapper "exists only in
these tests, not as a committed gate tool." Today those wrappers live in two pytest
files and in heredocs inside a workflow that is **untracked in the authoritative
repository** (§2). A CI gate invoking the bare flag lists without that wrapper would
silently lose every one of those properties, and `.claude/rules/infra/iac.md` control
1 requires any `.github/workflows/**` change to land as a reviewed commit before it
takes effect anywhere — which the judged workflow, having executed on a disposable
fork branch while uncommitted and unreviewed in the governing repo, did not do. This
post-hoc review is the available remedy for the drill; it is not a precedent for a
gate.

## 6. Control-plane state: the prior bounded approval is not recorded anywhere

Verified read-only this session. `validate_capabilities.py` reports **FAIL — 12
errors**, three each for CAP-009, CAP-010, CAP-011, CAP-012. For CAP-009 and
CAP-010 the errors are `CAPABILITY_NOT_APPROVED` (review_status begins
`**QUALIFIED — NOT APPROVED…`), `APPROVED with no named approved_by`, and an
unparseable `next_review_due` (`NOT SET — assigned by the independent
determination`). The CAP-009/CAP-010 registry rows and both
`module-capabilities.yaml` entries still read `QUALIFIED`, `approved_by` empty,
`required_status: … independent Opus determination PENDING. Not APPROVED; not
ACTIVE.`

So the 14:25Z determination's §8.1–8.4 corrections have **not been applied**, and
its §8.4 expected movement from 12 errors to 6 has not occurred. Consequence, stated
plainly: under `CAPABILITY_POLICY.md`'s fail-closed rule ("any capability not present
in `CAPABILITY_REGISTRY.md` with status `APPROVED` is **not usable** on this
project"), **even the already-granted synthetic-only bounded scope is currently
non-operative**, as is CAP-010's §7.2(b) local lint extension. Approving a broader
real-tree/CI scope on top of a row that still reads `NOT APPROVED` would produce a
control plane in which the wide scope is recorded as approved while the narrow one
remains pending — the exact self-authorising shape the prior §8.1 was written to
delete. This is an independent reason the extension cannot be granted in this round,
additional to the evidence gaps in §5.

## 7. Determination — CAP-009, gitleaks 8.30.1

### 7.1 Verdict

**BLOCKED.** No extension to real-tree, Git index, Git history, or CI scope is
granted. The prior synthetic-fixture-only bounded approval (prior §6.2) is
**unchanged** — neither broadened nor narrowed by this determination — and remains
non-operative until §6's registry correction lands.

The decisive reason is not a judgment call about risk appetite. It is that
**the qualified governed shape structurally cannot accept a Veyro path**: both the
local and the CI wrapper raise a refusal when the target is the repository (or the
checkout) or lies beneath it. There is consequently no stated, no drilled, and no
executable governed invocation for a real-tree target. Granting "real tree + CI"
would be approving a shape that does not exist — which is precisely the
infer-from-green-CI error this charge names. The green run is genuine, verified by
me, and entirely synthetic by construction (§4.1); its own evidence record states
the same conclusion. Added to that: the §6.3 item 2 non-vacuity clause is unmet for
its allowlist half (§5.2), the mode a repository secret-scanning gate would actually
use (`gitleaks git` / `--staged`) has **zero** evidence in any environment, the only
hash-established local artifact is not the binary on `PATH` (§3.2), and the
fail-closed properties exist only inside drill code and an uncommitted workflow
(§5.3).

### 7.2 What *is* newly established (recorded so a future round does not redo it)

- Execution of the **pinned Linux artifact** `551f6fc8…2470eb`, with install-time
  digest verification before extraction, failing closed, in a real CI job — prior
  §6.3 item 1's second branch, discharged and independently verified (§4.2).
- All **three** default-on suppression surfaces shown default-suppressed and
  governed-detected in `dir` mode, each with an unsuppressed control, locally and in
  CI; plus a **fourth** surface honestly discovered and handled by refusal.
- Exit-code separation held in a real environment: `0` clean / `42` leak / `1` error
  (missing target `rc=1`, malformed config `rc=1` — neither `0` nor `42`).
- Redaction held live: the placeholder appears nowhere in the CI log (§4.2).
- The Homebrew-vs-upstream mismatch is now **twice** independently derived (§3.2).

### 7.3 Exact scope that remains in force (unchanged, authoritative)

Target/mode: `gitleaks dir` against **disposable synthetic directories created
outside the Veyro repository** (OS temp / pytest `tmp_path`), cwd also outside the
repository. Flags: `--no-banner --no-color --redact=100 --exit-code 42
--report-format json --report-path <temp path outside the repo>
--ignore-gitleaks-allow -i <empty dir>`; `gitleaks version` asserted `== 8.30.1`.
Output: JSON report to a temp path outside the repository; value-free (rule IDs,
file names, redacted secrets only). Exit contract: `0` clean / `42` leak / anything
else an error. Suppression handling: `--ignore-gitleaks-allow` set, `-i` pointed at
a verified-empty directory, `--baseline-path` **never** passed in any form.
Empty-target handling: **refuse before scanning** — target must be a directory
containing ≥1 non-empty file; a single-file target is refused; a target-root
`.gitleaksignore` is refused (no flag defeats it). Supply-chain: the executable's
own SHA-256 must equal a hash-verified upstream artifact —
`ba52fb1bfabbcde42f032afad3d6e0b19dff8ed105229a16e7caa338bbc0e84f` (darwin arm64,
contained) or the binary extracted from a digest-verified
`gitleaks_8.30.1_linux_x64.tar.gz` (`551f6fc8…2470eb`) — verified **at install time
on every run**, because the release is mutable (`immutable: false`, re-confirmed
§3.1). **The Homebrew binary `052d1882…c771422` is ineligible for every scope, and
local Homebrew identity may never be assumed.** Network: none required.
Permanently excluded: any Veyro path as a target, `gitleaks git`, `--staged`,
`--baseline-path`, archive/decode-depth expansion, and any gate or required-status
role.

### 7.4 Can a further CI gate implementation legally rely on CAP-009 now?

**No.** Three independent bars, each sufficient on its own: the registry row reads
`NOT APPROVED` and the validator fail-closes (§6); no real-tree invocation is stated
or drilled (§5.1 item 3); and the gate's fail-closed properties exist only in
uncommitted drill code (§5.3). The existing `c06-synthetic-scanner-qualification.yml`
is a qualification drill and **must not** be promoted to a required status check,
referenced by a gate, or treated as a trust anchor — as its own header already
states.

## 8. Determination — CAP-010, Ruff 0.16.9

### 8.1 Two distinct questions, kept apart (as the charge requires)

**(i) Local non-gate lint/format — C10-1.** `ruff check` and `ruff format --check` /
`--diff` over Veyro Python, run locally by the project's own verification loop under
the committed configuration. This scope was **already granted** by the prior
determination §7.2(b), conditioned on C10-1. I verified C10-1 first-hand and it is
**SATISFIED** (§3.3): `backend/.venv/bin/ruff` is byte-identical to the
hash-verified PyPI macOS arm64 wheel's script. The prior determination's own text
makes the consequence automatic and judgment-free — the extension "takes effect
only once the following is recorded as evidence," and it is now recorded and
independently reproduced.

This is **not** a scope extension granted by this determination; it is a
pre-existing authority whose condition is met. It is explicitly **not** a SAST
authorisation and **not** a CI authorisation. It remains non-operative until the
registry and manifest actually record it (§6), and it does not retroactively
authorise anything — BUG-057 is unaffected.

Exact permitted shape for (i): `ruff check` and `ruff format --check` / `--diff`
only; configuration from the committed `ruff.toml` / `backend/pyproject.toml` at the
hashes in §2; **no `--select S`** and no `S`-inclusive selection; local only, never
in CI, never a gate or required status; executable SHA-256 must equal
`8b799e53…509e57` (equivalently, must be shown to derive from the hash-verified
wheel for its host platform — on any other host, C10-1 must be re-satisfied for
that platform before the extension applies there). Permanently excluded in every
mode: `--fix`, `--unsafe-fixes`, in-place `ruff format` without `--check`/`--diff`,
and `--add-noqa`. Any future configuration introducing `extend`, plugins,
`exclude`, or `per-file-ignores` is a stage-9 material change and voids this
extension until re-reviewed.

**(ii) Ruff SAST (`--select S`) on the real tree, and any CI execution.** This is
the scope-extension question actually before me, and it is answered next.

### 8.2 Verdict on (ii)

**BLOCKED.** No extension to real-tree `--select S` scanning or to any CI execution
is granted. The prior §7.2(a) synthetic bounded approval is unchanged.

CAP-010's evidence is materially stronger than CAP-009's — three of the four §7.4
items are satisfied, including the two that cost the most work (real-configuration
drill, pinned-Linux-wheel CI execution), and I verified both live. But the single
irreducible gap is identical and decisive: **§7.4 item 3's target set was never
stated, and both qualified wrappers refuse any repository path by construction**, so
no `S` invocation against any Veyro file has been specified, drilled, or made
executable. A green synthetic CI run, however genuine, cannot establish behaviour on
a target class the drill is structurally incapable of accepting. Secondary
conditions that must be closed in the same round: the partial-gitignore vacuity
residual on directory targets (§5.3), the absence of any committed gate wrapper
(§5.3), §7.4 item 4's standing limit still not carried into the row, and the
registry/manifest state in §6.

One operational caution for whoever authors that round, offered as a sequencing
point rather than a security objection: the governed `S` shape passes
`--ignore-noqa`, so any existing in-tree `# noqa: S…` is defeated, and the
`S`-cleanliness of the Veyro tree is recorded as unknown. The first real-tree `S`
run may therefore produce a large, previously-unseen finding set. GOV-01-R03's own
evidence obligation is a **real report** ("even if '0 findings' — the tool working is
the evidence, not a finding count"), not a clean tree, so the first run should be
staged as advisory/report-producing and only then considered for a gate — coupling
approval and required-status in one step would be an avoidable self-inflicted block.

### 8.3 Exact scope that remains in force for (ii)-adjacent synthetic use

Target/mode: `ruff check` and `ruff format --check` / `--diff` with
`--isolated --no-cache`, or `--config <committed repo config> --no-cache --no-fix
--select S --output-format json` with `--ignore-noqa`, against **disposable
synthetic files created outside the Veyro repository**. Non-vacuity: a `--show-files`
pre-check must list ≥1 file **and** every explicit target must yield at least one
checked file; targets must exist and be non-empty — otherwise refuse before
scanning, because Ruff itself returns a vacuous `rc 0` on empty and missing targets.
Exit contract: `0` clean / `1` findings (classified by code, with `invalid-syntax`
distinguished from `S` findings) / `2` tool or configuration error. Suppression
handling: `--ignore-noqa` in the governed shape; `--add-noqa` never. Supply-chain:
executable must derive from a hash-verified PyPI wheel —
`a21713e6…bc728` (linux x64, for CI) or `1632eb1d…64ab6a` (macOS arm64, installed
script `8b799e53…509e57`) — with the digest verified at install time; the PyPI 0.16.9
release is immutable, and no PyPI attestation is published for it (inherited finding,
§3.1). Permanently excluded in every mode: `--fix`, `--unsafe-fixes`, in-place
`ruff format`, `--add-noqa`, any Veyro path under `--select S`, and any gate or
required-status role.

### 8.4 Can a further CI gate implementation legally rely on CAP-010 now?

**No**, for the SAST/CI gate role — same three bars as §7.4: registry `NOT APPROVED`
(§6), no stated real-tree target set (§5.3 item 3), fail-closed properties
uncommitted (§5.3). For the local lint/format role in §8.1(i), CI reliance is
excluded by the scope itself: it is local, read-only, and non-gate by definition, and
even that becomes usable only once the registry and manifest record it.

## 9. Rejected claims

Each of the following is a reading the evidence could invite. Each is rejected, with
the specific ground.

1. **"The green CI run extends scope to real-tree/CI."** Rejected. Both CI wrappers
   refuse checkout paths by construction; every target was generated under
   `RUNNER_TEMP`; the two config files were read via `--config` and were never
   targets (§4.1, verified in source). A successful synthetic run is evidence about
   synthetic targets. The run's own evidence record reaches the same conclusion, and
   the charge forbids the inference independently.
2. **"The Homebrew gitleaks mismatch has been resolved."** Rejected. It is
   **confirmed**, not cured — re-derived this session (§3.2). The sole consequence is
   that the Homebrew binary is ineligible for every scope and that broader scope, if
   ever granted, must bind to a hash-verified upstream artifact.
3. **"The wrapper's ≥1-non-empty-file check satisfies §6.3 item 2's non-vacuity
   requirement."** Rejected. It closes the *empty-target* half and leaves the
   *fully-allowlisted* half — named explicitly in the clause — entirely untested; no
   drill exercises the default global allowlist at all (§5.2).
4. **"33 PASS / failures: 0 is an R03 (or scenario) result."** Rejected. No scenario
   is executed or disposed by this evidence. GOV-01-R03's acceptance criterion
   requires every named tool to run "successfully in CI **against the current repo
   state**" and its evidence obligation requires a real report from "this repo's own
   current tree" — which is exactly the scope still withheld. The C06 batch cannot
   mark R03's scanner criterion met on this evidence.
5. **"The prior bounded approval is in force."** Rejected. Registry rows and both
   manifest entries read `QUALIFIED — NOT APPROVED` / `PENDING`, and the validator
   fail-closes with 12 errors, not the 6 the prior §8.4 predicted after correction
   (§6). Under the policy's fail-closed rule, nothing is operative yet.
6. **"Governed shapes are available tooling."** Rejected. They exist only in two
   pytest files and in heredocs inside a workflow that is untracked in the
   authoritative repository (§2, §5.3). Every fail-closed property is wrapper-side;
   a bare-flag CI invocation would lose all of them.
7. **"C10-1 being met authorises Ruff `S`, CI use, or a gate."** Rejected. C10-1
   activates only the local, read-only, non-gate lint/format extension the prior
   §7.2(b) already granted, and expressly not `--select S` or CI (§8.1).
8. **"This determination disposes anything beyond the two capability scopes."**
   Rejected by charge and by content. No scenario PASS, no R03/R04 acceptance
   criterion, no gate closure, no module progress, no CAP-011/CAP-012 verdict, no
   R04 gate-2/gate-3 or SCN-070 reopening. BUG-057 stays **OPEN**: its dependency 1
   (an individual verdict per capability) now has a second determination for each,
   while dependency 2 (real-tree/CI use) is satisfied for neither.

**One discrepancy I could not close and will not launder.** The governed-shape record
states that `--max-decode-depth` defaults to **5** in this binary, contradicting the
prior determination §3 item 3's "both default to `0`." Verifying it would require
executing gitleaks, which this review declined on separation grounds, so it is
**implementation-reported and not independently verified by this reviewer**. It is
not load-bearing for either verdict (both are BLOCKED on other grounds), but it must
not be written into a registry row as established fact until someone verifies it;
whichever figure is correct, the row should carry it with its provenance. Note the
direction: the prior report *understated* default coverage, so this is an accuracy
defect, not a newly discovered exposure.

## 10. Remaining mandatory dependency — the smallest exact missing criterion

Stated as the charge requires: the single smallest mandatory criterion whose absence
blocks approval, per capability. No confidence review is requested, and none is
needed — these are objective, authorable artifacts.

### 10.1 CAP-009 — smallest exact missing mandatory criterion

> **C09-X.** A **stated and executed governed invocation whose target is a Veyro
> path.** No such invocation exists in any record, and every qualified wrapper
> refuses repository paths by construction, so there is nothing to review. Authoring
> it is the irreducible prerequisite; everything else below is a property that
> invocation must have, not a separate round.

To be approvable, that invocation must arrive with all five of:

1. **A committed, reviewed gate wrapper** carrying the fail-closed pre-checks as
   executable code in the authoritative repository — non-vacuity, target-root
   `.gitleaksignore` refusal, no-baseline, explicit target enumeration — not in a
   drill heredoc. Per `.claude/rules/infra/iac.md` control 1, the wrapper and its
   workflow are committed and reviewed **before** they take effect anywhere.
2. **An explicit Veyro target set**, enumerated rather than implied, with the
   expected scanned-path set recorded.
3. **Allowlist non-vacuity** (§5.2): one synthetic case planting the labelled
   placeholder inside a path the **default global allowlist** excludes, showing it is
   missed under the default config, and then either detected under the governed
   configuration **or** declared out of coverage with the excluded path set
   enumerated in the registry row. A real-tree "0 findings" must be accompanied by a
   recorded exclusion set.
4. **Evidence for the mode the gate will actually use.** If history/index scanning is
   intended, `gitleaks git` / `--staged` needs its own positive / negative /
   fail-closed / non-vacuity drill — it has **none** today, and its surfaces (commit
   range, `--log-opts`, repo-root `.gitleaksignore`, baseline) differ from `dir`'s.
5. **Install-time digest verification on every run**, failing closed, against a
   hash-verified upstream artifact, with the Homebrew binary excluded by hash — the
   release is mutable, so a recorded pin is not enforcement (§3.1).

### 10.2 CAP-010 — smallest exact missing mandatory criterion

> **C10-X.** A **stated governed `S` target set over Veyro paths, executed through a
> committed wrapper.** §7.4 item 3's target set is the only one of its four items
> still substantively open; both qualified wrappers refuse repository paths, so no
> `S` invocation against a Veyro file is specifiable today.

To be approvable, it must arrive with:

1. **The target set itself**, enumerated — preferably explicit file lists rather than
   directory targets.
2. **Count-based non-vacuity** closing the partial-gitignore residual (§5.3): assert
   checked-file count equals an enumerated expected `.py` count for the target set,
   rather than merely "≥1 checked file per target."
3. **A committed, reviewed wrapper and workflow** carrying the `--show-files`
   pre-check and the exit-code classification as executable code in the authoritative
   repository (`iac.md` control 1).
4. **§7.4 item 4 carried into the registry row**: `S` is pattern-based, not taint
   analysis; its stable set is version-dependent; an `S`-clean tree is not an absence
   of injection defects and must never be reported as one.
5. **Advisory-before-gate sequencing** (§8.2), since the tree's `S` state is unknown
   and the governed shape defeats in-tree `# noqa`.

### 10.3 Dependency binding on both, independent of the evidence gaps

Per §6: the 14:25Z determination's §8.1–8.4 registry/manifest corrections must land
first — including deleting the self-authorising sentence from both rows, writing
`approved_by` and a parseable `next_review_due`, putting the bound in the `scope`
cell and the manifest `used_for` / `required_status` cells (the validator checks
only the `APPROVED` prefix, a named `approved_by`, and a parseable date — **never
scope adherence**), and the expected validator movement from 12 errors to 6. Until
that is done, **no** CAP-009/CAP-010 scope is operative, narrow or broad, and no
subsequent extension round has a coherent row to extend.

## 11. What this determination does not establish

A capability-security scope judgment and nothing else. It infers no CI gate
authorisation, no scenario PASS, no gate closure, and no module progress.
SCN-MOD001-029, 094, 134, 135, 136 and all 13 M1-C-06 scenarios remain **NOT
EXECUTED**. No GOV-01-R03 or GOV-01-R04 acceptance criterion is closed; R03's
scanner criterion in particular cannot be closed by evidence that withholds the
real-tree scanning it names. M1-C-05's scanner execution remains blocked by the
absence of approved real-tree scanning. No layer-3 "runs in CI" authorisation and no
layer-4 branch-protection authority is created, implied, or affected. The
`c06-synthetic-scanner-qualification.yml` workflow is not approved as a gate, is not
a required status, and is not a trust anchor. CAP-011 (pytest) and CAP-012 (mypy)
were deliberately **not** adjudicated and their verdicts must not be inferred from
these two. R04 gate-2, gate-3, and SCN-070 were not read from, written to, or relied
upon, and no review entitlement beyond this single scope-extension action is created
or consumed. MOD-001 exit is unchanged. No owner-reserved restriction was engaged:
no spend, no real member data, no Production action, no material scope change — the
one credential-shaped value anywhere in this evidence set is a runtime-assembled,
explicitly-labelled `EXAMPLE_NOT_A_REAL_KEY` placeholder, verified absent from the
CI log (§4.2). Other workflow files under `.github/workflows/` were not adjudicated.

## 12. Residual risks (recorded, accepted only within the unchanged bounded scopes)

Both tools' provenance chains terminate at GitHub/PyPI with no verified cryptographic
signature, so a platform-level compromise is not detected by the checksum agreement
recorded here. The gitleaks release is mutable, making install-time re-verification
load-bearing rather than ceremonial. Rule-behaviour evidence remains one rule deep
per tool (`github-pat` of 222; `S608` of 73), which bounds what any approval can
mean. The CI runner image (`ubuntu-24.04`) and its supplied toolchain (`curl`, `tar`,
`sha256sum`, `git`, `python3`) are unpinned and mutable; only the two scanner
artifacts are hash-pinned. And `gitleaks dir` on a real tree would, under the default
global allowlist, examine an unquantified subset of bytes (§5.2) — which is a reason
the extension is withheld rather than a risk accepted.

Not accepted, and therefore withheld rather than disclosed: everything in §7.1 and
§8.2.

---

*Two separate verdicts, as the charge specified. No second reviewer is required or
implied by this file. This reviewer modified no file other than this report.*
