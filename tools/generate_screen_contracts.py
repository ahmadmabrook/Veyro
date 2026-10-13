#!/usr/bin/env python3
"""
Validates an explicit per-screen owner/route/API binding ("mapping-input")
source against the canonical Screen ID registry
(`contracts/ui/screen-registry.json`, produced by
`tools/generate_screen_registry.py`).

This tool is **validation-only**. It has no code path — CLI or function —
that writes or renders `contracts/ui/screen-contracts.yaml` or any other
canonical artifact shape, and it never claims a gate-5/manifest PASS. On a
syntactically complete, unambiguous mapping-input covering every canonical
Screen ID, the most this tool reports is `SOURCE INPUT SHAPE VALID`: that
the caller-supplied rows are well-formed. It does not check Appendix B
ownership, a frontend route registry, OpenAPI, or AsyncAPI, so real
route/API sources remain unresolved regardless of what this tool reports.
(Corrected 2026-10-09, subgoal R04-GATE5-PARTIAL-CANONICAL-OUTPUT-DENIAL —
an earlier revision wrote the two-field `id`/`target` shape to
`contracts/ui/screen-contracts.yaml` on a syntactically complete mapping,
and a test asserted that output passed gate 5's own parser as PASS; see
`knowledge/03-Modules/MOD-001/evidence/implementation/R04-GATE5-EXPLICIT-MAPPING-INPUT-LOCAL-RECONCILIATION-2026-10-09.md`.
A four-field synthetic subset could be mistaken for a fully qualified
170-screen manifest, which is a concrete false-completeness affordance.
This tool no longer has any way to produce that output.)

Why a separate mapping-input file (MOD-001 `IMPLEMENTATION.md` §10 steps
4-6, EIP Appendix F's "Generated row schema" line): Appendix F requires
owning-module/route/API-target rows to be generated "from source metadata
and module/domain ownership" and explicitly forbids "hand-authored
placeholder Screen IDs" — but this repository currently has no
authoritative frontend route registry, OpenAPI/AsyncAPI source, or full
screen-contract manifest to generate that binding *from* (confirmed by
inspection: no `contracts/modules/ownership.json`-equivalent route/API
source exists for the UI surface). Appendix B's execution-slice mapping
(§10 step 4) is the intended authority for owning-module resolution, but
is prose in `EIP_MIRROR.md`, not a machine-readable artifact this tool
can import. Inventing a resolution here — from the Screen ID's prefix,
from the UX prototype, or from any other heuristic — is exactly what
IMPLEMENTATION.md §10 step 1 and Appendix F's own text prohibit. This
tool therefore takes the binding as an explicit, caller-supplied input and
only *validates* it; it never infers one.

Mapping-input shape (JSON, stdlib only — no PyYAML, matching gate 5's own
"stdlib only" input contract):

    {
      "version": 1,
      "mappings": [
        {
          "screen_id": "CON-01",
          "owner_module": "mod_console",
          "route": null,
          "target": null,
          "provenance": {
            "route": "ABSENT_NO_AUTHORITATIVE_SOURCE",
            "target": "ABSENT_NO_AUTHORITATIVE_SOURCE"
          }
        }
      ]
    }

`route` and `target` are each nullable and must pair exactly with their
`provenance` component: when `provenance.<field>` is the literal
`ABSENT_NO_AUTHORITATIVE_SOURCE`, `<field>` itself must be JSON `null` --
never a populated literal, which is exactly the "inferred route" EIP
Appendix F forbids for a cell with no authoritative source. When
`provenance.<field>` is anything else (a purported pointer), `<field>`
must be populated. A row that breaks this pairing is rejected
(`ABSENT_PROVENANCE_VALUE_POPULATED`), independently for `route` and for
`target`.

The five fields are the minimum subset of Appendix F's full generated-row
schema ("screen_id -> surface -> route -> owning implementation module ->
wave -> owner_domain -> primary read model/query -> commands ->
permissions -> realtime -> masking/offline/error-state contract") needed
to validate an explicit owner/route/API binding shape — surface/wave/
owner_domain/permissions/etc. are a later, separate Implementation
Complete concern this tool does not touch, and this tool does not emit
any manifest row for any of the fields it does check.

Per the R04 gate-5 source-authority lead decision (2026-10-09,
`R04-GATE5-SOURCE-AUTHORITY-LEAD-DECISION-2026-10-09.md` §1/§4), every
route and API (`target`) cell must carry its own provenance: a pointer to
the specific authoritative source that establishes it (an authoritative
frontend route registry for `route`, OpenAPI/AsyncAPI for `target`), or
else the explicit literal `ABSENT_NO_AUTHORITATIVE_SOURCE` recording that
no such source exists. `provenance` is a single per-row field with
exactly two string-valued components, `route` and `target`, mirroring
the two cells it covers.

**Documented limit (this repository has no authoritative frontend route
registry, OpenAPI, or AsyncAPI source to resolve a pointer against —
same absence the lead decision's authority table records as ABSENT for
both fields): this tool can only ever accept the literal
`ABSENT_NO_AUTHORITATIVE_SOURCE` as a structurally well-formed
provenance value, and even that is not treated as success.** Any other
string is a purported pointer this tool has no way to verify, and is
rejected outright (`UNVERIFIABLE_PROVENANCE_POINTER`) rather than
accepted on faith — nominal-looking pointer strings (a path, a URL, a
spec anchor) are never treated as authoritative just because they are
present. And the honest `ABSENT_NO_AUTHORITATIVE_SOURCE` declaration
itself still yields `PROVENANCE_UNRESOLVED`, a violation like any
other: the lead decision is explicit that "no PASS, no partial PASS, no
waiver" applies while any row lacks route or API authority, so an
all-absent mapping-input must not be reported as
`SOURCE INPUT SHAPE VALID` — that would read as route/API coverage this
tool has not established. Both codes are fail-closed (nonzero exit,
explicit per-screen diagnostic); neither ever lets this tool invent or
infer a route/API binding.

Validation is fail-closed on every one of the following, each citing the
specific Screen ID (or row index when the row has no usable `screen_id`)
and never silently dropped, defaulted, or merged:

* `MISSING_SCREEN_BINDING` — a canonical Screen ID has no mapping row.
* `UNKNOWN_SCREEN_ID` — a mapping row's `screen_id` is not in the
  canonical registry (an extra/unknown ID).
* `INCOMPLETE_MAPPING_ROW` — a row is missing one of the five required
  fields, a field is not a well-formed value (`route`/`target` may be
  `null`, but if not `null` must be well-formed), or `provenance` is not
  an object with exactly the `route`/`target` components.
* `ABSENT_PROVENANCE_VALUE_POPULATED` — `provenance.<field>` is the
  literal `ABSENT_NO_AUTHORITATIVE_SOURCE` but `<field>` (`route` or
  `target`) is populated with a literal instead of `null`. A cell with
  no authoritative source must be absent, never filled with a value --
  checked independently for `route` and for `target`.
* `INVALID_TARGET` — `target` is populated but does not match gate 5's
  own `bff:<dotted>`/`command:<dotted>` shape.
* `UNVERIFIABLE_PROVENANCE_POINTER` — a `provenance` component is a
  string other than the literal `ABSENT_NO_AUTHORITATIVE_SOURCE`; this
  repository has no authoritative source to resolve it against, so the
  purported pointer is rejected rather than trusted.
* `PROVENANCE_UNRESOLVED` — a `provenance` component is the literal
  `ABSENT_NO_AUTHORITATIVE_SOURCE`; an honest declaration of the gap,
  but still fail-closed, never treated as route/API coverage.
* `DUPLICATE_MAPPING_ID` — the same `screen_id` appears more than once
  with identical field values.
* `AMBIGUOUS_MAPPING_ID` — the same `screen_id` appears more than once
  with conflicting field values (IMPLEMENTATION.md §10 step 6's
  "ambiguous owner").

Only when zero violations are found does this tool report
`SOURCE INPUT SHAPE VALID` on stdout and exit 0 — it never writes any
file, and that message is a source-shape validation result, not a
gate-5/manifest PASS. Given the documented limit above, every row's
`provenance` is fail-closed by construction (either
`UNVERIFIABLE_PROVENANCE_POINTER` or `PROVENANCE_UNRESOLVED`), so a
real mapping-input covering real route/API cells cannot reach that zero-
violation state until an authoritative frontend route registry and
OpenAPI/AsyncAPI source actually exist in this repository.

What this does NOT do (deliberately out of scope): resolve or infer any
owner/route/API binding from the Screen ID, the UX prototype, or any
other heuristic; cross-check `owner_module` against a module-ownership
registry (none exists yet — see above); resolve or verify a
`provenance` pointer against any real route/OpenAPI/AsyncAPI source (no
such source exists in this repository yet — see the documented limit
above); emit placeholder/synthetic rows for the real 170-screen registry
(no real binding source exists, so a real run with no mapping-input is
expected to fail closed, citing every canonical ID as
`MISSING_SCREEN_BINDING`); wire this into CI; write or render
`contracts/ui/screen-contracts.yaml` or any other canonical artifact
shape; or claim any gate/scenario/manifest PASS.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCREEN_REGISTRY = REPO_ROOT / "contracts" / "ui" / "screen-registry.json"

REQUIRED_ROW_FIELDS = ("screen_id", "owner_module", "route", "target", "provenance")

# The two row cells `provenance` must independently account for -- route
# authority and API (`target`) authority -- per the R04 gate-5 lead decision's
# authority table (both currently ABSENT in this repository).
PROVENANCE_COMPONENTS = ("route", "target")

# The only literal this tool accepts in place of a real resolvable pointer.
# See the module docstring's "Documented limit" -- no authoritative frontend
# route registry, OpenAPI, or AsyncAPI source exists here to resolve any
# other value against, so this is the sole non-rejected provenance value.
PROVENANCE_ABSENT = "ABSENT_NO_AUTHORITATIVE_SOURCE"

# Mirrors `validate_architecture_gates._SCREEN_TARGET_RE` exactly (duplicated
# here rather than imported, matching `generate_screen_registry.py`'s own
# precedent of re-stating gate-owned shapes locally instead of coupling to
# the gate module's internals) -- a target this tool accepts must be a
# target gate 5 itself will accept.
_SEGMENT = r"[a-z][a-z0-9_]*"
_TARGET_RE = re.compile(rf"(?:bff|command):{_SEGMENT}(?:\.{_SEGMENT})*")

# Minimal sanity shape for `route` -- an absolute path, no whitespace. No
# frontend route registry exists to validate against more strictly than
# this (see module docstring); this only rejects obviously-empty/garbage
# values, it does not assert the route is real.
_ROUTE_RE = re.compile(r"/[^\s]*")


class MappingInputError(ValueError):
    """The canonical registry or the mapping-input file itself did not
    match the documented shape -- a whole-file problem, not a per-row one."""


@dataclass(frozen=True)
class Violation:
    code: str
    subject: str
    detail: str


def load_screen_registry(path: Path) -> list[str]:
    """The canonical identity input: `contracts/ui/screen-registry.json`,
    `{"version": 1, "screens": [...]}`, duplicate-free. Re-validated here
    directly (not imported from `validate_architecture_gates.py`), matching
    `generate_screen_registry.py`'s own precedent of not coupling tool
    scripts to the gate module's internals."""
    if path.is_symlink() or not path.is_file():
        raise MappingInputError(f"screen registry {path} not found or is a symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MappingInputError(f"screen registry {path}: unreadable ({type(exc).__name__}: {exc})") from exc
    if (not isinstance(raw, dict) or set(raw) != {"version", "screens"}
            or type(raw.get("version")) is not int or raw["version"] != 1):
        raise MappingInputError(f"screen registry {path} must be exactly {{'version': 1, 'screens': [...]}}")
    screens = raw["screens"]
    if not isinstance(screens, list) or not all(isinstance(s, str) and s for s in screens):
        raise MappingInputError(f"screen registry {path} 'screens' must be a list of non-empty strings")
    if len(set(screens)) != len(screens):
        raise MappingInputError(f"screen registry {path} 'screens' has duplicate Screen ID(s)")
    return screens


def load_mapping_input(path: Path) -> list[Any]:
    """The explicit, caller-supplied owner/route/API binding source. Only
    the whole-file shape is checked here; per-row content is checked by
    `validate_mappings` so every row-level problem can be cited by ID."""
    if path.is_symlink() or not path.is_file():
        raise MappingInputError(f"mapping-input {path} not found or is a symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MappingInputError(f"mapping-input {path}: unreadable ({type(exc).__name__}: {exc})") from exc
    if (not isinstance(raw, dict) or set(raw) != {"version", "mappings"}
            or type(raw.get("version")) is not int or raw["version"] != 1):
        raise MappingInputError(f"mapping-input {path} must be exactly {{'version': 1, 'mappings': [...]}}")
    mappings = raw["mappings"]
    if not isinstance(mappings, list):
        raise MappingInputError(f"mapping-input {path} 'mappings' must be a list")
    return mappings


def _row_subject(row: Any, index: int) -> str:
    if isinstance(row, dict) and isinstance(row.get("screen_id"), str) and row["screen_id"]:
        return row["screen_id"]
    return f"mappings[{index}]"


def _structural_errors(row: Any) -> str | None:
    """Reason the row is incomplete/malformed independent of target shape
    (checked separately so it gets its own `INVALID_TARGET` code), or
    `None` if the row is structurally sound enough to check that next."""
    if not isinstance(row, dict) or set(row) != set(REQUIRED_ROW_FIELDS):
        return f"row must have exactly the fields {REQUIRED_ROW_FIELDS}"
    screen_id, owner_module, route, target, provenance = (row[k] for k in REQUIRED_ROW_FIELDS)
    if not (isinstance(screen_id, str) and screen_id):
        return "screen_id must be a non-empty string"
    if not (isinstance(owner_module, str) and owner_module.strip()):
        return "owner_module must be a non-empty string"
    if route is not None and not (isinstance(route, str) and _ROUTE_RE.fullmatch(route)):
        return ("route must be null (absent, pairing with provenance.route "
                f"{PROVENANCE_ABSENT!r}) or a non-empty absolute path with no whitespace")
    if target is not None and not isinstance(target, str):
        return ("target must be null (absent, pairing with provenance.target "
                f"{PROVENANCE_ABSENT!r}) or a string")
    if not isinstance(provenance, dict) or set(provenance) != set(PROVENANCE_COMPONENTS):
        return f"provenance must be an object with exactly the fields {PROVENANCE_COMPONENTS}"
    for component in PROVENANCE_COMPONENTS:
        value = provenance[component]
        if not (isinstance(value, str) and value.strip()):
            return f"provenance.{component} must be a non-empty string"
    return None


def _provenance_violations(screen_id: str, provenance: dict[str, str]) -> list[Violation]:
    """Per the documented limit (module docstring): this repository has no
    authoritative frontend route registry, OpenAPI, or AsyncAPI source, so
    there is no value this function can accept as an established, verified
    binding. Every component yields a violation -- `PROVENANCE_UNRESOLVED`
    for the honest `ABSENT_NO_AUTHORITATIVE_SOURCE` declaration,
    `UNVERIFIABLE_PROVENANCE_POINTER` for any other (unverifiable, possibly
    invented) value -- so route/API coverage is never implied by this tool."""
    found: list[Violation] = []
    for component in PROVENANCE_COMPONENTS:
        value = provenance[component]
        if value == PROVENANCE_ABSENT:
            found.append(Violation(
                "PROVENANCE_UNRESOLVED", screen_id,
                f"provenance.{component} is explicitly {PROVENANCE_ABSENT} -- no authoritative "
                f"source exists for this component in this repository, so {screen_id}'s "
                f"{component} authority is not established; an honest gap declaration, not a pass",
            ))
        else:
            found.append(Violation(
                "UNVERIFIABLE_PROVENANCE_POINTER", screen_id,
                f"provenance.{component} {value!r} cannot be resolved against an authoritative "
                "source -- this repository has no frontend route registry, OpenAPI, or AsyncAPI "
                f"source to verify it against; use the literal {PROVENANCE_ABSENT!r} instead of "
                "a purported pointer",
            ))
    return found


def _pairing_violations(screen_id: str, row: dict[str, Any]) -> list[Violation]:
    """Per the qualified R04 gate-5 source-authority decision: a cell with
    no authoritative source is explicitly absent (`None`/JSON `null`),
    never filled with a literal value -- a populated literal paired with
    ABSENT provenance is exactly the "inferred route" EIP Appendix F
    forbids. `PROVENANCE_COMPONENTS` names both the `provenance` keys and
    the row's own `route`/`target` fields, so this checks each row field
    against its own provenance component independently."""
    found: list[Violation] = []
    for field in PROVENANCE_COMPONENTS:
        if row["provenance"][field] == PROVENANCE_ABSENT and row[field] is not None:
            found.append(Violation(
                "ABSENT_PROVENANCE_VALUE_POPULATED", screen_id,
                f"{field} is {row[field]!r} but provenance.{field} is {PROVENANCE_ABSENT!r} -- "
                f"a cell with no authoritative source must be absent (null), never filled with "
                f"a literal value",
            ))
    return found


def _row_sort_key(row: dict[str, Any]) -> tuple:
    """A hashable, order-stable representation of a stored row for the
    duplicate/ambiguous dedupe below -- `provenance` is itself a dict, which
    plain `tuple(sorted(row.items()))` cannot hash or compare."""
    return tuple(sorted(
        (k, tuple(sorted(v.items())) if isinstance(v, dict) else v)
        for k, v in row.items()
    ))


def validate_mappings(canonical: list[str], mappings: list[Any]) -> tuple[list[Violation], dict[str, str]]:
    """Returns `(violations, {screen_id: target})`. The target map is an
    in-memory diagnostic aid only -- it is never rendered into
    `contracts/ui/screen-contracts.yaml` or any other canonical shape, and
    is still returned even when `violations` is non-empty so callers that
    want partial diagnostics can inspect it. Every value is `None`: no
    row's `target` provenance is ever independently source-verified in
    this repository (see the module docstring's "Documented limit"), so a
    populated literal -- whether paired with ABSENT provenance or an
    unverifiable pointer -- must never surface here."""
    violations: list[Violation] = []
    canonical_set = set(canonical)
    by_id: dict[str, list[dict[str, str]]] = defaultdict(list)

    for index, row in enumerate(mappings):
        subject = _row_subject(row, index)
        reason = _structural_errors(row)
        if reason is not None:
            violations.append(Violation("INCOMPLETE_MAPPING_ROW", subject, reason))
            continue
        screen_id, target, provenance = row["screen_id"], row["target"], row["provenance"]
        violations.extend(_pairing_violations(screen_id, row))
        if target is not None and not _TARGET_RE.fullmatch(target):
            violations.append(Violation(
                "INVALID_TARGET", screen_id,
                f"target {target!r} is not bff:<dotted> or command:<dotted>",
            ))
            continue
        if screen_id not in canonical_set:
            violations.append(Violation(
                "UNKNOWN_SCREEN_ID", screen_id,
                f"{screen_id} is not in the canonical screen registry",
            ))
            continue
        violations.extend(_provenance_violations(screen_id, provenance))
        by_id[screen_id].append({k: row[k] for k in REQUIRED_ROW_FIELDS})

    target_by_id: dict[str, str] = {}
    for screen_id, rows in by_id.items():
        distinct = {_row_sort_key(r) for r in rows}
        if len(rows) > 1 and len(distinct) == 1:
            violations.append(Violation(
                "DUPLICATE_MAPPING_ID", screen_id,
                f"{screen_id} has {len(rows)} identical mapping rows; exactly one is required",
            ))
        elif len(rows) > 1:
            violations.append(Violation(
                "AMBIGUOUS_MAPPING_ID", screen_id,
                f"{screen_id} has {len(distinct)} conflicting mapping rows (differing owner_module/route/target)",
            ))
        else:
            # No row's `target` provenance is ever independently
            # source-verified in this repository (see the module docstring's
            # "Documented limit" -- no OpenAPI/AsyncAPI source exists to
            # verify a pointer against, and the sole accepted ABSENT literal
            # itself yields PROVENANCE_UNRESOLVED, not verification). A
            # populated `target` must never surface here, whether it arrived
            # paired with ABSENT provenance (ABSENT_PROVENANCE_VALUE_POPULATED)
            # or an unverifiable pointer (UNVERIFIABLE_PROVENANCE_POINTER) --
            # this diagnostic aid only ever reflects the row's own null target.
            target_by_id[screen_id] = None

    for screen_id in canonical:
        if screen_id not in by_id:
            violations.append(Violation(
                "MISSING_SCREEN_BINDING", screen_id,
                f"{screen_id} has no owner/route/API binding in the mapping-input",
            ))

    return violations, target_by_id


def main(argv: list[str] | None = None) -> int:
    """Validation-only entry point. There is deliberately no `--output`
    option and no code path here that writes or renders
    `contracts/ui/screen-contracts.yaml` -- an unrecognized `--output`
    flag is rejected by argparse itself (exit 2), not silently accepted
    and ignored. See the module docstring's correction note."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--screen-registry", type=Path, default=DEFAULT_SCREEN_REGISTRY,
                        help="canonical Screen ID identity input (contracts/ui/screen-registry.json)")
    parser.add_argument("--mapping-input", type=Path, required=True,
                        help="explicit per-screen owner/route/API binding source (JSON) -- "
                             "no default: no authoritative source exists in this repository yet")
    args = parser.parse_args(argv)

    try:
        canonical = load_screen_registry(args.screen_registry)
        mappings = load_mapping_input(args.mapping_input)
    except MappingInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    violations, _ = validate_mappings(canonical, mappings)
    if violations:
        for v in violations:
            print(f"error: {v.code}: {v.subject}: {v.detail}", file=sys.stderr)
        print(f"error: {len(violations)} violation(s)", file=sys.stderr)
        return 2

    print(
        f"SOURCE INPUT SHAPE VALID: {args.mapping_input} covers all "
        f"{len(canonical)} canonical screen ID(s) in {args.screen_registry} "
        "with well-formed, unambiguous owner/route/API binding rows. This "
        "is a source-shape validation result, not a gate-5/manifest PASS; "
        "no contracts/ui/screen-contracts.yaml was written, and real "
        "route/API sources remain unresolved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
