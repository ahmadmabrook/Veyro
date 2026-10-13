#!/usr/bin/env python3
"""
Unit tests for tools/validate_surface_profile.py (MOD-001, ADR-005 Decision 2
Part 3 / IMPLEMENTATION.md §4 gate 7 — surface-profile activation) and its
dispatch wiring in tools/validate_architecture_gates.py's `--gate
surface-profile`.

Every fixture is a synthetic tree built inside `tempfile.TemporaryDirectory`;
none of these tests ever touch the real `knowledge/`, the real
`module-capabilities.yaml`, or any other real project state.

Scenario coverage (synthetic, matching the catalog's own fixture shapes —
these are test-level drills, not a scenario-catalog promotion):

  SCN-MOD001-102 (positive) -- test_activated_profile_passes,
    test_known_infrastructure_passes
  SCN-MOD001-103 (negative) -- test_deferred_surface_application_file_denied
  SCN-MOD001-112 (unnamed-path case) -- test_unknown_top_level_surface_denied,
    test_unmatched_root_file_is_out_of_surface_scope,
    test_explicit_manifest_root_row_still_checked
  SCN-MOD001-138 (carve-out positive) /
  SCN-MOD001-139 (carve-out boundary, same run) --
    test_carveout_passes_while_sibling_application_file_denied_same_run

Run directly (`python3 tools/tests/test_validate_surface_profile.py`) or
with pytest.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from validate_surface_profile import (
    ERROR,
    FAIL,
    INCONCLUSIVE,
    PASS,
    GateInputError,
    _pattern_matches,
    run_surface_profile_gate,
)

# Mirrors the real knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml
# repository_paths_surfaces list (19 rows: 3 ACTIVATED globs across 2 profiles,
# 9 DEFERRED globs across 8 profiles, 7 profile:null known-infrastructure rows)
# -- a synthetic copy, not a read of the real file, per this project's "never
# against real project state" fixture convention.
MANIFEST_TEXT = """\
repository_paths_surfaces:
  - path: backend/**
    profile: Backend
    state: ACTIVATED
  - path: infra/**
    profile: Infra/SRE/CI
    state: ACTIVATED
  - path: .github/workflows/**
    profile: Infra/SRE/CI
    state: ACTIVATED
  - path: admin-web/**
    profile: Admin Web
    state: DEFERRED
    marker: admin-web/.profile-pending
  - path: web/**
    profile: General Web
    state: DEFERRED
    marker: web/.profile-pending
  - path: frontdesk-web/**
    profile: Front Desk/POS
    state: DEFERRED
    marker: frontdesk-web/.profile-pending
  - path: frontdesk-edge-bridge/**
    profile: Front Desk/POS
    state: DEFERRED
    marker: frontdesk-edge-bridge/.profile-pending
  - path: mobile/shared/**
    profile: KMP Mobile
    state: DEFERRED
    marker: mobile/shared/.profile-pending
  - path: mobile/iosApp/**
    profile: iOS Host
    state: DEFERRED
    marker: mobile/iosApp/.profile-pending
  - path: mobile/androidApp/**
    profile: Android Host
    state: DEFERRED
    marker: mobile/androidApp/.profile-pending
  - path: mobile/*.md
    profile: null  # cross-cutting mobile-wide policy docs
    state: n/a
  - path: RELEASE_TRAIN.md
    profile: null  # cross-cutting, repo-root release-train doc
    state: n/a
  - path: edge/**
    profile: Edge
    state: DEFERRED
    marker: edge/.profile-pending
  - path: data-ai/**
    profile: Data/AI
    state: DEFERRED
    marker: data-ai/.profile-pending
  - path: contracts/**
    profile: null
    state: n/a
  - path: tools/**
    profile: null
    state: n/a
  - path: .claude/**
    profile: null  # known-infrastructure, not a §4.3 surface
    state: n/a
  - path: knowledge/**
    profile: null  # known-infrastructure, not a §4.3 surface
    state: n/a
  - path: veyro-product-experience-design/**
    profile: null  # known-infrastructure, frozen design-bundle baseline
    state: n/a
required_agent_roles:
  - role: veyro-implementer
    scope: "Routine implementation outside the above"
    model: sonnet
    status: ACTIVE
"""


def _write_manifest(root: Path, text: str = MANIFEST_TEXT) -> Path:
    manifest = root / "module-capabilities.yaml"
    manifest.write_text(text)
    return manifest


def _write(root: Path, relpath: str, content: str = "x = 1\n") -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _git_add(root: Path, *relpaths: str) -> None:
    subprocess.run(["git", "add", *relpaths], cwd=root, check=True)


# --- SCN-MOD001-102 (positive): activated profile, and known-infrastructure --


def test_activated_profile_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "backend/app/main.py")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == PASS, report.render()
        assert report.checked == ["backend/app/main.py"]


def test_known_infrastructure_passes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "knowledge/00-System/NOTE.md", "# doc\n")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == PASS, report.render()


def test_infra_sre_ci_second_glob_and_dot_directories_are_reachable():
    """Regression: a naive walker that prunes every dot-directory (the
    convention validate_architecture_gates.py's own _walk_module uses for its
    own, unrelated scan root) would make `.claude/**` and
    `.github/workflows/**` permanently unreachable -- silently vacuous for
    two real manifest-governed paths. Both must be scanned and PASS."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, ".github/workflows/ci.yml", "name: ci\n")
        _write(src, ".claude/agents/foo.md", "# agent\n")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == PASS, report.render()
        assert set(report.checked) == {".github/workflows/ci.yml", ".claude/agents/foo.md"}


# --- SCN-MOD001-103 (negative): deferred surface, application file ----------


def test_deferred_surface_application_file_denied():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "admin-web/App.tsx", "export const x = 1;\n")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == FAIL, report.render()
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.code == "SURFACE_PROFILE_NOT_ACTIVATED"
        assert v.subject == "admin-web/App.tsx"
        assert "Admin Web" in v.detail and "DEFERRED" in v.detail


# --- SCN-MOD001-112 (unnamed-path case) --------------------------------------


def test_unknown_top_level_surface_denied():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "analytics/report.py")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == FAIL, report.render()
        assert report.violations[0].code == "UNKNOWN_SURFACE"
        assert report.violations[0].subject == "analytics/report.py"


def test_unmatched_root_file_is_out_of_surface_scope():
    """ADR-005 Decision 2 Part 3 path-scopes this gate to §4.3's surface
    globs -- a loose repository-root file (no directory nesting, so never a
    candidate surface) that matches no manifest row must be skipped, not
    denied UNKNOWN_SURFACE. Regression for the real-repo default-source run
    denying 53 loose root files (.gitignore, governing baseline docx, a
    scratch commit-message txt) that are not themselves top-level surfaces."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, ".gitignore", "*.pyc\n")
        _write(src, "COMMIT_MSG_SCRATCH.txt", "wip\n")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == PASS, report.render()
        assert set(report.checked) == {".gitignore", "COMMIT_MSG_SCRATCH.txt"}


def test_explicit_manifest_root_row_still_checked():
    """A root file the manifest names explicitly (RELEASE_TRAIN.md's own
    `profile: null` row) must still be matched and PASS via the ordinary
    `exempt` path -- the new root-file skip must not be the only reason it
    passes, and must not interfere with it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "RELEASE_TRAIN.md", "# release train\n")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == PASS, report.render()
        assert report.checked == ["RELEASE_TRAIN.md"]


# --- SCN-MOD001-138/139 (carve-out positive + boundary, same run) -----------


def test_carveout_passes_while_sibling_application_file_denied_same_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        # 138: a recognised build/toolchain file under a still-DEFERRED surface.
        _write(src, "mobile/androidApp/build.gradle.kts", "android {}\n")
        # 139: an application-logic file under the same deferred mobile family,
        # in the very same run, must still be denied -- the carve-out must not
        # widen to the whole directory.
        _write(src, "mobile/shared/src/Foo.kt", "class Foo\n")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == FAIL, report.render()
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.code == "SURFACE_PROFILE_NOT_ACTIVATED"
        assert v.subject == "mobile/shared/src/Foo.kt"
        assert "mobile/androidApp/build.gradle.kts" in report.checked
        assert "mobile/androidApp/build.gradle.kts" not in {v.subject for v in report.violations}


def test_carveout_is_closed_not_open_ended():
    """A filename that is not on the closed carve-out list, even one that
    looks build-adjacent, still denies under a DEFERRED surface."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "mobile/androidApp/build.properties", "x=1\n")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == FAIL, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_NOT_ACTIVATED"


# --- Precedence: known-infrastructure over a §4.3 glob on the same path -----


def test_known_infrastructure_takes_precedence_over_overlapping_glob():
    """IMPLEMENTATION.md §4 gate 7's own disclosed precedence rule: the real
    manifest's 7 known-infra paths and 12 §4.3 globs are disjoint today, so
    this is a synthetic manifest constructed specifically to exercise the
    rule the documentation states for a hypothetical future overlap."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        extra_row = (
            "  - path: admin-web/**\n"
            "    profile: null  # hypothetical future known-infra reclassification\n"
            "    state: n/a\n"
        )
        overlapping = MANIFEST_TEXT.replace(
            "required_agent_roles:", extra_row + "required_agent_roles:")
        assert overlapping != MANIFEST_TEXT  # sanity: splice actually happened
        manifest = _write_manifest(root, overlapping)
        _write(src, "admin-web/App.tsx")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == PASS, report.render()


# --- INCONCLUSIVE / vacuous --------------------------------------------------


def test_empty_source_dir_is_vacuous_not_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        src.mkdir()
        manifest = _write_manifest(root)
        report = run_surface_profile_gate(src, manifest)
        assert report.status == INCONCLUSIVE, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_GATE_VACUOUS"


# --- Fail-closed on malformed/missing input ---------------------------------


def test_missing_manifest_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        _write(src, "backend/app/main.py")
        report = run_surface_profile_gate(src, root / "does-not-exist.yaml")
        assert report.status == ERROR, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_GATE_INPUT_INVALID"


def test_manifest_missing_key_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        _write(src, "backend/app/main.py")
        manifest = _write_manifest(root, "required_agent_roles: []\n")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == ERROR, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_GATE_INPUT_INVALID"


def test_manifest_row_missing_field_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        _write(src, "backend/app/main.py")
        bad = "repository_paths_surfaces:\n  - path: backend/**\n    state: ACTIVATED\n"
        manifest = _write_manifest(root, bad)
        report = run_surface_profile_gate(src, manifest)
        assert report.status == ERROR, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_GATE_INPUT_INVALID"


def test_manifest_inconsistent_profile_state_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        _write(src, "backend/app/main.py")
        bad = (
            "repository_paths_surfaces:\n"
            "  - path: backend/**\n"
            "    profile: null\n"
            "    state: ACTIVATED\n"
        )
        manifest = _write_manifest(root, bad)
        report = run_surface_profile_gate(src, manifest)
        assert report.status == ERROR, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_GATE_INPUT_INVALID"


def test_manifest_unsupported_glob_shape_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        _write(src, "backend/foo/bar.py")
        bad = (
            "repository_paths_surfaces:\n"
            "  - path: backend/*/bar.py\n"
            "    profile: Backend\n"
            "    state: ACTIVATED\n"
        )
        manifest = _write_manifest(root, bad)
        report = run_surface_profile_gate(src, manifest)
        assert report.status == ERROR, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_GATE_INPUT_INVALID"


