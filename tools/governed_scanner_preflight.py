"""
Governed real-tree scanner preflight and invocation wrapper (MOD-001, M1-C-06).

**This tool does not authorise anything.** It exists to make the *intended*
Veyro real-tree target sets for CAP-009 (`gitleaks` 8.30.1) and CAP-010 (Ruff
0.16.9 `S`) reviewable, and to keep the real-tree execution path provably
fail-closed until a separately recorded qualified scope approval and a reviewed
commit/workflow boundary both exist.

Why it exists — the two named mandatory criteria it is written against
(`knowledge/03-Modules/MOD-001/evidence/security/
M1-C-06-CAP-REAL-SCOPE-EXTENSION-DETERMINATION-2026-10-09.md` §10):

  * **C09-X** — "a stated and executed governed invocation whose target is a
    Veyro path"; its five required properties are a committed/reviewed wrapper
    carrying the fail-closed pre-checks as code, an explicitly enumerated Veyro
    target set, allowlist non-vacuity, evidence for the mode the gate actually
    uses, and install-time digest verification on every run.
  * **C10-X** — "a stated governed `S` target set over Veyro paths, executed
    through a committed wrapper"; its required properties are the enumerated
    target set, count-based non-vacuity (exact expected `.py` count, not
    "≥1 file"), a committed/reviewed wrapper and workflow, the `S` capability
    limits carried in the registry row, and advisory-before-gate sequencing.

This file supplies the *stated and reviewable* half of both: the enumeration,
the manifest binding, the supply-chain check, the governed argv, the exit
classification, the redaction, and the authorisation predicate. `invoke` /
`scan` is the real-tree invocation path those pieces compose into — written so
it can be **reviewed before** a scope grant exists and can **only** execute
after one. It supplies no way to execute either scanner against a Veyro path
today: `_require_scan_allowed` is the single choke point for every real-tree
invocation, and it refuses while any blocker in `authorisation_blockers`
stands. On this revision every blocker stands, so `scan` exits 3.

Why a vacuous or partial target is treated as the same class of risk as an
unauthorised one: a scanner that reports "0 findings" over a target set that
was silently truncated (an allowlisted path species, a partial `.py` set, a
directory walk that missed gitignored files) produces a false clean report,
which is worse than no report. Hence the exact manifest drift check, the
count-based `--show-files` non-vacuity pre-check, the allowlist-vacuity
refusal, and `assert_clean_committed_checkout` — which is what stops
`gitleaks dir`, a *directory* walker, from quietly examining untracked and
ignored bytes that the reviewed manifest never enumerated.

Non-self-authorising by construction. There is no `--force`, no
`--allow-real-tree`, no environment override and no marker file this
implementation can create to enable a real-tree scan. The blockers are
(a) a grant token inside the CAP registry row *and* inside a manifest-named
independent determination (both governed documents requiring a named Opus
`approved_by`), (b) this wrapper, its manifest and its workflow each being
git-tracked **and** byte-identical to HEAD — i.e. committed and reviewed, per
`.claude/rules/infra/iac.md` control 1 — and (c) the cryptographic artifact and
target-set checks below. See the residuals section of the evidence record: (a)
is document text, not a cryptographic control.

Why the gitleaks target is a materialized snapshot rather than the checkout
itself. `gitleaks dir` walks a *directory*, and the directory the reviewed bytes
live in is a Git checkout — the candidate workflow has to fetch one, because Git
is what proves the tree is the exact pushed commit. A checkout contains `.git`,
i.e. Git object and pack bytes, which is history: a surface CAP-009 records as
NOT approved and which `run_gitleaks_governed` refuses outright. The two
requirements are therefore satisfied by two different directories, not by
relaxing either: `materialize_tracked_snapshot` copies exactly the enumerated
committed blobs out of the checkout into a directory holding no Git object at
all, and that is what the scanner is pointed at. Nothing passes Git objects or
history to either scanner anywhere in this module.

Scope honesty. Executing either scanner against a Veyro file, the Git index,
Git history, or a copy of those files is outside CAP-009/CAP-010's APPROVED
(BOUNDED) scope and is not performed by this tool. A materialized snapshot is
such a copy, so it is governed as one: its destination is registered in
`_VEYRO_DERIVED_TARGETS` and `_require_scan_allowed` treats it exactly as it
treats a path inside the repository. Copying reviewed bytes outside the
repository cannot turn a Veyro scan into an approved synthetic one. Synthetic
targets that are not derived from Veyro bytes remain in scope and are what the
tests exercise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "tools" / "governed_scanner_targets.json"
REGISTRY_PATH = REPO_ROOT / "knowledge" / "00-System" / "CAPABILITY_REGISTRY.md"
SELF_REL = "tools/governed_scanner_preflight.py"
MANIFEST_REL = "tools/governed_scanner_targets.json"

# Exit codes. Distinct on purpose: a refusal must never be confused with
# "clean", and an authorisation block must never be confused with either.
EXIT_OK = 0
EXIT_FINDINGS = 1  # gate mode only; advisory mode reports findings at EXIT_OK
EXIT_REFUSED = 2  # precondition / supply-chain / drift refusal, or tool error
EXIT_BLOCKED = 3  # real-tree scan not authorised

# --- Supply-chain pins -------------------------------------------------------
# Copied from CAPABILITY_REGISTRY.md CAP-009/CAP-010 `content_hash` cells. The
# gitleaks release is mutable (`immutable: false`), so a recorded pin is not
# enforcement: the digest is re-verified on every invocation, never once.
GITLEAKS_VERSION = "8.30.1"
RUFF_VERSION = "ruff 0.16.9"

# Recorded *contained-binary* identities, not real-tree scan grants. The Linux
# digest was derived from the archive pinned below; CAP-009/010 scope still
# requires a separate qualified determination and the authorisation predicate.
GITLEAKS_ELIGIBLE_BINARY_SHA256 = frozenset(
    {
        "ba52fb1bfabbcde42f032afad3d6e0b19dff8ed105229a16e7caa338bbc0e84f",  # darwin arm64
        "88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509",  # linux x64
    }
)
# Archive digests, for an install-time verify-then-extract step (CI).
GITLEAKS_ELIGIBLE_ARCHIVE_SHA256 = frozenset(
    {
        "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",  # linux x64
        "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",  # darwin arm64
    }
)
# Named ineligible, so its rejection carries a specific reason rather than
# landing in the generic "unknown digest" branch: Homebrew is definitively not
# the upstream artifact and "is ineligible for every scope".
GITLEAKS_INELIGIBLE_BINARY_SHA256 = {
    "052d18829513f92eb683b63cd15b34d845f9a7adec761fe26cd462eb3c771422": (
        "Homebrew gitleaks — definitively not the upstream artifact; "
        "ineligible for every CAP-009 scope"
    )
}
RUFF_ELIGIBLE_BINARY_SHA256 = frozenset(
    {"8b799e53434b026a3e80aef658c06c3c98f9fb4cfc4eae379a16313936509e57"}  # macOS arm64
)
RUFF_ELIGIBLE_WHEEL_SHA256 = frozenset(
    {"a21713e629d3e5bdb2f5c2def1cc7f04f47fa8e1a7eb0571b4a28e1da64bc728"}  # linux x64
)

GITLEAKS_LEAK_EXIT = 42  # non-default: upstream's default 1 conflates leak/error
RUFF_CONFIGS = ("ruff.toml", "backend/pyproject.toml")

# The one config the governed real-tree `S` invocation passes via `--config`.
# Pinned by digest because CAP-010's scope cell pins it by digest: a changed
# config (adding `select`, `extend`, plugins, `exclude`, `per-file-ignores`) is
# a stage-9 material change, so an unpinned config would silently re-scope the
# run. Verified on every invocation, never once.
RUFF_CONFIG_REL = "ruff.toml"
RUFF_CONFIG_SHA256 = "81c6492e759cb6a3a622e29d7996de6fb8f590190110b36ad993bf2b534c9743"

# How many offending paths a checkout refusal names. The walk short-circuits at
# this many so a refusal stays cheap on a tree with a populated venv/cache.
UNENUMERATED_SAMPLE_CAP = 20

# The git-free directory a gitleaks `dir` run is pointed at, created under the
# work directory (which is always outside the repository). See
# `materialize_tracked_snapshot` for why the scanned directory cannot be the
# checkout itself.
SNAPSHOT_DIRNAME = "committed-snapshot"

GRANT_TOKENS = {
    "gitleaks": ("CAP-009", "GRANT-REAL-TREE-DIR-SCAN: CAP-009"),
    "ruff": ("CAP-010", "GRANT-REAL-TREE-S-SCAN: CAP-010"),
}

# Path species treated as excluded by the *shipped default* gitleaks global
# allowlist. Observed (pinned upstream 8.30.1, synthetic probe, evidence
# `M1-C-06-C09-ALLOWLIST-NONVACUITY-2026-10-09.md`): `node_modules/`, a venv
# `lib/pythonX.Y/site-packages` tree, `yarn.lock`, `poetry.lock`, `.docx` and
# `.png` are skipped; `vendor/`, `*.dist-info/` and `requirements.lock.txt` are
# detected, so they are NOT listed here. The probe was not exhaustive. Every
# other entry below (`.git`, `.mypy_cache`, `.venv`/`venv` as bare segments,
# `Pipfile.lock`, `package-lock.json`, `gitleaks.toml`, the remaining suffixes)
# was recorded from the second determination §5.2 and is UNTESTED: it is kept
# only so that an untested species is not silently counted as examined (it can
# only make the vacuity refusal fire more readily), and is not a claim that the
# species is excluded or covered. The declared out-of-coverage set is a lower
# bound for observed species only.
ALLOWLIST_EXCLUDED_DIR_SEGMENTS = (
    ".git",
    ".mypy_cache",
    ".venv",
    "node_modules",
    "site-packages",
    "venv",
)
ALLOWLIST_EXCLUDED_NAMES = (
    "Pipfile.lock",
    "gitleaks.toml",
    "package-lock.json",
    "poetry.lock",
    "yarn.lock",
)
ALLOWLIST_EXCLUDED_SUFFIXES = (
    ".bmp",
    ".docx",
    ".eot",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".pdf",
    ".png",
    ".so",
    ".svg",
    ".tar",
    ".ttf",
    ".whl",
    ".woff",
    ".woff2",
    ".zip",
)


class GovernedScanRefused(Exception):
    """Fail-closed refusal of a precondition the scanner itself cannot enforce."""


class RealScanBlocked(Exception):
    """A Veyro-path invocation was attempted while authorisation blockers stand."""

    def __init__(self, scanner: str, blockers: list[str]) -> None:
        self.scanner = scanner
        self.blockers = blockers
        super().__init__(f"real-tree {scanner} scan blocked: " + "; ".join(blockers))


# --- Target-set enumeration --------------------------------------------------


@dataclass(frozen=True)
class TargetSet:
    """The enumerated Veyro target set, derived only from the Git index."""

    head_commit: str
    tracked: tuple[str, ...]
    python_targets: tuple[str, ...]
    allowlist_excluded: tuple[str, ...]
    symlink_violations: tuple[str, ...]

    @property
    def tracked_sha256(self) -> str:
        return _list_digest(self.tracked)

    @property
    def python_sha256(self) -> str:
        return _list_digest(self.python_targets)

    def as_dict(self) -> dict:
        return {
            "head_commit": self.head_commit,
            "tracked_count": len(self.tracked),
            "tracked_sha256": self.tracked_sha256,
            "python_target_count": len(self.python_targets),
            "python_sha256": self.python_sha256,
            "tracked": list(self.tracked),
            "python_targets": list(self.python_targets),
            "declared_allowlist_excluded": list(self.allowlist_excluded),
            "declared_allowlist_excluded_count": len(self.allowlist_excluded),
            "symlink_violations": list(self.symlink_violations),
        }


def _list_digest(paths: tuple[str, ...]) -> str:
    return hashlib.sha256(("\n".join(paths) + "\n").encode()).hexdigest()


def is_allowlist_excluded(rel_path: str) -> bool:
    """True if the default global allowlist is observed or recorded (see above) as excluding this path."""
    parts = rel_path.split("/")
    if any(segment in ALLOWLIST_EXCLUDED_DIR_SEGMENTS for segment in parts[:-1]):
        return True
    name = parts[-1]
    return name in ALLOWLIST_EXCLUDED_NAMES or name.endswith(ALLOWLIST_EXCLUDED_SUFFIXES)


def _staged_entries(repo_root: Path) -> tuple[tuple[str, str, str], ...]:
    """`(mode, blob_oid, rel_path)` for every path in the Git index.

    The blob id is carried because it is the only thing that can prove a
    working-tree byte is the committed byte (`materialize_tracked_snapshot`);
    the mode is what identifies an index symlink.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    entries: list[tuple[str, str, str]] = []
    for entry in listing.stdout.split("\0"):
        if not entry.strip():
            continue
        meta, rel = entry.split("\t", 1)
        mode, oid, _stage = meta.split(" ", 2)
        entries.append((mode, oid, rel))
    return tuple(entries)


