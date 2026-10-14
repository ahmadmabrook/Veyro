"""
Focused tests for tools/validate_appendix_b_gov01_traceability.py (EIP
Appendix B GOV-01-R01..R08 split/completion traceability, OWN-009/ADR-015,
MOD-001). Tamper cases run on temp copies only; the frozen DOCX, the real
mirror and MOD-001.md are never written.
"""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
TOOL = ROOT / "tools" / "validate_appendix_b_gov01_traceability.py"
DOCX = ROOT / ("Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_"
               "APPROVED_GOVERNING_BASELINE.docx")
MIRROR = ROOT / "knowledge/00-System/EIP_MIRROR.md"
MOD001 = ROOT / "knowledge/03-Modules/MOD-001/MOD-001.md"
HEAD = "# Appendix B. Blueprint Requirement-to-Implementation-Module Traceability"
OWN009_HEADING = ("### OWN-009 requirement ownership and certification "
                   "dependencies (mapped; no PASS)")


def run(docx: Path, mirror: Path, mod001: Path):
    return subprocess.run(
        [sys.executable, "-E", "-s", str(TOOL), "--docx", str(docx),
         "--mirror", str(mirror), "--mod001", str(mod001)],
        capture_output=True, text=True)


def mirror_with(tmp_path: Path, edit) -> Path:
    text = MIRROR.read_text(encoding="utf-8")
    at = text.index(HEAD)
    out = tmp_path / "mirror.md"
    out.write_text(text[:at] + edit(text[at:]), encoding="utf-8")
    return out


def mod001_with(tmp_path: Path, edit) -> Path:
    text = MOD001.read_text(encoding="utf-8")
    out = tmp_path / "MOD-001.md"
    out.write_text(edit(text), encoding="utf-8")
    return out


def row_block(region: str, req_id: str) -> str:
    m = re.search(rf"^  {req_id} .*?(?=\n\n|\n  -{{5,}})", region, re.S | re.M)
    assert m, req_id
    return m.group(0)


def test_real_sources_pass():
    r = run(DOCX, MIRROR, MOD001)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "docx GOV-01 rows 8; mirror GOV-01 rows 8; OWN-009 rows 8" in r.stdout
    assert "PASS" in r.stdout


# --- DOCX vs mirror: missing / duplicate / drifted GOV-01 rows -------------

def test_mirror_missing_gov01_row_is_blocked(tmp_path):
    tampered = mirror_with(tmp_path, lambda t: t.replace(row_block(t, "GOV-01-R05") + "\n\n", "", 1))
    r = run(DOCX, tampered, MOD001)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "APPENDIXB_MISSING_ROW" in r.stdout or "APPENDIXB_MIRROR_MISSING_ROW" in r.stdout, r.stdout


def test_mirror_duplicate_gov01_row_is_blocked(tmp_path):
    tampered = mirror_with(tmp_path, lambda t: t.replace(
        row_block(t, "GOV-01-R02"), row_block(t, "GOV-01-R02") + "\n\n" + row_block(t, "GOV-01-R02"), 1))
    r = run(DOCX, tampered, MOD001)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "APPENDIXB_DUPLICATE_ROW" in r.stdout, r.stdout


def test_mirror_cell_drift_is_blocked(tmp_path):
    """Mirror's Completing module cell for one row silently changed from the DOCX."""
    tampered = mirror_with(tmp_path, lambda t: t.replace(
        row_block(t, "GOV-01-R04"), row_block(t, "GOV-01-R04").replace("MOD-001", "MOD-099", 1), 1))
    r = run(DOCX, tampered, MOD001)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "APPENDIXB_CELL_MISMATCH" in r.stdout, r.stdout


def test_mirror_row_order_change_is_blocked(tmp_path):
    def swap(t):
        a, b = row_block(t, "GOV-01-R01"), row_block(t, "GOV-01-R02")
        return t.replace(a, "\0A").replace(b, a).replace("\0A", b)
    r = run(DOCX, mirror_with(tmp_path, swap), MOD001)
    assert r.returncode == 1 and "APPENDIXB_ROW_ORDER" in r.stdout, r.stdout


def test_docx_side_wrong_completing_module_is_blocked(tmp_path):
    """Wrong 'original' completing-module/slice data inside the DOCX itself."""
    out = tmp_path / "eip.docx"
    with zipfile.ZipFile(DOCX) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                marker = "CI gates for lint, test,"
                at = text.index(marker)
                # The <w:t>MOD-001</w:t> run nearest before the GOV-01-R04 requirement text.
                mod_at = text.rindex("<w:t>MOD-001</w:t>", 0, at)
                text = text[:mod_at] + text[mod_at:].replace("<w:t>MOD-001</w:t>", "<w:t>MOD-099</w:t>", 1)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    r = run(out, MIRROR, MOD001)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "APPENDIXB_WRONG_COMPLETING_OR_SLICE_DATA" in r.stdout, r.stdout