def test_symlink_in_source_tree_is_error():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "backend/app/main.py")
        (src / "backend" / "app" / "link.py").symlink_to(src / "backend" / "app" / "main.py")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == ERROR, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_GATE_INPUT_INVALID"


# --- Git-backed candidate-input boundary (MOD-001 C04 gate7 default-source --
# --- defect: a plain filesystem walk from REPO_ROOT would recurse into the  -
# --- Git-ignored backend/.venv/ and ERROR on its Python symlink) -----------


def test_git_backed_source_dir_includes_tracked_and_nonignored_untracked():
    """A Git work tree source root must still reach tracked files, plus
    untracked-but-not-ignored files -- explicitly including .claude and
    .github/workflows, the two dot-prefixed known-infra/ACTIVATED paths gate
    7 has always had to be able to see."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "backend/app/main.py")
        _write(src, ".github/workflows/ci.yml", "name: ci\n")
        _write(src, ".claude/agents/foo.md", "# agent\n")
        _git_init(src)
        _git_add(src, "backend/app/main.py")  # .github/.claude left untracked
        report = run_surface_profile_gate(src, manifest)
        assert report.status == PASS, report.render()
        assert set(report.checked) == {
            "backend/app/main.py",
            ".github/workflows/ci.yml",
            ".claude/agents/foo.md",
        }


def test_git_ignored_tree_excluded_even_with_symlink_inside():
    """Direct regression for the concrete defect: a Git-ignored directory
    (modelled on backend/.venv/, excluded via a committed .gitignore rule)
    must never become walk input at all -- not even to be rejected -- so a
    symlink inside it (modelled on backend/.venv/bin/python) no longer
    ERRORs the whole gate."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "backend/app/main.py")
        _git_init(src)
        # Mirrors the real repo's own backend/.gitignore, which is itself
        # under the ACTIVATED backend/** glob -- not a stray top-level file.
        (src / "backend" / ".gitignore").write_text(".venv/\n")
        venv_bin = src / "backend" / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        real = venv_bin / "python3.14"
        real.write_text("#!/bin/sh\n")
        (venv_bin / "python").symlink_to(real)
        _git_add(src, "backend/app/main.py", "backend/.gitignore")
        report = run_surface_profile_gate(src, manifest)
        assert report.status == PASS, report.render()
        assert set(report.checked) == {"backend/app/main.py", "backend/.gitignore"}


