#!/usr/bin/env python3
"""
Validates an explicit, full per-screen Appendix F source declaration
("declarations" input) against the canonical Screen ID registry
(`contracts/ui/screen-registry.json`, produced by
`tools/generate_screen_registry.py`), together with two separate explicit
authority inputs for frontend routes and OpenAPI/AsyncAPI operations.

This is the next bounded increment after `tools/generate_screen_contracts.py`
(MOD-001 `IMPLEMENTATION.md` §10, EIP Appendix F), per
`R04-GATE5-FULL-SOURCE-CONTRACT-SELECTION-2026-10-09.md`'s minimum next
bounded work unit: "Define the smallest explicit, versioned source
contract for full-field per-screen declarations and separate frontend
route/OpenAPI/AsyncAPI inputs, using canonical Screen IDs as keys."

This tool is **validation-only**, like its predecessor. It has no code
path that writes or renders `contracts/ui/screen-contracts.yaml` or any
other canonical artifact shape, and it never claims a gate-5/manifest
PASS. On a syntactically complete, unambiguous declaration set covering
every canonical Screen ID with resolved route/API provenance, the most
this tool reports is `SOURCE INPUT SHAPE VALID` -- a source-shape
validation result, never a gate-5/manifest PASS.

Declaration row shape (JSON, stdlib only -- no PyYAML):

    {
      "screen_id": "CON-01",
      "surface": "Console",
      "owner_domain": "Console",
      "owner_module": "mod_console",
      "secondary_domains": [],
      "ownership_provenance": "EIP_APPENDIX_B:Console",
      "route": "/console/overview",
      "route_provenance": "FRONTEND_ROUTE_REGISTRY",
      "primary_read_model": "console_overview_read",
      "queries": ["bff:console.overview_read"],
      "commands": [],
      "realtime_channels": [],
      "permissions": ["console.read"],
      "assurance": "standard",
      "masking_variant": "none",
      "offline_mode": "unsupported",
      "expected_error_codes": ["NOT_FOUND"],
      "states": {"empty": "No data yet", "loading": "Loading...", "error": "Retry"},
      "api_provenance": "FRONTEND_API_REGISTRY"
    }

Every field in `REQUIRED_DECLARATION_FIELDS` is mandatory on every row --
never silently defaulted. `route`/`route_provenance` and the API bundle
(`primary_read_model`/`queries`/`commands`/`realtime_channels` paired with
`api_provenance`) each follow the same absence-pairing rule as the prior
tool: a cell with no authoritative source is explicitly absent (`null` /
empty list), never filled with a value, which is exactly the "inferred
route" EIP Appendix F forbids. `ownership_provenance` has no such escape
hatch -- MOD-001 `IMPLEMENTATION.md` §10 step 6 treats zero or ambiguous
ownership as a validation failure, never an honest gap, so the literal
`ABSENT_NO_AUTHORITATIVE_SOURCE` is never accepted there.

Unlike the prior tool, this one accepts two separate, explicit authority
inputs -- `--route-authority` (a declared set of authoritative frontend
routes) and `--api-authority` (a declared set of authoritative OpenAPI/
AsyncAPI operation identifiers) -- so a non-absent provenance pointer CAN
resolve, against synthetic fixtures only. A run with either flag omitted
resolves that authority to the committed zero-row registry
(`contracts/ui/frontend-route-registry.json` /
`contracts/ui/api-operation-authority.json`), which defines no routes or
operations yet, so every non-absent pointer is
`UNVERIFIABLE_PROVENANCE_POINTER`. (The `load_*_authority(None)` helpers
still return the empty set; only the CLI defaults point at the files.)
Nothing here infers a route, command, or query from the Screen ID, the UX
prototype, or any heuristic -- every value is caller-supplied explicit
input, only ever checked, never originated.

Validation is fail-closed on every one of the following, each citing the
specific Screen ID (or row index when the row has no usable `screen_id`)
and a field name where relevant, never silently dropped or merged:

* `MISSING_SCREEN_DECLARATION` -- a canonical Screen ID has no declaration row.
* `UNKNOWN_SCREEN_ID` -- a declaration row's `screen_id` is not in the
  canonical registry.
* `UNKNOWN_SURFACE_PREFIX` -- a `screen_id`'s prefix matches no known UI
  surface (IMPLEMENTATION.md §10 step 3/6's "unknown prefix" failure).
* `INCOMPLETE_DECLARATION_ROW` -- a row is missing a required field, a
  field is malformed, or `owner_domain` also appears in its own
  `secondary_domains` (primary and secondary must be disjoint).
* `OWNERSHIP_PROVENANCE_ABSENT` -- `ownership_provenance` is the literal
  `ABSENT_NO_AUTHORITATIVE_SOURCE`; ownership must always resolve.
* `ABSENT_PROVENANCE_VALUE_POPULATED` -- a cell with absent provenance
  (`route_provenance` or `api_provenance` is the absent literal) carries a
  populated value anyway (`route` non-null, or any of
  `primary_read_model`/`queries`/`commands`/`realtime_channels` non-empty).
* `PROVENANCE_UNRESOLVED` -- `route_provenance` or `api_provenance` is the
  absent literal; an honest gap declaration, but still fail-closed.
* `UNVERIFIABLE_PROVENANCE_POINTER` -- a non-absent `route`, `query`,
  `command`, or `realtime_channel` value does not appear in the
  corresponding authority input (or no authority input was supplied).
* `DUPLICATE_DECLARATION_ID` -- the same `screen_id` appears more than once
  with identical field values.
* `CONFLICTING_DECLARATION_ID` -- the same `screen_id` appears more than
  once with differing field values.

What this does NOT do (deliberately out of scope): resolve or infer any
owner/route/API binding from the Screen ID or any heuristic; generate or
write `contracts/ui/screen-contracts.yaml`; populate the real 170-screen
mapping (no real route/API authority source exists in this repository);
wire this into CI; or claim any gate/scenario/manifest PASS.
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
DEFAULT_ROUTE_AUTHORITY = REPO_ROOT / "contracts" / "ui" / "frontend-route-registry.json"
DEFAULT_API_AUTHORITY = REPO_ROOT / "contracts" / "ui" / "api-operation-authority.json"

# Real canonical V1 UI surface prefixes (`IMPLEMENTATION.md` §10 step 3) --
# mirrors `generate_screen_registry.py`'s own `_UI_SURFACE_PREFIXES` rather
# than importing it, matching that tool's own precedent of not coupling
# sibling tool scripts to each other's internals.
_UI_SURFACE_PREFIXES = ("ADM-", "FD-", "POS-", "CCH-", "MBR-", "CON-")

REQUIRED_DECLARATION_FIELDS = (
    "screen_id", "surface", "owner_domain", "owner_module", "secondary_domains",
    "ownership_provenance", "route", "route_provenance", "primary_read_model",
    "queries", "commands", "realtime_channels", "permissions", "assurance",
    "masking_variant", "offline_mode", "expected_error_codes", "states",
    "api_provenance",
)

# The row fields the API-authority input independently verifies -- the
# literal OpenAPI/AsyncAPI surface references (queries == OpenAPI reads,
# commands == OpenAPI writes, realtime_channels == AsyncAPI channels).
_API_LIST_FIELDS = ("queries", "commands", "realtime_channels")
_LIST_FIELDS = (*_API_LIST_FIELDS, "permissions", "expected_error_codes")
_STATE_KEYS = ("empty", "loading", "error")

# The only literal accepted in place of a real resolvable pointer for
# route/API provenance -- mirrors `generate_screen_contracts.py`'s own
# `PROVENANCE_ABSENT` constant and meaning exactly.
PROVENANCE_ABSENT = "ABSENT_NO_AUTHORITATIVE_SOURCE"

_ROUTE_RE = re.compile(r"/[^\s]*")


class SourceInputError(ValueError):
    """The canonical registry, an authority input, or the declarations file
    itself did not match the documented whole-file shape."""


@dataclass(frozen=True)
class Violation:
    code: str
    subject: str
    detail: str


def load_screen_registry(path: Path) -> list[str]:
    """The canonical identity input: `contracts/ui/screen-registry.json`,
    `{"version": 1, "screens": [...]}`, duplicate-free."""
    if path.is_symlink() or not path.is_file():
        raise SourceInputError(f"screen registry {path} not found or is a symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceInputError(f"screen registry {path}: unreadable ({type(exc).__name__}: {exc})") from exc
    if (not isinstance(raw, dict) or set(raw) != {"version", "screens"}
            or type(raw.get("version")) is not int or raw["version"] != 1):
        raise SourceInputError(f"screen registry {path} must be exactly {{'version': 1, 'screens': [...]}}")
    screens = raw["screens"]
    if not isinstance(screens, list) or not all(isinstance(s, str) and s for s in screens):
        raise SourceInputError(f"screen registry {path} 'screens' must be a list of non-empty strings")
    if len(set(screens)) != len(screens):
        raise SourceInputError(f"screen registry {path} 'screens' has duplicate Screen ID(s)")
    return screens


def load_declarations(path: Path) -> list[Any]:
    """The explicit, caller-supplied full per-screen source declaration
    input. Only the whole-file shape is checked here; per-row content is
    checked by `validate_declarations` so every row-level problem can be
    cited by Screen ID."""
    if path.is_symlink() or not path.is_file():
        raise SourceInputError(f"declarations {path} not found or is a symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceInputError(f"declarations {path}: unreadable ({type(exc).__name__}: {exc})") from exc
    if (not isinstance(raw, dict) or set(raw) != {"version", "declarations"}
            or type(raw.get("version")) is not int or raw["version"] != 1):
        raise SourceInputError(f"declarations {path} must be exactly {{'version': 1, 'declarations': [...]}}")
    declarations = raw["declarations"]
    if not isinstance(declarations, list):
        raise SourceInputError(f"declarations {path} 'declarations' must be a list")
    return declarations


def _load_authority(path: Path | None, key: str) -> set[str]:
    """A declared set of authoritative values (routes, or API operation
    identifiers). Returns the empty set when no authority input was
    supplied -- this repository has no real such source yet, so every
    non-absent provenance pointer is then necessarily unverifiable."""
    if path is None:
        return set()
    if path.is_symlink() or not path.is_file():
        raise SourceInputError(f"authority input {path} not found or is a symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceInputError(f"authority input {path}: unreadable ({type(exc).__name__}: {exc})") from exc
    if (not isinstance(raw, dict) or set(raw) != {"version", key}
            or type(raw.get("version")) is not int or raw["version"] != 1):
        raise SourceInputError(f"authority input {path} must be exactly {{'version': 1, {key!r}: [...]}}")
    values = raw[key]
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise SourceInputError(f"authority input {path} {key!r} must be a list of non-empty strings")
    if len(set(values)) != len(values):
        raise SourceInputError(f"authority input {path} {key!r} has duplicate entries")
    return set(values)


def load_route_authority(path: Path | None) -> set[str]:
    """`{"version": 1, "routes": [...]}` -- the authoritative frontend
    route registry, kept separate from the API authority input."""
    return _load_authority(path, "routes")


def load_api_authority(path: Path | None) -> set[str]:
    """`{"version": 1, "operations": [...]}` -- the authoritative OpenAPI/
    AsyncAPI operation identifiers, kept separate from the route authority
    input."""
    return _load_authority(path, "operations")


def _row_subject(row: Any, index: int) -> str:
    if isinstance(row, dict) and isinstance(row.get("screen_id"), str) and row["screen_id"]:
        return row["screen_id"]
    return f"declarations[{index}]"


def _structural_errors(row: Any) -> str | None:
    """Reason the row is incomplete/malformed, or `None` if the row is
    structurally sound enough to check provenance/authority next."""
    if not isinstance(row, dict) or set(row) != set(REQUIRED_DECLARATION_FIELDS):
        return f"row must have exactly the fields {REQUIRED_DECLARATION_FIELDS}"
    r = row
    if not (isinstance(r["screen_id"], str) and r["screen_id"]):
        return "screen_id must be a non-empty string"
    if not (isinstance(r["surface"], str) and r["surface"].strip()):
        return "surface must be a non-empty string"
    if not (isinstance(r["owner_domain"], str) and r["owner_domain"].strip()):
        return "owner_domain must be a non-empty string"
    if not (isinstance(r["owner_module"], str) and r["owner_module"].strip()):
        return "owner_module must be a non-empty string"
    if not (isinstance(r["secondary_domains"], list)
            and all(isinstance(d, str) and d.strip() for d in r["secondary_domains"])):
        return "secondary_domains must be a list of non-empty strings"
    if r["owner_domain"] in r["secondary_domains"]:
        return "owner_domain also appears in secondary_domains -- primary and secondary must be disjoint"
    if not (isinstance(r["ownership_provenance"], str) and r["ownership_provenance"].strip()):
        return "ownership_provenance must be a non-empty string"
    if r["route"] is not None and not (isinstance(r["route"], str) and _ROUTE_RE.fullmatch(r["route"])):
        return "route must be null or a non-empty absolute path with no whitespace"
    if not (isinstance(r["route_provenance"], str) and r["route_provenance"].strip()):
        return "route_provenance must be a non-empty string"
    if r["primary_read_model"] is not None and not (
            isinstance(r["primary_read_model"], str) and r["primary_read_model"].strip()):
        return "primary_read_model must be null or a non-empty string"
    for field in _LIST_FIELDS:
        if not (isinstance(r[field], list) and all(isinstance(v, str) and v for v in r[field])):
            return f"{field} must be a list of non-empty strings"
    for field in ("assurance", "masking_variant", "offline_mode"):
        if r[field] is not None and not (isinstance(r[field], str) and r[field].strip()):
            return f"{field} must be null or a non-empty string"
    if (not isinstance(r["states"], dict) or set(r["states"]) != set(_STATE_KEYS)
            or not all(isinstance(r["states"][k], str) and r["states"][k].strip() for k in _STATE_KEYS)):
        return f"states must be an object with exactly the non-empty string fields {_STATE_KEYS}"
    if not (isinstance(r["api_provenance"], str) and r["api_provenance"].strip()):
        return "api_provenance must be a non-empty string"
    return None


def _ownership_violations(screen_id: str, row: dict[str, Any]) -> list[Violation]:
    if row["ownership_provenance"] == PROVENANCE_ABSENT:
        return [Violation(
            "OWNERSHIP_PROVENANCE_ABSENT", screen_id,
            f"{screen_id}'s ownership_provenance is {PROVENANCE_ABSENT!r} -- ownership must always "
            "resolve (IMPLEMENTATION.md §10 step 6 treats zero/ambiguous ownership as a failure, "
            "never an honest gap)",
        )]
    return []


def _route_violations(screen_id: str, row: dict[str, Any], route_authority: set[str]) -> list[Violation]:
    absent = row["route_provenance"] == PROVENANCE_ABSENT
    if absent and row["route"] is not None:
        return [Violation(
            "ABSENT_PROVENANCE_VALUE_POPULATED", screen_id,
            f"route is {row['route']!r} but route_provenance is {PROVENANCE_ABSENT!r} -- a cell "
            "with no authoritative source must be absent (null), never filled with a value",
        )]
    if absent:
        return [Violation(
            "PROVENANCE_UNRESOLVED", screen_id,
            f"{screen_id}'s route_provenance is explicitly {PROVENANCE_ABSENT!r} -- no authoritative "
            "frontend route source exists for this screen, so its route authority is not established",
        )]
    if row["route"] is None:
        return [Violation(
            "INCOMPLETE_DECLARATION_ROW", screen_id,
            f"{screen_id}'s route_provenance is populated ({row['route_provenance']!r}) but route "
            "is null -- a claimed source with no cited value",
        )]
    if row["route"] not in route_authority:
        return [Violation(
            "UNVERIFIABLE_PROVENANCE_POINTER", screen_id,
            f"route {row['route']!r} does not appear in the supplied --route-authority input "
            "(or none was supplied) -- this repository has no authoritative frontend route registry "
            "to verify it against",
        )]
    return []


def _api_violations(screen_id: str, row: dict[str, Any], api_authority: set[str]) -> list[Violation]:
    absent = row["api_provenance"] == PROVENANCE_ABSENT
    bundle_populated = row["primary_read_model"] is not None or any(row[f] for f in _API_LIST_FIELDS)
    if absent and bundle_populated:
        return [Violation(
            "ABSENT_PROVENANCE_VALUE_POPULATED", screen_id,
            f"{screen_id}'s api_provenance is {PROVENANCE_ABSENT!r} but primary_read_model/queries/"
            "commands/realtime_channels are not all empty -- a cell with no authoritative source "
            "must be absent, never filled with a value",
        )]
    if absent:
        return [Violation(
            "PROVENANCE_UNRESOLVED", screen_id,
            f"{screen_id}'s api_provenance is explicitly {PROVENANCE_ABSENT!r} -- no authoritative "
            "OpenAPI/AsyncAPI source exists for this screen, so its API authority is not established",
        )]
    if not bundle_populated:
        return [Violation(
            "INCOMPLETE_DECLARATION_ROW", screen_id,
            f"{screen_id}'s api_provenance is populated ({row['api_provenance']!r}) but queries/"
            "commands/realtime_channels are all empty -- a claimed source with nothing cited",
        )]
    found: list[Violation] = []
    for field in _API_LIST_FIELDS:
        for value in row[field]:
            if value not in api_authority:
                found.append(Violation(
                    "UNVERIFIABLE_PROVENANCE_POINTER", screen_id,
                    f"{field} entry {value!r} does not appear in the supplied --api-authority input "
                    "(or none was supplied) -- this repository has no authoritative OpenAPI/AsyncAPI "
                    "source to verify it against",
                ))
    return found


def _surface_violations(screen_id: str) -> list[Violation]:
    if not screen_id.startswith(_UI_SURFACE_PREFIXES):
        return [Violation(
            "UNKNOWN_SURFACE_PREFIX", screen_id,
            f"{screen_id}: unknown prefix (matches no known UI surface {_UI_SURFACE_PREFIXES})",
        )]
    return []


def _freeze(value: Any) -> Any:
    """A hashable, order-stable representation of a declaration row for
    the duplicate/conflicting dedupe below -- rows contain nested lists and
    a nested `states` dict, neither of which plain `tuple(sorted(...))` can
    hash directly."""
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def validate_declarations(
    canonical: list[str],
    declarations: list[Any],
    route_authority: set[str],
    api_authority: set[str],
) -> tuple[list[Violation], dict[str, dict[str, str]]]:
    """Returns `(violations, {screen_id: {"owner_domain": ..., "owner_module": ...}})`.
    The resolution map is an in-memory diagnostic aid only -- it is never
    rendered into `contracts/ui/screen-contracts.yaml` or any other
    canonical shape -- and records the *primary* owner only, never a
    `secondary_domains` entry, so a caller can confirm multi-domain rows
    resolve to the primary mutation/route contract's owner, not the
    secondary reference (IMPLEMENTATION.md §10 step 5)."""
    violations: list[Violation] = []
    canonical_set = set(canonical)
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, row in enumerate(declarations):
        subject = _row_subject(row, index)
        reason = _structural_errors(row)
        if reason is not None:
            violations.append(Violation("INCOMPLETE_DECLARATION_ROW", subject, reason))
            continue
        screen_id = row["screen_id"]
        violations.extend(_surface_violations(screen_id))
        if screen_id not in canonical_set:
            violations.append(Violation(
                "UNKNOWN_SCREEN_ID", screen_id,
                f"{screen_id} is not in the canonical screen registry",
            ))
            continue
        violations.extend(_ownership_violations(screen_id, row))
        violations.extend(_route_violations(screen_id, row, route_authority))
        violations.extend(_api_violations(screen_id, row, api_authority))
        by_id[screen_id].append(row)

    resolved_by_id: dict[str, dict[str, str]] = {}
    for screen_id, rows in by_id.items():
        distinct = {_freeze(r) for r in rows}
        if len(rows) > 1 and len(distinct) == 1:
            violations.append(Violation(
                "DUPLICATE_DECLARATION_ID", screen_id,
                f"{screen_id} has {len(rows)} identical declaration rows; exactly one is required",
            ))
        elif len(rows) > 1:
            violations.append(Violation(
                "CONFLICTING_DECLARATION_ID", screen_id,
                f"{screen_id} has {len(distinct)} conflicting declaration rows "
                "(differing owner/route/API fields)",
            ))
        else:
            resolved_by_id[screen_id] = {
                "owner_domain": rows[0]["owner_domain"],
                "owner_module": rows[0]["owner_module"],
            }

    for screen_id in canonical:
        if screen_id not in by_id:
            violations.append(Violation(
                "MISSING_SCREEN_DECLARATION", screen_id,
                f"{screen_id} has no source declaration row",
            ))

    return violations, resolved_by_id


def main(argv: list[str] | None = None) -> int:
    """Validation-only entry point. There is deliberately no `--output`
    option and no code path here that writes or renders
    `contracts/ui/screen-contracts.yaml` -- an unrecognized `--output`
    flag is rejected by argparse itself (exit 2), not silently accepted."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--screen-registry", type=Path, default=DEFAULT_SCREEN_REGISTRY,
                        help="canonical Screen ID identity input (contracts/ui/screen-registry.json)")
    parser.add_argument("--declarations", type=Path, required=True,
                        help="explicit full per-screen Appendix F source declaration input (JSON) -- "
                             "no default: no authoritative source exists in this repository yet")
    parser.add_argument("--route-authority", type=Path, default=DEFAULT_ROUTE_AUTHORITY,
                        help="authoritative frontend route registry input (JSON); default is the "
                             "committed zero-row contracts/ui/frontend-route-registry.json")
    parser.add_argument("--api-authority", type=Path, default=DEFAULT_API_AUTHORITY,
                        help="authoritative OpenAPI/AsyncAPI operation input (JSON); default is the "
                             "committed zero-row contracts/ui/api-operation-authority.json")
    args = parser.parse_args(argv)

    try:
        canonical = load_screen_registry(args.screen_registry)
        declarations = load_declarations(args.declarations)
        route_authority = load_route_authority(args.route_authority)
        api_authority = load_api_authority(args.api_authority)
    except SourceInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    violations, _ = validate_declarations(canonical, declarations, route_authority, api_authority)
    if violations:
        for v in violations:
            print(f"error: {v.code}: {v.subject}: {v.detail}", file=sys.stderr)
        print(f"error: {len(violations)} violation(s)", file=sys.stderr)
        return 2

    print(
        f"SOURCE INPUT SHAPE VALID: {args.declarations} declares all {len(canonical)} canonical "
        f"screen ID(s) in {args.screen_registry} with well-formed, unambiguous ownership and "
        "resolved route/API provenance. This is a source-shape validation result, not a "
        "gate-5/manifest PASS; no contracts/ui/screen-contracts.yaml was written."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
