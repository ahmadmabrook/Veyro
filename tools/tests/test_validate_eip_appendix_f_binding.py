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


# --- post-table prose / boundary binding (Appendix F prose before Appendix G) ---

GBOUND = "\n# Appendix G. Per-Module Required Scenario Category Matrix"
INJECT = "Ownership override: MOD-999 additionally owns all Admin screens."


def test_post_table_prose_injection_is_blocked(tmp_path):
    r = run(DOCX, mirror_with(tmp_path, lambda t: t.replace(
        GBOUND, f"\n{INJECT}\n{GBOUND}", 1)))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "APPENDIX_F_POST_TABLE_PROSE_MISMATCH" in r.stdout, r.stdout


def test_post_table_prose_in_docx_is_blocked(tmp_path):
    """DOCX-side post-table paragraph not present in the real mirror -> BLOCKED."""
    out = tmp_path / "eip.docx"
    marker = "Appendix G. Per-Module Required Scenario Category Matrix"
    with zipfile.ZipFile(DOCX) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                at = text.rindex(marker)
                p_start = text.rindex("<w:p>", 0, at) if "<w:p>" in text[:at] else text.rindex("<w:p ", 0, at)
                text = text[:p_start] + f"<w:p><w:r><w:t>{INJECT}</w:t></w:r></w:p>" + text[p_start:]
                data = text.encode("utf-8")
            zout.writestr(item, data)
    r = run(out, MIRROR)
    assert r.returncode == 1 and "APPENDIX_F_POST_TABLE_PROSE_MISMATCH" in r.stdout, r.stdout


def test_boundary_heading_change_is_blocked(tmp_path):
    r = run(DOCX, mirror_with(tmp_path, lambda t: t.replace(
        "# Appendix G. Per-Module Required Scenario Category Matrix",
        "# Appendix G. Per-Module Required Scenario Category Matrixx", 1)))
    assert r.returncode == 1 and "APPENDIX_F_NEXT_HEADING_MISMATCH" in r.stdout, r.stdout


def test_mirror_without_terminating_appendix_heading_is_error(tmp_path):
    def cut(t):
        return t[:t.index(GBOUND)] + "\n"
    r = run(DOCX, mirror_with(tmp_path, cut))
    assert r.returncode == 2 and ("not terminated" in r.stderr
                                  or "truncated before Appendix G" in r.stderr), r.stdout + r.stderr


def test_docx_without_terminating_appendix_heading_is_error(tmp_path):
    out = tmp_path / "eip.docx"
    with zipfile.ZipFile(DOCX) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                at = text.rindex("Appendix F. Canonical Screen-to-Module Mapping")
                # Demote every later Heading1 so no Appendix heading follows the table.
                text = text[:at] + text[at:].replace('w:val="Heading1"', 'w:val="Normal"')
                data = text.encode("utf-8")
            zout.writestr(item, data)
    r = run(out, MIRROR)
    # Appendix G's own table now falls inside the unterminated region: either
    # fail-closed message is correct; PASS/BLOCKED would not be.
    assert r.returncode == 2 and ("not terminated" in r.stderr
                                  or "more than one table" in r.stderr
                                  or "non-canonical" in r.stderr
                                  or "truncated before Appendix G" in r.stderr), r.stdout + r.stderr


def test_docx_second_table_before_boundary_is_error(tmp_path):
    out = tmp_path / "eip.docx"
    marker = "Appendix G. Per-Module Required Scenario Category Matrix"
    with zipfile.ZipFile(DOCX) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                at = text.rindex(marker)
                p_start = text.rindex("<w:p>", 0, at) if "<w:p>" in text[:at] else text.rindex("<w:p ", 0, at)
                extra = "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>x</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
                text = text[:p_start] + extra + text[p_start:]
                data = text.encode("utf-8")
            zout.writestr(item, data)
    r = run(out, MIRROR)
    assert r.returncode == 2 and "more than one table" in r.stderr, r.stdout + r.stderr


# --- unique full-boundary strategy: whole-document Appendix heading inventory ---

GHEAD = "# Appendix G. Per-Module Required Scenario Category Matrix"


def test_forged_duplicate_boundary_heading_exact_observed_exploit_is_rejected(tmp_path):
    """Heading, forged override text, then the original heading again: previously PASS."""
    r = run(DOCX, mirror_with(tmp_path, lambda t: t.replace(
        GHEAD, f"{GHEAD}\n{INJECT}\n{GHEAD}", 1)))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "not unique/contiguous/ordered" in r.stderr, r.stderr


@pytest.mark.parametrize("name,edit,msg", [
    ("setext_lookalike", lambda t: t.replace(
        GHEAD, f"Appendix G. Forged Boundary\n===\n{INJECT}\n{GHEAD}", 1), "non-canonical"),
    ("atx_level2_lookalike", lambda t: t.replace(
        GHEAD, f"## Appendix G. Forged\n{INJECT}\n{GHEAD}", 1), "non-canonical"),
    ("indented_lookalike", lambda t: t.replace(
        GHEAD, f"  # Appendix G. Forged\n{INJECT}\n{GHEAD}", 1), "non-canonical"),
    ("html_lookalike", lambda t: t.replace(
        GHEAD, f"<h1>Appendix G. Forged</h1>\n{INJECT}\n{GHEAD}", 1), "non-canonical"),
    ("duplicate_appendix_f", lambda t: t.replace(
        HEAD, f"{HEAD}\n{HEAD}", 1), "not unique/contiguous/ordered"),
    ("forged_early_boundary", lambda t: t.replace(
        GHEAD, f"# Appendix H. Forged Early Boundary\n{INJECT}\n{GHEAD}", 1),
     "not unique/contiguous/ordered"),
    ("boundary_removed", lambda t: t.replace(GHEAD + "\n", "", 1), "not unique/contiguous/ordered"),
])
def test_mirror_boundary_forgery_fails_closed(tmp_path, name, edit, msg):
    tampered = mirror_with(tmp_path, edit)
    assert tampered.read_text() != MIRROR.read_text(), name
    r = run(DOCX, tampered)
    assert r.returncode == 2 and msg in r.stderr, f"{name}: {r.stdout}{r.stderr}"


