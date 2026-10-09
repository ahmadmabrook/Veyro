#!/usr/bin/env python3
"""
Generates `contracts/ui/screen-registry.json` — the canonical Screen ID
input to `tools/validate_screen_source_inputs.py` (`load_screen_registry`;
TSD §24.1 gate 5) — from the frozen canonical UX export
`veyro-product-experience-design/project/veyro-registry-data.js`, per
`IMPLEMENTATION.md` §10's import/validation contract and EIP Appendix F.

Scope (deliberately bounded — MOD-001 `R04-GATE5-CANONICAL-UX-INPUT-ADAPTER`,
2026-10-09): parse the frozen `R` export's rows directly, select the V1 UI
rows (`phase == 'V1'`, excluding the eight backend-only `SYS-*` rows —
`IMPLEMENTATION.md` §10 step 3: Backend-only/no-UI is a surface
classification, not a silent count waiver), and materialize the
duplicate-free Screen ID list in the exact
`{"version": 1, "screens": [...]}` shape `load_screen_registry` in
`validate_screen_source_inputs.py` already enforces.

What this does NOT do (separate, later, Implementation Complete
obligations — never invented here): resolve owning module/route/BFF or
read-model mappings (`IMPLEMENTATION.md` §10 steps 4-6); generate
`screen-contracts.yaml`; wire CI; or claim any review/scenario PASS.

Parsing is a narrow, explicit, line-exact extraction of the fixed 8-field
row-literal shape the source file's own header comment documents — never
a JS/eval interpreter, per Appendix F's own prohibition on re-deriving
registry data (`IMPLEMENTATION.md` §10 step 1). Any row, in the `R` array's
span, that does not match that exact shape is a fail-closed
`SourceFormatError` — never silently skipped or defaulted. The frozen
source file itself is never modified by this tool.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = (
    REPO_ROOT / "veyro-product-experience-design" / "project" / "veyro-registry-data.js"
)
DEFAULT_OUTPUT = REPO_ROOT / "contracts" / "ui" / "screen-registry.json"

_START_MARKER = "export const R = ["
_END_MARKER = "\n];"

# One row: `['id','module','name','phase','status','roles','ar','note'],`
# — the exact 8 single-quoted fields the source header comment documents.
# No backslash-escape handling: the frozen source contains none (fields use
# a literal middle-dot `·`, never an apostrophe), so an escape would be an
# unrecognised shape, not a silently-decoded one.
_ROW_RE = re.compile(
    r"\['([^'\\]*)','([^'\\]*)','([^'\\]*)','([^'\\]*)',"
    r"'([^'\\]*)','([^'\\]*)','([^'\\]*)','([^'\\]*)'\],?"
)

# Real canonical V1 UI Screen ID shapes (`IMPLEMENTATION.md` §10): the five
# two-segment non-Admin UI surfaces, or the three-segment Admin form.
_SCREEN_ID_RE = re.compile(r"(?:FD|POS|CCH|MBR|CON)-[0-9]{2}|ADM-[A-Z]{2,4}-[0-9]{2}")
_UI_SURFACE_PREFIXES = ("ADM-", "FD-", "POS-", "CCH-", "MBR-", "CON-")
_BACKEND_ONLY_PREFIX = "SYS-"

# The frozen source's own current, deterministic V1 UI shape — asserted,
# never silently assumed, so a future change to the hash-pinned baseline
# fails closed here instead of materializing a silently different count.
EXPECTED_TOTAL = 170
EXPECTED_BY_SURFACE = {"ADM": 85, "FD+POS": 16, "CCH": 19, "MBR": 35, "CON": 15}
EXPECTED_BACKEND_ONLY = 8


class SourceFormatError(ValueError):
    """The frozen source's row shape, or the resulting canonical projection,
    did not match the documented/expected contract."""


def _surface(screen_id: str) -> str:
    prefix = screen_id.split("-", 1)[0]
    return "FD+POS" if prefix in ("FD", "POS") else prefix


def parse_source_rows(text: str) -> list[list[str]]:
    """Extract the 8-field rows between the `R` array's start/end markers.
    Every non-blank, non-comment line in that span must match the exact
    row shape; any deviation is a fail-closed `SourceFormatError` naming
    the offending line, never a dropped or best-effort row."""
    start = text.find(_START_MARKER)
    if start == -1:
        raise SourceFormatError(f"source has no {_START_MARKER!r} marker")
    end = text.find(_END_MARKER, start)
    if end == -1:
        raise SourceFormatError(f"source has no closing {_END_MARKER!r} for the R array")
    body = text[start + len(_START_MARKER):end]
    rows: list[list[str]] = []
    for lineno, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        match = _ROW_RE.fullmatch(line)
        if not match:
            raise SourceFormatError(
                f"source line {lineno} does not match the 8-field row shape: {raw_line!r}"
            )
        rows.append(list(match.groups()))
    return rows


def select_v1_ui_ids(rows: list[list[str]]) -> list[str]:
    """V1-phase rows, excluding the backend-only `SYS-*` rows. Fail-closed
    on an unknown prefix or a duplicate ID — never silently dropped."""
    ids: list[str] = []
    seen: set[str] = set()
    backend_only = 0
    for row in rows:
        screen_id, phase = row[0], row[3]
        if phase != "V1":
            continue
        if screen_id.startswith(_BACKEND_ONLY_PREFIX):
            backend_only += 1
            continue
        if not screen_id.startswith(_UI_SURFACE_PREFIXES):
            raise SourceFormatError(
                f"{screen_id!r}: unknown prefix (neither a known UI surface nor {_BACKEND_ONLY_PREFIX!r})"
            )
        if not _SCREEN_ID_RE.fullmatch(screen_id):
            raise SourceFormatError(f"{screen_id!r}: does not match the canonical Screen ID shape")
        if screen_id in seen:
            raise SourceFormatError(f"{screen_id!r}: duplicate Screen ID in source")
        seen.add(screen_id)
        ids.append(screen_id)
    if backend_only != EXPECTED_BACKEND_ONLY:
        raise SourceFormatError(
            f"expected {EXPECTED_BACKEND_ONLY} backend-only {_BACKEND_ONLY_PREFIX!r} V1 row(s), "
            f"found {backend_only}"
        )
    return ids


def verify_projection(ids: list[str]) -> None:
    """Fail-closed proof of the known 170-count/five-surface split against
    the frozen source — a deviation (e.g. an unauthorized source edit this
    repository's baseline-integrity rule already forbids) is reported here
    rather than silently materialized."""
    if len(ids) != EXPECTED_TOTAL:
        raise SourceFormatError(f"expected {EXPECTED_TOTAL} canonical V1 UI Screen ID(s), found {len(ids)}")
    counts: dict[str, int] = {}
    for screen_id in ids:
        counts[_surface(screen_id)] = counts.get(_surface(screen_id), 0) + 1
    if counts != EXPECTED_BY_SURFACE:
        raise SourceFormatError(f"expected surface split {EXPECTED_BY_SURFACE}, found {counts}")


def build_registry(source_text: str) -> dict:
    rows = parse_source_rows(source_text)
    ids = select_v1_ui_ids(rows)
    verify_projection(ids)
    return {"version": 1, "screens": ids}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="frozen canonical UX export (veyro-registry-data.js)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="generated contracts/ui/screen-registry.json path")
    args = parser.parse_args(argv)

    if args.source.is_symlink() or not args.source.is_file():
        print(f"error: {args.source} not found or is a symlink", file=sys.stderr)
        return 2
    try:
        source_text = args.source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: {args.source}: unreadable ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 2

    try:
        registry = build_registry(source_text)
    except SourceFormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(registry['screens'])} Screen ID(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
