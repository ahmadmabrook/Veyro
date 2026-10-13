#!/usr/bin/env python3
"""
ADR-005 Decision 2 Part 3 / MOD-001 `IMPLEMENTATION.md` §4 gate 7:
surface-profile activation.

TSD §24.1's six architecture gates live in `validate_architecture_gates.py`.
This is the 7th, ADR-005-added gate (Scenario Review round 1, P1-9), kept in
its own module so the dispatching file does not have to grow a new gate's
worth of scanning/matching logic inline. `validate_architecture_gates.py`
dispatches `--gate surface-profile` into `run_surface_profile_gate` below and
adapts its report into its own `GateReport` shape.

## What this gate checks

`module-capabilities.yaml`'s `repository_paths_surfaces` list is the sole
authority this gate consults for path/profile/state (ADR-005 Decision 2 Part
3: "the check reads that marker rather than an inferred mapping" — this
module invents no path/profile mapping of its own; it only interprets the
manifest's own rows). Every row is one of:

  * `profile: null`, `state: n/a` — a known-infrastructure/cross-cutting
    path (`.claude/**`, `knowledge/**`, `veyro-product-experience-design/**`,
    `contracts/**`, `tools/**`, `mobile/*.md`, `RELEASE_TRAIN.md`). Any file
    under one of these PASSes unconditionally.
  * a named §4.3 profile with `state: ACTIVATED` (currently Backend and
    Infra/SRE/CI only). Any file under one of these PASSes unconditionally.
  * a named §4.3 profile with `state: DEFERRED`. A file here PASSes only if
    it matches the closed build/toolchain/CI carve-out (below); otherwise it
    is denied `SURFACE_PROFILE_NOT_ACTIVATED`, citing the path and the
    deferred profile (plus its manifest marker, if any).

A file matching none of the manifest's rows at all — an entirely new
top-level surface, e.g. a hypothetical `analytics/` directory
(`SCN-MOD001-112`) — is denied `UNKNOWN_SURFACE`, the catch-all a
marker-keyed check has no row to consult for by construction.

Per `IMPLEMENTATION.md` §4 gate 7's own disclosed precedence rule, a known-
infrastructure/cross-cutting match takes precedence over a §4.3 glob match
on the same path; the two sets are disjoint in the current manifest, so this
is not presently exercised, but the matching order below (exempt, then
activated, then deferred) encodes it for a future manifest row that adds one.

## The build/toolchain/CI carve-out (ADR-005's own dividing line)

"build, toolchain, and CI configuration for a surface is Infra/SRE/CI-
profile work; the surface's own profile activates when the surface's own
source code appears." The recognised extension/filename set is closed, not
open-ended (Scenario Review round 12, P0-1 removed an earlier "etc."):
exactly `.gradle.kts`, `.gradle`, `.xcconfig`, `Package.swift`, `Podfile`,
`package.json`, `package-lock.json`, `gradle.properties`,
`settings.gradle.kts`, `gradle-wrapper.properties` (`SCN-MOD001-138`
positive, `SCN-MOD001-139` negative/boundary — the carve-out is
extension/filename-scoped, not surface-wide).

## Residual, disclosed rather than silently resolved

A loose top-level file with no directory nesting is outside this gate's
scope unless the manifest itself names it (`RELEASE_TRAIN.md`'s own
`profile: null` row, matched like any other exempt row, still applies
first). ADR-005 Decision 2 Part 3 binds this gate to §4.3's surface *path
globs* acquiring source files — "a surface path acquires its first source
file of that surface's file types" — not to arbitrary top-level repository
files that have no directory of their own and so cannot be a surface by
construction. An unmatched root file (e.g. `.gitignore`, a governing
baseline `.docx`, a scratch commit-message `.txt`) is therefore skipped,
not denied. This does not widen into an exemption for new surfaces: any
file inside a genuinely new, unlisted top-level *directory*
(`SCN-MOD001-112`'s `analytics/` case) still has a `/` in its repo-relative
path and is still denied `UNKNOWN_SURFACE` — only bare root files are
exempted, and only because a marker-keyed check has no row to consult for
a path that was never a candidate surface in the first place.

This tool never writes to anything it inspects.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import NamedTuple

PASS, FAIL, INCONCLUSIVE, ERROR = "PASS", "FAIL", "INCONCLUSIVE", "ERROR"
EXIT_CODES = {PASS: 0, FAIL: 1, INCONCLUSIVE: 2, ERROR: 2}

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DIR = REPO_ROOT
DEFAULT_CAPABILITIES_MANIFEST = (
    REPO_ROOT / "contracts" / "engineering" / "module-capabilities.yaml"
)

# ADR-005 Decision 2 Part 3's own dividing line, closed not open-ended
# (Scenario Review round 12, P0-1). Three are extension suffixes, the rest
# are exact filenames — kept as two separate closed sets rather than one, so
# neither can silently widen into the other.
_CARVEOUT_EXTENSIONS = (".gradle.kts", ".gradle", ".xcconfig")
_CARVEOUT_FILENAMES = frozenset({
    "Package.swift", "Podfile", "package.json", "package-lock.json",
    "gradle.properties", "settings.gradle.kts", "gradle-wrapper.properties",
})

_SURFACE_ROW_FIELD_RE = re.compile(r"^(\w+)\s*:\s*(.*)$")


class GateInputError(Exception):
    """Malformed/unusable manifest input — always ERROR, never PASS or FAIL."""


@dataclass(frozen=True)
class Violation:
    code: str
    subject: str
    detail: str


@dataclass
class GateReport:
    gate: str
    status: str
    violations: list[Violation] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def render(self) -> str:
        lines = [f"[{self.gate}] {self.status} — checked {len(self.checked)} subject(s)"]
        lines += [f"  {v.code}: {v.subject} — {v.detail}" for v in self.violations]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


class _SurfaceRow(NamedTuple):
    path: str
    profile: str | None  # None for a known-infrastructure/cross-cutting row
    marker: str | None


def _is_carveout_file(filename: str) -> bool:
    if filename in _CARVEOUT_FILENAMES:
        return True
    return any(filename.endswith(ext) for ext in _CARVEOUT_EXTENSIONS)


def _strip_inline_comment(value: str) -> str:
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def _extract_block(text: str, key: str) -> str:
    """The indented block of lines following a top-level `<key>:` in a YAML
    document — same shallow, regex-based scoping technique used throughout
    this project's other manifest validators (never a real YAML parser).
    Raises if the key is absent: the caller has nothing to consult then,
    which is an input problem, not a "no rows" result."""
    lines = text.splitlines()
    key_re = re.compile(rf"^(\s*){re.escape(key)}\s*:\s*(.*)$")
    for i, line in enumerate(lines):
        m = key_re.match(line)
        if not m:
            continue
        key_indent = len(m.group(1))
        block_lines: list[str] = []
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                block_lines.append(nxt)
                continue
            nxt_indent = len(nxt) - len(nxt.lstrip(" "))
            if nxt_indent <= key_indent:
                break
            block_lines.append(nxt)
        return "\n".join(block_lines)
    raise GateInputError(f"manifest has no top-level {key!r} key")


def _parse_surface_rows(
    manifest_text: str,
) -> tuple[list[_SurfaceRow], list[_SurfaceRow], list[_SurfaceRow]]:
    """Every `repository_paths_surfaces` list item, sorted into
    (exempt, activated, deferred) `_SurfaceRow` buckets. Fails closed
    (`GateInputError`) on any row that does not carry a well-formed
    `path`/`profile`/`state` triple, or whose `profile`/`state` pair is
    internally inconsistent (`profile: null` must pair with `state: n/a`
    and nothing else) — this gate does not guess what an ambiguous row
    means."""
    block = _extract_block(manifest_text, "repository_paths_surfaces")
    raw_rows: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in block.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            if current is not None:
                raw_rows.append(current)
            current = {}
            stripped = stripped[2:]
        if current is None:
            raise GateInputError(f"repository_paths_surfaces: stray line {raw_line!r}")
        m = _SURFACE_ROW_FIELD_RE.match(stripped)
        if not m:
            raise GateInputError(f"repository_paths_surfaces: malformed entry {raw_line!r}")
        current[m.group(1)] = _strip_inline_comment(m.group(2))
    if current is not None:
        raw_rows.append(current)
    if not raw_rows:
        raise GateInputError("repository_paths_surfaces: no rows found")

    exempt: list[_SurfaceRow] = []
    activated: list[_SurfaceRow] = []
    deferred: list[_SurfaceRow] = []
    for raw in raw_rows:
        path, profile, state, marker = raw.get("path"), raw.get("profile"), raw.get("state"), raw.get("marker")
        if not path or profile is None or state is None:
            raise GateInputError(f"repository_paths_surfaces: row missing path/profile/state: {raw!r}")
        is_null_profile = profile == "null"
        is_na_state = state == "n/a"
        if is_null_profile != is_na_state:
            raise GateInputError(
                f"repository_paths_surfaces: inconsistent profile/state for {path!r}: "
                f"profile={profile!r} state={state!r}")
        if is_null_profile:
            exempt.append(_SurfaceRow(path, None, marker))
        elif state == "ACTIVATED":
            activated.append(_SurfaceRow(path, profile, marker))
        elif state == "DEFERRED":
            deferred.append(_SurfaceRow(path, profile, marker))
        else:
            raise GateInputError(f"repository_paths_surfaces: unknown state {state!r} for {path!r}")
    return exempt, activated, deferred


def _pattern_matches(relpath: str, pattern: str) -> bool:
    """Matches one of this gate's three closed, known manifest-pattern
    shapes. Any other shape is refused (`GateInputError`) rather than
    silently interpreted — the same "closed, not open-ended" discipline
    `IMPLEMENTATION.md` §4 gate 7 applies to its own carve-out list."""
    if pattern.endswith("/**"):
        prefix = pattern[:-2]  # keep the trailing "/"
        return relpath.startswith(prefix)
    if "*" in pattern:
        dir_part, sep, name_pattern = pattern.rpartition("/")
        if not sep or "/" in name_pattern or "*" in dir_part:
            raise GateInputError(f"unsupported manifest glob shape: {pattern!r}")
        rel_dir, rel_sep, rel_name = relpath.rpartition("/")
        if not rel_sep or rel_dir != dir_part:
            return False
        return fnmatch.fnmatchcase(rel_name, name_pattern)
    return relpath == pattern


_PRUNED_DIR_NAMES = frozenset({".git", "__pycache__"})


def _git_candidate_relpaths(source_dir: Path) -> list[str] | None:
    """Tracked files plus untracked-but-not-ignored files under `source_dir`,
    as reported by Git itself, relative to `source_dir`. This is the gate's
    actual candidate-input boundary: a plain filesystem walk has no notion of
    `.gitignore` and will happily descend into a Git-ignored tree such as
    `backend/.venv/` (not a surface this gate has any business scanning, and
    one whose own interpreter symlinks previously made the gate ERROR
    outright). Returns `None`, never raises, when `source_dir` is not inside
    a Git work tree at all -- the ordinary case for this gate's own
    synthetic `tempfile.TemporaryDirectory` test fixtures, which must keep
    using the plain walk below unchanged."""
    try:
        probe = subprocess.run(
            ["git", "-C", str(source_dir), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None

    relpaths: set[str] = set()
    for extra_args in (["ls-files", "-z"], ["ls-files", "-z", "--others", "--exclude-standard"]):
        result = subprocess.run(
            ["git", "-C", str(source_dir), *extra_args],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise GateInputError(
                f"git {' '.join(extra_args)} failed under {source_dir}: {result.stderr.strip()}")
        relpaths.update(p for p in result.stdout.split("\0") if p)
    return sorted(relpaths)


def _walk_source_files(source_dir: Path) -> list[Path]:
    """Every candidate regular file under `source_dir`. When `source_dir` is
    inside a Git work tree, candidates are exactly Git's own tracked plus
    non-ignored-untracked view (`_git_candidate_relpaths`) -- Git-ignored
    trees such as `backend/.venv/` are never entered, matching
    `.gitignore`/`backend/.gitignore` rather than an independently
    maintained prune list. Otherwise (this gate's own synthetic
    `tempfile.TemporaryDirectory` test fixtures, which are never Git work
    trees), this falls back to a plain walk pruning only `.git` and
    `__pycache__` without descending into them -- unlike
    `validate_architecture_gates.py`'s own `_walk_module` (which blanket-
    prunes every dot-directory, correct for its own scan root under
    `backend/app/modules`), this fallback must NOT prune dot-directories
    generally: `.claude/**` (known-infrastructure) and `.github/workflows/**`
    (ACTIVATED Infra/SRE/CI) are both real, manifest-governed top-level
    dot-prefixed paths this gate has to be able to reach. Either path:
    any symlink among the candidates is ERROR, fail-closed."""
    candidate_relpaths = _git_candidate_relpaths(source_dir)
    if candidate_relpaths is not None:
        files: list[Path] = []
        for relpath in candidate_relpaths:
            entry = source_dir / relpath
            if entry.is_symlink():
                raise GateInputError(f"{entry}: symlinks are refused")
            if not entry.is_file():
                raise GateInputError(f"{entry}: not a regular file")
            files.append(entry)
        return files

    files = []
    stack = [source_dir]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if entry.is_symlink():
                raise GateInputError(f"{entry}: symlinks are refused")
            if entry.is_dir():
                if entry.name in _PRUNED_DIR_NAMES:
                    continue
                stack.append(entry)
            elif entry.is_file():
                files.append(entry)
            else:
                raise GateInputError(f"{entry}: not a regular file")
    return files


def run_surface_profile_gate(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    capabilities_manifest: Path = DEFAULT_CAPABILITIES_MANIFEST,
) -> GateReport:
    try:
        manifest_text = capabilities_manifest.read_text()
    except OSError as exc:
        return GateReport("surface-profile", ERROR, [Violation(
            "SURFACE_PROFILE_GATE_INPUT_INVALID", str(capabilities_manifest),
            f"could not read capabilities manifest ({type(exc).__name__})")])

    try:
        exempt, activated, deferred = _parse_surface_rows(manifest_text)
        source_files = _walk_source_files(source_dir)
    except GateInputError as exc:
        return GateReport("surface-profile", ERROR, [Violation(
            "SURFACE_PROFILE_GATE_INPUT_INVALID", str(source_dir), str(exc))])

    if not source_files:
        return GateReport("surface-profile", INCONCLUSIVE, [Violation(
            "SURFACE_PROFILE_GATE_VACUOUS", str(source_dir),
            "no files found under the scanned source directory — an empty scan is not evidence of compliance")])

    violations: list[Violation] = []
    checked: list[str] = []
    try:
        for file_path in sorted(source_files):
            relpath = file_path.relative_to(source_dir).as_posix()
            checked.append(relpath)

            if any(_pattern_matches(relpath, row.path) for row in exempt):
                continue
            if any(_pattern_matches(relpath, row.path) for row in activated):
                continue

            deferred_hit = next((row for row in deferred if _pattern_matches(relpath, row.path)), None)
            if deferred_hit is not None:
                if _is_carveout_file(file_path.name):
                    continue
                marker_clause = f", marker {deferred_hit.marker}" if deferred_hit.marker else ""
                violations.append(Violation(
                    "SURFACE_PROFILE_NOT_ACTIVATED", relpath,
                    f"profile '{deferred_hit.profile}' is DEFERRED for this path{marker_clause}"))
                continue

            if "/" not in relpath:
                # ADR-005 Decision 2 Part 3 path-scopes this gate to §4.3's
                # surface globs acquiring source files; a loose repo-root file
                # has no directory nesting and so is never a candidate surface
                # by construction. A manifest row naming it exactly (e.g.
                # RELEASE_TRAIN.md) already matched above via `exempt` --
                # anything else at root (.gitignore, governing baseline docx,
                # scratch commit-message txt, ...) is out of this gate's scope
                # rather than an unlisted surface.
                continue

            violations.append(Violation(
                "UNKNOWN_SURFACE", relpath,
                "matches no known-infrastructure path and no named §4.3 surface glob "
                "in module-capabilities.yaml's repository_paths_surfaces"))
    except GateInputError as exc:
        return GateReport("surface-profile", ERROR, [Violation(
            "SURFACE_PROFILE_GATE_INPUT_INVALID", str(capabilities_manifest), str(exc))])

    status = FAIL if violations else PASS
    return GateReport("surface-profile", status, violations, sorted(checked))
