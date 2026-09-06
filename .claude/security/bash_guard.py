#!/usr/bin/env python3
"""PreToolUse Bash security guard v2 for Veyro MOD-000 (BUG-013/022/023).

ARCHITECTURE: allow-by-construction, fail closed on ambiguity.

v1 (now `.claude/security/superseded_v1/`) tried to UNDERSTAND arbitrary
Bash/zsh syntax well enough to prove a request safe: normalize wrappers,
resolve absolute paths, skip git global options, track a virtual working
directory, recognize reserved words and redirection operators. Four
independent fresh-context security reviews (RR-1..RR-4) each found a new
syntactic shape it hadn't modeled — a different shell dialect, a
different redirection spelling, a different wrapper command, a different
git config key that executes its value as a shell command. That pattern,
repeated four times, was treated as an architectural finding rather than
a queue of patches to keep applying. Full history:
`knowledge/03-Modules/MOD-000/evidence/security/BASH_GUARD_DEVELOPMENT_2026-09-06.md`
and `.claude/security/superseded_v1/README.md`.

v2 does not try to parse or understand shell composition at all. Every
Bash command this guard is asked about gets exactly one of two outcomes:

  1. It exactly matches one of the small set of command families defined
     below (Class A: safe read-only; Class B: narrowly governed
     mutation, structurally incapable of the destructive operations this
     project cares about) → explicit ALLOW.
  2. Anything else — an unrecognized command, a recognized command with
     an unrecognized flag/argument shape, ANY shell composition/
     substitution syntax, or a parse failure → explicit DENY.

There is no third outcome. Unlike v1 (which stayed silent and deferred
to `.claude/settings.json`'s own allow/deny/defaultMode when it didn't
recognize a violation), v2 is the primary decision-maker for every Bash
call once activated: UNKNOWN MUST DENY, not "fall through to whatever
else happens to be configured." This is deliberately far more
restrictive than v1 or the bare `.claude/settings.json` allow list —
ordinary shell composition (piping, chaining, wrapping one command in
another, redirection) is simply unavailable through this guard. That is
the intended trade-off: a small, fully-enumerated, easily-audited
trusted surface instead of a general-purpose shell-normalization engine
that keeps discovering new blind spots.

## Stage 1 — composition/substitution rejected outright, unconditionally

Any occurrence of a small set of substrings anywhere in the raw command
text is an automatic, unconditional deny — no quote-awareness, no
context, no exceptions. This is a deliberate simplification: v1's whole
four-round history is a record of quote-aware, context-sensitive parsing
being exactly where the mistakes lived. A blanket substring check cannot
be evaded by a redirection spelling, a wrapper command, or a shell
dialect it wasn't written for, because it never tries to *understand*
the syntax at all — it just refuses to run anything containing it. This
also means a legitimate need to include one of these characters inside
an ALLOWED command's own argument (e.g. a commit message containing
"&&", or a grep pattern containing "|") is also denied — an accepted,
documented cost of the simplification, not an oversight. Rephrase or
split into two separate Bash calls in that case.

## Stage 2 — tokenize what's left; parse failure fails closed

The composition-free remainder is tokenized with `shlex` (POSIX mode).
Unbalanced quotes raise `ValueError`, which this guard treats as a deny,
not a pass-through.

## Stage 3 — exact-shape match against the family allowlist

Each family below validates the exact subcommand, an explicit flag
allowlist (not a blacklist — an unrecognized flag on an otherwise-known
command is denied, the same "unknown must deny" rule applied at the flag
level), and an argument shape. Command names, paths, and flags are
matched CASE-SENSITIVELY and EXACTLY as typed: this is a feature, not a
gap — v1 burned two of its four review rounds on case-sensitivity and
absolute-path/wrapper evasion because it was trying to *see through*
surface variation to classify intent; v2 doesn't classify intent, it
matches an exact known-good shape, so `RM`, `/bin/rm`, `env rm`, or a
`noglob` prefix simply don't match anything and are denied by
construction, with no special-case code required to catch any of them.

## Protected paths (defense in depth, not the primary barrier)

Stage 1's composition ban is the primary reason a governed-mutation
family (e.g. `git add`, `mkdir -p`) can't be turned into an arbitrary
write: there is no way to chain, redirect, or substitute your way out of
the fixed argv shape each family validates. `PROTECTED_PATH_FRAGMENTS`
below is an additional, narrower check specifically for the families
that take a path argument, so that even a validly-shaped governed
mutation can't target the project's governing artifacts.
"""
import json
import os
import re
import shlex
import sys

