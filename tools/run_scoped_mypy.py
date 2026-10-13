"""
Fixed-scope mypy runner for `backend/app` (MOD-001, GOV-01-R04; CAP-012 wrapper).

**This tool authorises nothing.** CAP-012 (`mypy` 2.3.1) is
`QUALIFIED — NOT APPROVED` in `knowledge/00-System/CAPABILITY_REGISTRY.md`: no
independent determination or `approved_by` exists, so no mypy result may be
relied on and no run through this file is a gate, scenario or assurance
result. It supplies the "unwritten/unqualified wrapper" the CAP-012 row lists
as a precondition, in reviewable form, and has been exercised only against
disposable synthetic trees outside the repository: the current self-contained
candidate ran locally on macOS CPython 3.14. Draft PR #6 ran the earlier
CAP-011-dependent bytes on Linux CPython 3.13; this revised file has not yet
run in CI. The drill is NOT a required CI typecheck and confers no capability
approval. This file imports nothing from CAP-011's `run_scoped_pytest`.

The caller supplies nothing. There is no path, flag or config argument; the one
invocation this file can ever start is the CAP-012 INTENDED shape, with cwd
`backend`:

    <backend/.venv/bin/python> -I -m mypy --config-file pyproject.toml \
        --cache-dir=/dev/null --no-color-output app

Everything below is checked before mypy starts (`plan()` raises `Denied`),
except the interpreter/mypy probes and the post-run checks, which `run()` makes:

  1. Scope. `backend`, `backend/app` and `backend/pyproject.toml` are walked
     component by component with no symlink allowed, and must canonicalise to
     themselves under the repository root. Any symlink inside `backend/app` is
     refused (mypy honours symlinked targets).
  2. Config. `[tool.mypy]` in `backend/pyproject.toml` must have exactly the
     key set {`python_version`, `strict`} with values `"3.13"` and `true`. Any
     other key — `plugins`, `mypy_path`, `files`, `exclude`, `follow_imports`,
     `ignore_errors`, an `overrides` table — is refused.
  3. Interpreter. `-I` isolates from `PYTHON*` variables, user site and the cwd.
     A probe (same cleared environment) requires the interpreter to be a venv
     and to be running isolated, and `mypy --version` to be the pinned release.
  4. Environment. The child gets only `PATH=/usr/bin:/bin` and a `HOME` and
     `TMPDIR` that are fresh disposable directories outside the repository,
     removed afterwards. An inherited `MYPYPATH`/`MYPY_*`/non-empty `PYTHONPATH`
     is refused outright rather than silently dropped.
  5. Cache. `--cache-dir=/dev/null`; no `.mypy_cache` may appear or change
     (an unchanged pre-existing one is tolerated).
  6. Result. rc 0 AND stdout is exactly `Success: no issues found in N source
     files` with N equal to the `.py` count counted here, with empty stderr.
     rc 1 is reported as type errors; every other outcome is a denial.

Source-tree rules that close the limits CAP-012 recorded: an empty tree (a
vacuous package exits 0) is refused; `.pyi` files (they shadow `.py`) and any
`.py` under a hidden/`site-packages`/`node_modules` directory (mypy skips them,
so N would diverge) are refused; and so are the comments/decorators that
silently hide real errors — `# type: ignore`, inline `# mypy:` config and
`no_type_check`. The tree and config are fingerprinted before and after the run.

Not proven, and not pretended to be: no plugin or `--install-types` flag is
ever passed, but mypy's own network/plugin behaviour is not sandboxed — the
absence of those flags and of a config that could enable them is the control.
Other soft-hiding constructs (`cast`, `Any`, stubs outside the tree reached by
imports) are not policed. The run is drilled on the macOS CPython 3.14 venv only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tokenize
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

if sys.version_info < (3, 11):  # tomllib; the system python3 on this host is 3.9
    raise SystemExit("DENY: run_scoped_mypy needs Python >= 3.11 (use backend/.venv)")
import tomllib  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_TYPE_ERRORS = 1
EXIT_DENIED = 2

EXPECTED_MYPY_VERSION_PREFIX = "mypy 2.3.1 "
EXPECTED_CONFIG = {"python_version": "3.13", "strict": True}
CHILD_PATH = "/usr/bin:/bin"
RUN_TIMEOUT_SECONDS = 900

# mypy skips these when crawling a directory, so a `.py` inside one would make
# the expected source count diverge from mypy's.
_SKIPPED_DIR_NAMES = {"site-packages", "node_modules"}
_HIDING_COMMENT = re.compile(r"type:\s*ignore|\bmypy\s*:")
_SUCCESS = re.compile(r"Success: no issues found in (\d+) source files?")


class Denied(Exception):
    """A fail-closed refusal. CAP-012-owned: this file imports nothing from CAP-011."""


def _canonical(root: Path, rel: str) -> Path:
    """Resolve `rel` under `root`, refusing a symlink in any component.

    Checked component by component on the way down, because `Path.resolve()`
    alone would quietly follow a symlink. The post-resolve equality is a second,
    independent statement that nothing was followed. Anything unexpected
    (empty/absolute/dot components, an unresolvable path) is a denial.
    """
    parts = rel.split("/")
    if rel.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise Denied(f"unsafe relative path in the fixed scope table: {rel!r}")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise Denied(f"symlink refused in the path to the scope: {rel} (at {part!r})")
    try:
        resolved = current.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Denied(f"{rel} cannot be resolved: {exc}")
    if resolved != current:
        raise Denied(f"{rel} does not canonicalise to itself ({resolved}): refusing")
    if root not in resolved.parents:
        raise Denied(f"{rel} resolves outside the repository root: {resolved}")
    return resolved


def _hash_file(digest: "hashlib._Hash", rel: str, data: bytes) -> None:
    digest.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())


def _check_source(path: Path, rel: str) -> bytes:
    """Return the file's bytes after refusing error-hiding comments/decorators."""
    data = path.read_bytes()
    try:
        for tok in tokenize.tokenize(io.BytesIO(data).readline):
            if tok.type == tokenize.COMMENT and _HIDING_COMMENT.search(tok.string):
                raise Denied(f"{rel}:{tok.start[0]}: comment can hide type errors: {tok.string!r}")
            if tok.type == tokenize.NAME and tok.string == "no_type_check":
                raise Denied(f"{rel}:{tok.start[0]}: no_type_check hides type errors")
    except (tokenize.TokenError, SyntaxError) as exc:
        raise Denied(f"{rel}: cannot tokenize, so error-hiding constructs cannot be ruled out: {exc}")
    return data


