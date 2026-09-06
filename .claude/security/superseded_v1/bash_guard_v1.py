#!/usr/bin/env python3
"""PreToolUse Bash security guard for Veyro MOD-000 (BUG-013/022/023).

Reads the PreToolUse JSON payload on stdin (verified contract:
knowledge/03-Modules/MOD-000/evidence/security/HOOK_CONTRACT_VERIFICATION_2026-09-06.md),
normalizes the requested Bash command past common wrappers, and denies a
fixed set of destructive/protected-path operations regardless of that
surface variation.

Contract: prints nothing and exits 0 when it finds no violation (normal
`.claude/settings.json` permission flow then applies unchanged — this
guard is additive, not a replacement). Prints a `hookSpecificOutput`
JSON with `permissionDecision: "deny"` and exits 0 when it denies.
Never exits 2 (an exit-2 hard block is indistinguishable from a guard
crash; this module always emits an inspectable JSON reason instead,
including on its own fail-closed path).

REVISION HISTORY:

RR-1 (2026-09-06): a first version of this guard was reviewed by a
fresh-context `veyro-security-reviewer` and found to have 5 P0 and 5 P1
bypasses, all in the command-*segmentation* layer beneath an otherwise-
sound normalization spine (absolute-path resolution, env/command
unwrapping, git global-option skipping, $() recursion, flag-character
bundling). Closed: newline-separated commands silently merging,
reserved-word/grouping punctuation being treated as an unrecognized
command name instead of an unmodeled construct, interpreter/wrapper
delegation being entirely unhandled (`bash -c`, `sh -c`, `eval`,
`xargs`, `sudo`, `timeout`, `env -S`), backslash line-continuation
splitting one command into two, `cd`-then-relative-path defeating
protected-path checks, plus P1s (narrower redirection operators,
`perl -pi`, glob/brace path evasion, several git subcommand gaps,
heredoc bodies mis-tokenized as shell code tripping the fail-closed
path on ordinary prose apostrophes).

RR-2 (2026-09-06): a second, independent fresh-context review of the
RR-1 fixes found 5 more P0 and 6 more P1 findings, plus a structural
critique: enumerating "bad" command/wrapper names is inherently
incomplete (each round finds fresh missing names) versus an allowlist-
of-known-safe-shapes design — noted here as accepted residual
architecture risk, not fixed by inverting the model this round (that
would require re-deriving a safe-command allowlist broad enough not to
cripple this repo's routine engineering workflow, which is a materially
larger undertaking; the wrapper/interpreter denylist below was instead
substantially widened). Closed: `$VAR`/`${VAR}` command names now FAIL
CLOSED instead of silently passing through (this was the sharpest
finding — it had bypassed the entire wrapper denylist in one token);
case-sensitive protected-path matching on a case-insensitive filesystem;
`cd`'s flag arguments (`-P`, `--`, ...) poisoning the virtual-cwd
tracker; `find -exec`/`-execdir` now recurses its executed command
through this same guard's full analysis instead of checking a 5-name
list (closes arbitrary `find -exec sh -c '...'`-shaped execution); the
wrapper denylist widened substantially (`nice`, `ionice`, `setsid`,
`caffeinate`, `arch`, `chroot`, `flock`, `script`, `parallel`, `ssh`,
`su`, `doas`, `osascript`, `csh`/`tcsh`/`fish`/`busybox`, the whole
`awk`/`gawk`/`nawk`/`mawk` family, `pushd`/`popd`); the write-primitive
set widened (`ln`, `install`, `rsync`, `patch`, `ditto`, `tar`, `unzip`,
`gzip`/`gunzip`, `shred`, `chmod`/`chown`/`chattr`); interpreter code-
evaluation denial now also covers stdin-fed code (heredoc/here-string/
explicit `-`/no script argument at all), not just `-c`/`-e`; `git
checkout`/`git restore` with an explicit protected-path argument (not
just whole-tree `.`) now denied; `git config alias.x '!<shell>'`
(persistent alias) now recurses the same way the transient `-c
alias.x=!<shell>` form already did; this guard's own directory
(`.claude/security/**`) and `.claude/settings.local.json` added to the
protected-path set. **The most consequential fix was to the reserved-
word check itself**: RR-1's version matched shlex *tokens* (which have
already had quotes stripped), so `grep -n 'if' file` or `echo done`
were wrongly denied — a real, disruptive false-positive class. It now
matches raw (unquoted, un-stripped) text in first-word-of-segment
position only, via `_check_unmodeled_raw_constructs`/
`_raw_whitespace_words`, so a quoted argument that merely spells a
keyword is never confused with the keyword used syntactically.

RR-3 (2026-09-06): a third independent fresh-context review of the RR-2
fixes found 4 more P0 and 5 more P1 findings, each verified to actually
execute in the real shell. **This session's own attached shell is zsh
5.9, not bash** — the review's most important structural finding — and
several fixes below close zsh-specific gaps the guard's bash-oriented
design had missed by construction, not by omission. Closed this round:
a leading redirection (`>/dev/null rm -rf x`, `2>/dev/null git reset
--hard`) putting the redirect operator itself in the command-name
position, which matched no rule and silently allowed whatever followed
it (`_strip_leading_redirections`, called after tokenizing each
segment); `_split_raw_by_chain_operators`'s greedy character-class scan
absorbing a real chain operator into what it mistook for one
redirection run (`echo hi >&2|rm -rf x` denied nothing because the `|`
was swallowed into the same "run" as `>&2` and never seen as a split
point) — replaced with `_match_redirect_operator`, which matches one
exact operator spelling from `_REDIRECT_OPERATOR_FORMS` and stops,
leaving anything after it for the next pass; zsh precommand modifiers
`noglob`/`nocorrect` and zsh reserved words `repeat`/`coproc` added to
the wrapper denylist; `time` added to the wrapper denylist too (it was
only in the raw-text reserved-word list, so `/usr/bin/time`, `command
time`, and `env time` — all of which reach the guard as logical command
`time` via normal resolution, not as a raw first word — went
unrecognized; the two lists had drifted apart); `git -c
diff.external=...`/`core.sshCommand=...`/etc. and the `git config`
long-form equivalent now recurse into the value as an embedded shell
command the same way the `alias.x=!...` form already did (git executes
several config values directly, unconditionally on some — `diff.external`
— and only interactively on others — `core.pager`/`core.editor` — but
this guard denies both classes alike rather than trying to model git's
own TTY-dependent invocation conditions); `git -C <dir>` is now threaded
into the `checkout`/`restore` protected-path check via a dedicated
`VirtualCwd` seeded from the resolved `-C` target (it was previously
consumed and discarded, so `git -C .claude checkout HEAD -- settings.json`
resolved `settings.json` against the call's original cwd, missing the
match); `cd -` (bash/zsh's "previous directory" marker, which this guard
cannot resolve) no longer poisons `VirtualCwd` with the literal string
`-` as a path component; `scp`/`sftp`/`tmux`/`screen`/`expect` added to
the wrapper denylist.

**Left genuinely OPEN this round — do not treat this guard as having
closed BUG-013/022/023 until these are resolved and a further
independent review confirms clean, per this project's standing
discipline of never declaring a security gate PASS while a known P0/P1
remains:**

  - **P0 (heredoc live-expansion):** `_strip_heredocs` deletes an entire
    heredoc body unconditionally, but a body under an UNQUOTED (or
    `<<-` unquoted) delimiter is a live shell-expansion context — `cat
    <<EOF` / `` `rm -rf x` ``/`$(rm -rf x)` inside that body executes in
    the real shell and is never seen by this guard, because the body is
    discarded before `_extract_substitutions` ever runs over it. The
    quoted-delimiter form (`<<'EOF'`) is correctly inert in the shell and
    correctly allowed; the guard cannot currently tell the two cases
    apart before discarding the body (delimiter-quoting IS captured by
    `_HEREDOC_RE`'s first group, just not yet acted on).
  - **P1 (ancestor-directory operations):** protected-path matching is
    per-listed-path, not per-subtree — `mv .claude /tmp/junk`, `cp -r
    .claude /tmp/exfil`, `tar -czf x.tgz .claude`, and `chmod -R 000
    .claude` all relocate/exfiltrate/lock every protected path under
    `.claude/` in one call without ever matching a fragment string
    directly (only `rm -rf .claude` is caught, incidentally, by the
    blanket recursive-rm rule).
  - **P1 (inline interpreter code via `-m`):** the stdin-feeding check
    for python/node/ruby/perl looks for missing script arguments or a
    `<`-containing argument; it does not catch `python3 -m timeit
    "<code>"`-shaped inline code passed as a plain positional argument
    to a module runner, which is semantically the same risk `-c` is
    blanket-denied for.
  - Several P2s from this round were not acted on: `PRODUCTION_ACTION`'s
    plain-substring match denies read-only greps for the word
    "production" (pre-existing, inherited policy, not new); brace-
    expansion false positives on ordinary idioms like `cp file{,.bak}`;
    a read-then-network-exfiltration path (`cat .claude/settings.json |
    curl ...`) is open while read-then-copy is closed; `#`-comments are
    not stripped before raw-text scanning, so a comment mentioning a
    redirect can trip `PROTECTED_PATH_MUTATION` on an otherwise-harmless
    line.

RR-4 (2026-09-06): a fourth independent fresh-context review re-verified
the three RR-3-disclosed open items as real and accurately described,
and found 3 more P0 and 3 more P1 beyond them (the reviewer also
accidentally executed part of a heredoc test payload as real commands
against this repo during testing — self-detected, self-restored via `mv`
and `git checkout --`, and independently re-verified clean by the
orchestrating session before continuing: `git status` byte-identical to
before, `CLAUDE.md`/`CAPABILITY_POLICY.md` zero-diff against HEAD, 194
tests still passing). Closed this round: command-*name* matching is now
case-insensitive (`_resolve_logical_command` lowercases its result) —
`RM -rf x`, `GIT reset --hard`, `Bash -c ...` all resolve and execute
identically to their lowercase spellings on this filesystem/PATH, the
same reasoning already applied to protected-*path* matching but missed
for command names; `builtin` (the `command` builtin's sibling
precommand modifier) added to the wrapper denylist (`builtin eval
'...'` reached analysis as an unrecognized logical name).

**Left OPEN, on top of the three items already disclosed under RR-3
(heredoc live-expansion, ancestor-directory operations, `python -m`
inline code) — this guard has now been through FOUR independent review
rounds and every one has found at least one new P0. That pattern is
itself the load-bearing fact: do not treat the absence of a fifth
round's findings as evidence there are none.**

  - **P0: zsh clobber/append redirection spellings** (`>!`, `>>!`,
    `>>&`, `&>!`, `&>|`) are not in `_REDIRECT_OPERATOR_FORMS` /
    `_REDIRECT_OP_CHARS`, so they both hide a leading command name
    (`>! /tmp/o rm -rf x`) and fail to protect a redirection target
    (`echo x >! .claude/settings.json`) — verified executing against
    this session's actual zsh 5.9.
  - **P1: several more git config keys execute their value as a shell
    command** beyond what `_GIT_SHELL_VALUE_KEY_RE` covers —
    `core.fsmonitor` (fires unconditionally, unlike the already-covered
    `core.pager`/`core.editor`), `difftool.*.cmd`, `mergetool.*.cmd`,
    `gpg.program`, and `git --config-env=key=ENVVAR` is consumed by the
    generic `--opt=value` skip branch without ever reaching the
    shell-value-key check at all.
  - **P1: the protected-path set omits files with equal or greater
    behavioral authority than what IS protected** — `CLAUDE.md` (root
    project instructions, same authority class as the already-protected
    `.claude/rules/**`), `.mcp.json`, and the governance documents this
    guard's own design record depends on
    (`knowledge/00-System/DEVELOPMENT_CONSTITUTION.md`,
    `CAPABILITY_POLICY.md`) are all currently unprotected.

HONEST SCOPE LIMITS (do not remove without updating the durable record
in knowledge/03-Modules/MOD-000/evidence/bugs/BUG-022-*.md and
BUG-023-*.md — this list is normative, not decorative):

  - This is not a full POSIX shell parser and does not attempt to be
    one. Grouping/subshell punctuation (`(...)`, `{ ...; }` — but not
    `${VAR}` parameter expansion or find's adjacent `{}` placeholder,
    both explicitly carved out) and a fixed set of reserved words/
    wrapper commands are denied outright when found; anything NOT in
    those enumerations is passed through unanalyzed. This is an
    enumeration, not a parser, and per RR-2's structural critique should
    be assumed incomplete — treat every new wrapper/interpreter/shell
    binary this repo starts using as a candidate gap to add, not as
    proof the list is done.
  - `$VAR`/`${VAR}` as the command name itself is denied
    (UNSUPPORTED_CONSTRUCT_WRAPPER) rather than resolved — this guard
    does not track shell variable values, so it cannot tell
    `$MY_TOOL --version` (harmless) from `$SHELL -c '...'` (arbitrary
    execution) apart, and fails closed rather than guess.
  - `$()`/backtick substitution is extracted and recursively analyzed
    one level deep. A substitution nested inside another substitution's
    text is not unwrapped a second time; nesting of that kind is itself
    a punctuation form (`(`) this guard denies outright once reached, so
    it fails closed rather than silently missing it — but this has not
    been exhaustively verified for every nesting shape.
  - Interpreter code-evaluation is blanket-denied for
    python/python2/python3/node/ruby/perl whenever an eval-style flag is
    present, OR whenever the interpreter has no script-file argument at
    all (empty, `-`, or any argument containing `<` — covering plain
    stdin, `<<<` here-strings, and heredocs) — regardless of what the
    code does; this guard does not analyze interpreted code. Running a
    script *file* (`python3 script.py`) is not blocked and is not
    analyzed; whatever that file does is outside this guard's reach.
    Known imprecision: the stdin-fed check treats ANY argument
    containing `<` as stdin-feeding, so `python3 -m json.tool < in.json`
    (module mode, reading data not code, from a file not stdin-as-code)
    is also denied — a false positive accepted in favor of not having to
    distinguish "code" input from "data" input on the redirection target
    alone.
  - `cd` tracking is a same-command approximation: a `cd DIR` inside the
    same chained command (`cd DIR && ...`, `cd DIR; ...`) updates a
    virtual working directory used to resolve later relative paths in
    *that same command*, seeded from the real `cwd` the hook payload
    reports for this call. Only `cd`'s first non-flag argument is used
    as the target (flags like `-P`/`-L`/`--` are skipped); `cd $(...)`
    (a dynamic target) resolves to the literal substitution placeholder
    text, not a real path, which effectively (and intentionally) makes
    later relative-path checks in that segment untrustworthy — this is
    accepted as a known imprecision rather than specifically fixed,
    since the underlying `$()` content is still independently analyzed
    as its own command by the existing substitution recursion. `cd`
    inside a pipeline stage (`|`) or a separate prior Bash tool call is
    not tracked beyond what the harness itself already reports as `cwd`.
  - Protected-path matching is case-insensitive (this repo lives on a
    case-insensitive-but-preserving filesystem) and glob/brace-aware:
    single-level, non-nested brace expansion, plus
    `glob.glob(..., recursive=True)` against the real filesystem from
    the resolved (real-or-virtual) working directory. A glob that
    matches nothing on disk right now (e.g. a redirection target that
    would *create* a new protected-looking path via an unresolvable
    pattern) falls back to the plain substring check only. Path
    normalization is textual (`os.path.normpath`/`os.path.join`); it
    does not resolve symlinks, `~`, or `$HOME`/`$PWD` environment
    variables appearing inside a path argument.
  - Quote-aware scanning (physical-line splitting, chain-operator
    splitting, redirection-operator detection, reserved-word detection)
    handles single quotes, double quotes with backslash escapes inside
    them, and a bare backslash escaping the next character outside
    quotes. It does not implement `$'...'` ANSI-C quoting semantics
    beyond treating it as a normal single-quoted-ish span.
  - Heredoc bodies (`<<DELIM ... DELIM`) are stripped out before
    tokenization (so ordinary prose apostrophes in a heredoc body do
    not trip the parser) and are not analyzed for protected-path
    content — except when the heredoc is feeding an interpreter's stdin
    (see the interpreter bullet above, which does catch that case, just
    not by reading the body). Only the heredoc's *command line*
    (including any redirection on that same line) is analyzed. Nested/
    multiple heredocs in one command are stripped iteratively, bounded
    to 10 iterations.
  - `find -exec`/`-execdir`'s own command is fully re-analyzed by this
    same guard (wrapper denylist, git logic, protected-path checks all
    apply), and `rm`/`shred`/`truncate`/`dd`/`find`/`mv` there are always
    denied regardless of flags (an iterative bulk operation over find's
    matches, not a single bounded call). Any OTHER command reached via
    `-exec` that is not in this guard's handled set (e.g. a bespoke
    binary) is not specifically analyzed beyond the wrapper/reserved-word
    checks, same as at the top level.
"""
import glob
import json
import os
import re
import shlex
import sys

