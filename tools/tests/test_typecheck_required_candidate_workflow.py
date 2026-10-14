#!/usr/bin/env python3
"""
Focused static + behavioral tests for
.github/workflows/typecheck-required-candidate.yml (MOD-001, GOV-01-R04
required type-check CI CANDIDATE; local tests only, never evidence about a CI
run and no gate credit).

Standard library only; no network, no mypy, no Veyro source is type-checked.
No YAML parser is available in the project venv, so the workflow text is
parsed line-wise. The tests do not just mirror the file:

  1. `audit(text)` encodes the policy (inert trigger, no PR activation, one
     job and the exact ordered steps, no secrets/actions/permissions, no
     direct mypy, one hash-enforced install and no other installer, env-only
     expressions, the trusted-definition boundary, the load-bearing lines of
     the wrapper step, pinned hashes equal to the committed files). The
     committed workflow must audit clean AND each deliberate tamper/drift of
     it must be flagged, including the five BUG-062 mutants (zero-file success
     regex, removed DENY screen, dropped `env -i`, added `pip3 install`, extra
     job) and the BUG-061 boundary mutants (wrapper run from source, no
     tamper compare, executable-mode source blobs, source checkout, ...).
  2. The extracted steps are EXECUTED under bash with stubs: wrong event/ref/
     sha is denied before any fetch; a wrong pin is denied; the wrapper step
     passes only on rc 0 with the exact success text and fails on everything
     else, runs under a cleared environment, and the install step strips PIP_*
     settings. Three of the BUG-062 mutants are additionally killed by running
     the mutated step script, independent of audit().
  3. The trusted-definition boundary runs against synthetic git repositories
     where the trusted sha and the source sha DIFFER: app-only changes are
     composed into the trusted tree; any change to the workflow, wrapper,
     assertion script, lock or mypy config (edit, delete, mode change, symlink
     swap, new config file) is denied; symlink, executable or gitlink source
     entries and a missing backend/app are denied; nothing from the source is
     executed.
  3b. BUG-062 round 2: steps 2 and 3 are frozen line-for-line in audit(); the
     mutated step-2 pin guard (got==got, wrapper check removed) and mutated
     step-3 (post-pin cp/cat of source bytes over a pinned trusted file) are
     EXECUTED against throwaway files/git repos to show the mutant lets the
     drift/overwrite through while the committed step denies or leaves it.
  3c. BUG-062 round 3 (closed world): the whole workflow file is pinned by SHA-256
     (`WORKFLOW_SHA256`) and every region - the preamble and each of the seven steps -
     has insert / reorder / whitespace mutants that must change the digest. A bounded
     write-surface inventory (`write_surface`) of the committed model is also frozen.
     The exact-bytes pin is a CHANGE TRIPWIRE for the reviewed bytes, NOT runtime
     protection: a coordinated edit of workflow + this test (new digest) passes it, and
     the write-surface inventory is a text heuristic, not a shell parser.
  3d. BUG-064 (followed-module composition): every .py/.pyi under backend/ in the composed
     tree must be the SOURCE entry (additions, modifications, deletions; non-Python files
     keep trusted bytes). Synthetic repos with trusted != source show an out-of-app edit
     is materialized, an unchanged tree is allowed, and symlink/gitlink/executable/.venv
     entries and gate-config edits are denied before the trusted tree is touched. Mutants
     of the new lines are EXECUTED to show each check is load-bearing (reverting the fix
     reproduces the poisoning: the real wrapper's `scan_import_closure` then fingerprints
     trusted bytes), and the composed tree is compared with an independent git oracle.
  4. The candidate branch named in the trigger must not exist in this
     repository (no accidental activation).
"""
import hashlib
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "typecheck-required-candidate.yml"

CANDIDATE_BRANCH = "candidate-only/typecheck-required-never-created"
WRAPPER_SHA256 = "1a5df02b6c0ddd69a90c46adb62c81e3adb0b2ba162484fa2180b14ec665399c"
PINS = {
    "WRAPPER_SHA256": ("tools/run_scoped_mypy.py", WRAPPER_SHA256),
    "ASSERT_SHA256": ("tools/assert_ci_python313.py", None),
    "LOCK_SHA256": ("backend/requirements-typecheck-linux-x86_64-cp313.lock.txt", None),
}
ALLOWED_EXPRESSIONS = {
    "github.event_name", "github.ref", "github.sha", "github.server_url", "github.repository",
}
FORBIDDEN_TRIGGERS = {
    "pull_request", "pull_request_target", "workflow_dispatch", "schedule", "workflow_run",
    "workflow_call", "repository_dispatch", "release", "issue_comment", "merge_group",
}
EXPECTED_STEPS = (
    "Deny unless candidate-only ref",
    "Guard pinned inputs",
    "Deny candidate tamper",
    "Resolve and assert CPython 3.13",
    "Create venv from asserted interpreter",
    "Hash-enforced install",
    "Scoped wrapper on the composed backend/app",
)
EXPECTED_ENV = {
    "Deny unless candidate-only ref": {
        "EVENT_NAME": "${{ github.event_name }}", "REF": "${{ github.ref }}",
        "TRUSTED_SHA": "${{ github.sha }}", "SOURCE_SHA": "${{ github.sha }}",
        "REPO_URL": "${{ github.server_url }}/${{ github.repository }}.git",
    },
    "Deny candidate tamper": {"TRUSTED_SHA": "${{ github.sha }}", "SOURCE_SHA": "${{ github.sha }}"},
}
# Gate-defining paths whose source copy must equal the trusted entry.
PROTECTED = (
    ".github/workflows/typecheck-required-candidate.yml",
    "tools/run_scoped_mypy.py",
    "tools/assert_ci_python313.py",
    "backend/requirements-typecheck-linux-x86_64-cp313.lock.txt",
    "backend/pyproject.toml",
    "backend/mypy.ini",
    "backend/.mypy.ini",
    "backend/setup.cfg",
    "backend/tox.ini",
)
INSTALLER_RE = re.compile(
    r"\bpip[0-9.]*\s+(install|download|wheel)\b|-m\s+pip\s+(install|download|wheel)\b|\bensurepip\b|"
    r"\beasy_install\b|\buv\s+(pip|sync|add)\b|\bget-pip\b|setup\.py\s+(install|develop)|\bpipx\b|"
    r"\bapt(-get)?\s+install\b|\bnpm\s+(i|install|ci)\b|\bbrew\s+install\b|\bconda\s+install\b"
)
EXEC_WORD_RE = re.compile(r"\b(python[0-9.]*|pip[0-9.]*|mypy|exec|eval|chmod|bash|sh|node|ruby|perl)\b")
SUCCESS_GREP = "grep -E '^Success: no issues found in [1-9][0-9]* source files$' >/dev/null"
MARKER_GREP = "grep -E '^run_scoped_mypy: rc=0 ' >/dev/null"
ENV_I_CALL = ('env -i PATH=/usr/bin:/bin HOME="$scratch/home" TMPDIR="$scratch/tmp" NO_COLOR=1 '
              'LC_ALL=C.UTF-8 \\\n            "$venv/bin/python" -I "$work/tools/run_scoped_mypy.py"')


# Gate-defining steps 2 and 3 are frozen line-for-line (BUG-062 round 2): any inserted,
# removed, reordered or weakened command - e.g. a post-pin overwrite of the trusted
# wrapper from source bytes, or a pin comparison that no longer compares to the pin -
# changes the sequence. Changing them deliberately means updating these literals.
GUARD_STEP_LINES = (
    'set -euo pipefail',
    'work="$RUNNER_TEMP/work"',
    'check() {',
    '  local path="$1" want="$2" got',
    '  [[ -e "$path" ]] || { echo "DENY: $path absent" >&2; exit 1; }',
    '  [[ ! -L "$path" ]] || { echo "DENY: $path is a symlink" >&2; exit 1; }',
    '  [[ -f "$path" ]] || { echo "DENY: $path is not a regular file" >&2; exit 1; }',
    '  got="$(sha256sum "$path" | cut -d\' \' -f1)"',
    '  [[ "$got" == "$want" ]] || { echo "DENY: $path sha256 $got, expected $want" >&2; exit 1; }',
    '  echo "pinned ok: $want $path"',
    '}',
    'check "$work/tools/run_scoped_mypy.py" "$WRAPPER_SHA256"',
    'check "$work/tools/assert_ci_python313.py" "$ASSERT_SHA256"',
    'check "$work/backend/requirements-typecheck-linux-x86_64-cp313.lock.txt" "$LOCK_SHA256"',
    '[[ -d "$work/backend/app" && ! -L "$work/backend/app" ]] \\',
    '  || { echo "DENY: backend/app is not a real directory" >&2; exit 1; }',
    '[[ -f "$work/backend/pyproject.toml" && ! -L "$work/backend/pyproject.toml" ]] \\',
    '  || { echo "DENY: backend/pyproject.toml is not a regular file" >&2; exit 1; }',
    '[[ ! -e "$work/backend/.venv" && ! -L "$work/backend/.venv" ]] \\',
    '  || { echo "DENY: backend/.venv is committed in the trusted tree" >&2; exit 1; }',
)

