---
doc: BUG-036
status: OPEN — Tier 1 CLOSED (applied by owner, commit `e971523c3a665020df601b685d8f4b092ead7052`, independently verified and 4 scripts + full 194-test regression suite actually executed for real); Tier 2 install materials corrected and internally consistent as of Round 4 (bare-`pip` hash-lock mechanism, `pip-tools` evaluated and rejected as unnecessary; exact 6-step owner sequence + lock-file format defined), install not yet performed, guard extension not yet applied or reviewed
found_date: 2026-09-25
found_by: this session, dispatched specifically to investigate the recurring CAP-007 execution block after Slices 1-3 all disclosed it independently
severity: P1 (degrades MOD-001's implementation evidence quality project-wide and blocks Gatekeeper certification's real-execution requirement; does NOT block continued implementation-slice authoring, since slices may still hand-trace logic and disclose execution as honestly BLOCKED, per established precedent) — narrowed by Tier 1's closure: the `tools/**` half of this bug is now fully resolved with real evidence; only the `pytest`/`ruff`/`mypy` half remains open
---

# BUG-036: no MOD-001 session can execute `pytest`/`ruff`/`mypy`, or any newly-authored `tools/**` validator script, through this project's own guarded Bash tool

## Relationship to BUG-025 — related, not a duplicate, not being folded in

`BUG-025` (`knowledge/03-Modules/MOD-000/evidence/bugs/BUG-025-no-material-change-reevaluation-trigger.md`)
is, and remains, `FIXED`. Its own subject — `validate_capabilities.py`
never detecting capability version drift — was a real MOD-000-era gap in
a specific tool's *logic*, and the fix (`capability_drift_check.py`) is
correct and unaffected by this bug. BUG-025's evidence separately
*disclosed* (not fixed) that the new script it built could not be
executed through `bash_guard.py`, for the same root-cause reason
documented below, and treated that as an accepted, non-blocking,
single-instance residual at the time (2026-09-13, MOD-000 certification
scope).

That residual has since recurred, unchanged, in every MOD-001
implementation slice that has touched `tools/**` or `backend/**`:
Slice 1 (`tools/validate_baseline_binding.py`), Slice 2
(`tools/validate_capability_manifest.py`), and Slice 3 (`tools/validate_repo_skeleton.py`,
`tools/tests/test_validate_repo_skeleton.py`, and all 4
`backend/tests/*/test_scaffold_live.py` scaffold-liveness fixtures) — 6
new files, 0 of them ever executed. This is no longer a single accepted
residual; it is every MOD-001 slice's outcome. `DEVELOPMENT_CONSTITUTION.md`
DC-11 ("Cumulative regression... becomes binding starting MOD-001")
means real, executed regression evidence is now a binding module
obligation, not the aspirational one it was during MOD-000 planning —
raising this from "disclosed and accepted" to "a real defect requiring
its own fix," per the owner's own instruction that prompted this
investigation. Filed as a new, distinct bug rather than reopening
BUG-025 because the scope is materially broader (a general MOD-001
test-execution capability, not one MOD-000 script) and BUG-025's own fix
is not in question.

## Root cause — read directly from `.claude/security/bash_guard.py` this session, not inferred

