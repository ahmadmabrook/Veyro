"""
Deterministic synthetic tests for tools/governed_scanner_preflight.py
(MOD-001, M1-C-06; the C09-X / C10-X reviewable-target-set work).

No scanner is executed against any Veyro file, index, history or copy of those
files anywhere in this file. Ruff runs only against pytest `tmp_path` fixtures
outside the repository, which is CAP-010's APPROVED (BOUNDED) synthetic scope;
the repository's committed Ruff config is read via `--config` and is never a
target. gitleaks is not executed at all: the only local binary is the Homebrew
one, which CAP-009 records as ineligible for every scope, so this file covers
the gitleaks side through wrapper-side logic (argv, preconditions, digest
eligibility, exit classification, redaction). Executed gitleaks behaviour lives
in test_gitleaks_governed_qualification.py, which uses the hash-verified
upstream binary.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import governed_scanner_preflight as gsp  # matches the tools/tests import convention

REPO_ROOT = Path(__file__).resolve().parents[2]
RUFF_BIN = REPO_ROOT / "backend" / ".venv" / "bin" / "ruff"
RUFF_CONFIG = REPO_ROOT / "ruff.toml"

# EXAMPLE_NOT_A_REAL_KEY: synthetic PAT-shaped value, joined at runtime so no
# credential-shaped literal is committed (`.claude/rules/infra/secrets.md` 1).
_FAKE_TOKEN = "ghp_" + "Q7xK2mP9" + "vL4nR8tW" + "3yB6cD1e" + "F5gH0jZs" + "A2uN"
_BANNER = "# EXAMPLE_NOT_A_REAL_KEY -- synthetic fixture, not a credential.\n"
PLANTED = f'{_BANNER}GITHUB_TOKEN = "{_FAKE_TOKEN}"\n'

S608_BAD = 'def f(c, u):\n    q = "SELECT n FROM a WHERE id = " + u\n    c.execute(q)\n'
S608_NOQA = (
    'def f(c, u):\n    q = "SELECT n FROM a WHERE id = " + u  # noqa: S608\n    c.execute(q)\n'
)
S608_CLEAN = 'def f(c, u):\n    c.execute("SELECT n FROM a WHERE id = %s", (u,))\n'


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """A disposable git repo standing in for Veyro, with the three bound files."""
    repo = tmp_path / "fake-repo"
    (repo / "tools").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "tools" / "governed_scanner_preflight.py").write_text("# stub wrapper\n")
    (repo / "tools" / "governed_scanner_targets.json").write_text("{}\n")
    (repo / ".github" / "workflows" / "cand.yml").write_text("# stub workflow\n")
    (repo / "pkg.py").write_text(S608_CLEAN)
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "bundled.py").write_text(PLANTED)
    (repo / "vendor").mkdir()
    (repo / "vendor" / "bundled.py").write_text(PLANTED)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        "fixture",
    )
    return repo


@pytest.fixture()
def granted(fake_repo: Path) -> tuple[Path, Path, dict]:
    """A fully-granted synthetic control: proves the predicate is not vacuous."""
    registry = fake_repo / "registry.md"
    registry.write_text(
        "| CAP-009 | gitleaks | GRANT-REAL-TREE-DIR-SCAN: CAP-009 |\n"
        "| CAP-010 | ruff | GRANT-REAL-TREE-S-SCAN: CAP-010 |\n"
    )
    determination = fake_repo / "det.md"
    determination.write_text(
        "GRANT-REAL-TREE-DIR-SCAN: CAP-009 and GRANT-REAL-TREE-S-SCAN: CAP-010\n"
    )
    manifest = {
        "authorising_determination": "det.md",
        "candidate_workflow": ".github/workflows/cand.yml",
    }
    _git(fake_repo, "add", "-A")
    _git(
        fake_repo,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        "grant",
    )
    return registry, fake_repo, manifest


@pytest.fixture()
def work(tmp_path: Path) -> Path:
    out = tmp_path / "work"
    out.mkdir()
    return out


# --- Target-set enumeration and drift ---------------------------------------


def test_enumerates_tracked_set_python_subset_and_exact_count(fake_repo: Path) -> None:
    targets = gsp.enumerate_targets(fake_repo)
    assert set(targets.tracked) == {
        ".github/workflows/cand.yml",
        "node_modules/bundled.py",
        "pkg.py",
        "tools/governed_scanner_preflight.py",
        "tools/governed_scanner_targets.json",
        "vendor/bundled.py",
    }
    assert targets.python_targets == (
        "node_modules/bundled.py",
        "pkg.py",
        "tools/governed_scanner_preflight.py",
        "vendor/bundled.py",
    )
    assert len(targets.python_targets) == 4
    assert targets.symlink_violations == ()
    assert targets.tracked_sha256 != targets.python_sha256


def test_live_veyro_enumeration_matches_the_reviewed_manifest() -> None:
    # The reviewed manifest is the artifact under review; this asserts it is an
    # accurate record of the intended target set, not a stale one.
    gsp.verify_against_manifest(gsp.enumerate_targets(), gsp.load_manifest())


@pytest.mark.parametrize("drift", ["missing", "extra", "count", "digest"])
def test_changed_target_set_is_refused(fake_repo: Path, drift: str) -> None:
    live = gsp.enumerate_targets(fake_repo)
    manifest = live.as_dict()
    manifest["authorising_determination"] = None
    if drift == "missing":
        manifest["tracked"] = [*manifest["tracked"], "ghost/removed.py"]
    elif drift == "extra":
        manifest["tracked"] = [p for p in manifest["tracked"] if p != "pkg.py"]
    elif drift == "count":
        manifest["python_target_count"] = 99
    else:
        manifest["tracked_sha256"] = "0" * 64
    with pytest.raises(gsp.GovernedScanRefused):
        gsp.verify_against_manifest(live, manifest)


def test_unmatched_manifest_sets_are_refused_not_treated_as_empty(fake_repo: Path) -> None:
    live = gsp.enumerate_targets(fake_repo)
    with pytest.raises(gsp.GovernedScanRefused, match="records no reviewed"):
        gsp.verify_against_manifest(live, {"tracked": [], "python_targets": []})


def test_symlinked_target_is_recorded_and_refused(fake_repo: Path) -> None:
    (fake_repo / "link.py").symlink_to(fake_repo / "pkg.py")
    _git(fake_repo, "add", "link.py")
    live = gsp.enumerate_targets(fake_repo)
    assert "link.py" in live.symlink_violations
    for scanner in ("gitleaks", "ruff"):
        with pytest.raises(gsp.GovernedScanRefused, match="unsafe symlink"):
            gsp.assert_scannable(live, scanner)


# --- Default global allowlist (C09-X item 3, out-of-coverage branch) --------


def test_planted_placeholder_path_is_declared_out_of_coverage(fake_repo: Path) -> None:
    # The placeholder is planted inside `node_modules/`, a path species the
    # pinned upstream gitleaks 8.30.1 was observed to skip under its default
    # global allowlist (evidence M1-C-06-C09-ALLOWLIST-NONVACUITY-2026-10-09.md).
    # The governed shape takes C09-X item 3's second branch: the path is
    # enumerated as out of coverage rather than claimed detected, so a real-tree
    # "0 findings" carries a recorded exclusion set instead of an implied full
    # examination. `vendor/` was observed DETECTED, so it is not excluded.
    planted = fake_repo / "node_modules" / "bundled.py"
    assert _FAKE_TOKEN in planted.read_text()
    live = gsp.enumerate_targets(fake_repo)
    assert "node_modules/bundled.py" in live.allowlist_excluded
    assert gsp.is_allowlist_excluded("node_modules/bundled.py")
    assert not gsp.is_allowlist_excluded("pkg.py")  # positive non-vacuity control
    assert "pkg.py" not in live.allowlist_excluded
    assert "vendor/bundled.py" not in live.allowlist_excluded
    assert not gsp.is_allowlist_excluded("vendor/bundled.py")
    assert not gsp.is_allowlist_excluded("x.dist-info/METADATA")
    assert not gsp.is_allowlist_excluded("requirements.lock.txt")
    # The real reviewed manifest records its own exclusion set the same way:
    # exactly the four tracked `.docx` paths, none inferred from untested species.
    manifest = gsp.load_manifest()
    declared = manifest["declared_allowlist_excluded"]
    assert manifest["declared_allowlist_excluded_count"] == len(declared) == 4
    assert all(p.endswith(".docx") for p in declared)
    assert all(gsp.is_allowlist_excluded(p) for p in declared)
    assert set(declared) == {p for p in manifest["tracked"] if p.endswith(".docx")}


def test_fully_allowlisted_target_set_is_refused_as_vacuous(tmp_path: Path) -> None:
    repo = tmp_path / "allowlisted-only"
    (repo / "node_modules").mkdir(parents=True)
    (repo / "node_modules" / "bundled.py").write_text(PLANTED)
    (repo / "poetry.lock").write_text("x = 1\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@e.invalid", "-c", "user.name=t", "commit", "-qm", "f")
    live = gsp.enumerate_targets(repo)
    with pytest.raises(gsp.GovernedScanRefused, match="allowlist vacuity"):
        gsp.assert_scannable(live, "gitleaks")
    # Ruff's `S` selection is not subject to the gitleaks allowlist, so the same
    # set is scannable for Ruff — the refusal is specific, not blanket.
    gsp.assert_scannable(live, "ruff")
    # Adding an observed-detected `vendor/` file makes the set examinable.
    (repo / "vendor").mkdir()
    (repo / "vendor" / "bundled.py").write_text(PLANTED)
    _git(repo, "add", "-A")
    gsp.assert_scannable(gsp.enumerate_targets(repo), "gitleaks")


def test_empty_target_set_is_refused(tmp_path: Path) -> None:
    empty = gsp.TargetSet("deadbeef", (), (), (), ())
    with pytest.raises(gsp.GovernedScanRefused, match="empty target set"):
        gsp.assert_scannable(empty, "gitleaks")
    no_python = gsp.TargetSet("deadbeef", ("README.md",), (), (), ())
    with pytest.raises(gsp.GovernedScanRefused, match="no .py target"):
        gsp.assert_scannable(no_python, "ruff")


# --- Supply chain ------------------------------------------------------------


def test_digest_mismatch_is_refused_and_homebrew_is_named_ineligible(tmp_path: Path) -> None:
    unknown = tmp_path / "gitleaks"
    unknown.write_bytes(b"not the upstream artifact")
    with pytest.raises(gsp.GovernedScanRefused, match="not a recorded eligible digest"):
        gsp.verify_artifact_digest(unknown, "gitleaks")
    homebrew = next(iter(gsp.GITLEAKS_INELIGIBLE_BINARY_SHA256))
    assert homebrew not in gsp.GITLEAKS_ELIGIBLE_BINARY_SHA256
    assert "Homebrew" in gsp.GITLEAKS_INELIGIBLE_BINARY_SHA256[homebrew]


def test_eligible_ruff_artifact_is_accepted_and_version_asserted() -> None:
    digest = gsp.verify_artifact_digest(RUFF_BIN, "ruff")
    assert digest in gsp.RUFF_ELIGIBLE_BINARY_SHA256
    assert gsp.assert_pinned_version(RUFF_BIN, "ruff") == gsp.RUFF_VERSION


def test_missing_or_symlinked_artifact_is_refused(tmp_path: Path) -> None:
    with pytest.raises(gsp.GovernedScanRefused, match="not a regular file"):
        gsp.verify_artifact_digest(tmp_path / "absent", "ruff")
    link = tmp_path / "linked-ruff"
    link.symlink_to(RUFF_BIN)
    with pytest.raises(gsp.GovernedScanRefused, match="not a regular file"):
        gsp.verify_artifact_digest(link, "ruff")


# --- Governed argv, exit classification, redaction --------------------------


def test_gitleaks_argv_is_dir_mode_only_with_no_baseline(tmp_path: Path) -> None:
    argv = gsp.gitleaks_argv(tmp_path / "gl", tmp_path / "t", tmp_path / "r.json",
                             tmp_path / "i")
    assert argv[1] == "dir"
    assert "git" not in argv and "--staged" not in argv
    assert "--baseline-path" not in argv and "-b" not in argv
    assert "--ignore-gitleaks-allow" in argv and "--redact=100" in argv
    assert argv[argv.index("--exit-code") + 1] == str(gsp.GITLEAKS_LEAK_EXIT)
    # No Git/index/history claim is constructible from this module at all: the
    # only argv builder for gitleaks hardcodes `dir`, and no `--staged`/`--log-opts`
    # surface appears anywhere in the module.
    source = Path(gsp.__file__).read_text()
    builder = source.split("def gitleaks_argv", 1)[1].split("\ndef ", 1)[0]
    assert '"git"' not in builder and "staged" not in builder
    assert "--staged" not in source and "--log-opts" not in source


def test_ruff_argv_carries_governed_s_selection_and_no_write_mode(tmp_path: Path) -> None:
    check = gsp.ruff_argv(tmp_path / "ruff", RUFF_CONFIG, [tmp_path / "a.py"], show_files=False)
    assert check[check.index("--select") + 1] == "S"
    assert "--ignore-noqa" in check and "--no-cache" in check and "--no-fix" in check
    assert "--fix" not in check and "--unsafe-fixes" not in check and "--add-noqa" not in check
    listing = gsp.ruff_argv(tmp_path / "ruff", RUFF_CONFIG, [tmp_path / "a.py"], show_files=True)
    assert "--show-files" in listing and "--output-format" not in listing


@pytest.mark.parametrize(
    ("rc", "mode", "expected"),
    [
        (0, "gate", (gsp.EXIT_OK, "clean")),
        (42, "advisory", (gsp.EXIT_OK, "leak")),
        (42, "gate", (gsp.EXIT_FINDINGS, "leak")),
        (1, "gate", (gsp.EXIT_REFUSED, "scanner error (rc=1)")),
        (2, "advisory", (gsp.EXIT_REFUSED, "scanner error (rc=2)")),
        (127, "gate", (gsp.EXIT_REFUSED, "scanner error (rc=127)")),
    ],
)
def test_gitleaks_nonzero_exits_are_classified_fail_closed(rc, mode, expected) -> None:
    assert gsp.classify_gitleaks_exit(rc, mode) == expected


@pytest.mark.parametrize(
    ("rc", "codes", "mode", "code"),
    [
        (0, set(), "gate", gsp.EXIT_OK),
        (1, {"S608"}, "advisory", gsp.EXIT_OK),
        (1, {"S608"}, "gate", gsp.EXIT_FINDINGS),
        (1, {"invalid-syntax"}, "gate", gsp.EXIT_REFUSED),
        (2, set(), "advisory", gsp.EXIT_REFUSED),
        (101, set(), "gate", gsp.EXIT_REFUSED),
    ],
)
def test_ruff_exits_are_classified_with_syntax_errors_kept_apart(rc, codes, mode, code) -> None:
    assert gsp.classify_ruff_exit(rc, codes, mode)[0] == code


def test_findings_are_redacted_and_unredacted_output_fails_closed() -> None:
    redacted = json.dumps(
        [{"RuleID": "github-pat", "File": "a.py", "StartLine": 2, "Fingerprint": "fp",
          "Secret": "REDACTED", "Match": "REDACTED"}]
    )
    safe = gsp.redact_gitleaks_findings(redacted)
    assert safe == [{"RuleID": "github-pat", "File": "a.py", "StartLine": 2,
                     "Fingerprint": "fp"}]
    assert "Secret" not in safe[0] and "Match" not in safe[0]
    leaky = json.dumps([{"RuleID": "github-pat", "Secret": _FAKE_TOKEN}])
    with pytest.raises(gsp.GovernedScanRefused) as caught:
        gsp.redact_gitleaks_findings(leaky)
    assert _FAKE_TOKEN not in str(caught.value)
    assert gsp.redact_gitleaks_findings("") == []


# --- Authorisation predicate and the real-tree choke point ------------------


def test_real_veyro_authorisation_is_blocked_for_both_scanners() -> None:
    for scanner, (_, token) in gsp.GRANT_TOKENS.items():
        blockers = gsp.authorisation_blockers(scanner)
        assert blockers, f"{scanner} must not be authorised by this revision"
        assert any(token in b for b in blockers)
        assert any("manifest names no authorising independent determination" in b for b in blockers)


def test_predicate_clears_only_in_a_fully_granted_synthetic_control(granted) -> None:
    # Non-vacuity of the control itself: the predicate can return [], so the
    # blocked verdict above is a real finding rather than an unconditional no.
    registry, repo, manifest = granted
    for scanner in gsp.GRANT_TOKENS:
        assert gsp.authorisation_blockers(scanner, manifest, repo, registry) == []


@pytest.mark.parametrize("break_it", ["registry", "determination", "uncommitted", "modified"])
def test_each_authorisation_condition_is_load_bearing(granted, break_it: str) -> None:
    registry, repo, manifest = granted
    manifest = dict(manifest)
    if break_it == "registry":
        registry.write_text("| CAP-009 | gitleaks | no grant |\n")
    elif break_it == "determination":
        manifest["authorising_determination"] = None
    elif break_it == "uncommitted":
        manifest["candidate_workflow"] = ".github/workflows/never-committed.yml"
    else:
        (repo / "tools" / "governed_scanner_targets.json").write_text('{"changed": true}\n')
    assert gsp.authorisation_blockers("gitleaks", manifest, repo, registry)


def test_no_override_flag_env_var_or_marker_file_exists() -> None:
    source = Path(gsp.__file__).read_text()
    # Strip the module docstring, which documents the absence of these by name.
    code = source.split('"""', 2)[2]
    for override in ("--force", "--allow-real", "--yes", "os.environ", "getenv", "VEYRO_ALLOW"):
        assert override not in code, f"{override} would make the wrapper self-authorising"
    # The predicate takes no parameter a caller could use to shorten its list.
    assert "def authorisation_blockers(\n    scanner: str,\n" in source


