---
doc: M1-C-06-LINUX-CP313-IMPORTED-CLOSURE
module: MOD-001
date: 2026-10-09
classification: MANDATORY_NOW — GOV-01-R04 type-check CI supply-chain prerequisite
status: LOCAL_LOCK_EXPANSION_VERIFIED; no capability approval, CI result or scenario disposition
---

# M1-C-06 — Linux cp313 lock expanded to the imported third-party closure

Implements `M1-C-06-TYPECHECK-TARGET-CLOSURE-ARCHITECTURE-2026-10-09.md` §9 (Option A,
`backend/app` target kept) by extending the additive lock from
`M1-C-06-LINUX-CP313-TYPECHECK-LOCK-ACQUISITION-2026-10-09.md`. Direct roots:
`mypy==2.3.1`, `pytest==9.1.1`, `psycopg[binary]==3.3.6` (imported by
`backend/app/modules/conftest.py` and the six scaffold modules via the local harness).
`ruff` and unrelated dev packages excluded. Local inert-byte evidence only.

## Commands

- Interpreter: `backend/.venv/bin/python` (3.14.5, pip 26.1.1; download/generator only).
- Scratch versions-only constraints (outside repo, `/tmp/m1c06-imported-constraints.*`):
  the six pre-existing pins (`mypy`, `ast-serialize`, `librt`, `mypy-extensions`,
  `pathspec`, `typing-extensions`) — retains existing transitive versions; no hashes.
- Two fresh empty dirs, `/tmp/m1c06-imported-a.BiRKbL05` (A) and
  `/tmp/m1c06-imported-b.PQcZ44Zk` (B), each an independent run of:

```
env -u PIP_INDEX_URL -u PIP_EXTRA_INDEX_URL -u PIP_FIND_LINKS -u PIP_NO_INDEX \
    -u PIP_TARGET -u PIP_PREFIX -u PIP_CONSTRAINT PIP_CONFIG_FILE=/dev/null \
  backend/.venv/bin/python -m pip download --only-binary=:all: \
    --platform manylinux_2_17_x86_64 --python-version 3.13 --implementation cp --abi cp313 \
    --index-url https://pypi.org/simple --no-cache-dir --no-input --disable-pip-version-check \
    -c <scratch constraints> --dest <A|B> 'mypy==2.3.1' 'pytest==9.1.1' 'psycopg[binary]==3.3.6'
```

No `pip install`; no wheel extracted, imported or executed; mypy not invoked; no Veyro path
typechecked.

## Observed results

- Exit codes: A=0, B=0 (both: "Successfully downloaded" 13 packages). No sdist, no extra entry.
- A/B `shasum -a 256` manifests (filename-sorted) are **byte-identical** (`cmp` clean).
- 13 wheels (name==version, sha256):

| Wheel | SHA-256 |
|---|---|
| ast_serialize-0.11.2-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64 | a7004ba5…2c51bbc |
| iniconfig-2.3.1-py3-none-any (new) | 9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7 |
| librt-0.15.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64 | 234d8d39…4281d2 |
| mypy-2.3.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64 | 1c80fbc4…dd5226 |
| mypy_extensions-1.1.0-py3-none-any | 1be4cccd…f5505 |
| packaging-26.3-py3-none-any (new) | d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c |
| pathspec-1.1.1-py3-none-any | a00ce642…b189 |
| pluggy-1.6.0-py3-none-any (new) | e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746 |
| psycopg-3.3.6-py3-none-any (new) | a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631 |
| psycopg_binary-3.3.6-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64 (new) | cec5ea900390897d0b46130f60bc2883bf19c314f9044235217c8be88b0ef269 |
| pygments-2.21.0-py3-none-any (new) | 2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9 |
| pytest-9.1.1-py3-none-any (new) | 37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c |
| typing_extensions-4.16.0-py3-none-any | 481caa48…70c2e8 |

  (Full digests for the six pre-existing wheels are in the manifest file.) Seven new wheels:
  `iniconfig`, `packaging`, `pluggy`, `psycopg`, `psycopg-binary`, `pygments`, `pytest`.
- **Previous-six invariant:** all six prior filename/digest pairs are present and unchanged in
  the new manifest; all six pins and all six hashes are retained in the new lock.
- **Official index verification:** each of the 13 wheel filename/sha256 pairs was compared
  against PyPI JSON (`/pypi/<name>/<version>/json` `urls[].digests.sha256`): 13/13 MATCH.
- **Generator:** unchanged (SHA-256 `c32436be…02b8c`). `generate <A>` exit 0 (13 packages,
  written to a scratch lock then copied to the repository after checks); `check <B>` exit 0;
  `check <A>` exit 0. No package installation occurred.
- **Changed files:**
  - `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt` — SHA-256
    `5e7596d408190a6103ffe1e3988f1c88ea33a34306302cc7de6f0570340e95de` (was `2bb541f7…9725`).
  - `backend/requirements-typecheck-linux-x86_64-cp313.wheels.sha256` — SHA-256
    `78177a9b5e86bd72e31a710b4d692a069b2979797f0aaf610d4e7d8b68ec5c4b` (was `7105f2d9…1c22`);
    mechanically produced from A's `shasum -a 256 *.whl`, line-sorted as the prior file was
    (line set identical to both A and B manifests).
- **Unchanged:** `backend/requirements-dev.lock.txt` SHA-256
  `5b9383fe128cb1d7d8b8442c82fe305988980915140215f4a4f5e3adcbe2d698`; generator, pyproject,
  requirements-dev.txt, old macOS lock, source, CI, registry, ledger, plan: untouched.

## Platform / marker limitation

`pip download` evaluates environment markers against the host (macOS, CPython 3.14.5, arm64),
not the cross-target flags. Checked against PyPI `requires_dist`: the only marker-gated edges
are `colorama; sys_platform=="win32"`, `exceptiongroup`/`tomli; python_version<"3.11"` (pytest),
`typing-extensions; python_version<"3.13"` and `tzdata; sys_platform=="win32"` (psycopg). All
evaluate false on both host and Linux/3.13 target, so the closure is identical for the target
(typing-extensions enters via mypy regardless). Re-verify if a root or pin changes.

## Boundary

Nothing here installs or runs mypy/pytest, approves CAP-012, creates a CI result or required
status, dispatches a reviewer, or dispositions any scenario/gate. The synthetic nested-layout
drill (target-closure §10/§11) was completed separately; real Linux/CI behavior, CI workflow
execution and capability-assurance dependencies remain open. MOD-001 stays active; WIP=1 preserved. Both new files remain untracked/modified
in the working tree, not committed.