# ---------------------------------------------------------------------------
# Stage 1 — raw-text preprocessing: heredocs, line continuation
# ---------------------------------------------------------------------------

_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n(.*?)\n[ \t]*\2\b", re.DOTALL)


def _strip_heredocs(text):
    def repl(m):
        quote, delim, restline = m.group(1), m.group(2), m.group(3)
        return f"<<{quote}{delim}{quote}{restline}"

    current = text
    for _ in range(10):  # bounded: multiple/nested-looking heredocs
        nxt = _HEREDOC_RE.sub(repl, current, count=1)
        if nxt == current:
            break
        current = nxt
    return current


def _join_line_continuations(text):
    return re.sub(r"\\\n", " ", text)


# ---------------------------------------------------------------------------
# Stage 2 — quote-aware scanning primitives (shared by line-splitting and
# redirection detection so both agree on what is "inside a quote")
# ---------------------------------------------------------------------------


def _quote_mask(text):
    """Return a list of bool, True where text[i] is unquoted AND not an
    escaped literal (i.e. syntactically live shell metacharacter
    territory). Handles '...' (no escapes), "..." (backslash escapes),
    and a bare backslash outside quotes escaping the next character."""
    mask = [False] * len(text)
    i = 0
    n = len(text)
    in_single = False
    in_double = False
    while i < n:
        c = text[i]
        if in_single:
            if c == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == '"':
                in_double = False
            i += 1
            continue
        # unquoted context
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "'":
            in_single = True
            i += 1
            continue
        if c == '"':
            in_double = True
            i += 1
            continue
        mask[i] = True
        i += 1
    return mask


