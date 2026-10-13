#!/usr/bin/env python3
"""
Generates `contracts/ui/screen-contracts.yaml` (TSD §24.1 gate 5 manifest) and
runs the gate-5 identity check against it. MOD-001 / GOV-01-R04, operation
M1-C-03 step R2b; governing decision ADR-014 D2 (+ D1 for the four-state
report) and EIP Appendix F (`EIP_MIRROR.md` "Canonical Screen-to-Module
Mapping" and its module table).

Subcommands:

    generate   write the manifest (deterministic, byte-stable)
    check      identity check; exit 0 PASS / 1 FAIL / 2 ERROR

Inputs (all repository files, never hand-keyed):

* `veyro-product-experience-design/project/veyro-registry-data.js` — the
  canonical registry. Rows are parsed with `generate_screen_registry`'s
  line-exact `parse_source_rows` (no JS evaluation). A canonical V1 UI row is
  a row `resolve()` marks `isV1` (phase V1 and status not deferred) whose
  surface is one of the five UI surfaces; the eight `SYS-*` rows are the
  `Backend / no UI` exclusion (ADR-014 D2.2).
* `contracts/ui/screen-registry.json` — the committed ID list; must equal the
  ID set derived from the source (cross-check, ERROR on generate / FAIL on
  check).
* `knowledge/00-System/EIP_MIRROR.md` — the Appendix F module table, parsed
  from its fixed-width columns (module, wave, TSD domain(s), surface
  ownership). Its canonical screen mapping rule is the *only* ownership
  authority: a module owns a screen iff the screen's `owner_domain` is in the
  module's TSD domain list AND the screen's surface is one of the module's
  surfaces.

Ownership honesty. The rule is keyed on `owner_domain`, a TSD domain code.
The registry source stores no such field: its rows are
`[id, module, name, phase, status, roles, ar, note]`, `module` is a UX word
("Members", "Payments"), and the header says surface/domain "are derived from
the id prefix — never stored". No document in the repository maps UX words or
ID prefixes to TSD domain codes. This tool therefore never infers one: a row
whose source carries no TSD domain code gets `owner_domain`/`owning_module`/
`wave` = null and `owner_resolution.status` = `UNRESOLVED`, and the identity
check FAILs listing every such Screen ID. A tool that "resolved" these by
guessing would be exactly the hand assignment ADR-014 D2.4 forbids.

Manifest file format: a JSON document (JSON is a strict subset of YAML 1.2, so
the `.yaml` file parses with any YAML reader and with stdlib `json` here — the
gate suite is stdlib-only). Rows keep source (registry) order.

Binding fields (ADR-014 D2.5) are the string `UNBOUND` with
`binding_status: UNBOUND`; never empty or invented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))
from generate_screen_registry import (  # same-directory tracked tool
    SourceFormatError,
    parse_source_rows,
)

SOURCE_REL = "veyro-product-experience-design/project/veyro-registry-data.js"
REGISTRY_REL = "contracts/ui/screen-registry.json"
EIP_REL = "knowledge/00-System/EIP_MIRROR.md"
MANIFEST_REL = "contracts/ui/screen-contracts.yaml"
DEFAULT_SOURCE = REPO_ROOT / SOURCE_REL
DEFAULT_REGISTRY = REPO_ROOT / REGISTRY_REL
DEFAULT_EIP = REPO_ROOT / EIP_REL
DEFAULT_MANIFEST = REPO_ROOT / MANIFEST_REL

PASS, FAIL, ERROR, NOT_APPLICABLE = "PASS", "FAIL", "ERROR", "NOT_APPLICABLE"
EXIT_CODE = {PASS: 0, FAIL: 1, ERROR: 2}  # NOT_APPLICABLE is never valid for gate 5 (ADR-014 D2.4)

# ADR-014 D2.3: explicit, checked registry-label -> EIP-vocabulary mapping.
SURFACE_LABEL_MAP = {
    "Veyro Admin": "Admin",
    "Front Desk & POS": "Front Desk & POS",
    "Veyro Coach": "Coach",
    "Veyro Member": "Member",
    "Internal Console": "Internal SaaS Console",
}
BACKEND_LABEL = "Backend / no UI"
BACKEND_ID_PREFIX = "SYS-"
EXPECTED_BACKEND_ONLY = 8
EXPECTED_TOTAL = 170
EXPECTED_BY_SURFACE = {
    "Admin": 85,
    "Front Desk & POS": 16,
    "Coach": 19,
    "Member": 35,
    "Internal SaaS Console": 15,
}
DEFERRED_STATUSES = ("V1.5", "V2", "ENT", "FUTURE")  # `resolve()`'s isDefer set

# EIP Appendix F surface vocabulary (EIP_MIRROR.md:17997). Module-table surface
# names map to the five V1 count-model surfaces; the six portals are post-V1
# ("no V1 Screen IDs expected") and therefore own no V1 screen.
MODULE_SURFACE_MAP: dict[str, str | None] = {
    "Admin Web": "Admin",
    "Front Desk": "Front Desk & POS",
    "POS": "Front Desk & POS",
    "Kiosk": "Front Desk & POS",
    "Staff Kiosk": "Front Desk & POS",
    "Coach App": "Coach",
    "Member App": "Member",
    "Member Web": "Member",
    "Internal SaaS Console": "Internal SaaS Console",
    "Developer Portal": None,
    "Corporate Portal": None,
    "Tenant Billing Portal": None,
    "Learning Portal": None,
    "Partner Portal": None,
    "Franchise Portal": None,
}

BINDING_FIELDS = (
    "route", "primary_read_model", "queries", "commands", "realtime_channels",
    "permissions", "assurance", "masking_variant", "offline_mode",
    "expected_error_codes", "empty_state", "loading_state", "error_state",
)
UNBOUND = "UNBOUND"
ROW_KEYS = (
    "screen_id", "surface", "registry_module", "owning_module", "wave",
    "owner_domain", "owner_resolution", "binding_status",
) + BINDING_FIELDS
OWNER_STATUSES = ("RESOLVED", "UNRESOLVED")
UNRESOLVED_NO_DOMAIN = "NO_TSD_OWNER_DOMAIN_IN_SOURCE_METADATA"

_DOMAIN_RE = re.compile(r"[A-Z]{2,4}-[0-9]{2}")
_MODULE_ID_RE = re.compile(r"MOD-[0-9]{3}")


class GenerationError(ValueError):
    """An input could not be read/parsed or violated an input contract (ERROR)."""


class ManifestError(ValueError):
    """The manifest under check is unparseable / outside its shape (ERROR)."""


# --- source (registry) ------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalRow:
    screen_id: str
    surface: str  # EIP vocabulary
    registry_module: str  # source `module` field, verbatim (traceability only)
    owner_domain_candidates: tuple[str, ...]  # TSD domain codes present in source fields


def source_surface_label(screen_id: str) -> str:
    """Python mirror of the source file's own `SURFACE_OF(id)`."""
    prefix = screen_id.split("-")[0]
    return {
        "ADM": "Veyro Admin", "FD": "Front Desk & POS", "POS": "Front Desk & POS",
        "CCH": "Veyro Coach", "MBR": "Veyro Member", "CON": "Internal Console",
    }.get(prefix, BACKEND_LABEL)