# ---------------------------------------------------------------------------
# Stage 1 — shell composition / substitution: unconditional deny
# ---------------------------------------------------------------------------

_COMPOSITION_MARKERS = (
    ";", "&&", "||", "|", "&", "`", "$(", "<(", ">(", "<<", ">", "<", "\n",
)


def _has_shell_composition(raw_command):
    return any(marker in raw_command for marker in _COMPOSITION_MARKERS)


# ---------------------------------------------------------------------------
# Protected paths (defense in depth — see module docstring)
# ---------------------------------------------------------------------------

PROTECTED_PATH_FRAGMENTS = [
    "gym_os_master_product_blueprint_v1_english.docx",
    "veyro_technical_system_design_v1.4.1_english_final.docx",
    "veyro_engineering_implementation_plan_v1.4.1_english_final_approved_governing_baseline.docx",
    "veyro-product-experience-design",
    # The entire .claude/ tree is governance-sensitive in this project
    # (settings, rules, agents, this guard itself) — protecting the bare
    # directory name, not just its known subpaths, is what closes RR-1
    # round's P1-1 finding: `git add .claude` (no subpath) matched none
    # of the earlier specific fragments below, even though it stages
    # every one of them.
    ".claude",
    "claude.md",
    ".mcp.json",
]


def _is_protected_path(token):
    """Substring check (works on any string shape) PLUS a normalized-
    path prefix check (catches `.claude//x`, `.claude/./x`,
    `.claude/y/../x` — anything that normalizes to the same protected
    location even though the raw substring differs). Callers should
    also run `_is_safe_relative_path` first, since that already rejects
    `..`/`//`/pathspec-magic characters outright — this function is the
    protected-*location* check, not the shape check."""
    lowered = token.lower()
    if any(frag in lowered for frag in PROTECTED_PATH_FRAGMENTS):
        return True
    try:
        normalized = os.path.normpath(token).lower()
    except Exception:
        return True  # fail closed on normalization error
    for frag in PROTECTED_PATH_FRAGMENTS:
        frag_clean = frag.rstrip("/")
        if normalized == frag_clean or normalized.startswith(frag_clean + "/"):
            return True
    return False


# Strict literal-relative-path charset for Class B mutation path
# arguments (git add, git commit -F, mkdir -p). Deliberately excludes
# ':', '*', '?', '$', '~', '{', '}', and anything else outside
# [A-Za-z0-9._-] plus '/' as a segment separator — this is what closes
# pathspec magic (`:/`), git's own glob expansion of an unquoted
# argument (`.claude/*`), and the shlex/shell tokenization divergence on
# `$'...'`/`${...}` (RR-1 P1-1/P2-2): none of those forms can be
# expressed using only this charset, so they are rejected by
# construction, not by enumerating each one.
_SAFE_RELATIVE_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")


