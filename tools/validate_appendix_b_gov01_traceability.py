#!/usr/bin/env python3
"""
EIP Appendix-B GOV-01-R01..R08 split/completion traceability check (MOD-001,
OWN-009/ADR-015; referenced by `knowledge/03-Modules/MOD-001/MOD-001.md`'s
"OWN-009 requirement ownership and certification dependencies" section,
which names this file as "a local candidate validator" at this path and
directs that its exact bytes and fail-closed behavior be qualified before a
MOD-001 Gatekeeper verdict).

The frozen EIP DOCX Appendix B prints MOD-001 as the sole "Completing
module" / "Execution slice module(s)" for all eight GOV-01 rows (the
pre-OWN-009 mapping). OWN-009/ADR-015 owner-approved a split: MOD-001 keeps
a mandatory-now foundation obligation per row, while the described product
behavior remains a later module's own certification dependency. That split
lives only as prose in MOD-001.md; nothing checked it was complete or that
a later edit could not silently drop a previously-recorded later-owner
module without comment. This script is a narrow, fail-closed traceability
check, modeled on `tools/validate_eip_appendix_f_binding.py`'s DOCX-vs-mirror
binding pattern (stdlib `zipfile` + `xml.etree`, no Pandoc):

  1. extracts the eight GOV-01-R01..R08 rows directly from the DOCX Appendix
     B table and checks the canonical identifier set (no missing/duplicate/
     extra row), the structural "original" fields every row must still carry
     (Domain/Priority/Phase/Completing module/Execution slice module(s)/
     Slice scope), and cross-checks the same rows as mirrored in
     `knowledge/00-System/EIP_MIRROR.md` cell-for-cell (catches mirror drift
     from the frozen DOCX);
  2. parses MOD-001.md's "OWN-009 requirement ownership and certification
     dependencies" table and requires all eight bare IDs (R01..R08) present
     exactly once with a non-trivial foundation cell and later-owner cell
     (an empty/placeholder half of the split fails closed), and requires
     each foundation cell to match its pinned owner-approved text exactly
     (a wholesale rewrite, e.g. to a deferral stub, fails closed even though
     the replacement text is non-trivial length); and
  3. compares each row's later-owner cell against a pinned baseline set of
     `MOD-###` identifiers captured from the currently owner-approved split
     text, failing closed if any of those identifiers has silently
     disappeared (a widened cell that still mentions every prior identifier
     is not a loss; a narrowed one that drops a prior identifier is), and
     separately requires each row's pinned owner-approved scope phrase(s)
     (not just the bare `MOD-###` token), including that row's pinned
     duty-bearing obligation sentence captured in EXPECTED_LATER_SEGMENTS, to
     remain a literal substring of the cell: deleting or negating one of
     those specific pinned clauses (e.g. a waiver that keeps every id but
     drops the pinned obligation sentence) fails closed for that clause.
     This is plain substring presence over a fixed, hand-picked baseline,
     not a semantic or NLP check and not a guarantee over every phrase in
     the cell — obligation wording that is not itself captured in
     EXPECTED_LATER_SEGMENTS can still be deleted or inverted undetected, so
     this baseline must be extended whenever MOD-001.md's owner-approved
     text legitimately changes.

This is a traceability/regression check, not a GOV-01 requirement PASS: it
does not execute, certify, or waive any of the eight requirements, and it
does not treat MOD-001.md's prose as proof that later modules have done
their own work. The frozen EIP DOCX is read-only and is never written here.

Exit: 0 PASS, 1 BLOCKED (findings), 2 ERROR (input unreadable / unparseable).
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent

DOCX_NAME = ("Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_"
             "APPROVED_GOVERNING_BASELINE.docx")
DEFAULT_DOCX = REPO_ROOT / DOCX_NAME
DEFAULT_MIRROR = REPO_ROOT / "knowledge/00-System/EIP_MIRROR.md"
DEFAULT_MOD001 = REPO_ROOT / "knowledge/03-Modules/MOD-001/MOD-001.md"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

HEADING_B = "Appendix B. Blueprint Requirement-to-Implementation-Module Traceability"
HEADER_CELLS_B = ["Requirement ID", "Domain", "Priority", "Phase", "Completing module",
                  "Requirement", "Execution slice module(s)", "Slice scope"]

GOV01_IDS = [f"GOV-01-R0{i}" for i in range(1, 9)]  # GOV-01-R01..GOV-01-R08
BARE_IDS = [f"R0{i}" for i in range(1, 9)]          # R01..R08 (MOD-001.md's own column)

# The DOCX's own pre-OWN-009 "original" fields: unchanged for every GOV-01
# row (ADR-015 explicitly keeps the EIP DOCX byte-unchanged). A mismatch here
# means either a tampered/misidentified DOCX copy or a real amendment that
# has not gone through the required formal EIP change process.
PINNED_STRUCTURAL = {
    "Domain": "GOV-01",
    "Priority": "Critical",
    "Phase": "Foundation",
    "Completing module": "MOD-001",
    "Execution slice module(s)": "MOD-001",
    "Slice scope": "Full requirement implemented and completed in the listed module.",
}

# Baseline foundation-cell text, captured verbatim (collapsed whitespace)
# from the currently owner-approved OWN-009 split in MOD-001.md. The
# mandatory-now foundation obligation is the entire point of OWN-009/ADR-015
# (MOD-001 keeps a real, present-tense foundation duty per row, not a later
# module's deferred one), so this cell is pinned to exact text rather than
# merely checked for non-triviality: a cell that no longer says this exact
# text (e.g. replaced wholesale with a deferral stub) fails closed. Any
# legitimate rewording of this prose must update this baseline alongside it,
# the same discipline PINNED_STRUCTURAL already requires for Appendix B.
PINNED_FOUNDATION_TEXT = {
    "R01": "Real repository test pyramid/fixtures and permanent-regression wiring; "
           "required layers execute in trusted CI where an actual foundation target "
           "exists; supported TestSprite integration and actual independent/manual-QA "
           "evidence remain required.",
    "R02": "Shared auth/tenant/permission/idempotency/financial test contracts and "
           "fail-closed CI hooks, with real foundation-level negatives and no "
           "fabricated product workflow PASS.",
    "R03": "Qualified scanner scope and runnable load/security/LOC/A11Y/offline/"
           "failure-test infrastructure; real CI-run control checks and "
           "CI-runner/environment smoke-load, not product-performance claims.",
    "R04": "Protected GitHub PR with **blocking trusted CI** for lint/type/test/build, "
           "six TSD §24.1 architecture gates, secret/dependency/SAST/schema/migration/"
           "capability/traceability checks, deliberate fail-closed violations, "
           "immutable provenance/signing and required independent assurance. The "
           "required check must be enforced on protected main, not only simulated "
           "locally.",
    "R05": "Automatic development/staging delivery from the governed merge, "
           "verification and safe rollback mechanism; no Production promotion.",
    "R06": "Backward-compatible migration tooling/policy, ordering and "
           "rollback/forward-fix checks with deliberate failing fixtures and CI "
           "enforcement; no claim of an absent product database migration.",
    "R07": "Mobile build/test integration, compatibility/version policy and release "
           "controls; no automatic store publication.",
    "R08": "Release-train/changelog/maintenance and beta/GA/deprecation policies "
           "implemented in the governed PR/CI/delivery chain.",
}

# Baseline later-owner `MOD-###` identifiers, captured from the currently
# owner-approved OWN-009 split text in MOD-001.md (section "OWN-009
# requirement ownership and certification dependencies"). This is a snapshot
# of what is already approved, not a correctness oracle over true ownership;
# it exists solely to catch a *silent* future loss of one of these mapped
# dependencies. Additions are fine; removals fail closed. R01/R04 describe
# generic "every/each later module" obligations rather than naming specific
# owners, so their pinned sets are the only concrete `MOD-###` tokens their
# current cells happen to contain.
EXPECTED_LATER_MOD_IDS = {
    "R01": frozenset({"MOD-002", "MOD-074"}),
    "R02": frozenset({"MOD-004", "MOD-007", "MOD-008", "MOD-014", "MOD-016", "MOD-017",
                       "MOD-018", "MOD-020", "MOD-022", "MOD-030", "MOD-031", "MOD-034",
                       "MOD-035", "MOD-037", "MOD-038", "MOD-041"}),
    "R03": frozenset({"MOD-003", "MOD-006", "MOD-009", "MOD-011", "MOD-020", "MOD-022",
                       "MOD-037", "MOD-038", "MOD-073"}),
    "R04": frozenset({"MOD-001"}),
    "R05": frozenset({"MOD-005", "MOD-033", "MOD-049", "MOD-061", "MOD-068", "MOD-074"}),
    "R06": frozenset({"MOD-030", "MOD-031"}),
    "R07": frozenset({"MOD-006", "MOD-020", "MOD-023", "MOD-025", "MOD-028", "MOD-037",
                       "MOD-039", "MOD-044", "MOD-048"}),
    "R08": frozenset({"MOD-031", "MOD-033", "MOD-049", "MOD-061", "MOD-068", "MOD-074"}),
}

# Baseline later-owner *scope phrases*, captured verbatim (collapsed
# whitespace, trailing punctuation dropped so an edit appended just after a
# phrase does not break containment) from the currently owner-approved cell
# text. Most entries are one per pinned `MOD-###` dependency above.
# EXPECTED_LATER_MOD_IDS alone only checks that a bare `MOD-###` token is
# present anywhere in the cell, so a rewrite that keeps every token but
# strips the surrounding obligation language (e.g. replacing the whole cell
# with a waiver that lists the same ids as "owing nothing") is not caught by
# the token check. Requiring each full scope phrase to remain a literal
# substring closes that gap: a pure addition (the widened-cell case) leaves
# every existing phrase intact, while a rewrite that drops the phrase
# wording fails closed even if it keeps the bare id.
#
# BUG-067 remediation: each row also pins one additional segment that is the
# row's approved duty-bearing obligation sentence — the clause stating what
# a later module must actually prove/do — even where that sentence carries
# no `MOD-###` token of its own (e.g. R01's "No empty layer or synthetic
# fixture proves that behavior", R07's "Store publication and Production
# promotion remain owner-reserved"). Without this, a waiver that kept every
# pinned id/phrase above but deleted or inverted the obligation sentence
# passed undetected (the BUG-067 P1-2 false-green class). This still only
# protects the specific sentences enumerated here; it is not a semantic or
# NLP check and not exhaustive over every clause in a cell — plain substring
# presence over a fixed, hand-picked baseline.
EXPECTED_LATER_SEGMENTS = {
    "R01": (
        "Every later module that introduces a service, UI or device flow "
        "(MOD-002–074 per its EIP §21 card/Appendix B) owns the applicable "
        "unit/component/integration/contract/E2E/mobile/exploratory executions "
        "for **its** behavior",
        "No empty layer or synthetic fixture proves that behavior",
    ),
    "R02": (
        "Tenant/RLS: MOD-004 (PLT-01)",
        "identity: MOD-007 (IAM-01)",
        "authorization/audit: MOD-008 (IAM-03)",
        "member record/catalog: MOD-014/016 (PPL-01/COM-02)",
        "membership contracts: MOD-017 and completion MOD-034 (COM-01)",
        "booking: MOD-020 and completion MOD-037 (OPS-02)",
        "payment/ledger: MOD-018 and completion MOD-035 (COM-04)",
        "POS: MOD-041 (COM-05)",
        "access: MOD-022 and completion MOD-038 (OPS-03)",
        "data migration: MOD-030/031 (LIF-02/LIF-01)",
        "Each named module must prove its real authorization, isolation, "
        "financial/concurrency/idempotency and negative paths before its own "
        "certificate",
    ),
    "R03": (
        "Shared localization/accessibility: MOD-003/006 (WHT-02)",
        "security/privacy behavior: MOD-009 and MOD-073 (SEC-01)",
        "observability/performance/reliability: MOD-011 and MOD-073 (REL-02/REL-01)",
        "offline booking/access: MOD-020/022 and completion MOD-037/038 (OPS-02/03)",
        "Every introducing module also owes its EIP §21 security/load/manual-QA "
        "scope on actual behavior",
    ),
    "R04": (
        "No product input is fabricated to give MOD-001 a green gate",
        "Each later module supplies genuine contracts/schema/permissions/"
        "screens/events and proves its applicable gates on its actual changes; "
        "UI owners are the exact source-derived modules/Screen IDs in EIP "
        "Appendix F, not invented owner placeholders",
    ),
    "R05": (
        "Feature-flag/remote-config behavior belongs to MOD-005 (PLT-02)",
        "Pilot/GA/V1.5/V2/enterprise program gates MOD-033/049/061/068/074 "
        "aggregate release evidence when reached",
        "each later deployable module proves its own rollout/rollback and "
        "environment behavior",
    ),
    "R06": (
        "Dedicated imports/migration are MOD-030 (LIF-02) and MOD-031 (LIF-01)",
        "Every module introducing a schema or data migration owns an actual "
        "expand–migrate/backfill–switch–contract and rollback/forward-fix "
        "proof before its certificate",
    ),
    "R07": (
        "MOD-006 (WHT-02/KMP + Compose Multiplatform production qualification) "
        "owns shared mobile-platform qualification",
        "pilot examples MOD-020/023–025/028; GA MOD-037/039/044–048",
        "Store publication and Production promotion remain owner-reserved",
    ),
    "R08": (
        "The first actual pilot go-live/communication is MOD-031 (LIF-01/GOV-04), "
        "followed by program gates MOD-033/049/061/068/074",
        "each release of changed product behavior owes its own changelog, "
        "deprecation impact, verification and customer communication before "
        "promotion",
    ),
}

OWN009_SECTION_HEADING = ("### OWN-009 requirement ownership and certification "
                           "dependencies (mapped; no PASS)")
OWN009_HEADER = ["ID", "MOD-001 mandatory-now foundation and exit dependency",
                 "Product-behavior owner and later certificate dependency"]

_MOD_ID_RE = re.compile(r"MOD-\d{3}(?:[/–-]\d{3})*")
_NEXT_APPX_HEADING = re.compile(r"^# Appendix [A-Z]\. ")

MIN_CELL_LEN = 20  # below this, treat a foundation/later-owner cell as effectively empty


class Error(Exception):
    pass


def mod_ids_in(text: str) -> set[str]:
    out: set[str] = set()
    for m in _MOD_ID_RE.finditer(text):
        for part in re.split(r"[/–-]", m.group(0)):
            if part.isdigit():
                out.add(f"MOD-{part}")
    return out


def collapse(text: str) -> str:
    return " ".join(text.split())


def _ptext(p: ET.Element) -> str:
    out = []
    for e in p.iter():
        if e.tag == W + "t":
            out.append(e.text or "")
        elif e.tag in (W + "tab", W + "br"):
            out.append(" ")
    return "".join(out)


def _is_heading1(k: ET.Element) -> bool:
    if k.tag != W + "p":
        return False
    style = k.find(f"{W}pPr/{W}pStyle")
    return style is not None and style.get(W + "val") == "Heading1"


# --- DOCX extraction -------------------------------------------------------

def extract_docx_rows(docx: Path) -> list[list[str]]:
    """Header + data rows (list of list[str]) of the table immediately
    following the Appendix B Heading1 paragraph in the DOCX body."""
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
            if _is_heading1(k) and collapse(_ptext(k)) == HEADING_B]
    if len(hits) != 1:
        raise Error(f"expected exactly one Heading1 {HEADING_B!r} in DOCX, found {len(hits)}")
    table = None
    for k in kids[hits[0] + 1:]:
        if k.tag == W + "tbl":
            table = k
            break
        if _is_heading1(k):
            break
    if table is None:
        raise Error(f"DOCX {HEADING_B!r} region has no table before the next heading")
    if table.find(f".//{W}tbl") is not None:
        raise Error(f"DOCX {HEADING_B!r} table contains a nested table")
    rows = [[collapse(" ".join(_ptext(p) for p in tc.findall(W + "p")))
             for tc in tr.findall(W + "tc")] for tr in table.findall(W + "tr")]
    return rows


# --- mirror extraction ------------------------------------------------------

_COL_TOKENS = ("**Requirement", "**Domain**", "**Priority**", "**Phase**",
               "**Completing", "**Requirement**", "**Execution", "**Slice scope**")
NCOLS = len(_COL_TOKENS)


def extract_mirror_rows(mirror_text: str) -> list[list[str]]:
    """Header + data rows of the Appendix B grid table in the mirror, parsed
    the same way `validate_eip_appendix_f_binding.py` parses Appendix F's."""
    lines = mirror_text.splitlines()
    starts = [i for i, l in enumerate(lines) if l.strip() == "# " + HEADING_B]
    if len(starts) != 1:
        raise Error(f"expected exactly one mirror heading {HEADING_B!r}, found {len(starts)}")
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if _NEXT_APPX_HEADING.match(lines[i])),
                None)
    if end is None:
        raise Error("mirror Appendix B is not terminated by a following Appendix heading")
    try:
        head = next(i for i in range(start, end)
                    if "**Domain**" in lines[i] and "**Priority**" in lines[i])
    except StopIteration:
        raise Error("mirror Appendix B table header not found") from None
    open_rule = head - 1
    while open_rule > start and not re.fullmatch(r"\s*-{3,}\s*", lines[open_rule]):
        open_rule -= 1
    if open_rule <= start:
        raise Error("mirror Appendix B table opening rule not found")

    header = lines[head]
    try:
        cols = [header.index(t) for t in _COL_TOKENS]
    except ValueError:
        raise Error("mirror Appendix B table header columns not found") from None
    if cols != sorted(cols):
        raise Error("mirror Appendix B table header columns out of order")

    def cell(line: str, n: int) -> str:
        return line[cols[n]:cols[n + 1] if n + 1 < len(cols) else None]

    rows: list[list[str]] = []
    cur: list[str] | None = None
    in_header = True
    dashes = 1  # opening rule already passed
    close = None
    for idx in range(head, end):
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
        if line[:cols[0]].strip():
            raise Error("mirror Appendix B table row has text left of the first column")
        if in_header:
            if cur is None:
                cur = [""] * NCOLS
        elif cell(line, 0).strip():
            if cur is not None:
                rows.append(cur)
            cur = [""] * NCOLS
        elif cur is None:
            raise Error("mirror Appendix B row continuation before any row")
        for n in range(NCOLS):
            cur[n] = f"{cur[n]} {cell(line, n)}"
    if close is None:
        raise Error("mirror Appendix B module table not terminated by a closing rule "
                     "before the next Appendix heading")
    if cur is not None:
        rows.append(cur)
    rows = [[collapse(c) for c in r] for r in rows]
    if rows:  # header cells are bold in the mirror's Pandoc rendering
        rows[0] = [re.fullmatch(r"\*\*(.*)\*\*", c).group(1)
                   if re.fullmatch(r"\*\*(.*)\*\*", c) else c for c in rows[0]]
    return rows


