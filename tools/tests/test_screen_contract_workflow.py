"""
Focused tests for .github/workflows/screen-contract.yml (GOV-01-R04 gate 5 PR
CI candidate). The workflow's own `run:` script is executed under bash against
a local mock "remote" (git `insteadOf`), built from copies of the real inputs.

A PASS here is a harness result for the WORKFLOW's trust/verdict logic only.
It is never live gate 5 credit: the real-tree verdict is asserted separately
as FAIL (SCREEN_CONTRACT_OWNER_UNRESOLVED), and the PASS-wrapper test uses a
clearly-labelled stub validator.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "screen-contract.yml"
REPO = "mock/veyro"
DOCX = [
    "Gym_OS_Master_Product_Blueprint_v1_English.docx",
    "Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx",
    "Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx",
]
COPY = DOCX + [
    "veyro-product-experience-design",
    "knowledge/00-System/EIP_MIRROR.md",
    "knowledge/00-System/PROJECT_INDEX.md",
    "knowledge/00-System/SESSION_BOOTSTRAP.md",
    "contracts/ui/screen-registry.json",
    "contracts/ui/screen-contracts.yaml",
    "tools/validate_architecture_gates.py",
    "tools/validate_baseline_binding.py",
    "tools/validate_eip_appendix_f_binding.py",
    "tools/generate_screen_contract_manifest.py",
    "tools/generate_screen_registry.py",
]
STUB_PASS = (
    '# mock validator "screen-contract"\nimport json,sys\n'
    'print(json.dumps({"gate":"screen-contract","status":%r,"violations":[]}))\n'
    'sys.exit(%d)\n'
)


def run_script() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    block = text.split("        run: |\n", 1)[1]
    return "".join(re.sub(r"^          ", "", ln, count=1) for ln in block.splitlines(True))


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


def copy_in(repo: Path) -> None:
    for rel in COPY:
        src, dst = ROOT / rel, repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


@pytest.fixture()
def world(tmp_path):
    """Trusted repo T (commit) and a clone C that the test mutates into a candidate."""
    t = tmp_path / "t"
    t.mkdir()
    git(t, "init", "-q")
    copy_in(t)
    git(t, "add", "-A")
    git(t, "commit", "-q", "-m", "trusted")
    trusted = git(t, "rev-parse", "HEAD")
    c = tmp_path / "c"
    subprocess.run(["git", "clone", "-q", str(t), str(c)], check=True)
    return {"t": t, "c": c, "trusted": trusted, "tmp": tmp_path}


def run(world, trusted_sha=None, head_sha=None):
    """Both trusted and candidate objects resolve through one mock remote (T plus C's commits)."""
    t, c = world["t"], world["c"]
    git(t, "fetch", "-q", str(c), "HEAD")
    head = head_sha or git(c, "rev-parse", "HEAD")
    env = {
        "PATH": os.environ["PATH"], "HOME": str(world["tmp"]),
        "REPO": REPO, "TRUSTED_SHA": trusted_sha or world["trusted"], "HEAD_SHA": head,
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": f"url.{t}.insteadOf",
        "GIT_CONFIG_VALUE_0": f"https://github.com/{REPO}.git",
        "GIT_CONFIG_KEY_1": "uploadpack.allowAnySHA1InWant",
        "GIT_CONFIG_VALUE_1": "true",
        "PYTHON_BIN": sys.executable,
    }
    py = world["tmp"] / "bin"
    py.mkdir(exist_ok=True)
    (py / "python3").symlink_to(sys.executable)
    env["PATH"] = f"{py}:{env['PATH']}"
    return subprocess.run(["bash", "-c", run_script()], env=env, capture_output=True,
                          text=True, timeout=120)


def commit_candidate(world, msg="cand"):
    git(world["c"], "add", "-A")
    git(world["c"], "commit", "-q", "-m", msg)


# --- static workflow shape -------------------------------------------------

def test_workflow_shape_and_trust_lint():
    text = WORKFLOW.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "pull_request_target" in code and "name: architecture-screen-contract" in code
    for banned in ("secrets.", "uses:", "continue-on-error", "if: always()", "paths:",
                   "workflow_dispatch"):
        assert banned not in code, banned
    assert "github.event.pull_request.head.sha" in code
    assert "pull_request.head.ref" not in code and "head_ref" not in code
    r = subprocess.run([sys.executable, str(ROOT / "tools/validate_workflow_trust.py"), str(WORKFLOW)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    subprocess.run(["bash", "-n"], input=run_script(), text=True, check=True)
    # Inline verdict interpreter runs in isolated mode (-I), never -E -s.
    assert re.search(r"^\s*python3 -I - ", code, re.M)
    assert not re.search(r"python3 -E -s -(\s|$)", code)


# --- trust boundary / negatives -------------------------------------------

def test_live_tree_gate_verdict_is_deny_owner_unresolved(world):
    r = run(world)
    assert r.returncode != 0
    assert "SCREEN_CONTRACT_OWNER_UNRESOLVED" in r.stdout + r.stderr
    assert "PASS (live gate 5" not in r.stdout


def test_trusted_snapshot_without_gate_5_fails_closed(world):
    t = world["t"]
    (t / "tools/generate_screen_contract_manifest.py").unlink()
    git(t, "add", "-A")
    git(t, "commit", "-q", "-m", "no generator")
    world["trusted"] = git(t, "rev-parse", "HEAD")
    r = run(world)
    assert r.returncode != 0
    assert "never NOT_APPLICABLE" in r.stderr
    assert "PASS" not in r.stdout


def test_candidate_validator_is_never_executed(world):
    c = world["c"]
    (c / "tools/validate_architecture_gates.py").write_text(STUB_PASS % ("PASS", 0))
    (c / "tools/validate_baseline_binding.py").write_text("raise SystemExit(0)\n")
    commit_candidate(world)
    r = run(world)
    assert r.returncode != 0
    assert "SCREEN_CONTRACT_OWNER_UNRESOLVED" in r.stdout + r.stderr


def test_tampered_eip_mirror_is_denied(world):
    c = world["c"]
    p = c / "knowledge/00-System/EIP_MIRROR.md"
    p.write_text(p.read_text() + "\ntamper\n")
    commit_candidate(world)
    r = run(world)
    assert r.returncode != 0
    assert "changed frozen governing input knowledge/00-System/EIP_MIRROR.md" in r.stderr


def test_tampered_registry_source_is_denied(world):
    c = world["c"]
    p = c / "veyro-product-experience-design/project/veyro-registry-data.js"
    p.write_text(p.read_text() + "\n// tamper\n")
    commit_candidate(world)
    r = run(world)
    assert r.returncode != 0
    assert "changed frozen governing input veyro-product-experience-design" in r.stderr


def test_symlinked_candidate_manifest_is_denied(world):
    c = world["c"]
    p = c / "contracts/ui/screen-contracts.yaml"
    p.unlink()
    p.symlink_to("screen-registry.json")
    commit_candidate(world)
    r = run(world)
    assert r.returncode != 0
    assert "absent or not a regular blob" in r.stderr


def test_missing_candidate_manifest_is_denied_not_applicable_is_never_used(world):
    c = world["c"]
    (c / "contracts/ui/screen-contracts.yaml").unlink()
    commit_candidate(world)
    r = run(world)
    assert r.returncode != 0
    assert "NOT_APPLICABLE" not in r.stdout


# --- verdict wrapper (mock validator in the TRUSTED snapshot only) ----------

@pytest.mark.parametrize("status,code,passes", [
    ("PASS", 0, True), ("PASS", 1, False), ("FAIL", 0, False), ("INCONCLUSIVE", 0, False),
])
def test_verdict_wrapper_passes_only_on_live_pass(world, status, code, passes):
    t = world["t"]
    (t / "tools/validate_architecture_gates.py").write_text(STUB_PASS % (status, code))
    git(t, "add", "-A")
    git(t, "commit", "-q", "-m", "stub")
    world["trusted"] = git(t, "rev-parse", "HEAD")
    r = run(world)
    assert (r.returncode == 0) is passes, r.stdout + r.stderr


def test_trusted_mirror_diverging_from_docx_is_denied_before_gate_5(world):
    """Trusted snapshot whose mirror owner_domain/surface was altered: DENY, gate 5 never runs."""
    t = world["t"]
    p = t / "knowledge/00-System/EIP_MIRROR.md"
    text = p.read_text()
    at = text.index("# Appendix F. Canonical Screen-to-Module Mapping")
    assert "GOV-01  " in text[at:]
    p.write_text(text[:at] + text[at:].replace("GOV-01  ", "GOV-09  ", 1))
    git(t, "add", "-A")
    git(t, "commit", "-q", "-m", "diverged mirror")
    world["trusted"] = git(t, "rev-parse", "HEAD")
    git(world["c"], "pull", "-q")  # candidate carries the same (diverged) mirror
    r = run(world)
    assert r.returncode != 0
    assert "Appendix F mirror does not match the EIP docx" in r.stderr
    assert "SCREEN_CONTRACT_OWNER_UNRESOLVED" not in r.stdout + r.stderr


def test_trusted_snapshot_without_appendix_f_verifier_fails_closed(world):
    t = world["t"]
    (t / "tools/validate_eip_appendix_f_binding.py").unlink()
    git(t, "add", "-A")
    git(t, "commit", "-q", "-m", "no verifier")
    world["trusted"] = git(t, "rev-parse", "HEAD")
    r = run(world)
    assert r.returncode != 0
    assert "never NOT_APPLICABLE" in r.stderr


def test_changed_candidate_project_index_is_denied(world):
    c = world["c"]
    p = c / "knowledge/00-System/PROJECT_INDEX.md"
    p.write_text(p.read_text() + "\ntamper\n")
    commit_candidate(world)
    r = run(world)
    assert r.returncode != 0
    assert "changed frozen governing input knowledge/00-System/PROJECT_INDEX.md" in r.stderr
    assert "SCREEN_CONTRACT_OWNER_UNRESOLVED" not in r.stdout + r.stderr


def test_missing_candidate_project_index_is_denied(world):
    c = world["c"]
    (c / "knowledge/00-System/PROJECT_INDEX.md").unlink()
    commit_candidate(world)
    r = run(world)
    assert r.returncode != 0
    assert "candidate lacks knowledge/00-System/PROJECT_INDEX.md" in r.stderr
