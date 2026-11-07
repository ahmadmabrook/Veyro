#!/usr/bin/env python3
"""Veyro MOD-004 Rule path-scope qualification (Python stdlib only, no network, never writes).

  rule_scope.py check  --root R          report each rule's declared scope against the repository
  rule_scope.py corpus --root R          run the EIP 11818 path-scope corpus
  rule_scope.py scope  --rule F PATH...  classify paths against one rule's declared globs

Exit 0 = PASS, 1 = BLOCKED (stdout JSON lists failures), 2 = malformed input/usage (fail closed).

**What this qualifies, and the one thing it cannot.** EIP Appendix H 11818, as quoted in
`contracts/engineering/capability-records/RULE-001-mod004-rls.md`, asks for "representative
matching paths and non-matching paths to show scoping is correct and does not pollute unrelated
contexts". This runs that corpus against the globs the rule files actually declare.

It does **not** exercise Claude Code's own rule-matching engine. The harness that applies
`.claude/rules/*` decides for itself which paths a rule reaches, its matching semantics are not
documented in this repository, and nothing here observes it. So a PASS means: *the declared globs,
under the semantics stated below, select the intended paths and reject the rest.* It does not mean
the running harness agrees. Closing that gap needs either documented harness semantics or an
observation of the harness, and neither is available statically -- it is the reason this tool
cannot, on its own, close `BLK-RULE-QUALIFICATION`.

Nor does it touch the other outstanding items either RULE record names: the runtime-negative
qualification (role-privilege and transaction-pool-reuse tests), which needs a live PostgreSQL and
so waits on `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME`; the independent review under 11774; and the
11816 abuse and permission-negative tests. **No RULE evidence ID follows from this tool, and no
lifecycle status, ACTIVE manifest row, Module Ready or security PASS is claimed.**

Authority: `OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` 1.6 bars any new
custom Skill or Rule *creation* attempt and says, in its own words, that this is "distinct and
**not** barred: *qualifying* the two rules that already exist, which is the path-scope tests,
runtime-negative tests and independent review its `qualification_state` names. Qualification is not
creation." This tool reads the two rule files and never writes to them: changing a rule's declared
paths would be a modification needing its own review, which 3.3 does not grant and this tool does
not perform.

**Assumed glob semantics, stated because the harness's are unknown.** Patterns are matched against
repository-relative, forward-slash paths with no leading `./`. `**` matches any number of
characters including `/`; `*` matches any run of characters other than `/`; `?` matches one
character other than `/`; every other character is literal. A trailing `/**` therefore selects
everything *below* a directory and not the directory's own path -- `backend/migrations/**` matches
`backend/migrations/0001.sql` and not `backend/migrations`. Matching is case-sensitive. A pattern
anchors at both ends: `backend/app/tenancy/**` does not match `backend/app/tenancy_s0.py`, which
is what keeps the published S0 slice outside RULE-001 (a property
`contracts/engineering/mod004-s0-capability.json` already asserts, and that `corpus` re-checks
rather than restates).

**Known divergences from gitignore convention**, found by probing this matcher rather than assumed,
and pinned by tests so they stay deliberate. A leading or interior `**` does not match zero
directories here: `**/x.py` does not match `x.py`, and `a/**/b` does not match `a/b`, where
gitignore would match both. Bracket characters are literal, so `a[b]/**` means the directory named
`a[b]` and not a character class. A leading `./` is not stripped and such a pattern is refused.
None of this affects the two rules being qualified -- neither uses `**` anywhere but at the end,
and neither uses brackets -- but a third rule that did would need this matcher corrected first.

`check` also prints each rule file's SHA-256. Both RULE records carry the rule file's hash as
`NOT_COMPUTED in the authoring session (no hashing tool); runner must verify externally`, and the
runner is retired. Reporting the hash here makes it computable and re-checkable by anyone, without
editing a capability record: `contracts/engineering/capability-records/` happens to sit inside
ADR-0006's `Covers`, but ADR-0006's subject is the D4.3 driver selection, and citing it to amend a
RULE record would be using path coverage as a loophole rather than as authority. Recording the
hashes in those records is left to a change whose own subject is that.

Rule files are read as a `---` delimited YAML front matter block holding `description:` and a
`paths:` list of `- "glob"` items. The parse is deliberately narrow -- no YAML library, since
`tools/` is stdlib-only -- and anything it does not recognise is an error rather than a silent
skip, so a rule whose front matter changes shape fails loudly instead of qualifying with an empty
glob set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

RULE_DIR = ".claude/rules"
CORPUS = "path_scope_corpus.json"
CORPUS_SCHEMA = 1
# Directories never worth walking when reporting which files a glob reaches.
SKIP_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", "node_modules", ".ruff_cache"})


class Malformed(Exception):
    """Usage or input error; always exit 2, never a PASS."""


def compile_glob(pattern: str) -> re.Pattern[str]:
    """Translate one glob to an anchored regex under the semantics in the module docstring."""
    if not pattern or pattern.startswith("/") or "\\" in pattern:
        raise Malformed(f"glob must be a relative forward-slash path: {pattern!r}")
    out = ["^"]
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        char = pattern[i]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def matches(pattern: str, path: str) -> bool:
    return compile_glob(pattern).fullmatch(path) is not None


def parse_rule(path: Path) -> dict:
    """Return {'path', 'description', 'paths'} for one rule file. Fails closed on any surprise."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Malformed(f"cannot read {path}: {exc}") from None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise Malformed(f"{path}: no front matter opening '---'")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise Malformed(f"{path}: front matter is not closed") from None

    description = ""
    globs: list[str] = []
    in_paths = False
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("description:"):
            description = raw.split(":", 1)[1].strip()
            in_paths = False
            continue
        if raw.strip() == "paths:":
            in_paths = True
            continue
        item = re.fullmatch(r"\s*-\s*(?:\"([^\"]+)\"|'([^']+)'|(\S+))\s*", raw)
        if in_paths and item:
            globs.append(item.group(1) or item.group(2) or item.group(3))
            continue
        if re.fullmatch(r"[A-Za-z][\w-]*:.*", raw.strip()):
            in_paths = False
            continue
        raise Malformed(f"{path}: unrecognised front-matter line: {raw!r}")
    if not globs:
        raise Malformed(f"{path}: front matter declares no paths")
    for glob in globs:
        compile_glob(glob)
    return {"path": str(path), "description": description, "paths": globs}