# --- MOD-001.md OWN-009 table parsing --------------------------------------

def parse_own009_table(mod001_text: str) -> dict[str, tuple[str, str]]:
    """{bare ID ('R01'..): (foundation cell, later-owner cell)} from MOD-001.md's
    OWN-009 section. Raises Error if the section or its table header is absent
    (a structurally missing mapping, not a reportable row-level finding)."""
    lines = mod001_text.splitlines()
    try:
        sec = next(i for i, l in enumerate(lines) if l.strip() == OWN009_SECTION_HEADING)
    except StopIteration:
        raise Error(f"MOD-001.md is missing the {OWN009_SECTION_HEADING!r} section") from None
    header_idx = next((i for i in range(sec + 1, len(lines))
                        if lines[i].strip().startswith("| ID |")), None)
    if header_idx is None:
        raise Error("MOD-001.md OWN-009 section has no '| ID | ...' table header")
    header_cells = [c.strip() for c in lines[header_idx].strip().strip("|").split("|")]
    if header_cells != OWN009_HEADER:
        raise Error(f"MOD-001.md OWN-009 table header cells unexpected: {header_cells!r}")
    sep_idx = header_idx + 1
    if sep_idx >= len(lines) or not re.fullmatch(r"\|[\s:-]+\|[\s:-]+\|[\s:-]+\|",
                                                  lines[sep_idx].strip()):
        raise Error("MOD-001.md OWN-009 table has no separator row after its header")
    out: dict[str, tuple[str, str]] = {}
    i = sep_idx + 1
    while i < len(lines) and lines[i].strip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if len(cells) != 3:
            raise Error(f"MOD-001.md OWN-009 table row has {len(cells)} cells, expected 3: "
                        f"{lines[i]!r}")
        id_ = cells[0]
        if id_ in out:
            raise Error(f"MOD-001.md OWN-009 table: duplicate row for {id_!r}")
        out[id_] = (cells[1], cells[2])
        i += 1
    if not out:
        raise Error("MOD-001.md OWN-009 table has a header but no data rows")
    return out


