"""
Toolchain-matrix real-config validator (MOD-001, GOV-01-R07; SCN-MOD001-127).

    validate_toolchain_matrix.py [--root DIR]

Reads <root>/mobile/TOOLCHAIN_MATRIX.md and every <root>/mobile/**/build.gradle.kts
and fails closed on:

  TOOLCHAIN_DRIFT                 a matrix pin differs from the committed Gradle config
  CONFIG_PIN_MISSING              a matrix pin has no counterpart in committed config
  WHITELABEL_BRAND_MISSING        a declared branded app (androidApp product flavor)
                                  has no whitelabel_release_metadata row
  WHITELABEL_FIELD_MISSING        a brand row has an empty field
  WHITELABEL_DRIFT                a brand row's bundle_package_id differs from config
  SHARED_MODULE_VERSION_MISSING   a declared KMP module has no shared_module_version
  SHARED_MODULE_VERSION_DRIFT     the matrix version differs from the module's version
  SHARED_MODULE_CONFIG_MISSING    a matrix-versioned module has no committed KMP build.gradle.kts
  MATRIX_INVALID                  unreadable file or missing section/pin

Matrix-internal consistency is a separate check (SCN-MOD001-051/099). Exit 0 on
pass; exit 1 with one named defect per line on stdout otherwise.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PINS = ("kotlin", "compose_compiler_plugin", "compose_multiplatform", "gradle", "agp", "xcode")
CONFIG_PINS = tuple(p for p in PINS if p != "xcode")  # Xcode has no committed config yet
BRAND_FIELDS = ("store", "bundle_package_id", "release_version", "min_supported_version", "store_status")

_V = r'"([^"]+)"'
PIN_PATTERNS = {
    "kotlin": (rf'kotlin\("(?:multiplatform|android)"\)\s+version\s+{_V}',),
    "compose_compiler_plugin": (rf'id\("org\.jetbrains\.kotlin\.plugin\.compose"\)\s+version\s+{_V}',),
    "compose_multiplatform": (rf'id\("org\.jetbrains\.compose"\)\s+version\s+{_V}',),
    "gradle": (rf'gradle\.gradleVersion\s*==\s*{_V}',),
    "agp": (rf'id\("com\.android\.(?:library|application)"\)\s+version\s+{_V}',),
}
_FLAVOR = re.compile(r'create\("(\w+)"\)\s*\{[^{}]*?applicationId\s*=\s*"([^"]+)"')
_MODULE_VERSION = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')
_BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
_LINE_COMMENT = re.compile(r'(?m)(?:^|(?<=\s))//.*$')
_HEADING = re.compile(r'^#{1,6}\s+(.*?)\s*#*\s*$')


def parse_matrix(text: str) -> dict[str, list[dict[str, str]]]:
    """Section name -> rows (dicts keyed by the table header)."""
    sections: dict[str, list[dict[str, str]]] = {}
    current = None
    header: list[str] | None = None
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            current, header = m.group(1).strip(), None
            sections.setdefault(current, [])
            continue
        if current is None or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        if header is None:
            header = cells
        elif len(cells) == len(header):
            sections[current].append(dict(zip(header, cells)))
    return sections


def _strip(src: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub(" ", src))


def check(root: Path) -> list[str]:
    mobile = root / "mobile"
    try:
        sections = parse_matrix((mobile / "TOOLCHAIN_MATRIX.md").read_text(encoding="utf-8"))
        gradle_files = sorted(p for p in mobile.rglob("build.gradle.kts") if "build" not in p.relative_to(mobile).parts[:-1])
        configs = {p: _strip(p.read_text(encoding="utf-8")) for p in gradle_files}
    except (OSError, UnicodeDecodeError) as exc:
        return [f"MATRIX_INVALID: unreadable input ({type(exc).__name__}: {exc})"]
    if not configs:
        return ["MATRIX_INVALID: no mobile/**/build.gradle.kts committed config found"]

    defects: list[str] = []

    pins = {r.get("component", ""): r.get("version", "") for r in sections.get("toolchain_pins", [])}
    for name in PINS:
        if not pins.get(name):
            defects.append(f"MATRIX_INVALID: toolchain_pins is missing a version for '{name}'")
    for name in CONFIG_PINS:
        found = {(p.relative_to(root).as_posix(), v) for p, src in configs.items()
                 for pat in PIN_PATTERNS[name] for v in re.findall(pat, src)}
        if not found:
            defects.append(f"CONFIG_PIN_MISSING: no committed Gradle config pins '{name}'")
        for path, value in sorted(found):
            if pins.get(name) and value != pins[name]:
                defects.append(f"TOOLCHAIN_DRIFT: {name} matrix={pins[name]} {path}={value}")

    declared_modules = {p.parent.relative_to(root).as_posix(): src for p, src in configs.items()
                        if 'kotlin("multiplatform")' in src}
    versions = {r.get("module", ""): r.get("shared_module_version", "")
                for r in sections.get("shared_module_version", [])}
    for module, src in sorted(declared_modules.items()):
        if not versions.get(module):
            defects.append(f"SHARED_MODULE_VERSION_MISSING: {module}")
            continue
        m = _MODULE_VERSION.search(src)
        if not m:
            defects.append(f"SHARED_MODULE_VERSION_DRIFT: {module} has no committed version in build.gradle.kts")
        elif m.group(1) != versions[module]:
            defects.append(f"SHARED_MODULE_VERSION_DRIFT: {module} matrix={versions[module]} config={m.group(1)}")

    for module in sorted(m for m in versions if m and m not in declared_modules):
        defects.append(f"SHARED_MODULE_CONFIG_MISSING: {module} has a matrix version but no committed KMP build.gradle.kts")

    brands = {r.get("brand", ""): r for r in sections.get("whitelabel_release_metadata", [])}
    declared_brands = {name: pkg for src in configs.values() for name, pkg in _FLAVOR.findall(src)}
    if not declared_brands:
        defects.append("MATRIX_INVALID: no branded app (androidApp product flavor) declared in committed config")
    for brand, pkg in sorted(declared_brands.items()):
        row = brands.get(brand)
        if row is None:
            defects.append(f"WHITELABEL_BRAND_MISSING: {brand}")
            continue
        for field in BRAND_FIELDS:
            if not row.get(field):
                defects.append(f"WHITELABEL_FIELD_MISSING: {brand}.{field}")
        if row.get("bundle_package_id") and row["bundle_package_id"] != pkg:
            defects.append(f"WHITELABEL_DRIFT: {brand} bundle_package_id matrix={row['bundle_package_id']} config={pkg}")
    return defects


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    defects = check(ap.parse_args(argv).root)
    for d in defects:
        print(d)
    if not defects:
        print("PASS: toolchain matrix matches committed config")
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