def _is_safe_relative_path(token):
    """The single shared gate for every path-shaped argument this guard
    accepts, in EVERY family (Class A read-only and Class B mutation
    alike) — RR-2's review found round-1's fix applied this only to
    mutation families, leaving read families on a much weaker
    `startswith('/'/'~')` check that a bare `$HOME`, `$'...'`, or `..`
    sailed through. There is now exactly one function path arguments are
    checked against, not one per family, so a future family cannot
    reintroduce this class by copying the wrong helper."""
    if not token or not _SAFE_RELATIVE_PATH_RE.match(token):
        return False  # rejects absolute (`/...`), home (`~...`), `$`,
        # glob metacharacters, and anything else outside [A-Za-z0-9._-]/
    if any(part == ".." for part in token.split("/")):
        return False  # traversal segments
    if token == ".":
        return True  # legitimate cwd shorthand (e.g. find's search root)
    if token in ("-", "--"):
        return False  # content-free tokens (git add's own separate
        # convention against a bare "." is enforced in _git_add
        # specifically, not in this shared path-shape gate)
    if not any(c.isalnum() for c in token):
        return False  # e.g. "---" or "..." — no real path is only punctuation
    return True


# Strict charset for git ref/remote-name positionals (git push/fetch/
# remote/log/diff/show/rev-parse). Includes '~'/'^' for relative-ref
# syntax (HEAD~1, HEAD^) but — unlike `_is_safe_relative_path` — still
# explicitly rejects a LEADING '~' or '/' below, since git accepts a
# plain filesystem path (not just a URL) as a remote, and RR-2 found
# `git push ~/exfil.git` / `git push /tmp/exfil.git` both slipped through
# a charset that allowed '/' and '~' unconditionally. Excludes ':' and
# '+' entirely — the exact characters git's refspec grammar uses to
# express delete (`:branch`) and force (`+branch`) — so both are
# rejected by construction (RR-1 P0-1/P0-2), and a URL (which needs
# "://") can never match either, closing the URL half of the arbitrary-
# remote-exfiltration vector (RR-1 P1-4; the filesystem-path half is the
# explicit leading-`/`/`~` rejection below, RR-2 P1-2).
_SAFE_REF_OR_REMOTE_RE = re.compile(r"^[A-Za-z0-9._/~^-]+$")


def _is_safe_ref_or_remote(token):
    if not token or not _SAFE_REF_OR_REMOTE_RE.match(token):
        return False
    if token.startswith("-") or token.startswith("/") or token.startswith("~") or ".." in token:
        return False
    return True


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def _split_flags_positionals(tokens):
    # "--" (the POSIX end-of-options marker) is always a positional, not
    # a flag — needed so `git diff HEAD~1 -- knowledge` doesn't get its
    # "--" swept into the flag list and rejected as an unknown flag.
    flags = [t for t in tokens if t.startswith("-") and t not in ("-", "--")]
    positionals = [t for t in tokens if t in ("-", "--") or not t.startswith("-")]
    return flags, positionals


class Decision:
    ALLOW = "allow"
    DENY = "deny"


class Verdict(Exception):
    def __init__(self, decision, code, detail):
        self.decision = decision
        self.code = code
        self.detail = detail
        super().__init__(f"{decision}:{code}: {detail}")


def _allow(detail):
    raise Verdict(Decision.ALLOW, "RECOGNIZED_SAFE", detail)


def _deny(code, detail):
    raise Verdict(Decision.DENY, code, detail)


# ---------------------------------------------------------------------------
# Class A — safe read-only command families
# ---------------------------------------------------------------------------

_GIT_STATUS_FLAGS = {"-s", "--short", "-b", "--branch", "--porcelain"}
_GIT_LOG_FLAGS = {
    "--oneline", "--stat", "--graph", "--all", "-p", "--name-only",
    "--name-status", "--decorate",
}
_GIT_DIFF_FLAGS = {"--stat", "--name-only", "--name-status", "--cached"}
_GIT_SHOW_FLAGS = {"--stat", "--name-only"}
_GIT_REVPARSE_FLAGS = {"--short", "--verify", "--is-inside-work-tree"}
_GIT_LSFILES_FLAGS = {"-m", "-o", "--others", "--exclude-standard"}
_GIT_BRANCH_LIST_FLAGS = {"-a", "-r", "-v", "-vv", "--list"}
_GIT_FETCH_FLAGS = {"--quiet", "-q"}