def scan_app(app: Path) -> tuple[int, str]:
    """Count the `.py` files mypy will check; refuse anything the count can't vouch for."""
    count = 0
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(app, followlinks=False):
        dirnames.sort()
        here = Path(dirpath)
        for name in dirnames:
            if (here / name).is_symlink():
                raise Denied(f"symlinked directory inside backend/app: {(here / name).relative_to(app)}")
        parts = here.relative_to(app).parts
        skipped = any(p.startswith(".") or p in _SKIPPED_DIR_NAMES or p == "__pycache__" for p in parts)
        for name in sorted(filenames):
            path = here / name
            rel = str(path.relative_to(app))
            if path.is_symlink():
                raise Denied(f"symlink inside backend/app: {rel}")
            if name.endswith(".pyi"):
                raise Denied(f"stub file inside backend/app (shadows its .py): {rel}")
            if not name.endswith(".py"):
                continue
            if skipped:
                raise Denied(f"{rel} sits in a directory mypy skips: the source count would diverge")
            if not path.is_file():
                raise Denied(f"{rel} is not a regular file")
            _hash_file(digest, rel, _check_source(path, rel))
            count += 1
    if count == 0:
        raise Denied("backend/app holds no .py file: an empty target exits 0 without checking anything")
    return count, digest.hexdigest()


def check_config(pyproject: Path) -> str:
    """Require `[tool.mypy]` to be exactly the expected two keys. Returns a content hash."""
    raw = pyproject.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise Denied(f"backend/pyproject.toml is not valid TOML: {exc}")
    section = data.get("tool", {}).get("mypy") if isinstance(data.get("tool"), dict) else None
    if not isinstance(section, dict):
        raise Denied("backend/pyproject.toml has no [tool.mypy] table")
    if set(section) != set(EXPECTED_CONFIG):
        raise Denied(
            f"[tool.mypy] keys are {sorted(section)}, expected exactly {sorted(EXPECTED_CONFIG)}: "
            f"any other key can widen, redirect or disable the check"
        )
    for key, want in EXPECTED_CONFIG.items():
        got = section[key]
        if type(got) is not type(want) or got != want:
            raise Denied(f"[tool.mypy] {key} = {got!r}, expected {want!r}")
    return hashlib.sha256(raw).hexdigest()


