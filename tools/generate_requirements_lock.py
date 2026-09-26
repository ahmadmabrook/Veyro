#!/usr/bin/env python3
"""
Deterministic dependency-lock generator/checker (MOD-001, BUG-036 Tier 2).

Never invoked by an agent session through `bash_guard.py` — this runs on
the owner's own machine, entirely outside the guard, against a wheel
directory `pip download --only-binary=:all:` has already populated (see
BUG-036 Round 5 for the full owner command sequence). Its only job is to
eliminate manual hash/version transcription when building
`backend/requirements-dev.lock.txt`: every value below is parsed from a
real downloaded wheel's own filename (PEP 427/600 naming) or computed
directly via `hashlib.sha256` on the real file bytes — a human never
re-types a version or a hash by hand, so there is no channel for a
transcription error to enter, the same class of risk a summarizing
web-fetch tool already demonstrated once in this bug's own history.

Two modes:
  generate <wheel_dir> <lock_file>   Write a fresh lock file from the
                                      wheels currently in <wheel_dir>.
  check <wheel_dir> <lock_file>      Independently verify an existing
                                      lock file against <wheel_dir>:
                                        - every wheel appears exactly
                                          once in the lock;
                                        - every lock entry's version is
                                          exact;
                                        - every lock entry's hash is the
                                          real file's SHA-256;
                                        - no extra entry exists in the
                                          lock with no matching wheel.

`generate` and `check` are independent code paths reading the same wheel
directory — running `check` after `generate` (or after re-downloading
into a fresh directory later) is a real, separate verification, not the
same computation repeated.

Deliberately stdlib-only (`argparse`, `hashlib`, `pathlib`, `sys`) — no
dependency on `packaging` or any other library being importable, so this
script itself has zero supply-chain surface beyond the Python interpreter
already required to run anything.
"""
import argparse
import hashlib
import sys
from pathlib import Path


def parse_wheel_filename(path: Path) -> tuple[str, str]:
    """PEP 427/600: {name}-{version}(-{build tag})?-{python tag}-{abi
    tag}-{platform tag}.whl — 5 or 6 dash-separated segments once '.whl'
    is stripped. Name/version segments never contain a literal '-'
    themselves (wheel-building tools normalize any '-' in the name or
    version to '_' before naming the file), so a plain split is safe."""
    if path.suffix != ".whl":
        raise ValueError(f"not a .whl file: {path.name}")
    stem = path.name[: -len(".whl")]
    parts = stem.split("-")
    if len(parts) not in (5, 6):
        raise ValueError(f"not a recognizable wheel filename: {path.name}")
    name, version = parts[0], parts[1]
    return name.replace("_", "-"), version


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_wheels(wheel_dir: Path) -> dict[str, tuple[str, str, Path]]:
    """Returns {name: (version, sha256, path)}. A duplicate package name
    in the directory is ambiguous (which wheel would the lock mean?) and
    is a hard error, never a silent pick-one."""
    if not wheel_dir.is_dir():
        print(f"BLOCKED: WHEEL_DIR_MISSING — {wheel_dir} is not a directory")
        sys.exit(1)
    found: dict[str, tuple[str, str, Path]] = {}
    for whl in sorted(wheel_dir.glob("*.whl")):
        name, version = parse_wheel_filename(whl)
        if name in found:
            print(
                f"BLOCKED: DUPLICATE_PACKAGE_IN_WHEEL_DIR — '{name}' matches both "
                f"{found[name][2].name} and {whl.name} in {wheel_dir} — refusing to guess which one the lock should pin"
            )
            sys.exit(1)
        found[name] = (version, sha256_of(whl), whl)
    return found


def generate(wheel_dir: Path, lock_file: Path) -> None:
    wheels = scan_wheels(wheel_dir)
    if not wheels:
        print(f"BLOCKED: NO_WHEELS_FOUND — no .whl files in {wheel_dir}")
        sys.exit(1)
    lines = [
        "# Generated deterministically by tools/generate_requirements_lock.py",
        f"# from the real downloaded wheels in {wheel_dir}.",
        "# Every name/version/hash below was parsed from a real wheel filename",
        "# or computed via hashlib.sha256 on the real file — never hand-typed.",
        "# Re-run `tools/generate_requirements_lock.py check <wheel_dir> <this file>`",
        "# to independently verify this file against the wheel directory.",
        "",
    ]
    for name in sorted(wheels):
        version, digest, _ = wheels[name]
        lines.append(f"{name}=={version} \\")
        lines.append(f"    --hash=sha256:{digest}")
    lock_file.write_text("\n".join(lines) + "\n")
    print(f"PASS — wrote {len(wheels)} package(s) to {lock_file}")


def _parse_lock(lock_file: Path) -> dict[str, list]:
    if not lock_file.exists():
        print(f"BLOCKED: LOCK_FILE_MISSING — {lock_file} does not exist")
        sys.exit(1)
    locked: dict[str, list] = {}
    current_name = None
    for raw in lock_file.read_text().splitlines():
        line = raw.strip()
        if line.endswith("\\"):
            line = line[:-1].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--hash=sha256:"):
            if current_name is None:
                print(f"BLOCKED: MALFORMED_LOCK — hash line with no preceding package: {raw!r}")
                sys.exit(1)
            locked[current_name][1] = line[len("--hash=sha256:"):]
            current_name = None
            continue
        if "==" not in line:
            print(f"BLOCKED: MALFORMED_LOCK — unrecognized line: {raw!r}")
            sys.exit(1)
        name, version = line.split("==", 1)
        if name in locked:
            print(f"BLOCKED: DUPLICATE_LOCK_ENTRY — '{name}' appears more than once in {lock_file}")
            sys.exit(1)
        locked[name] = [version, None]
        current_name = name
    return locked


def check(wheel_dir: Path, lock_file: Path) -> None:
    wheels = scan_wheels(wheel_dir)
    locked = _parse_lock(lock_file)

    errors = []
    for name, (_version, digest) in locked.items():
        if digest is None:
            errors.append(f"{name}: package line has no following --hash= line")
    for name in sorted(wheels):
        version, digest, whl = wheels[name]
        if name not in locked:
            errors.append(f"{name}: real wheel {whl.name} has no lock entry at all")
            continue
        locked_version, locked_digest = locked[name]
        if locked_version != version:
            errors.append(f"{name}: lock says version {locked_version!r}, real wheel is {version!r}")
        if locked_digest != digest:
            errors.append(f"{name}: lock hash does not match the real wheel's SHA-256")
    for name in locked:
        if name not in wheels:
            errors.append(f"{name}: lock entry has no matching wheel in {wheel_dir} (extra/stale entry)")

    if errors:
        print(f"BLOCKED: LOCK_MISMATCH — {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(
        f"PASS — {len(wheels)} package(s): every wheel appears exactly once in the lock, "
        "every version and SHA-256 is exact, no extra entries."
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)

    g = sub.add_parser("generate", help="Write a fresh lock file from a wheel directory")
    g.add_argument("wheel_dir", type=Path)
    g.add_argument("lock_file", type=Path)

    c = sub.add_parser("check", help="Verify an existing lock file against a wheel directory")
    c.add_argument("wheel_dir", type=Path)
    c.add_argument("lock_file", type=Path)

    args = p.parse_args()
    if args.mode == "generate":
        generate(args.wheel_dir, args.lock_file)
    else:
        check(args.wheel_dir, args.lock_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