_LOG_FORMAT_FLAG_RE = re.compile(r"^--format=[A-Za-z0-9%_ .:-]+$")


def _numeric_or_flag(tok, allowed):
    return bool(
        tok in allowed
        or re.match(r"^-\d+$", tok)
        or re.match(r"^--max-count=\d+$", tok)
        or _LOG_FORMAT_FLAG_RE.match(tok)
    )


def _trailing_pathspec_ok(positionals):
    """For `log`/`diff`: positionals are allowed only as an optional
    single ref (safe ref charset) optionally followed by `--` and then
    safe relative paths — this is what lets `git diff HEAD~1 -- knowledge/`
    work without opening up arbitrary positional content."""
    if not positionals:
        return True
    if "--" in positionals:
        idx = positionals.index("--")
        refs, paths = positionals[:idx], positionals[idx + 1 :]
    else:
        refs, paths = positionals, []
    if len(refs) > 1:
        return False
    if refs and not _is_safe_ref_or_remote(refs[0]):
        return False
    return all(_is_safe_relative_path(p) for p in paths)


def _git_readonly(subcommand, rest):
    flags, positionals = _split_flags_positionals(rest)

    if subcommand == "status":
        if all(f in _GIT_STATUS_FLAGS for f in flags) and not positionals:
            _allow("git status")
        return
    if subcommand == "log":
        if all(_numeric_or_flag(f, _GIT_LOG_FLAGS) for f in flags) and _trailing_pathspec_ok(positionals):
            _allow("git log")
        return
    if subcommand == "diff":
        if all(f in _GIT_DIFF_FLAGS for f in flags) and _trailing_pathspec_ok(positionals):
            _allow("git diff")
        return
    if subcommand == "show":
        if all(f in _GIT_SHOW_FLAGS for f in flags) and len(positionals) <= 1 and (
            not positionals or _is_safe_ref_or_remote(positionals[0])
        ):
            _allow("git show")
        return
    if subcommand == "rev-parse":
        if all(f in _GIT_REVPARSE_FLAGS for f in flags) and len(positionals) <= 1 and (
            not positionals or _is_safe_ref_or_remote(positionals[0])
        ):
            _allow("git rev-parse")
        return
    if subcommand == "ls-files":
        if all(f in _GIT_LSFILES_FLAGS for f in flags) and not positionals:
            _allow("git ls-files")
        return
    if subcommand == "branch":
        if not flags and not positionals:
            _allow("git branch (list)")
        if flags and all(f in _GIT_BRANCH_LIST_FLAGS for f in flags) and not positionals:
            _allow("git branch (list, flagged)")
        return
    if subcommand == "remote":
        if flags == ["-v"] and not positionals:
            _allow("git remote -v")
        if not flags and 1 <= len(positionals) <= 2 and positionals[0] == "show" and all(
            _is_safe_ref_or_remote(p) for p in positionals[1:]
        ):
            _allow("git remote show")
        return
    if subcommand == "fetch":
        if all(f in _GIT_FETCH_FLAGS for f in flags) and len(positionals) <= 2 and all(
            _is_safe_ref_or_remote(p) for p in positionals
        ):
            _allow("git fetch (scoped)")
        return
    if subcommand == "worktree":
        if positionals[:1] == ["list"] and not flags:
            _allow("git worktree list")
        return
    if subcommand == "stash":
        if positionals[:1] == ["list"] and not flags:
            _allow("git stash list")
        return


_FIND_VALUE_FLAGS = {"-name", "-iname", "-type", "-maxdepth", "-mindepth", "-newer"}
_FIND_BARE_FLAGS = {"-print", "-print0"}