def ambient_denials(env: Mapping[str, str]) -> list[str]:
    denials = [
        f"{name} is set in the environment: an ambient mypy setting can redirect imports, "
        f"cache or config this wrapper never declared"
        for name in sorted(env)
        if name == "MYPYPATH" or name.startswith("MYPY_")
    ]
    if env.get("PYTHONPATH"):
        denials.append("PYTHONPATH is set: refused rather than inherited")
    return denials


def child_env(home: Path, tmp: Path) -> dict[str, str]:
    """The whole child environment: three variables, nothing inherited."""
    return {"PATH": CHILD_PATH, "HOME": str(home), "TMPDIR": str(tmp)}


@dataclass(frozen=True)
class Plan:
    """A canonicalised, inspectable invocation. Nothing here is a result."""

    root: Path
    cwd: Path
    target: Path
    config: Path
    python: Path
    expected_sources: int
    fingerprint: str

    def argv(self) -> list[str]:
        return [
            str(self.python),
            "-I",
            "-m",
            "mypy",
            "--config-file",
            "pyproject.toml",
            "--cache-dir=/dev/null",
            "--no-color-output",
            "app",
        ]

    def as_dict(self) -> dict:
        return {
            "tool": "tools/run_scoped_mypy.py",
            "cwd": str(self.cwd),
            "target": str(self.target),
            "config": str(self.config),
            "expected_source_files": self.expected_sources,
            "argv": self.argv(),
            "child_env_keys": ["HOME", "PATH", "TMPDIR"],
            "capability_status": "CAP-012 QUALIFIED - NOT APPROVED; no result here is a gate",
        }


