#!/usr/bin/env python3
"""
Database-migration expand/contract ordering + record-completeness
validator (MOD-001, GOV-01-R06 — "Database-change policy/tooling").

Per `REQUIREMENTS.md` GOV-01-R06 and TSD §24.2 (verbatim): "Expand ->
migrate/backfill -> switch reads/writes -> contract. Destructive contract
happens only after all deployed versions stop using old shape... Every
migration records owner, expected lock/write impact, rollback/forward-fix
strategy and data validation query."

This tool is deliberately NOT wired to Alembic or any specific DB
migration framework: no actual product schema exists yet (R06's own
"OUT of scope" line), and CAPABILITIES.md's precedent for GOV-01-R01
explicitly defers concrete-tool selection to real implementation rather
than inventing a stack this planning turn didn't mandate. What TSD §24.2
actually requires right now — ordering discipline and a fixed record
schema — is fully checkable as a static lint over plain migration-record
files, with zero new dependencies (stdlib only), matching
`validate_baseline_binding.py`/`validate_capability_manifest.py`/
`validate_repo_skeleton.py`'s existing self-contained convention. A real
Alembic (or other) migration tool can be introduced later, at the point a
real schema exists, without needing to change this lint's contract.

## Record format

Each migration record is a `.yaml`-front-matter file (parsed with a
minimal `key: value` line scanner, not a YAML library — no new
dependency for 6 flat scalar fields):

    ---
    change_id: add_user_email_index
    phase: expand
    owner: jane@example.com
    lock_impact: CREATE INDEX CONCURRENTLY, no write lock
    rollback_strategy: DROP INDEX CONCURRENTLY IF EXISTS ix_users_email
    validation_query: SELECT count(*) FROM users WHERE email IS NULL
    ---

    Free-text description below the closing `---` is ignored by this tool.

`phase` must be one of `expand`, `migrate`, `switch`, `contract` (TSD
§24.2's own 4 stages — `migrate` covers "migrate/backfill"). The other 5
fields (`change_id` plus TSD's 4 named record fields: `owner`,
`lock_impact`, `rollback_strategy`, `validation_query`) are all required
and must be non-empty.

## Record discovery (hardened 2026-10-04, round-1 review finding R1-3)

A record is a `*.yaml` file **directly inside** the records dir. Every
other file anywhere in that tree — a `.yml` spelling, a `.md` file (the
extension of `TEMPLATE.md`, which authors copy from), or a `.yaml` nested
in a subdirectory — is reported as `UNRECOGNIZED_RECORD_FILE`, not
silently skipped. Round 1 proved the previous `glob("*.yaml")` let a
genuinely out-of-order destructive record set pass with exit 0 under all
three spellings, contradicting this tool's own "never a silent partial
pass" contract. Enumerating-and-rejecting is preferred over widening the
glob because it is explicit: an unreadable or misplaced file becomes a
visible failure rather than an invisible omission. Only
`IGNORED_NON_RECORD_FILES` (the repo's `.gitkeep` placeholder and macOS's
`.DS_Store`) are skipped — neither is a plausible migration-record name.

Symlinks anywhere in that tree are themselves reported
(`SYMLINK_IN_RECORDS_TREE`) rather than followed — round-2 review finding
R2-1 proved `rglob` does not descend through a symlinked directory, so a
destructive out-of-order record hidden behind one passed with exit 0 and no
notice at all.

Enumeration itself is error-reporting, not error-suppressing: `rglob` was
replaced by `enumerate_tree()` (round-3 finding R3-1), so any subtree that
cannot be read becomes a named `UNREADABLE_RECORDS_PATH` problem instead of
an empty result indistinguishable from an empty directory.

## Metadata acquisition (hardened 2026-10-04, round-4 finding R4-1)

Replacing the enumerator alone was **not** sufficient, and the reason is the
whole point of this section. The invariant that kept recurring (R1-3, R2-1,
R2-3, R3-1) was never "`rglob` specifically suppresses errors" — it was
**this tool cannot distinguish a path it could not read from a path with
nothing in it**. Round 3 fixed the walker and left two more error-swallowing
probes on the gate *in front of* the walker (`Path.is_dir()`,
`Path.exists()`) plus a third in `main()`'s notice path, so the identical
observable defect simply migrated one layer out: a records directory that
exists and holds a destructive out-of-order `contract`, but whose **parent**
is unreadable, produced exit 0, the ordinary `PASS` line, and a NOTICE
affirmatively stating the directory "does not exist".

So metadata is now acquired **once**, explicitly, by an error-propagating
`os.stat`/`os.lstat` (`acquire_records_dir()`), into one of exactly three
outcomes — present directory / genuinely absent / error-or-wrong-type — and
that single result is shared by validation, traversal and the CLI notice
(`run_validation()` returns both the problems and the notice; `main()`
prints what it is given and re-probes nothing). Only a genuine
`FileNotFoundError` from **both** `os.stat` and `os.lstat` — i.e. a path
that is affirmatively determined not to be there, not merely one `lstat`
failed to describe — may produce the documented default vacuous PASS;
`PermissionError` or any other `OSError` from **either** call is a named
nonzero diagnostic **in both flag modes**. Round 4 left the `lstat` half of
that sentence untrue (a bare `except OSError: return ABSENT`); round-5
finding R5-1 names it and `acquire_records_dir`'s total classification table
now enumerates all six outcome classes of the syscall pair, so no residual
`OSError` bucket remains for an unknown state to fall into. No
`Path.exists()` or
`Path.is_dir()` decides a PASS or a NOTICE anywhere in this module anymore,
and nothing re-runs discovery to decide either —
`test_no_pathlib_existence_probe_decides_a_pass_or_notice` locks that
structurally, because three rounds of shape-by-shape predicate guards
demonstrated that a behavioral test per known shape is not enough.

Inside the walk, the same rule applies to per-entry classification:
`os.scandir`'s `DirEntry` metadata is read once with its `OSError`
propagated into a named `UNCLASSIFIABLE_RECORDS_ENTRY` problem (it used to
set `descend = False` and say nothing), and `discover_records` consumes that
captured classification rather than re-probing the filesystem through
`Path.is_symlink()`/`Path.is_dir()`, which swallow `OSError` the same way.

## Ordering rule

Per `change_id`, phases must appear across files (in filename-sorted
order, so callers use a numeric prefix like `0001_...`) in the sequence
expand -> migrate -> switch -> contract. A phase may repeat (multiple
expand files for one change are fine) but may not skip ahead or regress:
`contract` for a `change_id` that never saw a prior `switch` (or `switch`
before `migrate`, etc.) fails closed as `OUT_OF_ORDER_PHASE`, naming the
change_id, the phase found, and the phase it needed to see first — never
a silent partial pass.

This tool never writes to the checked tree — read-only, always.
"""
import argparse
import os
import stat
import sys
from pathlib import Path
from typing import NamedTuple