def test_git_backed_nonignored_symlink_still_errors():
    """Fail-closed must survive the Git-backed enumeration: a symlink that is
    NOT Git-ignored (unlike the backend/.venv/ case above) still ERRORs the
    gate, whether tracked or merely untracked-and-visible."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "backend/app/main.py")
        _git_init(src)
        (src / "backend" / "app" / "link.py").symlink_to(src / "backend" / "app" / "main.py")
        _git_add(src, "backend/app/main.py")  # link.py left untracked, not ignored
        report = run_surface_profile_gate(src, manifest)
        assert report.status == ERROR, report.render()
        assert report.violations[0].code == "SURFACE_PROFILE_GATE_INPUT_INVALID"


def test_non_git_source_dir_still_uses_plain_walk_fallback():
    """This gate's own synthetic tempfile.TemporaryDirectory fixtures are
    never Git work trees; `_git_candidate_relpaths` must return None for them
    (not raise), leaving the plain-walk fallback -- and its denials -- intact."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "analytics/report.py")
        from validate_surface_profile import _git_candidate_relpaths
        assert _git_candidate_relpaths(src) is None
        report = run_surface_profile_gate(src, manifest)
        assert report.status == FAIL, report.render()
        assert report.violations[0].code == "UNKNOWN_SURFACE"