def plan(
    repo_root: Path | None = None,
    python: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Plan:
    """Validate scope, config, tree and interpreter path. Starts no process."""
    root = (repo_root if repo_root is not None else REPO_ROOT).resolve()
    environ = env if env is not None else os.environ
    for denial in ambient_denials(environ):
        raise Denied(denial)
    cwd = _canonical(root, "backend")
    target = _canonical(root, "backend/app")
    if not target.is_dir():
        raise Denied("backend/app is missing or not a directory")
    config = _canonical(root, "backend/pyproject.toml")
    if not config.is_file():
        raise Denied("backend/pyproject.toml is missing")
    interpreter = python if python is not None else root / "backend" / ".venv" / "bin" / "python"
    if not interpreter.is_absolute() or not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise Denied(f"interpreter is not an absolute, executable file: {interpreter}")
    if not (interpreter.parent.parent / "pyvenv.cfg").is_file():
        raise Denied(f"{interpreter} is not laid out as a venv interpreter (no pyvenv.cfg)")
    config_hash = check_config(config)
    count, tree_hash = scan_app(target)
    return Plan(
        root=root,
        cwd=cwd,
        target=target,
        config=config,
        python=interpreter,
        expected_sources=count,
        fingerprint=f"{config_hash}:{tree_hash}",
    )


def classify_result(returncode: int, stdout: str, stderr: str, expected: int) -> tuple[int, str]:
    """Map a finished mypy run. Only an exact success line at rc 0 is a pass."""
    if returncode == 1:
        return EXIT_TYPE_ERRORS, "mypy reported type errors"
    if returncode != 0:
        return EXIT_DENIED, f"mypy exited {returncode}: not a usable result"
    if stderr.strip():
        return EXIT_DENIED, "mypy rc 0 but wrote to stderr: not an exact success"
    match = _SUCCESS.fullmatch(stdout.strip())
    if match is None:
        return EXIT_DENIED, "mypy rc 0 but output is not exactly the success line"
    reported = int(match.group(1))
    if reported != expected or match.group(0) != (
        f"Success: no issues found in {expected} source file" + ("" if expected == 1 else "s")
    ):
        return EXIT_DENIED, f"mypy checked {reported} source files, expected exactly {expected}"
    return EXIT_OK, f"no issues found in exactly {expected} source files"


def _probe(current: Plan, env: Mapping[str, str]) -> None:
    """Prove the interpreter is an isolated venv and mypy is the pinned release."""
    code = "import sys;print(int(sys.prefix != sys.base_prefix), sys.flags.isolated)"
    kwargs = {"cwd": current.cwd, "env": dict(env), "capture_output": True, "text": True,
              "check": False, "timeout": 60}
    venv = subprocess.run([str(current.python), "-I", "-c", code], **kwargs)
    if venv.returncode != 0 or venv.stdout.split() != ["1", "1"]:
        raise Denied(f"interpreter is not an isolated venv python (rc={venv.returncode}, {venv.stdout!r})")
    version = subprocess.run([str(current.python), "-I", "-m", "mypy", "--version"], **kwargs)
    reported = version.stdout.strip() + " "
    if version.returncode != 0 or not reported.startswith(EXPECTED_MYPY_VERSION_PREFIX):
        raise Denied(f"mypy reported {version.stdout.strip()!r} (rc={version.returncode}), "
                     f"expected {EXPECTED_MYPY_VERSION_PREFIX.strip()!r}: not the CAP-012 pin")


def _cache_state(directory: Path) -> tuple[object, ...] | None:
    """Stat-only snapshot of a `.mypy_cache` (None if absent); never follows symlinks."""
    try:
        top = os.lstat(directory)
    except FileNotFoundError:
        return None
    entries: list[tuple[object, ...]] = [("", top.st_mode, top.st_size, top.st_mtime_ns, top.st_ctime_ns)]
    if stat.S_ISDIR(top.st_mode):
        for here, dirs, files in os.walk(directory):
            for name in dirs + files:
                path = Path(here, name)
                info = os.lstat(path)
                entries.append((str(path.relative_to(directory)), info.st_mode, info.st_size,
                                info.st_mtime_ns, info.st_ctime_ns))
    return tuple(sorted(entries, key=repr))


def _cache_states(current: Plan) -> dict[Path, tuple[object, ...] | None]:
    return {d: _cache_state(d) for d in (current.cwd / ".mypy_cache", current.root / ".mypy_cache")}


def run(repo_root: Path | None = None, python: Path | None = None) -> int:
    """Validate, probe, run the one allowlisted command, check the result."""
    current = plan(repo_root, python)
    print(json.dumps(current.as_dict(), indent=2, sort_keys=True), flush=True)
    sandbox = Path(tempfile.mkdtemp(prefix="veyro-mypy-")).resolve()
    try:
        if current.root in sandbox.parents:
            raise Denied(f"disposable HOME/TMPDIR landed inside the repository: {sandbox}")
        home, tmp = sandbox / "home", sandbox / "tmp"
        home.mkdir()
        tmp.mkdir()
        environment = child_env(home, tmp)
        caches_before = _cache_states(current)
        _probe(current, environment)
        try:
            result = subprocess.run(
                current.argv(), cwd=current.cwd, env=environment, capture_output=True,
                text=True, errors="replace", check=False, timeout=RUN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise Denied(f"mypy exceeded {RUN_TIMEOUT_SECONDS}s")
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if _cache_states(current) != caches_before:
            raise Denied("a .mypy_cache was created or modified: the cache was not disabled")
        if plan(repo_root, python).fingerprint != current.fingerprint:
            raise Denied("config or source tree changed during the run")
        code, label = classify_result(
            result.returncode, result.stdout, result.stderr, current.expected_sources
        )
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    print(f"run_scoped_mypy: rc={result.returncode} — {label}", flush=True)
    if code == EXIT_DENIED:
        raise Denied(label)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--plan",
        action="store_true",
        help="validate and print the invocation without running mypy",
    )
    args = parser.parse_args(argv)
    try:
        if args.plan:
            print(json.dumps(plan().as_dict(), indent=2, sort_keys=True))
            return EXIT_OK
        return run()
    except Denied as exc:
        print(f"DENY: {exc}", file=sys.stderr)
        return EXIT_DENIED


if __name__ == "__main__":
    raise SystemExit(main())
