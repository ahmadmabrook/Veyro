## What happened chunk 62, 2026-09-26 — BUG-036 Round 5: hardened the Tier-2 install plan before the owner ran it — no pip upgrade, wheel-only acquisition, eliminated manual lock transcription via a new generator/checker script, portability stated honestly

Continuation of chunk 61's `BUG-036` reconciliation. Before running the
install, the owner asked for 4 further hardening fixes: an unpinned
`pip install --upgrade pip` bootstrap step; wheel-only acquisition to
guarantee no source-distribution build path runs; verification that
required packages have compatible wheels for the owner's actual macOS/
Python environment before proceeding; and elimination of the remaining
manual transcription risk in assembling `backend/requirements-dev.lock.txt`.
Explicitly: do not install anything, do not touch the Tier-2 guard, do
not start another implementation slice, keep `BUG-036` `OPEN`.

**Bootstrap re-verified fresh:** local HEAD == `origin/main` ==
`7f66f1b6668df6908fab36f63723f62542e8a294` (chunk 61's own commit).
Re-read `backend/pyproject.toml`, `backend/requirements-dev.txt`, and
`BUG-036`'s own file before changing anything.

**1. pip bootstrap — decided against upgrading.** `pip install --upgrade
pip` was itself an unpinned, un-hash-verified mutation, one level
removed from the exact problem this remediation exists to close.
Decision: use whatever pip `python3 -m venv` bundles via `ensurepip`,
unchanged — `--only-binary=:all:` (pip ≥7.1) and `--require-hashes`
(pip ≥8) are both old, stable features any Python 3.13 build's bundled
pip comfortably supports, so there is no functional reason to add a
second unpinned thing to the sequence. `pip --version` remains available
as a read-only diagnostic, not a decision point.

**2. Wheel-only acquisition — `pip download --only-binary=:all:`.**
Confirmed as the exact mechanism: refuses to fall back to a source
distribution for any package in the closure, failing loudly (naming the
package) rather than silently running build-backend code — a failure
here is a new, separate decision point, never something to route around
by dropping the flag for just that package.

**3. Environment-compatibility verification — deferred honestly to the
owner's own machine.** This session has no `pip` access and no knowledge
of the owner's exact CPU architecture or Python 3.13 patch build, so it
cannot itself confirm wheel availability. Stated plainly: a best-effort
desk check (all three are mainstream wheel-first-distribution projects)
is not a substitute for the real verification, which is simply the
owner's own `pip download --only-binary=:all:` succeeding on their real
machine — the same lesson this bug's own Round 3 already taught once,
when a `WebFetch`-sourced value proved unreliable for a security-relevant
detail.

**4. Eliminating manual lock-file transcription.** Built
`tools/generate_requirements_lock.py` (stdlib-only: `argparse`,
`hashlib`, `pathlib`, `sys` — no dependency on `packaging`): `generate`
derives every package name and version by parsing real wheel filenames
(PEP 427/600 naming) and every hash via `hashlib.sha256` on the real
file bytes, so no value in the lock file is ever hand-typed; `check` is
an independent second code path that re-derives the same values from a
wheel directory and diffs them against an existing lock file, proving
directly: every wheel appears exactly once, every version is exact,
every hash is exact, and no lock entry lacks a matching wheel — a
duplicate package name in the wheel directory is also a hard, named
failure, never a silent pick-one. `tools/tests/test_generate_requirements_lock.py`
proves both directions against synthetic, isolated fixtures (a clean
round trip; a hand-tampered hash, an extra lock entry, and a duplicate
wheel name each fail closed). Neither script has been executed —
disclosed honestly, same structural `bash_guard.py` gap as every other
MOD-001 tool, verified instead by hand-tracing every code path against
the test file's own cases.

**Exact 6-step owner sequence, corrected and hardened:** venv create
(no pip upgrade) → `pip --version` (diagnostic) → `pip download
--only-binary=:all: -r backend/requirements-dev.txt -d /tmp/veyro-wheels`
→ `generate_requirements_lock.py generate` → `generate_requirements_lock.py
check` → `pip install --require-hashes -r backend/requirements-dev.lock.txt`
→ verify with `--version` on all three tools. If the download step fails
naming a package, stop — do not drop the wheel-only flag to work around
it.

**Portability stated honestly, not implied:** the resulting lock file is
specific to the exact macOS/architecture/Python-3.13-build it is
generated on (`ruff`/`mypy` ship platform-specific wheels, unlike
`pytest`'s universal one) — not portable to a different platform or
Python minor version without regenerating. A future need for a second
platform's lock (e.g. Linux CI) is a distinct decision, not assumed
solved here.

**Durable state updated this chunk:**
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-036-no-local-deterministic-test-execution-capability.md`
(new "Round 5" section; Round 4's own stale next-action item struck
through and pointed at this correction); 2 new files
(`tools/generate_requirements_lock.py`,
`tools/tests/test_generate_requirements_lock.py`);
`backend/requirements-dev.txt` (comment corrected to the hardened
sequence, no dependency change); `BUG_REGISTRY.md` (row + front matter +
new "Corrected" note); `STATUS.md`'s "Implementation progress" section;
`CURRENT_HANDOFF.md` (chunk 60 compressed/archived per the retention rule to make
room, this chunk added in full).

**Disposition:** `BUG-036` remains `OPEN`, unchanged scope. No install
performed. No `.claude/security/**` file touched. No Tier-2 security
review run, per explicit instruction. No implementation slice started.
MOD-001 remains `IMPLEMENTATION IN PROGRESS`, not approved. WIP remains 1.

**Next legally allowed action:** owner runs the 6-step sequence above,
outside Claude Code; if the download step fails for any package, stop
and report which one rather than working around it; commits
`backend/requirements-dev.lock.txt` once `generate`/`check` both report
`PASS`; routes Tier 2(b)'s `bash_guard.py`-extension draft (unchanged
since Round 2) to a fresh-context `veyro-security-reviewer` for
independent review. Once reviewed and applied, a fresh session should
execute the 4 `backend/tests/*/test_scaffold_live.py` fixtures via
`pytest`, run `ruff check`/`mypy` against `backend/`, and record those
real results the same way Round 3 did for Tier 1's 4 scripts. Not
another implementation slice in the meantime.
