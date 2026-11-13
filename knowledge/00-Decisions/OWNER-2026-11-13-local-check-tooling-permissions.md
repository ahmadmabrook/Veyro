# Local check tooling may install the hash-pinned locks

Date: 2026-11-13
Scope: `.claude/settings.json` only. No product behaviour, no migration, no runtime privilege.

## What the owner instructed

On 2026-11-13 the owner was asked whether to allow installing `backend/requirements-dev.lock`
into the repository's `.venv`, because the local checks could not run without it. The owner
answered yes, and added that the session may edit `.claude/settings.json` itself rather than
coming back for permission each time something blocks it.

That instruction is recorded here rather than in the settings file's own comment, because a file
should not be the only witness to the authority that permits it.

## What changed, and what deliberately did not

Removed from `deny`: `Bash(pip install*)`, `Bash(python -m pip install*)`,
`Bash(python3 -m pip install*)`.

Added to `allow`, naming the lock files explicitly: the two `--require-hashes -r
backend/requirements*.lock` forms for both `pip` and `uv pip`, `uv pip compile*`, and the three
check commands (`ruff`, `mypy`, `unittest`) run through `.venv/bin/python3`.

Unchanged: `sudo*`, `brew install*` and `npm install*` stay denied. The first two change the
machine rather than this project. `npm install` was briefly removed in the first version of this
change and has been put back: this repository has no npm dependency tree, so removing it bought
nothing, and an unexplained removal is worse than no removal.

**Installing an arbitrary package is still not allowed.** `uv pip install <name>` and
`pip install <name>` are not on the allowlist and still prompt. An earlier version of this change
allowed `Bash(uv pip install*)` with a wildcard, which would have run any package with no
confirmation — the exact thing the reasoning below says is prevented. That was caught in review
and narrowed before it was committed.

## Why this is the right place for the guard

Every dependency this repository uses is declared in `backend/requirements.txt` or
`requirements-dev.txt` and hash-pinned in the matching `.lock`, regenerated with
`uv pip compile … --generate-hashes`. An install from a lock is reproducible, and a dependency
nobody reviewed appears as a lock diff in a commit, which is where a human can actually see it.

A shell-pattern deny was not catching that. It caught the repository's own check tooling, so
`ruff`, `mypy` and the 535-test suite could not run locally. That does not prevent a bad
dependency; it just moves the first failure from a developer's terminal to CI, and makes a red
`main` more likely rather than less. CLAUDE.md already says a local red is cheaper than a red
`main`, and this rule was working against that.

## What this does not authorize

Nothing about runtime database privilege, tenant isolation, the owner-reserved actions in
`governance/registry.json`, or the baseline pins. The `PROJECT_INDEX.md` and `.docx` deny rules
are untouched: adopting an edited baseline means re-pinning `PROJECT_INDEX.md` and
`governance/registry.json` together, and that deny is what forces the re-pin to be a deliberate
act rather than a side effect of some other edit.