def map_surface_label(label: str) -> str:
    try:
        return SURFACE_LABEL_MAP[label]
    except KeyError:
        raise GenerationError(f"unknown surface label {label!r}: outside the checked mapping") from None


def build_canonical_rows(
    source_text: str,
    label_of: Callable[[str], str] = source_surface_label,
) -> list[CanonicalRow]:
    """isV1 rows minus the `Backend / no UI` rows, in source order. No count
    enforcement here (see `verify_counts`) so `check` can report a count
    deviation as FAIL rather than ERROR."""
    try:
        rows = parse_source_rows(source_text)
    except SourceFormatError as exc:
        raise GenerationError(f"registry source: {exc}") from exc
    out: list[CanonicalRow] = []
    seen: set[str] = set()
    backend = 0
    for fields in rows:
        screen_id, status = fields[0], fields[4]
        if not (fields[3] == "V1" and status not in DEFERRED_STATUSES):
            continue
        label = label_of(screen_id)
        if label == BACKEND_LABEL:
            if not screen_id.startswith(BACKEND_ID_PREFIX):
                raise GenerationError(
                    f"{screen_id!r}: backend/no-UI surface label without the {BACKEND_ID_PREFIX!r} prefix")
            backend += 1
            continue
        surface = map_surface_label(label)
        if screen_id in seen:
            raise GenerationError(f"{screen_id!r}: duplicate Screen ID in source")
        seen.add(screen_id)
        domains = tuple(f for f in fields[1:] if _DOMAIN_RE.fullmatch(f))
        out.append(CanonicalRow(screen_id, surface, fields[1], domains))
    if backend != EXPECTED_BACKEND_ONLY:
        raise GenerationError(
            f"expected {EXPECTED_BACKEND_ONLY} backend-only V1 row(s), found {backend}")
    return out