TAMPER_STEP_LINES = (
    'set -euo pipefail',
    'deny() { echo "DENY: $1" >&2; exit 1; }',
    'work="$RUNNER_TEMP/work"',
    'src="$RUNNER_TEMP/source.git"',
    'stage="$RUNNER_TEMP/source-app"',
    '[[ "$TRUSTED_SHA" =~ ^[0-9a-f]{40}$ ]] || deny "trusted sha is not 40-hex"',
    '[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || deny "source sha is not 40-hex"',
    '[[ "$(git -C "$work" rev-parse HEAD)" == "$TRUSTED_SHA" ]] || deny "trusted tree is not $TRUSTED_SHA"',
    '[[ "$(git -C "$src" rev-parse "$SOURCE_SHA^{commit}")" == "$SOURCE_SHA" ]] \\',
    '  || deny "source objects are not commit $SOURCE_SHA"',
    'for rel in \\',
    '  .github/workflows/typecheck-required-candidate.yml \\',
    '  tools/run_scoped_mypy.py \\',
    '  tools/assert_ci_python313.py \\',
    '  backend/requirements-typecheck-linux-x86_64-cp313.lock.txt \\',
    '  backend/pyproject.toml backend/mypy.ini backend/.mypy.ini backend/setup.cfg backend/tox.ini',
    'do',
    '  want="$(git -C "$work" ls-tree --full-tree "$TRUSTED_SHA" -- "$rel")"',
    '  got="$(git -C "$src" ls-tree --full-tree "$SOURCE_SHA" -- "$rel")"',
    '  [[ "$got" == "$want" ]] \\',
    '    || deny "candidate changed $rel; gate bytes must come from the reviewed trusted sha"',
    'done',
    'git -C "$src" ls-tree -r -z --full-tree "$SOURCE_SHA" -- backend/app > "$RUNNER_TEMP/app.lst"',
    '[[ -s "$RUNNER_TEMP/app.lst" ]] || deny "source has no backend/app entries"',
    'rm -rf "$stage"',
    'mkdir -p "$stage"',
    'count=0',
    "while IFS= read -r -d '' rec; do",
    '  meta="${rec%%$\'\\t\'*}"',
    '  path="${rec#*$\'\\t\'}"',
    '  read -r mode type oid <<<"$meta"',
    '  [[ "$mode" == "100644" && "$type" == "blob" ]] \\',
    '    || deny "refused source entry mode $mode type $type at \'$path\' (symlink/gitlink/executable)"',
    '  case "$path" in backend/app/?*) ;; *) deny "source entry outside backend/app: \'$path\'" ;; esac',
    '  case "/$path/" in',
    '    */../*|*/./*|*//*|*/.git/*) deny "unsafe source path \'$path\'" ;;',
    '  esac',
    '  mkdir -p "$stage/$(dirname "$path")"',
    '  git -C "$src" cat-file blob "$oid" > "$stage/$path"',
    '  count=$((count + 1))',
    'done < "$RUNNER_TEMP/app.lst"',
    '[[ "$count" -ge 1 ]] || deny "no source blobs materialized"',
    'git -C "$src" ls-tree -r -z --full-tree "$SOURCE_SHA" -- backend > "$RUNNER_TEMP/backend.lst"',
    'outstage="$RUNNER_TEMP/source-backend"',
    'rm -rf "$outstage"',
    'mkdir -p "$outstage"',
    ': > "$RUNNER_TEMP/outside.lst"',
    'outside=0',
    "while IFS= read -r -d '' rec; do",
    '  meta="${rec%%$\'\\t\'*}"',
    '  path="${rec#*$\'\\t\'}"',
    '  read -r mode type oid <<<"$meta"',
    '  case "$path" in backend/app|backend/app/*) continue ;; backend/?*) ;; *) deny "source entry outside backend: \'$path\'" ;; esac',
    '  case "/$path/" in',
    '    */../*|*/./*|*//*|*/.git/*|/backend/.venv/*) deny "unsafe source path \'$path\'" ;;',
    '  esac',
    '  case "$mode" in 120000|160000) deny "refused source entry mode $mode at \'$path\' (symlink/gitlink under backend)" ;; esac',
    '  case "$path" in',
    '    *.py|*.pyi)',
    '      [[ "$mode" == "100644" && "$type" == "blob" ]] \\',
    '        || deny "refused source module entry mode $mode type $type at \'$path\' (executable or irregular)"',
    '      mkdir -p "$outstage/$(dirname "$path")"',
    '      git -C "$src" cat-file blob "$oid" > "$outstage/$path"',
    '      printf \'%s\\t%s\\0\' "$oid" "$path" >> "$RUNNER_TEMP/outside.lst"',
    '      outside=$((outside + 1)) ;;',
    '  esac',
    'done < "$RUNNER_TEMP/backend.lst"',
    'rm -rf "$work/backend/app"',
    'mv "$stage/backend/app" "$work/backend/app"',
    '[[ -z "$(find "$work/backend/app" ! -type f ! -type d)" ]] || deny "non-regular entry in materialized backend/app"',
    '[[ "$(find "$work/backend/app" -type f | wc -l | tr -d \' \')" == "$count" ]] \\',
    '  || deny "materialized file count differs from the source listing"',
    'echo "materialized $count inert source blobs from $SOURCE_SHA into the trusted $TRUSTED_SHA tree"',
    'find "$work/backend" -path "$work/backend/app" -prune -o \\( -name \'*.py\' -o -name \'*.pyi\' \\) \\( -type f -o -type l \\) -print0 > "$RUNNER_TEMP/trusted-modules.lst"',
    'while IFS= read -r -d \'\' f; do rm -f "$f"; done < "$RUNNER_TEMP/trusted-modules.lst"',
    "while IFS= read -r -d '' rec; do",
    '  oid="${rec%%$\'\\t\'*}"',
    '  path="${rec#*$\'\\t\'}"',
    '  mkdir -p "$work/$(dirname "$path")"',
    '  mv "$outstage/$path" "$work/$path"',
    '  [[ -f "$work/$path" && ! -L "$work/$path" ]] || deny "followed module \'$path\' is not a regular file after composition"',
    '  [[ "$(git -C "$work" hash-object --no-filters -- "$work/$path")" == "$oid" ]] \\',
    '    || deny "followed module \'$path\' is not the source blob $oid"',
    'done < "$RUNNER_TEMP/outside.lst"',
    '[[ "$(find "$work/backend" -path "$work/backend/app" -prune -o \\( -name \'*.py\' -o -name \'*.pyi\' \\) \\( -type f -o -type l \\) -print | wc -l | tr -d \' \')" == "$outside" ]] \\',
    '  || deny "composed backend/ holds .py/.pyi files that are not in the source listing"',
    'echo "composed $outside followed backend/ .py/.pyi modules from $SOURCE_SHA (add, modify, delete); no trusted copy remains"',
)


# Closed-world snapshot (BUG-062 round 3). Changing the workflow deliberately means
# re-reviewing it and updating this digest (and, if needed, WRITE_SURFACE below).
# This pins reviewed bytes; it does not stop someone who edits workflow AND test together.
WORKFLOW_SHA256 = "d51186bda63d6bf67c0bd7107ede2477d1723885ad49ca612be0f53a0c4436f2"

REDIRECT_RE = re.compile(r'(?<![<>&\w])\d*>{1,2}(?!&)\s*("[^"]*"|[^\s;|&)]+)')
WRITE_VERB_RE = re.compile(
    r"(?<![\w$./-])(rm|mv|cp|ln|mkdir|tee|touch|chmod|chown|dd|truncate|install|rsync|tar|sed|awk|"
    r"perl|ruby|node|eval)\s|(?<![\w$./-])git\s+(-[Cc]\s+\S+\s+)*(init|fetch|checkout|clone|archive|apply|am|"
    r"reset|restore|merge|worktree|read-tree)\b|-m\s+(venv|pip\s+(install|download|wheel))\b")
CHANNEL_RE = re.compile(r"GITHUB_(ENV|PATH|OUTPUT|STATE|STEP_SUMMARY)\b")
# Redirect targets must stay in runner scratch space and never name a gate-defining path.
SAFE_TARGET_RE = re.compile(r'^"\$(RUNNER_TEMP|stage|outstage)[/"]')
GATE_PATH_RE = re.compile(r"/tools/|\.github|requirements-typecheck|pyproject|mypy\.ini|setup\.cfg|tox\.ini")

# Frozen write inventory of the committed workflow: (step number, folded command line).
WRITE_SURFACE = (
    (1, 'git init -q "$work"'),
    (1, 'git -C "$work" fetch -q --no-tags --depth=1 "$REPO_URL" "$TRUSTED_SHA"'),
    (1, 'git -C "$work" -c advice.detachedHead=false checkout -q FETCH_HEAD'),
    (1, 'git init -q --bare "$src"'),
    (1, 'git -C "$src" fetch -q --no-tags --depth=1 "$REPO_URL" "$SOURCE_SHA"'),
    (3, 'git -C "$src" ls-tree -r -z --full-tree "$SOURCE_SHA" -- backend/app > "$RUNNER_TEMP/app.lst"'),
    (3, 'rm -rf "$stage"'),
    (3, 'mkdir -p "$stage"'),
    (3, 'mkdir -p "$stage/$(dirname "$path")"'),
    (3, 'git -C "$src" cat-file blob "$oid" > "$stage/$path"'),
    (3, 'git -C "$src" ls-tree -r -z --full-tree "$SOURCE_SHA" -- backend > "$RUNNER_TEMP/backend.lst"'),
    (3, 'rm -rf "$outstage"'),
    (3, 'mkdir -p "$outstage"'),
    (3, ': > "$RUNNER_TEMP/outside.lst"'),
    (3, 'mkdir -p "$outstage/$(dirname "$path")"'),
    (3, 'git -C "$src" cat-file blob "$oid" > "$outstage/$path"'),
    (3, 'printf \'%s\\t%s\\0\' "$oid" "$path" >> "$RUNNER_TEMP/outside.lst"'),
    (3, 'rm -rf "$work/backend/app"'),
    (3, 'mv "$stage/backend/app" "$work/backend/app"'),
    (3, 'find "$work/backend" -path "$work/backend/app" -prune -o \\( -name \'*.py\' -o -name \'*.pyi\' \\) \\( -type f -o -type l \\) -print0 > "$RUNNER_TEMP/trusted-modules.lst"'),
    (3, 'while IFS= read -r -d \'\' f; do rm -f "$f"; done < "$RUNNER_TEMP/trusted-modules.lst"'),
    (3, 'mkdir -p "$work/$(dirname "$path")"'),
    (3, 'mv "$outstage/$path" "$work/$path"'),
    (4, 'printf \'%s\\n\' "$chosen" > "$RUNNER_TEMP/interpreter.path"'),
    (5, '"$py" -m venv "$RUNNER_TEMP/venv-typecheck"'),
    (6, '"$RUNNER_TEMP/venv-typecheck/bin/python" -m pip install --require-hashes --only-binary=:all: --no-deps --index-url https://pypi.org/simple --no-cache-dir --no-input --disable-pip-version-check -r "$lock"'),
    (7, 'ln -s "$venv" "$work/backend/.venv"'),
    (7, 'trap \'rm -rf "$scratch"\' EXIT'),
    (7, 'mkdir -p "$scratch/home" "$scratch/tmp"'),
)


def snapshot_violations(data):
    """Closed-world check: the workflow bytes (all steps, preamble, whitespace, EOLs) equal the reviewed snapshot."""
    got = hashlib.sha256(data).hexdigest()
    return [] if got == WORKFLOW_SHA256 else [f"workflow sha256 {got} != reviewed snapshot {WORKFLOW_SHA256}"]


def write_surface(text):
    """Bounded, fail-closed write-surface read of the committed model. Returns (inventory, violations).

    A line-wise text heuristic, NOT a shell parser: it flags file-mutating verbs, redirections,
    GitHub env/path/output channels and redirect targets outside runner scratch or onto gate paths.
    Writes through anything it does not recognise (interpreters, eval'd strings) are not seen -
    the exact-bytes pin, not this function, is what freezes the committed behaviour.
    """
    inventory, bad = [], []
    for idx, (_name, _env, script) in enumerate(steps(text), 1):
        for ln in re.sub(r"\\\n\s*", " ", script).splitlines():
            ln = ln.strip()
            targets = [t for t in REDIRECT_RE.findall(ln) if t != "/dev/null"]
            if WRITE_VERB_RE.search(ln) or targets:
                inventory.append((idx, re.sub(r"\s+", " ", ln)))
            for t in targets:
                if not SAFE_TARGET_RE.match(t) or GATE_PATH_RE.search(t):
                    bad.append(f"step {idx}: redirect target outside runner scratch or onto a gate path: {t}")
            if CHANNEL_RE.search(ln):
                bad.append(f"step {idx}: GitHub env/path/output channel: {ln}")
    if tuple(inventory) != WRITE_SURFACE:
        added = [e for e in inventory if e not in WRITE_SURFACE]
        removed = [e for e in WRITE_SURFACE if e not in inventory]
        bad.append(f"write inventory differs from the frozen model: added {added}, removed {removed}"
                   if added or removed else "write inventory reordered/duplicated")
    return inventory, bad


def regions(data):
    """Split workflow bytes into (label, [lines]) for the preamble and each step, in file order."""
    lines = data.decode("utf-8").splitlines(keepends=True)
    starts = [i for i, ln in enumerate(lines) if ln.startswith("      - name: ")]
    bounds = [0] + starts + [len(lines)]
    out = [("preamble", lines[:starts[0]])]
    out += [(f"step {n}", lines[a:b]) for n, (a, b) in enumerate(zip(starts, bounds[2:]), 1)]
    return out


def region_mutants(data):
    """{label: mutated bytes}: insertion, reorder, whitespace (trailing, blank-line, CRLF) per region."""
    regs = regions(data)
    assert len(regs) == 1 + len(EXPECTED_STEPS), [label for label, _ in regs]
    out = {}
    for k, (label, lines) in enumerate(regs):
        def put(new_lines, k=k):
            return "".join("".join(new_lines if j == k else r[1]) for j, r in enumerate(regs)).encode("utf-8")
        last = max(i for i, ln in enumerate(lines) if ln.strip())
        pair = next(i for i in range(1, len(lines) - 1)
                    if lines[i].strip() and lines[i + 1].strip() and lines[i] != lines[i + 1])
        body = "          echo tripwire\n" if label != "preamble" else "# tripwire\n"
        out[f"{label}: insert line"] = put(lines[:last + 1] + [body] + lines[last + 1:])
        out[f"{label}: insert line first"] = put(lines[:1] + [body] + lines[1:]) if label != "preamble" \
            else put([body] + lines)
        swapped = list(lines)
        swapped[pair], swapped[pair + 1] = swapped[pair + 1], swapped[pair]
        out[f"{label}: reorder adjacent lines"] = put(swapped)
        out[f"{label}: trailing space"] = put(lines[:last] + [lines[last].rstrip("\n") + " \n"] + lines[last + 1:])
        out[f"{label}: extra blank line"] = put(lines + ["\n"])
        out[f"{label}: CRLF"] = put([ln.replace("\n", "\r\n") for ln in lines])
    return out


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_lines(text):
    """Lines with full-line comments removed (header prose mentions forbidden words)."""
    return [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]


