#!/usr/bin/env python3
"""Veyro v2 owner-operable control wrapper (Python stdlib only; no network, no subprocess, no shell).

Installed root-owned beside runner.py and normally started through the fixed launcher `veyro-ctl` (sudo, runas the worker
account). The launcher is a convenience, not a gate: any process running as the worker can run this file or `runner.py enqueue`
directly, so a task's `source: owner` says "queued through the owner-facing path", never that the owner authenticated.
Every path, account and pin is a constant below: the caller chooses a verb and, for `enqueue`, one JSON task spec on stdin,
nothing else. Verbs: status, pause, resume, stop, cancel ID, enqueue. `run`, `dashboard`, `acknowledge-escaped` and anything
unknown are refused. It adds no queue logic: it calls runner.enqueue / set_control / cancel_task / snapshot, so tasks keep
source "owner" (see above). Automatic handoff stays disabled (runner.HANDOFF_ENABLED); this wrapper is interactive operation only.
"""
import json
import os
import pwd
import stat
import sys
from pathlib import Path

WORKER_ACCOUNT = "veyroworker"
INSTALL_DIR = Path("/Library/Application Support/Veyro/release-v2-ctl1/runner")
REPO = Path("/Users/Shared/veyroworker/veyro")
HOME = Path("/Users/Shared/veyroworker/mission-runner")
OWNER_HOME = Path("/Users/ahmadmabrouk")
CLAUDE_BIN = Path("/Library/Application Support/Veyro/release-v2-ctl1/bin/claude")
CLAUDE_SHA256 = "75e3016e9d2570767b08e43a7467d4817a4f149232c169ca295f2c95fef21433"
CLAUDE_VERSION = "2.1.286"
LEGACY_STATE = Path("/Library/Application Support/Veyro/legacy-2026-10-29/state.json")
LEGACY_EVIDENCE = Path("/Library/Application Support/Veyro/legacy-2026-10-29/evidence")
CUTOVER_PROOF = Path("/Library/Application Support/Veyro/legacy-2026-10-29/cutover.json")  # root-owned, outside worker HOME
ROOT_UID = 0  # the only uid trusted to own the install and the cutover proof; tests patch it for disposable fixtures

VERBS = ("status", "pause", "resume", "stop", "cancel", "enqueue")
ENQUEUE_KEYS = frozenset({"id", "module", "role", "title", "prompt", "allowed_paths", "verify_cmd", "review_of", "depends_on",
                          "max_attempts", "remediates"})
SPEC_MAX = 256 * 1024
OUT_MAX = 256 * 1024
STR_MAX, LIST_MAX, TASKS_MAX, EVENTS_MAX, ERR_MAX = 500, 100, 200, 20, 300
ENV_DENY_PREFIXES = ("PYTHON", "VEYRO_", "DYLD_", "LD_", "GIT_", "CLAUDE", "ANTHROPIC", "OPENCLAW")
EXIT_USAGE, EXIT_BOUNDARY = 2, 5  # same codes as runner.py (EXIT_BOUNDARY)


class Refused(Exception):
    """The request or the host boundary was refused; the message is safe to print."""


def parse_argv(argv):
    """(verb, arg) for an allowed verb with exactly its arguments, else Refused. Pure: no side effects, nothing echoed back."""
    if not argv or argv[0] not in VERBS:
        raise Refused("unknown or not-permitted verb; allowed: " + ", ".join(VERBS))
    verb, rest = argv[0], argv[1:]
    if verb == "cancel":
        if len(rest) != 1:
            raise Refused("usage: cancel ID")
        return verb, rest[0]
    if rest:
        raise Refused(f"{verb} takes no arguments")
    return verb, None


def env_problem(environ=None):
    environ = os.environ if environ is None else environ
    bad = sorted(k for k in environ if k.upper().startswith(ENV_DENY_PREFIXES))
    return f"environment variable(s) not accepted: {', '.join(b[:40] for b in bad[:5])}" if bad else None


def worker_problem():
    uid, euid = os.getuid(), os.geteuid()
    if 0 in (uid, euid) or uid != euid:
        return "must run as the worker account with equal real/effective uid (not root)"
    try:
        want = pwd.getpwnam(WORKER_ACCOUNT).pw_uid
    except KeyError:
        return f"account {WORKER_ACCOUNT!r} does not exist"
    if euid != want:
        return f"not running as {WORKER_ACCOUNT!r}"
    return None


def _root_file_problem(st):
    """Why an lstat/fstat result is not a root-owned regular file that neither group nor other can write, else None."""
    if not stat.S_ISREG(st.st_mode):
        return "not a regular file"
    if st.st_uid != ROOT_UID or st.st_mode & 0o022:
        return "not root-owned and unwritable by group/other"
    return None