def _find_readonly(tokens):
    """Walks find's own grammar rather than a blanket flags/positionals
    split: a value-taking flag's value (e.g. -name's pattern) may
    legitimately contain wildcard characters (`*.py`) and is NOT path-
    checked, but any OTHER bare positional — the search root, or any
    stray positional — must be a safe literal path. RR-2 P0-1: a bare
    positional like `*` is exactly what a real shell glob-expands before
    find ever sees it (potentially into a filename that IS a flag, e.g.
    a file named `-delete`); this guard cannot see that expansion, so it
    must refuse to accept an unexplained bare glob/wildcard token in the
    first place rather than try to guess what it might expand to."""
    i, n = 0, len(tokens)
    while i < n:
        t = tokens[i]
        if t.startswith("-"):
            if t in _FIND_VALUE_FLAGS:
                if i + 1 >= n:
                    return  # dangling flag with no value
                i += 2
                continue
            if t in _FIND_BARE_FLAGS:
                i += 1
                continue
            return  # unrecognized flag (-delete/-exec/-execdir/-fprint*/-ok* etc.)
        else:
            if not _is_safe_relative_path(t):
                return
            i += 1
    _allow("find (read-only predicates only)")


def _shasum_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    for f in flags:
        if f != "-a" and not re.match(r"^-a\d+$", f):
            return
    if not all(_is_safe_relative_path(p) for p in positionals):
        return
    if positionals or "-a" in flags:
        _allow("shasum")


_SIMPLE_SHORT_FLAG_RE = re.compile(r"^-[a-zA-Z0-9]+$")
_SIMPLE_LONG_FLAG_RE = re.compile(r"^--[a-z][a-z0-9-]*$")


def _generic_readonly_flags_ok(flags):
    return all(_SIMPLE_SHORT_FLAG_RE.match(f) or _SIMPLE_LONG_FLAG_RE.match(f) for f in flags)


def _ls_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if _generic_readonly_flags_ok(flags) and all(_is_safe_relative_path(p) for p in positionals):
        _allow("ls")


def _cat_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if _generic_readonly_flags_ok(flags) and positionals and all(_is_safe_relative_path(p) for p in positionals):
        _allow("cat")


def _head_tail_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    for f in flags:
        if f not in ("-n", "-c") and not re.match(r"^-n\d+$", f) and not re.match(r"^-\d+$", f):
            return
    if positionals and all(_is_safe_relative_path(p) for p in positionals):
        _allow("head/tail")


def _wc_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if all(f in ("-l", "-w", "-c", "-m") for f in flags) and positionals and all(
        _is_safe_relative_path(p) for p in positionals
    ):
        _allow("wc")


def _pwd_readonly(tokens):
    if not tokens:
        _allow("pwd")


def _stat_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if _generic_readonly_flags_ok(flags) and positionals and all(_is_safe_relative_path(p) for p in positionals):
        _allow("stat")


def _grep_readonly(tokens):
    flags, positionals = _split_flags_positionals(tokens)
    if not _generic_readonly_flags_ok(flags):
        return
    if "-f" in flags:
        # -f's value is a PATTERN FILE — a path, not search text — so
        # every positional must be path-checked in this mode (RR-2 P2-2).
        if positionals and all(_is_safe_relative_path(p) for p in positionals):
            _allow("grep -f (pattern file)")
        return
    # pattern + at least one explicit path — no implicit stdin reads,
    # since Stage 1 already forbids piping data into this process. Only
    # the path arguments (not the search pattern itself) are restricted
    # to repo-relative — the pattern is search text, not a filesystem
    # location.
    if len(positionals) >= 2 and all(_is_safe_relative_path(p) for p in positionals[1:]):
        _allow("grep")


# Fixed allowlist of project-owned validator/checker scripts. Arguments
# after the script path are passed through unrestricted (Stage 1 already
# guarantees they carry no shell composition) — they are runtime
# parameters to an already-trusted, fixed script, not attacker-
# controlled code paths. Adding a new script here is a reviewable,
# one-line change, not a parsing exercise.
_ALLOWED_PYTHON_SCRIPTS = {
    "knowledge/00-System/validate_capabilities.py",
    "knowledge/00-System/verify_baselines.py",
    "knowledge/05-QA/tools/mr_verify.py",
    "knowledge/05-QA/tools/resolution_bound.py",
    "knowledge/03-Modules/MOD-000/scenario-catalog/tools/validate_catalog.py",
    "knowledge/03-Modules/MOD-000/evidence/scenario-execution/phase3/tools/evidence_integrity_check.py",
    ".claude/security/tests/test_bash_guard.py",
}