def enumerate_targets(repo_root: Path | None = None) -> TargetSet:
    """Enumerate the intended target set from the Git index (no scanner runs).

    Symlink handling is a refusal input, not a filter: an index symlink, an
    on-disk symlink, or a tracked path whose resolved location escapes the
    repository is recorded as a violation and refused by `assert_scannable`.
    """
    repo_root = repo_root if repo_root is not None else REPO_ROOT
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    tracked: list[str] = []
    symlinks: list[str] = []
    root = repo_root.resolve()
    for mode, _oid, rel in _staged_entries(repo_root):
        tracked.append(rel)
        on_disk = repo_root / rel
        try:
            escapes = root not in on_disk.resolve().parents
        except OSError:  # unreadable/looping link — treat as unsafe, never as fine
            escapes = True
        if mode == "120000" or on_disk.is_symlink() or escapes:
            symlinks.append(rel)

    tracked_sorted = tuple(sorted(tracked))
    return TargetSet(
        head_commit=head,
        tracked=tracked_sorted,
        python_targets=tuple(p for p in tracked_sorted if p.endswith(".py")),
        allowlist_excluded=tuple(p for p in tracked_sorted if is_allowlist_excluded(p)),
        symlink_violations=tuple(sorted(symlinks)),
    )


def verify_against_manifest(live: TargetSet, manifest: dict) -> None:
    """Refuse on any drift from the reviewed target set — missing or extra."""
    for key, live_paths in (("tracked", live.tracked), ("python_targets", live.python_targets)):
        reviewed = set(manifest.get(key) or ())
        if not reviewed:
            raise GovernedScanRefused(f"manifest records no reviewed '{key}' set")
        missing = sorted(reviewed - set(live_paths))
        extra = sorted(set(live_paths) - reviewed)
        if missing or extra:
            raise GovernedScanRefused(
                f"{key} drifted from the reviewed set: "
                f"{len(missing)} missing {missing[:5]}, {len(extra)} extra {extra[:5]}"
            )
    expected = manifest.get("python_target_count")
    if expected != len(live.python_targets):
        raise GovernedScanRefused(
            f"reviewed python_target_count {expected} != live {len(live.python_targets)}"
        )
    if manifest.get("tracked_sha256") != live.tracked_sha256:
        raise GovernedScanRefused("tracked-set digest differs from the reviewed manifest")
    if manifest.get("python_sha256") != live.python_sha256:
        raise GovernedScanRefused("python-target digest differs from the reviewed manifest")


