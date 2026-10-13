"""
Synthetic-only qualification preparation for Ruff `S` (flake8-bandit) as a
SAST candidate (MOD-001, GOV-01-R03 / SCN-134 negative+positive shape).

This is a qualification-drill fixture, not CI evidence and not a capability
approval: Ruff's security rules are unregistered in CAPABILITY_REGISTRY.md,
so `--select S` is only ever pointed at the two throwaway files this test
writes into a temporary directory — never at Veyro source or any real
project file.

  1. test_fixture_set_is_nonempty — both synthetic files exist before the
     scanner runs (a scan of zero files would be a vacuous pass).
  2. test_insecure_fixture_is_flagged_s608 — hardcoded SQL string
     concatenation -> S608, nonzero exit.
  3. test_corrected_fixture_is_clean — the parameterized companion -> exit 0,
     no findings.

Output is value-free: assertions look only at rule codes and file names.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PINNED_RUFF_VERSION = "0.16.9"

INSECURE_SOURCE = """\
def lookup(cursor, user_id):
    query = "SELECT name FROM accounts WHERE id = " + user_id
    cursor.execute(query)
"""

CORRECTED_SOURCE = """\
def lookup(cursor, user_id):
    cursor.execute("SELECT name FROM accounts WHERE id = %s", (user_id,))
"""


def _ruff() -> str:
    beside_python = Path(sys.executable).parent / "ruff"
    found = str(beside_python) if beside_python.exists() else shutil.which("ruff")
    if found is None:
        pytest.fail("ruff executable not found; install is out of scope for this test")
    return found


@pytest.fixture()
def fixtures(tmp_path: Path) -> dict[str, Path]:
    insecure = tmp_path / "insecure_fixture.py"
    corrected = tmp_path / "corrected_fixture.py"
    insecure.write_text(INSECURE_SOURCE)
    corrected.write_text(CORRECTED_SOURCE)
    return {"insecure": insecure, "corrected": corrected}


def _scan(path: Path) -> tuple[int, list[dict]]:
    # --isolated: ignore any repo/user Ruff config; explicit file only.
    result = subprocess.run(
        [
            _ruff(),
            "check",
            "--isolated",
            "--no-cache",
            "--select",
            "S",
            "--output-format",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def test_ruff_is_pinned_version() -> None:
    result = subprocess.run([_ruff(), "--version"], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == f"ruff {PINNED_RUFF_VERSION}"


def test_fixture_set_is_nonempty(fixtures: dict[str, Path]) -> None:
    assert fixtures
    assert all(path.is_file() and path.stat().st_size > 0 for path in fixtures.values())


def test_insecure_fixture_is_flagged_s608(fixtures: dict[str, Path]) -> None:
    returncode, findings = _scan(fixtures["insecure"])
    assert returncode != 0
    assert "S608" in {finding["code"] for finding in findings}


def test_corrected_fixture_is_clean(fixtures: dict[str, Path]) -> None:
    returncode, findings = _scan(fixtures["corrected"])
    assert returncode == 0
    assert findings == []