def surface_counts(surfaces: list[str]) -> dict[str, int]:
    return {s: surfaces.count(s) for s in EXPECTED_BY_SURFACE}


def verify_counts(rows: list[CanonicalRow]) -> None:
    if len(rows) != EXPECTED_TOTAL:
        raise GenerationError(f"expected {EXPECTED_TOTAL} canonical V1 UI rows, found {len(rows)}")
    counts = surface_counts([r.surface for r in rows])
    if counts != EXPECTED_BY_SURFACE:
        raise GenerationError(f"expected surface split {EXPECTED_BY_SURFACE}, found {counts}")


def load_registry_ids(path: Path) -> list[str]:
    if path.is_symlink() or not path.is_file():
        raise GenerationError(f"{path} not found or is a symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"{path}: unreadable ({type(exc).__name__}: {exc})") from exc
    if (not isinstance(raw, dict) or set(raw) != {"version", "screens"}
            or raw["version"] != 1 or not isinstance(raw["screens"], list)
            or not all(isinstance(s, str) for s in raw["screens"])):
        raise GenerationError(f"{path} must be exactly {{'version': 1, 'screens': [...]}}")
    return raw["screens"]


# --- EIP Appendix F module table ---------------------------------------------------


@dataclass(frozen=True)
class ModuleEntry:
    module: str
    wave: str
    domains: tuple[str, ...]
    surfaces: tuple[str, ...]  # EIP vocabulary; post-V1 portals and non-UI dropped


def parse_module_table(eip_text: str) -> dict[str, ModuleEntry]:
    """Parse the fixed-width Appendix F module table by header column offsets.
    Unknown surface names are ERROR (never silently dropped)."""
    lines = eip_text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines)
                     if l.startswith("# Appendix F. Canonical Screen-to-Module Mapping"))
        head = next(i for i in range(start, len(lines))
                    if "**Module**" in lines[i] and "**Wave**" in lines[i])
    except StopIteration:
        raise GenerationError("EIP Appendix F module table header not found") from None
    header = lines[head]
    try:
        cols = [header.index(tok) for tok in
                ("**Module**", "**Wave**", "**TSD", "**UI /", "**Canonical", "**Ready-state")]
    except ValueError:
        raise GenerationError("EIP Appendix F module table header columns not found") from None
    if cols != sorted(cols):
        raise GenerationError("EIP Appendix F module table header columns out of order")

    def cell(line: str, n: int) -> str:
        return line[cols[n]:cols[n + 1] if n + 1 < len(cols) else None].strip()

    dashes = 0
    raw_rows: list[list[str]] = []
    for line in lines[head + 1:]:
        if re.fullmatch(r"\s*(?:-{3,}\s*)+", line):
            dashes += 1
            if dashes == 2:
                break
            continue
        if not line.strip():
            continue
        first = cell(line, 0)
        if first:
            if not _MODULE_ID_RE.fullmatch(first):
                raise GenerationError(f"EIP Appendix F table: unexpected module cell {first!r}")
            raw_rows.append([first, "", "", ""])
        elif not raw_rows:
            continue
        cur = raw_rows[-1]
        for n in (1, 2, 3):
            text = cell(line, n)
            if text:
                cur[n] = f"{cur[n]} {text}".strip()
    if dashes != 2 or not raw_rows:
        raise GenerationError("EIP Appendix F module table not terminated / empty")

    table: dict[str, ModuleEntry] = {}
    for module, wave, domain_cell, surface_cell in raw_rows:
        if module in table:
            raise GenerationError(f"EIP Appendix F table: duplicate module {module}")
        domains = tuple(_DOMAIN_RE.findall(domain_cell))
        surfaces: list[str] = []
        if not surface_cell.startswith("Non-UI"):
            for name in (s.strip() for s in surface_cell.split(",")):
                if name not in MODULE_SURFACE_MAP:
                    raise GenerationError(f"EIP Appendix F table: {module} unknown surface name {name!r}")
                mapped = MODULE_SURFACE_MAP[name]
                if mapped and mapped not in surfaces:
                    surfaces.append(mapped)
        table[module] = ModuleEntry(module, wave, domains, tuple(surfaces))
    return table