def assert_scannable(live: TargetSet, scanner: str) -> None:
    """Target-side fail-closed checks that hold regardless of authorisation."""
    if live.symlink_violations:
        raise GovernedScanRefused(
            f"unsafe symlink(s) in the target set: {list(live.symlink_violations)[:5]}"
        )
    if not live.tracked:
        raise GovernedScanRefused("empty target set: vacuous scan")
    if scanner == "gitleaks":
        examined = [p for p in live.tracked if not is_allowlist_excluded(p)]
        if not examined:
            raise GovernedScanRefused(
                "allowlist vacuity: every target path is in the recorded default "
                "global-allowlist exclusion set, so a 0-findings result would be "
                "produced by exclusion rather than by examination"
            )
    if scanner == "ruff" and not live.python_targets:
        raise GovernedScanRefused("no .py target: vacuous S scan")


def _on_disk_files(repo_root: Path, tracked: frozenset[str]) -> tuple[list[str], bool]:
    """Relative paths physically present under `repo_root`, excluding `.git/`.

    Deliberately ignores `.gitignore`: whether `gitleaks dir` honours ignore
    files in 8.30.1 is UNTESTED here, so the conservative set is everything on
    disk, which is the set the scanner could actually walk. Returns the
    unenumerated sample and whether it was truncated.
    """
    extra: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        here = Path(dirpath)
        if here == repo_root:
            dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            rel = str((here / name).relative_to(repo_root))
            if rel not in tracked:
                extra.append(rel)
                if len(extra) >= UNENUMERATED_SAMPLE_CAP:
                    return sorted(extra), True
    return sorted(extra), False


def assert_clean_committed_checkout(live: TargetSet, repo_root: Path | None = None) -> None:
    """Require the on-disk tree to be exactly the enumerated committed bytes.

    Two independent reasons this is a precondition of a real-tree scan, not a
    nicety:

      * `gitleaks dir` walks a **directory**, not the Git index. Without this
        check it would silently examine every untracked, ignored, generated and
        vendored file under the target — files the reviewed manifest never
        enumerated and no reviewer ever saw — while the report's target-set
        digests would still read as the reviewed set.
      * A tracked file modified in the working tree is not the reviewed blob.
        Scanning it (either scanner) produces a result about unreviewed bytes,
        so this also binds Ruff's explicit-file targets, which cannot pick up
        an unenumerated path but can pick up an unenumerated *version* of one.
    """
    repo_root = repo_root if repo_root is not None else REPO_ROOT
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if dirty:
        raise GovernedScanRefused(
            f"working tree is not a clean committed checkout: {len(dirty)} modified/"
            f"untracked entr{'y' if len(dirty) == 1 else 'ies'} {dirty[:5]}"
        )
    tracked = frozenset(live.tracked)
    absent = sorted(p for p in live.tracked if not (repo_root / p).is_file())
    if absent:
        raise GovernedScanRefused(
            f"{len(absent)} enumerated target(s) absent from disk: {absent[:5]}"
        )
    extra, truncated = _on_disk_files(repo_root, tracked)
    if extra:
        raise GovernedScanRefused(
            f"{len(extra)}{'+' if truncated else ''} on-disk file(s) are not in the "
            f"enumerated target set and would be scanned unreviewed: {extra[:5]}"
        )


# --- Git-free materialization of the committed target set --------------------
#
# Destinations materialized *from* Veyro committed bytes. A copy of reviewed
# Veyro bytes is still a Veyro scan, so registering the destination here is what
# stops `_require_scan_allowed` from reading a snapshot that sits outside the
# repository as an ordinary in-scope synthetic target. Append-only within a
# process, and consulted in one direction only: it can add a refusal, never
# remove one, so nothing here can widen scope.
_VEYRO_DERIVED_TARGETS: set[Path] = set()


def _is_veyro_derived(resolved: Path) -> bool:
    """True if `resolved` is, or is inside, a snapshot of Veyro committed bytes."""
    return any(
        resolved == root or root in resolved.parents for root in _VEYRO_DERIVED_TARGETS
    )