PHASE_ORDER = ["expand", "migrate", "switch", "contract"]
REQUIRED_FIELDS = ["change_id", "phase", "owner", "lock_impact", "rollback_strategy", "validation_query"]

# Files inside the records tree that are deliberately NOT migration records
# and must not raise UNRECOGNIZED_RECORD_FILE (R1-3). Kept as a tight,
# explicit allowlist rather than a pattern: `.gitkeep` is the repo's own
# empty-dir placeholder (`backend/migrations/records/.gitkeep`) and
# `.DS_Store` is macOS Finder metadata that appears without anyone
# authoring it. Neither is a plausible migration-record filename, so
# skipping exactly these two opens no path for a real record to hide.
IGNORED_NON_RECORD_FILES = frozenset({".gitkeep", ".DS_Store"})

DEFAULT_RECORDS_DIR = Path(__file__).resolve().parent.parent / "backend" / "migrations" / "records"

# The two vacuous-pass notices, as constants rather than literals inside
# `main()` — round-4 finding R4-1. They used to be printed from `main()` on
# the strength of a *second*, independent probe of the filesystem
# (`args.records_dir.exists()` and a repeat `discover_records()` call), which
# is how the CLI came to print "records dir does not exist" over a directory
# that does exist and holds a destructive record. A notice is now a value
# returned alongside the problems by the one authoritative validation pass, so
# it cannot disagree with the verdict it is printed next to.
NOTICE_ABSENT = ("NOTICE: records dir does not exist — vacuous pass, no record was "
                 "checked. Pass --require-dir to fail closed on a missing path.")
