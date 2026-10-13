"""
Synthetic-only governed-shape qualification drill for gitleaks 8.30.1
(MOD-001, M1-C-06 mandatory R03 correction; see
knowledge/03-Modules/MOD-001/evidence/security/
M1-C-06-CAPABILITY-SECURITY-DETERMINATION-2026-10-09.md §6.3 items 2-3).

Qualification-drill fixture, not CI evidence and not a capability approval.
It complements (does not replace) test_gitleaks_qualification.py. Every scan
target is a disposable pytest `tmp_path` tree outside the Veyro repository;
only `gitleaks dir` runs; no Veyro file, Git index or history is touched.

The binary under test is the contained upstream darwin-arm64 binary named by
$VEYRO_GITLEAKS_BIN (extracted from the SHA-256-verified release archive in a
disposable directory). The Homebrew binary is NOT eligible: the test pins the
executable's own SHA-256 and fails closed on any mismatch.

For each suppression surface (inline `gitleaks:allow`, `.gitleaksignore`,
`--baseline-path`) the same planted fake token is shown to be
  * suppressed by the default invocation shape, and
  * still detected under the governed shape (`_governed_scan`).
A control scan proves each default-shape "clean" result is caused by the
suppression and not by an empty or non-matching target. Output is value-free;
the credential-shaped value is an EXAMPLE_NOT_A_REAL_KEY placeholder built at
runtime from fragments.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

PINNED_VERSION = "8.30.1"
PINNED_BINARY_SHA256 = "ba52fb1bfabbcde42f032afad3d6e0b19dff8ed105229a16e7caa338bbc0e84f"
LEAK_EXIT_CODE = 42  # distinct from 0 (clean) and 1 (gitleaks runtime error)
REPO_ROOT = Path(__file__).resolve().parents[2]

# EXAMPLE_NOT_A_REAL_KEY: synthetic GitHub-PAT-shaped value, joined at runtime.
_FAKE_TOKEN = "ghp_" + "Q7xK2mP9" + "vL4nR8tW" + "3yB6cD1e" + "F5gH0jZs" + "A2uN"
_BANNER = "# EXAMPLE_NOT_A_REAL_KEY -- synthetic qualification fixture, not a credential.\n"
PLAIN = f'{_BANNER}GITHUB_TOKEN = "{_FAKE_TOKEN}"\n'
INLINE_ALLOWED = f'{_BANNER}GITHUB_TOKEN = "{_FAKE_TOKEN}"  # gitleaks:allow\n'


class GovernedScanRefused(Exception):
    """Wrapper-side fail-closed refusal (precondition the tool cannot enforce)."""


def _gitleaks() -> str:
    path = os.environ.get("VEYRO_GITLEAKS_BIN")
    if not path or not Path(path).is_file():
        pytest.fail("VEYRO_GITLEAKS_BIN must name the hash-verified upstream gitleaks binary")
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest != PINNED_BINARY_SHA256:
        pytest.fail(f"gitleaks binary SHA-256 {digest} != pinned upstream {PINNED_BINARY_SHA256}")
    return path


def _run(
    argv_tail: list[str], target: Path, work: Path
) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    report = work / "report.json"
    report.unlink(missing_ok=True)
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
            *argv_tail,
            str(target),
        ],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    findings = json.loads(report.read_text()) if report.is_file() else []
    return result, findings


def _default_scan(target: Path, work: Path, *extra: str):
    # Default shape: `-i` left at its default ("."), inline allow honoured,
    # baseline only if the caller passes one. cwd=work (outside the repo).
    return _run(list(extra), target, work)


def _governed_scan(target: Path, work: Path):
    """Governed invocation. Preconditions the tool cannot enforce are checked here."""
    target = target.resolve()
    work = work.resolve()
    for path in (target, work):
        if REPO_ROOT == path or REPO_ROOT in path.parents:
            raise GovernedScanRefused("path inside Veyro repository")
    if not target.is_dir():
        raise GovernedScanRefused("target is not a directory")
    files = [p for p in target.rglob("*") if p.is_file() and p.stat().st_size > 0]
    if not files:
        raise GovernedScanRefused("zero non-empty files: vacuous scan")  # non-vacuity
    if (target / ".gitleaksignore").exists():
        # gitleaks 8.30.1 reads <target>/.gitleaksignore even when `-i` points
        # elsewhere; no flag disables it, so the wrapper refuses.
        raise GovernedScanRefused("target-root .gitleaksignore cannot be disabled by flag")
    empty = work / "empty-ignore-dir"
    empty.mkdir(exist_ok=True)
    assert not any(empty.iterdir())
    # No --baseline-path, ever. --ignore-gitleaks-allow, `-i` -> empty dir.
    return _run(["--ignore-gitleaks-allow", "-i", str(empty)], target, work)


def _fingerprints(target: Path, work: Path) -> list[str]:
    _, findings = _governed_scan(target, work)
    return [f["Fingerprint"] for f in findings]


@pytest.fixture()
def tree(tmp_path: Path) -> tuple[Path, Path]:
    target, work = tmp_path / "target", tmp_path / "work"
    target.mkdir()
    work.mkdir()
    return target, work


def _assert_detected(result, findings) -> None:
    assert result.returncode == LEAK_EXIT_CODE
    assert len(findings) == 1
    assert findings[0]["RuleID"] == "github-pat"
    assert _FAKE_TOKEN not in json.dumps(findings) + result.stdout + result.stderr


def _assert_suppressed(result, findings) -> None:
    assert result.returncode == 0
    assert findings == []


def test_binary_is_pinned_upstream_version() -> None:
    out = subprocess.run([_gitleaks(), "version"], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == PINNED_VERSION


def test_unsuppressed_control_is_detected_in_both_shapes(tree) -> None:
    target, work = tree
    (target / "p.py").write_text(PLAIN)
    _assert_detected(*_default_scan(target, work))
    _assert_detected(*_governed_scan(target, work))


def test_inline_allow_suppressed_by_default_detected_when_governed(tree) -> None:
    target, work = tree
    (target / "p.py").write_text(INLINE_ALLOWED)
    assert (target / "p.py").stat().st_size > 0
    _assert_suppressed(*_default_scan(target, work))
    _assert_detected(*_governed_scan(target, work))


def test_gitleaksignore_in_cwd_suppressed_by_default_detected_when_governed(tree) -> None:
    target, work = tree
    (target / "p.py").write_text(PLAIN)
    fps = _fingerprints(target, work)
    assert len(fps) == 1
    (work / ".gitleaksignore").write_text("\n".join(fps) + "\n")
    _assert_suppressed(*_default_scan(target, work))
    _assert_detected(*_governed_scan(target, work))


def test_gitleaksignore_in_target_root_suppresses_and_governed_refuses(tree) -> None:
    # Documents the inability: `-i <empty dir>` does NOT defeat a target-root
    # .gitleaksignore, so the governed shape must refuse rather than pass.
    target, work = tree
    (target / "p.py").write_text(PLAIN)
    fps = _fingerprints(target, work)
    (target / ".gitleaksignore").write_text("\n".join(fps) + "\n")
    _assert_suppressed(*_default_scan(target, work))
    empty = work / "empty-ignore-dir"
    empty.mkdir(exist_ok=True)
    _assert_suppressed(*_run(["--ignore-gitleaks-allow", "-i", str(empty)], target, work))
    with pytest.raises(GovernedScanRefused):
        _governed_scan(target, work)


def test_baseline_suppressed_by_default_detected_when_governed(tree) -> None:
    target, work = tree
    (target / "p.py").write_text(PLAIN)
    _, baseline_findings = _governed_scan(target, work)
    assert len(baseline_findings) == 1
    baseline = work / "baseline.json"
    baseline.write_text(json.dumps(baseline_findings))
    _assert_suppressed(*_default_scan(target, work, "--baseline-path", str(baseline)))
    # Governed shape never passes --baseline-path, so the same target is detected.
    _assert_detected(*_governed_scan(target, work))


def test_governed_invocation_never_carries_a_baseline_flag() -> None:
    source = Path(__file__).read_text()
    governed = source.split("def _governed_scan", 1)[1].split("def _fingerprints", 1)[0]
    assert '"--baseline-path"' not in governed and '"-b"' not in governed


@pytest.mark.parametrize("case", ["empty_dir", "only_empty_file", "file_target", "inside_repo"])
def test_governed_wrapper_refuses_vacuous_or_out_of_scope_targets(tree, case: str) -> None:
    target, work = tree
    if case == "only_empty_file":
        (target / "e.py").write_text("")
    elif case == "file_target":
        (target / "p.py").write_text(PLAIN)
        target = target / "p.py"
    elif case == "inside_repo":
        target = REPO_ROOT / "tools"  # path check only; refused before any scan
    with pytest.raises(GovernedScanRefused):
        _governed_scan(target, work)


@pytest.mark.parametrize("excluded", ["node_modules/p.py", "p.docx"])
def test_default_global_allowlist_misses_planted_placeholder_and_manifest_declares_it(
    tree, excluded: str
) -> None:
    # C09-X item 3 (allowlist non-vacuity). The placeholder is planted in a path the
    # shipped default global allowlist excludes. Control: the same content outside
    # such a path is detected in both shapes, so the miss is caused by the path.
    target, work = tree
    (target / "ctrl").mkdir()
    (target / "ctrl" / "p.py").write_text(PLAIN)
    _assert_detected(*_default_scan(target, work))
    _assert_detected(*_governed_scan(target, work))
    (target / "ctrl" / "p.py").unlink()
    (target / "ctrl").rmdir()
    planted = target / excluded
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(PLAIN)
    assert planted.stat().st_size > 0
    # Default shape and governed shape both miss it: the governed flags do not change
    # the allowlist, and the wrapper's non-empty-file check passes (vacuous pass).
    _assert_suppressed(*_default_scan(target, work))
    _assert_suppressed(*_governed_scan(target, work))
    # Honest C09-X branch: not detected under governed configuration, so the species is
    # declared out of coverage in the reviewed target manifest, with the affected paths.
    manifest = json.loads((REPO_ROOT / "tools" / "governed_scanner_targets.json").read_text())
    declared, tracked = manifest["declared_allowlist_excluded"], manifest["tracked"]
    assert declared and manifest["declared_allowlist_excluded_count"] == len(declared)
    if excluded.endswith(".docx"):
        assert declared == [t for t in tracked if t.endswith(".docx")]
    else:
        assert not [t for t in tracked if "node_modules/" in t]  # species absent from set


def test_tool_fails_closed_on_missing_target_and_malformed_config(tree) -> None:
    target, work = tree
    (target / "p.py").write_text(PLAIN)
    result, findings = _run([], work / "does_not_exist", work)
    assert result.returncode not in (0, LEAK_EXIT_CODE) and findings == []
    bad = work / "malformed.toml"
    bad.write_text("[[rules]\nid = \n this is not valid toml {{{\n")
    result, findings = _run(["--config", str(bad)], target, work)
    assert result.returncode not in (0, LEAK_EXIT_CODE) and findings == []