def repo_files(root: Path) -> list[str]:
    out = []
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        rel = candidate.relative_to(root)
        if SKIP_DIRS & set(rel.parts):
            continue
        out.append(rel.as_posix())
    return sorted(out)


def find_rules(root: Path) -> list[Path]:
    rules_root = root / RULE_DIR
    if not rules_root.is_dir():
        raise Malformed(f"no rule directory at {rules_root}")
    found = sorted(rules_root.rglob("*.md"))
    if not found:
        raise Malformed(f"no rule file under {rules_root}")
    return found


def check(root: Path) -> dict:
    """Report every rule's declared scope and what it reaches in the repository as it stands."""
    files = repo_files(root)
    report = []
    for rule_path in find_rules(root):
        rule = parse_rule(rule_path)
        matched = sorted({f for f in files for g in rule["paths"] if matches(g, f)})
        digest = hashlib.sha256(rule_path.read_bytes()).hexdigest()
        missing_dirs = [g for g in rule["paths"] if g.endswith("/**")
                        and not (root / g[:-3]).is_dir()]
        report.append({
            "rule": rule["path"],
            "sha256": digest,
            "declared_paths": rule["paths"],
            "matched_files_in_repository": matched,
            "declared_directories_absent": missing_dirs,
        })
    return {"rules": report, "repository_files_considered": len(files)}