def test_unreadable_inputs_are_errors_not_pass(tmp_path):
    assert run(tmp_path / "missing.docx", MIRROR, MOD001).returncode == 2
    assert run(DOCX, tmp_path / "missing.md", MOD001).returncode == 2
    assert run(DOCX, MIRROR, tmp_path / "missing.md").returncode == 2
    empty = tmp_path / "empty.md"
    empty.write_text("# nothing\n")
    assert run(DOCX, empty, MOD001).returncode == 2
    assert run(DOCX, MIRROR, empty).returncode == 2


# --- MOD-001.md OWN-009 table: missing mapping / silent dependency loss ----

def test_own009_section_missing_is_error(tmp_path):
    tampered = mod001_with(tmp_path, lambda t: t.replace(OWN009_HEADING, "### Renamed section"))
    r = run(DOCX, MIRROR, tampered)
    assert r.returncode == 2 and "OWN-009" in r.stderr, r.stdout + r.stderr


def test_own009_missing_row_is_blocked(tmp_path):
    def drop_r05(t):
        m = re.search(r"^\| R05 \|.*\|\n", t, re.M)
        assert m
        return t[:m.start()] + t[m.end():]
    r = run(DOCX, MIRROR, mod001_with(tmp_path, drop_r05))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "OWN009_MISSING_ROW" in r.stdout, r.stdout


def test_own009_duplicate_row_is_error(tmp_path):
    def dup_r01(t):
        m = re.search(r"^\| R01 \|.*\|\n", t, re.M)
        assert m
        row = m.group(0)
        return t[:m.end()] + row + t[m.end():]
    r = run(DOCX, MIRROR, mod001_with(tmp_path, dup_r01))
    assert r.returncode == 2 and "duplicate row" in r.stderr, r.stdout + r.stderr


def test_own009_empty_later_owner_cell_is_blocked(tmp_path):
    def blank_r06_later(t):
        m = re.search(r"^(\| R06 \| [^|]*\| )([^|]*)( \|)\n", t, re.M)
        assert m, "R06 row not found"
        return t[:m.start(2)] + "x" + t[m.end(2):]
    r = run(DOCX, MIRROR, mod001_with(tmp_path, blank_r06_later))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "OWN009_LATER_OWNER_CELL_MISSING" in r.stdout, r.stdout


def test_own009_silent_later_dependency_loss_is_blocked(tmp_path):
    """R02's later-owner cell silently drops one previously-mapped MOD-018 reference."""
    tampered = mod001_with(tmp_path, lambda t: t.replace(
        "payment/ledger: MOD-018 and completion MOD-035 (COM-04); ",
        "payment/ledger handled elsewhere; ", 1))
    r = run(DOCX, MIRROR, tampered)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "OWN009_LATER_DEPENDENCY_LOST" in r.stdout, r.stdout
    assert "MOD-018" in r.stdout, r.stdout


def test_own009_widened_later_cell_is_not_a_loss(tmp_path):
    """Adding a module reference (never removing one) must stay PASS."""
    needle = "data migration: MOD-030/031 (LIF-02/LIF-01)."
    def widen(t):
        assert t.count(needle) == 1, f"widening needle not found verbatim: {needle!r}"
        return t.replace(
            needle,
            "data migration: MOD-030/031 (LIF-02/LIF-01); also tracked by MOD-900.", 1)
    r = run(DOCX, MIRROR, mod001_with(tmp_path, widen))
    assert r.returncode == 0, r.stdout + r.stderr


def test_own009_foundation_cells_replaced_with_deferred_is_blocked(tmp_path):
    """BUG-067 P1-1: replacing every mandatory-now foundation cell with a
    deferral stub is the exact inversion of the ADR-015 split and must not
    read as an intact mapping, even though the replacement text clears the
    old length-only threshold."""
    def defer_all(t):
        new_t, n = re.subn(r"^\| (R0[1-8]) \| [^|]*\|",
                            r"| \1 | Deferred to later modules. |", t, flags=re.M)
        assert n == 8, f"expected 8 foundation cells replaced, got {n}"
        return new_t
    r = run(DOCX, MIRROR, mod001_with(tmp_path, defer_all))
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout.count("OWN009_FOUNDATION_CELL_CHANGED") == 8, r.stdout


