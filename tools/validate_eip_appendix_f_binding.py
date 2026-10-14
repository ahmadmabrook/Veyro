#!/usr/bin/env python3
"""
EIP Appendix F source-authenticity check (MOD-001, GOV-01-R04 gate 5; ADR-014 D2).

`tools/generate_screen_contract_manifest.py` derives screen ownership from
`knowledge/00-System/EIP_MIRROR.md`. `validate_baseline_binding.py` hashes the
frozen EIP DOCX but nothing tied the mirror's Appendix F to that DOCX. This
check closes that gap by extracting Appendix F directly from the DOCX
(stdlib `zipfile` + `xml.etree`, no Pandoc) and comparing it to the mirror:

  1. the Appendix F prose preceding the table (surface-vocabulary mapping,
     registry-authority/count paragraph, generated-row schema / mapping rule),
  2. every module-table row: all six cells (module, wave, TSD domain(s),
     UI/surface ownership, canonical screen mapping rule, ready-state),
  3. that the generator's own parse of the mirror (module, wave, domains,
     surfaces) equals the same derivation from the DOCX cells.

The only normalisation is whitespace collapsing (the mirror is hard-wrapped
fixed-width text; the DOCX has no such wrapping), folding typographic quotes
to ASCII on both sides (Pandoc's rendering), and removal of the mirror's
line-leading markdown markers `# ` / `- ` and header-cell `**` bold. No
wording, case, other punctuation or cell content is normalised. Missing / duplicate / extra / reordered /
truncated rows and any changed owner_domain, surface or mapping-rule text
exit non-zero with a named code. Read-only; never writes any baseline.

Exit: 0 PASS, 1 BLOCKED (findings), 2 ERROR (input unreadable / not found).
"""
import argparse
import hashlib
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

DOCX_NAME = ("Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_"
             "APPROVED_GOVERNING_BASELINE.docx")
DEFAULT_DOCX = REPO_ROOT / DOCX_NAME
DEFAULT_MIRROR = REPO_ROOT / "knowledge/00-System/EIP_MIRROR.md"

HEADING = "Appendix F. Canonical Screen-to-Module Mapping"
HEADER_CELLS = ["Module", "Wave", "TSD domain(s)", "UI / surface ownership",
                "Canonical screen mapping rule", "Ready-state requirement"]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class Error(Exception):
    pass


# Pandoc's markdown writer renders typographic quotes as ASCII; this is the
# only character-level fold, applied identically to both sides.
_QUOTE_FOLD = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def collapse(text: str) -> str:
    return " ".join(text.translate(_QUOTE_FOLD).split())


def _ptext(p: ET.Element) -> str:
    out = []
    for e in p.iter():
        if e.tag == W + "t":
            out.append(e.text or "")
        elif e.tag in (W + "tab", W + "br"):
            out.append(" ")
    return "".join(out)


def extract_docx(docx: Path) -> tuple[list[str], list[list[str]]]:
    """(prose paragraphs between the heading and the table, table rows incl. header)."""
    try:
        with zipfile.ZipFile(docx) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise Error(f"cannot read {docx}: {exc}") from None
    body = root.find(W + "body")
    if body is None:
        raise Error("DOCX has no body")
    kids = list(body)
    hits = [i for i, k in enumerate(kids)
            if k.tag == W + "p" and collapse(_ptext(k)) == HEADING]
    if len(hits) != 1:
        raise Error(f"expected exactly one body heading {HEADING!r} in DOCX, found {len(hits)}")
    prose: list[str] = []
    table = None
    for k in kids[hits[0] + 1:]:
        if k.tag == W + "tbl":
            table = k
            break
        if k.tag == W + "p":
            style = k.find(f"{W}pPr/{W}pStyle")
            if style is not None and style.get(W + "val") == "Heading1" \
                    and collapse(_ptext(k)).startswith("Appendix "):
                break
            text = collapse(_ptext(k))
            if text:
                prose.append(text)
    if table is None:
        raise Error("DOCX Appendix F has no module table")
    if table.find(f".//{W}tbl") is not None:
        raise Error("DOCX Appendix F module table contains a nested table")
    rows = [[collapse(" ".join(_ptext(p) for p in tc.findall(W + "p")))
             for tc in tr.findall(W + "tc")] for tr in table.findall(W + "tr")]
    return prose, rows