def _split_physical_lines(text):
    """Split on real newlines that are outside any quote."""
    mask = _quote_mask(text)
    lines = []
    buf = []
    for i, c in enumerate(text):
        if c == "\n" and mask[i]:
            lines.append("".join(buf))
            buf = []
        else:
            buf.append(c)
    lines.append("".join(buf))
    return lines


_REDIRECT_OP_CHARS = set("<>&|")


def _find_unquoted_redirect_targets(line):
    """Scan one physical line for unquoted output-redirection operators
    (>, >>, >|, &>, &>>, >&, and digit-prefixed forms like 2>, 1>>) and
    return the quote-stripped word immediately following each, using the
    same quote-state machine as line splitting (so a quoted '>' is never
    mistaken for an operator)."""
    mask = _quote_mask(line)
    n = len(line)
    targets = []
    i = 0
    while i < n:
        if mask[i] and (line[i] in _REDIRECT_OP_CHARS or line[i].isdigit()):
            j = i
            while j < n and mask[j] and (line[j].isdigit() or line[j] in _REDIRECT_OP_CHARS):
                j += 1
            op = line[i:j]
            if ">" in op and j > i:
                # skip unquoted whitespace
                k = j
                while k < n and mask[k] and line[k] in " \t":
                    k += 1
                # collect the target word (quote-aware, quotes stripped)
                word_chars = []
                in_single = in_double = False
                while k < n:
                    c = line[k]
                    if in_single:
                        if c == "'":
                            in_single = False
                            k += 1
                            continue
                        word_chars.append(c)
                        k += 1
                        continue
                    if in_double:
                        if c == "\\" and k + 1 < n:
                            word_chars.append(line[k + 1])
                            k += 2
                            continue
                        if c == '"':
                            in_double = False
                            k += 1
                            continue
                        word_chars.append(c)
                        k += 1
                        continue
                    if c == "'":
                        in_single = True
                        k += 1
                        continue
                    if c == '"':
                        in_double = True
                        k += 1
                        continue
                    if c in " \t":
                        break
                    if mask[k] and c in _REDIRECT_OP_CHARS:
                        break
                    word_chars.append(c)
                    k += 1
                if word_chars:
                    targets.append("".join(word_chars))
            i = j if j > i else i + 1
        else:
            i += 1
    return targets


