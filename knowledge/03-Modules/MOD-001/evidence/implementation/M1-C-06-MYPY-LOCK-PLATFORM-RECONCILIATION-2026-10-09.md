---
doc: M1-C-06-MYPY-LOCK-PLATFORM-RECONCILIATION
module: MOD-001
date: 2026-10-09
type: deterministic read-only provenance reconciliation
requirement: GOV-01-R04 type-check CI stage; CAP-012
status: MANDATORY_NOW lock-platform mismatch identified; no capability approval
---

# CAP-012 lock-platform boundary

At 2026-10-09 11:47 UTC, the sole orchestrator compared the six mypy-closure
pins in `backend/requirements-dev.lock.txt` with the published SHA-256 digests
in each exact-version PyPI JSON release record (`https://pypi.org/pypi/<name>/<version>/json`).
The three compiled-package records are
`https://pypi.org/pypi/mypy/2.3.1/json`,
`https://pypi.org/pypi/ast-serialize/0.11.2/json`, and
`https://pypi.org/pypi/librt/0.15.0/json`.
No wheel was downloaded, installed, imported or executed; no Veyro source was
type-checked. This is PyPI metadata reconciliation, **not** a signature or
attestation verification, installed-tree origin proof, CI run, or approval.

| Package | Current lock SHA-256 identifies | Candidate Linux x86-64 / Python 3.13 artifact and PyPI SHA-256 |
|---|---|---|
| mypy 2.3.1 | `mypy-2.3.1-cp314-cp314-macosx_11_0_arm64.whl` — `192abaedf75da1bc0b1cef104927e70ec49c1ef0031cc4825c7ee10a438ed24d` | `mypy-2.3.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` — `1c80fbc405ed8020f5ff3802dc18cf060197bcdd3fbdd6a26ef2fd34dfdd5226` |
| ast-serialize 0.11.2 | `ast_serialize-0.11.2-cp39-abi3-macosx_11_0_arm64.whl` — `1844ed9a487fb3de7325c52ddb33f2918b66b65cd54d3f8d83d23785ffe99fa4` | `ast_serialize-0.11.2-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` — `a7004ba572f09be34342ccb98dcd4bad5707d3d81adc8cb4c3f685d2a2c51bbc` |
| librt 0.15.0 | `librt-0.15.0-cp314-cp314-macosx_11_0_arm64.whl` — `6c0eb900c0e91f4aebe680845242e614f1864edfd44106380d0752ac29522bf8` | `librt-0.15.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` — `234d8d394721fa0d786af15ebf1f3fb7f3ed82fd1cd0cde45c2f247b5d4281d2` |

The remaining three closure pins match platform-independent wheels:
`mypy_extensions-1.1.0-py3-none-any.whl`,
`pathspec-1.1.1-py3-none-any.whl`, and
`typing_extensions-4.16.0-py3-none-any.whl` (their exact current lock hashes
matched one published release file each). PyPI also publishes a universal
`mypy-2.3.1-py3-none-any.whl`, but neither ast-serialize nor librt has a
universal wheel. The three current compiled pins therefore cannot be assumed
to satisfy a Linux x86-64 hash-enforced installation. That is a metadata-based
inference, **not** an executed CI failure.

The currently observed workflows use Ubuntu 24.04 or `ubuntu-latest`, while
`backend/pyproject.toml` requires Python >=3.13; no final type-check CI
interpreter/platform has yet been fixed. The current lock generator
`tools/generate_requirements_lock.py` accepts only one wheel/hash per package
and rejects duplicate package wheels. A Linux-specific lock generated and
independently checked from the actual selected Linux wheel bytes is the
smallest apparent correction; a multi-platform generator extension is not
needed merely to satisfy one pinned CI platform. Select the CI interpreter
first, then use a guarded Sonnet implementation substep to create the minimum
lock/install path and deterministic positive/negative evidence. Do not hand
transcribe PyPI hashes into a governed lock. Do not alter the current macOS
lock or run mypy on real project files before CAP-012's separate independent
Opus determination and APPROVED exact-scope registration.

Classification: **MANDATORY_NOW** within existing M1-C-06 (GOV-01-R04's
blocking type-check stage cannot install reproducibly on the intended CI
runner from macOS-only compiled hashes); no new bounded operation, scenario
PASS, review entitlement, or owner stop. CAP-012 remains QUALIFIED only.