NOTICE_NO_RECORDS = ("NOTICE: records dir exists but contains no migration records — "
                     "vacuous pass, no record was checked.")

# The three — and only three — outcomes of acquiring the records path's
# metadata. "Unknown" is deliberately NOT folded into "absent": that fold is
# the root cause of the R1-3/R2-1/R2-3/R3-1/R4-1 invariant family.
RECORDS_PATH_DIRECTORY = "directory"
RECORDS_PATH_ABSENT = "absent"
RECORDS_PATH_ERROR = "error"


class RecordsPath(NamedTuple):
    """Tri-state result of `acquire_records_dir`. `problem` is set if and only
    if `kind` is `RECORDS_PATH_ERROR`."""
    kind: str
    problem: str | None


class TreeEntry(NamedTuple):
    """One entry from `enumerate_tree`, carrying the metadata that was read
    once, at enumeration time, from `os.scandir`'s own `DirEntry` cache.

    Consumers must use these captured booleans rather than re-probing the
    path: `Path.is_symlink()`/`Path.is_dir()` return `False` on `OSError`
    instead of raising, which is the error-swallowing property this whole
    module is structured to avoid (round-4 finding R4-1)."""
    path: Path
    is_symlink: bool
    is_dir: bool


class ValidationOutcome(NamedTuple):
    """The single authoritative result of one validation pass: every problem
    found, plus the vacuous-pass notice (if any) that belongs with it.

    `notice` is `None` whenever `problems` is non-empty — a "vacuous pass"
    line printed next to a `BLOCKED` verdict is self-contradictory (the
    misleading-diagnostic failure mode of round-1 finding R1-7), and making
    that structural rather than conventional is what stops a caller from
    reconstructing the notice from a second filesystem probe."""
    problems: list[str]
    notice: str | None


class RecordError(Exception):
    """A single migration record fails a structural or field check."""


