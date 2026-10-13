---
doc: M1-C-06-LINUX-CP313-WHEEL-ACQUISITION-BLOCK
module: MOD-001
date: 2026-10-09
status: BLOCKED_AT_ACQUISITION; no lock generated or capability approved
---

# M1-C-06 Linux cp313 wheel acquisition — observed blocker

Under the sole runner lease, after contract refresh and a `CLEAR` live
`operation_loop.py` assessment for M1-C-06, the local deterministic §11.5
acquisition step was attempted. The fresh, empty out-of-repository directory
was `/tmp/m1c06-typecheck-a.aNSD9Q`. The interpreter was
`backend/.venv/bin/python` (Python 3.14, pip 26.1.1); this was a cross-target
**download only**, not execution of a downloaded wheel.

Command shape:

```text
PIP_CONFIG_FILE=/dev/null backend/.venv/bin/python -m pip download \
  --only-binary=:all: --platform manylinux_2_28_x86_64 \
  --python-version 3.13 --implementation cp --abi cp313 \
  --dest /tmp/m1c06-typecheck-a.aNSD9Q mypy==2.3.1
```

It exited 1. Pip selected metadata for the expected mypy 2.3.1 cp313
manylinux wheel, but selected **librt 0.16.0**, not the six-pin precedent's
0.15.0. It then reported:

```text
ERROR: Could not find a version that satisfies the requirement ast-serialize<1.0.0,>=0.6.0 (from mypy) (from versions: 0.0.1)
ERROR: No matching distribution found for ast-serialize<1.0.0,>=0.6.0
```

No `PIP_INDEX_URL` or `PIP_EXTRA_INDEX_URL` environment variable was present.
An otherwise identical retry with explicit
`--index-url https://pypi.org/simple` exited 1 with the same resolution error.
The destination remained empty (`ls -la` showed no downloaded wheel).
There was no B download, no generator invocation, no lock or hash manifest.

The published candidate `ast_serialize-0.11.2` wheel documented in
`M1-C-06-MYPY-LOCK-PLATFORM-RECONCILIATION-2026-10-09.md` carries
`manylinux_2_17_x86_64`/`manylinux2014_x86_64` tags, not the command's
`manylinux_2_28_x86_64` tag. This is a **likely compatibility cause**, not
yet a proven pip resolver root cause. Separately, an unconstrained
`librt>=0.13.0` now resolves 0.16.0, so the earlier asserted exact six-version
closure is no longer reproduced by the proposed command. Both observations
are material discrepancies against §3/§11.5's stop-on-divergence condition.

**Disposition:** M1-C-06 remains in progress/blocked at this substep. Do not
retry the same command or silently add `--no-deps`, change platform tags, pin
transitives, or generate a lock from a partial set. The next legal bounded
action is an ARCHITECTURE_CRITICAL reconciliation of the target-tag and
version-selection contract against current package metadata and the required
CI interpreter, producing a corrected exact acquisition command or a specific
blocker. This is a changed technical subgoal, not a capability approval,
review, or scenario result.

No wheel was installed, imported, extracted, or executed; no mypy run, CI
workflow edit, registry/manifest change, remote action, reviewer dispatch,
scenario PASS, or MOD-001 certification credit occurred. R04 gate-2 F01-F14
remain 14/14 closed.