Three independent, precise reasons, confirmed by direct code inspection
(`.claude/security/bash_guard.py`, current governed content, SHA-256
`315df926ff607fb0560f4f1842646d28eeb2a059b771130db5002edb347cc245` —
independently recomputed this session via `shasum -a 256`, exact match
to `CAPABILITY_REGISTRY.md`'s CAP-007 row; no drift):

1. **`pytest` and `ruff`/`mypy` have no command family in the guard at
   all.** `_READONLY_DISPATCH` (line 580) lists exactly 11 command
   names: `find`, `shasum`, `ls`, `cat`, `head`, `tail`, `wc`, `pwd`,
   `stat`, `grep`, `python3`. Neither `pytest`, `ruff`, nor `mypy`
   appears. `classify()`'s final fallthrough (line 724) denies any
   command name not in `_GIT_MUTATION_DISPATCH`/`_MUTATION_DISPATCH`/
   `_READONLY_DISPATCH` with `UNKNOWN_COMMAND` — this fires
   unconditionally for these three tool names, regardless of flags or
   arguments.

2. **`python3` is recognized, but `_python_readonly` (line 571) only
   allows one exact shape: `python3 <script>` where `<script>` is one of
   7 fixed, SHA-256-content-hash-pinned paths in `_ALLOWED_PYTHON_SCRIPTS`
   (line 538).** None of MOD-001's 4 new Python scripts
   (`tools/validate_baseline_binding.py`, `tools/validate_capability_manifest.py`,
   `tools/validate_repo_skeleton.py`, `tools/tests/test_validate_repo_skeleton.py`)
   is in that dict, so `script in _ALLOWED_PYTHON_SCRIPTS` is `False` for
   all 4 and the function returns without allowing — falling through to
   `classify()`'s `DISALLOWED_FLAG_OR_SHAPE` deny. This also explains why
   a bare `python3 --version` or `python3 -m pytest ...` is denied even
   with no fixture involved at all: `-m`/`--version` are never in the
   allowlist dict either, so the exact-match check fails immediately —
   this is a structural gate, not specific to any one script or flag
   combination (independently re-confirmed this session by direct
   attempt: `python3 --version` and `python3 tools/validate_repo_skeleton.py`
   both denied, byte-identical `BLOCKED: DISALLOWED_FLAG_OR_SHAPE —
   python3 did not match its allowlisted read-only shape`).

3. **No command family exists for installing anything (`pip`, `pip3`,
   `python3 -m pip`, `uv`, etc.), so even a hypothetically corrected
   guard could not install `pytest`/`ruff`/`mypy` into this environment
   if they are not already present** — see "Open, unresolved question"
   below; this session could not determine whether they are already
   installed, because every read-only command this guard exposes
   (`ls`/`find`/`cat`/`stat`/etc.) is itself restricted to *repo-relative*
   paths only (`_is_safe_relative_path` rejects any leading `/`), so this
   guarded session cannot inspect `/usr/bin`, `/usr/local/bin`, a global
   `site-packages`, or any other absolute-path system location to check.

## Affected commands (all confirmed by direct attempt this session, in addition to all three agents' independent reports during Slice 3)

- `pytest` (any invocation) — `UNKNOWN_COMMAND`.
- `ruff` (any invocation) — `UNKNOWN_COMMAND` (not attempted directly
  this session, but structurally certain from `_READONLY_DISPATCH`'s
  fixed 11-name list; no code path could allow it).
- `mypy` (any invocation) — `UNKNOWN_COMMAND`, same reasoning.
- `python3 -m pytest ...` (any form) — `DISALLOWED_FLAG_OR_SHAPE`.
- `python3 <any-script-not-in-the-7-item-dict>` — `DISALLOWED_FLAG_OR_SHAPE`,
  including all 4 of MOD-001's own new validator/test scripts.
- `python3 --version` / `python3 -c ...` — `DISALLOWED_FLAG_OR_SHAPE`
  (the allowlist has no bare-flag or inline-code shape at all).
- `pip install ...` / `pip3 install ...` — `UNKNOWN_COMMAND` (no `pip`
  family exists; not itself part of this bug's fix, see Tier 2 below).

## Open, unresolved question this session could not answer

Whether `pytest`/`ruff`/`mypy` binaries (or a `pytest`-capable Python
environment) already exist anywhere on this host, outside this guarded
session's own repo-relative visibility. This matters because it changes
which tier of the fix below is actually load-bearing. Resolving it
requires either an owner/human-terminal check outside Claude Code's
guard (`which pytest ruff mypy`, or equivalent) or a narrowly-scoped
future guard extension that can answer the same question read-only
without granting broader access — not attempted here, since it is
exactly the kind of new-command-family decision Tier 2 below already
requires independent review for.

## Recommended remediation — two independent tiers, smallest first

Both tiers are governed by `CAPABILITY_POLICY.md`'s stage 9
("Re-evaluate — a material change to a capability... triggers a
mandatory return to stage 4-5") applied to `CAP-007`
(`.claude/security/bash_guard.py`) itself, which the policy's own scope
line explicitly covers ("every Skill, Rule, Plugin, MCP server, hook, or
script"). Every prior change to this file — v1's four review rounds, v2's
two-round redesign cap, the owner-authorized Round 3, the Round-3-P1
remediation — went through an independent, fresh-context
`veyro-security-reviewer` (Opus) pass before being trusted. Neither tier
below is proposed as already-approved; both need that same pass. Per
this project's `.claude/security/**` Edit/Write-deny (confirmed this
session against the live `.claude/settings.json`, lines 148-154), no
session — this one included — can apply either patch itself.

### Tier 1 (recommended now — smallest possible diff, zero new mechanism, no `pip`/install dependency)

Add 4 new entries to the *existing, already-`APPROVED`*
`_ALLOWED_PYTHON_SCRIPTS` dict (`.claude/security/bash_guard.py` lines
538-553) — the exact same hash-pinning mechanism already governing the 7
current entries, extended with no new code. All 4 scripts are
stdlib-only (verified by reading each file's own imports: `argparse`,
`subprocess`, `sys`, `pathlib`, `hashlib`, `json`, `re`, `tempfile`,
`shutil` — no third-party import in any of them), so this tier needs no
`pip install` and no environment change to become executable the moment
it lands. SHA-256 values independently recomputed this session via
`shasum -a 256` (not copied from any agent's own report):

```python
_ALLOWED_PYTHON_SCRIPTS = {
    "knowledge/00-System/validate_capabilities.py":
        "680ee3fbb0a0c076412f1dac084053c8613e4f00546511f18a73478f0aec6db2",
    "knowledge/00-System/verify_baselines.py":
        "d8deb8679c71fe775875690b0486228c2cf32e717f3c756d818cffbd2dca8a72",
    "knowledge/05-QA/tools/mr_verify.py":
        "be5a4ce85ca4bb1b7154bf0d422c5b70aa7213faaa140372fc4a994ced31d40e",
    "knowledge/05-QA/tools/resolution_bound.py":
        "c50105f7fc08be0d73d4728caf3b93acf60a2c3f0c5afd1014b50cba9194c527",
    "knowledge/03-Modules/MOD-000/scenario-catalog/tools/validate_catalog.py":
        "d0bfab4e756a89600e67db98d77addeaad69b6695930605a3e38dfd526ae81fd",
    "knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/evidence_integrity_check.py":
        "881c83ed1adff28f0c23f9c4a1b2e1b4d392620d3237d93e49b4e38a55dee409",
    ".claude/security/tests/test_bash_guard.py":
        "c3ab3e94e77824c3966755a398f1fae8aa1b4c39e5d21f6423c03fec437d409c",
    # --- new entries (BUG-036 Tier 1) ---
    "tools/validate_baseline_binding.py":
        "b76c4f37491a858ccfb58d72a3f2a8d040f9862d6c80529113c1596bfbe0d70b",
    "tools/validate_capability_manifest.py":
        "c53404eda5837f0754ab68e00699effb25a2f653bce2d8eacb98360217c99517",
    "tools/validate_repo_skeleton.py":
        "162750a3e8a52afb93cf6ed3087df3814e7d5cd9150a1e152f3f11f8cdaf5d91",
    "tools/tests/test_validate_repo_skeleton.py":
        "bcae0d8a81fdd41972b5398f14ded7bed806cc6f8c1a274316095ab8aa2ed919",
}
```

This closes the "python3 for new project validators" bullet entirely —
including, incidentally, `tools/tests/test_validate_repo_skeleton.py`
itself, which already has its own `if __name__ == "__main__"` block and
needs no `pytest` at all to run and report PASS/FAIL. It does **not**
touch `pytest`/`ruff`/`mypy` and needs no governance decision about
installing anything.

**What this tier does NOT weaken:** no new command family, no flag
loosened, no path-shape check loosened, no `.claude/` protection
touched, `_ALLOWED_PYTHON_SCRIPTS` remains a fixed enumerated dict (not a
directory glob or a dynamic trust rule) — the exact "no arbitrary Python
script execution" property is preserved by construction, since a 5th,
6th, or Nth script still has to be individually added, hashed, and
re-reviewed the same way.

### Tier 2 (larger, needed for `pytest`/`ruff`/`mypy` specifically — requires an owner policy decision first, then independent review)

Two sequential owner decisions are needed before this tier can even be
built for review, not after:

**(a) Is a `pip install` (even narrowly, exact-pinned versions only,
e.g. `pip install pytest==<X> ruff==<Y> mypy==<Z>`) an action any agent
session may take through this project's guarded Bash tool at all?**
`CAPABILITIES.md`'s existing "Standard open-source test tooling — no
special review beyond this project's existing DC-19 supply-chain
discipline" line covered the decision to *use* these tools in the
project; it did not decide whether an autonomous session may fetch and
execute third-party PyPI package code through its own Bash tool, which
is a materially different, DC-19-governed question (provenance,
transitive dependencies, and install-time arbitrary code execution via
`setup.py`/build backends are all real for a `pip install`, in a way a
read-only `ruff check` invocation is not). **If the answer is no** (or if
`pytest`/`ruff`/`mypy` already exist in this host's Python environment,
per the open question above — an owner/human-terminal check can resolve
this without any guard change), no install mechanism is needed and only
part (b) below applies.

**(b) A new, narrow Class-A-style command family for `pytest`/`ruff`/`mypy`
themselves**, drafted here for independent review — **explicitly not
proposed as final, not to be merged without a fresh-context
`veyro-security-reviewer` pass, per every prior change to this file**:

```python
_ALLOWED_TEST_TOOL_ROOTS = ("backend/", "tools/")


def _under_allowed_test_root(path):
    return any(
        path == root.rstrip("/") or path.startswith(root)
        for root in _ALLOWED_TEST_TOOL_ROOTS
    )


_PYTEST_FLAGS = {"-v", "-vv", "-q", "-x", "--collect-only", "--tb=short", "--tb=line", "--tb=no"}


def _pytest_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if not all(f in _PYTEST_FLAGS for f in flags):
        return
    if not positionals:
        return  # never a bare "pytest" — no implicit repo-wide discovery
    if not all(_is_safe_relative_path(p) and _under_allowed_test_root(p) for p in positionals):
        return
    _allow("pytest (bounded to backend/, tools/)")


_RUFF_READONLY_FLAGS = {"--quiet", "-q", "--check"}


def _ruff_readonly(tokens):
    if not tokens:
        return
    subcommand, rest = tokens[0], tokens[1:]
    flags, positionals = _split_flags_positionals(rest)
    if subcommand == "check":
        pass
    elif subcommand == "format":
        if "--check" not in flags:
            return  # never allow in-place rewrite through this guard
    else:
        return
    if not all(f in _RUFF_READONLY_FLAGS for f in flags):
        return
    if positionals and not all(_is_safe_relative_path(p) and _under_allowed_test_root(p) for p in positionals):
        return
    _allow(f"ruff {subcommand} (read-only, bounded)")


def _mypy_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if flags:
        return  # no flags at all in this first bounded pass
    if not positionals:
        return
    if not all(_is_safe_relative_path(p) and _under_allowed_test_root(p) for p in positionals):
        return
    _allow("mypy (bounded to backend/, tools/)")
```

...and 3 new entries in `_READONLY_DISPATCH`:

```python
    "pytest": _pytest_readonly,
    "ruff": _ruff_readonly,
    "mypy": _mypy_readonly,
```

**Design notes for the reviewer, not conclusions:** deliberately no
`ruff format` without `--check` (would be an in-place mutation, a
different risk class this draft avoids); deliberately no `-m` invocation
form for any of the three (avoids re-opening the module-injection
ambiguity `_python_readonly` was built to close); deliberately requires
at least one explicit bounded positional for `pytest`/`mypy` (never
implicit whole-repo discovery); deliberately restricts every positional
to `backend/`/`tools/` only, never `.claude/`/`knowledge/`, via the
existing `_is_safe_relative_path` primitive plus a new bounded-root
check, so this cannot be pointed at governance files even if a future
`pytest`/`mypy` plugin tried to read arbitrary paths as fixtures.

## Security properties this fix (either tier) preserves

- No new shell composition/substitution surface — Stage 1's
  unconditional composition ban is untouched by both tiers.
- No new absolute-path, wrapper, or case-insensitive matching — exact
  command-name and flag matching, per the file's existing philosophy.
- No loosening of any existing family's flags or path checks.
- `.claude/**`, the 3 governing baseline docs, and the design bundle
  remain unreachable from any new or existing family (Tier 2's bounded
  roots are `backend/`/`tools/` only; Tier 1 adds no new path logic at
  all).
- `_ALLOWED_PYTHON_SCRIPTS` remains a fixed, individually-hash-pinned
  dict — Tier 1 does not introduce a directory-glob or path-prefix trust
  rule that would auto-trust a future 12th script without its own
  explicit addition and review.
- Neither tier grants any new mutation capability — both are Class A
  (read-only) additions; `ruff format` without `--check` is explicitly
  excluded from Tier 2's draft for exactly this reason.

## Regression tests required before either tier may reach `ACTIVE`

Per CAP-007's own established discipline (194 tests before the last
approval, growing with each change): new positive cases (each of the 4
Tier-1 scripts executes and the guard's own decision is `ALLOW`; each of
the 3 Tier-2 families executes a legitimate bounded invocation and is
`ALLOW`) and new negative cases (a script NOT in the Tier-1 dict is still
denied; a Tier-2 family invoked against a `.claude/`- or
`knowledge/`-rooted path is denied; `ruff format` without `--check` is
denied; a bare `pytest` with no positional is denied; every existing
positive/negative case in `.claude/security/tests/test_bash_guard.py`
still passes unregressed). The existing suite's own hash is itself
pinned in `_ALLOWED_PYTHON_SCRIPTS` — a change to it is part of the same
reviewed commit, not a separate step.

## Disposition

**Not fixed by this session** — `.claude/security/**` is Edit/Write- and
Bash-mutation-denied to every session (confirmed this session against
the live `.claude/settings.json`); this file exists to hand the owner an
exact, reviewable patch rather than leave the gap as an unstructured
observation. **BUG-025 is not reopened** — its own subject remains
correctly fixed. **MOD-001 remains IMPLEMENTATION IN PROGRESS**; no
implementation slice was started or continued as part of this
investigation, per explicit instruction.

## Next owner action

1. Resolve the open question above (are `pytest`/`ruff`/`mypy` already
   present on this host, outside this guarded session's visibility?) —
   this determines whether Tier 2(a)'s `pip install` policy question is
   even live.
2. Apply Tier 1 (the 4-entry dict addition above) — lowest-risk,
   immediately actionable, no dependency on (1).
3. Decide Tier 2(a) (the `pip install` policy question).
4. If Tier 2(a) is yes (or moot per (1)), route Tier 2(b)'s draft to a
   fresh-context `veyro-security-reviewer` (Opus) for the same
   independent review every prior `bash_guard.py` change has received,
   before any workflow relies on it.
5. After either tier lands, a fresh session must re-run the affected
   Slice 1/2/3 scripts for real and correct their evidence files from
   "hand-traced only" to actual pass/fail output — not before.

## Round 2 (2026-09-26) — owner environment check completed; Tier 1 finalized with fresh hashes; Tier 2 redesigned around an owner-side install step

**Owner check, outside Claude Code:** `pytest`, `ruff`, `mypy` are **not
installed** anywhere this host exposes to the owner's own check. This
resolves the open question Round 1 left unanswered — Tier 2(a)'s install
question is live, not moot.

**Bootstrap re-verified fresh before finalizing anything:** local HEAD ==
`origin/main` == `ab5473fe0cd5380a71851eb726a2d054029a67df`.
`.claude/security/bash_guard.py`'s own SHA-256 independently
re-recomputed: `315df926ff607fb0560f4f1842646d28eeb2a059b771130db5002edb347cc245`
— unchanged from Round 1, and from `CAPABILITY_REGISTRY.md`'s CAP-007
row. The 4 target scripts' hashes independently **recomputed fresh this
turn**, not reused from Round 1's record (they happen to be identical,
since none of the 4 files changed between turns — confirmed by
recomputing rather than assumed):

```
b76c4f37491a858ccfb58d72a3f2a8d040f9862d6c80529113c1596bfbe0d70b  tools/validate_baseline_binding.py
c53404eda5837f0754ab68e00699effb25a2f653bce2d8eacb98360217c99517  tools/validate_capability_manifest.py
162750a3e8a52afb93cf6ed3087df3814e7d5cd9150a1e152f3f11f8cdaf5d91  tools/validate_repo_skeleton.py
bcae0d8a81fdd41972b5398f14ded7bed806cc6f8c1a274316095ab8aa2ed919  tools/tests/test_validate_repo_skeleton.py
```

### Tier 1 — finalized owner patch (ready to apply as-is)

Target file: `.claude/security/bash_guard.py`. Change: append exactly 4
new key/value pairs to the existing `_ALLOWED_PYTHON_SCRIPTS` dict
(current lines 538-553). No other line in the file changes. No new
function, no new dispatch entry, no new mechanism — `python3` is already
in `_READONLY_DISPATCH` and already routes to `_python_readonly`, which
already checks any `script in _ALLOWED_PYTHON_SCRIPTS`; these 4 lines are
the entire diff.

```diff
 _ALLOWED_PYTHON_SCRIPTS = {
     "knowledge/00-System/validate_capabilities.py":
         "680ee3fbb0a0c076412f1dac084053c8613e4f00546511f18a73478f0aec6db2",
     "knowledge/00-System/verify_baselines.py":
         "d8deb8679c71fe775875690b0486228c2cf32e717f3c756d818cffbd2dca8a72",
     "knowledge/05-QA/tools/mr_verify.py":
         "be5a4ce85ca4bb1b7154bf0d422c5b70aa7213faaa140372fc4a994ced31d40e",
     "knowledge/05-QA/tools/resolution_bound.py":
         "c50105f7fc08be0d73d4728caf3b93acf60a2c3f0c5afd1014b50cba9194c527",
     "knowledge/03-Modules/MOD-000/scenario-catalog/tools/validate_catalog.py":
         "d0bfab4e756a89600e67db98d77addeaad69b6695930605a3e38dfd526ae81fd",
     "knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/evidence_integrity_check.py":
         "881c83ed1adff28f0c23f9c4a1b2e1b4d392620d3237d93e49b4e38a55dee409",
     ".claude/security/tests/test_bash_guard.py":
         "c3ab3e94e77824c3966755a398f1fae8aa1b4c39e5d21f6423c03fec437d409c",
+    "tools/validate_baseline_binding.py":
+        "b76c4f37491a858ccfb58d72a3f2a8d040f9862d6c80529113c1596bfbe0d70b",
+    "tools/validate_capability_manifest.py":
+        "c53404eda5837f0754ab68e00699effb25a2f653bce2d8eacb98360217c99517",
+    "tools/validate_repo_skeleton.py":
+        "162750a3e8a52afb93cf6ed3087df3814e7d5cd9150a1e152f3f11f8cdaf5d91",
+    "tools/tests/test_validate_repo_skeleton.py":
+        "bcae0d8a81fdd41972b5398f14ded7bed806cc6f8c1a274316095ab8aa2ed919",
 }
```

**Newly allowed after Tier 1:**
- `python3 tools/validate_baseline_binding.py`
- `python3 tools/validate_capability_manifest.py`
- `python3 tools/validate_repo_skeleton.py`
- `python3 tools/tests/test_validate_repo_skeleton.py` (this one is
  self-contained — its own `if __name__ == "__main__"` block runs all 3
  of its tests and prints PASS/FAIL with no `pytest` dependency at all)
- The same 4, prefixed `./`, per `_python_readonly`'s existing
  `./`-stripping normalization (unchanged behavior, not new).
- Trailing arguments after any of the 4 scripts (e.g.
  `python3 tools/validate_repo_skeleton.py --root /tmp/fixture`) —
  already unrestricted for allowlisted scripts per the existing
  mechanism's own documented design (the script is integrity-checked;
  its own argument parsing is its business, not the guard's).

**Still denied after Tier 1 (unchanged, confirmed by re-reading
`_python_readonly` and `classify()`):**
- `pytest`, `ruff`, `mypy` in any form — still `UNKNOWN_COMMAND`, no
  family added.
- `python3 -m pytest ...` / `python3 -m <anything>` — still
  `DISALLOWED_FLAG_OR_SHAPE` (`tokens[0]` is `"-m"`, never a dict key).
- `python3 --version` / `python3 -c ...` — still
  `DISALLOWED_FLAG_OR_SHAPE`.
- `python3 <any 5th script not in the dict>` — still
  `DISALLOWED_FLAG_OR_SHAPE`; the mechanism stays a fixed enumerated set,
  not a glob or directory-prefix rule, per the explicit instruction not
  to broaden Python execution beyond the exact-script mechanism.
- `pip`/`pip3`/`python3 -m pip` — still `UNKNOWN_COMMAND`; Tier 1 adds no
  install path.

### Tier 2(a) — the minimal owner decision, now that "not installed" is confirmed

Exactly one decision is required, with two parts that should be decided
together: **may `pytest`, `ruff`, and `mypy` (exact-pinned versions) be
installed into a project-local virtual environment, and if so, by what
mechanism.**

**Recommended narrowest mechanism — a project-local venv, installed
OUTSIDE this guarded session, never through an agent's own Bash tool:**

1. `python3 -m venv backend/.venv` — already excluded from git
   (`backend/.gitignore` line 3, `.venv/`, added in Slice 3). This is the
   narrowest possible install boundary available: every installed file
   lands under one already-gitignored, already-project-scoped directory;
   nothing touches the host's global `site-packages`, no `--user`
   install, no system package manager.
2. Pin exact versions before installing — `backend/pyproject.toml`'s
   current `dev = ["pytest", "ruff", "mypy"]` (Slice 3) is unpinned
   floating-latest, which is itself a supply-chain gap by this project's
   own standard (the same "floating tag/version is not reviewable"
   principle `.claude/rules/infra/iac.md` control 5 already applies to
   GitHub Actions). **Recommend, as part of this same owner decision**:
   pin `dev = ["pytest==<exact>", "ruff==<exact>", "mypy==<exact>"]` (or
   an equivalent `backend/requirements-dev.txt` with `--require-hashes`
   -compatible `--hash=sha256:...` entries per package, if stronger
   reproducibility is wanted) — not applied by this session, since it is
   a `backend/pyproject.toml` content edit outside this turn's own
   10-item scope, but it is the natural, small, separate follow-up
   commit to make at the same time the owner performs the install.
3. `backend/.venv/bin/pip install -r backend/requirements-dev.txt` (or
   the pinned `pyproject.toml` extra) — run by the owner, or by CI/a
   human terminal outside Claude Code's guard. **No agent session
   performs this step, ever** — `pip install` fetches and can execute
   arbitrary third-party code (`setup.py`/build-backend hooks), a
   fundamentally different risk class from anything this guard's Class A
   (read-only) or Class B (narrowly governed mutation) already permits;
   this is exactly the class of action this project's own precedent
   (BUG-029/030/034, and this very bug's Tier 1) already routes to the
   owner rather than attempting inside a guarded session.

**Why this is the owner decision, not something to infer:** DC-19's
supply-chain review (provenance, license, transitive dependencies) for
these three specific packages has not been formally recorded anywhere —
`CAPABILITIES.md`'s existing "standard tooling, no special review" line
covered the decision to *use* pytest/ruff/mypy in this project's stack,
not the decision to let an autonomous session (or even a human, without
the owner's sign-off) install them. This session makes no assumption
about whether that sign-off is a formality or a real gate — it names the
decision precisely and stops.

### Tier 2(b) — exact planned command shapes and guard patch draft (for review only, after installation, not applied)

Once `backend/.venv/bin/{pytest,ruff,mypy}` exist (owner-installed, per
above), the guard needs to recognize exactly 3 command shapes — narrower
than Round 1's draft, which used bare `pytest`/`ruff`/`mypy` names (PATH-
resolved, ambiguous about which binary actually runs) and included a
`ruff format --check` shape this turn's instruction does not ask for.
This redesign keys on the **exact venv-relative path** as the command
name itself — matching `_python_readonly`'s own exact-script-path
philosophy, and removing any ambiguity about which binary executes (a
system-wide `pytest`, if one ever appeared on PATH, would simply not
match any dispatch key):

- `backend/.venv/bin/pytest <bounded backend/ paths>`
- `backend/.venv/bin/ruff check <bounded backend/ paths>`
- `backend/.venv/bin/mypy <bounded backend/ paths>`

Scope is `backend/**` only, not `tools/**` — Tier 1 already fully covers
`tools/**` (all 4 scripts there are stdlib-only, no `pytest`/`ruff`/`mypy`
need ever touches that directory), so extending Tier 2's bounded-root
set to `tools/` as Round 1's draft did would be unused scope, not a real
need.

```python
_VENV_TEST_TOOL_ROOT = "backend/"


def _under_venv_test_tool_root(path):
    return path == _VENV_TEST_TOOL_ROOT.rstrip("/") or path.startswith(_VENV_TEST_TOOL_ROOT)


_PYTEST_FLAGS = {"-v", "-vv", "-q", "-x", "--collect-only", "--tb=short", "--tb=line", "--tb=no"}


def _venv_pytest_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if not all(f in _PYTEST_FLAGS for f in flags):
        return
    if not positionals:
        return  # never implicit/bare invocation — always an explicit bounded target
    if not all(_is_safe_relative_path(p) and _under_venv_test_tool_root(p) for p in positionals):
        return
    _allow("backend/.venv/bin/pytest (bounded to backend/)")


def _venv_ruff_check_readonly(tokens):
    if not tokens or tokens[0] != "check":
        return  # only the "check" subcommand — never "format" (would mutate files in place)
    flags, positionals = _split_flags_positionals(tokens[1:])
    if not all(f in ("--quiet", "-q") for f in flags):
        return
    if not positionals:
        return  # never an implicit/cwd-relative scope
    if not all(_is_safe_relative_path(p) and _under_venv_test_tool_root(p) for p in positionals):
        return
    _allow("backend/.venv/bin/ruff check (bounded to backend/)")


def _venv_mypy_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if flags:
        return  # no flags at all in this first bounded pass
    if not positionals:
        return
    if not all(_is_safe_relative_path(p) and _under_venv_test_tool_root(p) for p in positionals):
        return
    _allow("backend/.venv/bin/mypy (bounded to backend/)")
```

...and 3 new entries in `_READONLY_DISPATCH` (the dict key is the exact
literal path string, not a bare command name — `classify()`'s
`cmd, rest = tokens[0], tokens[1:]` and its `if cmd in _READONLY_DISPATCH`
check already support any string as a key, so this needs no change to
`classify()` itself):

```python
    "backend/.venv/bin/pytest": _venv_pytest_readonly,
    "backend/.venv/bin/ruff": _venv_ruff_check_readonly,
    "backend/.venv/bin/mypy": _venv_mypy_readonly,
```

**Explicitly not proposed as final — needs the same fresh-context
`veyro-security-reviewer` (Opus) pass every prior `bash_guard.py` change
has received, per CAP-007's own stage-9 re-evaluation rule.** Design
notes for that reviewer: no `-m` invocation form anywhere (avoids
re-opening the module-injection ambiguity `_python_readonly` was built
to close); `ruff format` excluded entirely, not just gated behind
`--check` (Round 1's draft allowed `format --check`; this redesign drops
`format` outright, since this turn's instruction only asks for
`ruff check`, and the narrower shape is preferred when nothing needs the
wider one); every family requires at least one explicit positional
(never implicit/whole-repo/cwd-relative scope); every positional is
restricted to `backend/` via the existing `_is_safe_relative_path`
primitive plus a new bounded-root check, so this cannot be pointed at
`.claude/`/`knowledge/` even by an unexpected `pytest`/`mypy` plugin
argument; the venv binaries themselves are trusted by exact path, not
content-hash-pinned like `_ALLOWED_PYTHON_SCRIPTS`'s 11 entries — a
disclosed, deliberate difference (these binaries change on every
legitimate reinstall/upgrade, unlike the long-lived validator scripts,
so a hash-pin-every-time model would be operationally impractical, not
a stronger control) that the reviewer should weigh explicitly, not
inherit silently from the python-script mechanism's own convention.

### Regression tests required — exact, for both tiers

**Tier 1 (before it may be trusted as `ACTIVE`):**
- Positive: each of the 4 new dict entries, invoked as
  `python3 <script>` with no other arguments, is classified `ALLOW`.
- Positive: `python3 tools/tests/test_validate_repo_skeleton.py`
  specifically executes end-to-end once the patch lands, and reports
  `PASS — all 3 tests passed.` (this is the one Tier-1 script that can
  fully close its own loop with no further tooling).
- Negative: the same 4 scripts, with even one byte of tampered content
  (a modified copy at the same path), are denied
  (`_script_integrity_ok` returns `False`) — proves the hash-pin, not
  just the path-membership, is load-bearing (this is the exact class of
  regression `_ALLOWED_PYTHON_SCRIPTS`'s own governance note already
  requires for the existing 7 entries; extend, don't special-case).
- Negative: a 5th, never-listed script (e.g. a throwaway fixture at
  `tools/not_allowlisted.py`) is still denied — proves the mechanism
  stayed a fixed enumerated set, not a directory-prefix rule.
- Regression: all existing cases in `.claude/security/tests/test_bash_guard.py`
  for the original 7 scripts still pass unchanged.

**Tier 2 (before it may be trusted as `ACTIVE`, additional to Tier 1's):**
- Positive: `backend/.venv/bin/pytest backend/tests/unit` (and the
  `component`/`integration`/`contract` equivalents) → `ALLOW`.
- Positive: `backend/.venv/bin/ruff check backend/app` → `ALLOW`.
- Positive: `backend/.venv/bin/mypy backend/app` → `ALLOW`.
- Negative: `backend/.venv/bin/ruff format backend/app` → denied (no
  `format` subcommand recognized at all).
- Negative: `backend/.venv/bin/ruff check .claude/rules` → denied (path
  outside `backend/`).
- Negative: `backend/.venv/bin/pytest` with **no** positional argument →
  denied (never implicit/bare invocation).
- Negative: `backend/.venv/bin/pytest -p no:cacheprovider backend/tests/unit`
  → denied (`-p` not in `_PYTEST_FLAGS`; this is exactly the
  plugin-loading flag class this design deliberately excludes).
- Negative: a bare, PATH-resolved `pytest`/`ruff`/`mypy` (no
  `backend/.venv/bin/` prefix) → still `UNKNOWN_COMMAND`, proving the
  dispatch key's exact-path requirement is load-bearing, not
  coincidental.
- Regression: every Tier-1 and pre-existing case still passes unchanged.

## Disposition (Round 2)

**`BUG-036` remains OPEN.** Tier 1 is now fully specified and ready for
the owner to apply verbatim; Tier 2's install step has an explicit,
narrow recommended mechanism (`backend/.venv/bin/pip install`, owner/
human-terminal only, never through an agent session) and its guard
extension is drafted for review, not applied. No `.claude/security/**`
file was or could be edited by this session. No implementation slice was
started or continued.

## Next owner action (Round 2)

1. Apply Tier 1 verbatim (the 4-entry diff above) — independent of every
   other decision here.
2. Decide Tier 2(a): approve the `backend/.venv/` install mechanism
   (and, ideally in the same decision, approve pinning exact versions in
   `backend/pyproject.toml` before installing).
3. If approved, perform the install (`python3 -m venv backend/.venv`
   then `backend/.venv/bin/pip install ...`) **outside this guarded
   session** — owner's own terminal, or CI.
4. Route Tier 2(b)'s draft to a fresh-context `veyro-security-reviewer`
   (Opus) for independent review before it may reach `ACTIVE`.
5. After Tier 1 (and, once ready, Tier 2) land, a fresh session should
   re-run Slices 1-3's scripts and fixtures for real and correct their
   evidence from "hand-traced only" to actual pass/fail output.

## Round 3 (2026-09-26) — Tier 1 applied and verified with real execution; Tier 2 install materials prepared

**Owner applied Tier 1** (commit
`e971523c3a665020df601b685d8f4b092ead7052`, "fix: allow MOD-001
deterministic validators"). Mission this round: verify the applied patch
matches exactly, recompute all hashes fresh, run the full guard
regression suite, actually execute the 4 newly-allowlisted scripts and
record real results, then prepare (not apply) Tier 2's install
materials.

### Tier 1 verification

- Local HEAD == `origin/main` == `e971523c3a665020df601b685d8f4b092ead7052`
  — confirmed via `git rev-parse` both, plus `git fetch` first.
- `git show e971523` read in full: exactly 8 lines added to
  `.claude/security/bash_guard.py`, all 4 new dict entries, byte-identical
  to the drafted Round-2 patch — no other line touched, no new function,
  no new mechanism.
- All 4 target scripts' SHA-256 recomputed fresh via `shasum -a 256`
  (not reused from Round 2's record) — all 4 match the guard's newly
  committed entries exactly:
  ```
  b76c4f37491a858ccfb58d72a3f2a8d040f9862d6c80529113c1596bfbe0d70b  tools/validate_baseline_binding.py
  c53404eda5837f0754ab68e00699effb25a2f653bce2d8eacb98360217c99517  tools/validate_capability_manifest.py
  162750a3e8a52afb93cf6ed3087df3814e7d5cd9150a1e152f3f11f8cdaf5d91  tools/validate_repo_skeleton.py
  bcae0d8a81fdd41972b5398f14ded7bed806cc6f8c1a274316095ab8aa2ed919  tools/tests/test_validate_repo_skeleton.py
  ```
- `bash_guard.py`'s own hash necessarily changed as a result of the
  patch: `db768d05537f471b1cbabe7b6b96975087a8bef60f5496cc838bc3e9b0b93c59`
  (was `315df926ff607fb0560f4f1842646d28eeb2a059b771130db5002edb347cc245`).
  `CAPABILITY_REGISTRY.md`'s CAP-007 row updated to the new hash, with an
  explicit disclosure that this specific diff has not yet had its own
  independent Opus security review (carried forward from the pre-patch
  `APPROVED` verdict on the reasoning that it only extends the
  already-reviewed fixed-hash-dict mechanism with more entries of the
  same shape — not assumed equivalent to a fresh review, stated as owed).

### bash_guard regression result

**Ran the full existing suite for real, for the first time this
project's `bash_guard.py` history has been executed from inside a
guarded Claude Code session** (every prior run was by a human/CI outside
the guard, per every prior `BASH_GUARD_*` evidence file): `python3
.claude/security/tests/test_bash_guard.py` → **194 tests, 194 `ok`, `Ran
194 tests in 8.327s`, `OK`.** No regression from the Tier 1 patch.

### Four script execution results — real, not hand-traced

1. **`tools/validate_baseline_binding.py`** (no arguments) → real `PASS`
   against the actual `PROJECT_INDEX.md`/`SESSION_BOOTSTRAP.md`. Full
   output and updated traceability now in
   `evidence/implementation/SLICE-1-baseline-binding-validator-2026-09-19.md`'s
   new "Execution residual — CLOSED 2026-09-26" section.
2. **`tools/validate_capability_manifest.py`** — first attempt with no
   arguments exited 2 with a usage error (`--manifest` is required); not
   hidden — recorded honestly, then re-run correctly with `--manifest
   knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml` → real
   `PASS`, 9 Rule IDs discovered, all `APPROVED`. This is the opposite of
   the 2026-09-19 hand-trace's predicted `FAIL` — correctly so, since
   `RULE-001`..`009` were `BLOCKED` at trace time and are `APPROVED` now
   (`BUG-035` Round 5, 2026-09-25); the data changed, not the logic. One
   real, minor, disclosed finding: a `SyntaxWarning` (invalid `\s` escape
   in a non-raw string, line 19) — does not affect behavior, not filed as
   a bug, noted for a future cleanup pass. Full detail in
   `evidence/implementation/SLICE-2-capability-manifest-validator-2026-09-19.md`.
3. **`tools/validate_repo_skeleton.py`** (no arguments) → real `PASS`,
   all 7 required paths present.
4. **`tools/tests/test_validate_repo_skeleton.py`** (no arguments,
   self-contained — no `pytest` needed) → real `PASS — all 3 tests
   passed.`, including the `shutil.rmtree`-the-`backend/`-directory
   negative case. Both results now in
   `evidence/implementation/SLICE-3-backend-test-pyramid-skeleton-2026-09-25.md`'s
   new "Execution residual — PARTIALLY CLOSED 2026-09-26" section
   (`backend/tests/*/test_scaffold_live.py`'s own 4 `pytest`-dependent
   fixtures remain unexecuted — Tier 2's scope, unaffected by Tier 1).

**No PASS is claimed for anything not actually executed.** The 4
scaffold-liveness `pytest` fixtures, `ruff check`, and `mypy` against
`backend/` all remain unexecuted, honestly, pending Tier 2.

### Slice 1/2/3 evidence status

All 3 updated with a new dated section recording the real run above the
original (now explicitly marked "historical," not deleted) hand-traced-only
record, so both the trace-time reasoning and the live result are
preserved. No prior claim was edited to look like it "was always" a
verified PASS — each file states plainly what changed and when.

### Tier 2 — provenance/license/transitive-dependency review

Performed via PyPI's own package JSON metadata (`pypi.org/pypi/<name>/json`
and `/pypi/<name>/<version>/json`), cross-checked twice per package where
the result mattered (see the hash caveat below):

| Package | Latest stable | License | Source repo | Provenance |
|---|---|---|---|---|
| `pytest` | 9.1.1 | MIT | `github.com/pytest-dev/pytest` | Official `pytest-dev` org, "Development Status :: 6 - Mature," the de facto standard Python test runner |
| `ruff` | 0.16.9 | MIT | `github.com/astral-sh/ruff` | Official Astral Software Inc. (also maintains `uv`), a well-known, well-funded Python tooling vendor |
| `mypy` | 2.3.1 | MIT | `github.com/python/mypy` | Official `python` GitHub org, maintained by CPython core/typeshed-adjacent contributors including Guido van Rossum |

**Transitive dependencies** (from each package's own declared
`requires_dist`, quoted verbatim from the PyPI JSON, not summarized):
- `pytest`: `colorama` (Windows only), `exceptiongroup` (Python<3.11),
  `iniconfig`, `packaging`, `pluggy`, `pygments`, `tomli` (Python<3.11) —
  all small, ubiquitous, long-established packages already present
  throughout the Python ecosystem.
- `ruff`: **none** (`requires_dist: null`) — Ruff ships as a compiled
  Rust binary wrapped in a wheel; zero Python-level transitive dependency
  surface.
- `mypy`: `typing_extensions`, `mypy_extensions`, `pathspec`, `tomli`
  (Python<3.11), `librt` (non-PyPy only), `ast-serialize` — the last two
  are less familiar names, re-verified with a second, explicitly
  "verbatim, no summarization" fetch to rule out a fetch-tool
  transcription error; both appeared identically both times and are
  plausibly newer mypy-ecosystem packages (mypy has been incorporating
  compiled/Rust-adjacent runtime components) published under the same
  official distribution chain, not a third-party add-on.

**Known-vulnerability check:** searched for current CVEs/advisories
against all three. The only historical hit was `CVE-2022-42969`, in the
long-deprecated `py` library pytest used to depend on years ago —
disputed as non-reproducible by multiple parties even at the time, and
irrelevant regardless: `py` does not appear anywhere in pytest 9.1.1's
own `requires_dist` list above, confirming modern pytest does not carry
that dependency. No current CVE found against `ruff` or `mypy`.

**Disclosed limitation — wheel SHA-256 hashes NOT authored in
`backend/requirements-dev.txt`:** an early attempt to have this
session's own web-fetch tooling report each package's exact wheel
SHA-256 produced a value of implausible length on first attempt (a
transcription artifact of the fetch tool's own summarizing layer, not a
real PyPI value) — caught by manually counting hex characters before
using it, not after. Given a wrong hash in a security-relevant lock file
is worse than no hash (it fails closed for the wrong reason and teaches
nothing), this session deliberately did **not** hand-copy any SHA-256
wheel hash into the committed file. `backend/requirements-dev.txt`
therefore carries exact `==` version pins only, with an explicit comment
directing the owner to generate a real hash-lock (`pip-compile
--generate-hashes` or `pip download` + `pip hash`) on their own machine
at install time — the only place such a value should be trusted from.

### Exact pinned versions proposed (and applied to `backend/pyproject.toml`)

```
pytest==9.1.1
ruff==0.16.9
mypy==2.3.1
```

Applied this round: `backend/pyproject.toml`'s `[project.optional-dependencies].dev`
list changed from unpinned (`"pytest"`, `"ruff"`, `"mypy"`) to these
exact pins — a 3-line change, not a new implementation slice. New file
`backend/requirements-dev.txt` created with the same 3 pins plus the
hash-generation guidance above.

### Exact owner terminal commands (none run by this session; run outside Claude Code)

```bash
cd /Users/ahmadmabrouk/Desktop/Veyro

# 1. Create the project-local venv (already gitignored)
python3 -m venv backend/.venv

# 2. Install the exact-pinned dev tools
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements-dev.txt

# 3. Verify installation
backend/.venv/bin/pytest --version
backend/.venv/bin/ruff --version
backend/.venv/bin/mypy --version
```

Optional, recommended strengthening (generates the hash lock this
session deliberately did not author):

```bash
backend/.venv/bin/pip install pip-tools
backend/.venv/bin/pip-compile --generate-hashes \
    --output-file=backend/requirements-dev.lock.txt \
    backend/requirements-dev.txt
```

### Tier 2 readiness

**Install materials ready. Install not performed. Guard extension not
applied, not reviewed.** Tier 2(b)'s bash_guard draft (Round 2 section
above) is unchanged and still requires a fresh-context
`veyro-security-reviewer` (Opus) pass before it may reach `ACTIVE`, per
CAP-007's own stage-9 rule — this round did not touch it, per explicit
instruction.

### Disposition (Round 3)

**`BUG-036` remains OPEN**, narrowed: the `tools/**` half (4 scripts) is
now genuinely closed with real, observed execution evidence — not
hand-traced, not fabricated. The `pytest`/`ruff`/`mypy` half remains
open, with install materials fully prepared and the guard extension
drafted but neither applied. No `.claude/security/**` file was or could
be edited by this session beyond what the owner already applied. No
implementation slice was started or continued (the `backend/pyproject.toml`
pin change and the new `requirements-dev.txt` are supply-chain hygiene
for this same bug's remediation, not GOV-01-R0x product work).

### Next owner action (Round 3 — superseded by Round 4 below; "optionally
generate the hash lock" understated a real inconsistency, corrected)

1. Review the provenance/license/dependency findings above.
2. ~~Run the exact terminal commands above (venv create + pinned
   install) outside Claude Code.~~ **Superseded — see Round 4: those
   commands installed directly from the unlocked
   `backend/requirements-dev.txt`, contradicting this same round's own
   "generate a hash lock first" recommendation. Use Round 4's corrected
   sequence instead.**
3. ~~Optionally generate the hash lock (`pip-compile --generate-hashes`).~~
   **Superseded — Round 4 found this was never actually wired into the
   install sequence above, and re-evaluated whether `pip-tools` is even
   the right tool for this narrow a job.**
4. Route Tier 2(b)'s draft (Round 2 section above) to a fresh-context
   `veyro-security-reviewer` for independent review. (unchanged)
5. Once reviewed and applied, a fresh session should execute the 4
   `backend/tests/*/test_scaffold_live.py` fixtures via `pytest`, run
   `ruff check`/`mypy` against `backend/`, and record those real results
   the same way this round did for Tier 1's 4 scripts. (unchanged)

## Round 4 (2026-09-26) — reconciling a real inconsistency: lock-generation was described but never wired into the install sequence; pip-tools evaluated and rejected as unnecessary

**The owner caught a real defect in Round 3's own output**, not a
misunderstanding: Round 3 stated hashes "should" be generated via
`pip-compile --generate-hashes` (in `backend/requirements-dev.txt`'s own
comment block) but the "exact owner terminal commands" given in that
same round's report installed directly from the **unlocked**
`backend/requirements-dev.txt` via a plain `pip install -r`, never
generating or using any lock file at all. The two halves of Round 3's
own output contradicted each other. This round reconciles that,
end-to-end, as one consistent sequence.

### Decision: bare `pip` (`pip download` + `pip hash`), NOT `pip-tools`

`pip-tools` is **not required**. Reasons, weighed against
`CAPABILITY_POLICY.md`'s own "no capability may be granted broader scope
... than the specific gap requires" scope rule and this project's
established preference (`IMPLEMENTATION.md` §7, `CAPABILITIES.md`) for
"default to free/open-source/already-available tooling first":

1. **Bootstrapping/second-order-trust problem.** `pip-tools` would
   itself need installing before it can generate anything — via an
   unpinned, un-hash-verified `pip install pip-tools` (the exact
   unverified-install pattern this whole remediation exists to avoid),
   or via its own separately-authored pin+hash (which does not eliminate
   manual hash-authoring, it just relocates it one level up, from the 3
   target packages to `pip-tools` itself and *its own* transitive
   dependencies — a strictly larger surface for no corresponding
   benefit at this scale).
2. **Scope mismatch.** `pip-tools`'s real value is automatic, repeated
   transitive-dependency *resolution* across a large, frequently-changing
   dependency graph. This is 3 direct dev-tool pins with a small (~13
   package), low-churn transitive closure (dev tooling, not runtime
   deps) — resolved once, not on every commit. `pip download`
   (recursive by default) plus `pip hash` covers the exact same
   `--require-hashes`-compatible output for this size of job, using a
   tool (`pip` itself) already mandatory for the install regardless — no
   new package, no new provenance/license review, no new trust root.
3. **This is a one-time, careful, owner-run step, not a recurring CI
   job.** The manual assembly step (below) is exactly the kind of
   security-sensitive authoring this project's own convention already
   reserves for the owner's own trusted machine (`BUG-036` Tier 2(a)'s
   own "never through an agent's own Bash tool" principle) — a small
   amount of one-time manual care there is the correct trade, not a
   burden to engineer away with an extra dependency.

**Alternative deterministic hash-lock mechanism (bare `pip`, consistent
with this project's supply-chain governance):** `pip download` resolves
and downloads the full transitive closure (direct packages plus every
dependency `requires_dist` pulls in) to a local directory as `.whl`
files; `pip hash` computes each file's real SHA-256 directly, as a local
subprocess, with **no summarizing web-fetch layer in the loop at all** —
this is the exact property that was missing when this session's own
`WebFetch` tool produced an implausible-length hash in Round 3. The
owner then hand-assembles a `--require-hashes`-compatible requirements
file from that real, locally-computed output, and `pip install
--require-hashes` refuses to install anything not exactly matching —
fail-closed, the same property `_ALLOWED_PYTHON_SCRIPTS`'s own
hash-pinning already relies on elsewhere in this project.

### Exact owner terminal commands, corrected and consistent, in order (none run by this session)

```bash
cd /Users/ahmadmabrouk/Desktop/Veyro

# 1. Create the project-local venv and update pip
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip

# 2. Download the 3 direct packages AND their full transitive closure
#    (no --no-deps this time — the lock file must cover every package
#    a --require-hashes install will need, not just the 3 direct pins)
mkdir -p /tmp/veyro-wheels
backend/.venv/bin/pip download -r backend/requirements-dev.txt -d /tmp/veyro-wheels

# 3. Compute each downloaded wheel's real SHA-256 (local subprocess
#    output — trust this directly, unlike a web-fetched value)
backend/.venv/bin/pip hash /tmp/veyro-wheels/*.whl
```

**4. Hand-assemble `backend/requirements-dev.lock.txt`** — one block per
file step 3 printed (the 3 direct packages plus every transitive
dependency `pip download` resolved: expected to include at minimum
`colorama`/`exceptiongroup`/`iniconfig`/`packaging`/`pluggy`/`pygments`/
`tomli` for `pytest`, and `typing_extensions`/`mypy_extensions`/
`pathspec`/`tomli`/`librt`/`ast-serialize` for `mypy`, per Round 3's own
transitive-dependency review — `ruff` has none). Exact format
(pip's native `--require-hashes` requirements syntax, one entry per
resolved package):

```
pytest==9.1.1 \
    --hash=sha256:<value pip hash printed for the pytest wheel>
ruff==0.16.9 \
    --hash=sha256:<value pip hash printed for the ruff wheel>
mypy==2.3.1 \
    --hash=sha256:<value pip hash printed for the mypy wheel>
colorama==<version pip download resolved> \
    --hash=sha256:<value pip hash printed for it>
# ... one block per remaining transitive package pip download resolved
```

(Each version number in the lock file comes from the actual filename
`pip download` wrote to `/tmp/veyro-wheels/`, not guessed — e.g.
`colorama-0.4.6-py2.py3-none-any.whl` names the exact resolved
`0.4.6`.)

```bash
# 5. Install strictly from the hash-locked file — refuses anything
#    that doesn't match exactly
backend/.venv/bin/pip install --require-hashes -r backend/requirements-dev.lock.txt

# 6. Verify
backend/.venv/bin/pytest --version
backend/.venv/bin/ruff --version
backend/.venv/bin/mypy --version
```

### Exact file committed

`backend/requirements-dev.lock.txt` — does not exist yet, generated and
committed by the owner after running the commands above.
`backend/requirements-dev.txt` (already committed, Round 3) stays as the
human-authored, unlocked source-of-intent file — its own comment block
updated this round to point at the corrected sequence above and to stop
recommending the direct, unlocked `pip install -r
backend/requirements-dev.txt` this round found was never actually
consistent with the rest of that file's own text.

### Whether any new owner decision is required

**No new decision beyond what Round 3 already asked for.** Tier 2(a)'s
original approval (project-local `backend/.venv` only, exact-pinned
versions, owner installs manually, no agent pip-install capability) already
covers this — this round only corrects *how* the hash-lock half of that
approval is actually carried out, it does not introduce a new capability,
new package, or new risk class. Choosing bare `pip` over `pip-tools`
is a tooling-mechanism decision within the scope Round 3's approval
already granted, not a fresh DC-19 supply-chain decision on its own
(there is no new third-party package being introduced by this choice —
that is precisely why it was chosen over the `pip-tools` alternative).

### Tier 2 install readiness (Round 4)

**Materials now internally consistent.** `backend/requirements-dev.txt`'s
own comment corrected to match the actual recommended sequence.
`backend/requirements-dev.lock.txt` does not exist yet — generating it is
the owner's own next step, using the exact commands above. Tier 2(b)'s
`bash_guard.py` extension draft (Round 2) is unchanged, still not applied,
still needs independent review.

### Disposition (Round 4)

**`BUG-036` remains OPEN**, unchanged scope from Round 3 (the `tools/**`
half closed with real execution; the `pytest`/`ruff`/`mypy` half open).
No install was performed. No `.claude/security/**` file was touched. No
implementation slice was started or continued — the
`backend/requirements-dev.txt` comment correction is the same class of
supply-chain-hygiene documentation fix Round 3's `pyproject.toml`
version-pinning was, not product work.

### Next owner action (Round 4)

1. Run the corrected 6-step sequence above (venv → download → hash →
   hand-assemble the lock file → `--require-hashes` install → verify),
   outside Claude Code.
2. Commit `backend/requirements-dev.lock.txt`.
3. Route Tier 2(b)'s guard-extension draft (Round 2 section) to a
   fresh-context `veyro-security-reviewer` for independent review.
4. Once reviewed and applied, a fresh session should execute the 4
   `backend/tests/*/test_scaffold_live.py` fixtures via `pytest`, run
   `ruff check`/`mypy` against `backend/`, and record those real results
   the same way Round 3 did for Tier 1's 4 scripts.