def parse_front_matter(path: Path) -> dict[str, str]:
    """Parses the `---`-delimited front matter at the top of `path` into a
    flat dict of the 6 scalar fields this tool understands. Raises
    `RecordError` (never returns a partial dict) if the file has no
    front-matter block at all, so a malformed record is never silently
    treated as an empty-but-valid one.

    A repeated key is also a `RecordError` (`DUPLICATE_FRONT_MATTER_KEY`),
    not a last-one-wins resolution — round-2 review finding R2-2. A record
    declaring `phase: contract` and later `phase: expand` previously linted
    as `expand` and passed with exit 0, while a human reading the
    authoritative first line sees `contract`. Picking either occurrence is a
    guess about author intent; refusing is the fail-closed answer."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise RecordError(f"{path.name}: MISSING_FRONT_MATTER — no opening '---' on line 1")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in fields:
            raise RecordError(
                f"{path.name}: DUPLICATE_FRONT_MATTER_KEY — '{key}' declared more than "
                f"once ('{fields[key]}' then '{value.strip()}'); the record must declare "
                f"each field exactly once so the phase a reader sees is the phase enforced"
            )
        fields[key] = value.strip()
    raise RecordError(f"{path.name}: MISSING_FRONT_MATTER — no closing '---' found")


def validate_fields(name: str, fields: dict[str, str]) -> list[str]:
    """Returns every TSD §24.2 field missing or empty in `fields`, plus an
    invalid `phase` value — empty list means the record's fields are
    structurally complete (ordering is checked separately)."""
    problems = []
    for field in REQUIRED_FIELDS:
        if not fields.get(field, "").strip():
            problems.append(f"{name}: MISSING_REQUIRED_FIELD — '{field}' absent or empty")
    phase = fields.get("phase", "").strip()
    if phase and phase not in PHASE_ORDER:
        problems.append(
            f"{name}: INVALID_PHASE — '{phase}' is not one of {PHASE_ORDER}"
        )
    return problems


def check_ordering(records: list[tuple[str, dict[str, str]]]) -> list[str]:
    """`records` is a filename-sorted list of (name, fields) tuples for
    records that already passed `validate_fields`. Returns every
    out-of-order phase transition found, walking each change_id's own
    phase history independently so unrelated changes never interfere with
    each other's ordering."""
    problems = []
    highest_index: dict[str, int] = {}
    for name, fields in records:
        change_id = fields["change_id"]
        phase = fields["phase"]
        phase_index = PHASE_ORDER.index(phase)
        if change_id not in highest_index:
            if phase_index != 0:
                needed = PHASE_ORDER[0]
                problems.append(
                    f"{name}: OUT_OF_ORDER_PHASE — change_id '{change_id}' starts at "
                    f"'{phase}' but must start with '{needed}'"
                )
                continue
            highest_index[change_id] = 0
            continue
        last = highest_index[change_id]
        if phase_index == last:
            continue  # repeat of the current phase (e.g. a second expand file) — fine
        if phase_index == last + 1:
            highest_index[change_id] = phase_index
            continue
        needed = PHASE_ORDER[last + 1] if phase_index > last else PHASE_ORDER[last]
        problems.append(
            f"{name}: OUT_OF_ORDER_PHASE — change_id '{change_id}' jumps to '{phase}' "
            f"without a preceding '{needed}'"
        )
    return problems


def enumerate_tree(root: Path) -> tuple[list[TreeEntry], list[str]]:
    """Depth-first enumeration of every entry under `root`, returning
    (entries, problems) with entries and problems each sorted for
    determinism. Each entry carries its symlink/directory classification,
    read once here from `os.scandir`'s `DirEntry` cache, so no consumer has
    to re-probe the filesystem with an error-swallowing `pathlib` predicate.

    This replaces `Path.rglob("*")` — round-3 review finding R3-1, and the
    architectural root cause behind the whole R1-3/R2-1/R2-3/R3-1 family.
    `pathlib`'s globbing swallows `OSError`/`PermissionError` and yields an
    empty iterator, so an unreadable directory was indistinguishable from an
    empty one: a mode-000 records dir holding a destructive out-of-order
    `contract` returned exit 0, the ordinary `PASS` line, and a NOTICE
    affirmatively stating the directory "contains no migration records." No
    guard existed to mutate, which is why an 11/11 mutation battery missed
    it. Ad-hoc guards layered over an error-suppressing enumerator cannot
    establish exhaustive discovery; only an enumerator that reports its own
    failures can.

    Every subtree that cannot be enumerated becomes a named
    `UNREADABLE_RECORDS_PATH` problem, so the caller fails closed instead of
    seeing a short list it cannot tell from a complete one.

    Symlink handling is deliberately identical to the previous `rglob`
    behavior: a symlink is yielded as an entry but never descended into
    (`follow_symlinks=False`), so `discover_records`'s existing
    `SYMLINK_IN_RECORDS_TREE` guard still sees it and no link target widens
    the walk or admits a cycle."""
    entries: list[TreeEntry] = []
    problems: list[str] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                children = list(scan)
        except OSError as exc:
            # The root is named by its full path (matching MISSING_RECORDS_DIR
            # and RECORDS_PATH_NOT_A_DIRECTORY); a nested directory by its
            # relative path (matching UNRECOGNIZED_RECORD_FILE and
            # SYMLINK_IN_RECORDS_TREE).
            where = str(root) if current == root else current.relative_to(root).as_posix()
            problems.append(
                f"{where}: UNREADABLE_RECORDS_PATH — could not enumerate this directory "
                f"({exc.strerror}), so any migration record under it would go unchecked; "
                f"a tree that cannot be read must never report a pass"
            )
            continue
        for entry in children:
            path = Path(entry.path)
            try:
                is_symlink = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError as exc:
                # Round-4 finding R4-1, same invariant one level down: this
                # branch used to set `descend = False` and record nothing, so
                # an entry whose type could not be read was silently treated
                # as "not a directory" and never descended. Whether records
                # hid under it was then unknown-folded-into-empty — exactly
                # the fold this module exists to refuse. Name it instead.
                problems.append(
                    f"{path.relative_to(root).as_posix()}: UNCLASSIFIABLE_RECORDS_ENTRY — "
                    f"could not read this entry's type ({exc.strerror}), so whether it "
                    f"hides migration records is unknown; an entry that cannot be "
                    f"classified must never report a pass"
                )
                continue
            entries.append(TreeEntry(path, is_symlink, is_dir))
            if is_dir and not is_symlink:
                stack.append(path)
    return sorted(entries), sorted(problems)