def module_table_digest(modules: dict[str, ModuleEntry]) -> str:
    canon = [[m.module, m.wave, list(m.domains), list(m.surfaces)] for m in modules.values()]
    return hashlib.sha256(json.dumps(canon, separators=(",", ":")).encode()).hexdigest()


def resolve_owner(surface: str, owner_domain: str | None,
                  modules: dict[str, ModuleEntry]) -> list[str]:
    """Appendix F canonical screen mapping rule, applied literally: modules
    whose TSD domains contain `owner_domain` and whose surfaces contain the
    screen's surface. No `owner_domain` -> nothing can match."""
    if owner_domain is None:
        return []
    return [m.module for m in modules.values()
            if owner_domain in m.domains and surface in m.surfaces]


def source_owner_domain(row: CanonicalRow, modules: dict[str, ModuleEntry]) -> str | None:
    """A TSD domain code carried by the source row itself, if exactly one
    known code is present. Real registry rows carry none (see module doc)."""
    known = {d for m in modules.values() for d in m.domains}
    found = sorted({d for d in row.owner_domain_candidates if d in known})
    return found[0] if len(found) == 1 else None


# --- manifest render ---------------------------------------------------------------


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_manifest(rows: list[CanonicalRow], modules: dict[str, ModuleEntry],
                   source_text: str, registry_ids: list[str]) -> dict[str, Any]:
    screens: list[dict[str, Any]] = []
    for r in rows:
        domain = source_owner_domain(r, modules)
        owners = resolve_owner(r.surface, domain, modules)
        if len(owners) == 1:
            owner, wave = owners[0], modules[owners[0]].wave
            resolution = {"status": "RESOLVED", "reason": None}
        else:
            owner = wave = None
            resolution = {"status": "UNRESOLVED",
                          "reason": UNRESOLVED_NO_DOMAIN if domain is None
                          else f"OWNER_MATCHES_{len(owners)}_MODULES"}
        row: dict[str, Any] = {
            "screen_id": r.screen_id, "surface": r.surface,
            "registry_module": r.registry_module, "owning_module": owner,
            "wave": wave, "owner_domain": domain if owner else None,
            "owner_resolution": resolution, "binding_status": UNBOUND,
        }
        row.update({f: UNBOUND for f in BINDING_FIELDS})
        screens.append(row)
    index: dict[str, list[str]] = {m: [] for m in modules}
    for s in screens:
        if s["owning_module"]:
            index[s["owning_module"]].append(s["screen_id"])
    return {
        "version": 1,
        "generated_from": {
            "registry_source": SOURCE_REL,
            "registry_source_sha256": _sha256_text(source_text),
            "screen_registry_json": REGISTRY_REL,
            "screen_registry_json_ids_sha256": _sha256_text("\n".join(registry_ids)),
            "eip_appendix_f_module_table": EIP_REL,
            "eip_appendix_f_module_table_sha256": module_table_digest(modules),
        },
        "counts": {"total": len(screens),
                   "by_surface": surface_counts([s["surface"] for s in screens])},
        "module_screens": index,
        "screens": screens,
    }