def test_own009_later_owner_negated_waiver_retaining_ids_is_blocked(tmp_path):
    """BUG-067 P1-2: a waiver that keeps every pinned MOD-### id but negates
    the obligation (no module owes any proof) must not pass just because the
    bare id tokens are all still present."""
    waiver = ("WAIVED by this edit: none of MOD-004, MOD-007, MOD-008, MOD-014, "
              "MOD-016, MOD-017, MOD-018, MOD-020, MOD-022, MOD-030, MOD-031, "
              "MOD-034, MOD-035, MOD-037, MOD-038, MOD-041 owes any proof before "
              "its own certificate.")
    def negate_r02_later(t):
        m = re.search(r"^(\| R02 \| [^|]*\| )([^|]*)( \|)\n", t, re.M)
        assert m, "R02 row not found"
        return t[:m.start(2)] + waiver + t[m.end(2):]
    r = run(DOCX, MIRROR, mod001_with(tmp_path, negate_r02_later))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "OWN009_LATER_OWNER_SEGMENT_LOST" in r.stdout, r.stdout


# BUG-067 P1-2 follow-up: before EXPECTED_LATER_SEGMENTS pinned each row's
# own duty-bearing obligation sentence, deleting that single sentence while
# leaving every pinned MOD-### id and every previously-pinned scope phrase
# intact returned rc 0 for all eight rows (review ceb5819d section A, "8/8
# FALSE GREEN"). Each clause below is copied verbatim (including trailing
# period) from the live OWN-009 table in MOD-001.md.
_ROW_DUTY_CLAUSES = [
    ("R01", "No empty layer or synthetic fixture proves that behavior."),
    ("R02", "Each named module must prove its real authorization, isolation, "
            "financial/concurrency/idempotency and negative paths before its "
            "own certificate."),
    ("R03", "Every introducing module also owes its EIP §21 security/load/"
            "manual-QA scope on actual behavior."),
    ("R04", "Each later module supplies genuine contracts/schema/permissions/"
            "screens/events and proves its applicable gates on its actual "
            "changes; UI owners are the exact source-derived modules/Screen "
            "IDs in EIP Appendix F, not invented owner placeholders."),
    ("R05", "each later deployable module proves its own rollout/rollback "
            "and environment behavior."),
    ("R06", "Every module introducing a schema or data migration owns an "
            "actual expand–migrate/backfill–switch–contract and "
            "rollback/forward-fix proof before its certificate."),
    ("R07", "Store publication and Production promotion remain "
            "owner-reserved."),
    ("R08", "each release of changed product behavior owes its own "
            "changelog, deprecation impact, verification and customer "
            "communication before promotion."),
]


@pytest.mark.parametrize(
    "row_id,clause", _ROW_DUTY_CLAUSES, ids=[row for row, _ in _ROW_DUTY_CLAUSES])
def test_own009_later_owner_duty_clause_negation_is_blocked(tmp_path, row_id, clause):
    """A row's later-owner cell has its approved duty-bearing obligation
    sentence deleted (R04's genuine-contracts/proves-its-gates duty, R06's
    expand-migrate/rollback migration-proof duty, R07's store/Production
    owner-reserved restriction, and the equivalent clause for every other
    row) while every pinned MOD-### id and every other pinned scope phrase
    for that row is left untouched. Must fail closed on its own, not merely
    when combined with an id/phrase loss."""
    def strip_clause(t: str) -> str:
        assert t.count(clause) == 1, (
            f"duty clause not found verbatim for {row_id}: {clause!r}")
        return t.replace(clause, "", 1)
    r = run(DOCX, MIRROR, mod001_with(tmp_path, strip_clause))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "OWN009_LATER_OWNER_SEGMENT_LOST" in r.stdout, r.stdout
    assert f"{row_id}:" in r.stdout, r.stdout


def test_id_set_cross_check_mismatch_is_blocked(tmp_path):
    """OWN-009 table id renamed so it no longer lines up with the DOCX GOV-01 ids."""
    tampered = mod001_with(tmp_path, lambda t: t.replace("| R08 |", "| R09 |", 1))
    r = run(DOCX, MIRROR, tampered)
    assert r.returncode == 1, r.stdout + r.stderr
    assert ("OWN009_MISSING_ROW" in r.stdout or "OWN009_EXTRA_ROW" in r.stdout
            or "APPENDIXB_OWN009_ID_SET_MISMATCH" in r.stdout), r.stdout