def run_corpus(root: Path, corpus_path: Path) -> list[dict[str, str]]:
    """Run the 11818 path-scope corpus. Returns failures; empty means the declared scope holds."""
    if not corpus_path.exists():
        raise Malformed(f"corpus not found: {corpus_path}")
    try:
        data = json.loads(corpus_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Malformed(f"corpus unreadable: {exc}") from None
    if not isinstance(data, dict) or data.get("schema") != CORPUS_SCHEMA:
        raise Malformed(f"corpus schema must be {CORPUS_SCHEMA}")
    entries = data.get("rules")
    if not isinstance(entries, list) or not entries:
        raise Malformed("corpus 'rules' must be a non-empty list")

    failures: list[dict[str, str]] = []
    covered: set[str] = set()
    for entry in entries:
        for field in ("rule", "must_match", "must_not_match"):
            if field not in entry:
                raise Malformed(f"corpus entry missing {field}")
        rule_path = root / entry["rule"]
        rule = parse_rule(rule_path)
        covered.add(entry["rule"])
        if not entry["must_match"] or not entry["must_not_match"]:
            # Both directions are required. A corpus with only positives would pass a glob of
            # `**`, and one with only negatives would pass an empty glob set.
            raise Malformed(f"{entry['rule']}: corpus needs both must_match and must_not_match")
        declared = entry.get("declared_paths")
        if declared is not None and declared != rule["paths"]:
            failures.append({"item": entry["rule"],
                             "detail": f"declared paths changed: corpus pins {declared}, "
                                       f"the rule file now says {rule['paths']}"})
        for path in entry["must_match"]:
            hit = [g for g in rule["paths"] if matches(g, path)]
            if not hit:
                failures.append({"item": f"{entry['rule']} :: {path}",
                                 "detail": f"must match, but no declared glob does: {rule['paths']}"})
        for path in entry["must_not_match"]:
            hit = [g for g in rule["paths"] if matches(g, path)]
            if hit:
                failures.append({"item": f"{entry['rule']} :: {path}",
                                 "detail": f"must not match, but {hit} does"})

    for rule_path in find_rules(root):
        rel = rule_path.relative_to(root).as_posix()
        if rel not in covered:
            failures.append({"item": rel,
                             "detail": "rule file has no corpus entry, so its scope is unqualified"})
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Veyro MOD-004 Rule path-scope qualification (EIP Appendix H 11818).")
    sub = parser.add_subparsers(dest="command", required=True)
    here = Path(__file__).resolve().parent

    p_check = sub.add_parser("check", help="report declared scope against the repository")
    p_check.add_argument("--root", default=".")

    p_corpus = sub.add_parser("corpus", help="run the path-scope corpus")
    p_corpus.add_argument("--root", default=".")
    p_corpus.add_argument("--corpus", default=str(here / CORPUS))

    p_scope = sub.add_parser("scope", help="classify paths against one rule's declared globs")
    p_scope.add_argument("paths", nargs="+")
    p_scope.add_argument("--rule", required=True)

    args = parser.parse_args(argv)
    limit = ("this reports the DECLARED globs only; Claude Code's own rule matcher is not "
             "exercised, and no RULE evidence ID follows")
    try:
        if args.command == "check":
            out = {"result": "PASS", "command": "check", "declared_scope_only": limit,
                   **check(Path(args.root))}
        elif args.command == "corpus":
            failures = run_corpus(Path(args.root), Path(args.corpus))
            out = {"result": "BLOCKED" if failures else "PASS", "command": "corpus",
                   "declared_scope_only": limit, "findings": failures}
        else:
            rule = parse_rule(Path(args.rule))
            out = {"result": "PASS", "command": "scope", "rule": rule["path"],
                   "declared_paths": rule["paths"], "declared_scope_only": limit,
                   "classified": {path: sorted(g for g in rule["paths"] if matches(g, path))
                                  for path in args.paths}}
    except Malformed as exc:
        print(json.dumps({"result": "MALFORMED", "detail": str(exc)}, indent=1, sort_keys=True))
        return 2
    print(json.dumps(out, indent=1, sort_keys=True))
    return 1 if out["result"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