# ---------------------------------------------------------------------------
# Stage 3 — tokenization for simple-command / logical-command analysis
# ---------------------------------------------------------------------------

_SUBST_RE = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")


def _extract_substitutions(command):
    found = []

    def _replace(m):
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        found.append(inner)
        return " __SUBST__ "

    return _SUBST_RE.sub(_replace, command), found


def _tokenize(command):
    """Raises ValueError on unbalanced quotes — callers must fail closed.

    Deliberately does NOT include '{'/'}'/'!' in punctuation_chars: '('/')'
    need forcible separation because `(cmd)` is commonly written with no
    surrounding space, but brace-grouping (`{ cmd; }`) requires spaces
    around both braces per bash syntax, and plain whitespace splitting
    already isolates them as their own tokens for the _UNMODELED_TOKENS
    check below. Forcing '{'/'}' apart here would instead break the
    extremely common `find ... -exec cmd {} \\;` idiom, whose `{}` is
    written with no space and must survive as one token.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&")
    lexer.whitespace_split = True
    return list(lexer)


# Exact redirection-operator spellings, longest first, so matching stops
# at the operator's real boundary instead of greedily swallowing whatever
# <>&| characters happen to follow it (RR-3 P0-2: a greedy run like
# ">&2|" used to absorb the trailing pipe into the "redirection", merging
# two commands into one never-analyzed segment — `echo hi >&2|rm -rf x`
# denied nothing because the `|` was never seen as a split point).
_REDIRECT_OPERATOR_FORMS = ["&>>", ">>", "<<<", "<<", "&>", ">&", ">|", "<", ">"]


def _match_redirect_operator(line, mask, pos):
    """If a valid redirection operator (optionally digit-prefixed, e.g.
    "2>>") starts at `pos`, return the index just past it; else None.
    Only ever consumes exactly one recognized operator spelling — never
    an unbounded run of <>&| characters."""
    n = len(line)
    j = pos
    while j < n and mask[j] and line[j].isdigit():
        j += 1
    for op in _REDIRECT_OPERATOR_FORMS:
        end = j + len(op)
        if line[j:end] == op and end <= n and all(mask[k] for k in range(j, end)):
            return end
    return None


def _split_raw_by_chain_operators(line):
    """Split one physical line into raw-text segments at unquoted chain
    operators (;, &&, ||, &, |), preserving order. Splitting at the raw
    (pre-tokenization) level — rather than tokenizing the whole line and
    then splitting tokens — is what lets `_check_redirection_targets` be
    run per-segment, in order, interleaved with `cd` effects from earlier
    segments in the same line (see VirtualCwd; this is the fix for the
    `cd DIR && ... > relative_path` ordering gap).

    At each position, a real redirection operator (`_match_redirect_operator`)
    is tried FIRST and consumed exactly — never more — so that whatever
    follows it (a chain operator, more text) is re-examined on its own.
    Only after that fails is a bare `&`/`|`/`&&`/`||` treated as a chain
    operator; ";" is handled separately, it never combines with anything."""
    mask = _quote_mask(line)
    n = len(line)
    segments = []
    start = 0
    i = 0
    while i < n:
        if mask[i] and line[i] == ";":
            segments.append(line[start:i])
            i += 1
            start = i
            continue
        if mask[i] and (line[i].isdigit() or line[i] in "<>&"):
            end = _match_redirect_operator(line, mask, i)
            if end is not None:
                i = end
                continue
        if mask[i] and line[i] in "&|":
            two = line[i : i + 2]
            if two in ("&&", "||") and i + 1 < n and mask[i + 1]:
                segments.append(line[start:i])
                i += 2
                start = i
                continue
            segments.append(line[start:i])
            i += 1
            start = i
            continue
        i += 1
    segments.append(line[start:])
    return segments


# Shell keywords that mean "this is a construct this guard does not
# model" when they appear as the FIRST word of a chain-split segment
# (their only syntactically meaningful position — `then`/`do`/`done`/
# `fi`/`esac` etc. always open/continue/close a compound command there;
# elsewhere they are ordinary argument text, e.g. `echo done`).
_RESERVED_WORDS_FIRST_WORD_ONLY = {
    "if", "then", "else", "elif", "fi",
    "for", "while", "until", "do", "done",
    "case", "esac", "function", "select",
    "time", "!", "pushd", "popd",
}


def _raw_whitespace_words(line):
    """Quote-aware split on unquoted whitespace. Unlike shlex, quotes are
    NOT stripped from the returned words — a quoted 'if' comes back as
    "'if'" (or '"if"'), which can never equal the bare keyword "if". This
    is what lets the reserved-word check below distinguish a real
    syntactic keyword from a quoted argument that merely spells one."""
    mask = _quote_mask(line)
    words = []
    buf = []
    for i, c in enumerate(line):
        if mask[i] and c in " \t":
            if buf:
                words.append("".join(buf))
                buf = []
        else:
            buf.append(c)
    if buf:
        words.append("".join(buf))
    return words


def _check_unmodeled_raw_constructs(segment):
    """Raw-text (quote-aware, pre-tokenization) check for constructs this
    guard does not model: unquoted parenthesized grouping/subshells
    (`$()`/backticks are already extracted before this runs, so any
    remaining unquoted paren is real grouping syntax), unquoted brace
    grouping/expansion (`{ cmd; }`, `{a,b}` — but NOT `${VAR}` parameter
    expansion, and NOT find's adjacent `{}` placeholder, both explicitly
    carved out), and a reserved keyword in first-word position."""
    mask = _quote_mask(segment)
    n = len(segment)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        c = segment[i]
        if c in "()":
            raise Violation("UNSUPPORTED_CONSTRUCT", f"unquoted {c!r} (grouping/subshell) in: {segment!r}")
        if c == "{":
            if i > 0 and segment[i - 1] == "$":
                depth = 1
                j = i + 1
                while j < n and depth > 0:
                    if mask[j]:
                        if segment[j] == "{":
                            depth += 1
                        elif segment[j] == "}":
                            depth -= 1
                    j += 1
                i = j
                continue
            if i + 1 < n and segment[i + 1] == "}":
                i += 2  # find's `{}` placeholder — not a construct
                continue
            raise Violation("UNSUPPORTED_CONSTRUCT", f"unquoted brace grouping/expansion in: {segment!r}")
        if c == "}":
            raise Violation("UNSUPPORTED_CONSTRUCT", f"stray unquoted '}}' in: {segment!r}")
        i += 1

    words = _raw_whitespace_words(segment)
    if words and words[0] in _RESERVED_WORDS_FIRST_WORD_ONLY:
        raise Violation("UNSUPPORTED_CONSTRUCT", f"unmodeled shell keyword {words[0]!r} in: {segment!r}")

_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _strip_leading_assignments(words):
    i = 0
    while i < len(words) and _ASSIGNMENT_RE.match(words[i]):
        i += 1
    return words[i:]


def _strip_leading_redirections(tokens):
    """Strip leading `VAR=val` assignments and leading redirection
    operator+target pairs (in any order/repetition) from a tokenized
    simple command, so the real command word is what logical-command
    resolution sees next.

    RR-3 P0-1: a bare leading redirection (`>/dev/null rm -rf x`,
    `2>/dev/null git reset --hard`) put the redirection operator itself
    in `tokens[0]`, which resolved to a logical command name of `>` or a
    bare digit — matching no rule in this guard at all, so the real
    command after it was never analyzed. The redirection target itself
    is still checked separately by `_check_redirection_targets` on the
    raw segment; this function only concerns itself with finding the
    real command word."""
    i = 0
    n = len(tokens)
    while i < n:
        if _ASSIGNMENT_RE.match(tokens[i]):
            i += 1
            continue
        j = i
        while j < n and tokens[j].isdigit():
            j += 1
        matched = False
        for op in _REDIRECT_OPERATOR_FORMS:
            if j < n and tokens[j] == op:
                i = j + 2  # operator token + its target token
                matched = True
                break
        if matched:
            continue
        break
    return tokens[i:]


class _CannotResolve(Exception):
    pass


_ENV_SKIP_FLAGS_WITH_ARG = {"-u", "--unset"}
_ENV_UNSAFE_FLAGS = {"-S", "--split-string"}


def _unwrap_env(words):
    if not words or words[0] != "env":
        return words
    i = 1
    while i < len(words):
        w = words[i]
        if w in _ENV_UNSAFE_FLAGS:
            raise _CannotResolve("env -S/--split-string re-splits its argument; not safely resolvable")
        if _ASSIGNMENT_RE.match(w):
            i += 1
            continue
        if w in _ENV_SKIP_FLAGS_WITH_ARG:
            i += 2
            continue
        if w.startswith("-") and w != "-":
            i += 1
            continue
        break
    return words[i:]


def _unwrap_command_builtin(words):
    if not words or words[0] != "command":
        return words
    i = 1
    while i < len(words) and words[i].startswith("-") and words[i] != "-":
        i += 1
    return words[i:]


def _resolve_logical_command(words):
    """Unwrap env/command wrappers and resolve an absolute/relative path
    binary to its logical (basename) command name. May raise
    _CannotResolve (caller must fail closed)."""
    words = _strip_leading_assignments(words)
    changed = True
    while changed and words:
        changed = False
        new_words = _unwrap_env(words)
        if new_words != words:
            words = _strip_leading_assignments(new_words)
            changed = True
            continue
        new_words = _unwrap_command_builtin(words)
        if new_words != words:
            words = new_words
            changed = True

    if not words:
        return None, words

    first = words[0]
    if "$" in first:
        return None, words  # unresolved $VAR command name — documented limitation

    logical = first.rsplit("/", 1)[-1]
    if logical == ".":
        logical = "source"
    # RR-4 P0-N2: command-name matching must be case-insensitive on this
    # host's filesystem/PATH resolution — `RM -rf x`, `GIT reset --hard`,
    # `Bash -c ...` all resolve and execute exactly like their lowercase
    # spellings. Protected-*path* matching was already made case-
    # insensitive for the same reason (see `_plain_mentions_protected_path`);
    # this closes the same gap for command *names*, which had been missed.
    return logical.lower(), words


# Wrapper/interpreter-delegation commands this guard cannot safely see
# inside. Their mere use as the logical command of a simple command is
# fail-closed denied — see the "Interpreter/wrapper delegation" HONEST
# SCOPE LIMITS note above.
_WRAPPER_ALWAYS_DENY = {
    "bash", "sh", "zsh", "ksh", "dash", "csh", "tcsh", "fish", "busybox",
    "eval", "xargs", "sudo", "doas", "su", "timeout", "nohup",
    "watch", "stdbuf", "source", "exec", "nice", "ionice", "setsid",
    "caffeinate", "arch", "chroot", "flock", "script", "parallel", "ssh",
    "scp", "sftp", "osascript", "pushd", "popd", "tmux", "screen",
    "expect",
    # `time` is denied here too, not only via the raw first-word reserved-
    # word check — RR-3 P1-4 found the two mechanisms had drifted apart:
    # `/usr/bin/time`, `command time`, `env time` all resolve to logical
    # command `time` (past env/command-unwrap and path-basename
    # resolution) but never reach the raw-text check, which only sees
    # `time` as a literal first word before any of that resolution runs.
    "time",
    # zsh precommand modifiers — this guard's runtime shell is the
    # macOS default (zsh), not bash; `noglob`/`nocorrect` are generic
    # "run this program" launchers of the same class as `nice`/`setsid`
    # above, and `repeat N`/`coproc` are zsh reserved words that take a
    # following command this guard does not otherwise model.
    "noglob", "nocorrect", "repeat", "coproc",
    # `builtin` is `command`'s sibling precommand modifier (forces a
    # shell builtin rather than a PATH lookup) and was missing from both
    # the unwrap logic and this denylist — `builtin eval '...'` reached
    # `_analyze_simple_command` as an unrecognized logical name.
    "builtin",
    # awk's system()/getline-pipe can run arbitrary shell; there is no
    # cheap way to tell a benign `awk '{print $1}'` from one that calls
    # system(...) without parsing the awk program, so — per this guard's
    # fail-closed doctrine — the whole family is blanket-denied rather
    # than heuristically inspected.
    "awk", "gawk", "nawk", "mawk",
}

_PY_NODE_RUBY_EVAL_FLAGS = {"-c", "-e", "--eval"}
_PERL_EVAL_FLAG_RE = re.compile(r"^-[a-zA-Z]*[cepin][a-zA-Z]*$")


def _short_flag_chars(tokens):
    for t in tokens:
        if t.startswith("--") or t == "-" or not t.startswith("-"):
            continue
        for ch in t[1:]:
            yield ch


# ---------------------------------------------------------------------------
# rm / find (BUG-013)
# ---------------------------------------------------------------------------


def _rm_is_recursive(args):
    if "--recursive" in args:
        return True
    return any(ch in ("r", "R") for ch in _short_flag_chars(args))


_FIND_EXEC_ALWAYS_DESTRUCTIVE = {"rm", "shred", "truncate", "dd", "find", "mv"}


def _find_exec_spans(args):
    """Return the token span of each -exec/-execdir invocation's own
    command (up to its terminating literal ';' or '+'), so the caller can
    run that command through the SAME full analysis this guard applies
    to a top-level command — rather than a fixed name list, which is
    exactly the enumeration-of-bad-names failure mode BUG-022 concluded
    was insufficient for `.claude/settings.json` in the first place."""
    spans = []
    i = 0
    while i < len(args):
        if args[i] in ("-exec", "-execdir"):
            j = i + 1
            while j < len(args) and args[j] not in (";", "+"):
                j += 1
            spans.append(args[i + 1 : j])
            i = j + 1
            continue
        i += 1
    return spans


# ---------------------------------------------------------------------------
# git (BUG-013 residual / BUG-022)
# ---------------------------------------------------------------------------

_GIT_GLOBAL_OPTS_TAKE_ARG = {
    "-c", "-C", "--git-dir", "--work-tree", "--namespace",
    "--super-prefix", "--config-env", "--exec-path",
}

_GIT_ALIAS_SHELL_RE = re.compile(r"^alias\.[^=]+=!(.*)$")

# Config keys whose VALUE git executes directly as a shell command,
# independent of the `alias.x=!shell` convention (RR-3 P1-1 — the
# original fix only recursed into the alias form and left this whole
# class open: `-c diff.external=...` fires unconditionally on `git
# diff`, unlike core.pager/core.editor which only fire interactively).
_GIT_SHELL_VALUE_KEY_RE = re.compile(
    r"^(diff\.external|core\.pager|core\.editor|credential\.helper|"
    r"core\.sshcommand|sequence\.editor|uploadpack\.packobjectshook|"
    r"filter\.[^.]+\.(clean|smudge))$",
    re.IGNORECASE,
)


def _split_git_global_opts(args):
    i = 0
    embedded_shell_fragments = []
    dash_C_dir = None  # RR-3 P1-3: `git -C <dir>` changes git's own cwd
    while i < len(args):
        tok = args[i]
        if tok in _GIT_GLOBAL_OPTS_TAKE_ARG:
            if tok == "-C" and i + 1 < len(args):
                dash_C_dir = args[i + 1]
            if tok == "-c" and i + 1 < len(args) and "=" in args[i + 1]:
                m = _GIT_ALIAS_SHELL_RE.match(args[i + 1])
                if m:
                    embedded_shell_fragments.append(m.group(1))
                else:
                    key, value = args[i + 1].split("=", 1)
                    if _GIT_SHELL_VALUE_KEY_RE.match(key):
                        embedded_shell_fragments.append(value)
            i += 2
            continue
        if tok.startswith("--") and "=" in tok:
            i += 1
            continue
        if tok.startswith("-") and tok != "-":
            i += 1
            continue
        break
    if i >= len(args):
        return None, [], embedded_shell_fragments, dash_C_dir
    return args[i], args[i + 1 :], embedded_shell_fragments, dash_C_dir


def _has_force_flag(rest):
    if any(t in ("--force", "--force-with-lease") for t in rest):
        return True
    if any(t.startswith("+") for t in rest):
        return True
    return "f" in _short_flag_chars(rest)


def _git_is_destructive(subcommand, rest):
    if subcommand == "reset" and "--hard" in rest:
        return "git reset --hard"
    if subcommand == "push":
        if _has_force_flag(rest):
            return "git push --force"
        if "--delete" in rest or "-d" in rest:
            return "git push --delete"
        if any(re.match(r"^:\S+$", t) for t in rest):
            return "git push <refspec-delete>"
    if subcommand == "branch":
        if "D" in _short_flag_chars(rest):
            return "git branch -D"
        if "--delete" in rest and ("--force" in rest or "f" in _short_flag_chars(rest)):
            return "git branch --delete --force"
    if subcommand == "checkout":
        if rest and rest[0] == ".":
            return "git checkout ."
        if "--" in rest:
            idx = rest.index("--")
            if idx + 1 < len(rest) and rest[idx + 1] == ".":
                return "git checkout -- ."
    if subcommand == "clean" and ("f" in _short_flag_chars(rest) or "--force" in rest):
        return "git clean -f"
    if subcommand == "restore" and "." in rest:
        return "git restore ."
    if subcommand == "filter-branch":
        return "git filter-branch"
    if subcommand == "filter-repo":
        return "git filter-repo"
    if subcommand == "reflog" and rest and rest[0] == "expire":
        return "git reflog expire"
    if subcommand == "update-ref" and "-d" in rest:
        return "git update-ref -d"
    if subcommand == "commit" and "--amend" in rest:
        return "git commit --amend"
    if subcommand == "stash" and rest and rest[0] in ("clear", "drop"):
        return "git stash " + rest[0]
    if subcommand == "worktree" and rest and rest[0] == "remove":
        return "git worktree remove"
    if subcommand == "gc" and any(t == "--prune" or t.startswith("--prune=") for t in rest):
        return "git gc --prune"
    if subcommand == "rm" and ("--recursive" in rest or "r" in _short_flag_chars(rest) or "R" in _short_flag_chars(rest)):
        return "git rm -r"
    return None


# ---------------------------------------------------------------------------
# Protected-path mutation (BUG-023), with cd-chain + glob/brace awareness
# ---------------------------------------------------------------------------

PROTECTED_PATH_FRAGMENTS = [
    "Gym_OS_Master_Product_Blueprint_v1_English.docx",
    "Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx",
    "Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx",
    "veyro-product-experience-design",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/rules",
    ".claude/agents",
    ".claude/security",  # this guard and its tests protect themselves too
]

_PROTECTED_PATH_FRAGMENTS_LOWER = [f.lower() for f in PROTECTED_PATH_FRAGMENTS]


def _plain_mentions_protected_path(text):
    # Case-insensitive: this repo lives on a case-insensitive-but-
    # preserving filesystem (macOS default APFS), where `.Claude/` and
    # `.claude/` name the same real directory.
    lowered = text.lower()
    return any(frag in lowered for frag in _PROTECTED_PATH_FRAGMENTS_LOWER)


_BRACE_RE = re.compile(r"\{([^{}]+)\}")


def _expand_braces_one_level(pattern):
    m = _BRACE_RE.search(pattern)
    if not m or "," not in m.group(1):
        return [pattern]
    prefix, suffix = pattern[: m.start()], pattern[m.end() :]
    return [prefix + part + suffix for part in m.group(1).split(",")]


def _mentions_protected_path(token, base_dir=None):
    """Substring check, plus (for glob-shaped tokens) brace expansion and
    real-filesystem glob expansion from base_dir. See HONEST SCOPE LIMITS."""
    if _plain_mentions_protected_path(token):
        return True
    if not any(ch in token for ch in "*?[{"):
        return False
    for variant in _expand_braces_one_level(token):
        if _plain_mentions_protected_path(variant):
            return True
        if any(ch in variant for ch in "*?["):
            try:
                search_root = variant if os.path.isabs(variant) else os.path.join(base_dir or ".", variant)
                for match in glob.glob(search_root, recursive=True):
                    if _plain_mentions_protected_path(match):
                        return True
            except Exception:
                return True  # fail closed on glob-expansion errors
    return False


class VirtualCwd:
    """Tracks `cd` effects within one chained command, seeded from the
    hook payload's real `cwd`. See HONEST SCOPE LIMITS: same-command only."""

    def __init__(self, real_cwd):
        self.real_cwd = real_cwd or "."

    def apply_cd(self, target):
        if not target:
            return
        if os.path.isabs(target):
            self.real_cwd = os.path.normpath(target)
        else:
            self.real_cwd = os.path.normpath(os.path.join(self.real_cwd, target))

    def resolve(self, token):
        if os.path.isabs(token):
            return token
        return os.path.normpath(os.path.join(self.real_cwd, token))