# --- Pattern-matcher unit coverage ------------------------------------------


def test_pattern_matches_double_star_prefix():
    assert _pattern_matches("backend/app/main.py", "backend/**")
    assert not _pattern_matches("backend2/app/main.py", "backend/**")


def test_pattern_matches_one_level_glob():
    assert _pattern_matches("mobile/TOOLCHAIN_MATRIX.md", "mobile/*.md")
    assert not _pattern_matches("mobile/shared/README.md", "mobile/*.md")


def test_pattern_matches_exact_literal():
    assert _pattern_matches("RELEASE_TRAIN.md", "RELEASE_TRAIN.md")
    assert not _pattern_matches("mobile/RELEASE_TRAIN.md", "RELEASE_TRAIN.md")


def test_pattern_matches_rejects_unsupported_shape():
    try:
        _pattern_matches("backend/foo/bar.py", "backend/*/bar.py")
        raise AssertionError("expected GateInputError")
    except GateInputError:
        pass


# --- CLI dispatch wiring (tools/validate_architecture_gates.py) ------------


def test_cli_surface_profile_no_longer_gate_not_implemented():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "backend/app/main.py")
        res = subprocess.run(
            [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate",
             "surface-profile", "--source-dir", str(src), "--capabilities-manifest",
             str(manifest), "--json"],
            capture_output=True, text=True, check=False,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        payload = json.loads(res.stdout)
        assert payload["status"] == PASS
        assert "GATE_NOT_IMPLEMENTED" not in res.stdout


def test_cli_surface_profile_denial_exit_code_and_text_output():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        manifest = _write_manifest(root)
        _write(src, "admin-web/App.tsx")
        res = subprocess.run(
            [sys.executable, str(TOOLS / "validate_architecture_gates.py"), "--gate",
             "surface-profile", "--source-dir", str(src), "--capabilities-manifest",
             str(manifest)],
            capture_output=True, text=True, check=False,
        )
        assert res.returncode == 1, res.stdout + res.stderr
        assert "SURFACE_PROFILE_NOT_ACTIVATED" in res.stdout


def test_surface_profile_in_implemented_not_deferred():
    from validate_architecture_gates import DEFERRED_GATES, IMPLEMENTED_GATES
    assert "surface-profile" in IMPLEMENTED_GATES
    assert "surface-profile" not in DEFERRED_GATES
    assert "toolchain-qualification" in DEFERRED_GATES


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