def _root_dir_problem(path):
    """Why `path` is not a root-owned directory that group/other cannot write, else None. A root-owned sticky directory (/tmp)
    is accepted as an ancestor, as in runner.chain_problem; the production install path contains none."""
    st = os.stat(path)
    if not stat.S_ISDIR(st.st_mode):
        return "not a directory"
    if st.st_uid not in (0, ROOT_UID) or (st.st_mode & 0o022 and not (st.st_mode & stat.S_ISVTX and st.st_uid == 0)):
        return "not root-owned and unwritable by group/other"
    return None


def install_tree_problem(install=None):
    """Checked BEFORE anything is imported, so unverified bytes never load: the install directory and every ancestor are
    root-owned directories group/other cannot write, and every entry in the install directory is a root-owned regular file
    not writable by group/other (a subdirectory would hold a planted __pycache__/*.pyc that is read despite -B), including the
    two modules this wrapper imports."""
    install = INSTALL_DIR if install is None else install
    try:
        for d in (install, *install.parents):
            why = _root_dir_problem(d)
            if why:
                return f"RUNNER_INSTALL: {d.name[:60] or '/'!r} is {why}"
        for entry in install.iterdir():
            why = _root_file_problem(os.lstat(entry))
            if why:
                return f"RUNNER_INSTALL: {entry.name[:60]!r} in the install directory is {why}"
        for name in ("runner.py", "acceptance_receipt.py"):
            why = _root_file_problem(os.lstat(install / name))
            if why:
                return f"RUNNER_INSTALL: {name} is {why}"
    except OSError as e:
        return f"RUNNER_INSTALL: cannot inspect the install ({type(e).__name__})"
    return None


def load_runner():
    """The runner module from INSTALL_DIR, only when this file is exactly INSTALL_DIR/control.py and the install tree passes
    install_tree_problem (-I drops the script dir from sys.path, so the directory is added explicitly, after the standard library
    so nothing in it can shadow a stdlib module, and only after both checks)."""
    if Path(__file__).resolve() != INSTALL_DIR / "control.py":
        raise Refused("control.py is not running from the fixed install directory")
    why = install_tree_problem()
    if why:
        raise Refused(why)
    if str(INSTALL_DIR) not in sys.path:
        sys.path.append(str(INSTALL_DIR))
    import runner
    if Path(runner.__file__).resolve() != INSTALL_DIR / "runner.py":
        raise Refused("runner module was not loaded from the fixed install directory")
    return runner


def _chain_problem(path):
    """Why `path` or any parent is not a root-owned directory unwritable by group/other (a swap point), else None."""
    for d in (path, *path.parents):
        why = _root_dir_problem(d)
        if why:
            return f"{d.name[:60] or '/'!r} is {why}"
    return None