def _python_readonly(tokens):
    if not tokens:
        return
    script = tokens[0]
    normalized = script[2:] if script.startswith("./") else script
    if normalized in _ALLOWED_PYTHON_SCRIPTS:
        _allow(f"python3 {normalized} (allowlisted validator script)")


_READONLY_DISPATCH = {
    "find": _find_readonly,
    "shasum": _shasum_readonly,
    "ls": _ls_readonly,
    "cat": _cat_readonly,
    "head": _head_tail_readonly,
    "tail": _head_tail_readonly,
    "wc": _wc_readonly,
    "pwd": _pwd_readonly,
    "stat": _stat_readonly,
    "grep": _grep_readonly,
    "python3": _python_readonly,
}


# ---------------------------------------------------------------------------
# Class B — narrowly governed mutations
# ---------------------------------------------------------------------------


def _git_add(rest):
    flags, positionals = _split_flags_positionals(rest)
    if flags:
        return  # no flags at all — specifically excludes -A/--all/-u
    if not positionals or any(p == "." for p in positionals):
        return  # require concrete paths, not "." (project convention:
        # never `git add -A`/`.` — stage specific files by name)
    # Every positional must be a literal safe relative path (rejects
    # ":/" pathspec magic, unquoted globs git itself would expand like
    # ".claude/*", "..", "//", and the shlex/shell $'...' divergence —
    # RR-1 P0-1/P1-1/P2-2) AND must not be, or normalize under, a
    # protected location (RR-1 P1-1's bare "git add .claude").
    if not all(_is_safe_relative_path(p) for p in positionals):
        return
    if any(_is_protected_path(p) for p in positionals):
        return
    _allow("git add <specific paths>")


def _git_commit(rest):
    if len(rest) == 2 and rest[0] == "-m":
        _allow("git commit -m <message>")
    if len(rest) == 2 and rest[0] == "-F":
        # Structural fix for the project's mandated multi-line/
        # attribution-trailer commit format (RR-1 P1-2): the message
        # content lives in a file (written beforehand via the Write
        # tool, never through this Bash command string), so the actual
        # Bash call stays a short, Stage-1-clean single line regardless
        # of how long or how many special characters the message has.
        path = rest[1]
        if _is_safe_relative_path(path) and not _is_protected_path(path):
            _allow("git commit -F <file>")


def _git_checkout_branch(rest):
    # Only the branch-creation shape — never plain `checkout <ref>` or
    # `checkout -- <path>`, which would let this family double as an
    # unreviewed content-overwrite mechanism.
    if len(rest) == 2 and rest[0] == "-b" and _is_safe_ref_or_remote(rest[1]):
        _allow("git checkout -b <new-branch>")


def _git_push(rest):
    flags, positionals = _split_flags_positionals(rest)
    if flags:
        return  # no flags at all — specifically excludes -f/--force/--delete/--mirror/etc.
    if len(positionals) > 2:
        return
    # Reject refspec syntax outright (RR-1 P0-1): git expresses force
    # ("+branch") and delete (":branch") as POSITIONAL text, not flags,
    # so excluding flags alone does not exclude them — the charset check
    # does, since neither "+" nor ":" is in it.
    if not all(_is_safe_ref_or_remote(p) for p in positionals):
        return
    _allow("git push [<remote> [<branch>]]")


def _mkdir(tokens):
    if tokens[:1] != ["-p"]:
        return
    rest = tokens[1:]
    if len(rest) != 1:
        return
    path = rest[0]
    if not _is_safe_relative_path(path):
        return  # rejects "..", "//", pathspec/glob-magic characters
    if _is_protected_path(path):
        return
    if not path.startswith("knowledge/"):
        return  # governed mutation scope: evidence tree only
    _allow("mkdir -p knowledge/... (evidence tree only)")