def discover_records(records_dir: Path) -> tuple[list[Path], list[str]]:
    """Walks the whole `records_dir` tree once and splits it into
    (record_paths, problems). A record is a `*.yaml` file directly inside
    `records_dir`; every other file is an `UNRECOGNIZED_RECORD_FILE`
    problem rather than a silent skip, except the explicitly-allowlisted
    `IGNORED_NON_RECORD_FILES`. See the module docstring's "Record
    discovery" section for why rejecting beats widening the glob (R1-3)."""
    records: list[Path] = []
    entries, problems = enumerate_tree(records_dir)
    for entry in entries:
        path = entry.path
        relative = path.relative_to(records_dir).as_posix()
        # Round-2 review finding R2-1, checked FIRST — before is_dir(), which
        # follows the link and `continue`s. `rglob` does not descend through a
        # symlinked directory, so files beneath one were never enumerated: a
        # records dir with a valid 4-phase set plus a symlinked `q4/` holding a
        # lone destructive `contract` produced exit 0, the ordinary PASS line,
        # and (because real records existed) not even a vacuous-pass NOTICE.
        # Reported rather than resolved: following link targets would widen the
        # walk and invite cycles, and narrowing this module's "every other file
        # anywhere in that tree" claim would leave the clean exit-0 PASS intact.
        # Side effect, deliberate: a dangling `*.yaml` symlink is now a named
        # problem instead of an uncaught FileNotFoundError traceback (R2-4's
        # symlink case only — unreadable-permission and non-UTF-8 records still
        # raise).
        #
        # Round-4 finding R4-1: both classifications below now come from the
        # `TreeEntry` the enumerator captured, not from `path.is_symlink()` /
        # `path.is_dir()`. Those two `pathlib` predicates return False on
        # `OSError` rather than raising, so on a hostile tree the symlink guard
        # could simply fail to fire — the same unknown-folded-into-absent
        # defect, in the guard that closed R2-1.
        if entry.is_symlink:
            problems.append(
                f"{relative}: SYMLINK_IN_RECORDS_TREE — symlinks are not followed, so "
                f"anything beneath or behind this link would go unchecked; replace it "
                f"with the real file/directory or remove it"
            )
            continue
        if entry.is_dir or path.name in IGNORED_NON_RECORD_FILES:
            continue
        if path.parent == records_dir and path.suffix == ".yaml":
            records.append(path)
            continue
        problems.append(
            f"{relative}: UNRECOGNIZED_RECORD_FILE — not a '*.yaml' file directly "
            f"inside the records dir, so it would not be checked at all; rename it "
            f"to '*.yaml', move it out of the subdirectory, or remove it"
        )
    return sorted(records), problems