def _arg_is_protected(token, vcwd):
    if _mentions_protected_path(token, base_dir=vcwd.real_cwd):
        return True
    resolved = vcwd.resolve(token)
    return _mentions_protected_path(resolved, base_dir=".")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


class Violation(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _check_redirection_targets(raw_line, vcwd):
    for target in _find_unquoted_redirect_targets(raw_line):
        if _arg_is_protected(target, vcwd):
            raise Violation(
                "PROTECTED_PATH_MUTATION",
                f"shell redirection targets a protected path: {target}",
            )


def _analyze_simple_command(words, vcwd):
    if not words:
        return

    try:
        logical, resolved_words = _resolve_logical_command(words)
    except _CannotResolve as e:
        raise Violation("UNSUPPORTED_CONSTRUCT_WRAPPER", str(e))

    if logical is None:
        # Unresolved $VAR/${VAR} command name: cannot identify what this
        # runs, so — unlike every other "can't classify" path in this
        # module, which defers to the existing permission flow — this
        # one fails closed. A dynamic command name is exactly the shape
        # `$SHELL -c '...'` bypasses take, and there is no way to tell
        # that apart from a harmless `$MY_TOOL --version` here without
        # resolving the variable, which this guard does not do.
        raise Violation(
            "UNSUPPORTED_CONSTRUCT_WRAPPER",
            f"command name depends on unresolved variable expansion: {' '.join(words)!r}",
        )

    if logical in _WRAPPER_ALWAYS_DENY:
        raise Violation(
            "UNSUPPORTED_CONSTRUCT_WRAPPER",
            f"delegates to an unanalyzable wrapper/interpreter: {logical} ({' '.join(words)})",
        )

    args = resolved_words[1:] if resolved_words else []

    if logical == "cd":
        target = None
        for a in args:
            if a == "--":
                continue
            if a == "-":
                # "cd -" means "the previous directory", which this
                # guard cannot know — leave vcwd unchanged rather than
                # treating the literal "-" as a path component.
                break
            if a.startswith("-"):
                continue  # cd flag (-P, -L, -e, -@, ...), not the target
            target = a
            break
        vcwd.apply_cd(target)
        return

    if logical == "rm":
        if any(_arg_is_protected(a, vcwd) for a in args if not a.startswith("-")):
            raise Violation("PROTECTED_PATH_MUTATION", "rm targets a protected path")
        if _rm_is_recursive(args):
            raise Violation("DESTRUCTIVE_FILESYSTEM_OPERATION", f"recursive rm ({' '.join(resolved_words)})")
        return

    if logical == "find":
        if "-delete" in args:
            raise Violation("DESTRUCTIVE_FILESYSTEM_OPERATION", f"find -delete ({' '.join(resolved_words)})")
        for span in _find_exec_spans(args):
            if not span:
                raise Violation("DESTRUCTIVE_FILESYSTEM_OPERATION", f"dangling -exec/-execdir with no command ({' '.join(resolved_words)})")
            try:
                exec_logical, _ = _resolve_logical_command(span)
            except _CannotResolve as e:
                raise Violation("UNSUPPORTED_CONSTRUCT_WRAPPER", str(e))
            if exec_logical in _FIND_EXEC_ALWAYS_DESTRUCTIVE:
                raise Violation(
                    "DESTRUCTIVE_FILESYSTEM_OPERATION",
                    f"find -exec {' '.join(span)} (iterative bulk operation, always denied regardless of flags)",
                )
            _analyze_simple_command(span, vcwd)  # full recursive analysis: wrapper/git/protected-path checks apply here too
        return

    if logical == "git":
        subcommand, rest, embedded_shell, dash_C_dir = _split_git_global_opts(args)
        git_vcwd = VirtualCwd(vcwd.resolve(dash_C_dir)) if dash_C_dir else vcwd
        for frag in embedded_shell:
            analyze_command(frag)  # recurse into `-c alias.x=!<shell>`
        if subcommand == "submodule" and "foreach" in rest:
            idx = rest.index("foreach")
            cmd_args = [t for t in rest[idx + 1 :] if not t.startswith("-")]
            if cmd_args:
                analyze_command(cmd_args[0])
        if subcommand == "config":
            # `git config alias.x '!<shell>'` / `git config diff.external
            # '<shell>'` persist the same dangers `-c alias.x=!<shell>`
            # and `-c diff.external=<shell>` recurse into above, just
            # written to disk instead of passed transiently.
            for idx, tok in enumerate(rest):
                key, has_inline_value = (tok.split("=", 1)[0], "=" in tok)
                if key.startswith("alias.") or _GIT_SHELL_VALUE_KEY_RE.match(key):
                    value = tok.split("=", 1)[1] if has_inline_value else (rest[idx + 1] if idx + 1 < len(rest) else "")
                    if key.startswith("alias.") and value.startswith("!"):
                        analyze_command(value[1:])
                    elif _GIT_SHELL_VALUE_KEY_RE.match(key) and value:
                        analyze_command(value)
        if subcommand in ("checkout", "restore"):
            # Content-clobbering forms: `checkout [HEAD] [--] <path>` and
            # `restore [--source=REF] <path>` overwrite the named
            # worktree file(s) from another ref — a protected-path
            # mutation distinct from the whole-tree `checkout .`/
            # `restore .` cases _git_is_destructive already covers.
            path_args = [t for t in rest if not t.startswith("-") and t not in ("HEAD", "--")]
            if any(_arg_is_protected(p, git_vcwd) for p in path_args):
                raise Violation(
                    "PROTECTED_PATH_MUTATION",
                    f"git {subcommand} overwrites a protected path ({' '.join(resolved_words)})",
                )
        if subcommand:
            reason = _git_is_destructive(subcommand, rest)
            if reason:
                raise Violation("DESTRUCTIVE_GIT_OPERATION", f"{reason} (resolved from: {' '.join(resolved_words)})")
        return

    if logical in ("python", "python2", "python3", "node", "ruby", "perl"):
        eval_flag = any(a in _PY_NODE_RUBY_EVAL_FLAGS for a in args) or (
            logical == "perl" and any(_PERL_EVAL_FLAG_RE.match(a) for a in args if a.startswith("-"))
        )
        # No script-file argument at all (nothing left once flags are
        # excluded), an explicit "-" stdin marker, or any input-
        # redirection-shaped argument (<, <<, <<<) means the interpreter
        # is fed code from stdin — semantically identical to -c/-e, and
        # closes the case where a heredoc or here-string was used
        # specifically to route code around the -c/-e check above.
        non_flag_args = [a for a in args if not a.startswith("-")]
        stdin_fed = (not non_flag_args) or any(a == "-" or "<" in a for a in args)
        if eval_flag or stdin_fed:
            raise Violation(
                "UNSUPPORTED_CONSTRUCT_INTERPRETER",
                f"{logical} inline/stdin code evaluation cannot be analyzed ({' '.join(resolved_words)})",
            )
        return

    if logical in (
        "cp", "mv", "sed", "tee", "truncate", "dd",
        "ln", "install", "rsync", "patch", "ditto",
        "tar", "unzip", "gzip", "gunzip", "shred",
        "chmod", "chown", "chattr",
    ):
        if any(_arg_is_protected(a, vcwd) for a in args if not a.startswith("-") and "=" not in a):
            raise Violation("PROTECTED_PATH_MUTATION", f"{logical} references a protected path ({' '.join(resolved_words)})")
        # dd uses of=/if=
        if logical == "dd":
            for a in args:
                if a.startswith("of=") or a.startswith("if="):
                    if _arg_is_protected(a.split("=", 1)[1], vcwd):
                        raise Violation("PROTECTED_PATH_MUTATION", f"dd references a protected path ({' '.join(resolved_words)})")
        return


def analyze_command(raw_command, real_cwd="."):
    """Raises Violation if `raw_command` matches a prohibited pattern.
    Returns normally if no violation is found — callers must treat that
    as "no decision", not as "confirmed safe"."""
    lowered = raw_command.lower()
    if "production" in lowered or "--prod" in lowered or "prod deploy" in lowered:
        raise Violation("PRODUCTION_ACTION", "command references production/--prod")

    if "testsprite" in lowered and (
        "test run" in lowered or "test rerun" in lowered or "testlist run" in lowered
    ):
        raise Violation("PAID_TESTSPRITE_EXECUTION", "billed TestSprite command")

    text = _strip_heredocs(raw_command)
    text = _join_line_continuations(text)
    text, substitutions = _extract_substitutions(text)

    for sub_command in substitutions:
        analyze_command(sub_command, real_cwd=real_cwd)

    vcwd = VirtualCwd(real_cwd)
    for physical_line in _split_physical_lines(text):
        if not physical_line.strip():
            continue
        for raw_segment in _split_raw_by_chain_operators(physical_line):
            if not raw_segment.strip():
                continue
            # Check this segment's own redirection target BEFORE analyzing
            # it further, but AFTER every earlier segment on this line has
            # already had a chance to update vcwd via `cd` — this ordering
            # is what makes `cd DIR && echo x > relative` resolve `relative`
            # against DIR instead of the call's original cwd.
            _check_unmodeled_raw_constructs(raw_segment)
            _check_redirection_targets(raw_segment, vcwd)
            tokens = _tokenize(raw_segment)  # may raise ValueError -> caller fails closed
            tokens = _strip_leading_redirections(tokens)
            _analyze_simple_command(tokens, vcwd)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _deny(code, detail):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"BLOCKED: {code} — {detail}",
                }
            }
        )
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # cannot read payload: not a classifiable command, no decision

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        sys.exit(0)

    cwd = payload.get("cwd") or "."

    try:
        analyze_command(command, real_cwd=cwd)
    except Violation as v:
        _deny(v.code, v.detail)
        sys.exit(0)
    except Exception as e:
        _deny("PARSE_FAILURE_FAIL_CLOSED", f"guard could not safely analyze this command: {e!r}")
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