_GIT_MUTATION_DISPATCH = {
    "add": _git_add,
    "commit": _git_commit,
    "push": _git_push,
    "checkout": _git_checkout_branch,
}

_MUTATION_DISPATCH = {
    "mkdir": _mkdir,
}


# ---------------------------------------------------------------------------
# Top-level classification
# ---------------------------------------------------------------------------


def classify(raw_command):
    """Raises Verdict (ALLOW or DENY) for every input — there is no
    third path. Callers must always act on the raised Verdict."""
    if _has_shell_composition(raw_command):
        _deny("UNSUPPORTED_SHELL_COMPOSITION", "command contains chaining/redirection/substitution syntax")

    try:
        tokens = shlex.split(raw_command, posix=True)
    except ValueError as e:
        _deny("PARSE_FAILURE_FAIL_CLOSED", f"could not tokenize command: {e!r}")

    if not tokens:
        _deny("UNKNOWN_COMMAND", "empty command")

    cmd, rest = tokens[0], tokens[1:]

    if cmd == "git":
        if not rest:
            _deny("UNRECOGNIZED_SUBCOMMAND", "git with no subcommand")
        subcommand, git_rest = rest[0], rest[1:]
        if subcommand in _GIT_MUTATION_DISPATCH:
            _GIT_MUTATION_DISPATCH[subcommand](git_rest)
            _deny("DISALLOWED_FLAG_OR_SHAPE", f"git {subcommand} did not match its governed-mutation shape")
        _git_readonly(subcommand, git_rest)
        _deny("UNRECOGNIZED_SUBCOMMAND", f"git {subcommand} is not an allowlisted read-only subcommand/shape")

    if cmd in _MUTATION_DISPATCH:
        _MUTATION_DISPATCH[cmd](rest)
        _deny("DISALLOWED_FLAG_OR_SHAPE", f"{cmd} did not match its governed-mutation shape")

    if cmd in _READONLY_DISPATCH:
        _READONLY_DISPATCH[cmd](rest)
        _deny("DISALLOWED_FLAG_OR_SHAPE", f"{cmd} did not match its allowlisted read-only shape")

    _deny("UNKNOWN_COMMAND", f"{cmd!r} is not an allowlisted command")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _emit(decision, code, detail):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": (
                        f"ALLOWED: {detail}" if decision == Decision.ALLOW else f"BLOCKED: {code} — {detail}"
                    ),
                }
            }
        )
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # cannot even read a JSON payload — nothing to classify

    # Everything past this point concerns a payload we successfully
    # parsed as JSON. RR-1 P2-5: a payload that parses but isn't the
    # expected dict shape (e.g. a bare JSON array/string/number) must
    # not be allowed to raise an uncaught exception here — an uncaught
    # exception exits non-zero with no JSON on stdout, which per the
    # hook contract is non-blocking and lets the tool call proceed
    # (fail OPEN). Every path below either exits silently (genuinely
    # not a Bash call) or emits an explicit decision — never a bare
    # crash.
    try:
        if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
            sys.exit(0)

        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str) or not command.strip():
            _emit(Decision.DENY, "UNKNOWN_COMMAND", "empty or non-string command")
            sys.exit(0)

        classify(command)
        # classify() always raises Verdict — reaching here is a bug in
        # this file, not a valid state. Fail closed rather than allow.
        _emit(Decision.DENY, "GUARD_INTERNAL_ERROR", "classify() returned without a verdict")
    except Verdict as v:
        _emit(v.decision, v.code, v.detail)
    except SystemExit:
        raise
    except Exception as e:
        _emit(Decision.DENY, "GUARD_INTERNAL_ERROR", f"unexpected error: {e!r}")

    sys.exit(0)


if __name__ == "__main__":
    main()
