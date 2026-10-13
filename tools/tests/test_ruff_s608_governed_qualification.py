"""
Synthetic-only governed-shape qualification drill for Ruff 0.16.9 `S608`
under the repository's real configuration (MOD-001, M1-C-06 mandatory R03
correction; see knowledge/03-Modules/MOD-001/evidence/security/
M1-C-06-CAPABILITY-SECURITY-DETERMINATION-2026-10-09.md §7.4 item 1).

Qualification-drill fixture, not CI evidence and not a capability approval.
It complements test_sast_ruff_qualification.py (which uses --isolated). Here
`--isolated` is NOT used: the repository's committed Ruff config is loaded via
an explicit `--config <repo file>` (config read only; Ruff is never pointed at
any Veyro source). Every scan target is a disposable pytest `tmp_path` file
outside the repository, so config auto-discovery cannot find the repo config
by itself and `--config` is the only way it is applied.

Shows: `# noqa: S608` suppresses by default and is defeated by
`--ignore-noqa`; the governed invocation lists a nonempty explicit target set
first (`--show-files`); exit 1 (findings) is distinct from exit 2 (tool
error); and the vacuous / missing-target `rc 0` that Ruff itself returns is
refused by the wrapper. Output is value-free (rule codes and file names).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
RUFF = REPO_ROOT / "backend" / ".venv" / "bin" / "ruff"
PINNED_VERSION = "ruff 0.16.9"
PINNED_BINARY_SHA256 = "8b799e53434b026a3e80aef658c06c3c98f9fb4cfc4eae379a16313936509e57"
REPO_CONFIGS = [REPO_ROOT / "ruff.toml", REPO_ROOT / "backend" / "pyproject.toml"]
ALLOWED_CONFIG_KEYS = {"line-length", "target-version"}

BAD = 'def f(c, u):\n    q = "SELECT n FROM a WHERE id = " + u\n    c.execute(q)\n'
SUPPRESSED = (
    'def f(c, u):\n    q = "SELECT n FROM a WHERE id = " + u  # noqa: S608\n    c.execute(q)\n'
)
CLEAN = 'def f(c, u):\n    c.execute("SELECT n FROM a WHERE id = %s", (u,))\n'


class GovernedScanRefused(Exception):
    """Wrapper-side fail-closed refusal for conditions Ruff reports as rc 0."""


def _ruff() -> str:
    if not RUFF.is_file():
        pytest.fail("backend/.venv/bin/ruff not found")
    digest = hashlib.sha256(RUFF.read_bytes()).hexdigest()
    if digest != PINNED_BINARY_SHA256:
        pytest.fail(f"ruff binary SHA-256 {digest} != verified {PINNED_BINARY_SHA256}")
    return str(RUFF)


def _check(config: Path, targets: list[Path], work: Path, *flags: str):
    result = subprocess.run(
        [
            _ruff(),
            "check",
            "--config",
            str(config),
            "--no-cache",
            "--no-fix",
            "--select",
            "S",
            "--output-format",
            "json",
            *flags,
            *map(str, targets),
        ],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result


def _codes(result) -> set[str]:
    return {f["code"] for f in json.loads(result.stdout)} if result.stdout.strip() else set()


def _governed_check(config: Path, targets: list[Path], work: Path):
    """Governed `S` invocation: explicit nonempty targets, --ignore-noqa, no write mode."""
    work = work.resolve()
    if REPO_ROOT in [work, *work.parents]:
        raise GovernedScanRefused("work dir inside Veyro repository")
    resolved = [t.resolve() for t in targets]
    for t in resolved:
        if REPO_ROOT in [t, *t.parents]:
            raise GovernedScanRefused("target inside Veyro repository (this drill is synthetic)")
        if not t.exists() or (t.is_file() and t.stat().st_size == 0):
            raise GovernedScanRefused(f"missing or empty target: {t.name}")
    listed = subprocess.run(
        [
            _ruff(),
            "check",
            "--config",
            str(config),
            "--no-cache",
            "--select",
            "S",
            "--show-files",
            *map(str, resolved),
        ],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    files = {Path(line).resolve() for line in listed.stdout.splitlines() if line.strip()}
    if listed.returncode != 0 or not files:
        raise GovernedScanRefused("zero files would be checked: vacuous scan")
    if not all(any(f == t or t in f.parents for f in files) for t in resolved):
        raise GovernedScanRefused("an explicit target yields no checked file (ignored/excluded)")
    return _check(config, resolved, work, "--ignore-noqa")


@pytest.fixture()
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    target, work = tmp_path / "target", tmp_path / "work"
    target.mkdir()
    work.mkdir()
    return target, work


@pytest.fixture(params=REPO_CONFIGS, ids=lambda p: p.parent.name + "/" + p.name)
def config(request) -> Path:
    return request.param


def test_binary_is_verified_pinned_version() -> None:
    out = subprocess.run([_ruff(), "--version"], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == PINNED_VERSION


def test_repo_config_has_no_select_extend_exclude_surface() -> None:
    # Guards the determination's §7.2 premise: only two trivial keys, so
    # `--config` of a repo file faithfully represents "the repo config".
    ruff_toml = tomllib.loads(REPO_CONFIGS[0].read_text())
    pyproject = tomllib.loads(REPO_CONFIGS[1].read_text())["tool"]["ruff"]
    assert set(ruff_toml) <= ALLOWED_CONFIG_KEYS
    assert set(pyproject) <= ALLOWED_CONFIG_KEYS


def test_default_and_governed_shapes_on_unsuppressed_fixture(dirs, config) -> None:
    target, work = dirs
    bad = target / "bad.py"
    bad.write_text(BAD)
    rc, res = _check(config, [bad], work)
    assert rc == 1 and _codes(res) == {"S608"}
    rc, res = _governed_check(config, [bad], work)
    assert rc == 1 and _codes(res) == {"S608"}


def test_noqa_suppresses_by_default_and_ignore_noqa_detects(dirs, config) -> None:
    target, work = dirs
    sup = target / "suppressed.py"
    sup.write_text(SUPPRESSED)
    assert sup.stat().st_size > 0
    rc, res = _check(config, [sup], work)  # default shape
    assert rc == 0 and _codes(res) == set()
    rc, res = _governed_check(config, [sup], work)  # governed shape
    assert rc == 1 and _codes(res) == {"S608"}


def test_clean_fixture_is_clean_when_governed(dirs, config) -> None:
    target, work = dirs
    clean = target / "clean.py"
    clean.write_text(CLEAN)
    rc, res = _governed_check(config, [clean], work)
    assert rc == 0 and _codes(res) == set()


def test_tool_error_exit_is_distinct_from_findings_exit(dirs) -> None:
    target, work = dirs
    bad = target / "bad.py"
    bad.write_text(BAD)
    broken = work / "broken.toml"
    broken.write_text("line-length = [\n")
    rc_error, _ = _check(broken, [bad], work)
    rc_finding, _ = _check(REPO_CONFIGS[0], [bad], work)
    assert (rc_error, rc_finding) == (2, 1)


def test_ruff_itself_is_vacuous_on_empty_and_missing_targets(dirs) -> None:
    # Documents the tool limit the wrapper must close: both return rc 0, no findings.
    target, work = dirs
    empty_dir = target / "empty"
    empty_dir.mkdir()
    for missing_or_empty in (empty_dir, target / "nope.py"):
        rc, res = _check(REPO_CONFIGS[0], [missing_or_empty], work)
        assert rc == 0 and _codes(res) == set()


@pytest.mark.parametrize("case", ["empty_dir", "missing", "zero_byte_file", "inside_repo"])
def test_governed_wrapper_refuses_vacuous_targets(dirs, case: str) -> None:
    target, work = dirs
    if case == "empty_dir":
        (target / "e").mkdir()
        targets = [target / "e"]
    elif case == "missing":
        targets = [target / "nope.py"]
    elif case == "zero_byte_file":
        (target / "z.py").write_text("")
        targets = [target / "z.py"]
    else:
        targets = [REPO_ROOT / "tools" / "tests" / "test_ruff_s608_governed_qualification.py"]
    with pytest.raises(GovernedScanRefused):
        _governed_check(REPO_CONFIGS[0], targets, work)


def test_gitignore_hides_files_from_discovery_but_not_explicit_targets(dirs) -> None:
    # respect-gitignore defaults to true: a gitignored tree reached by directory
    # discovery is skipped (wrapper refuses the vacuous result), while an
    # explicitly named file is still checked and detected.
    target, work = dirs
    ignored = target / "ignored_dir"
    ignored.mkdir()
    (ignored / "bad.py").write_text(BAD)
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    (target / ".gitignore").write_text("ignored_dir/\n")
    with pytest.raises(GovernedScanRefused):
        _governed_check(REPO_CONFIGS[0], [target], work)
    rc, res = _governed_check(REPO_CONFIGS[0], [ignored / "bad.py"], work)
    assert rc == 1 and _codes(res) == {"S608"}


def test_syntax_error_is_not_mistaken_for_an_s_finding(dirs) -> None:
    target, work = dirs
    broken = target / "syn.py"
    broken.write_text("def (\n")
    rc, res = _governed_check(REPO_CONFIGS[0], [broken], work)
    assert rc == 1 and "S608" not in _codes(res) and "invalid-syntax" in _codes(res)