def acquire_records_dir(records_dir: Path) -> RecordsPath:
    """Acquires `records_dir`'s metadata ONCE, with errors propagated rather
    than swallowed, and classifies it into exactly one of three outcomes:
    a present directory, a genuinely absent path, or an error/wrong-type path
    that carries its own named problem.

    This is the architectural fix for round-4 finding R4-1 and for the whole
    invariant family behind it. The predecessor was a pair of `pathlib`
    predicates — `records_dir.is_dir()` then `records_dir.exists()` — and both
    return `False` on `OSError` instead of raising. So "I could not read this
    path" and "this path is not there" were the same answer, and a records
    directory holding a destructive out-of-order `contract` behind an
    unreadable parent reported exit 0, `PASS`, and a NOTICE asserting the
    directory did not exist. `os.stat` raises instead, which is the entire
    reason it is used here in place of the convenience predicates:

      * `FileNotFoundError` from `stat` **and** `FileNotFoundError` from
        `lstat` — genuinely absent, the path is not even a symlink. This is
        the ONE outcome permitted to produce the documented default vacuous
        PASS (GOV-01-R06's "no product schema exists yet" case), and only
        without `--require-dir`. Note what establishes it: a *successful*
        ENOENT answer from `lstat`, never merely "`lstat` did not succeed"
        (round-5 finding R5-1).
      * `FileNotFoundError` from `stat` where `lstat` nonetheless succeeds — a
        dangling symlink. The path itself is present, so "does not exist"
        would be a false statement about it; named, nonzero, both flag modes.
      * `FileNotFoundError` from `stat` where `lstat` fails with any other
        `OSError` — whether the path is absent or merely unreadable is
        UNKNOWN, so neither "absent" nor "pass" may be asserted about it;
        named, nonzero, both flag modes (R5-1).
      * any other `OSError` from `stat` (`PermissionError`,
        `NotADirectoryError`, EIO …) — the path's state is UNKNOWN, which is
        never a pass. Named, nonzero, both flag modes. `--require-dir` is an
        assertion about a *missing* directory; it must not be what stands
        between an unreadable tree and a green run, especially since
        `run_regression.py` — the only automated caller — deliberately omits
        it.
      * stat succeeded but the mode is not a directory — `RECORDS_PATH_NOT_A_
        DIRECTORY`, fail-closed regardless of the flag, unchanged from R2-3.

    `os.stat` follows symlinks, exactly as the replaced `is_dir()` did, so a
    symlink pointing at a real records directory is still usable.

    ## The total classification table (round-5 finding R5-1)

    Round 4 wrote the outer `os.stat` classification exhaustively but left the
    inner `os.lstat` fallback as a bare `except OSError: return ABSENT`, so
    "lstat says the path is not there" and "lstat could not tell me anything
    about the path" were once again the same answer — the same
    unknown-folded-into-absent root cause this scenario had already removed
    from four other sites, relocated into the one branch no test and no mutant
    touched. The fix is not another shape-specific guard: it is enumerating
    **every** outcome class of the two syscalls, so there is no residual
    `OSError` bucket left for an unknown state to fall into.

    | `os.stat` | `os.lstat` | Kind | Named problem |
    |---|---|---|---|
    | OK, mode is a directory   | not called | `DIRECTORY` | — (proceed to traversal) |
    | OK, mode is not a directory | not called | `ERROR` | `RECORDS_PATH_NOT_A_DIRECTORY` |
    | `FileNotFoundError`       | `FileNotFoundError` | `ABSENT` | — (the ONE permitted vacuous pass) |
    | `FileNotFoundError`       | returns OK | `ERROR` | `BROKEN_RECORDS_SYMLINK` |
    | `FileNotFoundError`       | any other `OSError` | `ERROR` | `UNREADABLE_RECORDS_PATH` |
    | any other `OSError`       | not called | `ERROR` | `UNREADABLE_RECORDS_PATH` |

    These six rows are total over the pair: `os.stat`/`os.lstat` signal every
    failure as an `OSError`, `FileNotFoundError` is the only `OSError` subclass
    that means "not there", and it is handled before the general case in both
    positions. `RECORDS_PATH_ABSENT` is therefore reachable by exactly one
    route — ENOENT from *both* calls — which is the property
    `test_no_except_handler_in_acquire_records_dir_folds_oserror_into_absent`
    locks structurally, because five rounds demonstrated that a behavioral
    test per known shape does not stop this fold from reappearing somewhere
    else."""
    try:
        info = os.stat(records_dir)
    except FileNotFoundError:
        # `stat` reported ENOENT. `lstat` now discriminates "genuinely absent"
        # from "present but unusable", and BOTH of its failure modes are
        # classified explicitly — `FileNotFoundError` first (the only
        # `OSError` subclass that means "not there"), then every other
        # `OSError` as a named error. A bare `except OSError` here is what
        # R5-1 was.
        try:
            os.lstat(records_dir)
        except FileNotFoundError:
            return RecordsPath(RECORDS_PATH_ABSENT, None)
        except OSError as exc:
            return RecordsPath(RECORDS_PATH_ERROR, (
                f"{records_dir}: UNREADABLE_RECORDS_PATH — the path's metadata could "
                f"not be read without following symlinks ({exc.strerror}), so whether "
                f"it is genuinely absent or merely unreadable is unknown; an "
                f"indeterminate path must never report a pass or an absence, with or "
                f"without --require-dir"
            ))
        return RecordsPath(RECORDS_PATH_ERROR, (
            f"{records_dir}: BROKEN_RECORDS_SYMLINK — this path is a symlink whose "
            f"target does not exist, so no record could ever be discovered under it "
            f"and it is not the absent-directory case either; point --records-dir at "
            f"the real records directory"
        ))
    except OSError as exc:
        return RecordsPath(RECORDS_PATH_ERROR, (
            f"{records_dir}: UNREADABLE_RECORDS_PATH — could not read this path's "
            f"metadata ({exc.strerror}), so whether it holds migration records is "
            f"unknown; an unreadable path must never report a pass, with or without "
            f"--require-dir"
        ))
    if not stat.S_ISDIR(info.st_mode):
        return RecordsPath(RECORDS_PATH_ERROR, (
            f"{records_dir}: RECORDS_PATH_NOT_A_DIRECTORY — this path exists but is "
            f"not a directory, so no record could ever be discovered under it; "
            f"point --records-dir at the real records directory"
        ))
    return RecordsPath(RECORDS_PATH_DIRECTORY, None)


