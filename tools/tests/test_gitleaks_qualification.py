"""
Synthetic-only stage-5 qualification drill for gitleaks (MOD-001, M1-C-06,
GOV-01-R03 / TSD §24.1 secret-scanning shape).

This is a qualification-drill fixture, not CI evidence and not a capability
approval: gitleaks has no row in CAPABILITY_REGISTRY.md, so it is only ever
pointed at throwaway files this test writes into a pytest `tmp_path` — never
at the Veyro working tree, the Git index, or Git history. Only `gitleaks dir`
is used; no `git` subcommand is ever invoked.

The credential-shaped value is an explicitly fake, labelled placeholder
(EXAMPLE_NOT_A_REAL_KEY, per .claude/rules/infra/secrets.md control 1). It is
assembled at runtime from fragments so this source file never contains a
complete credential-shaped literal for a repo-wide scanner to trip on.

  1. test_fixture_set_is_nonempty — both synthetic files exist before the
     scanner runs (a scan of zero files would be a vacuous pass).
  2. test_planted_fixture_is_detected — fake token -> leak exit code, one
     finding, expected rule id, value redacted in the report.
  3. test_clean_fixture_is_clean — clean companion -> exit 0, no findings.
  4. test_malformed_*_fails_closed — unparseable config / missing target ->
     nonzero exit that is neither success nor the leak exit code.

Output is value-free: assertions look only at exit codes, rule ids and file
names.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PINNED_GITLEAKS_VERSION = "8.30.1"
LEAK_EXIT_CODE = 42  # distinct from 0 (clean) and 1 (gitleaks runtime error)

# EXAMPLE_NOT_A_REAL_KEY: synthetic GitHub-PAT-shaped value, fragments joined
# at runtime. Not issued by any service; carries no access.
_FAKE_TOKEN = "ghp_" + "Q7xK2mP9" + "vL4nR8tW" + "3yB6cD1e" + "F5gH0jZs" + "A2uN"

PLANTED_SOURCE = f"""\
# EXAMPLE_NOT_A_REAL_KEY -- synthetic qualification fixture, not a credential.
GITHUB_TOKEN = "{_FAKE_TOKEN}"
"""

CLEAN_SOURCE = """\
# Synthetic qualification fixture: clean companion, no credential-shaped values.
import os

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
"""


def _gitleaks() -> str:
    found = shutil.which("gitleaks")
    if found is None:
        pytest.fail("gitleaks executable not found; install is out of scope for this test")
    return found


@pytest.fixture()
def fixtures(tmp_path: Path) -> dict[str, Path]:
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    planted = scan_root / "planted_fixture.py"
    clean = tmp_path / "clean" / "clean_fixture.py"
    clean.parent.mkdir()
    planted.write_text(PLANTED_SOURCE)
    clean.write_text(CLEAN_SOURCE)
    return {"planted": planted, "clean": clean}


def _scan(
    target: Path, workdir: Path, *extra: str
) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    # cwd=workdir (a tmp dir) so the default `.gitleaksignore` lookup and
    # default-config discovery never touch the Veyro tree; no --config means
    # the built-in default ruleset unless `extra` supplies one.
    report = workdir / "report.json"
    result = subprocess.run(
        [
            _gitleaks(),
            "dir",
            "--no-banner",
            "--no-color",
            "--redact=100",
            "--exit-code",
            str(LEAK_EXIT_CODE),
            "--report-format",
            "json",
            "--report-path",
            str(report),
            *extra,
            str(target),
        ],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    findings = json.loads(report.read_text()) if report.is_file() else []
    return result, findings


def test_gitleaks_is_pinned_version() -> None:
    result = subprocess.run([_gitleaks(), "version"], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == PINNED_GITLEAKS_VERSION


def test_fixture_set_is_nonempty(fixtures: dict[str, Path]) -> None:
    assert fixtures
    assert all(path.is_file() and path.stat().st_size > 0 for path in fixtures.values())


def test_planted_fixture_is_detected(fixtures: dict[str, Path], tmp_path: Path) -> None:
    result, findings = _scan(fixtures["planted"].parent, tmp_path)
    assert result.returncode == LEAK_EXIT_CODE
    assert len(findings) == 1
    assert findings[0]["RuleID"] == "github-pat"
    assert Path(findings[0]["File"]).name == "planted_fixture.py"
    # Redaction: the fake value must not be echoed in the report or output.
    assert _FAKE_TOKEN not in json.dumps(findings)
    assert _FAKE_TOKEN not in result.stdout + result.stderr


def test_clean_fixture_is_clean(fixtures: dict[str, Path], tmp_path: Path) -> None:
    result, findings = _scan(fixtures["clean"].parent, tmp_path)
    assert result.returncode == 0
    assert findings == []


def test_malformed_config_fails_closed(fixtures: dict[str, Path], tmp_path: Path) -> None:
    bad_config = tmp_path / "malformed.toml"
    bad_config.write_text("[[rules]\nid = \n this is not valid toml {{{\n")
    result, findings = _scan(fixtures["planted"].parent, tmp_path, "--config", str(bad_config))
    assert result.returncode not in (0, LEAK_EXIT_CODE)
    assert findings == []


def test_missing_target_fails_closed(tmp_path: Path) -> None:
    result, findings = _scan(tmp_path / "does_not_exist", tmp_path)
    assert result.returncode not in (0, LEAK_EXIT_CODE)
    assert findings == []
