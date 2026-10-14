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
     the prose after the table up to the next Appendix heading, and that
     boundary heading itself (missing boundary fails closed),
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


def _is_appendix_heading(k: ET.Element) -> bool:
    if k.tag != W + "p":
        return False
    style = k.find(f"{W}pPr/{W}pStyle")
    return (style is not None and style.get(W + "val") == "Heading1"
            and collapse(_ptext(k)).startswith("Appendix "))


_DOCX_APPX = re.compile(r"Appendix ([A-Z])\. \S")
_DOCX_APPX_LOOSE = re.compile(r"Appendix\s+[A-Za-z]\s*[.:)]\s+\S", re.I)
_MIRROR_APPX_STRICT = re.compile(r"# Appendix ([A-Z])\. \S.*")
# Anything that could be read as an Appendix heading in ATX/HTML markdown form
# (grid-table cell text such as "Appendix A.   Appendix B." is not a heading).
_MIRROR_APPX_LOOSE = re.compile(r"[\s>*_`|-]*(?:<h[1-6][^>]*>\s*|#+\s*)appendix\b", re.I)
_SETEXT_TITLE = re.compile(r"\s{0,3}appendix\s+[A-Za-z]\s*[.:)]\s+\S", re.I)
_SETEXT_RULE = re.compile(r"\s{0,3}(?:=+|-+)\s*")


def _check_inventory(label: str, headings: list[str]) -> None:
    """Whole-document Appendix heading inventory must be A, B, C... each exactly
    once, in order, with Appendix F followed immediately by Appendix G. A
    duplicated, forged, reordered or missing boundary heading fails closed."""
    letters = [h[len("Appendix "):][0] for h in headings]
    want = [chr(ord("A") + i) for i in range(len(letters))]
    if letters != want:
        raise Error(f"{label}: Appendix headings are not unique/contiguous/ordered from A: "
                    f"{''.join(letters)!r}")
    if len(letters) < 7:
        raise Error(f"{label}: Appendix heading inventory truncated before Appendix G "
                    f"({''.join(letters)!r})")
    if headings[5] != HEADING:
        raise Error(f"{label}: Appendix F heading text unexpected: {headings[5]!r}")


def docx_heading_inventory(body: ET.Element) -> list[str]:
    """Every direct-body paragraph that reads as an 'Appendix X.' heading must be
    a canonical Heading1; a Normal-style lookalike (forged boundary) fails closed.
    Table-cell paragraphs (the DOCX's own cross-reference tables list the Appendix
    titles) are never section boundaries and are not inventoried."""
    found: list[str] = []
    for k in body:
        if k.tag != W + "p":
            continue
        text = collapse(_ptext(k))
        heading = _is_appendix_heading(k)
        if not heading and not _DOCX_APPX_LOOSE.match(text):
            continue
        if not heading or not _DOCX_APPX.match(text):
            raise Error(f"DOCX: non-canonical Appendix heading-like paragraph {text[:80]!r}")
        found.append(text)
    _check_inventory("DOCX", found)
    return found


def mirror_heading_inventory(lines: list[str]) -> list[str]:
    found: list[str] = []
    for i, l in enumerate(lines):
        setext = (_SETEXT_TITLE.match(l) and i + 1 < len(lines)
                  and _SETEXT_RULE.fullmatch(lines[i + 1]))
        if not (_MIRROR_APPX_LOOSE.match(l) or setext):
            continue
        if not _MIRROR_APPX_STRICT.fullmatch(l):
            raise Error(f"mirror: non-canonical Appendix heading-like line {l.strip()[:80]!r}")
        found.append(collapse(l[2:]))
    _check_inventory("mirror", found)
    return found


