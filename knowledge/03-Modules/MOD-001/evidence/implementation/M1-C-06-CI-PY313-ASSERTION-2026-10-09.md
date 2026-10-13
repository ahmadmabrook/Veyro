# M1-C-06 — CI CPython 3.13 interpreter assertion (local-equivalent component)

Date: 2026-10-09. Substep of
`M1-C-06-MYPY-CI-LOCK-ARCHITECTURE-2026-10-09.md` (§4; acceptance B2, B9).
Implementation only. No PASS, no APPROVED, no scenario/status change.

## Artifacts (SHA-256)

- `tools/assert_ci_python313.py` — `ea51c067d5d75ff2ba1bb7602e37a0a5c88f9908a18c40d957d65b825a4a3d9c`
- `tools/tests/test_assert_ci_python313.py` — `a10abecd32f3e9a0776d265ee5ee853f8c874af247f1074af0996e6fd5713b7f`

## Behaviour

Stdlib only. Pure `check_interpreter(implementation, version_info, platform,
maxsize)` returns all four checks (no short-circuit); `all_passed` denies on an
empty set. `main` prints executable path, full `sys.version`, each check with
its observed value, then `RESULT: ALLOW` (exit 0) or `RESULT: DENY` (exit 1).
Checks: implementation `cpython`; `version_info[:2] == (3, 13)` exactly;
`sysconfig.get_platform()` starts `linux-x86_64`; `sys.maxsize > 2**32`.
Malformed injected values deny rather than raise; `bool` maxsize denies.

## Observed results (host: macOS arm64, `backend/.venv/bin/python` 3.14.5)

- `python -m unittest tools.tests.test_assert_ci_python313 -v`: 14 tests, OK
  (13 pure injected-value positive/negative cases + 1 live exit-code
  consistency check). Built-in unittest, not pytest.
- `python -I tools/assert_ci_python313.py`: exit 1, `RESULT: DENY` — as
  expected on this host: cpython PASS; version_is_3_13 FAIL (observed 3.14);
  platform_is_linux_x86_64 FAIL (observed `macosx-26.0-arm64`); is_64_bit PASS.
  This is a host observation, not a CI outcome.
- `py_compile` of both files: rc 0.
- `git diff --check`: rc 0 (covers tracked changes only; new files separately
  grepped for trailing whitespace: none).
- `backend/.venv/bin/python knowledge/00-System/verify_baselines.py`: 4/4
  baselines MATCH, PASS.

## Not done / not claimed

No workflow authored, no wheel acquired, no lock/generator/registry/manifest/
scenario/status change, mypy neither installed nor run, CAP-012 not applied,
no reviewer dispatched, no remote mutation. The local run is not evidence that
CI behaves identically; live CI execution, the runner's default-`python3`
negative (B7) and the wiring of this script into a workflow (B2) remain open.
SCN-MOD001-030/031 remain NOT EXECUTED; MOD-001 exit 0/8 unchanged.