def trigger_block(text):
    lines = code_lines(text)
    out, inside = [], False
    for ln in lines:
        if re.match(r"^on:\s*$", ln):
            inside = True
            continue
        if inside and re.match(r"^\S", ln):
            break
        if inside:
            out.append(ln)
    return out


def steps(text):
    """[(name, env_lines, run_script)] in order."""
    lines = code_lines(text)
    found, cur = [], None
    for ln in lines:
        m = re.match(r"^      - name: (.*)$", ln)
        if m:
            cur = {"name": m.group(1), "body": []}
            found.append(cur)
        elif cur is not None:
            cur["body"].append(ln)
    result = []
    for step in found:
        body = step["body"]
        run, env, mode = [], [], None
        for ln in body:
            if re.match(r"^        run: \|\s*$", ln):
                mode = "run"
            elif re.match(r"^        env:\s*$", ln):
                mode = "env"
            elif re.match(r"^        \S", ln):
                mode = None
            elif mode == "run":
                run.append(ln[10:] if ln.startswith(" " * 10) else ln.strip())
            elif mode == "env":
                env.append(ln)
        result.append((step["name"], env, "\n".join(run) + "\n"))
    return result


def audit(text):
    """Return a list of policy violations (empty means the candidate is sound)."""
    bad = []
    code = "\n".join(code_lines(text))
    joined = re.sub(r"\\\n\s*", " ", code)  # shell line continuations folded
    parsed = steps(text)

    # --- inert trigger --------------------------------------------------
    tb = trigger_block(text)
    keys = [m.group(1) for ln in tb if (m := re.match(r"^  ([A-Za-z_]+):", ln))]
    if keys != ["push"]:
        bad.append(f"trigger keys are {keys}, expected exactly ['push']")
    if set(keys) & FORBIDDEN_TRIGGERS:
        bad.append("forbidden trigger present")
    for word in FORBIDDEN_TRIGGERS:
        if re.search(rf"(^|\s){word}\s*:", "\n".join(tb)):
            bad.append(f"forbidden trigger {word}")
    if re.search(r"^on:[ \t]*\S", code, re.MULTILINE):
        bad.append("inline/non-block on: form")
    branches = [m.group(1).strip().strip("'\"") for ln in tb if (m := re.match(r"^\s+- (.+)$", ln))]
    if branches != [CANDIDATE_BRANCH]:
        bad.append(f"branches are {branches}, expected only the candidate-only branch")
    if any(k in "\n".join(tb) for k in ("paths", "tags", "branches-ignore", "*")):
        bad.append("trigger uses wildcard/tags/paths/ignore")
    if "main" in branches or "master" in branches:
        bad.append("default branch is a trigger")

    # --- structure: one job, exact ordered steps, no flow-control escapes ---
    top = re.findall(r"^([A-Za-z_-]+):", code, re.MULTILINE)
    if top != ["name", "on", "permissions", "jobs"]:
        bad.append(f"top-level keys are {top}")
    jobs_text = code.split("\njobs:\n", 1)[1] if "\njobs:\n" in code else ""
    job_ids = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", jobs_text, re.MULTILINE)
    if job_ids != ["typecheck-required-candidate"]:
        bad.append(f"jobs are {job_ids}, expected exactly one")
    job_keys = re.findall(r"^    ([A-Za-z0-9_-]+):", jobs_text, re.MULTILINE)
    if job_keys != ["name", "runs-on", "timeout-minutes", "steps"]:
        bad.append(f"job keys are {job_keys}")
    if re.findall(r"^      - (?!name: )", jobs_text, re.MULTILINE):
        bad.append("step list item that does not start with name:")
    step_keys = re.findall(r"^        ([A-Za-z0-9_-]+):", jobs_text, re.MULTILINE)
    if not set(step_keys) <= {"env", "shell", "run"}:
        bad.append(f"unexpected step keys: {sorted(set(step_keys) - {'env', 'shell', 'run'})}")
    if re.search(r"continue-on-error|\bif\s*:|\|\|\s*true\b|\bneeds\s*:|\bstrategy\s*:", code):
        bad.append("flow-control escape (continue-on-error/if/|| true/needs/strategy)")
    names = [n for n, _e, _s in parsed]
    if len(names) != len(EXPECTED_STEPS) or not all(n.startswith(p) for n, p in zip(names, EXPECTED_STEPS)):
        bad.append(f"steps are {names}, expected the exact ordered set {list(EXPECTED_STEPS)}")
    for name, _env, script in parsed:
        if not script.startswith("set -euo pipefail\n"):
            bad.append(f"step '{name}' does not start with set -euo pipefail")
    if code.count("set +e") != 1 or code.count("\n          set -e\n") != 1:
        bad.append("set +e must appear exactly once, around the wrapper call")

    # --- no authority ---------------------------------------------------
    if not re.search(r"^permissions: \{\}\s*$", code, re.MULTILINE):
        bad.append("top-level permissions: {} missing")
    if len(re.findall(r"\bpermissions\s*:", code)) != 1:
        bad.append("extra permissions key")
    for pat, why in ((r"\bsecrets\.", "secret reference"), (r"GITHUB_TOKEN", "token reference"),
                     (r"^\s*-?\s*uses\s*:", "action reference"), (r"id-token", "oidc permission"),
                     (r"\bcontainer\s*:|\bservices\s*:", "container/services"),
                     (r"upload-artifact|download-artifact|actions/cache", "artifact/cache action"),
                     (r"\b(curl|wget)\b", "ad-hoc download"),
                     (r"\bgit\s+(clone|pull)\b|--branch\b|refs/heads/(main|master)\b.*fetch", "ref drift"),
                     (r"\bFETCH_HEAD\b.*\b(main|master)\b", "ref drift")):
        if re.search(pat, code, re.MULTILINE):
            bad.append(why)

    # --- expressions only in env, from the allowlist --------------------
    for ln in code_lines(text):
        for expr in re.findall(r"\$\{\{\s*(.*?)\s*\}\}", ln):
            if expr not in ALLOWED_EXPRESSIONS:
                bad.append(f"expression not allowlisted: {expr}")
            if not re.match(r"^          [A-Z_]+: \$\{\{ [a-z_.]+ \}\}(/\$\{\{ [a-z_.]+ \}\}\.git)?$", ln) \
               and not re.match(r"^          [A-Z_]+: \$\{\{ [a-z_.]+ \}\}.*$", ln):
                bad.append(f"expression outside an env mapping: {ln.strip()}")
    for name, _env, script in parsed:
        if "${{" in script:
            bad.append(f"expression interpolated into script body of '{name}'")

    # --- trusted-definition boundary (BUG-061) ----------------------------
    for prefix, want in EXPECTED_ENV.items():
        match = [env for n, env, _s in parsed if n.startswith(prefix)]
        got = {}
        for ln in (match[0] if match else []):
            m = re.match(r"^          ([A-Z_0-9]+): (.*)$", ln)
            if m:
                got[m.group(1)] = m.group(2).strip()
        if got != want:
            bad.append(f"env of '{prefix}' is {got}, expected {want}")
    fetches = re.findall(r'^\s*git -C "\$(\w+)" fetch -q --no-tags --depth=1 "\$REPO_URL" "\$(\w+)"\s*$',
                         code, re.MULTILINE)
    if fetches != [("work", "TRUSTED_SHA"), ("src", "SOURCE_SHA")] or len(re.findall(r"\bgit\b[^\n]*\bfetch\b", code)) != 2:
        bad.append(f"fetches are {fetches}, expected trusted->work then source->bare src only")
    if len(re.findall(r"\bgit\b[^\n]*\bcheckout\b", code)) != 1 \
       or '-C "$work" -c advice.detachedHead=false checkout -q FETCH_HEAD' not in code:
        bad.append("exactly one checkout, of the trusted fetch into $work, is allowed")
    if re.search(r"\bgit\b[^\n]*\b(archive|worktree|clone|read-tree|restore|reset|merge|submodule|apply|am)\b", code):
        bad.append("git verb that could materialize or run source content")
    if 'git init -q --bare "$src"' not in code:
        bad.append("source objects must live in a bare store")
    tamper_scripts = [s for n, _e, s in parsed if n.startswith("Deny candidate tamper")]
    ts = tamper_scripts[0] if tamper_scripts else ""
    for rel in PROTECTED:
        if f"            {rel}" not in ts and f" {rel}" not in ts:
            bad.append(f"tamper compare does not cover {rel}")
    for needle in ('[[ "$(git -C "$work" rev-parse HEAD)" == "$TRUSTED_SHA" ]] || deny "trusted tree is not $TRUSTED_SHA"',
                   '[[ "$(git -C "$src" rev-parse "$SOURCE_SHA^{commit}")" == "$SOURCE_SHA" ]] \\\n  || deny "source objects are not commit $SOURCE_SHA"',
                   'want="$(git -C "$work" ls-tree --full-tree "$TRUSTED_SHA" -- "$rel")"',
                   'got="$(git -C "$src" ls-tree --full-tree "$SOURCE_SHA" -- "$rel")"',
                   '[[ "$got" == "$want" ]]',
                   '[[ "$mode" == "100644" && "$type" == "blob" ]]',
                   'git -C "$src" cat-file blob "$oid" > "$stage/$path"',
                   'rm -rf "$work/backend/app"',
                   'case "$path" in backend/app/?*) ;;',
                   '*/../*|*/./*|*//*|*/.git/*) deny'):
        if needle not in ts:
            bad.append(f"tamper/materialize step missing: {needle}")
    for ln in code_lines(text):
        if re.search(r'\$(src|stage)\b|source-app|source\.git', ln):
            if EXEC_WORD_RE.search(ln) or re.search(r'cd\s+"?\$(src|stage)', ln) \
               or re.match(r'^\s*"?\$(src|stage)', ln):
                bad.append(f"source content reaches an execution word: {ln.strip()}")
        if re.search(r'\s-I\s', ln) and re.search(r'\$(src|stage)\b|source', ln):
            bad.append(f"isolated interpreter pointed at source: {ln.strip()}")
    for tool in ("assert_ci_python313", "run_scoped_mypy"):
        prefixes = set(re.findall(rf'([^\s"/]*(?:/[^\s"/]+)*/?)tools/{tool}\.py', code))
        if not prefixes <= {"$RUNNER_TEMP/work/", "$work/", ""}:
            bad.append(f"{tool}.py referenced outside the trusted tree: {sorted(prefixes)}")
    if 'assert="$RUNNER_TEMP/work/tools/assert_ci_python313.py"' not in code:
        bad.append("assertion script is not run from the trusted tree")

    # --- steps 2 and 3 are frozen line-for-line (BUG-062 round 2) ----------
    for prefix, frozen in (("Guard pinned inputs", GUARD_STEP_LINES), ("Deny candidate tamper", TAMPER_STEP_LINES)):
        got_lines = [ln.rstrip() for n, _e, s in parsed if n.startswith(prefix) for ln in s.splitlines() if ln.strip()]
        if tuple(got_lines) != frozen:
            extra = [ln for ln in got_lines if ln not in frozen]
            missing = [ln for ln in frozen if ln not in got_lines]
            bad.append(f"step '{prefix}' differs from the frozen script: added {extra}, removed {missing}"
                       if extra or missing else f"step '{prefix}' lines reordered/duplicated")

    # --- exact head fetch, no drift ------------------------------------
    for needle in ('[[ "$TRUSTED_SHA" =~ ^[0-9a-f]{40}$ ]]', '[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]',
                   "fetch -q --no-tags --depth=1", 'rev-parse HEAD)" == "$TRUSTED_SHA"',
                   'refs/heads/' + CANDIDATE_BRANCH, '"$EVENT_NAME" == "push"'):
        if needle not in code:
            bad.append(f"fetch/ref guard missing: {needle}")

    # --- pinned hashes equal the committed files -------------------------
    for env_name, (rel, fixed) in PINS.items():
        m = re.search(rf"^\s+{env_name}: ([0-9a-f]{{64}})\s*$", code, re.MULTILINE)
        actual = sha256_of(REPO / rel)
        if not m:
            bad.append(f"{env_name} pin missing")
        elif m.group(1) != actual:
            bad.append(f"{env_name} pin {m.group(1)} != committed {rel} {actual}")
        if fixed and (not m or m.group(1) != fixed):
            bad.append(f"{env_name} is not the CAP-012 approved value")

    # --- install: the only installer anywhere, hash-enforced, lock only ----
    for name, _env, script in parsed:
        n_inst = len(INSTALLER_RE.findall(script))
        want_n = 1 if name.startswith("Hash-enforced install") else 0
        if n_inst != want_n:
            bad.append(f"step '{name}' has {n_inst} installer invocation(s), expected {want_n}")
    inst = [s for n, _e, s in parsed if n.startswith("Hash-enforced install")]
    inst_script = inst[0] if inst else ""
    for flag in ("--require-hashes", "--only-binary=:all:", "--no-deps", '-r "$lock"', "--no-cache-dir",
                 "--index-url https://pypi.org/simple", "export PIP_CONFIG_FILE=/dev/null",
                 'case "$v" in PIP_*) unset "$v" ;; esac'):
        if flag not in inst_script:
            bad.append(f"install step missing: {flag}")
    if re.search(r"pip install[^\n]*(--upgrade|-U\b|--pre\b|--extra-index-url|--find-links|-e\b|--no-verify)", joined):
        bad.append("weakened install flag")

    # --- never mypy directly; the wrapper is the only entry ---------------
    if re.search(r"-m\s+mypy\b|\bmypy\s+(--|app|backend)|bin/mypy", code):
        bad.append("direct mypy invocation")
    if len(re.findall(r'-I "\$work/tools/run_scoped_mypy\.py"', code)) != 1 or ENV_I_CALL not in code:
        bad.append("wrapper is not invoked once, under env -i, from the trusted tree")

    # --- the wrapper step's load-bearing lines (BUG-062) --------------------
    wrap = [s for n, _e, s in parsed if n.startswith("Scoped wrapper")]
    ws = wrap[0] if wrap else ""
    if SUCCESS_GREP not in ws:
        bad.append("exact non-zero-file success diagnostic grep missing or weakened")
    if MARKER_GREP not in ws:
        bad.append("rc=0 marker grep missing or weakened")
    if not re.search(r"if printf '%s\\n' \"\$out\" \| grep -E '\^DENY:' >/dev/null; then\n"
                     r"\s+echo \"DENY: [^\n]*\" >&2\n\s+exit 1\n\s*fi\n", ws):
        bad.append("DENY-line screen missing or weakened")
    if len(re.findall(r"\|\| \{ echo \"DENY: [^\n]*\" >&2; exit 1; \}", ws)) != 2:
        bad.append("success/marker greps must each deny on failure")

    # --- rc handling: only 0 passes --------------------------------------
    if not re.search(r"^\s+0\) ;;\s*$", code, re.MULTILINE):
        bad.append("rc 0 arm missing")
    for arm in ("1)", "2)", "*)"):
        m = re.search(rf"^\s+{re.escape(arm)} .*$", code, re.MULTILINE)
        if not m or "exit 1" not in m.group(0):
            bad.append(f"rc arm {arm} does not exit 1")

    # --- claims wording ---------------------------------------------------
    if "NO GATE CREDIT" not in text:
        bad.append("no-gate-credit wording missing")
    return bad


