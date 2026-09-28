## What happened chunk 61, 2026-09-26 — BUG-036 Round 4: reconciled a real inconsistency in the Tier-2 install plan (lock-generation described but never wired in); pip-tools evaluated and rejected; corrected bare-pip mechanism defined

Continuation of chunk 60's `BUG-036` remediation. Before performing the
Tier-2 install, the owner caught a genuine inconsistency in chunk 60's
own output: `backend/requirements-dev.txt`'s comment recommended
generating a hash lock via `pip-compile --generate-hashes`, but the
"exact owner terminal commands" given in that same chunk's report
installed directly from the unlocked file via a plain `pip install -r`
— the lock-generation step was described but never actually used.
Mission: reconcile this, decide the exact deterministic dependency-
locking mechanism (preferring the smallest project-local solution),
and — if `pip-tools` turns out to be required — give its own pinned
version and provenance review; if not, explain why and give the
alternative. Explicitly: do not install anything, do not touch the
Tier-2 guard, keep `BUG-036` `OPEN`, no new implementation slice.

**Bootstrap re-verified fresh:** local HEAD == `origin/main` ==
`8015a1d4a3f0b1cb86859cdec852786ec592831e` (chunk 60's own commit).
Re-read `backend/pyproject.toml`, `backend/requirements-dev.txt`, and
`BUG-036`'s own file to confirm the inconsistency directly rather than
take the owner's description on trust — confirmed: the file's own
comment named `pip-compile --generate-hashes` as the "preferred" path,
but nothing in the prior chunk's install commands or in the file's own
"Install this file with" line ever generated or referenced a lock file.

**Decision: bare `pip` (`pip download` + `pip hash`), NOT `pip-tools`.**
Weighed against `CAPABILITY_POLICY.md`'s "no capability may be granted
broader scope... than the specific gap requires" scope rule and this
project's "default to free/open-source/already-available tooling
first" convention: `pip-tools` would need its own unpinned bootstrap
install (the exact unverified-install pattern this remediation exists
to avoid) or its own separate pin+hash review (relocating the
manual-hash problem one level up, to `pip-tools` itself and its own
transitive dependencies, not solving it) — for a resolution feature
(automatic transitive-dependency resolution across a large,
frequently-changing graph) this narrow a job (3 direct pins, ~13-package
low-churn transitive closure, resolved once, not on every commit) does
not need. Bare `pip download` (recursive by default, resolves the full
closure) + `pip hash` (real local-subprocess SHA-256, no summarizing
web-fetch layer in the loop — the exact property missing when chunk
60's own `WebFetch` attempt produced an implausible-length hash)
achieves the same `--require-hashes`-compatible result using a tool
(`pip`) already mandatory for the install regardless.

**Corrected sequence defined, end-to-end, consistent this time:**
create `backend/.venv` → `pip download -r backend/requirements-dev.txt
-d /tmp/veyro-wheels` (full closure, no `--no-deps`) → `pip hash
/tmp/veyro-wheels/*.whl` → owner hand-assembles
`backend/requirements-dev.lock.txt` (pip's native `--require-hashes`
format, one `name==version` + `--hash=sha256:...` block per resolved
file, including every transitive package, not just the 3 direct ones)
→ `pip install --require-hashes -r backend/requirements-dev.lock.txt` →
verify with `--version` on all three. `backend/requirements-dev.txt`'s
own comment block corrected to point at this sequence and explicitly
state it is the unlocked source-of-intent file, not an install target.

**No new owner decision required** beyond chunk 60's own Tier 2(a)
approval (project-local venv, exact-pinned versions, owner installs
manually, no agent pip-install capability) — this only corrects *how*
the hash-lock half of that approval is carried out; no new package, no
new capability, no new risk class is introduced by choosing bare `pip`
over `pip-tools`.

**Durable state updated this chunk:**
`knowledge/03-Modules/MOD-001/evidence/bugs/BUG-036-no-local-deterministic-test-execution-capability.md`
(new "Round 4" section; Round 3's own stale "optionally generate the
hash lock" next-action item struck through and pointed at this
correction); `backend/requirements-dev.txt` (comment block corrected —
no code/dependency change, same 3 version pins); `BUG_REGISTRY.md` (row
+ front matter + new "Corrected" note); this file (chunk 59
compressed/archived per the retention rule to make room, this chunk
added in full).

**Disposition:** `BUG-036` remains `OPEN`, unchanged scope from Round 3.
No install performed. No `.claude/security/**` file touched. No
implementation slice started — the `requirements-dev.txt` comment fix is
the same class of supply-chain-hygiene documentation correction Round 3's
`pyproject.toml` pinning was, not product work. MOD-001 remains
`IMPLEMENTATION IN PROGRESS`, not approved. WIP remains 1.

**Next legally allowed action:** owner runs the corrected 6-step
sequence above (venv → download → hash → hand-assemble the lock file →
`--require-hashes` install → verify) outside Claude Code, commits
`backend/requirements-dev.lock.txt`; routes Tier 2(b)'s
`bash_guard.py`-extension draft (unchanged since Round 2) to a
fresh-context `veyro-security-reviewer` for independent review. Once
reviewed and applied, a fresh session should execute the 4
`backend/tests/*/test_scaffold_live.py` fixtures via `pytest`, run
`ruff check`/`mypy` against `backend/`, and record those real results the
same way Round 3 did for Tier 1's 4 scripts. Not another implementation
slice in the meantime.