def test_veyro_path_is_blocked_before_any_scanner_argv_is_built(monkeypatch, work) -> None:
    def explode(*_args, **_kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("a scanner argv was built for a Veyro path")

    monkeypatch.setattr(gsp, "gitleaks_argv", explode)
    monkeypatch.setattr(gsp, "ruff_argv", explode)
    with pytest.raises(gsp.RealScanBlocked) as gl:
        gsp.run_gitleaks_governed(RUFF_BIN, REPO_ROOT / "tools", work, mode="advisory")
    assert gl.value.scanner == "gitleaks" and gl.value.blockers
    with pytest.raises(gsp.RealScanBlocked):
        gsp.run_ruff_s_governed(
            RUFF_BIN,
            RUFF_CONFIG,
            [REPO_ROOT / "tools" / "governed_scanner_preflight.py"],
            work,
            expected_file_count=1,
            mode="advisory",
        )


def test_cli_preflight_is_inspectable_and_scan_is_blocked(capsys) -> None:
    assert gsp.main(["preflight", "--scanner", "ruff", "--json"]) == gsp.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["authorised_for_real_tree_scan"] is False
    assert report["refusals"] == [] and report["blockers"]
    assert report["live_target_set"]["python_target_count"] == len(
        report["intended_python_targets"]
    )
    assert gsp.main(["scan", "--scanner", "ruff"]) == gsp.EXIT_BLOCKED
    assert "BLOCKED" in capsys.readouterr().err


# --- Executed synthetic Ruff `S` drill (outside the repository) -------------


def _synthetic(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / "synthetic" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(body)
    return path


def test_governed_s_run_detects_and_clears_synthetic_fixtures(tmp_path, work) -> None:
    bad = _synthetic(tmp_path, "bad.py", S608_BAD)
    code, label, codes = gsp.run_ruff_s_governed(
        RUFF_BIN, RUFF_CONFIG, [bad], work, expected_file_count=1, mode="gate"
    )
    assert (code, label, codes) == (gsp.EXIT_FINDINGS, "S findings", {"S608"})
    code, label, _ = gsp.run_ruff_s_governed(
        RUFF_BIN, RUFF_CONFIG, [bad], work, expected_file_count=1, mode="advisory"
    )
    assert (code, label) == (gsp.EXIT_OK, "S findings")  # advisory before gate
    clean = _synthetic(tmp_path, "clean.py", S608_CLEAN)
    code, label, codes = gsp.run_ruff_s_governed(
        RUFF_BIN, RUFF_CONFIG, [clean], work, expected_file_count=1, mode="gate"
    )
    assert (code, label, codes) == (gsp.EXIT_OK, "clean", set())


def test_governed_s_run_defeats_in_fixture_noqa(tmp_path, work) -> None:
    suppressed = _synthetic(tmp_path, "noqa.py", S608_NOQA)
    _, _, codes = gsp.run_ruff_s_governed(
        RUFF_BIN, RUFF_CONFIG, [suppressed], work, expected_file_count=1, mode="gate"
    )
    assert codes == {"S608"}


def test_show_files_count_must_equal_the_expected_count(tmp_path, work) -> None:
    one = _synthetic(tmp_path, "one.py", S608_CLEAN)
    _synthetic(tmp_path, "two.py", S608_CLEAN)
    directory = one.parent
    for wrong in (0, 1, 3):
        with pytest.raises(gsp.GovernedScanRefused, match="expected exactly"):
            gsp.run_ruff_s_governed(
                RUFF_BIN, RUFF_CONFIG, [directory], work, expected_file_count=wrong,
                mode="gate",
            )
    code, _, _ = gsp.run_ruff_s_governed(
        RUFF_BIN, RUFF_CONFIG, [directory], work, expected_file_count=2, mode="gate"
    )
    assert code == gsp.EXIT_OK


def test_governed_s_run_refuses_missing_empty_and_symlinked_targets(tmp_path, work) -> None:
    good = _synthetic(tmp_path, "good.py", S608_CLEAN)
    empty = _synthetic(tmp_path, "empty.py", "")
    link = tmp_path / "synthetic" / "link.py"
    link.symlink_to(good)
    for target, pattern in (
        (tmp_path / "synthetic" / "absent.py", "missing or empty"),
        (empty, "missing or empty"),
        (link, "symlinked target refused"),
    ):
        with pytest.raises(gsp.GovernedScanRefused, match=pattern):
            gsp.run_ruff_s_governed(
                RUFF_BIN, RUFF_CONFIG, [target], work, expected_file_count=1, mode="gate"
            )


def test_governed_s_run_fails_closed_on_a_tool_error(tmp_path, work) -> None:
    bad = _synthetic(tmp_path, "bad.py", S608_BAD)
    broken = tmp_path / "broken.toml"
    broken.write_text("line-length = [\n")
    with pytest.raises(gsp.GovernedScanRefused):
        gsp.run_ruff_s_governed(
            RUFF_BIN, broken, [bad], work, expected_file_count=1, mode="gate"
        )


# --- The real-tree invocation path (`invoke` / `scan`) ----------------------
#
# Nothing below executes gitleaks or Ruff against any Veyro path, copy, index or
# history. The authorised route is exercised entirely inside a disposable git
# repository under pytest `tmp_path`, with a *fake* executable whose SHA-256 is
# temporarily recorded as the eligible digest — so the real digest-verification
# code stays in the path and only the recorded pin moves, rather than the
# verification being monkeypatched away.


def _fake_tool(tmp_path: Path, name: str, body: str) -> Path:
    exe = tmp_path / name
    exe.write_text(f"#!{sys.executable}\n{body}")
    exe.chmod(0o755)
    return exe


_RECORD_ARGV = (
    "import json, pathlib, sys\n"
    "argv = sys.argv[1:]\n"
    "with open(__file__ + '.argv', 'a') as fh:\n"
    "    fh.write(json.dumps(argv) + '\\n')\n"
)


def _recorded_argv(exe: Path) -> list[list[str]]:
    log = Path(str(exe) + ".argv")
    return [json.loads(line) for line in log.read_text().splitlines()] if log.is_file() else []


def _fake_ruff(tmp_path: Path, *, rc: int, findings: list[dict]) -> Path:
    return _fake_tool(
        tmp_path,
        "fake-ruff",
        _RECORD_ARGV
        + "if '--version' in argv:\n"
        f"    print({gsp.RUFF_VERSION!r})\n"
        "    sys.exit(0)\n"
        "if '--show-files' in argv:\n"
        "    print('\\n'.join(a for a in argv if a.endswith('.py')))\n"
        "    sys.exit(0)\n"
        f"print(json.dumps({findings!r}))\n"
        f"sys.exit({rc})\n",
    )


def _fake_gitleaks(tmp_path: Path, *, rc: int, findings: list[dict]) -> Path:
    return _fake_tool(
        tmp_path,
        "fake-gitleaks",
        _RECORD_ARGV
        + "if argv[:1] == ['version']:\n"
        f"    print({gsp.GITLEAKS_VERSION!r})\n"
        "    sys.exit(0)\n"
        "report = pathlib.Path(argv[argv.index('--report-path') + 1])\n"
        f"report.write_text(json.dumps({findings!r}))\n"
        f"sys.exit({rc})\n",
    )


def _fake_gitleaks_reporting(tmp_path: Path, *, rc: int, file_expr: str) -> Path:
    """Fake gitleaks whose finding `File` is computed from the target it was given.

    Needed because the governed gitleaks target is a snapshot directory whose
    path is only known at run time, so the reported path cannot be a literal.
    """
    return _fake_tool(
        tmp_path,
        "fake-gitleaks-reporting",
        _RECORD_ARGV
        + "if argv[:1] == ['version']:\n"
        f"    print({gsp.GITLEAKS_VERSION!r})\n"
        "    sys.exit(0)\n"
        "target = argv[-1]\n"
        f"finding = dict({REDACTED_LEAK[0]!r}, File={file_expr})\n"
        "report = pathlib.Path(argv[argv.index('--report-path') + 1])\n"
        f"report.write_text(json.dumps([finding] if {bool(rc)} else []))\n"
        f"sys.exit({rc})\n",
    )


REDACTED_LEAK = [
    {
        "RuleID": "github-pat",
        "File": "pkg.py",
        "StartLine": 2,
        "Fingerprint": "pkg.py:github-pat:2",
        "Secret": "REDACTED",
        "Match": "REDACTED",
    }
]
S608_FINDING = [
    {
        "code": "S608",
        "filename": "pkg.py",
        "location": {"row": 2, "column": 9},
        # Ruff's own message quotes the offending construct; the governed report
        # must not forward it. Asserted value-free below.
        "message": "Possible SQL injection vector through string-based query construction",
    }
]


def _granted_repo(tmp_path: Path, monkeypatch, *, advisory_recorded: bool) -> Path:
    """A disposable repo in which every authorisation condition is satisfied.

    Exists to prove the blocked verdict against the live Veyro tree is a real
    finding about that tree, not an unconditional refusal: the same code reaches
    the scanner here. The Veyro repository clears none of these conditions.
    """
    repo = tmp_path / "granted-repo"
    (repo / "tools").mkdir(parents=True)
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "tools" / "governed_scanner_preflight.py").write_text("# stub wrapper\n")
    (repo / "tools" / "governed_scanner_targets.json").write_text("{}\n")
    (repo / ".github" / "workflows" / "cand.yml").write_text("# stub workflow\n")
    (repo / "pkg.py").write_text(S608_BAD)
    (repo / "ruff.toml").write_bytes(RUFF_CONFIG.read_bytes())  # digest-pinned bytes
    (repo / ".gitignore").write_text("ignored-artifact.txt\n")
    (repo / "registry.md").write_text(
        "| CAP-009 | gitleaks | GRANT-REAL-TREE-DIR-SCAN: CAP-009 |\n"
        "| CAP-010 | ruff | GRANT-REAL-TREE-S-SCAN: CAP-010 |\n"
    )
    (repo / "det.md").write_text(
        "GRANT-REAL-TREE-DIR-SCAN: CAP-009 and GRANT-REAL-TREE-S-SCAN: CAP-010\n"
    )
    (repo / "adv.md").write_text(
        "ADVISORY-RUN-RECORDED: CAP-009\nADVISORY-RUN-RECORDED: CAP-010\n"
    )
    _commit(repo, "fixture")
    manifest_path = repo / "tools" / "governed_scanner_targets.json"
    manifest = {
        **gsp.enumerate_targets(repo).as_dict(),
        "authorising_determination": "det.md",
        "candidate_workflow": ".github/workflows/cand.yml",
        "advisory_run_evidence": "adv.md" if advisory_recorded else None,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    _commit(repo, "bind manifest")
    monkeypatch.setattr(gsp, "REPO_ROOT", repo)
    monkeypatch.setattr(gsp, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(gsp, "REGISTRY_PATH", repo / "registry.md")
    return repo


def _commit(repo: Path, message: str) -> None:
    if not (repo / ".git").exists():
        _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", message)


@pytest.fixture()
def no_scanner_may_run(monkeypatch):
    """Explodes if any scanner argv is built or any scanner process is started."""

    def explode(*_args, **_kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("a scanner was reached for a Veyro path")

    for name in ("gitleaks_argv", "ruff_argv", "run_gitleaks_governed", "run_ruff_s_governed"):
        monkeypatch.setattr(gsp, name, explode)


# (1) Without a grant, the CLI cannot invoke a scanner on the Veyro path.


@pytest.mark.parametrize("scanner", list(gsp.GRANT_TOKENS))
@pytest.mark.parametrize("mode", ["advisory", "gate"])
@pytest.mark.parametrize("with_binary", [False, True])
def test_live_scan_is_blocked_and_reaches_no_scanner(
    no_scanner_may_run, capsys, scanner, mode, with_binary
) -> None:
    argv = ["scan", "--scanner", scanner, "--mode", mode]
    if with_binary:
        # Supplying a genuinely eligible, digest-verified executable must not
        # change the verdict: authorisation is asked before anything else.
        argv += ["--binary", str(RUFF_BIN)]
    assert gsp.main(argv) == gsp.EXIT_BLOCKED
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["outcome"] == "blocked" and report["exit_code"] == gsp.EXIT_BLOCKED
    assert report["findings"] == [] and "binary_sha256" not in report
    assert any(gsp.GRANT_TOKENS[scanner][1] in b for b in report["blockers"])
    assert "BLOCKED" in captured.err


def test_blocked_scan_names_the_live_target_set_without_scanning_it(no_scanner_may_run) -> None:
    code, report = gsp.invoke("gitleaks", "advisory", None)
    assert code == gsp.EXIT_BLOCKED
    manifest = gsp.load_manifest()
    # The report is about the reviewed set, and says so, having examined no byte.
    assert report["target_set"]["tracked_count"] == manifest["tracked_count"]
    assert report["target_set"]["python_sha256"] == manifest["python_sha256"]
    assert report["target_set"]["declared_allowlist_excluded"] == (
        manifest["declared_allowlist_excluded"]
    )


# (2) Even with a simulated grant, drift or unenumerated source refuses first.


def test_simulated_grant_clears_every_blocker(tmp_path, monkeypatch) -> None:
    # Non-vacuity of the control: without this, every refusal below would be
    # indistinguishable from the unconditional block.
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    for scanner in gsp.GRANT_TOKENS:
        assert gsp.authorisation_blockers(scanner, gsp.load_manifest(), repo) == []


@pytest.mark.parametrize("scanner", list(gsp.GRANT_TOKENS))
def test_manifest_drift_refuses_before_any_scanner_runs(
    tmp_path, monkeypatch, no_scanner_may_run, scanner
) -> None:
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    # Staged, so the Git index — the enumeration source — gains a path the
    # reviewed manifest never listed, while the three bound files stay committed
    # and byte-identical, i.e. authorisation still clears.
    (repo / "intruder.py").write_text(S608_CLEAN)
    _git(repo, "add", "intruder.py")
    assert gsp.authorisation_blockers(scanner, gsp.load_manifest(), repo) == []
    code, report = gsp.invoke(scanner, "advisory", RUFF_BIN, tmp_path / "work", repo)
    assert code == gsp.EXIT_REFUSED and report["outcome"] == "refused"
    assert any("drifted from the reviewed set" in r for r in report["refusals"])
    assert any("intruder.py" in r for r in report["refusals"])


@pytest.mark.parametrize("scanner", list(gsp.GRANT_TOKENS))
def test_uncommitted_source_refuses_before_any_scanner_runs(
    tmp_path, monkeypatch, no_scanner_may_run, scanner
) -> None:
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    (repo / "pkg.py").write_text(S608_CLEAN + "# working-tree edit\n")
    code, report = gsp.invoke(scanner, "advisory", RUFF_BIN, tmp_path / "work", repo)
    assert code == gsp.EXIT_REFUSED
    assert any("not a clean committed checkout" in r for r in report["refusals"])


@pytest.mark.parametrize("scanner", list(gsp.GRANT_TOKENS))
def test_gitignored_on_disk_file_refuses_before_any_scanner_runs(
    tmp_path, monkeypatch, no_scanner_may_run, scanner
) -> None:
    # The `gitleaks dir` silent-scan case specifically: a file that `git status`
    # does not report at all, because it is ignored, but that a directory walker
    # would still examine. Nothing except the physical walk catches this.
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    (repo / "ignored-artifact.txt").write_text("generated output\n")
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        == ""
    )
    code, report = gsp.invoke(scanner, "advisory", RUFF_BIN, tmp_path / "work", repo)
    assert code == gsp.EXIT_REFUSED
    assert any("would be scanned unreviewed" in r for r in report["refusals"])
    assert any("ignored-artifact.txt" in r for r in report["refusals"])


@pytest.mark.parametrize("scanner", list(gsp.GRANT_TOKENS))
def test_gate_mode_refuses_until_an_advisory_run_is_recorded(
    tmp_path, monkeypatch, no_scanner_may_run, scanner
) -> None:
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=False)
    code, report = gsp.invoke(scanner, "gate", RUFF_BIN, tmp_path / "work", repo)
    assert code == gsp.EXIT_REFUSED
    assert any("requires a recorded prior advisory run" in r for r in report["refusals"])
    # Non-vacuity, and that the recorded token must be the right one: the
    # predicate does clear, but only for a scanner the record actually names.
    cap_id, _ = gsp.GRANT_TOKENS[scanner]
    assert gsp.gate_mode_refusals(scanner, {"advisory_run_evidence": "adv.md"}, repo) == []
    (repo / "other.md").write_text("ADVISORY-RUN-RECORDED: CAP-999\n")
    assert gsp.gate_mode_refusals(scanner, {"advisory_run_evidence": "other.md"}, repo)
    assert cap_id in gsp.gate_mode_refusals(scanner, {"advisory_run_evidence": None}, repo)[0]


def test_unpinned_or_uncommitted_ruff_config_is_refused(tmp_path, monkeypatch) -> None:
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    assert gsp._verify_governed_ruff_config(repo) == repo / "ruff.toml"
    (repo / "ruff.toml").write_text("line-length = 42\n")
    _git(repo, "add", "ruff.toml")  # staged but not committed: not reviewed bytes
    with pytest.raises(gsp.GovernedScanRefused, match="!= the pinned"):
        gsp._verify_governed_ruff_config(repo)
    (repo / "ruff.toml").unlink()
    with pytest.raises(gsp.GovernedScanRefused, match="not a regular file"):
        gsp._verify_governed_ruff_config(repo)


def test_work_directory_inside_the_repository_is_refused(tmp_path, monkeypatch) -> None:
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    with pytest.raises(gsp.GovernedScanRefused, match="outside the repository"):
        gsp._resolve_work_dir(repo / "reports")
    assert gsp._resolve_work_dir(tmp_path / "outside").is_dir()


# (3) Governed argv and exit mapping on the authorised path, via a fake tool.


@pytest.mark.parametrize(
    ("mode", "expected"), [("advisory", gsp.EXIT_OK), ("gate", gsp.EXIT_FINDINGS)]
)
def test_authorised_ruff_s_path_uses_the_governed_argv_and_exit_mapping(
    tmp_path, monkeypatch, mode, expected
) -> None:
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    fake = _fake_ruff(tmp_path, rc=1, findings=S608_FINDING)
    monkeypatch.setattr(
        gsp,
        "RUFF_ELIGIBLE_BINARY_SHA256",
        frozenset({hashlib.sha256(fake.read_bytes()).hexdigest()}),
    )
    live = gsp.enumerate_targets(repo)
    code, report = gsp.invoke("ruff", mode, fake, tmp_path / "work", repo)
    assert (code, report["exit_code"]) == (expected, expected)
    assert report["outcome"] == "S findings" and report["rule_codes"] == ["S608"]
    assert report["refusals"] == [] and report["blockers"] == []
    assert report["binary_version"] == gsp.RUFF_VERSION
    assert report["binary_sha256"] in gsp.RUFF_ELIGIBLE_BINARY_SHA256
    assert report["finding_count"] == 1
    # Value-free reporting: rule, path and line only — never Ruff's message.
    assert report["findings"] == [{"code": "S608", "filename": "pkg.py", "row": 2}]
    assert "message" not in json.dumps(report)
    # The governed argv: the `--show-files` count pre-check, then the check run
    # over exactly the enumerated targets under the pinned config.
    listing, check = _recorded_argv(fake)[-2:]
    assert "--show-files" in listing
    assert check[check.index("--config") + 1] == str(repo / "ruff.toml")
    assert check[check.index("--select") + 1] == "S"
    assert {"--no-cache", "--no-fix", "--ignore-noqa"} <= set(check)
    assert not {"--fix", "--unsafe-fixes", "--add-noqa"} & set(check)
    assert [a for a in check if a.endswith(".py")] == [
        str(repo / p) for p in live.python_targets
    ]
    assert len(live.python_targets) == gsp.load_manifest()["python_target_count"]


def test_a_target_directory_containing_dot_git_is_still_refused(
    tmp_path, monkeypatch, work
) -> None:
    # The backstop, kept after materialization became the mechanism: a caller
    # that hands `dir` mode a checkout is refused rather than served, because
    # `dir` would walk Git object bytes and CAP-009 approves neither index nor
    # history scope. Synthetic directory outside the repository throughout.
    fake = _fake_gitleaks(tmp_path, rc=0, findings=[])
    monkeypatch.setattr(
        gsp,
        "GITLEAKS_ELIGIBLE_BINARY_SHA256",
        frozenset({hashlib.sha256(fake.read_bytes()).hexdigest()}),
    )
    target = tmp_path / "checkout-shaped"
    (target / ".git").mkdir(parents=True)
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (target / "pkg.py").write_text(PLANTED)
    with pytest.raises(gsp.GovernedScanRefused, match="target contains .git"):
        gsp.run_gitleaks_governed(fake, target, work, mode="advisory")
    assert all("dir" not in recorded for recorded in _recorded_argv(fake))


# --- Git-free materialization of the committed target set -------------------
#
# The C09-X git-vs-CI contradiction: the candidate workflow fetches a Git
# checkout (Git is what proves the tree is the exact pushed commit), while
# `dir` mode must never be pointed at one. These cover the second directory
# that resolves it — exactly the committed blobs, no Git object — and that
# copying those bytes outside the repository does not reclassify the scan.


def test_snapshot_holds_exactly_the_committed_bytes_and_no_git(fake_repo, work) -> None:
    live = gsp.enumerate_targets(fake_repo)
    snapshot, digest = gsp.materialize_tracked_snapshot(live, fake_repo, work)
    materialized = sorted(
        str(p.relative_to(snapshot)) for p in snapshot.rglob("*") if p.is_file()
    )
    assert materialized == sorted(live.tracked)
    for rel in live.tracked:
        assert (snapshot / rel).read_bytes() == (fake_repo / rel).read_bytes()
        assert not (snapshot / rel).is_symlink()
    # Git-free: the source checkout has a `.git`, the materialized target has
    # none at any depth, so no object/pack byte can reach a directory walker.
    assert (fake_repo / ".git").is_dir()
    assert not list(snapshot.rglob(".git"))
    assert not (snapshot / ".git").exists()
    # The digest is content-level, so evidence can state which bytes were
    # materialized rather than only how many.
    assert len(digest) == 64
    assert gsp.materialize_tracked_snapshot(live, fake_repo, work / "second")[1] == digest


def test_snapshot_refuses_working_tree_bytes_that_are_not_the_committed_blob(
    fake_repo, work
) -> None:
    live = gsp.enumerate_targets(fake_repo)
    (fake_repo / "pkg.py").write_text(S608_BAD)  # committed blob unchanged
    with pytest.raises(gsp.GovernedScanRefused, match="not the reviewed committed bytes"):
        gsp.materialize_tracked_snapshot(live, fake_repo, work)


def test_snapshot_refuses_index_drift_a_reused_destination_and_a_symlink(
    fake_repo, work
) -> None:
    live = gsp.enumerate_targets(fake_repo)
    gsp.materialize_tracked_snapshot(live, fake_repo, work)
    with pytest.raises(gsp.GovernedScanRefused, match="already exists"):
        gsp.materialize_tracked_snapshot(live, fake_repo, work)
    # Index gains a path the enumeration never saw: refuse rather than copy a
    # set that no longer matches the one the manifest check cleared.
    (fake_repo / "intruder.py").write_text(S608_CLEAN)
    _git(fake_repo, "add", "intruder.py")
    with pytest.raises(gsp.GovernedScanRefused, match="index changed"):
        gsp.materialize_tracked_snapshot(live, fake_repo, work / "drift")
    linked = gsp.TargetSet(live.head_commit, live.tracked, live.python_targets, (), ("l.py",))
    with pytest.raises(gsp.GovernedScanRefused, match="unsafe symlink"):
        gsp.materialize_tracked_snapshot(linked, fake_repo, work / "symlink")


def test_snapshot_destination_inside_the_repository_is_refused(fake_repo) -> None:
    with pytest.raises(gsp.GovernedScanRefused, match="outside the repository"):
        gsp.materialize_tracked_snapshot(
            gsp.enumerate_targets(fake_repo), fake_repo, REPO_ROOT / "reports"
        )


def test_a_snapshot_outside_the_repository_is_still_a_veyro_scan(
    fake_repo, tmp_path, work
) -> None:
    # The source-repository authorisation choke point, asserted at the exact
    # place it could have been lost: the snapshot sits outside the repository,
    # which is the shape `_require_scan_allowed` otherwise lets through as
    # approved synthetic scope. Provenance, not geography, decides.
    live = gsp.enumerate_targets(fake_repo)
    snapshot, _ = gsp.materialize_tracked_snapshot(live, fake_repo, work)
    assert REPO_ROOT not in snapshot.parents  # would read as synthetic on path alone
    fake = _fake_gitleaks(tmp_path, rc=0, findings=[])
    with pytest.raises(gsp.RealScanBlocked) as blocked:
        gsp.run_gitleaks_governed(fake, snapshot, work, mode="advisory")
    assert blocked.value.blockers
    assert _recorded_argv(fake) == []
    # Non-vacuity of the registry: a sibling directory of the same shape, not
    # derived from committed bytes, is still approved synthetic scope.
    synthetic = tmp_path / "not-derived"
    synthetic.mkdir()
    assert gsp._require_scan_allowed("gitleaks", [synthetic]) is None
    assert gsp._is_veyro_derived(snapshot) and not gsp._is_veyro_derived(synthetic)


def test_blocked_invoke_materializes_no_copy_of_the_tree(tmp_path, no_scanner_may_run) -> None:
    # Authorisation is asked before materialization, so a blocked run leaves no
    # copy of any Veyro byte anywhere.
    out = tmp_path / "work"
    code, report = gsp.invoke("gitleaks", "advisory", None, out)
    assert code == gsp.EXIT_BLOCKED and report["blockers"]
    assert "materialized_snapshot" not in report
    assert not (out / gsp.SNAPSHOT_DIRNAME).exists()


def test_findings_are_mapped_back_to_reviewed_paths_or_refused(tmp_path, work) -> None:
    snapshot = tmp_path / "snap"
    (snapshot / "backend").mkdir(parents=True)
    (snapshot / "backend" / "app.py").write_text(PLANTED)
    for reported in (str(snapshot / "backend" / "app.py"), "backend/app.py"):
        mapped = gsp.veyro_relative_findings(
            [{"RuleID": "github-pat", "File": reported}], snapshot, work
        )
        assert mapped == [{"RuleID": "github-pat", "File": "backend/app.py"}]
    for outside in ("/etc/hosts", "", str(work / "gitleaks-report.json")):
        with pytest.raises(gsp.GovernedScanRefused, match="not inside the materialized"):
            gsp.veyro_relative_findings(
                [{"RuleID": "github-pat", "File": outside}], snapshot, work
            )


@pytest.mark.parametrize(
    ("rc", "mode", "expected", "outcome"),
    [
        (gsp.GITLEAKS_LEAK_EXIT, "advisory", gsp.EXIT_OK, "leak"),
        (gsp.GITLEAKS_LEAK_EXIT, "gate", gsp.EXIT_FINDINGS, "leak"),
        (0, "gate", gsp.EXIT_OK, "clean"),
    ],
)
def test_authorised_gitleaks_path_scans_the_git_free_snapshot(
    tmp_path, monkeypatch, rc, mode, expected, outcome
) -> None:
    # The simulated authorised path, end to end, inside a disposable repo: the
    # scanner receives the materialized snapshot, never the checkout, and the
    # argv carries no Git surface. The live Veyro tree clears none of these
    # conditions and is exercised nowhere here.
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    fake = _fake_gitleaks_reporting(tmp_path, rc=rc, file_expr="target + '/pkg.py'")
    monkeypatch.setattr(
        gsp,
        "GITLEAKS_ELIGIBLE_BINARY_SHA256",
        frozenset({hashlib.sha256(fake.read_bytes()).hexdigest()}),
    )
    live = gsp.enumerate_targets(repo)
    code, report = gsp.invoke("gitleaks", mode, fake, tmp_path / "work", repo)
    assert (code, report["exit_code"]) == (expected, expected)
    assert (report["outcome"], report["refusals"], report["blockers"]) == (outcome, [], [])
    assert report["materialized_snapshot"] == {
        "file_count": len(live.tracked),
        "content_sha256": report["materialized_snapshot"]["content_sha256"],
        "git_free": True,
        "retained_after_run": False,
    }
    scan_argv = _recorded_argv(fake)[-1]
    target = Path(scan_argv[-1])
    assert scan_argv[0] == "dir"
    assert target == (tmp_path / "work" / gsp.SNAPSHOT_DIRNAME).resolve()
    assert target != repo and repo not in target.parents  # never the checkout
    assert not {"--baseline-path", "-b", "git", "--staged"} & set(scan_argv)
    # The copy does not outlive the run, and the finding names the reviewed
    # repository-relative path rather than a temporary directory.
    assert not target.exists()
    assert report["findings"] == (
        [{"RuleID": "github-pat", "File": "pkg.py", "StartLine": 2,
          "Fingerprint": "pkg.py:github-pat:2"}]
        if rc
        else []
    )


def test_authorised_gitleaks_path_refuses_a_finding_outside_the_snapshot(
    tmp_path, monkeypatch
) -> None:
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    fake = _fake_gitleaks_reporting(
        tmp_path, rc=gsp.GITLEAKS_LEAK_EXIT, file_expr="'/etc/hosts'"
    )
    monkeypatch.setattr(
        gsp,
        "GITLEAKS_ELIGIBLE_BINARY_SHA256",
        frozenset({hashlib.sha256(fake.read_bytes()).hexdigest()}),
    )
    code, report = gsp.invoke("gitleaks", "advisory", fake, tmp_path / "work", repo)
    assert code == gsp.EXIT_REFUSED and report["findings"] == []
    assert any("not inside the materialized snapshot" in r for r in report["refusals"])
    assert not (tmp_path / "work" / gsp.SNAPSHOT_DIRNAME).exists()
    # A report-mapping refusal is one of the exits cleanup must cover, and the
    # removal is recorded as observed rather than asserted by default.
    assert report["materialized_snapshot"]["retained_after_run"] is False


# --- No copy of reviewed bytes survives a failure ---------------------------
#
# The defect these cover was reproduced after the materialization path was
# first written: a refusal raised part way through the copy loop left the
# already-copied files on disk, because the caller's cleanup `finally` is only
# established once materialization *returns*. The suite passed at the time
# because it asserted the refusal and never looked at the destination.


def _two_file_repo_with_a_later_mismatch(tmp_path: Path) -> tuple[Path, gsp.TargetSet]:
    """A committed repo whose *second* enumerated path is not its committed blob.

    Enumeration is sorted, so `a.txt` is copied before `z.txt` is examined:
    the refusal necessarily fires with one file already written.
    """
    repo = tmp_path / "later-mismatch"
    repo.mkdir()
    (repo / "a.txt").write_text("first file, committed and unchanged\n")
    (repo / "z.txt").write_text("second file, committed\n")
    _commit(repo, "two committed files")
    live = gsp.enumerate_targets(repo)
    assert live.tracked == ("a.txt", "z.txt")
    (repo / "z.txt").write_text("working-tree bytes only\n")  # index unchanged
    return repo, live


def test_a_later_path_blob_mismatch_leaves_no_partial_snapshot(tmp_path, work) -> None:
    repo, live = _two_file_repo_with_a_later_mismatch(tmp_path)
    with pytest.raises(gsp.GovernedScanRefused, match="not the reviewed committed bytes"):
        gsp.materialize_tracked_snapshot(live, repo, work)
    dest = work / gsp.SNAPSHOT_DIRNAME
    # The refusal is not enough: the file that was already copied must be gone,
    # and nothing of the reviewed tree may remain under the work directory.
    assert not (dest / "a.txt").exists()
    assert not dest.exists()
    assert [str(p.relative_to(work)) for p in work.rglob("*") if p.is_file()] == []


def test_an_unexpected_error_during_the_copy_also_leaves_no_partial_snapshot(
    tmp_path, work, monkeypatch
) -> None:
    # Not every failure is a refusal: an OS error on the second write leaves the
    # same partial copy, so cleanup covers any exception, not one class of it.
    repo = tmp_path / "copy-error"
    repo.mkdir()
    (repo / "a.txt").write_text("first\n")
    (repo / "z.txt").write_text("second\n")
    _commit(repo, "two committed files")
    live = gsp.enumerate_targets(repo)
    real_write = Path.write_bytes
    calls: list[Path] = []

    def failing_write(self: Path, data: bytes) -> int:
        calls.append(self)
        if len(calls) > 1:
            raise OSError("disk full")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write)
    with pytest.raises(OSError, match="disk full"):
        gsp.materialize_tracked_snapshot(live, repo, work)
    assert not (work / gsp.SNAPSHOT_DIRNAME).exists()


def test_a_scanner_error_discards_the_snapshot_and_records_it(tmp_path, monkeypatch) -> None:
    # The scanner-side exit of the same obligation: an unexpected scanner rc is
    # a refusal, and the copy it was handed must not outlive it.
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    fake = _fake_gitleaks(tmp_path, rc=7, findings=[])
    monkeypatch.setattr(
        gsp,
        "GITLEAKS_ELIGIBLE_BINARY_SHA256",
        frozenset({hashlib.sha256(fake.read_bytes()).hexdigest()}),
    )
    code, report = gsp.invoke("gitleaks", "advisory", fake, tmp_path / "work", repo)
    assert code == gsp.EXIT_REFUSED and report["findings"] == []
    assert any("scanner error (rc=7)" in r for r in report["refusals"])
    assert report["materialized_snapshot"]["retained_after_run"] is False
    assert "retention_residue" not in report["materialized_snapshot"]
    assert not (tmp_path / "work" / gsp.SNAPSHOT_DIRNAME).exists()


def test_a_refusal_whose_cleanup_fails_names_the_retained_copy(
    tmp_path, work, monkeypatch
) -> None:
    # Honesty when removal itself does not work: the only removal primitive is
    # neutered, so `_discard_snapshot`'s independent existence check is what has
    # to notice. A refusal that could not clean up must say what is still there
    # rather than report a clean refusal.
    repo, live = _two_file_repo_with_a_later_mismatch(tmp_path)
    monkeypatch.setattr(gsp.shutil, "rmtree", lambda *_a, **_k: None)
    with pytest.raises(gsp.GovernedScanRefused, match="could not be removed") as refused:
        gsp.materialize_tracked_snapshot(live, repo, work)
    message = str(refused.value)
    assert "not the reviewed committed bytes" in message  # original cause kept
    assert "a.txt" in message  # and what is still on disk is named
    assert (work / gsp.SNAPSHOT_DIRNAME / "a.txt").exists()


def test_an_unremovable_snapshot_turns_a_clean_scan_into_a_refusal(
    tmp_path, monkeypatch
) -> None:
    # The successful-scan counterpart: exit 0 with a surviving copy of reviewed
    # bytes is not an acceptable outcome, and the report must not claim
    # `retained_after_run: false` when the copy is demonstrably still there.
    repo = _granted_repo(tmp_path, monkeypatch, advisory_recorded=True)
    fake = _fake_gitleaks_reporting(tmp_path, rc=0, file_expr="target + '/pkg.py'")
    monkeypatch.setattr(
        gsp,
        "GITLEAKS_ELIGIBLE_BINARY_SHA256",
        frozenset({hashlib.sha256(fake.read_bytes()).hexdigest()}),
    )
    monkeypatch.setattr(gsp.shutil, "rmtree", lambda *_a, **_k: None)
    code, report = gsp.invoke("gitleaks", "advisory", fake, tmp_path / "work", repo)
    snapshot = tmp_path / "work" / gsp.SNAPSHOT_DIRNAME
    assert code == gsp.EXIT_REFUSED and report["outcome"] == "refused"
    assert any("outlived the run" in r for r in report["refusals"])
    assert report["materialized_snapshot"]["retained_after_run"] is True
    assert str(snapshot) in report["materialized_snapshot"]["retention_residue"]
    assert snapshot.exists()  # the honest report matches what is on disk


@pytest.mark.parametrize(
    ("rc", "mode", "expected", "outcome"),
    [
        (gsp.GITLEAKS_LEAK_EXIT, "advisory", gsp.EXIT_OK, "leak"),
        (gsp.GITLEAKS_LEAK_EXIT, "gate", gsp.EXIT_FINDINGS, "leak"),
        (0, "gate", gsp.EXIT_OK, "clean"),
    ],
)
def test_governed_gitleaks_argv_and_exit_mapping_via_a_fake_tool(
    tmp_path, monkeypatch, work, rc, mode, expected, outcome
) -> None:
    # Synthetic directory outside the repository (CAP-009's approved bounded
    # scope), and a fake executable rather than gitleaks: this covers the
    # governed argv, the exit mapping and the redaction contract end to end
    # without any Veyro byte being examined.
    fake = _fake_gitleaks(tmp_path, rc=rc, findings=REDACTED_LEAK if rc else [])
    monkeypatch.setattr(
        gsp,
        "GITLEAKS_ELIGIBLE_BINARY_SHA256",
        frozenset({hashlib.sha256(fake.read_bytes()).hexdigest()}),
    )
    target = tmp_path / "synthetic-target"
    target.mkdir()
    (target / "pkg.py").write_text(PLANTED)
    code, label, findings = gsp.run_gitleaks_governed(fake, target, work, mode=mode)
    assert (code, label) == (expected, outcome)
    assert findings == (
        [{"RuleID": "github-pat", "File": "pkg.py", "StartLine": 2,
          "Fingerprint": "pkg.py:github-pat:2"}]
        if rc
        else []
    )
    assert _FAKE_TOKEN not in json.dumps(findings)
    scan_argv = _recorded_argv(fake)[-1]
    assert scan_argv[0] == "dir" and scan_argv[-1] == str(target.resolve())
    assert scan_argv[scan_argv.index("--exit-code") + 1] == str(gsp.GITLEAKS_LEAK_EXIT)
    assert "--redact=100" in scan_argv and "--ignore-gitleaks-allow" in scan_argv
    assert not {"--baseline-path", "-b", "git", "--staged"} & set(scan_argv)
