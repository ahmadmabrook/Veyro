---
doc: HANDOFF_ARCHIVE_CHUNK_59
status: ARCHIVED
archived: 2026-09-26 (forty-third retention-rule application, chunk 61)
---

# Archived: CURRENT_HANDOFF.md chunk 59 (2026-09-26)

Full original text, preserved verbatim for evidence continuity. See
`CURRENT_HANDOFF.md` for the current compressed summary line and pointer
to this file.

---

## What happened chunk 59, 2026-09-26 — BUG-036 remediation planning: owner confirmed pytest/ruff/mypy not installed; Tier 1 patch finalized with fresh hashes; Tier 2 redesigned around an owner-side venv install

Continuation of chunk 58's `BUG-036` investigation, per an explicit
follow-up instruction: the owner ran an environment check outside Claude
Code and confirmed `pytest`/`ruff`/`mypy` are not installed anywhere this
host exposes — resolving chunk 58's open question. Mission: finalize the
exact Tier-1 owner patch with freshly-recomputed (not reused) SHA-256
hashes, define the minimal owner decision needed to install
`pytest`/`ruff`/`mypy`, recommend the narrowest install mechanism, draft
(not apply) the Tier-2 guard patch for the exact bounded shapes needed
after installation, and define exact regression tests for both tiers —
explicitly no implementation slice, no `.claude/security/**` edit,
`BUG-036` stays `OPEN`.

**Bootstrap re-verified fresh:** local HEAD == `origin/main` ==
`ab5473fe0cd5380a71851eb726a2d054029a67df` (chunk 58's own commit).
`.claude/security/bash_guard.py`'s own SHA-256 independently
re-recomputed — unchanged (`315df926ff607fb0560f4f1842646d28eeb2a059b771130db5002edb347cc245`).
The 4 target scripts' hashes recomputed fresh via `shasum -a 256` rather
than reused from chunk 58's record (confirmed identical, since none of
the 4 files changed between turns — verified, not assumed).

**Tier 1 finalized:** the exact 4-line diff to
`_ALLOWED_PYTHON_SCRIPTS` (no other line changes, no new mechanism) is
now ready for the owner to apply verbatim. Newly-allowed/still-denied
command lists spelled out precisely.

**Tier 2 redesigned**, given "not installed" is now confirmed: the
narrowest install mechanism is a project-local `backend/.venv/`
(already gitignored since Slice 3), installed by the owner or a human
terminal — **never through an agent's own Bash tool**, since `pip
install` fetches and can execute arbitrary third-party code, a
different risk class from anything this guard's Class A/B already
permits. Recommended, alongside the install decision: pin
`backend/pyproject.toml`'s currently-floating `pytest`/`ruff`/`mypy` dev
deps to exact versions first (not applied this chunk — outside this
turn's own scope, flagged as a natural follow-up commit). The guard
extension itself now keys its 3 new command families on the **exact
venv-relative binary path** (`backend/.venv/bin/{pytest,ruff,mypy}`)
rather than a bare, PATH-ambiguous command name — matching
`_python_readonly`'s own exact-script-path philosophy — bounded to
`backend/**` only (not `tools/**`, which Tier 1 already fully covers),
and drops `ruff format` entirely rather than gating it (only
`ruff check` was asked for). Exact positive/negative regression tests
defined for both tiers, including tampered-hash and unlisted-script
negatives for Tier 1, and bounded-path/no-implicit-invocation/wrong-flag
negatives for Tier 2.

**Durable state updated this chunk:**
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-036-no-local-deterministic-test-execution-capability.md`
(new "Round 2" section — finalized Tier 1 diff, redesigned Tier 2 draft,
exact regression tests, front matter updated); `BUG_REGISTRY.md` (row +
front matter + new "Corrected" note); this file (chunk 57
compressed/archived per the retention rule to make room, this chunk
added in full).

**Disposition:** `BUG-036` remains `OPEN`. No `.claude/security/**` file
was or could be edited by this session. No implementation slice was
started or continued. MOD-001 remains `IMPLEMENTATION IN PROGRESS`, not
approved. WIP remains 1.

**Next legally allowed action:** owner applies Tier 1 verbatim
(independent of everything else); owner decides Tier 2(a) (approve the
`backend/.venv/` install mechanism, ideally alongside pinning exact
versions in `backend/pyproject.toml`); if approved, the install itself
happens outside this guarded session; Tier 2(b)'s draft then routes to a
fresh-context `veyro-security-reviewer` (Opus) before it may reach
`ACTIVE`. After either tier lands, a fresh session should re-run Slices
1-3's scripts and fixtures for real. Not another implementation slice in
the meantime.