def _blob_oid(data: bytes) -> str:
    """The Git blob object id of `data` (sha1 object format).

    Not used as a security hash — it is used because it is the identifier the
    Git index records, so it is the only value a copied byte string can be
    compared against to show it is the *committed* byte string. A repository in
    sha256 object format records 64-hex ids, which will not compare equal here,
    so such a repository refuses rather than being silently accepted.
    """
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _discard_snapshot(dest: Path) -> str | None:
    """Delete a materialized snapshot. Returns None only if nothing survives.

    A copy of reviewed Veyro bytes must not outlive the attempt that made it,
    whether that attempt succeeded, refused part way through its copy loop, or
    died on an OS error. `shutil.rmtree(ignore_errors=True)` alone cannot be
    trusted to answer that question — it reports nothing — so removal is
    followed by an independent existence check, and whatever is still on disk is
    described rather than assumed absent. The caller must treat a non-None
    return as a refusal: `retained_after_run: false` is a claim about verified
    cleanup, never a default.
    """
    shutil.rmtree(dest, ignore_errors=True)
    if not dest.exists():
        return None
    try:
        survivors = sorted(str(p.relative_to(dest)) for p in dest.rglob("*"))
    except OSError as exc:  # unreadable residue is still residue
        return f"{dest} still exists and could not be enumerated: {exc}"
    return (
        f"{dest} still exists after cleanup, holding {len(survivors)} entr(ies) "
        f"{survivors[:5]}"
    )


def materialize_tracked_snapshot(
    live: TargetSet, repo_root: Path | None = None, work: Path | None = None
) -> tuple[Path, str]:
    """Copy exactly the enumerated committed bytes into a git-free directory.

    Why this exists. `gitleaks dir` walks a *directory*, and the directory the
    reviewed bytes live in is a Git checkout — the candidate workflow fetches
    one because Git is what proves the tree is the exact pushed commit. A
    checkout contains `.git`, whose object and pack bytes are history, which
    CAP-009 records as NOT approved and which `run_gitleaks_governed` refuses.
    So the reviewed-bytes directory and the scannable directory cannot be the
    same directory, and the resolution is a second directory rather than a
    relaxed refusal: exactly the enumerated committed blobs, nothing else, and
    no Git object at all.

    What makes it exact rather than approximately exact. Every file's bytes are
    hashed into their Git blob id and compared against the index entry for that
    path. Working-tree bytes that are not the committed blob — a smudge/clean
    filter, an end-of-line conversion, a race against an editor — refuse here
    instead of being scanned as though they were the reviewed bytes. That is
    `assert_clean_committed_checkout`'s guarantee restated over content instead
    of over the path set, and it is checked independently rather than inferred
    from it.

    What it is not. It is not a scope widening and not a route around the
    source-repository authorisation choke point: the destination is registered
    in `_VEYRO_DERIVED_TARGETS` before a single byte is written, so every
    `_require_scan_allowed` call that sees this target (or anything under it)
    demands the same cleared blockers a path inside the repository would. There
    is no caller-supplied flag that changes that.

    What a failure leaves behind: nothing. Every refusal and every unexpected
    exception raised after the first byte could have been written removes the
    destination before propagating, because a refusal that leaves half a copy of
    reviewed bytes outside the repository is not fail-closed. If that removal
    cannot be completed, the refusal names the path still on disk.

    Returns the destination and a content digest over `path\\0sha256(bytes)`
    lines, so the evidence record can state *which* bytes were materialized
    rather than only how many.
    """
    repo_root = (repo_root if repo_root is not None else REPO_ROOT).resolve()
    work = _resolve_work_dir(work)
    dest = work / SNAPSHOT_DIRNAME
    if dest == repo_root or repo_root in dest.parents:
        raise GovernedScanRefused(
            "snapshot destination is inside the source repository (it would dirty the "
            "reviewed checkout and become an unenumerated target of its own)"
        )
    if dest.exists():
        raise GovernedScanRefused(
            f"snapshot destination already exists: {dest} — a reused destination could "
            f"leave bytes from an earlier run inside the scanned target"
        )
    if live.symlink_violations:
        raise GovernedScanRefused(
            f"unsafe symlink(s) in the target set: {list(live.symlink_violations)[:5]}"
        )
    # Registered before the first write, so even a partially-written snapshot is
    # already governed as Veyro-derived.
    _VEYRO_DERIVED_TARGETS.add(dest)

    # Everything that can write a byte runs inside this guard. A refusal raised
    # from the copy loop — a later path's blob mismatch, an unsafe component, an
    # OS error — happens before any caller's `finally` could be established, so
    # cleanup is this function's own obligation and not the caller's: partial
    # copies of reviewed bytes must not survive a fail-closed refusal. Only the
    # destination this call created is removed; the pre-existing-destination
    # refusal above runs before this guard, so a caller's earlier snapshot is
    # never touched.
    try:
        oid_by_path = {rel: oid for _mode, oid, rel in _staged_entries(repo_root)}
        if set(oid_by_path) != set(live.tracked):
            drifted = sorted(set(oid_by_path) ^ set(live.tracked))
            raise GovernedScanRefused(
                f"the Git index changed between enumeration and materialization: "
                f"{len(drifted)} path(s) {drifted[:5]}"
            )
        digest = hashlib.sha256()
        for rel in live.tracked:
            if any(part in ("", ".", "..", ".git") for part in rel.split("/")):
                raise GovernedScanRefused(f"unsafe enumerated path refused: {rel!r}")
            source = repo_root / rel
            if source.is_symlink() or not source.is_file():
                raise GovernedScanRefused(
                    f"enumerated target is not a regular file: {rel}"
                )
            data = source.read_bytes()
            oid = _blob_oid(data)
            if oid != oid_by_path[rel]:
                raise GovernedScanRefused(
                    f"{rel} working-tree bytes hash to blob {oid}, not the indexed "
                    f"{oid_by_path[rel]}: these are not the reviewed committed bytes"
                )
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            digest.update(f"{rel}\0{hashlib.sha256(data).hexdigest()}\n".encode())

        present = sorted(
            str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()
        )
        if present != sorted(live.tracked):
            raise GovernedScanRefused(
                f"materialized snapshot holds {len(present)} file(s), not the "
                f"{len(live.tracked)} enumerated target(s)"
            )
        offenders = [
            str(p.relative_to(dest))
            for p in dest.rglob("*")
            if p.is_symlink() or p.name == ".git"
        ]
        if offenders:
            raise GovernedScanRefused(
                f"materialized snapshot is not git-free or holds a symlink: "
                f"{offenders[:5]}"
            )
    except BaseException as exc:  # noqa: BLE001 - cleanup must cover every exit
        # Deliberately BaseException: an interrupt mid-copy leaves the same
        # partial copy a refusal does. If the residue cannot be removed, the
        # retained path is named in the raised refusal rather than left silent —
        # an unremovable copy of reviewed bytes is itself the finding.
        residue = _discard_snapshot(dest)
        if residue is None:
            raise
        raise GovernedScanRefused(
            f"snapshot materialization failed ({exc}) and the partial copy of "
            f"reviewed bytes could not be removed: {residue}"
        ) from exc
    return dest, digest.hexdigest()