def extract_mirror(mirror_text: str) -> tuple[str, list[list[str]]]:
    """(collapsed pre-table prose, table rows incl. header) from the mirror."""
    lines = mirror_text.splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip() == "# " + HEADING]
    if len(starts) != 1:
        raise Error(f"expected exactly one mirror heading {HEADING!r}, found {len(starts)}")
    start = starts[0]
    try:
        head = next(i for i in range(start, len(lines))
                    if "**Module**" in lines[i] and "**Wave**" in lines[i])
    except StopIteration:
        raise Error("mirror Appendix F table header not found") from None
    # Pre-table prose: every line between the heading and the grid's opening
    # rule. The first dash line precedes the header row.
    open_rule = head - 1
    while open_rule > start and not re.fullmatch(r"\s*-{3,}\s*", lines[open_rule]):
        open_rule -= 1
    prose_lines = []
    for l in lines[start + 1:open_rule]:
        l = re.sub(r"^(#|-)\s+", "", l.strip())
        prose_lines.append(l)
    prose = collapse(" ".join(prose_lines))

    header = lines[head]
    tokens = ("**Module**", "**Wave**", "**TSD", "**UI /", "**Canonical", "**Ready-state")
    try:
        cols = [header.index(t) for t in tokens]
    except ValueError:
        raise Error("mirror Appendix F table header columns not found") from None
    if cols != sorted(cols):
        raise Error("mirror Appendix F table header columns out of order")

    def cell(line: str, n: int) -> str:
        return line[cols[n]:cols[n + 1] if n + 1 < len(cols) else None]

    # Header row spans several physical lines until the second rule.
    rows: list[list[str]] = []
    cur: list[str] | None = None
    in_header = True
    dashes = 1  # opening rule already passed
    for line in lines[head:]:
        if re.fullmatch(r"\s*(?:-{3,}\s*)+", line):
            dashes += 1
            if dashes == 3:
                break
            if dashes == 2:
                if cur is not None:
                    rows.append(cur)
                cur, in_header = None, False
            continue
        if not line.strip():
            continue
        if in_header:
            if cur is None:
                cur = [""] * 6
        elif cell(line, 0).strip():
            if cur is not None:
                rows.append(cur)
            cur = [""] * 6
        elif cur is None:
            raise Error("mirror Appendix F row continuation before any row")
        for n in range(6):
            cur[n] = f"{cur[n]} {cell(line, n)}"
    if dashes != 3:
        raise Error("mirror Appendix F module table not terminated by a closing rule")
    if cur is not None:
        rows.append(cur)
    # The header was collected before its separating rule; move it first.
    rows = [[collapse(c) for c in r] for r in rows]
    if rows:  # header cells are bold in the mirror's Pandoc rendering
        rows[0] = [re.fullmatch(r"\*\*(.*)\*\*", c).group(1)
                   if re.fullmatch(r"\*\*(.*)\*\*", c) else c for c in rows[0]]
    return prose, rows


def _modules_from_cells(rows: list[list[str]]):
    """Same derivation the generator applies, from already-extracted cells."""
    import generate_screen_contract_manifest as g
    out = {}
    for module, wave, domain_cell, surface_cell, *_ in rows:
        surfaces: list[str] = []
        if not surface_cell.startswith("Non-UI"):
            for name in (s.strip() for s in surface_cell.split(",")):
                mapped = g.MODULE_SURFACE_MAP[name]  # KeyError => unknown surface
                if mapped and mapped not in surfaces:
                    surfaces.append(mapped)
        out[module] = g.ModuleEntry(module, wave, tuple(g._DOMAIN_RE.findall(domain_cell)),
                                    tuple(surfaces))
    return out