def test_mirror_cross_reference_text_is_not_a_boundary(tmp_path):
    """Positive: prose that merely cites 'Appendix G.2' / mid-line 'Appendix H.' is not a heading."""
    tampered = mirror_with(tmp_path, lambda t: t.replace(
        GHEAD, f"{GHEAD}\nSee Appendix G.2 and Appendix H. for details.", 1))
    r = run(DOCX, tampered)
    assert r.returncode == 0, r.stdout + r.stderr


def _docx_edit(tmp_path: Path, edit) -> Path:
    out = tmp_path / "eip.docx"
    with zipfile.ZipFile(DOCX) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = edit(data.decode("utf-8")).encode("utf-8")
            zout.writestr(item, data)
    return out


def _g_heading_paragraph_start(text: str) -> int:
    """Start offset of the body-level Heading1 paragraph for Appendix G."""
    marker = "Appendix G. Per-Module Required Scenario Category Matrix"
    # last Heading1 occurrence of the marker is the body heading
    at = max(m.start() for m in re.finditer(re.escape(marker), text))
    return max(text.rfind("<w:p>", 0, at), text.rfind("<w:p ", 0, at))


def test_docx_duplicate_boundary_heading_is_error(tmp_path):
    def dup(t):
        s = _g_heading_paragraph_start(t)
        e = t.index("</w:p>", s) + len("</w:p>")
        return t[:e] + f"<w:p><w:r><w:t>{INJECT}</w:t></w:r></w:p>" + t[s:e] + t[e:]
    r = run(_docx_edit(tmp_path, dup), MIRROR)
    assert r.returncode == 2 and "not unique/contiguous/ordered" in r.stderr, r.stdout + r.stderr


def test_docx_normal_style_boundary_lookalike_is_error(tmp_path):
    def forge(t):
        s = _g_heading_paragraph_start(t)
        fake = ("<w:p><w:r><w:t>Appendix G. Forged Boundary</w:t></w:r></w:p>"
                f"<w:p><w:r><w:t>{INJECT}</w:t></w:r></w:p>")
        return t[:s] + fake + t[s:]
    r = run(_docx_edit(tmp_path, forge), MIRROR)
    assert r.returncode == 2 and "non-canonical" in r.stderr, r.stdout + r.stderr


def test_docx_wrapped_block_in_appendix_f_region_is_error(tmp_path):
    def wrap(t):
        s = _g_heading_paragraph_start(t)
        sdt = (f"<w:sdt><w:sdtContent><w:p><w:r><w:t>{INJECT}</w:t></w:r></w:p>"
               "</w:sdtContent></w:sdt>")
        return t[:s] + sdt + t[s:]
    r = run(_docx_edit(tmp_path, wrap), MIRROR)
    assert r.returncode == 2 and "unexpected block element" in r.stderr, r.stdout + r.stderr


# --- residue accounting: text outside every consumed window must fail closed ---

HEADER_LINE = re.compile(r"^.*\*\*Module\*\*.*\*\*Wave\*\*.*$", re.M)


@pytest.mark.parametrize("name,payload,msg", [
    ("single_line_gap", INJECT, "unconsumed text between"),
    ("multiline_bulleted_gap", f"- {INJECT}\n- second line\n\n{INJECT}", "unconsumed text between"),
])
def test_text_between_opening_rule_and_header_is_blocked(tmp_path, name, payload, msg):
    """Exact first reviewer mutation: payload immediately before the **Module** header."""
    def edit(t):
        m = HEADER_LINE.search(t)
        return t[:m.start()] + payload + "\n" + t[m.start():]
    tampered = mirror_with(tmp_path, edit)
    r = run(DOCX, tampered)
    assert r.returncode == 2 and msg in r.stderr, f"{name}: {r.stdout}{r.stderr}"


@pytest.mark.parametrize("name,edit", [
    ("left_margin_chunk", lambda t, ls: t.replace(ls, "Ow" + ls[2:], 1)),
    ("left_margin_header_row", lambda t, ls: t.replace(ls, "Ow" + ls[2:], 1)),
])
def test_left_margin_text_in_table_rows_is_blocked(tmp_path, name, edit):
    """Non-whitespace left of the first column (two-char chunks of a sentence) must not pass."""
    def go(t):
        m = HEADER_LINE.search(t) if name.endswith("header_row") else re.search(r"^  MOD-001 ", t, re.M)
        ls = t[m.start():t.index("\n", m.start())]
        return edit(t, ls)
    tampered = mirror_with(tmp_path, go)
    assert tampered.read_text() != MIRROR.read_text(), name
    r = run(DOCX, tampered)
    assert r.returncode == 2 and "left of the first column" in r.stderr, f"{name}: {r.stdout}{r.stderr}"