# --- comparisons -------------------------------------------------------------

def _check_gov01_id_set(label: str, ids: list[str], findings: list[dict]) -> None:
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        findings.append({"code": "APPENDIXB_DUPLICATE_ROW",
                          "detail": f"{label}: {dup} appears {ids.count(dup)} times"})
    missing = [i for i in GOV01_IDS if i not in ids]
    if missing:
        findings.append({"code": "APPENDIXB_MISSING_ROW",
                          "detail": f"{label}: missing {missing}"})
    extra = sorted({i for i in ids if i not in GOV01_IDS})
    if extra:
        findings.append({"code": "APPENDIXB_EXTRA_ROW",
                          "detail": f"{label}: unexpected GOV-01 row id(s) {extra}"})


def compare_docx_and_mirror(docx_rows: list[list[str]],
                             mirror_rows: list[list[str]]) -> list[dict]:
    f: list[dict] = []

    def add(code: str, detail: str) -> None:
        f.append({"code": code, "detail": detail})

    if not docx_rows or docx_rows[0] != HEADER_CELLS_B:
        add("APPENDIXB_DOCX_HEADER_UNEXPECTED", f"DOCX header cells {docx_rows[:1]!r}")
    if not mirror_rows or mirror_rows[0] != HEADER_CELLS_B:
        add("APPENDIXB_MIRROR_HEADER_MISMATCH",
            f"mirror header cells {mirror_rows[:1]!r} != {HEADER_CELLS_B!r}")

    docx_gov = [r for r in docx_rows[1:] if len(r) > 1 and r[1] == "GOV-01"]
    mirror_gov = [r for r in mirror_rows[1:] if len(r) > 1 and r[1] == "GOV-01"]

    _check_gov01_id_set("DOCX", [r[0] for r in docx_gov], f)
    _check_gov01_id_set("mirror", [r[0] for r in mirror_gov], f)

    idx_map = {name: HEADER_CELLS_B.index(name) for name in PINNED_STRUCTURAL}
    for r in docx_gov:
        if len(r) != len(HEADER_CELLS_B):
            add("APPENDIXB_DOCX_ROW_SHAPE", f"{r[0] if r else '?'}: {len(r)} DOCX cells")
            continue
        for name, expected in PINNED_STRUCTURAL.items():
            if r[idx_map[name]] != expected:
                add("APPENDIXB_WRONG_COMPLETING_OR_SLICE_DATA",
                    f"{r[0]} column {name!r}: DOCX {r[idx_map[name]]!r} != expected {expected!r}")

    d_ids, m_ids = [r[0] for r in docx_gov], [r[0] for r in mirror_gov]
    for mod in d_ids:
        if mod not in m_ids:
            add("APPENDIXB_MIRROR_MISSING_ROW", f"mirror lacks DOCX row {mod}")
    for mod in m_ids:
        if mod not in d_ids:
            add("APPENDIXB_MIRROR_EXTRA_ROW", f"mirror has row {mod} absent from DOCX")
    if sorted(d_ids) == sorted(m_ids) and d_ids != m_ids:
        add("APPENDIXB_ROW_ORDER", "mirror GOV-01 row order differs from DOCX")

    m_by = {r[0]: r for r in mirror_gov}
    for d in docx_gov:
        m = m_by.get(d[0])
        if m is None or len(d) != len(HEADER_CELLS_B) or len(m) != len(HEADER_CELLS_B):
            continue
        for n, name in enumerate(HEADER_CELLS_B):
            if d[n] != m[n]:
                add("APPENDIXB_CELL_MISMATCH",
                    f"{d[0]} column {name!r}: DOCX {d[n]!r} != mirror {m[n]!r}")
    return f