def tamper(text, old, new, count=1):
    assert old in text, f"tamper anchor absent: {old!r}"
    return text.replace(old, new, count)


def round2_mutants(t):
    """BUG-062 round-2 mutants of steps 2 and 3 (post-pin source overwrite, neutered/removed pin compare)."""
    wipe = '          rm -rf "$work/backend/app"\n'
    return {
        "M1 cp source over trusted wrapper": tamper(
            t, wipe, '          cp "$stage/backend/app/__init__.py" "$work/tools/run_scoped_mypy.py"\n' + wipe),
        "M1b cat source over trusted assert script": tamper(
            t, wipe, '          cat "$stage/backend/app/__init__.py" > "$work/tools/assert_ci_python313.py"\n' + wipe),
        "M5b pin compares got to got": tamper(
            t, '[[ "$got" == "$want" ]] || { echo "DENY: $path sha256', '[[ "$got" == "$got" ]] || { echo "DENY: $path sha256'),
        "M5c wrapper pin check removed": tamper(
            t, '          check "$work/tools/run_scoped_mypy.py" "$WRAPPER_SHA256"\n', ""),
    }


class FakeBash:
    """Run an extracted step script under bash with a scratch RUNNER_TEMP."""

    @staticmethod
    def run(script, env, cwd):
        full = {"PATH": os.environ["PATH"], "HOME": str(cwd)}
        full.update(env)
        return subprocess.run(["bash", "-c", script], env=full, cwd=cwd, capture_output=True,
                              text=True, timeout=60)


def step_script(name_prefix, text=None):
    for name, _env, script in steps(text if text is not None else WORKFLOW.read_text(encoding="utf-8")):
        if name.startswith(name_prefix):
            return script
    raise AssertionError(f"step not found: {name_prefix}")


POISON = {
    "PYTHONPATH": "/evil", "PYTHONSTARTUP": "/evil", "MYPYPATH": "/evil", "MYPY_CACHE_DIR": "/evil",
    "PIP_INDEX_URL": "https://evil.invalid/simple", "SECRET_TOKEN": "x", "LD_PRELOAD": "/evil",
}


class WrapperHarness:
    """Run the final-step script against a stub interpreter standing in for the wrapper run."""

    SUCCESS = ('{"plan": "json"}\nSuccess: no issues found in 25 source files\n'
               "run_scoped_mypy: rc=0 — no type errors\n")

    @classmethod
    def run(cls, script, rc, output, extra_env=None):
        tmp = Path(tempfile.mkdtemp(prefix="tcrc-wrap-")).resolve()
        try:
            (tmp / "work/backend/app").mkdir(parents=True)
            (tmp / "work/tools").mkdir(parents=True)
            (tmp / "venv-typecheck/bin").mkdir(parents=True)
            (tmp / "payload.txt").write_text(output, encoding="utf-8")
            stub = tmp / "venv-typecheck/bin/python"
            stub.write_text(f'#!/bin/bash\nenv > "{tmp}/envdump.txt"\ncat "{tmp}/payload.txt"\nexit {rc}\n')
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
            env = {"RUNNER_TEMP": str(tmp)}
            env.update(extra_env or {})
            r = FakeBash.run(script, env, tmp)
            dump = (tmp / "envdump.txt").read_text() if (tmp / "envdump.txt").exists() else ""
            link = (tmp / "work/backend/.venv").is_symlink()
            return r, dump, link
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @classmethod
    def failures(cls, script):
        """Labels of expectations the given wrapper-step script violates (empty = behaves)."""
        bad = []
        r, _d, _l = cls.run(script, 0, cls.SUCCESS)
        if r.returncode != 0:
            bad.append("exact success did not pass")
        for label, rc, out in (
            ("rc1", 1, "app/x.py:1: error: boom\n"), ("rc2", 2, "DENY: scope\n"), ("rc3", 3, cls.SUCCESS),
            ("empty", 0, ""),
            ("zero files", 0, "Success: no issues found in 0 source files\nrun_scoped_mypy: rc=0 — ok\n"),
            ("no marker", 0, "Success: no issues found in 25 source files\n"),
            ("no success line", 0, "run_scoped_mypy: rc=0 — ok\n"),
            ("DENY line present", 0, cls.SUCCESS + "DENY: something\n"),
        ):
            r, _d, _l = cls.run(script, rc, out)
            if r.returncode == 0:
                bad.append(f"accepted: {label}")
        _r, dump, _l = cls.run(script, 0, cls.SUCCESS, POISON)
        leaked = sorted(k for k in POISON if re.search(rf"^{k}=", dump, re.MULTILINE))
        if not dump:
            bad.append("wrapper stub never ran")
        if leaked:
            bad.append(f"environment not cleared: {leaked}")
        return bad


class AuditPolicyTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_committed_candidate_audits_clean(self):
        self.assertEqual(audit(self.text), [])

    def test_pinned_wrapper_is_the_cap012_approved_hash(self):
        self.assertEqual(sha256_of(REPO / "tools/run_scoped_mypy.py"), WRAPPER_SHA256)

    def _bug062_mutants(self):
        t = self.text
        no_deny = re.sub(r"          if printf '%s\\n' \"\$out\" \| grep -E '\^DENY:'.*?\n          fi\n", "", t,
                         flags=re.DOTALL)
        return {
            "zero-file success regex": tamper(t, "[1-9][0-9]* source files", "[0-9]* source files"),
            "removed DENY screen": no_deny,
            "dropped env -i": tamper(t, "env -i PATH=/usr/bin:/bin", "env PATH=/usr/bin:/bin"),
            "added pip3 install": tamper(
                t, '          "$RUNNER_TEMP/venv-typecheck/bin/python" -m pip list',
                '          pip3 install requests\n          "$RUNNER_TEMP/venv-typecheck/bin/python" -m pip list'),
            "extra job": t.rstrip("\n") + "\n\n  extra:\n    runs-on: ubuntu-24.04\n    steps:\n"
                                          "      - name: extra\n        run: echo hi\n",
        }

    def test_bug062_mutants_are_flagged_by_audit(self):
        for label, mutated in self._bug062_mutants().items():
            with self.subTest(label):
                self.assertNotEqual(mutated, self.text, "mutant was a no-op")
                self.assertNotEqual(audit(mutated), [], f"mutant survives audit: {label}")

    def test_round2_mutants_are_flagged_by_audit(self):
        for label, mutated in round2_mutants(self.text).items():
            with self.subTest(label):
                self.assertNotEqual(mutated, self.text, "mutant was a no-op")
                self.assertNotEqual(audit(mutated), [], f"mutant survives audit: {label}")

    def test_wrapper_step_mutants_are_also_killed_by_execution(self):
        """Independent of audit(): run the mutated wrapper step under the behaviour matrix."""
        mutants = self._bug062_mutants()
        self.assertEqual(WrapperHarness.failures(step_script("Scoped wrapper", self.text)), [])
        for label in ("zero-file success regex", "removed DENY screen", "dropped env -i"):
            with self.subTest(label):
                script = step_script("Scoped wrapper", mutants[label])
                self.assertNotEqual(WrapperHarness.failures(script), [], f"behaviour matrix missed: {label}")

    def test_tampers_are_flagged(self):
        t = self.text
        cases = {
            "pull_request trigger": tamper(t, "on:\n  push:", "on:\n  pull_request:\n  push:"),
            "pull_request_target trigger": tamper(
                t, "on:\n  push:", "on:\n  pull_request_target:\n    branches:\n      - main\n  push:"),
            "workflow_dispatch": tamper(t, "on:\n  push:", "on:\n  workflow_dispatch:\n  push:"),
            "schedule": tamper(t, "on:\n  push:", "on:\n  schedule:\n    - cron: '0 0 * * *'\n  push:"),
            "default branch": tamper(t, f"      - {CANDIDATE_BRANCH}", "      - main"),
            "wildcard branch": tamper(t, f"      - {CANDIDATE_BRANCH}", f"      - {CANDIDATE_BRANCH}\n      - '**'"),
            "extra branch": tamper(t, f"      - {CANDIDATE_BRANCH}", f"      - {CANDIDATE_BRANCH}\n      - other"),
            "stale wrapper pin": tamper(t, WRAPPER_SHA256, "0" * 64),
            "stale lock pin": tamper(t, re.search(r"LOCK_SHA256: ([0-9a-f]{64})", t).group(1), "1" * 64),
            "action reference": tamper(t, "    steps:\n", "    steps:\n      - uses: actions/checkout@v4\n"),
            "secret reference": tamper(t, "SOURCE_SHA: ${{ github.sha }}", "SOURCE_SHA: ${{ secrets.X }}"),
            "broad permissions": tamper(t, "\npermissions: {}\n", "\npermissions: write-all\n"),
            "pr head sha expr as source": tamper(t, "SOURCE_SHA: ${{ github.sha }}",
                                                 "SOURCE_SHA: ${{ github.event.pull_request.head.sha }}"),
            "pr head sha expr as trusted": tamper(t, "TRUSTED_SHA: ${{ github.sha }}",
                                                  "TRUSTED_SHA: ${{ github.event.pull_request.head.sha }}"),
            "interpolation into script": tamper(t, 'echo "trusted sha: $TRUSTED_SHA"',
                                                'echo "trusted sha: ${{ github.head_ref }}"'),
            "direct mypy": tamper(t, '"$venv/bin/python" -I "$work/tools/run_scoped_mypy.py"',
                                  '"$venv/bin/python" -m mypy backend/app'),
            "dropped hash enforcement": tamper(t, "            --require-hashes --only-binary", "            --only-binary"),
            "extra index": tamper(t, "--no-deps \\\n", "--no-deps --extra-index-url https://example.invalid/simple \\\n"),
            "PIP_ unset loop removed": tamper(t, 'for v in $(compgen -e); do case "$v" in PIP_*) unset "$v" ;; esac; done\n', ""),
            "rc2 accepted": re.sub(r"(\n\s+2\) )echo [^\n]*", r"\1;;", t),
            "rc1 accepted": re.sub(r"(\n\s+1\) )echo [^\n]*", r"\1;;", t),
            "default rc accepted": re.sub(r"(\n\s+\*\) )echo [^\n]*", r"\1;;", t),
            "no-gate wording dropped": t.replace("NO GATE CREDIT", "gate"),
            # structure / flow control
            "continue-on-error": tamper(t, "        shell: bash\n        run: |\n          set -euo pipefail\n          work=\"$RUNNER_TEMP/work\"\n          check()",
                                        "        continue-on-error: true\n        shell: bash\n        run: |\n          set -euo pipefail\n          work=\"$RUNNER_TEMP/work\"\n          check()"),
            "step if": tamper(t, "      - name: Create venv", "      - if: always()\n        name: Create venv"),
            "or true": tamper(t, "exit 1; }\n          printf '%s\\n' \"$out\" | grep -E '^run_scoped_mypy",
                              "exit 1; } || true\n          printf '%s\\n' \"$out\" | grep -E '^run_scoped_mypy"),
            "step removed": tamper(t, "      - name: Create venv from asserted interpreter (bundled pip, not upgraded)\n        shell: bash\n        run: |\n          set -euo pipefail\n          py=",
                                   "      - name: Create venv from asserted interpreter (bundled pip, not upgraded)\n        shell: bash\n        run: |\n          set -euo pipefail\n          py="
                                   ).replace("      - name: Resolve and assert CPython 3.13", "      - name: Resolve and assert CPython 3.12", 1),
            "pipefail dropped": tamper(t, "          set -euo pipefail\n          py=", "          set -eu\n          py="),
            # BUG-061 trusted-definition boundary
            "wrapper run from source": tamper(t, '-I "$work/tools/run_scoped_mypy.py"', '-I "$stage/tools/run_scoped_mypy.py"'),
            "assert script from source": tamper(t, 'assert="$RUNNER_TEMP/work/tools/assert_ci_python313.py"',
                                                'assert="$RUNNER_TEMP/source-app/tools/assert_ci_python313.py"'),
            "tamper compare neutered": tamper(t, '[[ "$got" == "$want" ]] \\', 'true \\'),
            "protected path dropped": tamper(t, "            backend/pyproject.toml backend/mypy.ini", "            backend/mypy.ini"),
            "executable mode accepted": tamper(t, '[[ "$mode" == "100644" && "$type" == "blob" ]]',
                                               '[[ "$type" == "blob" ]]'),
            "path screen dropped": tamper(t, "*/../*|*/./*|*//*|*/.git/*) deny", "*/.git/*) deny"),
            "scope screen dropped": tamper(t, "case \"$path\" in backend/app/?*) ;; *) deny \"source entry outside backend/app: '$path'\" ;; esac",
                                           "true"),
            "source checked out": tamper(t, 'git -C "$src" fetch -q', 'git -C "$src" checkout -q "$SOURCE_SHA"\n          git -C "$src" fetch -q'),
            "source archived": tamper(t, 'git -C "$src" cat-file blob "$oid" > "$stage/$path"',
                                      'git -C "$src" archive "$SOURCE_SHA" | tar -x -C "$stage"'),
            "source run": tamper(t, 'rm -rf "$work/backend/app"', 'python3 "$stage/backend/app/__init__.py"\n          rm -rf "$work/backend/app"'),
            "source fetched into trusted tree": tamper(t, 'git -C "$src" fetch -q --no-tags --depth=1 "$REPO_URL" "$SOURCE_SHA"',
                                                       'git -C "$work" fetch -q --no-tags --depth=1 "$REPO_URL" "$SOURCE_SHA"'),
            "trusted not verified": tamper(t, '[[ "$(git -C "$work" rev-parse HEAD)" == "$TRUSTED_SHA" ]] || deny', 'true || deny'),
            "app not replaced": tamper(t, 'rm -rf "$work/backend/app"\n', ""),
        }
        cases.update({f"bug062: {k}": v for k, v in self._bug062_mutants().items()})
        cases.update({f"round2: {k}": v for k, v in round2_mutants(t).items()})
        for label, mutated in cases.items():
            with self.subTest(label):
                self.assertNotEqual(mutated, t, "tamper was a no-op")
                self.assertNotEqual(audit(mutated), [], f"tamper not detected: {label}")

    def test_candidate_branch_does_not_exist(self):
        if shutil.which("git") is None:
            self.skipTest("git unavailable")
        out = subprocess.run(["git", "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes",
                              "refs/tags"], cwd=REPO, capture_output=True, text=True)
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        for ref in out.stdout.split():
            self.assertNotIn("typecheck-required", ref, f"candidate ref exists: {ref}")


class ClosedWorldSnapshotTest(unittest.TestCase):
    """BUG-062 round 3: exact-current-snapshot pin over all seven steps + preamble, and a bounded write surface.

    Tripwire for reviewed bytes only: it does not defend against a coordinated workflow+test edit,
    and it is not CI evidence or gate credit.
    """

    def setUp(self):
        self.data = WORKFLOW.read_bytes()

    def test_committed_workflow_is_the_exact_reviewed_snapshot(self):
        self.assertEqual(snapshot_violations(self.data), [])
        self.assertEqual(len(regions(self.data)), 1 + len(EXPECTED_STEPS))

    def test_every_region_mutant_changes_bytes_and_is_denied_by_the_snapshot(self):
        mutants = region_mutants(self.data)
        for label in ("preamble", *(f"step {n}" for n in range(1, len(EXPECTED_STEPS) + 1))):
            for kind in ("insert line", "insert line first", "reorder adjacent lines", "trailing space",
                         "extra blank line", "CRLF"):
                self.assertIn(f"{label}: {kind}", mutants)
        for label, mutated in mutants.items():
            with self.subTest(label):
                self.assertNotEqual(mutated, self.data, "mutant was a no-op")
                self.assertNotEqual(snapshot_violations(mutated), [], f"snapshot missed: {label}")

    def test_committed_write_surface_matches_the_frozen_model(self):
        inventory, bad = write_surface(self.data.decode("utf-8"))
        self.assertEqual(bad, [])
        self.assertEqual(tuple(inventory), WRITE_SURFACE)

    def test_write_surface_flags_added_writes_in_any_step(self):
        text = self.data.decode("utf-8")
        injected = (
            'cp "$work/backend/app/__init__.py" "$work/tools/run_scoped_mypy.py"',
            'printf x > "$RUNNER_TEMP/work/tools/assert_ci_python313.py"',
            'echo "PATH=/evil:$PATH" >> "$GITHUB_PATH"',
            'echo x | tee "$RUNNER_TEMP/work/backend/requirements-typecheck-linux-x86_64-cp313.lock.txt"',
            'sed -i s/a/b/ "$work/backend/pyproject.toml"',
            'echo x > /etc/passwd',
            'echo x > "$RUNNER_TEMP/anything"',
            'chmod +x "$work/backend/app/__init__.py"',
        )
        names = [n for n, _e, _s in steps(text)]
        for step_no, name in enumerate(names, 1):
            for cmd in injected:
                with self.subTest(f"step {step_no}: {cmd}"):
                    mutated = tamper(text, "        run: |\n          set -euo pipefail\n",
                                     f"        run: |\n          set -euo pipefail\n          {cmd}\n",
                                     count=1) if step_no == 1 else self._insert_in_step(text, name, cmd)
                    self.assertNotEqual(mutated, text)
                    self.assertNotEqual(write_surface(mutated)[1], [], "write surface missed the injected write")

    @staticmethod
    def _insert_in_step(text, name, cmd):
        head = f"      - name: {name}\n"
        start = text.index(head)
        marker = "          set -euo pipefail\n"
        at = text.index(marker, start) + len(marker)
        return text[:at] + f"          {cmd}\n" + text[at:]

    def test_write_surface_flags_removed_or_reordered_writes(self):
        text = self.data.decode("utf-8")
        removed = tamper(text, '          rm -rf "$stage"\n', "")
        self.assertNotEqual(write_surface(removed)[1], [])
        a, b = '          mkdir -p "$stage"\n', '          rm -rf "$stage"\n'
        reordered = tamper(text, b + a, a + b)
        self.assertNotEqual(write_surface(reordered)[1], [])


def _git(repo, *args, check=True):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check, env=env)