def extract_docx(docx: Path) -> tuple[list[str], list[list[str]], list[str], str]:
    """(pre-table prose paragraphs, table rows incl. header, post-table prose
    paragraphs up to the next Appendix heading, that next heading's text)."""
    try:
        with zipfile.ZipFile(docx) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise Error(f"cannot read {docx}: {exc}") from None
    body = root.find(W + "body")
    if body is None:
        raise Error("DOCX has no body")
    inventory = docx_heading_inventory(body)
    kids = list(body)
    hits = [i for i, k in enumerate(kids)
            if k.tag == W + "p" and collapse(_ptext(k)) == HEADING]
    if len(hits) != 1:
        raise Error(f"expected exactly one body heading {HEADING!r} in DOCX, found {len(hits)}")
    region_end = next(i for i in range(hits[0] + 1, len(kids)) if _is_appendix_heading(kids[i]))
    for k in kids[hits[0] + 1:region_end]:
        if k.tag not in (W + "p", W + "tbl", W + "sectPr", W + "bookmarkStart", W + "bookmarkEnd"):
            raise Error(f"DOCX Appendix F region contains unexpected block element {k.tag}")
    prose: list[str] = []
    table = None
    for k in kids[hits[0] + 1:]:
        if k.tag == W + "tbl":
            table = k
            break
        if k.tag == W + "p":
            if _is_appendix_heading(k):
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
    # Everything after the table up to the next Appendix heading is Appendix F
    # prose too. A second table, or no terminating heading, fails closed.
    post: list[str] = []
    next_heading = None
    for k in kids[kids.index(table) + 1:]:
        if k.tag == W + "tbl":
            raise Error("DOCX Appendix F has more than one table before the next Appendix heading")
        if k.tag != W + "p":
            continue
        if _is_appendix_heading(k):
            next_heading = collapse(_ptext(k))
            break
        text = collapse(_ptext(k))
        if text:
            post.append(text)
    if next_heading is None:
        raise Error("DOCX Appendix F is not terminated by a following Appendix heading")
    if next_heading != inventory[6]:
        raise Error(f"DOCX Appendix F boundary {next_heading!r} is not the unique Appendix G heading")
    return prose, rows, post, next_heading


def extract_mirror(mirror_text: str) -> tuple[str, list[list[str]], str, str]:
    """(collapsed pre-table prose, table rows incl. header, collapsed post-table
    prose up to the next Appendix heading, that heading's text) from the mirror."""
    lines = mirror_text.splitlines()
    inventory = mirror_heading_inventory(lines)
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
    close = None
    for idx in range(head, len(lines)):
        line = lines[idx]
        if re.fullmatch(r"\s*(?:-{3,}\s*)+", line):
            dashes += 1
            if dashes == 3:
                close = idx
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
    # Post-table prose: every line after the closing rule up to the next
    # Appendix heading; no terminating heading fails closed.
    end = next((i for i in range(close + 1, len(lines))
                if re.match(r"# Appendix [A-Z]\. ", lines[i])), None)
    if end is None:
        raise Error("mirror Appendix F is not terminated by a following Appendix heading")
    post_lines = [re.sub(r"^(#|-)\s+", "", l.strip()) for l in lines[close + 1:end]]
    post = collapse(" ".join(post_lines))
    next_heading = collapse(re.sub(r"^#\s+", "", lines[end]))
    if next_heading != inventory[6]:
        raise Error(f"mirror Appendix F boundary {next_heading!r} is not the unique Appendix G heading")
    # The header was collected before its separating rule; move it first.
    rows = [[collapse(c) for c in r] for r in rows]
    if rows:  # header cells are bold in the mirror's Pandoc rendering
        rows[0] = [re.fullmatch(r"\*\*(.*)\*\*", c).group(1)
                   if re.fullmatch(r"\*\*(.*)\*\*", c) else c for c in rows[0]]
    return prose, rows, post, next_heading


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
            mirror_text: str, docx_post: list[str], mirror_post: str,
            docx_next: str, mirror_next: str) -> list[dict]:
    f: list[dict] = []

    def add(code: str, detail: str) -> None:
        f.append({"code": code, "detail": detail})

    want_prose = collapse(" ".join(docx_prose))
    if mirror_prose != want_prose:
        add("APPENDIX_F_PROSE_MISMATCH",
            f"mirror Appendix F prose differs from DOCX (docx {len(want_prose)} chars, "
            f"mirror {len(mirror_prose)} chars)")

    want_post = collapse(" ".join(docx_post))
    if mirror_post != want_post:
        add("APPENDIX_F_POST_TABLE_PROSE_MISMATCH",
            f"mirror Appendix F post-table prose {mirror_post!r} != DOCX {want_post!r}")
    if mirror_next != docx_next:
        add("APPENDIX_F_NEXT_HEADING_MISMATCH",
            f"mirror boundary heading {mirror_next!r} != DOCX {docx_next!r}")

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
        docx_prose, docx_rows, docx_post, docx_next = extract_docx(args.docx)
        mirror_text = args.mirror.read_text(encoding="utf-8")
        mirror_prose, mirror_rows, mirror_post, mirror_next = extract_mirror(mirror_text)
    except (Error, OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    findings = compare(docx_prose, docx_rows, mirror_prose, mirror_rows, mirror_text,
                       docx_post, mirror_post, docx_next, mirror_next)
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