def check_own009_mapping(own009: dict[str, tuple[str, str]]) -> list[dict]:
    f: list[dict] = []

    def add(code: str, detail: str) -> None:
        f.append({"code": code, "detail": detail})

    missing = [i for i in BARE_IDS if i not in own009]
    if missing:
        add("OWN009_MISSING_ROW", f"OWN-009 table missing row(s) {missing}")
    extra = sorted(i for i in own009 if i not in BARE_IDS)
    if extra:
        add("OWN009_EXTRA_ROW", f"OWN-009 table has unexpected row id(s) {extra}")

    for id_, (foundation, later) in own009.items():
        if id_ not in BARE_IDS:
            continue
        if len(foundation) < MIN_CELL_LEN:
            add("OWN009_FOUNDATION_CELL_MISSING",
                f"{id_}: foundation cell is empty/placeholder ({foundation!r})")
        if len(later) < MIN_CELL_LEN:
            add("OWN009_LATER_OWNER_CELL_MISSING",
                f"{id_}: later-owner cell is empty/placeholder ({later!r})")

        pinned_foundation = PINNED_FOUNDATION_TEXT.get(id_)
        if pinned_foundation is not None and collapse(foundation) != pinned_foundation:
            add("OWN009_FOUNDATION_CELL_CHANGED",
                f"{id_}: foundation cell no longer matches the owner-approved "
                f"mandatory-now text, got {foundation!r}")

        expected_ids = EXPECTED_LATER_MOD_IDS.get(id_, frozenset())
        current_ids = mod_ids_in(later)
        lost = sorted(expected_ids - current_ids)
        if lost:
            add("OWN009_LATER_DEPENDENCY_LOST",
                f"{id_}: later-owner cell silently lost previously-mapped {lost}")

        collapsed_later = collapse(later)
        missing_segments = [seg for seg in EXPECTED_LATER_SEGMENTS.get(id_, ())
                             if seg not in collapsed_later]
        if missing_segments:
            add("OWN009_LATER_OWNER_SEGMENT_LOST",
                f"{id_}: later-owner cell no longer contains the owner-approved "
                f"scope phrase(s) {missing_segments!r} (bare id tokens alone are "
                f"not sufficient; the obligation wording must remain intact), "
                f"got {later!r}")
    return f