def read_pin(max_bytes):
    """legacy_sha256 from the cutover proof, or ValueError if it is missing, unreadable, not a root-owned regular file that
    group/other cannot write, or malformed."""
    try:
        why = _chain_problem(CUTOVER_PROOF.parent)
        if why:
            raise ValueError(f"cutover proof has an unsafe parent chain ({why})")
        fd = os.open(CUTOVER_PROOF, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        raise ValueError(f"cutover proof cannot be opened ({type(e).__name__})")
    try:
        why = _root_file_problem(os.fstat(fd))
        if why:
            raise ValueError(f"cutover proof is {why}")
        raw = os.read(fd, max_bytes + 1)
    except OSError as e:
        raise ValueError(f"cutover proof unreadable ({type(e).__name__})")
    finally:
        os.close(fd)
    if len(raw) > max_bytes:
        raise ValueError("cutover proof is too large")
    try:
        proof = json.loads(raw)
    except ValueError:
        raise ValueError("cutover proof is not valid JSON")
    pin = proof.get("legacy_sha256") if isinstance(proof, dict) else None
    if not (isinstance(proof, dict) and proof.get("schema") == 1 and isinstance(pin, str) and len(pin) == 64
            and all(c in "0123456789abcdef" for c in pin)):
        raise ValueError("cutover proof is malformed")
    return pin


def build_config(runner, strict):
    """Config from constants only. Every Config field with an environment fallback is passed explicitly. With strict (enqueue)
    a missing or malformed cutover proof is fatal; otherwise the pin is just absent and status reports the legacy error."""
    try:
        pin = read_pin(runner.CUTOVER_MAX)
    except ValueError:
        if strict:
            raise
        pin = None
    return runner.Config(home=HOME, repo=REPO, claude_bin=str(CLAUDE_BIN), claude_sha256=CLAUDE_SHA256,
                         claude_version=CLAUDE_VERSION, owner_home=OWNER_HOME, legacy_state=LEGACY_STATE, legacy_sha256=pin,
                         cutover_proof=CUTOVER_PROOF, legacy_evidence=LEGACY_EVIDENCE,
                         models={"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"})


def guard(verb):
    """(runner, cfg) once the environment, worker uid and install boundary all hold, else Refused."""
    why = env_problem() or worker_problem()
    if why:
        raise Refused(f"BOUNDARY: {why}")
    runner = load_runner()
    cfg = build_config(runner, strict=False)
    why = runner.runner_install_problem(cfg, INSTALL_DIR)
    if why:
        raise Refused(why)
    why = runner.worker_boundary_problem(cfg)
    if why:
        raise Refused(why)
    if verb == "enqueue":
        for what, path in (("cutover proof", CUTOVER_PROOF), ("legacy state", LEGACY_STATE), ("legacy evidence", LEGACY_EVIDENCE)):
            try:
                why = _chain_problem(path.parent)
            except OSError as e:
                why = f"cannot be inspected ({type(e).__name__})"
            if why:
                raise Refused(f"BOUNDARY: the {what} parent chain is unsafe: {why}")
        cfg = build_config(runner, strict=True)
        why = runner.host_problem(cfg)
        if why:
            raise Refused(why)
    return runner, cfg


def parse_spec(raw, runner):
    """The enqueue task spec from stdin bytes: bounded, UTF-8, no duplicate keys or NaN, an object, allowlisted fields only."""
    if len(raw) > SPEC_MAX:
        raise ValueError(f"spec exceeds {SPEC_MAX} bytes")
    try:
        spec = runner.strict_json(raw.decode("utf-8"))
    except (UnicodeDecodeError, RecursionError):
        raise ValueError("spec is not valid UTF-8 JSON")
    except ValueError as e:
        raise ValueError(f"spec is not valid JSON: {e}")
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")
    extra = sorted(set(spec) - ENQUEUE_KEYS)
    if extra:
        raise ValueError(f"fields not accepted: {', '.join(k[:40] for k in extra[:5])}")
    return spec


def clip(v, depth=0):
    if isinstance(v, str):
        return v if len(v) <= STR_MAX else v[:STR_MAX] + "...[clipped]"
    if isinstance(v, (bool, int, float)) or v is None:
        return v
    if depth > 4:
        return "[clipped]"
    if isinstance(v, (list, tuple)):
        return [clip(x, depth + 1) for x in v[:LIST_MAX]]
    if isinstance(v, dict):
        return {str(k)[:STR_MAX]: clip(x, depth + 1) for k, x in list(v.items())[:LIST_MAX]}
    return str(v)[:STR_MAX]


def status_view(runner, cfg):
    """Bounded snapshot: no prompts exist in it; events are reduced to kind/time/task id; every field is clipped, as event
    contents are untrusted."""
    s = runner.snapshot(cfg)
    events = [{k: clip(e.get(k)) for k in ("ts", "kind", "task_id")} for e in s.pop("events", [])[:EVENTS_MAX] if isinstance(e, dict)]
    legacy = s.pop("legacy_tasks")
    tasks = s.pop("tasks")
    view = clip(s) | {"events": events, "legacy_task_count": len(legacy), "task_count": len(tasks)}
    keep = TASKS_MAX
    while True:  # newest tasks first-in-budget; halve until the whole document fits
        view["tasks"] = clip(tasks[-keep:]) if keep else []
        out = json.dumps(view, indent=1, sort_keys=True)
        if len(out) <= OUT_MAX:
            return out
        if not keep:  # the non-task fields (usage, runner, handoff) alone are too big: say so instead of exceeding the bound
            return json.dumps({"error": "status too large to display", "task_count": len(tasks)})
        keep //= 2


def execute(runner, cfg, verb, arg, stdin):
    """Run one verb and return the text to print. ValueError/OSError/StateCorrupt are the caller's to report."""
    if verb == "status":
        return status_view(runner, cfg)
    if verb in runner.CONTROLS:
        runner.set_control(cfg, verb)
        return json.dumps({"command": verb, "control": runner.CONTROLS[verb]})
    if verb == "cancel":
        if not runner.ID_RE.fullmatch(arg):
            raise ValueError("id must match [A-Za-z0-9._-]{1,64}")
        return json.dumps({"task_id": arg, "result": runner.cancel_task(cfg, arg)})
    return json.dumps({"queued": runner.enqueue(cfg, parse_spec(stdin.read(SPEC_MAX + 1), runner))})


def main(argv=None, stdin=None):
    argv = sys.argv[1:] if argv is None else argv
    stdin = sys.stdin.buffer if stdin is None else stdin
    try:
        verb, arg = parse_argv(argv)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return EXIT_USAGE
    try:
        runner, cfg = guard(verb)
    except Refused as e:
        print(f"refused: {str(e)[:ERR_MAX]}", file=sys.stderr)
        return EXIT_BOUNDARY
    except ValueError as e:
        print(f"refused: {str(e)[:ERR_MAX]}", file=sys.stderr)
        return EXIT_USAGE
    try:
        print(execute(runner, cfg, verb, arg, stdin))
    except (ValueError, OSError, runner.StateCorrupt) as e:
        print(f"{verb} refused: {str(e)[:ERR_MAX]}", file=sys.stderr)
        return EXIT_USAGE
    return 0


if __name__ == "__main__":
    sys.exit(main())