def compare(docx_prose: list[str], docx_rows: list[list[str]],
            mirror_prose: str, mirror_rows: list[list[str]],
            mirror_text: str) -> list[dict]:
    f: list[dict] = []

    def add(code: str, detail: str) -> None:
        f.append({"code": code, "detail": detail})

    want_prose = collapse(" ".join(docx_prose))
    if mirror_prose != want_prose:
        add("APPENDIX_F_PROSE_MISMATCH",
            f"mirror Appendix F prose differs from DOCX (docx {len(want_prose)} chars, "
            f"mirror {len(mirror_prose)} chars)")

    if not docx_rows or docx_rows[0] != HEADER_CELLS:
        add("APPENDIX_F_DOCX_HEADER_UNEXPECTED", f"DOCX header cells {docx_rows[:1]!r}")
    if not mirror_rows or mirror_rows[0] != HEADER_CELLS:
        add("APPENDIX_F_MIRROR_HEADER_MISMATCH",
            f"mirror header cells {mirror_rows[:1]!r} != {HEADER_CELLS!r}")
    d_body, m_body = docx_rows[1:], mirror_rows[1:]

    for label, body in (("DOCX", d_body), ("mirror", m_body)):
        ids = [r[0] for r in body]
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            add("APPENDIX_F_DUPLICATE_ROW", f"{label}: module {dup} appears {ids.count(dup)} times")
    d_ids, m_ids = [r[0] for r in d_body], [r[0] for r in m_body]
    for mod in d_ids:
        if mod not in m_ids:
            add("APPENDIX_F_MISSING_ROW", f"mirror lacks DOCX row {mod}")
    for mod in m_ids:
        if mod not in d_ids:
            add("APPENDIX_F_EXTRA_ROW", f"mirror has row {mod} absent from DOCX")
    if sorted(d_ids) == sorted(m_ids) and d_ids != m_ids:
        add("APPENDIX_F_ROW_ORDER", "mirror row order differs from DOCX")

    m_by = {r[0]: r for r in m_body}
    for d in d_body:
        m = m_by.get(d[0])
        if m is None:
            continue
        if len(d) != 6:
            add("APPENDIX_F_DOCX_ROW_SHAPE", f"{d[0]}: {len(d)} DOCX cells")
            continue
        for n, name in enumerate(HEADER_CELLS):
            if d[n] != m[n]:
                add("APPENDIX_F_CELL_MISMATCH",
                    f"{d[0]} column {name!r}: DOCX {d[n]!r} != mirror {m[n]!r}")

    # Generator-consumption cross-check: what the generator derives from the
    # mirror text must equal the derivation from the DOCX cells.
    try:
        import generate_screen_contract_manifest as g
        from_mirror = g.parse_module_table(mirror_text)
        from_docx = _modules_from_cells(d_body)
        if g.module_table_digest(from_mirror) != g.module_table_digest(from_docx):
            add("APPENDIX_F_GENERATOR_VIEW_MISMATCH",
                "generator's parse of the mirror differs from the DOCX-derived module/wave/"
                "domain/surface table")
    except Exception as exc:  # noqa: BLE001 - any failure here denies
        add("APPENDIX_F_GENERATOR_VIEW_ERROR", f"{type(exc).__name__}: {exc}")
    return f


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--docx", type=Path, default=DEFAULT_DOCX)
    p.add_argument("--mirror", type=Path, default=DEFAULT_MIRROR)
    args = p.parse_args(argv)
    try:
        docx_prose, docx_rows = extract_docx(args.docx)
        mirror_text = args.mirror.read_text(encoding="utf-8")
        mirror_prose, mirror_rows = extract_mirror(mirror_text)
    except (Error, OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    findings = compare(docx_prose, docx_rows, mirror_prose, mirror_rows, mirror_text)
    sha = hashlib.sha256(args.docx.read_bytes()).hexdigest()
    print(f"EIP Appendix F binding: docx sha256 {sha}; docx rows {len(docx_rows) - 1}; "
          f"mirror rows {len(mirror_rows) - 1}")
    if findings:
        print(f"BLOCKED: {len(findings)} finding(s):")
        for x in findings:
            print(f"  - {x['code']}: {x['detail']}")
        return 1
    print("PASS - mirror Appendix F prose and module table match the EIP DOCX "
          "(source-authenticity check only; not certification)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