def veyro_relative_findings(findings: list[dict], snapshot: Path, work: Path) -> list[dict]:
    """Re-express snapshot-local finding paths as reviewed repository-relative paths.

    Without this a finding would name a temporary directory that no longer
    exists once the run ends, which is unverifiable as evidence about the
    reviewed target set. A `File` that cannot be placed inside the snapshot is
    refused rather than reported: a path this wrapper cannot map back to an
    enumerated target is not a result about the reviewed bytes.
    """
    snapshot, work = snapshot.resolve(), work.resolve()
    relocated: list[dict] = []
    for finding in findings:
        raw = finding.get("File") or ""
        candidates = [Path(raw), snapshot / raw, work / raw] if raw else []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved != snapshot and snapshot in resolved.parents:
                relocated.append({**finding, "File": str(resolved.relative_to(snapshot))})
                break
        else:
            raise GovernedScanRefused(
                f"gitleaks reported a finding path that is not inside the materialized "
                f"snapshot: {raw!r}"
            )
    return relocated


# --- Supply chain ------------------------------------------------------------


def verify_artifact_digest(path: Path, scanner: str) -> str:
    """Hash the executable and require an eligible recorded digest. Every run."""
    if not path.is_file() or path.is_symlink():
        raise GovernedScanRefused(f"{scanner} artifact is not a regular file: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if scanner == "gitleaks":
        reason = GITLEAKS_INELIGIBLE_BINARY_SHA256.get(digest)
        if reason:
            raise GovernedScanRefused(f"{scanner} artifact {digest} is ineligible: {reason}")
        eligible = GITLEAKS_ELIGIBLE_BINARY_SHA256
    else:
        eligible = RUFF_ELIGIBLE_BINARY_SHA256
    if digest not in eligible:
        raise GovernedScanRefused(
            f"{scanner} artifact SHA-256 {digest} is not a recorded eligible digest "
            f"{sorted(eligible)}"
        )
    return digest


def assert_pinned_version(path: Path, scanner: str) -> str:
    """Assert the tool reports its pinned version (not a scan; no target given)."""
    argv = [str(path), "version"] if scanner == "gitleaks" else [str(path), "--version"]
    expected = GITLEAKS_VERSION if scanner == "gitleaks" else RUFF_VERSION
    out = subprocess.run(argv, capture_output=True, text=True, check=False)
    reported = out.stdout.strip()
    if out.returncode != 0 or reported != expected:
        raise GovernedScanRefused(f"{scanner} reported {reported!r}, expected {expected!r}")
    return reported


# --- Authorisation predicate -------------------------------------------------


def _git_blob_matches_head(rel: str, repo_root: Path | None = None) -> tuple[bool, str]:
    """True only if `rel` is git-tracked AND byte-identical to HEAD."""
    repo_root = repo_root if repo_root is not None else REPO_ROOT
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", rel],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.returncode != 0:
        return False, f"{rel} is not git-tracked (uncommitted; iac.md control 1)"
    diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", rel],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode != 0:
        return False, f"{rel} differs from HEAD (not the reviewed bytes)"
    return True, ""


def _registry_row(cap_id: str, registry_path: Path | None = None) -> str:
    registry_path = registry_path if registry_path is not None else REGISTRY_PATH
    for line in registry_path.read_text().splitlines():
        if line.startswith(f"| {cap_id} "):
            return line
    return ""


def authorisation_blockers(
    scanner: str,
    manifest: dict | None = None,
    repo_root: Path | None = None,
    registry_path: Path | None = None,
) -> list[str]:
    """Every unmet condition for a real-tree invocation. Empty list == allowed.

    Deliberately has no override parameter: there is nothing a caller can pass,
    set, or create to shorten this list. The two path parameters select *which*
    repository and registry are interrogated, never whether; they resolve at
    call time so the whole predicate is exercisable against a disposable
    synthetic repository (which is how its non-vacuity is demonstrated).
    """
    repo_root = repo_root if repo_root is not None else REPO_ROOT
    registry_path = registry_path if registry_path is not None else REGISTRY_PATH
    manifest = manifest if manifest is not None else load_manifest()
    cap_id, token = GRANT_TOKENS[scanner]
    blockers: list[str] = []

    row = _registry_row(cap_id, registry_path)
    if not row:
        blockers.append(f"{cap_id} has no row in CAPABILITY_REGISTRY.md")
    elif token not in row:
        blockers.append(
            f"{cap_id} registry row carries no '{token}' grant "
            f"(its scope cell still records real-tree/CI as NOT approved)"
        )

    named = manifest.get("authorising_determination")
    if not named:
        blockers.append(
            "manifest names no authorising independent determination "
            "('authorising_determination' is null)"
        )
    else:
        doc = repo_root / named
        if not doc.is_file():
            blockers.append(f"named authorising determination not found: {named}")
        elif token not in doc.read_text():
            blockers.append(f"{named} does not carry the '{token}' grant")

    workflow_rel = manifest.get("candidate_workflow") or ""
    for rel in (SELF_REL, MANIFEST_REL, workflow_rel):
        if not rel:
            blockers.append("manifest names no candidate workflow")
            continue
        ok, why = _git_blob_matches_head(rel, repo_root)
        if not ok:
            blockers.append(why)
    return blockers


def _require_scan_allowed(scanner: str, paths: list[Path]) -> None:
    """The single choke point. Any Veyro path requires zero blockers.

    Synthetic paths outside the repository pass straight through — that is the
    APPROVED (BOUNDED) scope. A repository path reaches a scanner only if every
    blocker above is cleared, which no part of this module can arrange.

    "Veyro path" is provenance, not geography. A snapshot materialized from
    committed Veyro bytes (`materialize_tracked_snapshot`) lives outside the
    repository by construction and is still governed here, because its bytes
    are the repository's bytes: copying them out must not silently reclassify a
    Veyro scan as an approved synthetic one.
    """
    root = REPO_ROOT.resolve()
    for path in paths:
        resolved = Path(path).resolve()
        if resolved == root or root in resolved.parents or _is_veyro_derived(resolved):
            blockers = authorisation_blockers(scanner)
            if blockers:
                raise RealScanBlocked(scanner, blockers)
            return


# --- Governed invocations ----------------------------------------------------


def gitleaks_argv(binary: Path, target: Path, report: Path, ignore_dir: Path) -> list[str]:
    """The governed gitleaks argv. `dir` mode only; no baseline flag, ever.

    This is the module's only gitleaks argv builder and the mode is hardcoded,
    so no index- or history-scanning subcommand is constructible anywhere here
    and the wrapper makes no claim about either surface.
    """
    return [
        str(binary),
        "dir",
        "--no-banner",
        "--no-color",
        "--redact=100",
        "--exit-code",
        str(GITLEAKS_LEAK_EXIT),
        "--report-format",
        "json",
        "--report-path",
        str(report),
        "--ignore-gitleaks-allow",
        "-i",
        str(ignore_dir),
        str(target),
    ]


def ruff_argv(
    binary: Path, config: Path, targets: list[Path], *, show_files: bool
) -> list[str]:
    """The governed Ruff `S` argv (or its `--show-files` non-vacuity pre-check)."""
    argv = [str(binary), "check", "--config", str(config), "--no-cache", "--select", "S"]
    if show_files:
        argv.append("--show-files")
    else:
        argv += ["--no-fix", "--output-format", "json", "--ignore-noqa"]
    return argv + [str(t) for t in targets]


def classify_gitleaks_exit(returncode: int, mode: str) -> tuple[int, str]:
    """0 clean / 42 leak / anything else an error. Mode decides leak severity."""
    if returncode == 0:
        return EXIT_OK, "clean"
    if returncode == GITLEAKS_LEAK_EXIT:
        return (EXIT_FINDINGS if mode == "gate" else EXIT_OK), "leak"
    return EXIT_REFUSED, f"scanner error (rc={returncode})"


def classify_ruff_exit(returncode: int, codes: set[str], mode: str) -> tuple[int, str]:
    """0 clean / 1 findings / 2 tool-or-config error; syntax errors kept apart."""
    if returncode == 2:
        return EXIT_REFUSED, "tool or configuration error"
    if returncode == 0:
        return EXIT_OK, "clean"
    if returncode != 1:
        return EXIT_REFUSED, f"unexpected exit (rc={returncode})"
    if codes and codes <= {"invalid-syntax"}:
        return EXIT_REFUSED, "invalid-syntax only: target not analysable, not S-clean"
    return (EXIT_FINDINGS if mode == "gate" else EXIT_OK), "S findings"


def redact_gitleaks_findings(raw: str) -> list[dict]:
    """Emit value-free findings. Fail closed if the report is not redacted."""
    findings = json.loads(raw) if raw.strip() else []
    safe = []
    for finding in findings:
        if finding.get("Secret") != "REDACTED":
            raise GovernedScanRefused("gitleaks report is not redacted — refusing to emit")
        safe.append(
            {
                "RuleID": finding.get("RuleID"),
                "File": finding.get("File"),
                "StartLine": finding.get("StartLine"),
                "Fingerprint": finding.get("Fingerprint"),
            }
        )
    return safe


def run_gitleaks_governed(
    binary: Path, target: Path, work: Path, *, mode: str
) -> tuple[int, str, list[dict]]:
    """Governed `gitleaks dir` run. Refuses every precondition gitleaks cannot."""
    _require_scan_allowed("gitleaks", [target, work])
    verify_artifact_digest(binary, "gitleaks")
    assert_pinned_version(binary, "gitleaks")
    target, work = target.resolve(), work.resolve()
    if not target.is_dir():
        raise GovernedScanRefused("target is not a directory")
    if not [p for p in target.rglob("*") if p.is_file() and p.stat().st_size > 0]:
        raise GovernedScanRefused("zero non-empty files: vacuous scan")
    if (target / ".gitleaksignore").exists():
        # No flag defeats a target-root .gitleaksignore in 8.30.1; refuse.
        raise GovernedScanRefused("target-root .gitleaksignore cannot be disabled by flag")
    if (target / ".git").exists():
        # `dir` mode walks a directory, so a `.git` inside the target puts Git
        # object/pack bytes — i.e. history — in front of the scanner. CAP-009
        # records Git index and history scope as NOT approved, and whether
        # 8.30.1's default global allowlist excludes `.git` is UNTESTED (see the
        # ALLOWLIST_EXCLUDED_DIR_SEGMENTS note). Refusing is the only reading
        # that does not depend on an unverified exclusion.
        #
        # This is a backstop, not the mechanism: the governed real-tree path in
        # `invoke` never hands a checkout to this function, because
        # `materialize_tracked_snapshot` builds a git-free target first. The
        # refusal stays so that a caller who skips that step is refused rather
        # than served.
        raise GovernedScanRefused(
            "target contains .git: `dir` mode would walk Git object bytes (history "
            "scope is not approved and the default-allowlist `.git` exclusion is "
            "untested)"
        )
    ignore_dir = work / "empty-ignore-dir"
    ignore_dir.mkdir(parents=True, exist_ok=True)
    if any(ignore_dir.iterdir()):
        raise GovernedScanRefused("-i directory is not empty")
    report = work / "gitleaks-report.json"
    report.unlink(missing_ok=True)
    result = subprocess.run(
        gitleaks_argv(binary, target, report, ignore_dir),
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    code, label = classify_gitleaks_exit(result.returncode, mode)
    if code == EXIT_REFUSED:
        raise GovernedScanRefused(f"gitleaks {label}")
    return code, label, redact_gitleaks_findings(report.read_text() if report.is_file() else "")


def redact_ruff_findings(raw: str) -> list[dict]:
    """Emit value-free `S` findings: rule, path, line. Never Ruff's message text.

    Ruff's JSON `message` quotes the offending construct, which for `S105`/`S106`
    (hardcoded password) is the credential-shaped value itself, so the message is
    dropped rather than forwarded (`secrets.md` control 1).
    """
    return [
        {
            "code": f.get("code"),
            "filename": f.get("filename"),
            "row": (f.get("location") or {}).get("row"),
        }
        for f in (json.loads(raw) if raw.strip() else [])
    ]


def run_ruff_s_governed(
    binary: Path,
    config: Path,
    targets: list[Path],
    work: Path,
    *,
    expected_file_count: int,
    mode: str,
    findings_sink: list[dict] | None = None,
) -> tuple[int, str, set[str]]:
    """Governed Ruff `S` run with an exact `--show-files` count pre-check."""
    _require_scan_allowed("ruff", [*targets, work])
    verify_artifact_digest(binary, "ruff")
    assert_pinned_version(binary, "ruff")
    for target in targets:
        # Symlink check on the *given* path: resolving first would silently
        # follow the link and hide it.
        if Path(target).is_symlink():
            raise GovernedScanRefused(f"symlinked target refused: {Path(target).name}")
    resolved = [t.resolve() for t in targets]
    for target in resolved:
        if not target.exists() or (target.is_file() and target.stat().st_size == 0):
            raise GovernedScanRefused(f"missing or empty target: {target.name}")
    listed = subprocess.run(
        ruff_argv(binary, config, resolved, show_files=True),
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    files = {line.strip() for line in listed.stdout.splitlines() if line.strip()}
    if listed.returncode != 0:
        raise GovernedScanRefused(f"--show-files pre-check failed (rc={listed.returncode})")
    if len(files) != expected_file_count:
        # Count equality, not ">= 1": closes the partial-gitignore vacuity the
        # second determination §5.3 left open for directory targets.
        raise GovernedScanRefused(
            f"--show-files listed {len(files)} files, expected exactly {expected_file_count}"
        )
    result = subprocess.run(
        ruff_argv(binary, config, resolved, show_files=False),
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    codes = (
        {f["code"] for f in json.loads(result.stdout)} if result.stdout.strip() else set()
    )
    if findings_sink is not None:
        findings_sink.extend(redact_ruff_findings(result.stdout))
    code, label = classify_ruff_exit(result.returncode, codes, mode)
    if code == EXIT_REFUSED:
        raise GovernedScanRefused(f"ruff {label}")
    return code, label, codes


# --- Preflight report --------------------------------------------------------


def load_manifest(path: Path | None = None) -> dict:
    path = path if path is not None else MANIFEST_PATH
    if not path.is_file():
        raise GovernedScanRefused(f"reviewed target manifest is missing: {path}")
    return json.loads(path.read_text())


def preflight(scanner: str, mode: str, repo_root: Path | None = None) -> dict:
    """Inspectable preflight. Executes no scanner against any Veyro file."""
    repo_root = repo_root if repo_root is not None else REPO_ROOT
    report: dict = {
        "tool": SELF_REL,
        "scanner": scanner,
        "mode": mode,
        "authorised_for_real_tree_scan": False,
        "refusals": [],
        "blockers": [],
    }
    manifest = load_manifest()
    live = enumerate_targets(repo_root)
    report["manifest"] = {
        "path": MANIFEST_REL,
        "reviewed_tracked_count": manifest.get("tracked_count"),
        "reviewed_python_target_count": manifest.get("python_target_count"),
        "authorising_determination": manifest.get("authorising_determination"),
        "candidate_workflow": manifest.get("candidate_workflow"),
    }
    report["live_target_set"] = {
        k: v for k, v in live.as_dict().items() if k not in ("tracked", "python_targets")
    }
    report["intended_python_targets"] = list(live.python_targets)
    for check in (
        lambda: verify_against_manifest(live, manifest),
        lambda: assert_scannable(live, scanner),
    ):
        try:
            check()
        except GovernedScanRefused as exc:
            report["refusals"].append(str(exc))
    # Informational, not a refusal: the clean-committed-checkout and
    # advisory-before-gate constraints bind the *invocation* path (`invoke`), and
    # a preflight is readable on a working tree mid-change. Reported here so the
    # distance between this tree and a scannable one is visible without running
    # anything.
    try:
        assert_clean_committed_checkout(live, repo_root)
        report["clean_committed_checkout"] = {"ok": True, "reason": None}
    except GovernedScanRefused as exc:
        report["clean_committed_checkout"] = {"ok": False, "reason": str(exc)}
    report["gate_mode_refusals"] = gate_mode_refusals(scanner, manifest, repo_root)
    report["blockers"] = authorisation_blockers(scanner, manifest, repo_root)
    report["authorised_for_real_tree_scan"] = not report["blockers"] and not report["refusals"]
    return report


def _verify_governed_ruff_config(repo_root: Path | None = None) -> Path:
    """The `--config` file must be the digest-pinned, committed, reviewed bytes."""
    repo_root = repo_root if repo_root is not None else REPO_ROOT
    config = repo_root / RUFF_CONFIG_REL
    if not config.is_file() or config.is_symlink():
        raise GovernedScanRefused(f"governed Ruff config is not a regular file: {RUFF_CONFIG_REL}")
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    if digest != RUFF_CONFIG_SHA256:
        raise GovernedScanRefused(
            f"{RUFF_CONFIG_REL} SHA-256 {digest} != the pinned {RUFF_CONFIG_SHA256}; a "
            f"changed config re-scopes the run (CAP-010 stage-9 material change)"
        )
    ok, why = _git_blob_matches_head(RUFF_CONFIG_REL, repo_root)
    if not ok:
        raise GovernedScanRefused(f"governed Ruff config is not reviewed bytes: {why}")
    return config


def gate_mode_refusals(scanner: str, manifest: dict, repo_root: Path | None = None) -> list[str]:
    """Advisory-before-gate: `gate` requires a recorded prior advisory run.

    C09-X/C10-X sequence advisory before gate because the tree's real state is
    unknown, so the first gate run could only ever be a surprise. The recorded
    advisory evidence is the thing that makes it not one.
    """
    repo_root = repo_root if repo_root is not None else REPO_ROOT
    cap_id, _ = GRANT_TOKENS[scanner]
    token = f"ADVISORY-RUN-RECORDED: {cap_id}"
    named = manifest.get("advisory_run_evidence")
    if not named:
        return [
            f"gate mode requires a recorded prior advisory run; the manifest's "
            f"'advisory_run_evidence' is null, so no {cap_id} advisory result exists to "
            f"sequence a gate after"
        ]
    doc = repo_root / named
    if not doc.is_file():
        return [f"named advisory-run evidence not found: {named}"]
    if token not in doc.read_text():
        return [f"{named} does not carry the '{token}' record"]
    return []


def _resolve_work_dir(work: Path | None) -> Path:
    """A report/ignore-dir location outside the repository (never inside it)."""
    if work is None:
        return Path(tempfile.mkdtemp(prefix="veyro-c06-scan-"))
    resolved = work.resolve()
    root = REPO_ROOT.resolve()
    if resolved == root or root in resolved.parents:
        raise GovernedScanRefused(
            "work directory must be outside the repository (a report written inside "
            "it would both dirty the reviewed checkout and become a scan target)"
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def invoke(
    scanner: str,
    mode: str,
    binary: Path | None,
    work: Path | None = None,
    repo_root: Path | None = None,
) -> tuple[int, dict]:
    """The governed real-tree invocation path. Returns (exit code, report).

    Order is deliberate and fail-closed at every step:

      1. **Authorisation** — the first question, asked before anything else is
         even computed about the binary or the work directory, so a blocked run
         cannot be turned into a different outcome by a bad flag.
      2. **Target-side refusals** — manifest drift, vacuity, and the clean
         committed checkout. All of these run *before* any scanner process
         starts, so an unreviewed target set never reaches a scanner.
      3. **Artifact identity** — digest and reported version, re-verified on
         this run (the gitleaks release is mutable; a pin recorded once is not
         enforcement).
      4. **Materialization** (gitleaks only) — exactly the enumerated committed
         blobs are copied into a git-free directory outside the repository, with
         each file's Git blob id re-derived from the bytes actually copied, so
         the scanner is handed the reviewed bytes and no Git object.
      5. **The scanner**, through the governed argv only, with value-free
         reporting and the distinct exit classification.
      6. **Discard** — the snapshot is removed on every exit from the scan, and
         the report states whether removal was *verified*, not whether it was
         attempted. A copy that cannot be removed turns a successful scan into a
         refusal.
    """
    repo_root = repo_root if repo_root is not None else REPO_ROOT
    manifest = load_manifest()
    live = enumerate_targets(repo_root)
    report: dict = {
        "tool": SELF_REL,
        "scanner": scanner,
        "mode": mode,
        "head_commit": live.head_commit,
        "target_set": {
            "tracked_count": len(live.tracked),
            "tracked_sha256": live.tracked_sha256,
            "python_target_count": len(live.python_targets),
            "python_sha256": live.python_sha256,
            "declared_allowlist_excluded": list(live.allowlist_excluded),
        },
        "blockers": authorisation_blockers(scanner, manifest, repo_root),
        "refusals": [],
        "findings": [],
        "outcome": "blocked",
        "exit_code": EXIT_BLOCKED,
    }
    if report["blockers"]:
        return EXIT_BLOCKED, report

    try:
        if binary is None:
            raise GovernedScanRefused(
                "no scanner executable given: --binary PATH is required and no PATH "
                "lookup is performed, so an unpinned or Homebrew binary can never be "
                "picked up implicitly"
            )
        verify_against_manifest(live, manifest)
        assert_scannable(live, scanner)
        assert_clean_committed_checkout(live, repo_root)
        if mode == "gate":
            for why in gate_mode_refusals(scanner, manifest, repo_root):
                raise GovernedScanRefused(why)
        resolved_work = _resolve_work_dir(work)
        report["binary_sha256"] = verify_artifact_digest(binary, scanner)
        report["binary_version"] = assert_pinned_version(binary, scanner)
        if scanner == "gitleaks":
            # The reviewed bytes sit in a Git checkout, which `dir` mode must
            # never be pointed at. Materialize exactly the enumerated committed
            # blobs into a git-free directory, scan that, and drop it: a copy of
            # the tree is not left lying around outside the repository.
            snapshot, content_digest = materialize_tracked_snapshot(
                live, repo_root, resolved_work
            )
            # `retained_after_run` is deliberately absent until cleanup has
            # actually been attempted and checked below: the earlier version of
            # this report asserted `false` here, before the scanner had even
            # run, which is a claim this code was not in a position to make.
            snapshot_report = {
                "file_count": len(live.tracked),
                "content_sha256": content_digest,
                "git_free": True,
            }
            report["materialized_snapshot"] = snapshot_report
            try:
                code, label, findings = run_gitleaks_governed(
                    binary, snapshot, resolved_work, mode=mode
                )
                report["findings"] = veyro_relative_findings(
                    findings, snapshot, resolved_work
                )
            finally:
                # Runs for a clean scan, a findings exit, a scanner refusal and
                # a finding-mapping refusal alike, and records what was observed
                # rather than what was intended.
                residue = _discard_snapshot(snapshot)
                snapshot_report["retained_after_run"] = residue is not None
                if residue is not None:
                    snapshot_report["retention_residue"] = residue
            if residue is not None:
                # A successful scan whose copy could not be removed is still a
                # refusal: reviewed bytes outliving the run is the defect.
                raise GovernedScanRefused(
                    f"the materialized snapshot of reviewed committed bytes outlived "
                    f"the run: {residue}"
                )
        else:
            config = _verify_governed_ruff_config(repo_root)
            sink: list[dict] = []
            code, label, codes = run_ruff_s_governed(
                binary,
                config,
                [repo_root / p for p in live.python_targets],
                resolved_work,
                expected_file_count=manifest["python_target_count"],
                mode=mode,
                findings_sink=sink,
            )
            report["findings"] = sink
            report["rule_codes"] = sorted(codes)
    except RealScanBlocked as exc:
        # The inner choke point disagreed with the outer check. Trust the refusal.
        report["blockers"] = exc.blockers
        return EXIT_BLOCKED, report
    except GovernedScanRefused as exc:
        report["refusals"].append(str(exc))
        report["outcome"] = "refused"
        report["exit_code"] = EXIT_REFUSED
        return EXIT_REFUSED, report
    report["outcome"] = label
    report["exit_code"] = code
    report["finding_count"] = len(report["findings"])
    return code, report


def _print(report: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        live = report["live_target_set"]
        print(f"scanner={report['scanner']} mode={report['mode']}")
        print(f"HEAD={live['head_commit']}")
        print(
            f"tracked={live['tracked_count']} ({live['tracked_sha256'][:16]}…)  "
            f"py={live['python_target_count']} ({live['python_sha256'][:16]}…)"
        )
        print(
            f"declared out-of-coverage (default global allowlist): "
            f"{live['declared_allowlist_excluded_count']} path(s)"
        )
        checkout = report["clean_committed_checkout"]
        print(f"clean_committed_checkout={checkout['ok']} {checkout['reason'] or ''}".rstrip())
        for refusal in report["refusals"]:
            print(f"REFUSED: {refusal}")
        for refusal in report["gate_mode_refusals"]:
            print(f"GATE-SEQUENCING: {refusal}")
        for blocker in report["blockers"]:
            print(f"BLOCKER: {blocker}")
        print(f"authorised_for_real_tree_scan={report['authorised_for_real_tree_scan']}")
    if report["refusals"]:
        return EXIT_REFUSED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("command", choices=("preflight", "emit-targets", "scan"))
    parser.add_argument("--scanner", choices=tuple(GRANT_TOKENS), default="gitleaks")
    parser.add_argument(
        "--mode",
        choices=("advisory", "gate"),
        default="advisory",
        help="advisory reports findings at exit 0; gate exits 1 on findings",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--binary",
        type=Path,
        help="path to the digest-pinned scanner executable; required by `scan` once "
        "authorisation stands. No PATH lookup is ever performed.",
    )
    parser.add_argument(
        "--work",
        type=Path,
        help="report/ignore-dir location for `scan`; must be outside the repository "
        "(default: a fresh temporary directory)",
    )
    args = parser.parse_args(argv)

    if args.command == "emit-targets":
        # Prints only. Never writes the reviewed manifest: this tool cannot
        # re-bind its own target set.
        print(json.dumps(enumerate_targets().as_dict(), indent=2, sort_keys=True))
        return EXIT_OK
    if args.command == "preflight":
        try:
            report = preflight(args.scanner, args.mode)
        except GovernedScanRefused as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return EXIT_REFUSED
        return _print(report, args.json)

    try:
        code, report = invoke(args.scanner, args.mode, args.binary, args.work)
    except GovernedScanRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps(report, indent=2, sort_keys=True))
    for blocker in report["blockers"]:
        print(f"BLOCKED: {blocker}", file=sys.stderr)
    for refusal in report["refusals"]:
        print(f"REFUSED: {refusal}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
