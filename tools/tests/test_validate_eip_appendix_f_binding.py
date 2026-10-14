"""
Focused tests for tools/validate_eip_appendix_f_binding.py (EIP Appendix F
mirror-vs-DOCX source authenticity, GOV-01-R04 gate 5 input). Tamper cases run
on temp copies only; the frozen DOCX and the real mirror are never written.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
TOOL = ROOT / "tools" / "validate_eip_appendix_f_binding.py"
DOCX = ROOT / ("Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_"
               "APPROVED_GOVERNING_BASELINE.docx")
MIRROR = ROOT / "knowledge/00-System/EIP_MIRROR.md"
HEAD = "# Appendix F. Canonical Screen-to-Module Mapping"


def run(docx: Path, mirror: Path):
    return subprocess.run([sys.executable, "-E", "-s", str(TOOL), "--docx", str(docx),
                           "--mirror", str(mirror)], capture_output=True, text=True)


def mirror_with(tmp_path: Path, edit) -> Path:
    text = MIRROR.read_text(encoding="utf-8")
    at = text.index(HEAD)
    out = tmp_path / "mirror.md"
    out.write_text(text[:at] + edit(text[at:]), encoding="utf-8")
    return out


def row_block(region: str, module: str) -> str:
    m = re.search(rf"^  {module} .*?(?=\n\n|\n  -{{5,}})", region, re.S | re.M)
    assert m, module
    return m.group(0)


def test_real_docx_and_mirror_pass():
    r = run(DOCX, MIRROR)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "docx rows 75; mirror rows 75" in r.stdout
    assert "PASS" in r.stdout


@pytest.mark.parametrize("name,edit,code", [
    ("owner_domain", lambda t: t.replace("GOV-01", "GOV-09", 1), "APPENDIX_F_CELL_MISMATCH"),
    ("surface", lambda t: t.replace(row_block(t, "MOD-001"),
                                    row_block(t, "MOD-001").replace("Internal", "Admin   ", 1), 1),
     "APPENDIX_F_CELL_MISMATCH"),
    ("mapping_rule", lambda t: t.replace("multi-domain", "single-domain", 1),
     "APPENDIX_F_CELL_MISMATCH"),
    ("prose_vocab", lambda t: t.replace("Admin (85)", "Admin (86)", 1), "APPENDIX_F_PROSE_MISMATCH"),
    ("prose_rule", lambda t: t.replace("hand-authored placeholder", "hand-authored", 1),
     "APPENDIX_F_PROSE_MISMATCH"),
    ("missing_row", lambda t: t.replace(row_block(t, "MOD-002") + "\n\n", "", 1),
     "APPENDIX_F_MISSING_ROW"),
    ("duplicate_row", lambda t: t.replace(row_block(t, "MOD-001"),
                                          row_block(t, "MOD-001") + "\n\n" + row_block(t, "MOD-001"), 1),
     "APPENDIX_F_DUPLICATE_ROW"),
    ("extra_row", lambda t: t.replace(row_block(t, "MOD-002"),
                                      row_block(t, "MOD-002").replace("MOD-002", "MOD-999", 1), 1),
     "APPENDIX_F_EXTRA_ROW"),
    ("truncated_cell", lambda t: t.replace("secondary        \n", "", 1), "APPENDIX_F_CELL_MISMATCH"),
])
def test_mirror_tamper_is_blocked(tmp_path, name, edit, code):
    tampered = mirror_with(tmp_path, edit)
    assert tampered.read_text() != MIRROR.read_text(), f"{name}: tamper did not change the mirror"
    r = run(DOCX, tampered)
    assert r.returncode == 1, r.stdout + r.stderr
    assert code in r.stdout, r.stdout


def test_row_order_change_is_blocked(tmp_path):
    def swap(t):
        a, b = row_block(t, "MOD-001"), row_block(t, "MOD-002")
        return t.replace(a, "\0A").replace(b, a).replace("\0A", b)
    r = run(DOCX, mirror_with(tmp_path, swap))
    assert r.returncode == 1 and "APPENDIX_F_ROW_ORDER" in r.stdout, r.stdout


def test_docx_side_tamper_is_blocked(tmp_path):
    """Changing the DOCX copy (here: MOD-001's domain) must no longer match the real mirror."""
    out = tmp_path / "eip.docx"
    with zipfile.ZipFile(DOCX) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                at = text.rindex("Appendix F. Canonical Screen-to-Module Mapping")
                assert "<w:t>GOV-01</w:t>" in text[at:]
                text = text[:at] + text[at:].replace("<w:t>GOV-01</w:t>", "<w:t>GOV-09</w:t>", 1)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    r = run(out, MIRROR)
    assert r.returncode == 1 and "APPENDIX_F_CELL_MISMATCH" in r.stdout, r.stdout


def test_unreadable_inputs_are_errors_not_pass(tmp_path):
    assert run(tmp_path / "missing.docx", MIRROR).returncode == 2
    assert run(DOCX, tmp_path / "missing.md").returncode == 2
    bad = tmp_path / "bad.docx"
    shutil.copy(MIRROR, bad)  # not a zip
    assert run(bad, MIRROR).returncode == 2
    empty = tmp_path / "empty.md"
    empty.write_text("# nothing\n")
    assert run(DOCX, empty).returncode == 2