class SyntheticRepo:
    """A local git repository whose commits stand in for the trusted base and the PR head."""

    def __init__(self, root):
        self.repo = Path(root) / "src"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false"),
                     ("uploadpack.allowAnySHA1InWant", "true"), ("core.symlinks", "true")):
            _git(self.repo, "config", k, v)

    BASE = {
        ".github/workflows/typecheck-required-candidate.yml": "workflow-v1\n",
        "tools/run_scoped_mypy.py": "wrapper-v1\n",
        "tools/assert_ci_python313.py": "assert-v1\n",
        "backend/requirements-typecheck-linux-x86_64-cp313.lock.txt": "lock-v1\n",
        "backend/pyproject.toml": "[tool.mypy]\n",
        "backend/app/__init__.py": "VALUE = 1\n",
        "backend/app/pkg/mod.py": "def f() -> int:\n    return 1\n",
    }

    def commit(self, files=None, drop=(), symlinks=None, execs=(), gitlinks=None, msg="c"):
        for entry in self.repo.iterdir():
            if entry.name != ".git":
                shutil.rmtree(entry) if entry.is_dir() and not entry.is_symlink() else entry.unlink()
        for rel, body in (self.BASE if files is None else files).items():
            if rel in drop:
                continue
            dest = self.repo / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
        for rel, target in (symlinks or {}).items():
            dest = self.repo / rel
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, dest)
        for rel in execs:
            (self.repo / rel).chmod(0o755)
        _git(self.repo, "add", "-A", "-f")
        for rel, sha in (gitlinks or {}).items():
            _git(self.repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},{rel}")
        _git(self.repo, "commit", "-q", "--allow-empty", "-m", msg)
        return _git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def variant(self, **kw):
        files = dict(self.BASE)
        files.update(kw.pop("set", {}))
        return self.commit(files=files, **kw)


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "bash and git required")
class GuardStepsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tcrc-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.script = step_script("Deny unless candidate-only ref")

    def _env(self, **kw):
        base = {"EVENT_NAME": "push", "REF": f"refs/heads/{CANDIDATE_BRANCH}", "TRUSTED_SHA": "a" * 40,
                "SOURCE_SHA": "a" * 40, "REPO_URL": "file:///nonexistent-repo.git", "RUNNER_TEMP": str(self.tmp)}
        base.update(kw)
        return base

    def test_wrong_event_ref_or_sha_is_denied_before_any_fetch(self):
        for label, env, msg in (
            ("pull_request event", {"EVENT_NAME": "pull_request"}, "event is not push"),
            ("pull_request_target event", {"EVENT_NAME": "pull_request_target"}, "event is not push"),
            ("workflow_dispatch event", {"EVENT_NAME": "workflow_dispatch"}, "event is not push"),
            ("main ref", {"REF": "refs/heads/main"}, "not the candidate-only branch"),
            ("pr merge ref", {"REF": "refs/pull/7/merge"}, "not the candidate-only branch"),
            ("prefix-only ref", {"REF": f"refs/heads/{CANDIDATE_BRANCH}-x"}, "not the candidate-only branch"),
            ("short trusted sha", {"TRUSTED_SHA": "abc123"}, "trusted sha is not 40-hex"),
            ("branch name as trusted sha", {"TRUSTED_SHA": "main"}, "trusted sha is not 40-hex"),
            ("short source sha", {"SOURCE_SHA": "abc123"}, "source sha is not 40-hex"),
            ("branch name as source sha", {"SOURCE_SHA": "refs/pull/7/head"}, "source sha is not 40-hex"),
            ("empty source sha", {"SOURCE_SHA": ""}, "source sha is not 40-hex"),
        ):
            with self.subTest(label):
                r = FakeBash.run(self.script, self._env(**env), self.tmp)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(msg, r.stderr)
                self.assertFalse((self.tmp / "work").exists(), "fetch started despite a denial")
                self.assertFalse((self.tmp / "source.git").exists(), "fetch started despite a denial")

    def test_distinct_trusted_and_source_shas_are_both_fetched_exactly(self):
        syn = SyntheticRepo(self.tmp)
        trusted = syn.commit()
        source = syn.variant(set={"backend/app/pkg/mod.py": "def f() -> int:\n    return 2\n"})
        self.assertNotEqual(trusted, source)
        env = self._env(TRUSTED_SHA=trusted, SOURCE_SHA=source, REPO_URL=f"file://{syn.repo}")
        r = FakeBash.run(self.script, env, self.tmp)
        if r.returncode != 0 and "not our ref" in r.stderr:
            self.skipTest("local git transport refuses fetch by sha")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"trusted sha: {trusted}", r.stdout)
        self.assertIn(f"source sha (inert backend/app input only): {source}", r.stdout)
        self.assertIn("NO GATE CREDIT", r.stdout)
        self.assertEqual(_git(self.tmp / "work", "rev-parse", "HEAD").stdout.strip(), trusted)
        # the trusted tree is a checkout of the trusted sha, not of the source
        self.assertEqual((self.tmp / "work/backend/app/pkg/mod.py").read_text(), "def f() -> int:\n    return 1\n")
        # the source is object-store only: no work tree, no checked-out files
        self.assertEqual(_git(self.tmp / "source.git", "rev-parse", "--is-bare-repository").stdout.strip(), "true")
        self.assertFalse((self.tmp / "source.git/backend").exists())

    def test_unfetchable_source_or_trusted_sha_fails(self):
        syn = SyntheticRepo(self.tmp)
        good = syn.commit()
        for label, over in (("source", {"SOURCE_SHA": "b" * 40}), ("trusted", {"TRUSTED_SHA": "b" * 40})):
            with self.subTest(label):
                shutil.rmtree(self.tmp / "work", ignore_errors=True)
                shutil.rmtree(self.tmp / "source.git", ignore_errors=True)
                env = self._env(**{"TRUSTED_SHA": good, "SOURCE_SHA": good, "REPO_URL": f"file://{syn.repo}", **over})
                self.assertNotEqual(FakeBash.run(self.script, env, self.tmp).returncode, 0)


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "bash and git required")
class TrustedBoundaryTest(unittest.TestCase):
    """Run steps 1 and 3 against synthetic repos where the trusted sha and the source sha differ."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tcrc-tb-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.rt = self.tmp / "rt"
        self.rt.mkdir()
        self.syn = SyntheticRepo(self.tmp)
        self.step1 = step_script("Deny unless candidate-only ref")
        self.step3 = step_script("Deny candidate tamper")
        self.trusted = self.syn.commit()

    def chain(self, source, step3=None):
        env = {"EVENT_NAME": "push", "REF": f"refs/heads/{CANDIDATE_BRANCH}", "TRUSTED_SHA": self.trusted,
               "SOURCE_SHA": source, "REPO_URL": f"file://{self.syn.repo}", "RUNNER_TEMP": str(self.rt)}
        r1 = FakeBash.run(self.step1, env, self.tmp)
        if r1.returncode != 0 and "not our ref" in r1.stderr:
            self.skipTest("local git transport refuses fetch by sha")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        return FakeBash.run(step3 or self.step3, env, self.tmp)

    def work(self, rel):
        return self.rt / "work" / rel

    def assertDenied(self, source, msg):
        r = self.chain(source)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(msg, r.stderr)
        # a denial must leave the trusted app and every trusted gate file as they were
        self.assertEqual(self.work("backend/app/pkg/mod.py").read_text(), SyntheticRepo.BASE["backend/app/pkg/mod.py"])
        self.assertEqual(self.work("tools/run_scoped_mypy.py").read_text(), "wrapper-v1\n")
        return r

    def test_app_only_change_is_composed_into_the_trusted_tree(self):
        source = self.syn.variant(
            set={"backend/app/pkg/mod.py": "def f() -> int:\n    return 99\n", "backend/app/new.py": "X = 1\n"},
            drop=("backend/app/__init__.py",))
        self.assertNotEqual(source, self.trusted)
        r = self.chain(source)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.work("backend/app/pkg/mod.py").read_text(), "def f() -> int:\n    return 99\n")
        self.assertTrue(self.work("backend/app/new.py").is_file())
        self.assertFalse(self.work("backend/app/__init__.py").exists(), "trusted app file survived replacement")
        # every executable / config byte is the trusted one
        for rel in PROTECTED[:5]:
            self.assertEqual(self.work(rel).read_text(), SyntheticRepo.BASE[rel], rel)
        self.assertIn("materialized 2 inert source blobs", r.stdout)

    def test_post_pin_source_overwrite_mutants_corrupt_gate_files_but_committed_step_does_not(self):
        """Executes mutated step 3 on a synthetic tree: the mutant rewrites a pinned trusted file from source bytes."""
        text = WORKFLOW.read_text(encoding="utf-8")
        evil = "EVIL = 1\n"
        source = self.syn.variant(set={"backend/app/__init__.py": evil})
        self.assertEqual(self.chain(source).returncode, 0)
        self.assertEqual(self.work("tools/run_scoped_mypy.py").read_text(), "wrapper-v1\n")
        self.assertEqual(self.work("tools/assert_ci_python313.py").read_text(), "assert-v1\n")
        mutants = round2_mutants(text)
        for label, rel, original in (
            ("M1 cp source over trusted wrapper", "tools/run_scoped_mypy.py", "wrapper-v1\n"),
            ("M1b cat source over trusted assert script", "tools/assert_ci_python313.py", "assert-v1\n"),
        ):
            with self.subTest(label):
                shutil.rmtree(self.rt / "work", ignore_errors=True)
                shutil.rmtree(self.rt / "source.git", ignore_errors=True)
                r = self.chain(source, step3=step_script("Deny candidate tamper", mutants[label]))
                self.assertEqual(r.returncode, 0, r.stderr)  # the mutant step still "succeeds"
                self.assertEqual(self.work(rel).read_text(), evil, f"mutant is not load-bearing: {label}")
                self.assertNotEqual(self.work(rel).read_text(), original)
                self.assertNotEqual(audit(mutants[label]), [], f"audit missed: {label}")

    def test_identical_trusted_and_source_sha_works(self):
        self.assertEqual(self.chain(self.trusted).returncode, 0)

    def test_candidate_edit_of_any_gate_file_is_denied(self):
        for rel in PROTECTED[:5]:
            with self.subTest(f"edit {rel}"):
                shutil.rmtree(self.rt / "work", ignore_errors=True)
                shutil.rmtree(self.rt / "source.git", ignore_errors=True)
                source = self.syn.variant(set={rel: "TAMPERED\n"})
                self.assertDenied(source, f"candidate changed {rel}")
                self.assertNotIn("TAMPERED", self.work(rel).read_text())

    def test_candidate_delete_added_config_mode_or_symlink_of_gate_file_is_denied(self):
        cases = {
            "delete workflow": dict(drop=(PROTECTED[0],)),
            "delete pyproject": dict(drop=("backend/pyproject.toml",)),
            "add mypy.ini": dict(set={"backend/mypy.ini": "[mypy]\nplugins = evil\n"}),
            "add .mypy.ini": dict(set={"backend/.mypy.ini": "[mypy]\n"}),
            "add setup.cfg": dict(set={"backend/setup.cfg": "[mypy]\n"}),
            "add tox.ini": dict(set={"backend/tox.ini": "[mypy]\n"}),
            "wrapper made executable": dict(execs=("tools/run_scoped_mypy.py",)),
            "wrapper replaced by symlink": dict(drop=("tools/run_scoped_mypy.py",),
                                                symlinks={"tools/run_scoped_mypy.py": "/tmp/evil.py"}),
            "wrapper replaced by same-bytes symlink": dict(
                drop=("tools/run_scoped_mypy.py",), symlinks={"tools/run_scoped_mypy.py": "wrapper-v1\n"}),
        }
        for label, kw in cases.items():
            with self.subTest(label):
                shutil.rmtree(self.rt / "work", ignore_errors=True)
                shutil.rmtree(self.rt / "source.git", ignore_errors=True)
                self.assertDenied(self.syn.variant(**kw), "candidate changed")
        self.assertFalse(self.work("backend/mypy.ini").exists())

    def test_irregular_or_unsafe_source_app_entries_are_denied(self):
        cases = {
            "symlink inside app": (dict(symlinks={"backend/app/link.py": "../../tools/run_scoped_mypy.py"}),
                                   "symlink/gitlink/executable"),
            "executable inside app": (dict(execs=("backend/app/pkg/mod.py",)), "symlink/gitlink/executable"),
            "gitlink inside app": (dict(gitlinks={"backend/app/sub": "1" * 40}), "symlink/gitlink/executable"),
            "backend/app itself a symlink": (dict(drop=("backend/app/__init__.py", "backend/app/pkg/mod.py"),
                                                  symlinks={"backend/app": "../tools"}), "symlink/gitlink/executable"),
            "no backend/app": (dict(drop=("backend/app/__init__.py", "backend/app/pkg/mod.py")), "no backend/app entries"),
        }
        for label, (kw, msg) in cases.items():
            with self.subTest(label):
                shutil.rmtree(self.rt / "work", ignore_errors=True)
                shutil.rmtree(self.rt / "source.git", ignore_errors=True)
                self.assertDenied(self.syn.variant(**kw), msg)

    def test_source_content_is_never_executed(self):
        marker = self.tmp / "executed.marker"
        payload = f'open({str(marker)!r}, "w").write("x")\n'
        source = self.syn.variant(set={"backend/app/__init__.py": payload, "backend/app/conftest.py": payload,
                                       "backend/app/sitecustomize.py": payload})
        self.assertEqual(self.chain(source).returncode, 0)
        self.assertFalse(marker.exists(), "source content was executed")
        self.assertEqual(self.work("backend/app/__init__.py").read_text(), payload)


def load_wrapper():
    """The approved CAP-012 wrapper as a module, or None where it cannot import (needs Python 3.11+)."""
    try:
        spec = importlib.util.spec_from_file_location("run_scoped_mypy_under_test", REPO / "tools/run_scoped_mypy.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod  # @dataclass resolves its own module at class-creation time
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 - any import failure means the observation test is skipped
        return None


# Exact spans of the BUG-064 composition lines in step 3, used to build executable mutants.
STAGE_BLOCK_START = "          # Followed in-repository modules outside backend/app (BUG-064)."
STAGE_BLOCK_END = '          rm -rf "$work/backend/app"\n'
APPLY_BLOCK_START = "          # Replace every trusted .py/.pyi under backend/ outside app by the staged source\n"
APPLY_BLOCK_LAST = 'no trusted copy remains"\n'
REMOVE_LOOP = "          while IFS= read -r -d '' f; do rm -f \"$f\"; done < \"$RUNNER_TEMP/trusted-modules.lst\"\n"
COUNT_CHECK = (
    "          [[ \"$(find \"$work/backend\" -path \"$work/backend/app\" -prune -o \\( -name '*.py' -o -name '*.pyi' \\) "
    "\\( -type f -o -type l \\) -print | wc -l | tr -d ' ')\" == \"$outside\" ]] \\\n"
    "            || deny \"composed backend/ holds .py/.pyi files that are not in the source listing\"\n")
HASH_CHECK = (
    "            [[ \"$(git -C \"$work\" hash-object --no-filters -- \"$work/$path\")\" == \"$oid\" ]] \\\n"
    "              || deny \"followed module '$path' is not the source blob $oid\"\n")
MODE_SCREEN = (
    "                [[ \"$mode\" == \"100644\" && \"$type\" == \"blob\" ]] \\\n"
    "                  || deny \"refused source module entry")
LINK_SCREEN = (
    "            case \"$mode\" in 120000|160000) deny \"refused source entry mode $mode at '$path' "
    "(symlink/gitlink under backend)\" ;; esac\n")


def without_module_composition(text):
    """The workflow as it was before BUG-064: backend/app composed from the source, everything else trusted."""
    a = text.index(STAGE_BLOCK_START)
    b = text.index(STAGE_BLOCK_END, a)
    text = text[:a] + text[b:]
    a = text.index(APPLY_BLOCK_START)
    end = text.index(APPLY_BLOCK_LAST, a) + len(APPLY_BLOCK_LAST)
    return text[:a].rstrip("\n") + "\n" + text[end:]


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "bash and git required")
class FollowedModuleCompositionTest(unittest.TestCase):
    """BUG-064: .py/.pyi under backend/ outside app are composed from the SOURCE sha, with trusted != source."""

    UTIL = "backend/shared/util.py"
    TRUSTED_UTIL = "def u() -> int:\n    return 1\n"
    PR_UTIL = "def u() -> str:\n    return 'pr'\n"
    EXTRA_BASE = {
        "backend/shared/__init__.py": "",
        "backend/shared/util.py": TRUSTED_UTIL,
        "backend/notes.txt": "trusted notes\n",
        "backend/app/uses.py": "from shared.util import u\n",
    }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tcrc-fm-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.rt = self.tmp / "rt"
        self.rt.mkdir()
        self.syn = SyntheticRepo(self.tmp)
        self.syn.BASE = {**SyntheticRepo.BASE, **self.EXTRA_BASE}
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.step1 = step_script("Deny unless candidate-only ref")
        self.step3 = step_script("Deny candidate tamper")
        self.trusted = self.syn.commit()

    def fresh(self):
        shutil.rmtree(self.rt / "work", ignore_errors=True)
        shutil.rmtree(self.rt / "source.git", ignore_errors=True)

    def chain(self, source, step3=None):
        env = {"EVENT_NAME": "push", "REF": f"refs/heads/{CANDIDATE_BRANCH}", "TRUSTED_SHA": self.trusted,
               "SOURCE_SHA": source, "REPO_URL": f"file://{self.syn.repo}", "RUNNER_TEMP": str(self.rt)}
        r1 = FakeBash.run(self.step1, env, self.tmp)
        if r1.returncode != 0 and "not our ref" in r1.stderr:
            self.skipTest("local git transport refuses fetch by sha")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        return FakeBash.run(step3 or self.step3, env, self.tmp)

    def work(self, rel):
        return self.rt / "work" / rel

    def mutant_step3(self, mutated_text):
        self.assertNotEqual(mutated_text, self.text, "mutant was a no-op")
        self.assertNotEqual(audit(mutated_text), [], "audit missed the mutant")
        self.assertNotEqual(snapshot_violations(mutated_text.encode("utf-8")), [], "snapshot missed the mutant")
        return step_script("Deny candidate tamper", mutated_text)

    def assert_trusted_tree_untouched(self):
        self.assertEqual(self.work(self.UTIL).read_text(), self.TRUSTED_UTIL)
        self.assertEqual(self.work("backend/app/pkg/mod.py").read_text(), SyntheticRepo.BASE["backend/app/pkg/mod.py"])
        self.assertEqual(self.work("tools/run_scoped_mypy.py").read_text(), "wrapper-v1\n")

    def test_out_of_app_followed_module_edit_is_materialized_not_trusted(self):
        source = self.syn.variant(set={self.UTIL: self.PR_UTIL, "backend/notes.txt": "PR notes\n"})
        self.assertNotEqual(source, self.trusted)
        r = self.chain(source)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.work(self.UTIL).read_text(), self.PR_UTIL)
        self.assertEqual(self.work("backend/notes.txt").read_text(), "trusted notes\n", "non-Python file left trusted")
        for rel in PROTECTED[:5]:
            self.assertEqual(self.work(rel).read_text(), SyntheticRepo.BASE[rel], rel)
        self.assertIn("composed 2 followed backend/ .py/.pyi modules", r.stdout)

    def test_additions_pyi_and_nested_package_are_materialized(self):
        source = self.syn.variant(set={"backend/shared/extra.py": "E = 1\n", "backend/shared/util.pyi": "def u() -> int: ...\n",
                                       "backend/newpkg/__init__.py": "", "backend/newpkg/deep/mod.py": "D = 1\n"})
        r = self.chain(source)
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel in ("backend/shared/extra.py", "backend/shared/util.pyi", "backend/newpkg/__init__.py", "backend/newpkg/deep/mod.py"):
            self.assertTrue(self.work(rel).is_file(), rel)
        self.assertIn("composed 6 followed", r.stdout)

    def test_deletions_remove_the_trusted_copy(self):
        r = self.chain(self.syn.variant(drop=(self.UTIL,)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.work(self.UTIL).exists(), "deleted followed module survived from the trusted tree")
        self.assertTrue(self.work("backend/shared/__init__.py").is_file())
        self.fresh()
        r = self.chain(self.syn.variant(drop=(self.UTIL, "backend/shared/__init__.py")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.work("backend/shared/__init__.py").exists())
        self.assertIn("composed 0 followed", r.stdout)

    def test_unchanged_followed_modules_are_allowed_and_identical(self):
        source = self.syn.variant(set={"backend/app/pkg/mod.py": "def f() -> int:\n    return 7\n"})
        r = self.chain(source)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.work(self.UTIL).read_text(), self.TRUSTED_UTIL)
        self.assertEqual(self.work("backend/shared/__init__.py").read_text(), "")
        self.fresh()
        self.assertEqual(self.chain(self.trusted).returncode, 0)

    def test_composed_modules_equal_an_independent_git_oracle(self):
        source = self.syn.variant(set={self.UTIL: self.PR_UTIL, "backend/lib/a.py": "A = 1\n", "backend/lib/b.pyi": "B: int\n",
                                       "backend/top.py": "T = 1\n", "backend/notes.txt": "x\n"},
                                  drop=("backend/shared/__init__.py",))
        r = self.chain(source)
        self.assertEqual(r.returncode, 0, r.stderr)
        listing = _git(self.syn.repo, "ls-tree", "-r", "--name-only", source, "--", "backend").stdout.split("\n")
        want = sorted(p for p in listing if p.endswith((".py", ".pyi")) and not p.startswith("backend/app/"))
        rels = [str(p.relative_to(self.rt / "work")) for p in (self.rt / "work/backend").rglob("*") if p.is_file()]
        got = sorted(p for p in rels if p.endswith((".py", ".pyi")) and not p.startswith("backend/app/"))
        self.assertEqual(got, want)
        for rel in want:
            self.assertEqual(self.work(rel).read_text(), _git(self.syn.repo, "show", f"{source}:{rel}").stdout, rel)

    def test_unsafe_entries_outside_app_are_denied_before_the_trusted_tree_is_touched(self):
        cases = {
            "symlink module": (dict(symlinks={"backend/shared/link.py": "util.py"}), "mode 120000"),
            "symlink with a non-module name": (dict(symlinks={"backend/shared/data": "/tmp/evil"}), "mode 120000"),
            "symlink replacing a package": (dict(drop=("backend/shared/__init__.py", self.UTIL),
                                                 symlinks={"backend/shared": "../tools"}), "mode 120000"),
            "gitlink under backend": (dict(gitlinks={"backend/vendor": "1" * 40}), "mode 160000"),
            "executable module": (dict(set={self.UTIL: self.PR_UTIL}, execs=(self.UTIL,)), "executable or irregular"),
            "executable stub": (dict(set={"backend/shared/x.pyi": "x: int\n"}, execs=("backend/shared/x.pyi",)),
                                "executable or irregular"),
            "module under backend/.venv": (dict(set={"backend/.venv/lib/evil.py": "X = 1\n"}), "unsafe source path"),
        }
        for label, (kw, msg) in cases.items():
            with self.subTest(label):
                self.fresh()
                r = self.chain(self.syn.variant(**kw))
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn(msg, r.stderr)
                self.assert_trusted_tree_untouched()

    def test_gate_config_edit_is_still_denied_alongside_a_module_edit(self):
        source = self.syn.variant(set={self.UTIL: self.PR_UTIL, "backend/pyproject.toml": "[tool.mypy]\nplugins = ['evil']\n"})
        r = self.chain(source)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("candidate changed backend/pyproject.toml", r.stderr)
        self.assert_trusted_tree_untouched()

    def test_followed_module_source_is_never_executed(self):
        marker = self.tmp / "executed.marker"
        payload = f'open({str(marker)!r}, "w").write("x")\n'
        source = self.syn.variant(set={self.UTIL: payload, "backend/conftest.py": payload,
                                       "backend/sitecustomize.py": payload, "backend/setup.py": payload})
        self.assertEqual(self.chain(source).returncode, 0)
        self.assertFalse(marker.exists(), "followed source was executed")
        self.assertEqual(self.work(self.UTIL).read_text(), payload)

    def test_directory_named_like_a_module_does_not_break_composition(self):
        source = self.syn.variant(drop=(self.UTIL,), set={"backend/shared/util.py/inner.py": "I = 1\n"})
        r = self.chain(source)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.work("backend/shared/util.py/inner.py").is_file())

    # --- executable mutants: each new check must be load-bearing --------------------------------

    def test_reverting_the_fix_reproduces_the_poisoning_and_is_flagged(self):
        reverted = self.mutant_step3(without_module_composition(self.text))
        r = self.chain(self.syn.variant(set={self.UTIL: self.PR_UTIL}), step3=reverted)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.work(self.UTIL).read_text(), self.TRUSTED_UTIL, "mutant should leave trusted bytes (BUG-064)")

    def test_trusted_removal_is_load_bearing_and_defence_in_depth_catches_its_absence(self):
        source = self.syn.variant(drop=(self.UTIL,))
        no_removal = self.mutant_step3(tamper(self.text, REMOVE_LOOP, ""))
        r = self.chain(source, step3=no_removal)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not in the source listing", r.stderr)
        self.fresh()
        both = self.mutant_step3(tamper(tamper(self.text, REMOVE_LOOP, ""), COUNT_CHECK, ""))
        r = self.chain(source, step3=both)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.work(self.UTIL).read_text(), self.TRUSTED_UTIL, "stale trusted module survived a source deletion")

    def test_corrupt_staging_is_denied_by_the_hash_check_and_accepted_without_it(self):
        corrupt = tamper(self.text, 'git -C "$src" cat-file blob "$oid" > "$outstage/$path"',
                         'printf corrupt > "$outstage/$path"')
        source = self.syn.variant(set={self.UTIL: self.PR_UTIL})
        r = self.chain(source, step3=self.mutant_step3(corrupt))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is not the source blob", r.stderr)
        self.fresh()
        r = self.chain(source, step3=self.mutant_step3(tamper(corrupt, HASH_CHECK, "")))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.work(self.UTIL).read_text(), "corrupt")

    def test_dropped_screens_let_unsafe_entries_through(self):
        cases = {
            "link screen dropped": (tamper(self.text, LINK_SCREEN, ""), dict(symlinks={"backend/shared/data": "/tmp/evil"})),
            "module mode screen dropped": (
                tamper(self.text, MODE_SCREEN, MODE_SCREEN.replace('[[ "$mode" == "100644" && "$type" == "blob" ]]', "true")),
                dict(set={self.UTIL: self.PR_UTIL}, execs=(self.UTIL,))),
            "venv screen dropped": (tamper(self.text, "|*/.git/*|/backend/.venv/*) deny", "|*/.git/*) deny"),
                                    dict(set={"backend/.venv/lib/evil.py": "X = 1\n"})),
        }
        for label, (mutated, kw) in cases.items():
            with self.subTest(label):
                self.fresh()
                source = self.syn.variant(**kw)
                committed = self.chain(source)
                self.assertNotEqual(committed.returncode, 0, "committed step must deny")
                self.fresh()
                r = self.chain(source, step3=self.mutant_step3(mutated))
                self.assertEqual(r.returncode, 0, f"mutant is not load-bearing: {label}: {r.stderr}")

    # --- observation against the approved wrapper's own import-closure fingerprint --------------

    def test_wrapper_closure_fingerprint_sees_pr_bytes_only_with_the_fix(self):
        wrapper = load_wrapper()
        if wrapper is None:
            self.skipTest("wrapper not importable (needs Python 3.11+)")

        def closure(root):
            backend = Path(root) / "backend"
            _count, _digest, files = wrapper.scan_app(backend / "app")
            return wrapper.scan_import_closure(backend, backend / "app", files)

        def write_tree(root, files):
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body)
            return root

        source = self.syn.variant(set={self.UTIL: self.PR_UTIL})
        reference = write_tree(self.tmp / "reference", {**self.syn.BASE, self.UTIL: self.PR_UTIL})
        self.assertEqual(self.chain(source).returncode, 0)
        fixed = closure(self.rt / "work")
        self.assertEqual(fixed, closure(reference), "composed closure fingerprint differs from the source tree's")
        # the pre-fix composition (BUG-064) fingerprints the trusted bytes of the followed module
        self.fresh()
        reverted = self.mutant_step3(without_module_composition(self.text))
        self.assertEqual(self.chain(source, step3=reverted).returncode, 0)
        old = closure(self.rt / "work")
        self.assertNotEqual(old, fixed, "pre-fix composition should not see the PR's edit")
        self.assertEqual(old, closure(write_tree(self.tmp / "trusted-reference", self.syn.BASE)))


@unittest.skipUnless(shutil.which("bash"), "bash required")
class PinGuardStepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tcrc-pin-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        work = self.tmp / "work"
        for rel, _ in PINS.values():
            dest = work / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, dest)
        (work / "backend/app").mkdir(parents=True, exist_ok=True)
        (work / "backend/pyproject.toml").write_text("[tool.mypy]\n")
        # sha256sum may be absent (macOS); provide an equivalent shim when so.
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        if shutil.which("sha256sum") is None:
            shim = self.bin / "sha256sum"
            shim.write_text('#!/bin/bash\nexec shasum -a 256 "$@"\n')
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        self.script = step_script("Guard pinned inputs")

    def _run(self, script=None, **over):
        env = {"RUNNER_TEMP": str(self.tmp), "PATH": f"{self.bin}:{os.environ['PATH']}",
               "WRAPPER_SHA256": WRAPPER_SHA256, "ASSERT_SHA256": sha256_of(REPO / PINS["ASSERT_SHA256"][0]),
               "LOCK_SHA256": sha256_of(REPO / PINS["LOCK_SHA256"][0])}
        env.update(over)
        return FakeBash.run(script or self.script, env, self.tmp)

    def test_matching_pins_pass(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_drifted_wrapper_bytes_are_denied(self):
        with open(self.tmp / "work/tools/run_scoped_mypy.py", "ab") as fh:
            fh.write(b"# drift\n")
        r = self._run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sha256", r.stderr)

    def test_pin_guard_mutants_let_drift_through_but_committed_step_and_audit_deny(self):
        """Executes the mutated step 2: a drifted wrapper passes the mutant, is denied by the committed step."""
        text = WORKFLOW.read_text(encoding="utf-8")
        with open(self.tmp / "work/tools/run_scoped_mypy.py", "ab") as fh:
            fh.write(b"# drift\n")
        self.assertNotEqual(self._run().returncode, 0, "committed step must deny the drift")
        mutants = round2_mutants(text)
        for label in ("M5b pin compares got to got", "M5c wrapper pin check removed"):
            with self.subTest(label):
                mutant = step_script("Guard pinned inputs", mutants[label])
                self.assertEqual(self._run(script=mutant).returncode, 0, f"mutant is not load-bearing: {label}")
                self.assertNotEqual(audit(mutants[label]), [], f"audit missed: {label}")
        # the M5b mutant still denies a missing file: only the pin comparison was defeated
        os.unlink(self.tmp / "work/tools/run_scoped_mypy.py")
        self.assertNotEqual(self._run(script=step_script("Guard pinned inputs", mutants["M5b pin compares got to got"])).returncode, 0)

    def test_wrong_pin_values_and_symlinks_are_denied(self):
        for var in PINS:
            with self.subTest(var):
                self.assertNotEqual(self._run(**{var: "0" * 64}).returncode, 0)
        wrapper = self.tmp / "work/tools/run_scoped_mypy.py"
        real = self.tmp / "real_wrapper.py"
        shutil.copy2(wrapper, real)
        wrapper.unlink()
        wrapper.symlink_to(real)
        r = self._run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("symlink", r.stderr)

    def test_committed_venv_dir_or_missing_lock_is_denied(self):
        (self.tmp / "work/backend/.venv").mkdir()
        self.assertNotEqual(self._run().returncode, 0)
        shutil.rmtree(self.tmp / "work/backend/.venv")
        (self.tmp / "work" / PINS["LOCK_SHA256"][0]).unlink()
        self.assertNotEqual(self._run().returncode, 0)


@unittest.skipUnless(shutil.which("bash"), "bash required")
class WrapperStepOutcomeTest(unittest.TestCase):
    """Run the real final-step script against a stub interpreter standing in for the wrapper run."""

    SUCCESS = WrapperHarness.SUCCESS

    def setUp(self):
        self.script = step_script("Scoped wrapper on the composed backend/app")

    def _run(self, rc, output):
        return WrapperHarness.run(self.script, rc, output)[0]

    def test_rc0_with_exact_success_passes(self):
        r, _dump, linked = WrapperHarness.run(self.script, 0, self.SUCCESS)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NO GATE CREDIT", r.stdout)
        self.assertTrue(linked)

    def test_rc1_type_errors_fail(self):
        r = self._run(1, "app/x.py:1: error: boom\nFound 1 error in 1 file\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rc 1", r.stderr)

    def test_rc2_denial_fails(self):
        r = self._run(2, "DENY: scope\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rc 2", r.stderr)

    def test_other_codes_fail(self):
        for rc in (3, 127, 255):
            with self.subTest(rc=rc):
                self.assertNotEqual(self._run(rc, self.SUCCESS).returncode, 0)

    def test_rc0_without_exact_success_text_fails(self):
        for label, out in (
            ("empty", ""),
            ("zero files", "Success: no issues found in 0 source files\nrun_scoped_mypy: rc=0 — ok\n"),
            ("no marker", "Success: no issues found in 25 source files\n"),
            ("no success line", "run_scoped_mypy: rc=0 — ok\n"),
            ("DENY line present", self.SUCCESS + "DENY: something\n"),
        ):
            with self.subTest(label):
                self.assertNotEqual(self._run(0, out).returncode, 0)

    def test_wrapper_runs_under_a_cleared_environment(self):
        r, dump, _ = WrapperHarness.run(self.script, 0, self.SUCCESS, POISON)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(dump, "stub did not record its environment")
        for key in POISON:
            self.assertNotRegex(dump, rf"(?m)^{key}=", f"{key} leaked into the wrapper run")
        self.assertRegex(dump, r"(?m)^PATH=/usr/bin:/bin$")
        self.assertRegex(dump, r"(?m)^LC_ALL=C\.UTF-8$")

    def test_full_behaviour_matrix_is_clean(self):
        self.assertEqual(WrapperHarness.failures(self.script), [])


@unittest.skipUnless(shutil.which("bash"), "bash required")
class InstallStepTest(unittest.TestCase):
    """The install step must strip PIP_* settings and run exactly one hash-enforced lock install."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tcrc-inst-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "venv-typecheck/bin").mkdir(parents=True)
        (self.tmp / "work/backend").mkdir(parents=True)
        stub = self.tmp / "venv-typecheck/bin/python"
        stub.write_text(f'#!/bin/bash\n{{ echo "ARGV: $*"; env | grep "^PIP_" | sed "s/^/ENV: /"; }} >> "{self.tmp}/calls.txt"\n')
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        self.script = step_script("Hash-enforced install")

    def test_pip_environment_is_stripped_and_flags_are_enforced(self):
        poison = {"PIP_INDEX_URL": "https://evil.invalid/simple", "PIP_EXTRA_INDEX_URL": "https://evil.invalid/x",
                  "PIP_REQUIRE_VIRTUALENV": "0", "PIP_CONFIG_FILE": "/evil/pip.conf"}
        r = FakeBash.run(self.script, {"RUNNER_TEMP": str(self.tmp), **poison}, self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = (self.tmp / "calls.txt").read_text().splitlines()
        installs = [c for c in calls if c.startswith("ARGV: -m pip install")]
        self.assertEqual(len(installs), 1, calls)
        for flag in ("--require-hashes", "--only-binary=:all:", "--no-deps", "--no-cache-dir",
                     "--index-url https://pypi.org/simple", "-r " + str(self.tmp / "work/backend/requirements-typecheck-linux-x86_64-cp313.lock.txt")):
            self.assertIn(flag, installs[0])
        env_calls = [c for c in calls if c.startswith("ENV: ")]
        for key in ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_REQUIRE_VIRTUALENV"):
            self.assertFalse([c for c in env_calls if c.startswith(f"ENV: {key}=")], f"{key} survived")
        self.assertTrue([c for c in env_calls if c == "ENV: PIP_CONFIG_FILE=/dev/null"])
        self.assertFalse([c for c in env_calls if "evil" in c])


if __name__ == "__main__":
    unittest.main()
