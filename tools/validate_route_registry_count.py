#!/usr/bin/env python3
"""
Frontend route-registry V1 count-equality lint (TSD §24.1 gate 5 release
gate; ADR-014 D2.7; EIP Appendix F):

    count(canonical V1 Screen IDs) == count(frontend route-registry V1 rows)

with the canonical count required to be exactly 170. Any mismatch is a
P1 that blocks feature freeze (`TSD_MIRROR.md:17349-17351`).

Inputs are the two existing committed files, read as-is and never written:
`contracts/ui/screen-registry.json` (`{"version": 1, "screens": [...]}`)
and `contracts/ui/frontend-route-registry.json`
(`{"version": 1, "routes": [...]}`). Every `routes` entry is counted as a
V1 row -- the existing file shape has no per-row phase marker. No route is
inferred or derived from a Screen ID.

Source binding: the screen-registry is not trusted on its own. The full
ordered Screen ID list is compared to the one the canonical generator
(`generate_screen_registry.build_registry`) derives from the frozen UX
export `veyro-product-experience-design/project/veyro-registry-data.js`.
Any difference is a release-stage `SCREEN_REGISTRY_SOURCE_MISMATCH`; a
missing, symlinked, unreadable or malformed source is exit 2. A count of
170 over fabricated IDs therefore cannot pass. The route-registry has no
frozen source to bind to (no route inventory exists yet), so only its count
and uniqueness are checked -- not that any path is correct.

Stages (ADR-014 D2.7: enforced at feature freeze/release):

* `release` (default, fail-closed): FAIL unless the canonical count is
  exactly 170 and the route-registry count equals it. An empty route
  registry is an explicit FAIL (`ROUTE_REGISTRY_EMPTY`), never a vacuous
  pass.
* `pre-release`: the equality is not enforced. The counts are still
  reported, with the shortfall stated; the result is `NOT ENFORCED`, never
  a PASS.

Exit codes: 0 = PASS (release) or NOT ENFORCED (pre-release); 1 = FAIL
(release-stage count violation); 2 = unreadable/malformed input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_screen_registry import DEFAULT_SOURCE, SourceFormatError, build_registry  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCREEN_REGISTRY = REPO_ROOT / "contracts" / "ui" / "screen-registry.json"
DEFAULT_ROUTE_REGISTRY = REPO_ROOT / "contracts" / "ui" / "frontend-route-registry.json"

# EIP Appendix F: Admin 85 + Front Desk & POS 16 + Coach 19 + Member 35 +
# Internal SaaS Console 15 = 170.
EXPECTED_V1_COUNT = 170

STAGES = ("release", "pre-release")


class RouteCountInputError(ValueError):
    """An input file did not match its documented whole-file shape."""


def _load_list(path: Path, key: str) -> list[str]:
    if path.is_symlink() or not path.is_file():
        raise RouteCountInputError(f"{key} input {path} not found or is a symlink")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouteCountInputError(f"{key} input {path}: unreadable ({type(exc).__name__}: {exc})") from exc
    if (not isinstance(raw, dict) or set(raw) != {"version", key}
            or type(raw.get("version")) is not int or raw["version"] != 1):
        raise RouteCountInputError(f"{key} input {path} must be exactly {{'version': 1, {key!r}: [...]}}")
    values = raw[key]
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise RouteCountInputError(f"{key} input {path} {key!r} must be a list of non-empty strings")
    if len(set(values)) != len(values):
        raise RouteCountInputError(f"{key} input {path} {key!r} has duplicate entries")
    return values


def load_canonical_ids(source: Path) -> list[str]:
    """Ordered canonical V1 UI Screen IDs, re-derived from the frozen UX
    export by the canonical generator (never from the registry under test)."""
    if source.is_symlink() or not source.is_file():
        raise RouteCountInputError(f"canonical source {source} not found or is a symlink")
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RouteCountInputError(
            f"canonical source {source}: unreadable ({type(exc).__name__}: {exc})") from exc
    try:
        return build_registry(text)["screens"]
    except SourceFormatError as exc:
        raise RouteCountInputError(f"canonical source {source}: {exc}") from exc


def check_source_binding(screens: list[str], canonical: list[str]) -> list[tuple[str, str]]:
    """Violations when the registry's ordered IDs differ from the canonical ones."""
    if screens == canonical:
        return []
    canon_set, reg_set = set(canonical), set(screens)
    detail = (f"screen-registry ({len(screens)} IDs) != canonical frozen-source list "
              f"({len(canonical)} IDs): {len(reg_set - canon_set)} not in source, "
              f"{len(canon_set - reg_set)} missing from registry")
    if canon_set == reg_set:
        detail += "; same IDs in a different order"
    return [("SCREEN_REGISTRY_SOURCE_MISMATCH", detail)]


def check_counts(screen_count: int, route_count: int) -> list[tuple[str, str]]:
    """Release-stage violations as `(code, detail)`; empty means equality holds."""
    violations: list[tuple[str, str]] = []
    if screen_count != EXPECTED_V1_COUNT:
        violations.append((
            "CANONICAL_COUNT_MISMATCH",
            f"canonical V1 Screen ID count is {screen_count}, expected exactly {EXPECTED_V1_COUNT}",
        ))
    if route_count == 0:
        violations.append((
            "ROUTE_REGISTRY_EMPTY",
            f"frontend route registry has 0 V1 rows; {EXPECTED_V1_COUNT} required -- an empty "
            "registry is not a pass",
        ))
    elif route_count != screen_count:
        violations.append((
            "ROUTE_COUNT_MISMATCH",
            f"frontend route-registry V1 count {route_count} != canonical V1 Screen ID count {screen_count}",
        ))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--screen-registry", type=Path, default=DEFAULT_SCREEN_REGISTRY)
    parser.add_argument("--route-registry", type=Path, default=DEFAULT_ROUTE_REGISTRY)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="frozen canonical UX export the screen-registry must match")
    parser.add_argument("--stage", choices=STAGES, default="release",
                        help="release (default, enforced, fail-closed) or pre-release (reported, not enforced)")
    args = parser.parse_args(argv)

    try:
        screens = _load_list(args.screen_registry, "screens")
        routes = _load_list(args.route_registry, "routes")
        canonical = load_canonical_ids(args.source)
    except RouteCountInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    violations = check_source_binding(screens, canonical) + check_counts(len(screens), len(routes))
    summary = f"canonical V1 screens={len(screens)}, route-registry V1 rows={len(routes)}, required={EXPECTED_V1_COUNT}"

    if args.stage == "pre-release":
        print(f"ROUTE COUNT NOT ENFORCED (pre-release stage): {summary}. "
              f"{len(violations)} release-stage violation(s) would apply. This is not a PASS.")
        for code, detail in violations:
            print(f"  would-fail: {code}: {detail}")
        return 0

    if violations:
        for code, detail in violations:
            print(f"error: {code}: {detail}", file=sys.stderr)
        print(f"ROUTE COUNT FAIL (release stage): {summary}", file=sys.stderr)
        return 1

    print(f"ROUTE COUNT PASS (release stage): {summary}. Count-equality lint only; "
          "not a gate-5 certification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