def run_validation(records_dir: Path, require_dir: bool = False) -> ValidationOutcome:
    """The one authoritative validation pass: acquires the records path's
    metadata once, then (only if it is a readable directory) discovers,
    field-checks and order-checks its records once. Returns every problem
    found together with the vacuous-pass notice that belongs with the result,
    so no caller needs — or is able — to re-derive either by probing the
    filesystem a second time (round-4 finding R4-1).

    An empty directory is PASS with a notice — no product schema exists yet,
    per this requirement's own explicitly-stated OUT-of-scope line. A
    genuinely *absent* directory is PASS with a notice for the same reason by
    default, and fails closed as `MISSING_RECORDS_DIR` when `require_dir` is
    set, so a typo'd or relocated path in a future CI job cannot pass green
    forever (R1-4). Every other acquisition outcome is a named problem in both
    flag modes — see `acquire_records_dir`."""
    acquired = acquire_records_dir(records_dir)
    if acquired.kind == RECORDS_PATH_ERROR:
        assert acquired.problem is not None  # RecordsPath's own invariant
        return ValidationOutcome([acquired.problem], None)
    if acquired.kind == RECORDS_PATH_ABSENT:
        if require_dir:
            return ValidationOutcome([(
                f"{records_dir}: MISSING_RECORDS_DIR — --require-dir was set but this "
                f"directory does not exist; a typo'd or relocated records path must fail "
                f"closed, not report a vacuous pass"
            )], None)
        return ValidationOutcome([], NOTICE_ABSENT)

    record_paths, problems = discover_records(records_dir)
    valid_records: list[tuple[str, dict[str, str]]] = []
    for path in record_paths:
        try:
            fields = parse_front_matter(path)
        except RecordError as exc:
            problems.append(str(exc))
            continue
        field_problems = validate_fields(path.name, fields)
        if field_problems:
            problems.extend(field_problems)
            continue
        valid_records.append((path.name, fields))
    problems.extend(check_ordering(valid_records))
    if problems:
        return ValidationOutcome(problems, None)
    return ValidationOutcome([], NOTICE_NO_RECORDS if not record_paths else None)