def cross_check_id_sets(docx_rows: list[list[str]], own009: dict[str, tuple[str, str]]
                         ) -> list[dict]:
    docx_gov_ids = {r[0][len("GOV-01-"):] for r in docx_rows[1:]
                    if len(r) > 1 and r[1] == "GOV-01" and r[0].startswith("GOV-01-")}
    own009_ids = set(own009)
    if docx_gov_ids != own009_ids and docx_gov_ids and own009_ids:
        return [{"code": "APPENDIXB_OWN009_ID_SET_MISMATCH",
                 "detail": f"DOCX GOV-01 ids {sorted(docx_gov_ids)} != "
                           f"OWN-009 table ids {sorted(own009_ids)}"}]
    return []


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--docx", type=Path, default=DEFAULT_DOCX)
    p.add_argument("--mirror", type=Path, default=DEFAULT_MIRROR)
    p.add_argument("--mod001", type=Path, default=DEFAULT_MOD001)
    args = p.parse_args(argv)
    try:
        docx_rows = extract_docx_rows(args.docx)
        mirror_text = args.mirror.read_text(encoding="utf-8")
        mirror_rows = extract_mirror_rows(mirror_text)
        mod001_text = args.mod001.read_text(encoding="utf-8")
        own009 = parse_own009_table(mod001_text)
    except (Error, OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    findings = compare_docx_and_mirror(docx_rows, mirror_rows)
    findings += check_own009_mapping(own009)
    findings += cross_check_id_sets(docx_rows, own009)

    print(f"EIP Appendix B GOV-01 traceability: docx GOV-01 rows "
          f"{len([r for r in docx_rows[1:] if len(r) > 1 and r[1] == 'GOV-01'])}; "
          f"mirror GOV-01 rows {len([r for r in mirror_rows[1:] if len(r) > 1 and r[1] == 'GOV-01'])}; "
          f"OWN-009 rows {len(own009)}")
    if findings:
        print(f"BLOCKED: {len(findings)} finding(s):")
        for x in findings:
            print(f"  - {x['code']}: {x['detail']}")
        return 1
    print("PASS - GOV-01-R01..R08 Appendix B rows match the frozen EIP DOCX and the "
          "mirror, and the OWN-009 foundation/later-owner split in MOD-001.md is "
          "complete with no detected silent loss of a mapped later dependency "
          "(traceability check only; not a GOV-01 requirement PASS or module certification)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