def render_manifest(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def generate_manifest_text(source_text: str, registry_ids: list[str], eip_text: str,
                           *, enforce: bool = True) -> str:
    rows = build_canonical_rows(source_text)
    if enforce:
        verify_counts(rows)
        if [r.screen_id for r in rows] != registry_ids:
            raise GenerationError(f"{REGISTRY_REL} Screen IDs differ from the registry source's V1 UI rows")
    modules = parse_module_table(eip_text)
    return render_manifest(build_manifest(rows, modules, source_text, registry_ids))


# --- identity check ----------------------------------------------------------------


@dataclass
class Violation:
    code: str
    subjects: list[str]
    detail: str


@dataclass
class Report:
    state: str
    violations: list[Violation] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _parse_manifest(text: str) -> dict[str, Any]:
    try:
        m = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest unparseable: {exc}") from exc
    if (not isinstance(m, dict) or m.get("version") != 1
            or not isinstance(m.get("screens"), list)
            or not isinstance(m.get("module_screens"), dict)):
        raise ManifestError("manifest must be an object with version 1, screens[] and module_screens{}")
    for i, row in enumerate(m["screens"]):
        if not isinstance(row, dict) or not isinstance(row.get("screen_id"), str):
            raise ManifestError(f"screens[{i}] is not an object with a string screen_id")
        if row.get("surface") not in EXPECTED_BY_SURFACE:
            raise ManifestError(
                f"{row['screen_id']}: unknown surface label {row.get('surface')!r}")
    return m


def check_manifest(manifest_text: str, source_text: str, registry_ids: list[str],
                   eip_text: str, implemented_modules: frozenset[str] = frozenset()) -> Report:
    """Gate-5 identity check (ADR-014 D2.4/D2.6). Never NOT_APPLICABLE."""
    try:
        manifest = _parse_manifest(manifest_text)
        modules = parse_module_table(eip_text)
        canonical = build_canonical_rows(source_text)
    except (ManifestError, GenerationError) as exc:
        return Report(ERROR, [Violation("INPUT_INVALID", ["-"], str(exc))])

    v: list[Violation] = []
    rows: list[dict[str, Any]] = manifest["screens"]
    ids = [r["screen_id"] for r in rows]
    src_ids = [c.screen_id for c in canonical]
    by_surface = surface_counts([r["surface"] for r in rows])
    info = [f"manifest rows: {len(rows)}; per-surface: {by_surface}",
            (f"source V1 UI rows: {len(src_ids)}; per-surface: "
             f"{surface_counts([c.surface for c in canonical])}")]

    if len(src_ids) != EXPECTED_TOTAL or surface_counts([c.surface for c in canonical]) != EXPECTED_BY_SURFACE:
        v.append(Violation("SOURCE_COUNT_MISMATCH", ["-"],
                           f"registry source has {len(src_ids)} V1 UI rows, expected {EXPECTED_TOTAL} "
                           f"split {list(EXPECTED_BY_SURFACE.values())}"))
    if src_ids != registry_ids:
        v.append(Violation("REGISTRY_JSON_MISMATCH", sorted(set(src_ids) ^ set(registry_ids)) or ["order"],
                           f"{REGISTRY_REL} Screen IDs differ from the registry source's V1 UI rows"))
    if len(rows) != EXPECTED_TOTAL or by_surface != EXPECTED_BY_SURFACE:
        v.append(Violation("COUNT_MISMATCH", ["-"],
                           f"manifest has {len(rows)} rows split {list(by_surface.values())}; "
                           f"expected {EXPECTED_TOTAL} split {list(EXPECTED_BY_SURFACE.values())}"))
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        v.append(Violation("DUPLICATE_SCREEN_ID", dupes, "Screen ID appears more than once"))
    invented = [i for i in ids if i not in set(src_ids)]
    if invented:
        v.append(Violation("INVENTED_SCREEN_ID", invented, "Screen ID is absent from the registry source"))
    missing = [i for i in src_ids if i not in set(ids)]
    if missing:
        v.append(Violation("MISSING_SCREEN_ID", missing, "source Screen ID has no manifest row"))

    bad_shape = [r["screen_id"] for r in rows if tuple(r) != ROW_KEYS]
    if bad_shape:
        v.append(Violation("ROW_SHAPE_INVALID", bad_shape, f"row keys must be exactly {ROW_KEYS}"))
    bad_binding = [r["screen_id"] for r in rows if r.get("binding_status") != UNBOUND
                   or any(r.get(f) != UNBOUND for f in BINDING_FIELDS)]
    if bad_binding:
        v.append(Violation("BINDING_FIELD_INVALID", bad_binding,
                           "binding_status must be UNBOUND with every binding field the literal UNBOUND "
                           "(never empty or invented); BOUND-row verification is not implemented here"))
    implemented_unbound = [r["screen_id"] for r in rows
                           if r.get("binding_status") == UNBOUND and r.get("owning_module") in implemented_modules]
    if implemented_unbound:
        v.append(Violation("UNBOUND_ROW_OWNER_IMPLEMENTED", implemented_unbound,
                           f"UNBOUND row whose owning module is marked implemented ({sorted(implemented_modules)})"))

    unresolved: list[str] = []
    ambiguous: list[str] = []
    mismatched: list[str] = []
    for r in rows:
        sid, owner, domain = r["screen_id"], r.get("owning_module"), r.get("owner_domain")
        if owner is None or owner not in modules or r.get("owner_resolution", {}).get("status") != "RESOLVED":
            unresolved.append(sid)
            continue
        candidates = resolve_owner(r["surface"], domain, modules)
        if len(candidates) > 1:
            ambiguous.append(sid)
        elif candidates != [owner] or r.get("wave") != modules[owner].wave:
            mismatched.append(sid)
    if unresolved:
        v.append(Violation("OWNER_UNRESOLVED", unresolved,
                           "no owning module resolves under the Appendix F rule (owner_domain + surface); "
                           "not guessed"))
    if ambiguous:
        v.append(Violation("OWNER_AMBIGUOUS", ambiguous, "owner_domain + surface match more than one module"))
    if mismatched:
        v.append(Violation("OWNER_MISMATCH", mismatched,
                           "recorded owner/wave is not what the Appendix F rule yields for the row"))

    index = manifest["module_screens"]
    if index.get("MOD-001") != []:
        v.append(Violation("MOD_001_ENTRY_INVALID", ["MOD-001"],
                           "module_screens must carry an explicit MOD-001: [] (MOD-001 owns zero screens)"))
    expected_index = {m: [r["screen_id"] for r in rows if r.get("owning_module") == m] for m in modules}
    if index != expected_index:
        v.append(Violation("MODULE_INDEX_MISMATCH", sorted(k for k in set(index) | set(expected_index)
                                                           if index.get(k) != expected_index.get(k)),
                           "module_screens does not equal the per-row owning_module grouping over the Appendix F modules"))

    try:
        regenerated = generate_manifest_text(source_text, registry_ids, eip_text, enforce=False)
    except GenerationError as exc:
        return Report(ERROR, [Violation("INPUT_INVALID", ["-"], str(exc))])
    if regenerated != manifest_text:
        v.append(Violation("MANIFEST_DRIFT", ["-"], "manifest is not byte-identical to regeneration from source"))

    return Report(FAIL if v else PASS, v, info)


def format_report(report: Report) -> str:
    out = [f"gate 5 screen-contract identity: {report.state}",
           (f"four-state result: state={report.state} (PASS|FAIL|ERROR|NOT_APPLICABLE; "
            "NOT_APPLICABLE is never a valid result for gate 5, ADR-014 D2.4)")]
    out += report.info
    for viol in report.violations:
        out.append(f"{viol.code} [{len(viol.subjects)}]: {viol.detail}")
        out.append("  " + ", ".join(viol.subjects))
    return "\n".join(out)


# --- CLI ---------------------------------------------------------------------------


def _read(path: Path, what: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise GenerationError(f"{what} {path} not found or is a symlink")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GenerationError(f"{what} {path}: unreadable ({type(exc).__name__}: {exc})") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("generate", "check"):
        p = sub.add_parser(name)
        p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
        p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
        p.add_argument("--eip", type=Path, default=DEFAULT_EIP)
        p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                       help="manifest path (output for generate, input for check)")
        if name == "check":
            p.add_argument("--implemented-modules", default="",
                           help="comma-separated module IDs marked implemented (no machine-readable "
                                "marker exists in the repository yet; default none)")
    args = parser.parse_args(argv)

    try:
        source_text = _read(args.source, "registry source")
        eip_text = _read(args.eip, "EIP mirror")
        registry_ids = load_registry_ids(args.registry)
        if args.cmd == "generate":
            text = generate_manifest_text(source_text, registry_ids, eip_text)
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            args.manifest.write_text(text, encoding="utf-8")
            print(f"wrote {args.manifest} ({len(text.splitlines())} lines)")
            return 0
        manifest_text = _read(args.manifest, "manifest")
    except GenerationError as exc:
        if args.cmd == "check":
            print(format_report(Report(ERROR, [Violation("INPUT_INVALID", ["-"], str(exc))])), file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    implemented = frozenset(m for m in args.implemented_modules.split(",") if m)
    report = check_manifest(manifest_text, source_text, registry_ids, eip_text, implemented)
    print(format_report(report))
    return EXIT_CODE[report.state]


if __name__ == "__main__":
    raise SystemExit(main())