def validate_directory(records_dir: Path, require_dir: bool = False) -> list[str]:
    """Problems-only view of `run_validation`, kept as this module's original
    entry point so every existing caller and test is unaffected by R4-1's
    restructuring. Returns every problem found; an empty list is PASS."""
    return run_validation(records_dir, require_dir=require_dir).problems


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Database-migration expand/contract ordering + record-completeness "
                     "validator (MOD-001, GOV-01-R06). Fails closed, naming every problem "
                     "record, if any migration record is incomplete or out of TSD "
                     "§24.2 phase order."
    )
    p.add_argument(
        "--records-dir", type=Path, default=DEFAULT_RECORDS_DIR,
        help=f"Directory of migration-record .yaml files to validate "
             f"(default: {DEFAULT_RECORDS_DIR}). Point this at a throwaway fixture "
             "directory for negative testing without touching the real tree.",
    )
    p.add_argument(
        "--require-dir", action="store_true",
        help="Fail closed (MISSING_RECORDS_DIR, exit 1) if --records-dir does not "
             "exist, instead of reporting a vacuous pass. Any future CI wiring should "
             "pass this so a typo'd or relocated path cannot pass green forever "
             "(round-1 review finding R1-4).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    outcome = run_validation(args.records_dir, require_dir=args.require_dir)

    print("=" * 70)
    print("MOD-001 DATABASE-MIGRATION ORDERING + RECORD VALIDATOR")
    print("=" * 70)
    print(f"\nRecords dir checked: {args.records_dir}")

    if outcome.problems:
        print(f"\nBLOCKED: {len(outcome.problems)} problem(s) found:")
        for problem in outcome.problems:
            print(f"  - {problem}")
        return 1

    # Distinguish a real pass over real records from a pass that checked nothing
    # at all (R1-4, and probe T4's finding that every historical
    # "validate_migration_ordering.py PASS" in this vault was vacuous).
    #
    # Round-4 finding R4-1: this block used to decide WHICH notice to print by
    # probing the filesystem a second time — `args.records_dir.exists()`, then a
    # repeat `discover_records()` call. Both probes were independent of the
    # verdict above them and `exists()` swallows `OSError`, so the CLI printed
    # "records dir does not exist" over a directory that existed and held a
    # destructive out-of-order record. The notice now comes from the same
    # `run_validation` result as the verdict, which is also why it can only ever
    # appear on the pass path: `ValidationOutcome` leaves it `None` whenever
    # there are problems, so a "vacuous pass" line can no longer be printed
    # beside a `BLOCKED` one (the misleading-diagnostic mode of R1-7).
    if outcome.notice:
        print(outcome.notice)

    print("\nPASS — every migration record is complete and phase-ordered correctly "
          "(or no records exist yet).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
