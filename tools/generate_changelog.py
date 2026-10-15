"""
Release changelog generator (MOD-001, GOV-01-R08; SCN-MOD001-107).

Derives one changelog entry from the actual committed Git history between a
prior release ref and the current release ref. It never reads a hand-written
draft.

    generate_changelog.py --repo . --from-ref train-2026.01 \
        --to-ref train-2026.02 --release-id train-2026.02 [--output CHANGELOG.md]

History walked: `git log --first-parent <from>..<to>`. Each first-parent
commit is classified:

  * merged PR  - merge commit whose subject is `Merge pull request #N from
                 <head>`; the PR title is the first non-empty body line.
  * squash PR  - non-merge commit whose subject ends in `(#N)`.
  * other      - plain direct commit; ignored (not a merged PR).

A merged PR is changelog-worthy unless its title's conventional-commit type is
one of chore/ci/docs/test/style/build (e.g. `docs(x): ...`, `ci!: ...`).

Output (stdout, or appended to --output) follows RELEASE_TRAIN.md's
"Changelog entry format" section:

    ## <release-id> (<from-ref>..<to-ref>)

    - <PR title> (#N)

Exit 0 with no output and no file change when no changelog-worthy PR exists.
Exit 1 with one defect per line on stderr (fail closed) for: bad release id,
unresolvable refs, from-ref not an ancestor of to-ref, an empty range, a
malformed PR merge (unparseable subject or empty title), a non-PR merge
commit, a duplicate PR number, or an --output file that already holds this
release id.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RELEASE_ID = re.compile(r"^train-\d{4}\.\d{2}$")
_PR_MERGE = re.compile(r"^Merge pull request #(\d+) from \S+$")
_PR_MERGE_PREFIX = "Merge pull request"
_SQUASH = re.compile(r"^(?P<title>.+?) \(#(?P<num>\d+)\)$")
_CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(\([^)]*\))?!?:\s")
NON_WORTHY_TYPES = frozenset({"chore", "ci", "docs", "test", "style", "build"})
_FIELD, _RECORD = "\x1f", "\x1e"


class ChangelogError(Exception):
    pass


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ChangelogError(f"git unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise ChangelogError(f"git {args[0]} failed: {proc.stderr.strip()}")
    return proc.stdout


def _resolve(repo: Path, ref: str, label: str) -> str:
    if not ref or ref.startswith("-"):
        raise ChangelogError(f"{label} is not a valid ref: {ref!r}")
    try:
        return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()
    except ChangelogError as exc:
        raise ChangelogError(f"{label} does not resolve to a commit: {ref!r}") from exc


def collect_pull_requests(repo: Path, from_ref: str, to_ref: str) -> list[PullRequest]:
    """Merged PRs on the first-parent path from_ref..to_ref, oldest first."""
    if not repo.is_dir():
        raise ChangelogError(f"repo is not a directory: {repo}")
    base = _resolve(repo, from_ref, "from-ref")
    head = _resolve(repo, to_ref, "to-ref")
    try:
        _git(repo, "merge-base", "--is-ancestor", base, head)
    except ChangelogError as exc:
        raise ChangelogError(f"from-ref {from_ref!r} is not an ancestor of to-ref {to_ref!r}") from exc
    if base == head:
        raise ChangelogError("from-ref and to-ref are the same commit (empty range)")

    fmt = f"%H{_FIELD}%P{_FIELD}%s{_FIELD}%b{_RECORD}"
    raw = _git(repo, "log", "--first-parent", "--reverse", f"--format={fmt}", f"{base}..{head}")
    prs: list[PullRequest] = []
    seen: set[int] = set()
    for record in raw.split(_RECORD):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(_FIELD)
        if len(parts) != 4:
            raise ChangelogError(f"unparseable git log record: {record[:60]!r}")
        sha, parents, subject, body = parts
        short = sha[:10]
        if len(parents.split()) > 1:
            m = _PR_MERGE.match(subject)
            if not m:
                kind = "malformed PR merge" if subject.startswith(_PR_MERGE_PREFIX) else "non-PR merge commit"
                raise ChangelogError(f"{kind} {short}: {subject!r}")
            title = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
            if not title:
                raise ChangelogError(f"PR merge {short} has an empty title: {subject!r}")
            pr = PullRequest(int(m.group(1)), title)
        else:
            m = _SQUASH.match(subject)
            if not m:
                continue
            pr = PullRequest(int(m.group("num")), m.group("title").strip())
        if pr.number in seen:
            raise ChangelogError(f"duplicate PR number #{pr.number} (commit {short})")
        seen.add(pr.number)
        prs.append(pr)
    return prs


def is_changelog_worthy(pr: PullRequest) -> bool:
    m = _CONVENTIONAL.match(pr.title)
    return not (m and m.group("type") in NON_WORTHY_TYPES)


def render_entry(release_id: str, from_ref: str, to_ref: str, prs: list[PullRequest]) -> str:
    worthy = [pr for pr in prs if is_changelog_worthy(pr)]
    if not worthy:
        return ""
    lines = [f"## {release_id} ({from_ref}..{to_ref})", ""]
    lines += [f"- {pr.title} (#{pr.number})" for pr in worthy]
    return "\n".join(lines) + "\n"


def generate(repo: Path, from_ref: str, to_ref: str, release_id: str) -> str:
    if not RELEASE_ID.match(release_id):
        raise ChangelogError(f"release-id must match train-YYYY.NN: {release_id!r}")
    return render_entry(release_id, from_ref, to_ref, collect_pull_requests(repo, from_ref, to_ref))


def _append(output: Path, release_id: str, entry: str) -> None:
    existing = output.read_text(encoding="utf-8") if output.exists() else ""
    if re.search(rf"^## {re.escape(release_id)}\b", existing, re.MULTILINE):
        raise ChangelogError(f"{output} already contains an entry for {release_id}")
    if existing and not existing.endswith("\n"):
        existing += "\n"
    sep = "\n" if existing else ""
    output.write_text(existing + sep + entry, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--from-ref", required=True, help="prior release ref")
    ap.add_argument("--to-ref", required=True, help="current release ref")
    ap.add_argument("--release-id", required=True, help="train-YYYY.NN")
    ap.add_argument("--output", type=Path, help="append the entry to this file")
    args = ap.parse_args(argv)
    try:
        entry = generate(args.repo, args.from_ref, args.to_ref, args.release_id)
        if entry and args.output:
            _append(args.output, args.release_id, entry)
    except (ChangelogError, OSError) as exc:
        print(f"DEFECT: {exc}", file=sys.stderr)
        return 1
    if entry and not args.output:
        sys.stdout.write(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
