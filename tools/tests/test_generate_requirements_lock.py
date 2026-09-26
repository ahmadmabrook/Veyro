#!/usr/bin/env python3
"""
Unit test for tools/generate_requirements_lock.py (MOD-001, BUG-036 Tier 2).

Uses isolated tempfile.TemporaryDirectory fixtures with synthetic .whl
files (real bytes, real filenames, real computed hashes) — never the
owner's actual downloaded wheels. Run directly with
`python3 tools/tests/test_generate_requirements_lock.py` (no pytest
dependency) or with pytest if available.
"""
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generate_requirements_lock import check, generate, parse_wheel_filename, scan_wheels


def _make_wheel(directory: Path, filename: str, content: bytes) -> None:
    (directory / filename).write_bytes(content)


def test_parse_wheel_filename_5_segment():
    name, version = parse_wheel_filename(Path("pytest-9.1.1-py3-none-any.whl"))
    assert (name, version) == ("pytest", "9.1.1"), (name, version)


def test_parse_wheel_filename_platform_tag_with_underscores():
    name, version = parse_wheel_filename(Path("ruff-0.16.9-py3-none-macosx_11_0_arm64.whl"))
    assert (name, version) == ("ruff", "0.16.9"), (name, version)


def test_parse_wheel_filename_6_segment_build_tag():
    name, version = parse_wheel_filename(Path("mypy-2.3.1-1-cp313-cp313-macosx_11_0_arm64.whl"))
    assert (name, version) == ("mypy", "2.3.1"), (name, version)


def test_parse_wheel_filename_underscore_name_normalized():
    name, version = parse_wheel_filename(Path("typing_extensions-4.15.0-py3-none-any.whl"))
    assert (name, version) == ("typing-extensions", "4.15.0"), (name, version)


def test_generate_then_check_round_trip_passes():
    with tempfile.TemporaryDirectory() as tmp:
        wheel_dir = Path(tmp) / "wheels"
        wheel_dir.mkdir()
        _make_wheel(wheel_dir, "pytest-9.1.1-py3-none-any.whl", b"fake pytest wheel bytes")
        _make_wheel(wheel_dir, "ruff-0.16.9-py3-none-macosx_11_0_arm64.whl", b"fake ruff wheel bytes")

        lock_file = Path(tmp) / "requirements-dev.lock.txt"
        generate(wheel_dir, lock_file)  # exits process only on failure; success just returns

        # check() also only exits on failure — reaching past it is the PASS signal
        check(wheel_dir, lock_file)


def test_scan_wheels_hash_matches_real_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        wheel_dir = Path(tmp)
        content = b"deterministic test content"
        _make_wheel(wheel_dir, "mypy-2.3.1-py3-none-any.whl", content)
        wheels = scan_wheels(wheel_dir)
        assert wheels["mypy"][0] == "2.3.1"
        assert wheels["mypy"][1] == hashlib.sha256(content).hexdigest()


def test_tampered_lock_hash_fails_closed():
    """generate() a real lock, then hand-corrupt one hash — check() must
    reject it, not silently pass. This is run as a subprocess-free direct
    call check since check() calls sys.exit(1) on failure; capture that
    via SystemExit rather than letting the test process itself die."""
    with tempfile.TemporaryDirectory() as tmp:
        wheel_dir = Path(tmp) / "wheels"
        wheel_dir.mkdir()
        _make_wheel(wheel_dir, "pytest-9.1.1-py3-none-any.whl", b"real content")

        lock_file = Path(tmp) / "lock.txt"
        generate(wheel_dir, lock_file)

        tampered = lock_file.read_text().replace(
            hashlib.sha256(b"real content").hexdigest(), "0" * 64
        )
        lock_file.write_text(tampered)

        try:
            check(wheel_dir, lock_file)
            raise AssertionError("check() should have exited non-zero on a tampered hash")
        except SystemExit as e:
            assert e.code != 0, "tampered hash must fail closed, not exit 0"


def test_extra_lock_entry_with_no_wheel_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        wheel_dir = Path(tmp) / "wheels"
        wheel_dir.mkdir()
        _make_wheel(wheel_dir, "pytest-9.1.1-py3-none-any.whl", b"real content")

        lock_file = Path(tmp) / "lock.txt"
        generate(wheel_dir, lock_file)

        extra = lock_file.read_text() + "phantom-package==1.0.0 \\\n    --hash=sha256:" + ("a" * 64) + "\n"
        lock_file.write_text(extra)

        try:
            check(wheel_dir, lock_file)
            raise AssertionError("check() should have exited non-zero on an extra lock entry")
        except SystemExit as e:
            assert e.code != 0, "an extra lock entry with no matching wheel must fail closed"


def test_duplicate_package_name_in_wheel_dir_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        wheel_dir = Path(tmp)
        _make_wheel(wheel_dir, "pytest-9.1.1-py3-none-any.whl", b"content one")
        _make_wheel(wheel_dir, "pytest-9.1.2-py3-none-any.whl", b"content two")
        try:
            scan_wheels(wheel_dir)
            raise AssertionError("scan_wheels() should have exited non-zero on a duplicate package name")
        except SystemExit as e:
            assert e.code != 0, "an ambiguous duplicate package name must fail closed, never pick one silently"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok — {t.__name__}")
    print(f"PASS — all {len(tests)} tests passed.")
