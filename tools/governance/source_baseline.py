#!/usr/bin/env python3
"""Offline product-source binding. It is a CI/acceptance check, never a runner lifecycle gate."""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PREFIXES = ("Gym_OS_Master_Product_Blueprint", "Veyro_Technical_System_Design",
            "Veyro_Engineering_Implementation_Plan", "veyro-product-experience-design")
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*`([0-9a-f]{64})`\s*\|\s*$", re.M)
HEX = re.compile(r"^[0-9a-f]{64}$")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_hash(repo, name):
    rel = Path(name.rstrip("/"))
    if rel.is_absolute() or not rel.parts or any(p in (".", "..") for p in rel.parts):
        raise ValueError(f"unsafe source path: {name}")
    root = Path(repo) / rel
    if root.is_symlink() or not root.exists():
        raise ValueError(f"missing or symlink source: {name}")
    if root.is_file():
        return digest(root)
    if not root.is_dir():
        raise ValueError(f"source is neither file nor directory: {name}")
    files = []
    for base, dirs, names in os.walk(root):
        for item in (*dirs, *names):
            if (Path(base) / item).is_symlink():
                raise ValueError(f"symlink in source directory: {name}")
        files.extend(Path(base) / n for n in names if n != ".DS_Store")
    h = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix().encode()):
        relbytes = path.relative_to(root).as_posix().encode()
        h.update(len(relbytes).to_bytes(4, "big") + relbytes)
        size = path.stat().st_size
        h.update(size.to_bytes(8, "big"))
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def index_rows(repo):
    index = Path(repo) / "PROJECT_INDEX.md"
    if index.is_symlink() or not index.is_file():
        raise ValueError("PROJECT_INDEX.md missing or symlink")
    raw = index.read_bytes()
    rows = ROW.findall(raw.decode())
    if not all(any(name.startswith(prefix) for name, _ in rows) for prefix in PREFIXES):
        raise ValueError("PROJECT_INDEX.md lacks a required source row")
    return hashlib.sha256(raw).hexdigest(), rows


def load_pin(path):
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None
    if (not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("index_sha256"), str)
            or not HEX.fullmatch(data["index_sha256"]) or not isinstance(data.get("sources"), list)
            or not data["sources"]):
        raise ValueError("invalid pin shape")
    for row in data["sources"]:
        if (not isinstance(row, dict) or not isinstance(row.get("name"), str)
                or not isinstance(row.get("sha256"), str) or not HEX.fullmatch(row["sha256"])):
            raise ValueError("invalid source pin")
    return data


def verify(repo, pin_path):
    try:
        pin = load_pin(pin_path)
    except (OSError, ValueError, KeyError, TypeError) as e:
        return {"ok": False, "code": "PIN_INVALID", "reason": str(e)}
    if pin is None:
        return {"ok": False, "code": "NOT_PINNED", "reason": "source baseline not pinned"}
    try:
        index_sha, rows = index_rows(repo)
        if index_sha != pin["index_sha256"]:
            return {"ok": False, "code": "MISMATCH", "reason": "PROJECT_INDEX.md differs from pin"}
        expected = {row["name"]: row["sha256"] for row in pin["sources"]}
        if len(expected) != len(pin["sources"]) or expected != dict(rows):
            return {"ok": False, "code": "MISMATCH", "reason": "source row set differs from pin"}
        bad = [name for name, want in expected.items() if source_hash(repo, name) != want]
        return {"ok": not bad, "code": "MISMATCH" if bad else None, "reason": f"source mismatch: {bad}" if bad else None}
    except (OSError, ValueError, UnicodeError) as e:
        return {"ok": False, "code": "ERROR", "reason": str(e)}


def pin(repo, pin_path, confirmation):
    target = Path(pin_path)
    if target.exists():
        raise ValueError("baseline already pinned; no overwrite")
    if Path(repo).resolve() in target.resolve().parents:
        raise ValueError("pin must live outside the repository")
    index_sha, rows = index_rows(repo)
    if confirmation != index_sha:
        raise ValueError("--confirm-index-sha256 does not match PROJECT_INDEX.md")
    sources = []
    for name, want in rows:
        got = source_hash(repo, name)
        if got != want:
            raise ValueError(f"source {name} differs from PROJECT_INDEX.md")
        sources.append({"name": name, "sha256": got})
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"schema": 1, "pinned_at": datetime.now(timezone.utc).isoformat(),
                       "index_sha256": index_sha, "sources": sources, "repo": str(Path(repo).resolve())},
                      sort_keys=True, indent=1).encode()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "wb") as out:
        out.write(body)
        out.flush()
        os.fsync(out.fileno())
    return {"ok": True, "code": None, "sources": len(sources)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("verify", "pin"))
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--pin", required=True, type=Path)
    parser.add_argument("--confirm-index-sha256")
    args = parser.parse_args(argv)
    try:
        if args.action == "pin":
            if not args.confirm_index_sha256:
                raise ValueError("--confirm-index-sha256 is required")
            result = pin(args.repo, args.pin, args.confirm_index_sha256)
        else:
            result = verify(args.repo, args.pin)
    except (OSError, ValueError) as e:
        result = {"ok": False, "code": "PIN_REFUSED", "reason": str(e)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else (1 if args.action == "verify" else 2)


if __name__ == "__main__":
    sys.exit(main())
