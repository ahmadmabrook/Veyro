---
doc: BUG-036
status: OPEN — OWNER ACTION NEEDED (patch drafted below, not applied; Tier 2 also needs an owner policy decision before it can even be drafted for review)
found_date: 2026-09-25
found_by: this session, dispatched specifically to investigate the recurring CAP-007 execution block after Slices 1-3 all disclosed it independently
severity: P1 (degrades MOD-001's implementation evidence quality project-wide and blocks Gatekeeper certification's real-execution requirement; does NOT block continued implementation-slice authoring, since slices may still hand-trace logic and disclose execution as honestly BLOCKED, per established precedent)
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
