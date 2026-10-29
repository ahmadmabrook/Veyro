#!/usr/bin/env python3
"""Veyro mission runner v2: a small, durable, local task executor (Python stdlib only).

One runner process owns a durable queue and runs one agent task at a time. Sonnet implements/tests, Opus reviews
independently. Everything is local: no GitHub, CI, network or operator receipt is needed to start, dispatch or
restart. Completed tasks are never module acceptance; acceptance stays an owner/governance record.

State (all under the home dir):
  v2/state.json    queue + control + usage     v2/events.jsonl  append-only event log
  v2/state.lock    short transaction lock      v2/runs/<id>-<n>/ per-attempt settings, output, verify log
  locks/runner.lock (sole v2 runner) and locks/repo-writer-*.lock (one repo writer, held across the agent child and
  inherited by it, so a crashed runner can never overlap a surviving child; the child's whole process group is killed
  and reaped before the lock is released, and again on restart).
The legacy v1 history is a MANDATORY, explicit, byte-for-byte copy pinned by sha256 (legacy_bytes); it is only read. v1 and v2
run under different accounts with different homes, so their locks are NOT shared: nothing here claims v1 and v2 exclude each
other by lock. Exclusion is an explicit cutover proof (cutover_problem) plus a process scan, and fails closed.

Host boundary (host_problem), checked at startup and before every dispatch, fails closed unless the runner runs as the dedicated
non-admin worker account, the owner home is untraversable, the runner's own install and the agent CLI are root-owned,
unwritable and outside every agent-writable tree, the CLI matches a pinned version and sha256, and the legacy/cutover
proofs hold. Agent-spawned processes that escape the process group (setsid, double fork) are detected after each turn and
halt dispatch; they are not claimed to be prevented. Clearance rescans the original baseline (new_worker_procs), excluding
only a kernel-verified (never argv), exactly pinned root-owned macOS system daemon (escape_allowlisted, DAEMON_EXE_PATHS)
- never an arbitrary worker-owned process, and never a `dashboard` restart trusted by argv, which is not allowlisted at
all. A pinned daemon's identity is re-verified fresh, by pid, on every rescan: being inside an earlier baseline is never
by itself a reason to stop checking what a pid's kernel-reported executable now is. acknowledge_escaped never force-clears
a real stray; it only asks the live runner to redo that same rescan on its next tick.

Dispatch for every role, including review, is also refused while the worktree holds any dirty or untracked project-
instruction path - a CLAUDE.md/CLAUDE.local.md or anything under a `.claude/` directory, matched case-insensitively
because the supported volumes are case-insensitive - found by walking the filesystem directly (instruction_contamination),
not by trusting `git status`, which hides gitignored paths by default. in_scope applies the same casefolded match, plus
a `.claude` path-component check, so a write task can never plant or edit either kind of path under any allowed_paths.

Agents run through the standalone `claude` CLI (Claude OAuth login, explicit Sonnet/Opus model ids) in print mode with a
trusted per-turn `--settings` file: only the Bash tool exists, and Claude Code's native sandbox confines it (see
turn_settings). The CLI process itself stays outside that sandbox so it can authenticate; it must be a protected install
outside the checkout and runner home (check_cli_install). acpx is no longer used.

Confinement: the agent's Bash is confined by the CLI's native sandbox; verifier and planner-CLI processes run under macOS
Seatbelt (confine_verifier / confine_planner). If any is unavailable or unverifiable, dispatch is refused (tasks stay
PENDING); enqueue, status, cancel and the heartbeat keep working.
"""
import argparse
import contextlib
import ctypes
import datetime
import fcntl
import fnmatch
import grp
import hashlib
import json
import os
import pwd
import re
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections import namedtuple
from pathlib import Path, PurePosixPath

if str(Path(__file__).resolve().parent) not in sys.path:  # also when loaded by file path (governance_check)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import acceptance_receipt  # protected with the rest of RUNNER_DIR by runner_install_problem

SCHEMA = 2
REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path(__file__).resolve().parent / "module_catalog.json"
STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")
WRITE_ROLES = ("implement", "test")  # Sonnet; may change files inside allowed_paths
REVIEW_ROLES = ("review",)  # Opus; read-only
ROLES = WRITE_ROLES + REVIEW_ROLES
FAMILIES = ("opus", "sonnet", "haiku")
TOKEN_FIELDS = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
OUTCOME_RE = re.compile(r"^OUTCOME:\s*(APPROVED|CHANGES_REQUESTED|BLOCKED)\s*$")
AUTH_RE = re.compile(r"(?i)not logged in|log ?in|auth|credential|unauthori|forbidden|\b40[13]\b")  # retrying cannot fix these
CHILD_ENV_KEEP = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL", "TERM")
CONTROLS = {"pause": "PAUSE", "resume": "RUN", "stop": "STOP"}
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MOD_RE = re.compile(r"^MOD-\d{3}$")
PROMPT_MAX = 200_000
ACP_LINE_MAX, ACP_TEXT_MAX, ACP_ERR_TAIL = 1_000_000, 200_000, 2_000  # the runner never buffers more of an agent's output
VERIFY_OUT_MAX = 200_000  # bound on the verifier output the runner keeps in memory while draining its pipe
HEARTBEAT_S = 3.0
MAX_SAME_WORK_FAILS = 3  # identical work may fail at most this often, whatever ids it was submitted under
EXIT_LOCKED, EXIT_CORRUPT, EXIT_BOUNDARY = 3, 4, 5
WORKER_ACCOUNT = "veyroworker"  # the dedicated non-admin account the runner and every agent child must run as
ADMIN_GROUPS = ("admin", "wheel")
TRUSTED_UIDS = (0,)  # only root may own the protected runner and CLI installs (a worker-owned install is agent-reachable)
HASH_MAX = 64 * 1024 * 1024  # largest repo file content-hashed; bigger files are identified by size + ctime instead
CLI_HASH_MAX = 1024 * 1024 * 1024
LEGACY_MAX = 64 * 1024 * 1024
CUTOVER_MAX = 64 * 1024
LEGACY_EVIDENCE_MAX_ENTRIES = 5000
RUNNER_DIR = Path(__file__).resolve().parent
AGENT_TOOLS = ("Bash",)  # the only tool the agent CLI is launched with; anything else seen on the stream is a violation
CLI_FLAGS = ("--restricted", "--strict-mcp-config", "--tools", "--allowedTools", "--permission-mode", "--permission-prompts",
             "--no-session-persistence", "--settings", "--output-format", "--model", "--disable-slash-commands")
MAX_TURNS = 100  # the CLI has no turn cap flag: the runner counts assistant messages and kills the group past this

# OpenClaw owns choosing the next legal task; the runner only triggers one bounded read-only planning turn and
# validates/enqueues the answer through the normal path. The planner agent has no write path (proved from its config).
ORCH_AGENT = "veyro-continuation-planner"
ORCH_SESSION = "agent:veyro-continuation-planner:mission-continuation"
PLANNER_MODEL = "openai/gpt-6-sol"
PLANNER_TOOLS = frozenset({"read", "ls", "dir_list"})
PLANNER_RUNTIME = "openclaw"
HANDOFF_KINDS = ("TASK", "BLOCKED", "WAITING_FOR_OWNER", "NO_LEGAL_WORK")
HANDOFF_TASK_KEYS = {"id", "module", "role", "title", "prompt", "allowed_paths", "verify_cmd", "review_of", "depends_on",
                     "max_attempts", "remediates"}
HANDOFF_OUT_MAX, HANDOFF_TEXT_MAX, HANDOFF_TRIES = 1_000_000, 64 * 1024, 3
# Proposed work may never touch the runner, CI, governance or module acceptance records.
PROPOSAL_PROTECTED = ("tools/mission_runner/", ".github/", ".githooks/", ".claude/", "governance/", "baseline/",
                      "knowledge/03-Modules/", "PROJECT_INDEX.md", "AGENTS.md", "CLAUDE.md", ".gitignore", ".gitattributes")
VERIFY_TARGET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,6}$")
ORCH_ENV_KEEP = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "TERM")
# Automatic handoff stays OFF in production: the planner would run inside the owner's Gateway under the owner's identity and
# policy, which cannot be proven from the worker account, and its proposals would flow from owner space into the worker queue.
# The implementation below is inert (every entry point checks HANDOFF_ENABLED); only a reviewed change that introduces a
# distinct, scoped OpenClaw worker identity and control path may flip it. Tests patch it explicitly to exercise the mechanics.
#
# HARD WARNING before ever flipping this: planner_policy_blocker below only proves that ~/.openclaw/openclaw.json, a
# WORKER-local, worker-WRITABLE file, currently describes a read-only planner entry. A worker-local config file is never
# independent proof of anything - the same worker identity that would run the planner could also rewrite that file. A
# clean planner_policy_blocker result is NOT the "distinct, scoped OpenClaw worker identity and control path" this
# comment requires; that is a separate, owner-side authority record this runner cannot derive from worker-local state.
HANDOFF_ENABLED = False
HANDOFF_BLOCKER = ("HANDOFF_DISABLED_PENDING_SCOPED_WORKER_IDENTITY: automatic OpenClaw handoff is off until a distinct scoped "
                   "worker identity and control path has been reviewed and proven")
HANDOFF_MAX_CONSEC_FAILS = 3  # consecutive FAILED handoff-sourced tasks per module before the runner forces WAITING_FOR_OWNER
# A conditional "ACCEPTED ... CONDITIONAL ON ... CI / RECEIPT" header is not acceptance for this runner: it cannot observe CI or
# verify a receipt, and the receipt prerequisite is not retired by any authority record. Flip only with such a record.
CONDITIONAL_SATISFIES_PREREQ = False


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def default_home():
    if os.environ.get("VEYRO_RUNNER_HOME"):
        return Path(os.environ["VEYRO_RUNNER_HOME"])
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Veyro/mission-runner"
    return Path.home() / ".local/state/veyro/mission-runner"


def parse_index(text):
    """(name, sha256) rows of PROJECT_INDEX.md; used by the governance checker."""
    return re.findall(r"^\|\s*`([^`]+)`\s*\|\s*`([0-9a-f]{64})`\s*\|\s*$", text, re.M)


def family_of(model):
    return next((f for f in FAMILIES if f in str(model).lower()), "unknown")


class Config:
    def __init__(self, home=None, repo=REPO, claude_bin=None, timeout=1800.0, tick=1.0, backoff_base=5.0,
                 backoff_cap=300.0, max_attempts=3, verify_timeout=600.0, models=None, module_order=True,
                 orchestrator_bin=None, handoff_timeout=600.0, handoff_cooldown=120.0, openclaw_config=None,
                 handoff_poll=5.0, sandbox="auto", max_turns=MAX_TURNS, owner_home=None, worker_account=WORKER_ACCOUNT,
                 claude_sha256=None, claude_version=None, legacy_state=None, legacy_sha256=None, cutover_proof=None,
                 legacy_evidence=None):
        self.home, self.repo = Path(home) if home else default_home(), Path(repo)
        # No PATH lookup, no default: the agent CLI must be named explicitly and pass check_cli_install before every dispatch.
        self.claude_bin = claude_bin or os.environ.get("VEYRO_CLAUDE_BIN") or None
        self.claude_sha256 = (claude_sha256 or os.environ.get("VEYRO_CLAUDE_SHA256") or "").lower() or None  # immutable pin
        self.claude_version = claude_version or os.environ.get("VEYRO_CLAUDE_VERSION") or None
        # Boundary inputs: the owner home that must be untraversable, and the mandatory pinned legacy v1 copy + cutover proof.
        oh = owner_home or os.environ.get("VEYRO_OWNER_HOME")
        self.owner_home = Path(oh) if oh else None
        self.worker_account = worker_account
        ls = legacy_state or os.environ.get("VEYRO_LEGACY_STATE")
        self.legacy_state = Path(ls) if ls else None
        self.legacy_sha256 = (legacy_sha256 or os.environ.get("VEYRO_LEGACY_SHA256") or "").lower() or None
        # The home default exists only so a config object is always complete: it is worker-writable, so read_cutover_proof refuses
        # it and Runner.run refuses to start without an explicit proof (cutover_proof_explicit).
        self.cutover_proof = Path(cutover_proof) if cutover_proof else Path(self.home) / "cutover.json"
        self.cutover_proof_explicit = bool(cutover_proof)
        le = legacy_evidence or os.environ.get("VEYRO_LEGACY_EVIDENCE")  # exact copy of v1 acceptances/ + runs/ (read-only)
        self.legacy_evidence = Path(le) if le else None
        self.max_turns, self._cli_seen = max_turns, None
        self.timeout, self.tick, self.verify_timeout = timeout, tick, verify_timeout
        self.backoff_base, self.backoff_cap, self.max_attempts = backoff_base, backoff_cap, max_attempts
        self.orchestrator_bin = orchestrator_bin or None  # None disables automatic OpenClaw handoff
        self.handoff_timeout, self.handoff_cooldown, self.openclaw_config = handoff_timeout, handoff_cooldown, openclaw_config
        self.handoff_poll = handoff_poll  # seconds between idle checks
        if sandbox not in ("auto", "off"):
            raise ValueError("sandbox must be 'auto' or 'off'")
        self.sandbox = sandbox  # 'off' exists for platform-less unit-test fixtures only; the CLI never sets it
        self.module_order = module_order  # write tasks wait for catalog dependencies to be recorded ACCEPTED
        self.models = {"sonnet": os.environ.get("VEYRO_MODEL_SONNET", "claude-sonnet-5-5"),
                       "opus": os.environ.get("VEYRO_MODEL_OPUS", "claude-opus-5-5"), **(models or {})}
        for family, alias in self.models.items():  # a mis-configured alias must never route a role to the wrong family
            if family not in ("sonnet", "opus") or family_of(alias) != family:
                raise ValueError(f"model alias {alias!r} is not a {family} model")


def required_family(role):
    return "sonnet" if role in WRITE_ROLES else "opus"


# ---------------------------------------------------------------- durable store
def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, data: bytes):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    fsync_dir(path.parent)


class StateCorrupt(Exception):
    pass


class Store:
    """v2 queue/state. Writers go through `txn()` (exclusive flock + atomic fsynced replace); readers never lock."""

    def __init__(self, home, create=True):
        self.dir = Path(home) / "v2"
        self.state_path, self.events_path = self.dir / "state.json", self.dir / "events.jsonl"
        if create:
            (self.dir / "runs").mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def empty():
        return {"schema": SCHEMA, "control": "RUN", "seq": 0, "tasks": {}, "usage": {}, "runner": None}

    def load(self):
        try:
            raw = self.state_path.read_text()
        except FileNotFoundError:
            return self.empty()
        try:
            st = json.loads(raw)
            if not (isinstance(st, dict) and st.get("schema") == SCHEMA and isinstance(st.get("tasks"), dict)):
                raise ValueError("unexpected state schema")
            return st
        except ValueError as e:  # fail closed: unreadable state is never overwritten
            raise StateCorrupt(f"{self.state_path}: {e}")

    def save(self, st):
        atomic_write(self.state_path, json.dumps(st, indent=1, sort_keys=True).encode())

    @contextlib.contextmanager
    def txn(self):
        fd = os.open(self.dir / "state.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            st = self.load()
            yield st
            self.save(st)
        finally:
            os.close(fd)

    def event(self, kind, **detail):
        line = json.dumps({"ts": now_iso(), "kind": kind, **detail}, sort_keys=True)
        fd = os.open(self.events_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def tail_events(self, n=200):
        try:
            with open(self.events_path, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 262144))
                lines = f.read().decode(errors="replace").splitlines()[-n:]
        except FileNotFoundError:
            return []
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass  # partial first line of the tail window
        return out[::-1]


class FileLock:
    """Advisory flock; closing the fd (not LOCK_UN) releases it, so an inheriting child keeps it after we die."""

    def __init__(self, path):
        self.path, self.fd, self.meta = Path(path), None, {}

    def acquire(self, owner):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self.fd, self.meta = fd, {**owner, "since": now_iso()}
        self._write()
        return True

    def _write(self):
        os.ftruncate(self.fd, 0)
        os.pwrite(self.fd, json.dumps(self.meta).encode(), 0)

    def update(self, extra):
        self.meta.update(extra)
        self._write()

    def release(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def owner(self):
        try:
            return json.loads(self.path.read_text() or "null")
        except (OSError, ValueError):
            return None

    @staticmethod
    def probe(path):
        """'held' / 'free' / 'unknown' without creating the file or disturbing a holder."""
        try:
            fd = os.open(path, os.O_RDONLY)
        except FileNotFoundError:
            return "free"
        except OSError:
            return "unknown"
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return "free"
        except OSError:
            return "held"
        finally:
            os.close(fd)


def runner_lock_path(home):
    # v1 and v2 live under different accounts and homes, so their locks are unrelated files: this lock excludes only a second
    # v2 runner. v1/v2 exclusion is the cutover proof (cutover_problem), never this lock.
    return Path(home) / "locks" / "runner.lock"


def writer_lock_path(home, repo):
    return Path(home) / "locks" / f"repo-writer-{hashlib.sha256(str(Path(repo).resolve()).encode()).hexdigest()[:12]}.lock"


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def child_alive(child):
    """The recorded pid must exist AND still carry the recorded start time (a reused pid is not our child)."""
    if not isinstance(child, dict) or not pid_alive(child.get("pid")):
        return False
    return bool(child.get("lstart")) and _lstart(child["pid"]) == child["lstart"]


def _lstart(pid):
    try:
        return subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=2, env={"PATH": "/bin:/usr/bin", "LC_ALL": "C"}).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _parse_lstart(text):
    """Epoch seconds of a `ps lstart` string, or None."""
    try:
        return time.mktime(time.strptime(" ".join(str(text).split()), "%a %b %d %H:%M:%S %Y"))
    except (ValueError, OverflowError):
        return None


# ------------------------------------------------------------------- git / repo evidence
def git_env():
    """Curated Git environment: no inherited GIT_* overrides, no system/global config."""
    env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    return env


def git_run(repo, *args, timeout=120):
    return subprocess.run(["git", "-c", "core.fsmonitor=", "-C", str(repo), *args], capture_output=True, check=True,
                          timeout=timeout, env=git_env(), stdin=subprocess.DEVNULL)


def file_hash(p):
    """Content identity of a worktree path, safe against hostile entries: never follows a symlink, never blocks on a FIFO or
    device, never reads more than HASH_MAX bytes. A file over the cap is identified by size + ctime (userspace cannot set
    ctime), so any later write still changes the identity."""
    p = Path(p)
    try:
        if p.is_symlink():
            return "link:" + os.readlink(p)
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as e:
        return f"unreadable:{e.errno}"
    try:
        st = os.fstat(fd)
        if stat.S_ISDIR(st.st_mode):
            return "dir"
        if not stat.S_ISREG(st.st_mode):
            return f"special:{stat.S_IFMT(st.st_mode):o}"  # FIFO, device, socket: identified, never read
        if st.st_size > HASH_MAX:
            return f"oversize:{st.st_size}:{st.st_ctime_ns}"
        h, left = hashlib.sha256(), HASH_MAX + 1
        while left:
            chunk = os.read(fd, min(1 << 20, left))
            if not chunk:
                return h.hexdigest()
            h.update(chunk)
            left -= len(chunk)
        return f"oversize:{st.st_size}:{st.st_ctime_ns}"  # grew past the cap while being read
    except OSError as e:
        return f"unreadable:{e.errno}"
    finally:
        os.close(fd)


def repo_state(repo):
    """HEAD + content hash of every path dirty vs HEAD. Diffing two states shows every change a child made."""
    repo = Path(repo)
    r = subprocess.run(["git", "-c", "core.fsmonitor=", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD"],
                       capture_output=True, text=True, env=git_env(), stdin=subprocess.DEVNULL)
    out = git_run(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames").stdout
    files = {}
    for e in out.split(b"\0"):
        if len(e) > 3:
            path = e[3:].decode(errors="surrogateescape")
            files[path] = file_hash(repo / path)
    return {"head": r.stdout.strip() or None, "files": files}


def diff_state(before, after):
    return sorted(p for p in set(before["files"]) | set(after["files"])
                  if before["files"].get(p, "<clean>") != after["files"].get(p, "<clean>"))


def in_scope(path, allowed):
    """Never in scope for a project-instruction filename (CLAUDE.md, CLAUDE.local.md, matched case-insensitively - the
    supported volumes are case-insensitive, so `claude.md` and `CLAUDE.MD` name the same file) at any depth, nor for any
    path with a `.claude` component under any casing, no matter what allowed_paths grants: a task that plants or edits
    one - new or pre-existing - is a SCOPE_VIOLATION, not a COMPLETED task, because a future agent session (implementer,
    reviewer or planner) may auto-load it as trusted instructions."""
    parts = PurePosixPath(path).parts
    if parts and parts[-1].casefold() in INSTRUCTION_BASENAMES_CF:
        return False
    if any(part.casefold() == ".claude" for part in parts):
        return False
    return any(path.startswith(a) if a.endswith("/") else (path == a or fnmatch.fnmatchcase(path, a)) for a in allowed)


def _walk_fail_closed(err):
    """os.walk's onerror hook for instruction_contamination: re-raise instead of letting os.walk silently skip an
    unreadable directory. os.walk has no error handler by default, so without this an unreadable directory - one a
    planting task could leave behind deliberately - would simply be left out of the scan rather than failing closed."""
    raise err


def instruction_contamination(repo):
    """Every CLAUDE.md/CLAUDE.local.md on disk (matched case-insensitively - the supported volumes are
    case-insensitive, so a planted `claude.md` resolves to the same file a CLI would load as `CLAUDE.md`), and every
    on-disk path under a `.claude/` directory of any casing, that is not byte-identical to what HEAD has committed at
    that exact path - walked directly off the filesystem rather than taken from `git status`, which hides gitignored
    paths by default. A planting task already fails in_scope, but the file itself stays in the worktree, and a
    .gitignore'd copy would never show up as 'dirty' to unresolved_dirt at all. Dispatch for EVERY role, write and
    review alike, must refuse while any of these exist: a later agent session (implementer, reviewer or planner) may
    auto-load one as trusted project instructions. An unreadable directory fails this closed (_walk_fail_closed)
    rather than being silently skipped from the scan."""
    repo = Path(repo)
    bad = []
    try:
        for dirpath, dirnames, filenames in os.walk(repo, topdown=True, followlinks=False, onerror=_walk_fail_closed):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            rel_dir = Path(dirpath).relative_to(repo)
            for d in dirnames:
                if d.casefold() == ".claude" and os.path.islink(Path(dirpath) / d):  # a symlinked .claude is untrusted
                    bad.append((rel_dir / d).as_posix() if str(rel_dir) != "." else d)
            under_claude = any(part.casefold() == ".claude" for part in rel_dir.parts)
            for name in filenames:
                if name.casefold() not in INSTRUCTION_BASENAMES_CF and not under_claude:
                    continue
                rel = (rel_dir / name).as_posix() if str(rel_dir) != "." else name
                if file_hash(Path(dirpath) / name) != head_content_hash(repo, rel):
                    bad.append(rel)
    except OSError:
        return ["<worktree unreadable>"]
    return sorted(set(bad))


# ------------------------------------------------------------------ catalog / module order
def load_catalog(repo=None):
    """Module order from the configured checkout's committed HEAD, never an install copy or dirty worktree."""
    try:
        source = Path(repo or REPO)
        path = "tools/mission_runner/module_catalog.json"
        sha = head_files(source, path).get(path)
        value = json.loads(head_blob(source, sha) or "") if sha else None
        return value if isinstance(value, list) else []
    except (OSError, ValueError, TypeError):
        return []


def head_files(repo, prefix):
    """{path: blob sha} of regular files under `prefix` in the COMMITTED HEAD tree (symlinks, submodules excluded).
    Never the working tree: an uncommitted edit, e.g. left behind by a failed write, is not a recorded decision."""
    try:
        out = git_run(repo, "ls-tree", "-r", "-z", "HEAD", "--", prefix, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    files = {}
    for row in out.split(b"\0"):
        meta, _, path = row.partition(b"\t")
        parts = meta.split()
        if len(parts) == 3 and parts[0] in (b"100644", b"100755") and parts[1] == b"blob":
            files[path.decode(errors="surrogateescape")] = parts[2].decode()
    return files


def head_blob(repo, sha, limit=200_000):
    try:
        return git_run(repo, "cat-file", "blob", sha, timeout=20).stdout[:limit].decode(errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None


def head_content_hash(repo, path):
    """sha256 of the exact bytes committed at `path` in HEAD - directly comparable to file_hash() of a worktree path,
    with no truncation or text decoding. None when `path` is not a regular file at HEAD."""
    sha = head_files(repo, path).get(path)
    if not sha:
        return None
    try:
        return hashlib.sha256(git_run(repo, "cat-file", "blob", sha, timeout=20).stdout).hexdigest()
    except (OSError, subprocess.SubprocessError):
        return "unreadable:head"


def module_record_path(module):
    return f"knowledge/03-Modules/{module}/{module}.md"


def module_approval_path(module):
    return f"knowledge/03-Modules/{module}/APPROVAL.md"


def module_record_state(repo, module):
    """'accepted' | 'conditional' | 'not-accepted' from the module's own record header as COMMITTED at HEAD. 'conditional' is an
    ACCEPTED header that is conditional on exact-SHA CI or a receipt: this runner observes neither, so it is never plain
    acceptance (it must neither unlock dependents nor hide a failed-CI forward repair). The runner never grants any of these.

    The bold `**Status: ...**` span is only the lead sentence; conditional wording (e.g. `*Conditional:* ...`) routinely sits
    in the rest of the same paragraph, not inside the bold span. Classification reads the whole paragraph, and also fails
    closed (conditional) when the module's own APPROVAL.md certificate still reads PENDING, so a certificate that has not
    caught up with the header text can never silently unlock a dependent."""
    sha = head_files(repo, module_record_path(module)).get(module_record_path(module))
    head = (head_blob(repo, sha, 4000) if sha else None) or ""
    m = re.search(r"\*\*Status:\s*([^*\n]+)\*\*", head)
    if not (head.startswith(f"# {module}") and m and re.match(r"ACCEPTED\b", m.group(1).strip(), re.I)):
        return "not-accepted"
    para_end = head.find("\n\n", m.end())
    paragraph = head[m.start():para_end if para_end != -1 else len(head)]
    if re.search(r"CONDITION", paragraph, re.I):
        return "conditional"
    cert_path = module_approval_path(module)
    cert_sha = head_files(repo, cert_path).get(cert_path)
    cert = (head_blob(repo, cert_sha, 2000) if cert_sha else None) or ""
    return "conditional" if re.search(r"PENDING", cert, re.I) else "accepted"


def module_record_accepted(repo, module):
    """Unconditional acceptance only (see module_record_state)."""
    return module_record_state(repo, module) == "accepted"


def prereq_problem(repo, module, cfg=None):
    """Why `module` does not satisfy a dependent's prerequisite, or None. A conditional header satisfies it only through a
    preserved v1 receipt that verifies right now (receipt_problem); it never becomes unconditional acceptance."""
    state = module_record_state(repo, module)
    if state == "accepted" or (state == "conditional" and CONDITIONAL_SATISFIES_PREREQ):
        return None
    if state == "conditional":
        why = receipt_problem(cfg, module) if cfg is not None else "no configuration to locate a preserved receipt"
        if why is None:
            return None
        return (f"module {module} is ACCEPTED only conditionally (exact-SHA CI / receipt) and no preserved acceptance "
                f"receipt verifies: {why}")
    return f"module {module} is not recorded ACCEPTED at HEAD"


def receipt_pins(cfg):
    """{module: sha256} of the receipts the operator pinned in the cutover proof, or ValueError. A missing, unreadable or
    malformed proof is 'no pins', never 'unpinned is fine'."""
    try:
        proof = json.loads(read_cutover_proof(cfg))
        pins = proof["acceptance_receipts"]
    except (ValueError, KeyError, TypeError):
        raise ValueError("the cutover proof is missing/unreadable/untrusted or has no acceptance_receipts object")
    if not (isinstance(pins, dict) and all(isinstance(k, str) and MOD_RE.match(k) and isinstance(v, str)
                                           and re.fullmatch(r"[0-9a-f]{64}", v) for k, v in pins.items())):
        raise ValueError("acceptance_receipts must map MOD-NNN to a sha256")
    return pins


def receipt_problem(cfg, module):
    """Why the preserved v1 receipt for `module` does not verify (offline), or None when it does."""
    try:
        pin = receipt_pins(cfg).get(module)
        if pin is None:
            return "no receipt for this module is pinned in the cutover proof"
        why = legacy_evidence_problem(cfg, check_pins=False)
        if why:
            return why
        acceptance_receipt.verify_receipt(cfg.legacy_evidence, cfg.repo, module, pin)
    except (ValueError, acceptance_receipt.ReceiptError) as e:
        return str(e)[:300]
    return None


def legacy_evidence_problem(cfg, check_pins=True):
    """The legacy v1 acceptance evidence is MANDATORY: an explicit absolute directory (the exact copy of the v1 home's
    `acceptances/` and the review outputs it names, same relative paths) outside every agent-writable tree, not group/other-writable. With `check_pins` each receipt
    pinned in the cutover proof must exist there byte-for-byte, so an incomplete or altered copy refuses start/dispatch."""
    ev = cfg.legacy_evidence
    if not ev or not Path(ev).is_absolute():
        return "LEGACY_EVIDENCE: --legacy-evidence must name the absolute, read-only copy of the v1 acceptances/ and runs/ trees"
    try:
        real = Path(ev).resolve()
        if Path(ev).is_symlink() or not real.is_dir():
            return "LEGACY_EVIDENCE: the evidence tree is missing, not a directory, or a symlink"
        if any(_inside(real, root) for root in agent_writable_roots(cfg)):
            return "LEGACY_EVIDENCE: the evidence tree lives inside an agent-writable tree (checkout, git dir or runner home)"
        if not (real / "acceptances").is_dir():
            return "LEGACY_EVIDENCE: the tree has no acceptances/ directory"
        seen = 0
        for top, dirs, files in os.walk(real, followlinks=False):  # review outputs sit wherever the receipts name them
            for name in (*dirs, *files, "."):
                q = Path(top) / name
                seen += 1
                if seen > LEGACY_EVIDENCE_MAX_ENTRIES:
                    return "LEGACY_EVIDENCE: the tree is larger than the bound"
                if q.is_symlink() or q.lstat().st_mode & 0o022:
                    return f"LEGACY_EVIDENCE: {q.name} is a symlink or group/other-writable"
    except OSError as e:
        return f"LEGACY_EVIDENCE: cannot inspect the evidence tree ({type(e).__name__})"
    if not check_pins:
        return None
    try:
        pins = receipt_pins(cfg)
    except ValueError:
        return None  # cutover_problem does not check acceptance_receipts; with no pins, receipt_problem/prereq_problem
        # itself fails closed (no pin -> no module can be shown as satisfying a conditional prerequisite)
    try:
        for module, pin in sorted(pins.items()):
            if acceptance_receipt.receipt_sha256(real, module) != pin:
                return f"LEGACY_EVIDENCE: {module} receipt is not the byte-for-byte pinned copy"
    except (ValueError, acceptance_receipt.ReceiptError) as e:
        return f"LEGACY_EVIDENCE: {str(e)[:200]}"
    return None


# ------------------------------------------------------------------ process groups
def group_alive(pgid):
    if not isinstance(pgid, int) or isinstance(pgid, bool) or pgid <= 1 or pgid == os.getpgrp():
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def kill_group(pgid, wait=10.0):
    """SIGKILL every member of the group (the agent child and anything it backgrounded) and wait until it is empty."""
    deadline = time.monotonic() + wait
    while group_alive(pgid):
        with contextlib.suppress(OSError):
            os.killpg(pgid, signal.SIGKILL)
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def reap_recorded(child):
    """Kill the recorded process group of a child left by a dead runner. True when no member remains."""
    child = child if isinstance(child, dict) else {}
    pgid = child.get("pgid") or child.get("pid")
    if pid_alive(child.get("pid")) and not child_alive(child):
        return True  # that pid now belongs to an unrelated process; never signal its group
    return kill_group(pgid) if group_alive(pgid) else True


# ------------------------------------------------------------------ validation / enqueue
def path_problem(p):
    if not isinstance(p, str) or not p or p != p.strip() or any(c in p for c in "\0\\\n\r,()"):
        return "empty, non-string or malformed path"
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return "absolute path"
    parts = p.rstrip("/").split("/")
    if any(x in ("", ".", "..") for x in parts) or parts[0] == ".git":
        return "path escapes the repository or targets .git"
    if re.search(r"[*?\[]", parts[0]):
        return "scope must start with a literal directory or file name"
    return None


def legacy_bytes(cfg):
    """The legacy v1 state.json bytes, or ValueError. It is MANDATORY and must be an exact copy: an explicit absolute path
    (never a default, never the runner home's own state.json) whose sha256 equals the operator's pin. Missing, unpinned,
    mismatching, symlinked, special, oversized or agent-writable-tree copies all fail closed, so an absent history can never
    silently mean 'no ids to protect'."""
    if not cfg.legacy_state or not cfg.legacy_sha256:
        raise ValueError("legacy v1 state is mandatory: set --legacy-state (explicit absolute path of the exact copy) and "
                         "--legacy-sha256 (its pinned digest)")
    if not re.fullmatch(r"[0-9a-f]{64}", cfg.legacy_sha256):
        raise ValueError("legacy v1 pin is not a sha256 hex digest")
    path = Path(cfg.legacy_state)
    if not path.is_absolute():
        raise ValueError("legacy v1 state path must be absolute")
    repo = Path(cfg.repo).resolve()
    if any(_inside(path.resolve(), root) for root in (repo, *git_dirs(repo))):
        raise ValueError("legacy v1 copy lives inside the agent-writable checkout")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        raise ValueError(f"legacy v1 copy cannot be opened ({type(e).__name__}); refusing to risk reusing an id")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > LEGACY_MAX:
            raise ValueError("legacy v1 copy is not a regular file within the size bound")
        data = b""
        while len(data) <= st.st_size:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            data += chunk
    except OSError as e:
        raise ValueError(f"legacy v1 copy unreadable ({type(e).__name__})")
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != cfg.legacy_sha256:
        raise ValueError("legacy v1 copy does not match its pinned sha256 (not a byte-for-byte copy)")
    return data


def legacy_state_tasks(cfg):
    """{id: record} of the pinned v1 history. ValueError unless the copy verifies and parses."""
    try:
        tasks = json.loads(legacy_bytes(cfg))["tasks"]
        if not isinstance(tasks, dict):
            raise TypeError("tasks is not an object")
    except (ValueError, KeyError, TypeError) as e:
        if isinstance(e, ValueError) and str(e).startswith("legacy v1"):
            raise
        raise ValueError(f"legacy v1 state exists but is unreadable ({type(e).__name__}); refusing to risk reusing an id")
    return tasks


def legacy_task_ids(cfg):
    """Every task id in the pinned read-only v1 state. Never empty-by-default: any problem is a ValueError."""
    tasks = legacy_state_tasks(cfg)
    return set(tasks) | {t["id"] for t in tasks.values() if isinstance(t, dict) and isinstance(t.get("id"), str)}


def legacy_problem(cfg):
    try:
        legacy_state_tasks(cfg)
    except ValueError as e:
        return str(e)
    return None


def work_fingerprint(task):
    """Identity of the WORK, independent of task id/title: module, role, scope, verifier, review subject and the
    normalized prompt. Used to refuse resubmitting failed work under a new id without corrective metadata."""
    norm = " ".join(re.sub(r"[^a-z0-9]+", " ", str(task.get("prompt", "")).lower()).split())
    key = [task.get("module"), task.get("role"), sorted(task.get("allowed_paths") or []), task.get("verify_cmd"),
           task.get("review_of"), norm]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()


def validate_task(spec, existing, legacy_ids=frozenset(), repo=None):
    """Normalized task from an enqueue spec, or ValueError. `existing` is the current tasks dict."""
    if not isinstance(spec, dict):
        raise ValueError("task must be an object")
    tid, module, role = spec.get("id"), spec.get("module"), spec.get("role")
    if not isinstance(tid, str) or not ID_RE.fullmatch(tid):
        raise ValueError("id must match [A-Za-z0-9._-]{1,64}")
    if tid in existing:
        raise ValueError(f"task {tid} already exists")
    if tid in legacy_ids:
        raise ValueError(f"task {tid} already exists in the preserved v1 history")
    if not isinstance(module, str) or not MOD_RE.match(module) or module not in {m.get("id") for m in load_catalog(repo)}:
        raise ValueError("module must be a catalog module id (MOD-nnn)")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    prompt = spec.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > PROMPT_MAX:
        raise ValueError("prompt must be a non-empty string under 200 KB")
    allowed = spec.get("allowed_paths") or []
    if not isinstance(allowed, list) or len(allowed) > 64:
        raise ValueError("allowed_paths must be a list of at most 64 paths")
    for p in allowed:
        bad = path_problem(p)
        if bad:
            raise ValueError(f"allowed_paths {p!r}: {bad}")
    if role in WRITE_ROLES and not allowed:
        raise ValueError(f"{role} tasks need at least one allowed path")
    if role in REVIEW_ROLES and allowed:
        raise ValueError("review tasks are read-only and take no allowed paths")
    verify = spec.get("verify_cmd")
    if verify is not None and not (isinstance(verify, list) and verify and len(verify) <= 64
                                   and all(isinstance(a, str) and a for a in verify)):
        raise ValueError("verify_cmd must be a non-empty argv list of strings")
    deps = spec.get("depends_on") or []
    if not (isinstance(deps, list) and all(isinstance(d, str) and d in existing for d in deps)) or tid in deps:
        raise ValueError("depends_on must list existing task ids")
    review_of = spec.get("review_of")
    if role in REVIEW_ROLES:
        target = existing.get(review_of) if isinstance(review_of, str) else None
        if not target or target["role"] not in WRITE_ROLES or target["module"] != module:
            raise ValueError("review_of must name an existing implement/test task of the same module")
        deps = list(dict.fromkeys([*deps, review_of]))
    elif review_of is not None:
        raise ValueError("review_of is only valid for review tasks")
    max_attempts = spec.get("max_attempts", 3)
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
        raise ValueError("max_attempts must be an integer 1..10")
    title = spec.get("title") or tid
    if not isinstance(title, str) or len(title) > 200:
        raise ValueError("title must be a string under 200 characters")
    remediates = spec.get("remediates")
    if remediates is not None:
        target = existing.get(remediates) if isinstance(remediates, str) else None
        if not target or target["status"] != "FAILED" or target["module"] != module:
            raise ValueError("remediates must name an existing FAILED task of the same module")
    task = {"id": tid, "module": module, "role": role, "title": title, "prompt": prompt, "allowed_paths": allowed,
            "verify_cmd": verify, "depends_on": deps, "review_of": review_of, "max_attempts": max_attempts,
            "remediates": remediates}
    fp = work_fingerprint(task)
    same = [i for i, t in existing.items() if t["status"] == "FAILED" and work_fingerprint(t) == fp]
    if same and (len(same) >= MAX_SAME_WORK_FAILS or remediates not in same):
        raise ValueError(f"the same work already FAILED as {', '.join(sorted(same))}; change the prompt, scope or verifier, "
                         f"or set remediates to the failed task it corrects (identical work fails at most "
                         f"{MAX_SAME_WORK_FAILS} times)")
    return task


def add_task(st, spec, cfg, source="owner"):
    """The one validated path into the queue (owner CLI and OpenClaw handoff alike); caller holds the txn."""
    task = validate_task(spec, st["tasks"], legacy_task_ids(cfg), repo=cfg.repo)
    st["seq"] += 1
    now = now_iso()
    st["tasks"][task["id"]] = {**task, "status": "PENDING", "seq": st["seq"], "attempts": 0, "created_at": now,
                               "updated_at": now, "started_at": None, "finished_at": None, "next_attempt_at": 0,
                               "stage": None, "reason": None, "last_error": None, "waiting": None, "child": None,
                               "route": None, "evidence": None, "result": None, "cancel_requested": False,
                               "source": source}
    return task


def enqueue(cfg, spec):
    store = Store(cfg.home)
    with store.txn() as st:
        task = add_task(st, spec, cfg)
    store.event("enqueue", task_id=task["id"], module=task["module"], role=task["role"])
    return task["id"]


def set_control(cfg, command):
    store = Store(cfg.home)
    with store.txn() as st:
        st["control"] = CONTROLS[command]
    store.event("command-applied", cmd=command)


def cancel_task(cfg, tid):
    """PENDING -> CANCELLED now; RUNNING -> the runner stops the child and records CANCELLED."""
    store = Store(cfg.home)
    with store.txn() as st:
        t = st["tasks"].get(tid)
        if not t:
            raise ValueError(f"unknown task {tid}")
        if t["status"] in TERMINAL:
            raise ValueError(f"task {tid} is already {t['status']}")
        if t["status"] == "PENDING":
            t.update(status="CANCELLED", reason="CANCELLED", finished_at=now_iso(), updated_at=now_iso())
            result = "cancelled"
        else:
            t.update(cancel_requested=True, updated_at=now_iso())
            result = "cancel requested"
    store.event("command-applied", cmd="cancel", task_id=tid)
    return result


def operator_identity():
    """Best-effort 'who ran this CLI command', for the acknowledgement audit trail only - never treated as
    authorization, just a label on the recorded evidence."""
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except (KeyError, OSError):
        return f"uid:{os.getuid()}"


def acknowledge_escaped(cfg):
    """N1: record an explicit, owner-run request to re-check the escaped-process gate. This NEVER clears `escaped`
    itself, and never touches the writer lock - only the live runner's own tick() may do either of those, from
    inside the same process that holds the lock, and only after a FRESH process-table rescan (the same
    allowlist-aware new_worker_procs the gate itself uses) comes back clean. A still-live, non-allowlisted stray
    keeps the halt in place no matter how many times this is run: it cannot silently clear a real escaped
    descendant. Evidence (who asked, when, what was recorded as escaped at the time) is logged regardless of
    whether the live runner later honors the request."""
    store = Store(cfg.home)
    try:
        st = store.load()
    except StateCorrupt as e:
        return f"refused: state unreadable ({e})"
    if not st.get("escaped"):
        return "nothing escaped is recorded; no acknowledgement needed"
    rows, who = st["escaped"], operator_identity()
    with store.txn() as cur:
        if cur.get("escaped"):
            cur["escape_ack_requested"] = {"at": now_iso(), "operator": who}
    store.event("escape-ack-requested", operator=who, pids=[r["pid"] for r in rows])
    return ("acknowledgement recorded; the live runner clears the gate on its own next tick only if a fresh process "
            "scan is then clean - it will not force-clear a still-present escaped process")


# ------------------------------------------------------------------- agent child
# The agent is the standalone `claude` CLI, one print-mode turn: prompt on stdin (from a file, so no pipe to deadlock on and
# nothing in argv), stream-json events on stdout. It is launched with --restricted (user/project/local settings ignored, so
# nothing the agent writes into the checkout can change policy), only the Bash tool, no MCP, no prompts, no session saved,
# and a per-turn --settings file written by the runner into its own home (turn_settings). The boundary is Claude Code's
# native sandbox on that Bash tool plus the runner's post-run checks (changed paths vs allowed_paths, HEAD movement, review
# read-only, verifier left the repo untouched). Prompts are not a boundary. The CLI process itself runs outside the sandbox
# (it must reach the login keychain); only its shell tool is confined, and the stream is checked to prove nothing else exists.
class CliUnavailable(Exception):
    """The agent CLI or its sandbox posture cannot be verified: dispatch is refused (fail closed)."""


def child_argv(claude_bin, alias, settings_path):
    return [str(claude_bin), "-p", "--output-format", "stream-json", "--verbose", "--model", alias,
            "--settings", str(settings_path), "--restricted", "--strict-mcp-config",
            "--tools", *AGENT_TOOLS, "--allowedTools", *AGENT_TOOLS, "--permission-mode", "dontAsk",
            "--permission-prompts", "none", "--no-session-persistence", "--disable-slash-commands"]


def _inside(path, root):
    return path == root or root in path.parents


def chain_problem(real):
    """Why `real` (and every parent) is not a protected, root-owned, unwritable path, or None. A root-owned sticky /tmp is fine.
    Callers exec the RESOLVED path, so a symlink at the configured name cannot be swapped in later."""
    for q in (Path(real), *Path(real).parents):
        st = q.stat()
        if st.st_uid not in TRUSTED_UIDS:
            return f"{q.name or '/'} is not owned by root"
        if st.st_mode & 0o022 and not (st.st_mode & stat.S_ISVTX and st.st_uid == 0):
            return f"{q.name or '/'} is group/other-writable"
    return None


def agent_writable_roots(cfg):
    repo = Path(cfg.repo).resolve()
    return (repo, Path(cfg.home).resolve(), *git_dirs(repo))


def check_cli_install(cfg):
    """Resolved path of the configured agent CLI, or CliUnavailable. The binary must be an explicit absolute path that no
    agent-writable tree (checkout, git dirs, runner home) contains - by name or after symlinks - and neither it nor any
    parent may be group/other-writable or owned by anyone but root (a worker-owned install, including one in the worker home,
    is writable by every unsandboxed worker process, so it is refused)."""
    if not cfg.claude_bin:
        raise CliUnavailable("no agent CLI configured (--claude-bin / VEYRO_CLAUDE_BIN); there is no PATH lookup")
    named = Path(cfg.claude_bin)
    if not named.is_absolute():
        raise CliUnavailable("the agent CLI path must be absolute")
    real = named.resolve()
    if not (real.is_file() and os.access(real, os.X_OK)):
        raise CliUnavailable("the agent CLI is not an executable file")
    for root in agent_writable_roots(cfg):
        if _inside(real, root) or _inside(Path(os.path.abspath(named)), root):
            raise CliUnavailable("the agent CLI lives inside an agent-writable tree (checkout or runner home)")
    why = chain_problem(real)
    if why:
        raise CliUnavailable(why)
    return real


def file_sha256(path, cap):
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            n += len(chunk)
            if n > cap:
                raise CliUnavailable("the agent CLI is larger than the hashing bound")
            h.update(chunk)
    return h.hexdigest()


def verify_cli(cfg):
    """check_cli_install plus an IMMUTABLE pin and a capability probe. The binary's sha256 and `--version` must equal the
    operator's pins (no pin = no dispatch; an auto-updated or swapped binary never runs), and it must advertise every lockdown
    flag we pass. Cached per binary identity; any doubt raises CliUnavailable."""
    real = check_cli_install(cfg)
    if not (cfg.claude_sha256 and cfg.claude_version and re.fullmatch(r"[0-9a-f]{64}", cfg.claude_sha256)):
        raise CliUnavailable("the agent CLI is not pinned: --claude-sha256 and --claude-version are mandatory")
    st = real.stat()
    key = (str(real), st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size, cfg.claude_sha256, cfg.claude_version)
    if cfg._cli_seen != key:
        try:
            digest = file_sha256(real, CLI_HASH_MAX)
            if digest != cfg.claude_sha256:
                raise CliUnavailable("the agent CLI does not match its pinned sha256")
            v = subprocess.run([str(real), "--version"], capture_output=True, text=True, timeout=30, cwd="/",
                               stdin=subprocess.DEVNULL, env=child_env())
            if v.returncode != 0 or v.stdout.split()[:1] != [cfg.claude_version]:
                raise CliUnavailable("the agent CLI version does not match its pin")
            r = subprocess.run([str(real), "--help"], capture_output=True, text=True, timeout=30, cwd="/",
                               stdin=subprocess.DEVNULL, env=child_env())
        except (OSError, subprocess.SubprocessError) as e:
            raise CliUnavailable(f"could not probe the agent CLI: {type(e).__name__}")
        if r.returncode != 0:
            raise CliUnavailable("the agent CLI probe failed")
        missing = [f for f in CLI_FLAGS if f not in r.stdout]
        if missing:
            raise CliUnavailable(f"the agent CLI lacks required flags {missing}")
        cfg._cli_seen = key
    return real


def cli_problem(cfg):
    try:
        verify_cli(cfg)
    except CliUnavailable as e:
        return str(e)
    except OSError as e:
        return f"agent CLI unreadable: {type(e).__name__}"
    return None


def child_env():
    env = {k: os.environ[k] for k in CHILD_ENV_KEEP if k in os.environ}  # no tokens, no GIT_* overrides
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # tests run by a read-only reviewer must not dirty the tree
    env["DISABLE_AUTOUPDATER"] = "1"  # the pinned CLI never replaces itself
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    return env  # no credential helper reaches a git child, and `git status` never takes index locks


# ---------------------------------------------------------------- host boundary (fail closed at startup and every dispatch)
Proc = namedtuple("Proc", "pid ppid uid lstart command")
PS_ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d+\s+\d\d:\d\d:\d\d\s+\d{4})\s+(.*)$")
RUNNER_RUN_RE = re.compile(r"runner\.py\b.*\srun(\s|$)")


def process_table():
    """Every process on the host as [Proc], or None when it cannot be enumerated (callers then fail closed)."""
    try:
        r = subprocess.run(["ps", "-axo", "pid=,ppid=,uid=,lstart=,command="], capture_output=True, text=True, timeout=15,
                           stdin=subprocess.DEVNULL, env={"PATH": "/bin:/usr/bin", "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return None
    rows = [PS_ROW.match(ln) for ln in r.stdout.splitlines() if ln.strip()]
    procs = [Proc(int(m[1]), int(m[2]), int(m[3]), " ".join(m[4].split()), m[5]) for m in rows if m]
    return procs if r.returncode == 0 and procs else None


def _relatives(table, me):
    """pids of `me`, its ancestors and its own descendants: the runner's own family, never a stray. Siblings and other
    descendants of an ancestor (another tab under the same shell, another sudo under sshd) are NOT family."""
    parent = {p.pid: p.ppid for p in table}
    fam, pid = {me}, me
    while parent.get(pid, 0) > 1 and parent[pid] not in fam:
        pid = parent[pid]
        fam.add(pid)
    mine = {me}
    grew = True
    while grew:
        grew = False
        for p in table:
            if p.ppid in mine and p.pid not in mine:
                mine.add(p.pid)
                grew = True
    return fam | mine


def worker_procs(table, uid=None):
    """[pid, lstart, daemon_identity_or_None] for every table row owned by `uid`. The third element is captured NOW,
    at baseline time, purely so a later rescan can tell a pinned daemon pid apart from an ordinary pre-existing one;
    it is never trusted on its own - new_worker_procs re-verifies it fresh against the CURRENT kernel-reported
    executable on every call, so a baseline entry is never a permanent pass for whatever that pid execs into next."""
    uid = os.geteuid() if uid is None else uid
    return [[p.pid, p.lstart, daemon_identity(p.pid)] for p in table if p.uid == uid]


DAEMON_EXE_PATHS = ("/usr/libexec/secd", "/usr/sbin/distnoted")  # exact, pinned per-user macOS daemons - never a directory
# prefix: a prefix (e.g. "/System/") also matches general-purpose interpreters that happen to live there (jsc, ruby, ...),
# which can run arbitrary worker-supplied code and must never be trusted just because the interpreter binary is root-owned.


def kernel_exe_path(pid):
    """The KERNEL's record of a process's backing executable (macOS proc_pidpath via libproc), never argv: a process
    cannot spoof this by rewriting its own command line the way it can `ps ... command=`. None on any failure or off
    Darwin - callers then treat the process as not allowlisted, never as allowlisted by default."""
    if sys.platform != "darwin":
        return None
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        buf = ctypes.create_string_buffer(4096)
        n = libproc.proc_pidpath(ctypes.c_int(pid), buf, ctypes.c_uint32(len(buf)))
    except OSError:
        return None
    if n <= 0:
        return None
    try:
        return buf.value.decode("utf-8", "surrogateescape")
    except ValueError:
        return None


def daemon_identity(pid):
    """This pid's CURRENT kernel-reported executable path (kernel_exe_path, never argv or a cached answer), if and
    only if it is EXACTLY one of DAEMON_EXE_PATHS - never a prefix match - and that path's whole chain is root-owned
    and unwritable right now. None for every other process, including one that used to match before it exec'd into
    something else: callers must call this fresh on every tick, never reuse a stale answer for the same pid."""
    real = kernel_exe_path(pid)
    if real not in DAEMON_EXE_PATHS:
        return None
    try:
        return real if chain_problem(Path(real)) is None else None
    except OSError:  # vanished between the kernel lookup and the stat (TOCTOU): not provable, never allowlisted
        return None


def escape_allowlisted(p, cfg):
    """True only when the KERNEL (kernel_exe_path, never argv) says a flagged process's real backing executable is
    one of the exact, pinned, root-owned, worker-unwritable macOS system daemons in DAEMON_EXE_PATHS (daemon_identity).
    Never an arbitrary worker-owned executable or script, and never decided from argv: a prior design also trusted a
    `dashboard`-labelled argv naming this install's runner.py, but argv is worker-controlled (`setsid <python> -c
    '<anything>' /path/to/runner.py dashboard &` satisfies it while running attacker code), so that branch is gone -
    there is currently no allowlisted way to restart the dashboard as an escape-tolerant process. `cfg` is accepted
    for call-site stability even though this check no longer depends on it."""
    return daemon_identity(p.pid) is not None


def new_worker_procs(baseline, table=None, cfg=None):
    """Worker-account processes that appeared since `baseline` ([[pid, lstart]] or [[pid, lstart, daemon_identity]])
    and are not the runner's own family. After the agent's process group has been killed and reaped, any such
    process escaped it (setsid, double fork). Returns None when the host cannot be enumerated - that is 'not
    provable', never 'clean'. With `cfg`, a process escape_allowlisted() clears (a root-owned, exactly pinned system
    daemon) is excluded from the result; callers with no cfg handle see the raw candidate set unfiltered.

    A baseline entry tagged with the daemon identity it matched at capture time (worker_procs) is NEVER a standing
    pass: that pid's kernel-reported executable is re-verified fresh, right now, on every single call. A process
    that has since exec'd into anything else - even keeping the same pid and start time, the exact TOCTOU a cached
    allowlist decision would miss - is treated as new, not as still that daemon, and flows through escape_allowlisted
    like any other candidate. An untagged baseline entry (ordinary pid, not a daemon at capture time) still means
    'pre-existing, not caused by this task' and is excluded without a recheck, unchanged from before."""
    table = process_table() if table is None else table
    if table is None or baseline is None:
        return None
    plain, pinned = set(), {}
    for entry in baseline:
        pid, ls = entry[0], entry[1]
        ident = entry[2] if len(entry) > 2 else None
        if ident:
            pinned[(pid, ls)] = ident
        else:
            plain.add((pid, ls))
    family = _relatives(table, os.getpid())
    cand = []
    for p in table:
        if p.uid != os.geteuid() or p.pid in family:
            continue
        key = (p.pid, p.lstart)
        if key in pinned:
            if daemon_identity(p.pid) == pinned[key]:
                continue  # still verified, right now, as that exact pinned daemon identity - not new
        elif key in plain:
            continue
        cand.append(p)
    return cand if cfg is None else [p for p in cand if not escape_allowlisted(p, cfg)]


def group_names():
    """Names of every group the process holds (primary, supplementary, directory-nested), or None if unresolvable."""
    try:
        user = pwd.getpwuid(os.geteuid()).pw_name
        gids = set(os.getgroups()) | set(os.getgrouplist(user, os.getegid()))
        names = {grp.getgrgid(g).gr_name for g in gids}
        for g in ADMIN_GROUPS:  # explicit membership lists too
            with contextlib.suppress(KeyError):
                if user in grp.getgrnam(g).gr_mem:
                    names.add(g)
        return names
    except (KeyError, OSError):
        return None


def worker_boundary_problem(cfg):
    """None only when this process IS the dedicated non-admin worker account and the owner's home is untraversable for it.
    No bypass: tests patch this function; production has no flag."""
    euid = os.geteuid()
    if euid == 0 or os.getuid() != euid:
        return "WORKER_BOUNDARY: the runner must not run as root or with a split real/effective uid"
    try:
        me, want = pwd.getpwuid(euid), pwd.getpwnam(cfg.worker_account)
    except KeyError:
        return f"WORKER_BOUNDARY: account {cfg.worker_account!r} does not exist, or the process uid has no account"
    if me.pw_uid != want.pw_uid:
        return f"WORKER_BOUNDARY: running as {me.pw_name!r}, not the dedicated worker account {cfg.worker_account!r}"
    groups = group_names()
    if groups is None:
        return "WORKER_BOUNDARY: group membership cannot be resolved"
    if groups & set(ADMIN_GROUPS):
        return f"WORKER_BOUNDARY: the worker account is in {sorted(groups & set(ADMIN_GROUPS))}"
    try:
        if Path.home().resolve() != Path(me.pw_dir).resolve():
            return "WORKER_BOUNDARY: $HOME is not the worker account's home (denials are computed from it)"
    except (OSError, RuntimeError):
        return "WORKER_BOUNDARY: the worker home cannot be resolved"
    oh = cfg.owner_home
    if not oh or not Path(oh).is_absolute() or not Path(oh).exists():
        return "WORKER_BOUNDARY: the owner home is not configured (--owner-home) or does not exist; cannot prove it is untraversable"
    if Path(oh).resolve() == Path(me.pw_dir).resolve():
        return "WORKER_BOUNDARY: the owner home is the worker home"
    # Durability: a bare "probe denied" only proves today's ACL/access state, which can be a single ACL entry that is
    # trivially removed. Require the standard POSIX bits to deny "other" as well, and that the owner home's group is not
    # one the worker holds, so the boundary still holds even if that one ACL entry (or staff-group access) goes away.
    try:
        oh_stat = Path(oh).stat()
    except OSError:
        return f"WORKER_BOUNDARY: the owner home {oh} cannot be stat'd"
    if oh_stat.st_mode & 0o007:
        return (f"WORKER_BOUNDARY: the owner home {oh} grants 'other' permission bits "
                f"({oct(oh_stat.st_mode & 0o777)}); not durable against a removed ACL entry")
    try:
        oh_group = grp.getgrgid(oh_stat.st_gid).gr_name
    except KeyError:
        oh_group = None
    if oh_group is not None and oh_group in groups:
        return f"WORKER_BOUNDARY: the owner home {oh} group {oh_group!r} is also held by the worker"
    try:  # a real syscall, not a mode guess: ENOENT/success means the path was traversable, EACCES means it is not
        os.stat(Path(oh) / ".veyro-traverse-probe")
        return f"WORKER_BOUNDARY: the owner home {oh} is traversable by the worker"
    except PermissionError:
        pass
    except OSError:
        return f"WORKER_BOUNDARY: the owner home {oh} is traversable by the worker"
    if os.access(oh, os.R_OK) or os.access(oh, os.X_OK):
        return f"WORKER_BOUNDARY: the owner home {oh} is accessible to the worker"
    return None


def runner_install_problem(cfg, install=None):
    """None only when the runner's own code (and the interpreter running it) sits outside every agent-writable tree, is owned
    by root and is not group/other-writable. An agent that could rewrite runner.py would run unsandboxed on the next restart."""
    base = Path(install or RUNNER_DIR).resolve()
    for root in agent_writable_roots(cfg):
        if _inside(base, root):
            return f"RUNNER_INSTALL: {base} is inside the agent-writable tree {root}; run a protected root-owned install"
    for var in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME"):
        if os.environ.get(var):
            return f"RUNNER_INSTALL: {var} is set; it can inject code into the runner"
    interp = Path(sys.executable).resolve()
    for what, path in (("interpreter", interp), ("runner directory", base)):
        why = chain_problem(path)
        if why:
            return f"RUNNER_INSTALL: {what} {path}: {why}"
    try:
        for f in sorted(base.iterdir()):
            if f.is_dir():
                continue
            real = f.resolve()
            st = real.stat()
            if any(_inside(real, root) for root in agent_writable_roots(cfg)):
                return f"RUNNER_INSTALL: {f.name} resolves into an agent-writable tree"
            if st.st_uid not in TRUSTED_UIDS or st.st_mode & 0o022 or (real.parent != base and chain_problem(real)):
                return f"RUNNER_INSTALL: {f.name} is not root-owned and unwritable"
    except OSError as e:
        return f"RUNNER_INSTALL: cannot inspect the install ({type(e).__name__})"
    if not (sys.flags.isolated or sys.flags.no_user_site):
        return ("RUNNER_INSTALL: the interpreter was not started isolated (-I) or with -s (no_user_site); "
                "~/Library/Python/*/site-packages/*.pth would still run code at startup")
    return None


def read_cutover_proof(cfg):
    """Raw bytes of the cutover proof, or ValueError. The proof is a single-writer claim, so it is trusted only when the worker
    cannot have forged it: an absolute path outside the runner home and the checkout, every parent root-owned and not
    group/other-writable (chain_problem), opened O_NOFOLLOW, and the opened file itself a root-owned regular file that group and
    other cannot write. There is no default location the worker could write; `run` requires --cutover-proof."""
    path = Path(cfg.cutover_proof)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("is not an absolute path")
    real = Path(os.path.realpath(path.parent)) / path.name
    if any(_inside(real, root.resolve()) for root in (Path(cfg.repo), Path(cfg.home))):
        raise ValueError("is inside an agent-writable tree")
    try:
        why = chain_problem(path.parent)
        if why:
            raise ValueError(f"has an unsafe parent chain ({why})")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise ValueError("is missing or unreadable")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid not in TRUSTED_UIDS or st.st_mode & 0o022:
            raise ValueError("is not a root-owned regular file unwritable by group/other")
        raw = os.read(fd, CUTOVER_MAX + 1)
    except OSError:
        raise ValueError("is missing or unreadable")
    finally:
        os.close(fd)
    if len(raw) > CUTOVER_MAX:
        raise ValueError("is too large")
    return raw


def _locked_runner_pid(cfg, table):
    """The pid of the ONE process that provably holds runner.lock in cfg.home, else None: the lock must be held right now, and
    its metadata pid + lstart must match a process_table row owned by this uid whose command is `runner.py ... run`. A free or
    stale lock, another uid (v1), a wrong start time or malformed metadata exempt nothing."""
    path = runner_lock_path(cfg.home)
    if FileLock.probe(path) != "held":
        return None
    meta = FileLock(path).owner()
    if not isinstance(meta, dict):
        return None
    pid, lstart = meta.get("pid"), meta.get("lstart")
    if not (isinstance(pid, int) and not isinstance(pid, bool) and pid > 1 and isinstance(lstart, str) and lstart.strip()):
        return None
    want, uid = " ".join(lstart.split()), os.geteuid()
    for p in table:
        if p.pid == pid and p.lstart == want and p.uid == uid and RUNNER_RUN_RE.search(p.command):
            return pid
    return None


def cutover_problem(cfg):
    """v1 and v2 hold unrelated locks in different homes, so exclusion needs an explicit proof: the operator-written
    `cutover.json` binds the pinned legacy copy to the v1 runner (pid + start time) it was copied from. Fails closed unless
    the proof is trustworthy (read_cutover_proof), that exact process is gone AND no other `runner.py run` process exists on
    the host. The only runner other than our own family that is tolerated is the single live v2 runner holding runner.lock
    in this home (_locked_runner_pid), so the owner wrapper can enqueue while it runs; v1 and any second runner stay refused.
    The v1 repo-writer lock lives in the owner's home and cannot be probed from here; this proof is what stands in for it."""
    try:
        raw = read_cutover_proof(cfg)
    except ValueError as e:
        return f"CUTOVER_PROOF: {cfg.cutover_proof} {e}; no cutover proof, no dispatch"
    try:
        proof = json.loads(raw)
    except ValueError:
        return f"CUTOVER_PROOF: {cfg.cutover_proof} is missing or unreadable; no cutover proof, no dispatch"
    v1 = proof.get("v1_runner") if isinstance(proof, dict) else None
    if not (isinstance(proof, dict) and proof.get("schema") == 1 and cfg.legacy_sha256 and proof.get("legacy_sha256") == cfg.legacy_sha256
            and isinstance(proof.get("operator"), str) and proof["operator"].strip() and isinstance(proof.get("stopped_at"), str)
            and isinstance(v1, dict) and isinstance(v1.get("pid"), int) and not isinstance(v1["pid"], bool) and v1["pid"] > 1
            and isinstance(v1.get("lstart"), str) and v1["lstart"].strip()):
        return "CUTOVER_PROOF: malformed, or not bound to the pinned legacy copy"
    table = process_table()
    if table is None:
        return "CUTOVER_PROOF: the host process table cannot be read; cannot prove the v1 runner is gone"
    want = " ".join(v1["lstart"].split())
    if any(p.pid == v1["pid"] and p.lstart == want for p in table):
        return f"CUTOVER_PROOF: the v1 runner (pid {v1['pid']}) is still running"
    family = _relatives(table, os.getpid())  # this runner, its launcher wrapper and its children are not 'another runner'
    # The runner is already in its own family; only an external control process needs the lock-holder exemption.
    # Never let writable lock metadata name a stray runner and hide it from the real runner's own dispatch check.
    live = None if any(p.pid in family and RUNNER_RUN_RE.search(p.command) for p in table) else _locked_runner_pid(cfg, table)
    others = [p.pid for p in table if p.pid not in family and p.pid != live and RUNNER_RUN_RE.search(p.command)]
    if others:
        return f"CUTOVER_PROOF: another runner process is alive (pid {others[:3]}); v1/v2 exclusion cannot be proven"
    return None


def host_problem(cfg):
    """First failed startup/dispatch predicate, or None. Every check is a real syscall or file read, never a flag."""
    for check in (worker_boundary_problem, runner_install_problem, legacy_problem, cutover_problem, legacy_evidence_problem):
        why = check(cfg)
        if why:
            return why
    return None


# OS confinement. The agent's Bash is confined by the CLI's native sandbox (turn_settings below); the planner CLI client and
# verifiers run under macOS Seatbelt. The planner tree cannot write the runner home (v2 state, v1 history, events, locks),
# any git dir, shell-profile / LaunchAgent persistence points, nor read credential stores. Network stays open for the planner
# because its client must reach the gateway; credential reach is cut instead (no global git config, no ssh/gh/keychain files).
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
# Paths below are relative to the WORKER home. Credential stores and the CLI's own login state: never readable by agent or verifier.
SECRET_DIRS = (".ssh", ".aws", ".gnupg", ".kube", ".docker", ".config/gh", ".config/git", ".openclaw", ".claude", ".config/claude",
               ".local/share/claude", "Library/Keychains", "Library/Application Support/Claude")
SECRET_FILES = (".netrc", ".npmrc", ".pypirc", ".git-credentials", ".claude.json")
# Shell-profile / launch / CLI-launcher persistence points: never writable by agent, verifier or planner client, stated
# explicitly rather than left to the native sandbox's default write scope.
PERSIST_WRITE = (".zshrc", ".zprofile", ".zshenv", ".zlogin", ".zlogout", ".bash_profile", ".bash_login", ".bashrc",
                 ".bash_logout", ".profile", ".gitconfig", ".config", ".local/bin", ".local/share", "Library/LaunchAgents",
                 "Library/Python", "Library/Preferences")
TOO_BROAD = ("/usr", "/usr/local", "/opt", "/System", "/Library", "/Applications", "/private", "/var")


class SandboxUnavailable(Exception):
    pass


def sandbox_ready(cfg):
    return cfg.sandbox == "off" or (sys.platform == "darwin" and os.access(SANDBOX_EXEC, os.X_OK))


def _sb(path):
    return json.dumps(str(path))  # Seatbelt string literals accept JSON-style escaping


def forms(*paths):
    """Every spelling of each path: as given and fully symlink-resolved (macOS /var -> /private/var, a symlinked home). A rule that
    names only one spelling is not a boundary; both are listed, sorted and de-duplicated."""
    out = set()
    for p in paths:
        p = Path(p)
        out.update((str(p), str(p.resolve())))
    return sorted(out)


def git_dirs(repo):
    """Every git dir of the checkout (a linked worktree has a private dir plus the shared common dir)."""
    repo = Path(repo).resolve()
    dirs = {repo / ".git"}
    try:
        for line in git_run(repo, "rev-parse", "--absolute-git-dir", "--git-common-dir").stdout.decode().split("\n"):
            if line.strip():
                dirs.add((repo / line.strip()).resolve())
    except (OSError, subprocess.SubprocessError):
        pass
    return sorted(dirs)


def worker_paths(rels):
    h = Path.home()
    return [h / r for r in rels]


def _deny_rules(cfg, secrets=True):
    r = Path(cfg.repo).resolve()
    writes = forms(Path(cfg.home), *git_dirs(r), *worker_paths(PERSIST_WRITE), *worker_paths(SECRET_DIRS),
                   *worker_paths(SECRET_FILES), RUNNER_DIR)
    rules = ["(deny file-write* " + " ".join(f"(subpath {_sb(p)})" for p in writes) + ")"]
    keep = SECRET_DIRS if secrets else tuple(p for p in SECRET_DIRS if p != ".openclaw")  # the planner client reads its gateway config
    reads = [f"(subpath {_sb(p)})" for p in forms(*worker_paths(keep))] + \
            [f"(literal {_sb(p)})" for p in forms(*worker_paths(SECRET_FILES))]
    return rules + ["(deny file-read* " + " ".join(reads) + ")"]


def confine_planner(cfg, profile_path):
    """argv prefix confining the OpenClaw planner CLI client; [] only for an explicit test fixture (sandbox='off')."""
    if cfg.sandbox == "off":
        return []
    if not sandbox_ready(cfg):
        raise SandboxUnavailable(f"{SANDBOX_EXEC} unavailable on this platform; agent dispatch is refused")
    try:
        atomic_write(profile_path, ("(version 1)\n(allow default)\n" + "\n".join(_deny_rules(cfg, secrets=False)) + "\n").encode())
    except OSError as e:
        raise SandboxUnavailable(f"could not write the sandbox profile: {e}"[:200])
    return [SANDBOX_EXEC, "-f", str(profile_path)]


# Native sandbox policy for one agent turn. Paths the CLI's Bash must never read (credential stores, the CLI's own login state,
# the runner home with its verify logs and history, the owner home) and never write (runner state and install, the CLI install,
# persistence points, Git metadata, anything that could change policy or hooks in the checkout). Every path is listed in each
# of its spellings (forms), and in the worker home, whatever HOME the CLI is started with.
PROTECTED_REPO = (".claude", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md", ".githooks")
# Agent-instruction filenames a CLI may auto-load as project instructions from ANY directory, not only the repo root.
# PROTECTED_REPO's deny_write only lists the top-level spelling (a real, durable denial for that one path); a nested copy
# is instead refused in-scope (see in_scope) no matter what a task's allowed_paths says, so planting one is never a
# COMPLETED task regardless of depth or whether the file already existed. in_scope only stops the planting TASK: the
# planted file itself stays in the worktree afterward, so instruction_contamination additionally refuses dispatch for
# every role (including review of some other, already-completed task) until it is gone.
INSTRUCTION_BASENAMES = ("CLAUDE.md", "CLAUDE.local.md")
INSTRUCTION_BASENAMES_CF = frozenset(b.casefold() for b in INSTRUCTION_BASENAMES)  # case-insensitive volumes: match either casing


def turn_settings(cfg, role, claude_real):
    """The --settings document for one turn. Implementers may write only the checkout; every other role (review, planner)
    may write nowhere in it. Bash has no network, no unsandboxed retry and no excluded commands."""
    repo = Path(cfg.repo).resolve()
    named = Path(os.path.abspath(cfg.claude_bin)) if cfg.claude_bin else Path(claude_real)
    legacy = [Path(cfg.legacy_state)] if cfg.legacy_state else []
    owner = [Path(cfg.owner_home)] if cfg.owner_home else []
    deny_write = forms(Path(cfg.home), RUNNER_DIR, Path(claude_real).parent, named.parent, *legacy, *owner,
                       *(repo / n for n in PROTECTED_REPO), *git_dirs(repo), *worker_paths(PERSIST_WRITE),
                       *worker_paths(SECRET_DIRS), *worker_paths(SECRET_FILES))
    if role not in WRITE_ROLES:
        deny_write = sorted({*deny_write, *forms(repo)})
    deny_read = forms(Path(cfg.home), *legacy, *owner, *worker_paths(SECRET_DIRS), *worker_paths(SECRET_FILES))
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        deny_read = sorted({*deny_read, *forms(os.environ["CLAUDE_CONFIG_DIR"])})
    return {"sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                        "excludedCommands": [],
                        "filesystem": {"allowWrite": [str(repo)] if role in WRITE_ROLES else [],
                                       "denyWrite": deny_write, "denyRead": deny_read},
                        "network": {"allowedDomains": []}},
            "permissions": {"allow": list(AGENT_TOOLS), "defaultMode": "dontAsk"},
            "disableAllHooks": True}


def assert_posture(cfg, role, claude_real, settings):
    """Independently re-derive what the settings must guarantee and compare; CliUnavailable on any gap or surprise. Run on
    the document in memory and again on the bytes read back from disk, so a weakened or truncated file never launches."""
    want = turn_settings(cfg, role, claude_real)
    sb, wsb = (settings.get("sandbox") if isinstance(settings, dict) else None), want["sandbox"]
    fs = sb.get("filesystem") if isinstance(sb, dict) and isinstance(sb.get("filesystem"), dict) else {}
    problems = []
    for key in ("enabled", "failIfUnavailable", "allowUnsandboxedCommands", "excludedCommands"):
        if not isinstance(sb, dict) or sb.get(key) != wsb[key] or type(sb.get(key)) is not type(wsb[key]):
            problems.append(f"sandbox.{key}")
    if not isinstance(sb, dict) or sb.get("network") != wsb["network"]:
        problems.append("sandbox.network")
    if fs.get("allowWrite") != wsb["filesystem"]["allowWrite"]:
        problems.append("sandbox.filesystem.allowWrite")
    for key in ("denyWrite", "denyRead"):
        have = fs.get(key)
        if not isinstance(have, list) or not set(wsb["filesystem"][key]) <= set(have):
            problems.append(f"sandbox.filesystem.{key}")
    perms = settings.get("permissions") if isinstance(settings, dict) else None
    if not isinstance(perms, dict) or perms.get("allow") != list(AGENT_TOOLS) or perms.get("defaultMode") != "dontAsk":
        problems.append("permissions")
    if not isinstance(settings, dict) or settings.get("disableAllHooks") is not True:
        problems.append("disableAllHooks")
    if problems:
        raise CliUnavailable("sandbox posture not verified: " + ", ".join(problems))


def write_turn_settings(cfg, role, claude_real, path):
    settings = turn_settings(cfg, role, claude_real)
    assert_posture(cfg, role, claude_real, settings)
    try:
        atomic_write(path, json.dumps(settings, indent=1).encode())
        assert_posture(cfg, role, claude_real, json.loads(Path(path).read_bytes()))
    except (OSError, ValueError) as e:
        raise CliUnavailable(f"could not write or re-read the turn settings: {type(e).__name__}")
    return path


def confine_verifier(cfg, profile_path, tmpdir, argv):
    """Deny-default verifier. Reads: the system, plus ONLY the checkout and the interpreter inside the worker and owner homes
    (deny-by-default there, so ssh/aws/gh/git credentials, shell profiles, the runner home and its logs, and the owner home
    are all unreadable); the credential and runner-state denials come last so they win even if a prefix sits beside them. No
    network, writes only to the private scratch dir. Every path is listed in each spelling."""
    if cfg.sandbox == "off":
        return []
    if not sandbox_ready(cfg):
        raise SandboxUnavailable(f"{SANDBOX_EXEC} unavailable on this platform; verification is refused")
    execs, prefixes = set(), set()
    for pre in {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix}:
        p = Path(pre).resolve()
        if len(p.parts) < 3 or str(p) in TOO_BROAD:
            raise SandboxUnavailable(f"python prefix {p} is too broad to allow process-exec under")
        prefixes.add(p)
        execs.update(f"(subpath {_sb(q)})" for q in forms(p))
    exe = shutil.which(argv[0]) or argv[0]
    execs.update(f"(literal {_sb(q)})" for q in forms(Path(exe).resolve(), Path(sys.executable).resolve()))
    repo = Path(cfg.repo).resolve()
    homes = [Path.home(), *([Path(cfg.owner_home)] if cfg.owner_home else []), Path(cfg.home)]
    closed = [f"(subpath {_sb(q)})" for q in forms(*homes)]
    open_ = [f"(subpath {_sb(q)})" for q in forms(repo, *prefixes)]
    secret = [f"(subpath {_sb(q)})" for q in forms(Path(cfg.home), *([Path(cfg.owner_home)] if cfg.owner_home else []),
                                                   *worker_paths(SECRET_DIRS))] + \
             [f"(literal {_sb(q)})" for q in forms(*([Path(cfg.legacy_state)] if cfg.legacy_state else []),
                                                    *worker_paths(SECRET_FILES), *worker_paths(PERSIST_WRITE))]
    profile = ("(version 1)\n(deny default)\n(allow file-read*)\n(allow sysctl-read)\n(allow process-fork)\n"
               "(allow signal (target self))\n(allow process-exec " + " ".join(sorted(execs)) + ")\n"
               "(deny file-read* " + " ".join(closed) + ")\n(allow file-read* " + " ".join(open_) + ")\n"
               "(deny file-read* " + " ".join(secret) + ")\n"
               "(allow file-write* (subpath " + _sb(Path(tmpdir).resolve()) + ') (literal "/dev/null"))\n')
    try:
        atomic_write(profile_path, profile.encode())
    except OSError as e:
        raise SandboxUnavailable(f"could not write the sandbox profile: {e}"[:200])
    return [SANDBOX_EXEC, "-f", str(profile_path)]


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0


class CliStream:
    """Bounded fold of the agent CLI's `--output-format stream-json` events. Keeps the final answer, the primary model, token
    usage, counts and names of tool activity, and the first policy violation. Raw events, tool inputs and tool results are
    never stored (they carry source and whatever the shell printed); the system/init event also carries account data."""

    def __init__(self, alias=None, max_turns=MAX_TURNS):
        self.alias, self.max_turns = alias, max_turns
        self.text, self.text_len, self.last_msg, self.msg_ids = [], 0, None, set()
        self.primary, self.session_id, self.final, self.error, self.init_ok = None, None, None, None, False
        self.violation = None  # (reason code, detail): the runner kills the turn as soon as one is set
        self.events = self.bad = self.dropped = self.tool_calls = self.tool_results = self.tool_errors = 0
        self.denials = []

    def flag(self, code, detail):
        self.violation = self.violation or (code, str(detail)[:200])

    def feed(self, line):
        try:
            ev = json.loads(line)
        except ValueError:
            self.bad += 1
            return
        if not isinstance(ev, dict):
            return
        self.events += 1
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            self.init(ev)
        elif kind == "assistant":
            self.assistant(ev.get("message") if isinstance(ev.get("message"), dict) else {})
        elif kind == "user":
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            for blk in msg.get("content") if isinstance(msg.get("content"), list) else ():
                if isinstance(blk, dict) and blk.get("type") == "tool_result":
                    self.tool_results += 1
                    self.tool_errors += blk.get("is_error") is True
        elif kind == "result":
            self.result(ev)

    def init(self, ev):
        model = ev.get("model")
        self.primary = model[:100] if isinstance(model, str) else None
        if isinstance(ev.get("session_id"), str):
            self.session_id = ev["session_id"][:100]
        if self.alias and self.primary and self.primary != self.alias:
            self.flag("MODEL_MISMATCH", f"CLI runs {self.primary}, configured {self.alias}")
        have = (ev.get("tools"), ev.get("mcp_servers"), ev.get("permissionMode"))
        if have != (list(AGENT_TOOLS), [], "dontAsk"):
            self.flag("SANDBOX_POSTURE_VIOLATION", f"CLI reported tools/mcp/mode {str(have)[:150]}")
        elif not self.violation:
            self.init_ok = True

    def assistant(self, msg):
        mid = msg.get("id") if isinstance(msg.get("id"), str) else None
        model = msg.get("model")
        if self.alias and isinstance(model, str) and model != self.alias:
            self.flag("MODEL_MISMATCH", f"a turn ran on {model[:80]}, configured {self.alias}")
        if mid and mid not in self.msg_ids:
            self.msg_ids.add(mid)
            if len(self.msg_ids) > self.max_turns:
                self.flag("TURN_LIMIT", f"more than {self.max_turns} assistant turns")
        for blk in msg.get("content") if isinstance(msg.get("content"), list) else ():
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "tool_use":
                self.tool_calls += 1
                if blk.get("name") not in AGENT_TOOLS:
                    self.flag("SANDBOX_POSTURE_VIOLATION", f"tool {str(blk.get('name'))[:40]} is not an allowed tool")
            elif blk.get("type") == "text" and isinstance(blk.get("text"), str) and self.text_len < ACP_TEXT_MAX:
                if self.last_msg is not None and mid != self.last_msg:
                    self.text.append("\n")  # a new message must not glue onto the previous line
                    self.text_len += 1
                self.last_msg = mid
                self.text.append(blk["text"][:ACP_TEXT_MAX - self.text_len])
                self.text_len += len(self.text[-1])

    def result(self, ev):
        self.final = ev
        if isinstance(ev.get("session_id"), str):
            self.session_id = ev["session_id"][:100]
        rows = ev.get("permission_denials")
        self.denials = [str(r.get("tool_name"))[:40] for r in rows[:50] if isinstance(r, dict)] if isinstance(rows, list) else []
        if ev.get("is_error") is True or ev.get("subtype") != "success":
            self.error = f"{str(ev.get('subtype'))[:40]}: {str(ev.get('result'))[:250]}"

    def pump(self, stream):
        """Read a pipe to EOF in bounded memory; a line over ACP_LINE_MAX is dropped, not buffered."""
        skipping = False
        for chunk in iter(lambda: stream.readline(ACP_LINE_MAX + 1), b""):
            full = chunk.endswith(b"\n")
            if skipping or (len(chunk) > ACP_LINE_MAX and not full):
                self.dropped += not skipping
                skipping = not full
            else:
                self.feed(chunk)

    @property
    def stop(self):
        """end_turn only for a successful result; everything else is the CLI's own subtype (error_max_turns, ...)."""
        f = self.final
        if not isinstance(f, dict):
            return None
        if f.get("is_error") is True:
            return "error"
        return "end_turn" if f.get("subtype") == "success" else str(f.get("subtype") or "error")[:40]

    def message(self):
        final = (self.final or {}).get("result")
        return final[:ACP_TEXT_MAX] if isinstance(final, str) and final.strip() else "".join(self.text)

    def model_usage(self):
        """{model: tokens+cost} from the final result's modelUsage (lists a haiku sidecar next to the primary)."""
        rows = (self.final or {}).get("modelUsage")
        out = {}
        for model, u in list(rows.items())[:20] if isinstance(rows, dict) else ():
            if isinstance(model, str) and isinstance(u, dict):
                out[model[:100]] = {k: _n(u.get(k)) for k in (*TOKEN_FIELDS, "costUSD")}
        return out


def judge_route(role, stream, alias=None):
    """Routing verdict from what the CLI reports: the primary model must be the configured model id exactly, and no
    non-primary model other than a haiku sidecar may have consumed tokens. Everything seen is recorded; absence of
    evidence is UNVERIFIED, never assumed."""
    want, usage = required_family(role), stream.model_usage()
    toks = {m: sum(_n(u.get(k)) for k in TOKEN_FIELDS) for m, u in usage.items()}
    models = sorted(({"model": m, "family": family_of(m), "tokens": n} for m, n in toks.items() if n > 0), key=lambda m: -m["tokens"])
    route = {"intended": want, "primary": stream.primary, "verdict": "UNVERIFIED", "models": models,
             "sidecars": [m["model"] for m in models if m["model"] != stream.primary]}
    if not stream.primary:
        return {**route, "basis": "CLI output carried no primary model; family not observable"}
    off = [m["model"] for m in models if m["family"] not in (want, "haiku")]
    if alias and stream.primary != alias:
        return {**route, "verdict": "MISMATCH", "basis": f"primary {stream.primary} is not the configured model {alias}"}
    if family_of(stream.primary) != want or off:
        return {**route, "verdict": "MISMATCH", "basis": f"primary {stream.primary}; non-{want} model(s) used: {off or [stream.primary]}"}
    if usage and not any(m["family"] == want for m in models):
        return {**route, "verdict": "MISMATCH", "basis": f"primary {stream.primary} but no {want} tokens in model usage"}
    return {**route, "verdict": "VERIFIED", "basis": f"primary {stream.primary} is {want}"
            + ("" if usage else "; no per-model usage reported")}


def subjects_current(repo, subject):
    return all(file_hash(Path(repo) / s["path"]) == s["sha256"] for s in subject)


# ------------------------------------------------------------ OpenClaw handoff helpers
class HandoffError(Exception):
    pass


def _no_dup_keys(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r}")
        out[k] = v
    return out


def _bad_constant(c):
    raise ValueError(f"non-finite constant {c}")


def strict_json(text):
    return json.loads(text, object_pairs_hook=_no_dup_keys, parse_constant=_bad_constant)


def _has_include(node):
    if isinstance(node, dict):
        return any(k in ("$include", "include", "includes") or _has_include(v) for k, v in node.items())
    return isinstance(node, list) and any(_has_include(v) for v in node)


def openclaw_config_path(path=None):
    return Path(path or os.environ.get("OPENCLAW_CONFIG_PATH") or Path.home() / ".openclaw" / "openclaw.json")


def planner_policy_blocker(config_path=None):
    """None only if the configured planner agent is provably read/list-only on the built-in OpenClaw runtime; else a
    precise blocker string. Anything not provable from the one strict-JSON config file fails closed.

    WARNING for any future change that would act on a clean (None) result: this reads a WORKER-local, worker-writable
    file. That makes it a useful, narrow lint against an obviously-misconfigured planner entry while handoff stays
    inert - it is NOT, and must never be treated as, the distinct scoped worker identity and independent control path
    HANDOFF_ENABLED's own gate requires. The worker that would run under this policy could rewrite the very file this
    function trusts."""
    path = openclaw_config_path(config_path)
    try:
        cfg = strict_json(path.read_text())
    except (OSError, ValueError) as e:
        return f"PLANNER_POLICY_UNPROVEN: cannot read strict-JSON gateway config {path.name} ({str(e)[:60]})"
    if _has_include(cfg):
        return "PLANNER_POLICY_UNPROVEN: config uses include/override layers; effective entry cannot be proven"
    agents = cfg.get("agents") if isinstance(cfg, dict) else None
    entries = agents.get("entries") if isinstance(agents, dict) and "list" not in agents else None
    if not isinstance(entries, dict):
        return "PLANNER_POLICY_UNPROVEN: agents.entries must be an object keyed by agent id (no legacy list)"
    mine = [k for k in entries if isinstance(k, str) and k.strip().lower() == ORCH_AGENT]
    if mine != [ORCH_AGENT] or not isinstance(entries[ORCH_AGENT], dict):
        return f"PLANNER_POLICY_UNPROVEN: agent {ORCH_AGENT} is missing, duplicated or malformed"
    a = entries[ORCH_AGENT]
    if set(a) - {"id", "name", "workspace", "model", "models", "tools", "subagents"} or a.get("id", ORCH_AGENT) != ORCH_AGENT:
        return "PLANNER_POLICY_UNPROVEN: unsafe tool or sandbox override on the planner entry"
    model = a.get("model")
    if isinstance(model, dict):
        model = model.get("primary") if set(model) <= {"primary"} else None
    if model != PLANNER_MODEL:
        return f"PLANNER_POLICY_UNPROVEN: model is not exactly {PLANNER_MODEL}"
    tools = a.get("tools")
    if not isinstance(tools, dict) or set(tools) - {"allow", "deny"}:
        return "PLANNER_POLICY_UNPROVEN: tools must be an allow/deny list only"
    allow, deny = tools.get("allow"), tools.get("deny", [])
    if not (isinstance(allow, list) and allow and all(isinstance(x, str) for x in allow)) or not set(allow) <= PLANNER_TOOLS:
        return "PLANNER_POLICY_UNPROVEN: tools.allow must be a non-empty subset of read/ls/dir_list"
    if not isinstance(deny, list) or not all(isinstance(x, str) for x in deny) or set(deny) & set(allow):
        return "PLANNER_POLICY_UNPROVEN: tools.deny must not contradict allow"
    sub = a.get("subagents")
    if not (isinstance(sub, dict) and sub.get("allowAgents") == []):
        return "PLANNER_POLICY_UNPROVEN: subagents.allowAgents must be an explicit empty list"
    scoped = a.get("models")
    override = scoped.get(PLANNER_MODEL) if isinstance(scoped, dict) and set(scoped) == {PLANNER_MODEL} else None
    runtime = override.get("agentRuntime") if isinstance(override, dict) and set(override) == {"agentRuntime"} else None
    if not (isinstance(runtime, dict) and set(runtime) == {"id"} and runtime["id"] == PLANNER_RUNTIME):
        return f'PLANNER_RUNTIME_UNPROVEN: models[{PLANNER_MODEL}] must be exactly {{"agentRuntime": {{"id": "{PLANNER_RUNTIME}"}}}}'
    return None


def discover_orchestrator_bin():
    """Absolute path of the OpenClaw CLI. The LaunchAgent PATH has no node/nvm dir, so look beyond PATH."""
    found = shutil.which("openclaw")
    if found:
        return found
    def ver(b):
        return tuple(int(x) if x.isdigit() else 0 for x in b.parent.parent.name.lstrip("v").split("."))
    nvm = sorted(Path.home().glob(".nvm/versions/node/*/bin/openclaw"), key=ver)
    fixed = [Path(x) for x in ("/opt/homebrew/bin/openclaw", "/usr/local/bin/openclaw") if os.access(x, os.X_OK)]
    cands = [*reversed(nvm), *fixed]
    return str(cands[0]) if cands else None


def _digest(p):
    """Bounded, non-following digest (file_hash); 'absent' when there is nothing there."""
    return file_hash(p) or "absent"


def parse_handoff_envelope(raw):
    """Final assistant text from `openclaw agent --json` stdout; only the documented envelope is read."""
    if len(raw) > HANDOFF_OUT_MAX:
        raise HandoffError("CLI stdout exceeds the size bound")
    try:
        env = strict_json(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise HandoffError("CLI stdout is not one strict JSON document")
    if not isinstance(env, dict) or env.get("status") != "ok":
        raise HandoffError("CLI envelope status is not ok")
    result = env.get("result")
    meta = result.get("meta") if isinstance(result, dict) else None
    agent = meta.get("agentMeta") if isinstance(meta, dict) else None
    if not isinstance(agent, dict) or meta.get("aborted") is not False:
        raise HandoffError("turn aborted, or abort state not reported")
    if agent.get("agentHarnessId") != PLANNER_RUNTIME:  # the policy check only proved this runtime
        raise HandoffError(f"agentHarnessId is not {PLANNER_RUNTIME!r}")
    payloads = result.get("payloads")
    final = payloads[-1] if isinstance(payloads, list) and payloads else None
    text = final.get("text") if isinstance(final, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text) > HANDOFF_TEXT_MAX:
        raise HandoffError("no final assistant text payload within the size bound")
    return text


def parse_handoff_proposal(text, req_id):
    """Exactly one JSON object {request_id, kind, reason, task?}; prose/markdown is rejected."""
    try:
        prop = strict_json(text)
    except ValueError:
        raise HandoffError("final payload is not a single strict JSON object")
    if not isinstance(prop, dict) or not {"request_id", "kind", "reason"} <= set(prop) or set(prop) - {"request_id", "kind", "reason", "task"}:
        raise HandoffError("proposal keys must be request_id, kind, reason and (TASK only) task")
    if prop["request_id"] != req_id:
        raise HandoffError("request_id does not match the open request (stale or foreign response)")
    if prop["kind"] not in HANDOFF_KINDS:
        raise HandoffError("kind must be TASK, BLOCKED, WAITING_FOR_OWNER or NO_LEGAL_WORK")
    if not isinstance(prop["reason"], str) or not 0 < len(prop["reason"].strip()) <= 500:
        raise HandoffError("reason must be a non-empty string of at most 500 chars")
    if (prop["kind"] == "TASK") != ("task" in prop):
        raise HandoffError("a task object is required for TASK and forbidden for every other kind")
    if prop["kind"] == "TASK" and not (isinstance(prop["task"], dict) and set(prop["task"]) <= HANDOFF_TASK_KEYS):
        raise HandoffError("task must be one object with only enqueue fields")
    return prop


def proposal_problem(cfg, spec):
    """Extra limits on orchestrator-proposed work, on top of validate_task. None if acceptable."""
    for a in spec.get("allowed_paths") or []:
        if isinstance(a, str):
            base = re.split(r"[*?\[]", a)[0]
            if any(base.startswith(p) or p.startswith(base) for p in PROPOSAL_PROTECTED):
                return f"allowed path {a!r} touches runner, CI, governance or module-record files"
    mod = spec.get("module")
    if isinstance(mod, str) and module_record_accepted(cfg.repo, mod):
        return f"{mod} is already recorded ACCEPTED; no further task is proposed for it"
    verify = spec.get("verify_cmd")
    if spec.get("role") in WRITE_ROLES:
        ok = (isinstance(verify, list) and len(verify) >= 4 and verify[0] in (sys.executable, "python3", "python")
              and verify[1:3] == ["-m", "unittest"] and all(isinstance(x, str) and VERIFY_TARGET_RE.match(x) for x in verify[3:]))
        if not ok:
            return "write tasks need verify_cmd [python, -m, unittest, <dotted test module>, ...]"
    elif verify is not None:
        return "review tasks carry no verify_cmd"
    return None


def handoff_failure_run(tasks, module=None):
    """Runner-side anti-loop backstop that no prompt wording can change: how many handoff-sourced tasks FAILED back to back at
    the tail of the queue (optionally only counting `module`). Any other task in the way - a completion, an owner task, one still
    pending - ends the run."""
    n = 0
    for t in sorted(tasks.values(), key=lambda x: x["seq"], reverse=True):
        if module is not None and t["module"] != module:
            continue
        if t.get("source") == "handoff" and t["status"] == "FAILED":
            n += 1
        else:
            break
    return n


def handoff_prompt(cfg, req_id, summary, previous):
    q = json.dumps
    return f"""You are the Veyro mission orchestrator running ONE read-only planning turn (request {req_id}).
The Veyro mission runner has no eligible task. Your only job: choose the next legal task, or report why none exists.
You are not a worker and have no write path.

Context (inspect it yourself, read-only; do not trust this summary):
- Repository: {q(str(cfg.repo))}
- Module catalog: {q(str(cfg.repo / 'tools/mission_runner/module_catalog.json'))} at committed HEAD; module records: knowledge/03-Modules/<MOD>/<MOD>.md (Status line)
- Task lifecycle: {summary}
- Your previous answer for the earlier state: {previous or 'none'}
- Legacy v1 history (read-only, preserved, never executed): {q(str(cfg.legacy_state))}. Never reuse a v1 task id. Old outcomes are not current task progress, but their rejected attempts and correction counts remain binding historical evidence.

Rules:
1. Base every decision on evidence in files and runner state (module records, task results, git HEAD), never on memory.
2. Module order: a write task needs every catalog dependency recorded ACCEPTED. Never propose work for an ACCEPTED module.
3. After a COMPLETED implement/test task, the next legal step in that module is an independent `review` task with review_of naming it. Roles: implement/test run on Sonnet, review on Opus.
4. If a task FAILED or was BLOCKED, propose only unrelated legal work unless the evidence shows its blocker is resolved. A corrective task must set "remediates" to the failed task id and change the prompt, scope or verifier materially; the runner refuses identical failed work under a new id, and refuses write tasks while a failed task's changes are still unresolved in the worktree unless "remediates" names it.
4a. For MOD-004 D16 design or correction work, read knowledge/00-Decisions/OWNER-2026-10-26-mod004-d16-dual-version-design.md and the cumulative D16 review history and count v1 plus v2 attempts against its one initial attempt and two material corrections total. Never reset the count by choosing a new task ID or runner. If the budget is exhausted or the count is ambiguous, answer WAITING_FOR_OWNER. Do not treat a prior CHANGES_REQUESTED review as approval.
5. Make no owner decisions. If progress needs an owner approval, acceptance or policy decision answer WAITING_FOR_OWNER.
6. Do NOT edit, create, delete or commit any file, run the runner CLI, or accept any module. The runner validates and enqueues.

Your final assistant message must be exactly one JSON object (no markdown, no prose, no code fence):
{{"request_id": "{req_id}", "kind": "TASK" | "BLOCKED" | "WAITING_FOR_OWNER" | "NO_LEGAL_WORK", "reason": "<one line, at most 500 chars>", "task": {{...}}}}
"task" only for TASK, one object with: id ([A-Za-z0-9._-]{{1,64}}, unique), module (MOD-nnn), role (implement|test|review), title, prompt (the full worker prompt), allowed_paths (exact files or dir/ prefixes; required for implement/test, none for review; never tools/mission_runner/, .github/, governance, baseline or knowledge/03-Modules/), verify_cmd (implement/test: exactly [{q(sys.executable)}, "-m", "unittest", "<dotted test module>", ...]; none for review), review_of (review only: the implement/test task id), optional depends_on, max_attempts and remediates.
"""


class Runner:
    def __init__(self, cfg):
        self.cfg, self.store = cfg, Store(cfg.home)
        self.rlock = FileLock(runner_lock_path(cfg.home))
        self.wlock = FileLock(writer_lock_path(cfg.home, cfg.repo))
        self.sig, self.last_hb, self.noted, self.last_idle = False, 0.0, {}, 0.0
        self.gate_at, self.gate_val = 0.0, None

    def note(self, key, kind, **detail):
        """Log a recurring condition once until it changes."""
        if self.noted.get(kind) != key:
            self.noted[kind] = key
            self.store.event(kind, reason=key, **detail)

    # --- lifecycle
    def gate(self):
        """host_problem, memoized for a second so one scheduling pass costs one process-table read, not one per task."""
        now = time.monotonic()
        if self.gate_val is None or now - self.gate_at > 1.0:
            self.gate_val, self.gate_at = (host_problem(self.cfg) or ""), now
        return self.gate_val or None

    def run(self):
        if not self.cfg.cutover_proof_explicit:
            print("refusing to start: --cutover-proof is mandatory (a root-owned file outside the worker-writable trees)", file=sys.stderr)
            return EXIT_BOUNDARY
        problem = host_problem(self.cfg)  # before the lock, the state and the heartbeat: nothing is touched on a bad host
        if problem:
            print(f"refusing to start: {problem}", file=sys.stderr)
            return EXIT_BOUNDARY
        lstart = _lstart(os.getpid())  # published in the lock so the owner wrapper can tell this live runner from a stray
        if not lstart:
            print("refusing to start: cannot read this process's start time", file=sys.stderr)
            return EXIT_BOUNDARY
        if not self.rlock.acquire({"pid": os.getpid(), "lstart": lstart, "host": socket.gethostname()}):
            print(f"another runner holds the lock: {self.rlock.owner()}", file=sys.stderr)
            return EXIT_LOCKED
        try:
            with self.store.txn() as st:
                st["runner"] = {"pid": os.getpid(), "host": socket.gethostname(), "started_at": now_iso(),
                                "heartbeat_at": now_iso(), "claude_bin": self.cfg.claude_bin, "repo": str(self.cfg.repo),
                                "orchestrator_bin": self.cfg.orchestrator_bin}
        except StateCorrupt as e:
            print(f"refusing to start, state unreadable: {e}", file=sys.stderr)
            self.rlock.release()
            return EXIT_CORRUPT
        for s in (signal.SIGTERM, signal.SIGINT):
            signal.signal(s, lambda *_: setattr(self, "sig", True))
        self.store.event("runner-start", pid=os.getpid())
        try:
            while not self.sig and self.tick():
                time.sleep(self.cfg.tick)
        except StateCorrupt as e:
            print(f"state unreadable, runner exiting: {e}", file=sys.stderr)
            return EXIT_CORRUPT
        finally:
            with contextlib.suppress(Exception):
                with self.store.txn() as st:
                    (st.get("runner") or {}).update(stopped_at=now_iso())
            self.store.event("runner-exit", pid=os.getpid())
            self.rlock.release()
        return 0

    def beat(self):
        """Refresh the heartbeat. Called from tick AND from every blocking wait (agent child, verifier, planner turn), so
        a busy runner never looks stale and no second scheduler/thread is needed."""
        now = time.time()
        if now - self.last_hb >= HEARTBEAT_S:
            self.last_hb = now
            with self.store.txn() as st:
                (st["runner"] or {})["heartbeat_at"] = now_iso()

    def tick(self):
        """One scheduling step. Returns False when the runner should exit (control STOP)."""
        self.beat()
        st = self.store.load()
        if st["control"] == "STOP":
            return False
        if st.get("escaped"):  # processes that left the agent's process group: no dispatch until a FRESH rescan is clean
            baseline = st.get("escaped_baseline")
            if baseline is None:  # no stored baseline (pre-upgrade, or a crash record predating L-a): exact-pid liveness,
                # but still allowlist-aware - a pinned root-owned daemon must not wedge this forever either.
                alive = [e for e in st["escaped"] if " ".join(_lstart(e["pid"]).split()) == e["lstart"]
                         and not escape_allowlisted(Proc(e["pid"], 0, os.geteuid(), e["lstart"], e["command"]), self.cfg)]
                if alive:
                    if self.wlock.fd is None and not self.wlock.acquire({"runner_pid": os.getpid(), "task_id": "escaped-process"}):
                        self.note("writer lock held", "recovery-waiting")  # another holder: still no dispatch from here
                    return self.note(str([e["pid"] for e in alive]), "escaped-process", pids=[e["pid"] for e in alive]) or True
            else:
                # Rescanning against the ORIGINAL baseline (not just checking whether the previously-recorded pids are
                # still alive) is what catches a pid-hopping descendant: a re-fork gets a new pid absent from `baseline`
                # and is still outside the runner's own family, so it is reported as escaped under its new pid too.
                current = new_worker_procs(baseline, cfg=self.cfg)
                if current is None:  # host unreadable: not provable clean, never cleared on an assumption
                    if self.wlock.fd is None and not self.wlock.acquire({"runner_pid": os.getpid(), "task_id": "escaped-process"}):
                        self.note("writer lock held", "recovery-waiting")
                    return self.note("unreadable", "escaped-process", pids=[e["pid"] for e in st["escaped"]]) or True
                if current:
                    rows = [{"pid": p.pid, "lstart": p.lstart, "command": p.command.split()[0].rsplit("/", 1)[-1][:60]}
                            for p in current[:20]]
                    if rows != st["escaped"]:  # keep the recorded/dashboard-visible rows current as a hopper's pid changes
                        with self.store.txn() as cur:
                            cur["escaped"] = rows
                    if self.wlock.fd is None and not self.wlock.acquire({"runner_pid": os.getpid(), "task_id": "escaped-process"}):
                        self.note("writer lock held", "recovery-waiting")  # another holder: still no dispatch from here
                    return self.note(str([r["pid"] for r in rows]), "escaped-process", pids=[r["pid"] for r in rows]) or True
            # Reached only once a fresh scan is clean (every remaining process is either gone or allowlisted). An
            # `escape_ack_requested` marker (acknowledge_escaped, a separate CLI invocation) never forces this branch
            # by itself - it is only ever attributed on the audit event once the SAME fresh-scan-is-clean gate the
            # automatic path already uses has passed.
            ack = (st.get("escape_ack_requested") or {}).get("operator")
            self.store.event("escape-cleared", pids=[e["pid"] for e in st["escaped"]], acknowledged_by=ack)
            with self.store.txn() as cur:
                cur.pop("escaped", None)
                cur.pop("escaped_baseline", None)
                cur.pop("escape_ack_requested", None)
            self.wlock.release()  # held (by this runner) only while a recorded escapee lived
            self.noted.pop("escaped-process", None)
        if st.get("orphan_pgid"):  # a process group that would not die: no dispatch until it is gone
            if not kill_group(st["orphan_pgid"], wait=2.0):
                return self.note(str(st["orphan_pgid"]), "orphan-group", pgid=st["orphan_pgid"]) or True
            with self.store.txn() as cur:
                cur.pop("orphan_pgid", None)
        if not self.reconcile(st):
            return True  # a RUNNING record is still owned by a live orphan child, or the writer lock is busy
        st = self.store.load()
        self.handoff_recover(st)  # an open request can only be left by a dead runner
        if st["control"] != "RUN":
            return True
        tid = self.next_task(st)
        if tid:
            self.execute(tid)
        else:
            self.handoff_idle(self.store.load())
        return True

    # --- scheduling
    def waiting_reason(self, st, t, contamination=None):
        for d in t["depends_on"]:
            dep = st["tasks"].get(d)
            if not dep or dep["status"] != "COMPLETED":
                return f"waiting for {d} ({dep['status'] if dep else 'missing'})"
        if not sandbox_ready(self.cfg):  # fail closed on dispatch only; enqueue, status, cancel and heartbeat carry on
            return f"agent dispatch refused: {SANDBOX_EXEC} (mandatory OS confinement) unavailable on this host"
        problem = self.gate() or cli_problem(self.cfg)
        if problem:
            return f"agent dispatch refused: {problem}"
        if contamination is None:
            contamination = instruction_contamination(self.cfg.repo)
        if contamination:  # refuses EVERY role, including review: a later session must never auto-load these as trusted
            return (f"agent dispatch refused: untrusted project-instruction path(s) in the worktree "
                    f"({', '.join(contamination[:3])}); remove or restore them before any task, including review, may dispatch")
        if t["role"] in WRITE_ROLES and self.cfg.module_order:
            for m in load_catalog(self.cfg.repo):
                if m.get("id") == t["module"]:
                    for dep_module in m.get("dependencies", []):
                        why = prereq_problem(self.cfg.repo, dep_module, self.cfg)  # committed HEAD, never the worktree
                        if why:
                            return why
        if t["role"] in WRITE_ROLES:
            return self.unresolved_dirt(st, t)
        return None

    def unresolved_dirt(self, st, t):
        """A failed task's changes stay in the worktree. Until each such path is restored/committed/changed again, or the
        task being dispatched is an explicitly linked remediation covering it, no write task may run on top of them."""
        fixed = {o.get("remediates") for o in st["tasks"].values() if o["status"] == "COMPLETED"}
        failed = {i: {c["path"]: c.get("sha256") for c in (f.get("evidence") or {}).get("changed", [])}
                  for i, f in st["tasks"].items() if f["status"] == "FAILED" and i not in fixed and i != t.get("remediates")}
        failed = {i: paths for i, paths in failed.items() if paths}
        if not failed and not t.get("remediates"):
            return None
        try:
            dirty = repo_state(self.cfg.repo)["files"]
        except (OSError, subprocess.SubprocessError):
            return "repo state unreadable"
        for i, paths in sorted(failed.items()):
            stuck = sorted(p for p, h in paths.items() if p in dirty and dirty[p] == h)
            if stuck:
                return f"unresolved changes from failed task {i} ({', '.join(stuck[:3])}); restore them or enqueue a task with remediates={i}"
        rem = st["tasks"].get(t.get("remediates") or "")
        if rem:
            stuck = [c["path"] for c in (rem.get("evidence") or {}).get("changed", [])
                     if dirty.get(c["path"]) == c.get("sha256") and not in_scope(c["path"], t["allowed_paths"])]
            if stuck:
                return f"remediation of {rem['id']} must cover its dirty paths ({', '.join(stuck[:3])})"
        return None

    def next_task(self, st):
        """First eligible PENDING task (FIFO); records why the others wait so the dashboard can say so."""
        now, pick, waiting, contamination = time.time(), None, {}, None
        for t in sorted(st["tasks"].values(), key=lambda x: x["seq"]):
            if t["status"] != "PENDING":
                continue
            dead = next((d for d in t["depends_on"] if st["tasks"].get(d, {}).get("status") in ("FAILED", "CANCELLED")), None)
            if dead:  # a dependency that can never complete: fail now instead of waiting forever
                self.finish(t["id"], "FAILED", "DEPENDENCY_FAILED", f"{dead} is {st['tasks'][dead]['status']}; this task can never run")
                continue
            if contamination is None:  # one walk per next_task call, not one per candidate task
                contamination = instruction_contamination(self.cfg.repo)
            why = self.waiting_reason(st, t, contamination)
            if why is None and t["next_attempt_at"] > now:
                why = "retry backoff"
            waiting[t["id"]] = None if why is None or why == "retry backoff" else why
            if why is None and pick is None:
                pick = t["id"]
        if any(st["tasks"][i].get("waiting") != w for i, w in waiting.items()):
            with self.store.txn() as cur:
                for i, w in waiting.items():
                    if cur["tasks"][i]["status"] == "PENDING":
                        cur["tasks"][i]["waiting"] = w
        return pick

    # --- crash reconciliation
    def reconcile(self, st):
        """Settle RUNNING records left by a dead runner. Never replays a write: only an untouched repo is re-queued."""
        running = [t for t in st["tasks"].values() if t["status"] == "RUNNING"]
        if not running:
            return True
        for t in running:  # an orphaned agent group (incl. anything it backgrounded) must be dead before we judge the repo
            if not reap_recorded(t.get("child")):
                self.note("orphan process group", "recovery-waiting")
                return False
        if not self.wlock.acquire({"runner_pid": os.getpid(), "task_id": "reconcile"}):
            self.note("writer lock held", "recovery-waiting")  # a surviving child (or another writer) still owns the repo
            return False
        strays = self.crash_strays(running)
        if strays is None or strays:
            if strays is None:  # not provable is never 'clean': keep the lock and the RUNNING record, retry next tick
                self.note("process table unreadable or no start-time evidence", "recovery-waiting")
                self.wlock.release()
                return False
            rows = [{"pid": p.pid, "lstart": p.lstart, "command": p.command.split()[0].rsplit("/", 1)[-1][:60]} for p in strays[:20]]
            # L-a: store the baseline here too, when every running record carries one, so tick()'s rescan uses the
            # same pid-hopper-proof original-baseline logic as a live-turn escape instead of falling back to the
            # weaker exact-pid-liveness path (which this crash-recovery write used to leave as the only option).
            baseline = ([list(p) for t in running for p in t["proc_before"]]
                        if all(isinstance(t.get("proc_before"), list) for t in running) else None)
            with self.store.txn() as cur:
                cur["escaped"] = rows
                if baseline is not None:
                    cur["escaped_baseline"] = baseline
            self.store.event("escaped-process", task_id=",".join(t["id"] for t in running), pids=[r["pid"] for r in rows],
                             source="crash-recovery")
            return False  # the writer lock stays held (tick releases it once every recorded process is gone); nothing is killed
        try:
            try:
                now_state = repo_state(self.cfg.repo)
            except (OSError, subprocess.SubprocessError):
                self.note("repo state unreadable", "recovery-waiting")
                return False
            for t in running:
                before = t.get("repo_before")
                changed = diff_state(before, now_state) if before else ["?"]
                head_before = (before or {}).get("head")
                moved = bool(before) and head_before != now_state["head"]  # a commit leaves a clean tree: HEAD is evidence too
                evidence = {"changed": [{"path": p, "sha256": now_state["files"].get(p)} for p in changed if p != "?"],
                            "head_before": head_before, "head": now_state["head"]}
                if moved:
                    self.finish(t["id"], "FAILED", "CRASH_HEAD_MOVED",
                                f"runner died after HEAD moved {str(head_before)[:12]} -> {str(now_state['head'])[:12]}"
                                f" ({len(changed)} dirty path(s)); never replayed", evidence=evidence)
                elif t["cancel_requested"]:
                    self.finish(t["id"], "CANCELLED", "CANCELLED", "cancelled while the runner was down", evidence=evidence)
                elif changed:
                    self.finish(t["id"], "FAILED", "CRASH_PARTIAL_WRITE",
                                f"runner died mid-task with {len(changed)} repo change(s); not replayed", evidence=evidence)
                elif t["attempts"] >= t["max_attempts"]:
                    self.finish(t["id"], "FAILED", "CRASH_RETRIES_EXHAUSTED", "runner died; attempts exhausted")
                else:
                    self.requeue(t["id"], "RUNNER_CRASH", "runner died before any repo change; re-queued", delay=0)
                self.store.event("recovered", task_id=t["id"], changed=len(changed))
        finally:
            self.wlock.release()
        return True

    def crash_strays(self, running):
        """Worker-account processes that appeared after a crashed task was dispatched and are not this runner's family. The
        agent's process group is already dead, so such a process escaped it (setsid, double fork). They are only DETECTED here:
        unattributable, never killed. None when that cannot be established. A worker process the operator starts while a task is
        RUNNING also matches (halting is the safe error); dispatch resumes when every listed pid is gone."""
        table = process_table()
        if table is None:
            return None
        found = {}
        for t in running:
            base = t.get("proc_before")
            if isinstance(base, list):
                cand = new_worker_procs(base, table, cfg=self.cfg)
            else:  # a record without a baseline: fall back to everything started since the agent child did
                since = _parse_lstart((t.get("child") or {}).get("lstart"))
                if since is None:
                    return None
                cand = [p for p in new_worker_procs([], table, cfg=self.cfg) if (_parse_lstart(p.lstart) or 0) >= since]
            for p in cand or ():
                found[(p.pid, p.lstart)] = p
        return list(found.values())

    # --- state transitions
    def requeue(self, tid, reason, detail, delay):
        with self.store.txn() as st:
            st["tasks"][tid].update(status="PENDING", reason=reason, last_error=detail, child=None, stage=None,
                                    repo_before=None, proc_before=None, next_attempt_at=time.time() + delay, updated_at=now_iso())
        self.store.event("task-retry", task_id=tid, reason=reason, delay_s=round(delay))

    def finish(self, tid, status, reason, detail=None, evidence=None, route=None, result=None, usage=None):
        with self.store.txn() as st:
            t = st["tasks"][tid]
            t.update(status=status, reason=None if status == "COMPLETED" else reason, last_error=detail, child=None,
                     stage=None, repo_before=None, proc_before=None, finished_at=now_iso(), updated_at=now_iso(), waiting=None)
            for key, val in (("evidence", evidence), ("route", route), ("result", result)):
                if val is not None:
                    t[key] = val
            for model, u in ((m, u) for m, u in (usage or {}).items() if isinstance(u, dict)):
                acc = st["usage"].setdefault(model, {"runs": 0, "input": 0, "output": 0, "cache": 0, "cost_usd": 0.0})
                acc["runs"] += 1
                acc["input"] += _n(u.get("inputTokens"))
                acc["output"] += _n(u.get("outputTokens"))
                acc["cache"] += _n(u.get("cacheReadInputTokens")) + _n(u.get("cacheCreationInputTokens"))
                acc["cost_usd"] += _n(u.get("costUSD"))
        kind = {"COMPLETED": "task-done", "FAILED": "task-failed", "CANCELLED": "task-cancelled"}[status]
        self.store.event(kind, task_id=tid, reason=reason if status != "COMPLETED" else None)

    def fail_or_retry(self, t, reason, detail, transient, changed, **kw):
        if transient and changed:
            return self.finish(t["id"], "FAILED", "PARTIAL_WRITE_NO_REPLAY", f"{reason}: {detail}; the child changed the repo, not replayed", **kw)
        if transient and t["attempts"] < t["max_attempts"]:
            delay = min(self.cfg.backoff_cap, self.cfg.backoff_base * 2 ** (t["attempts"] - 1))
            return self.requeue(t["id"], reason, detail, delay)
        self.finish(t["id"], "FAILED", reason + ("_EXHAUSTED" if transient else ""), detail, **kw)

    # --- execution
    def execute(self, tid):
        if not self.wlock.acquire({"runner_pid": os.getpid(), "task_id": tid}):
            self.note("writer lock held", "dispatch-waiting", task_id=tid)
            return
        try:
            self._execute(tid)
        finally:
            self.wlock.release()

    def _execute(self, tid):
        cfg = self.cfg
        t = self.store.load()["tasks"][tid]
        if t["role"] in REVIEW_ROLES:
            subject = (self.store.load()["tasks"][t["review_of"]].get("evidence") or {}).get("changed", [])
            if not subject:
                return self.finish(tid, "FAILED", "REVIEW_NO_SUBJECT", "the reviewed task recorded no changed files")
            if not subjects_current(cfg.repo, subject):
                return self.finish(tid, "FAILED", "REVIEW_SUBJECT_CHANGED", "reviewed files changed since the write task finished")
        try:
            before = repo_state(cfg.repo)
        except (OSError, subprocess.SubprocessError) as e:
            return self.note(type(e).__name__, "dispatch-waiting", task_id=tid)  # repo unreadable: nothing started
        problem = host_problem(cfg)  # fresh, not the tick's memo: the boundary must hold at the moment of launch
        if problem:
            return self.note(problem[:200], "dispatch-refused", task_id=tid)
        baseline = process_table()  # worker-account processes before the turn; whatever is new afterwards escaped the group
        if baseline is None:
            return self.note("process table unreadable", "dispatch-refused", task_id=tid)
        proc_before = worker_procs(baseline)
        attempt = t["attempts"] + 1
        run_dir = cfg.home / "v2" / "runs" / f"{tid}-{attempt}"
        run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        prompt_path = run_dir / "prompt.txt"
        with self.store.txn() as st:
            st["tasks"][tid].update(status="RUNNING", attempts=attempt, started_at=now_iso(), updated_at=now_iso(),
                                    stage="agent", repo_before=before, proc_before=proc_before, waiting=None, last_error=None)
        t = self.store.load()["tasks"][tid]
        self.store.event("dispatch", task_id=tid, attempt=attempt, role=t["role"])
        alias = cfg.models[required_family(t["role"])]
        prompt = t["prompt"]
        if t["role"] in REVIEW_ROLES:
            subject = self.store.load()["tasks"][t["review_of"]]["evidence"]["changed"]
            prompt += ("\n\nIndependent review of task %s. Files under review (sha256):\n%s\nEnd your answer with exactly one "
                       "line: OUTCOME: APPROVED, OUTCOME: CHANGES_REQUESTED or OUTCOME: BLOCKED.\n"
                       % (t["review_of"], "\n".join(f"- {s['path']} {s['sha256']}" for s in subject)))
        atomic_write(prompt_path, prompt.encode())  # the CLI reads it on stdin from this file: no pipe, nothing in argv
        interrupt, rc, spawn_error, orphan, err_tail, escaped = None, None, None, False, bytearray(), []
        stream, unverified = CliStream(alias, cfg.max_turns), None
        try:
            real = verify_cli(cfg)  # protected install + capability probe, then the posture of this very turn
            settings = write_turn_settings(cfg, t["role"], real, run_dir / "settings.json")
            with open(prompt_path, "rb") as stdin:
                p = subprocess.Popen(child_argv(real, alias, settings), stdin=stdin, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, cwd=cfg.repo, start_new_session=True, env=child_env(),
                                     pass_fds=(self.wlock.fd,))  # inherits the writer lock
        except CliUnavailable as e:
            unverified = str(e)
        except (OSError, SandboxUnavailable) as e:
            spawn_error = f"{type(e).__name__}: {e}"
        if spawn_error is None and unverified is None:
            def drain_err():
                for chunk in iter(lambda: p.stderr.read(4096), b""):
                    err_tail[:] = (err_tail + chunk)[-ACP_ERR_TAIL:]
            pumps = [threading.Thread(target=stream.pump, args=(p.stdout,), daemon=True),
                     threading.Thread(target=drain_err, daemon=True)]
            for th in pumps:
                th.start()
            child = {"pid": p.pid, "pgid": p.pid, "lstart": _lstart(p.pid)}
            self.wlock.update({"child_pid": p.pid})
            with self.store.txn() as st:
                st["tasks"][tid]["child"] = child
            rc, interrupt = self.wait_child(p, tid, stream)
            orphan = not kill_group(p.pid)  # nothing the agent backgrounded may outlive it, or race the next writer
            for th in pumps:
                th.join(5)
            for f in (p.stdout, p.stderr):
                with contextlib.suppress(OSError):
                    f.close()
            escaped = new_worker_procs(proc_before, cfg=self.cfg)  # after the group is dead: anything new outside our family escaped it
            if stream.violation and not interrupt:
                interrupt = "violation"  # the exit raced the wait loop's check
            summary = {"rc": rc, "events": stream.events, "bad_lines": stream.bad, "dropped_lines": stream.dropped,
                       "stop_reason": stream.stop, "primary_model": stream.primary, "posture_verified": stream.init_ok,
                       "model_usage": stream.model_usage(), "error": stream.error, "text_chars": stream.text_len,
                       "tool_calls": stream.tool_calls, "tool_results": stream.tool_results,
                       "tool_errors": stream.tool_errors, "permission_denials": stream.denials,
                       "violation": stream.violation and stream.violation[0]}  # counts and names only: no inputs, no output
            atomic_write(run_dir / "cli.json", json.dumps(summary).encode())
            (run_dir / "stderr.txt").write_bytes(bytes(err_tail))
        try:
            after = repo_state(cfg.repo)
        except (OSError, subprocess.SubprocessError) as e:
            return self.finish(tid, "FAILED", "REPO_STATE_UNREADABLE", type(e).__name__)
        changed = diff_state(before, after)
        head_moved = after["head"] != before["head"]
        wrote = bool(changed) or head_moved  # any repo effect at all (a commit can leave the tree clean)
        evidence = {"changed": [{"path": p, "sha256": after["files"].get(p)} for p in changed], "head": after["head"],
                    "head_before": before["head"], "run_dir": str(run_dir.relative_to(cfg.home))}
        if orphan:
            with self.store.txn() as st:
                st["orphan_pgid"] = p.pid
            return self.finish(tid, "FAILED", "ORPHAN_PROCESS_GROUP", "agent descendants survived SIGKILL; dispatch halted", evidence=evidence)
        if escaped is None or escaped:
            return self.halt_escaped(tid, escaped, proc_before, evidence=evidence)
        t = self.store.load()["tasks"][tid]  # fresh attempts/cancel flag
        if interrupt == "cancel" or (t["cancel_requested"] and interrupt):
            return self.finish(tid, "CANCELLED", "CANCELLED", "cancelled by owner", evidence=evidence)
        if interrupt == "stop":
            if wrote:
                return self.finish(tid, "FAILED", "INTERRUPTED_PARTIAL_WRITE", "runner stopped mid-task after repo changes", evidence=evidence)
            with self.store.txn() as st:
                st["tasks"][tid]["attempts"] -= 1  # a stop is not a failed attempt
            return self.requeue(tid, "RUNNER_STOPPED", "runner stopped before any repo change", 0)
        kw = {"evidence": evidence}
        if unverified:  # fail closed and never retry: the posture will not improve by itself
            return self.finish(tid, "FAILED", "SANDBOX_POSTURE_UNVERIFIED", unverified[:300], **kw)
        if spawn_error:
            return self.fail_or_retry(t, "AGENT_SPAWN_FAILED", spawn_error, True, wrote, **kw)
        if interrupt == "violation":
            code, detail = stream.violation
            kw.update(route=judge_route(t["role"], stream, alias), usage=stream.model_usage())  # recorded, never hidden
            return self.finish(tid, "FAILED", code, detail, **kw)
        if interrupt == "timeout":
            return self.fail_or_retry(t, "AGENT_TIMEOUT", f"no result within {cfg.timeout:.0f}s", True, wrote, **kw)
        text, final = stream.message(), stream.final
        if rc != 0 or not isinstance(final, dict):
            err = stream.error or bytes(err_tail).decode(errors="replace").strip()
            return self.fail_or_retry(t, "AGENT_FAILED", f"exit {rc}; {err}"[:400], not AUTH_RE.search(err), wrote, **kw)
        usage = stream.model_usage()
        route = judge_route(t["role"], stream, alias)
        kw.update(route=route, usage=usage, result={"text": text[:2000], "session_id": stream.session_id,
                                                    "stop_reason": stream.stop, "permission_denied": bool(stream.denials),
                                                    "tool_calls": stream.tool_calls, "tool_errors": stream.tool_errors})
        if not stream.init_ok:  # the CLI never proved its tool set / mode: nothing it did can be trusted
            return self.finish(tid, "FAILED", "SANDBOX_POSTURE_UNVERIFIED", "no valid system/init event from the agent CLI", **kw)
        if stream.stop != "end_turn":
            return self.fail_or_retry(t, "AGENT_ERROR", f"stop {stream.stop}; {text[-250:]}", False, wrote, **kw)
        if route["verdict"] != "VERIFIED":
            return self.finish(tid, "FAILED", f"MODEL_{route['verdict']}", route["basis"], **kw)
        if t["role"] in REVIEW_ROLES:
            if wrote:
                return self.finish(tid, "FAILED", "REVIEW_WROTE_FILES",
                                   f"read-only review changed {changed}" + (" and moved HEAD" if head_moved else ""), **kw)
            subject = self.store.load()["tasks"][t["review_of"]]["evidence"]["changed"]
            if not subjects_current(cfg.repo, subject):
                return self.finish(tid, "FAILED", "REVIEW_SUBJECT_CHANGED", "reviewed files changed during the review", **kw)
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            m = OUTCOME_RE.match(lines[-1]) if lines else None
            if not m:
                return self.finish(tid, "FAILED", "REVIEW_NO_OUTCOME", "review did not end with an OUTCOME line", **kw)
            evidence.update(review_outcome=m.group(1), review_of=t["review_of"], subject=subject)
            if m.group(1) != "APPROVED":
                return self.finish(tid, "FAILED", f"REVIEW_{m.group(1)}", text[-300:], **kw)
        else:
            out_of_scope = [p for p in changed if not in_scope(p, t["allowed_paths"])]
            if out_of_scope:
                return self.finish(tid, "FAILED", "SCOPE_VIOLATION", f"changed outside allowed_paths: {out_of_scope}", **kw)
            if head_moved:
                return self.finish(tid, "FAILED", "HEAD_MOVED", "the agent child moved HEAD", **kw)
        if t["verify_cmd"]:
            with self.store.txn() as st:
                st["tasks"][tid]["stage"] = "verifying"
            try:
                evidence["verify"] = self.verify(t, run_dir)
            except SandboxUnavailable as e:
                evidence["verify"] = {"argv": t["verify_cmd"], "exit": -1, "tail": f"verification refused: {e}"[:300]}
                return self.finish(tid, "FAILED", "VERIFY_SANDBOX_UNAVAILABLE", str(e)[:300], **kw)
            escaped = new_worker_procs(proc_before, cfg=self.cfg)  # a verifier descendant that left its group is just as disqualifying
            if escaped is None or escaped:
                return self.halt_escaped(tid, escaped, proc_before, **kw)
            try:
                post = repo_state(cfg.repo)
            except (OSError, subprocess.SubprocessError) as e:
                return self.finish(tid, "FAILED", "REPO_STATE_UNREADABLE", type(e).__name__, **kw)
            if post["head"] != after["head"] or diff_state(after, post):  # a verifier is read-only: any effect fails the task
                evidence["changed"] = [{"path": p, "sha256": post["files"].get(p)} for p in diff_state(before, post)]
                evidence["head"] = post["head"]
                return self.finish(tid, "FAILED", "VERIFY_MUTATED_REPO",
                                   f"verifier changed {diff_state(after, post)[:5]}" + (" and moved HEAD" if post["head"] != after["head"] else ""), **kw)
            if evidence["verify"]["exit"] != 0:
                return self.finish(tid, "FAILED", "VERIFY_FAILED", f"verify exit {evidence['verify']['exit']}", **kw)
        self.finish(tid, "COMPLETED", None, None, **kw)

    def halt_escaped(self, tid, escaped, proc_before, **kw):
        """Fail the task and halt dispatch. Escaped descendants are NOT killed: they cannot be proven to be the agent's, and
        killing by guess could hit unrelated worker processes. Dispatch resumes only when a FRESH rescan of `proc_before`
        (not just the recorded pids - see tick) is clean, so a pid-hopping descendant cannot outlive clearance and no
        later task's diff or review subject can be changed behind the runner's back."""
        if escaped is None:
            return self.finish(tid, "FAILED", "PROCESS_SCAN_UNAVAILABLE",
                               "the host process table could not be read after the turn; escaped descendants cannot be ruled out", **kw)
        rows = [{"pid": p.pid, "lstart": p.lstart, "command": p.command.split()[0].rsplit("/", 1)[-1][:60]} for p in escaped[:20]]
        with self.store.txn() as st:
            st["escaped"] = rows
            st["escaped_baseline"] = [list(p) for p in proc_before]
        self.store.event("escaped-process", task_id=tid, pids=[r["pid"] for r in rows])
        return self.finish(tid, "FAILED", "ESCAPED_PROCESS",
                           f"{len(escaped)} new worker-account process(es) {[r['pid'] for r in rows[:5]]} outlived the agent turn "
                           "outside its process group (setsid/double fork); not killed (unattributable); dispatch halted until "
                           "they exit", **kw)

    def wait_child(self, p, tid, stream):
        deadline, interrupt = time.monotonic() + self.cfg.timeout, None
        while True:
            try:
                return p.wait(timeout=0.5), None
            except subprocess.TimeoutExpired:
                pass
            self.beat()
            peek = self.store.load()
            if self.sig or peek["control"] == "STOP":
                interrupt = "stop"
            if peek["tasks"][tid]["cancel_requested"]:
                interrupt = "cancel"
            if time.monotonic() > deadline:
                interrupt = interrupt or "timeout"
            if stream.violation:  # wrong model, extra tool, bad init or turn cap: stop spending and acting at once
                interrupt = interrupt or "violation"
            if interrupt:
                with contextlib.suppress(OSError):
                    os.killpg(p.pid, signal.SIGTERM)
                try:
                    return p.wait(timeout=5), interrupt
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(OSError):
                        os.killpg(p.pid, signal.SIGKILL)
                    return p.wait(), interrupt

    def verify(self, t, run_dir):
        """Run the task's verify argv (no shell) in the repo under mandatory read-only OS confinement: no network, no
        writes except a private tmpdir. Product tests failing blocks completion; the caller re-checks repo state and HEAD.
        The verifier's own sandbox denies it writes everywhere but its scratch dir, including through an fd inherited
        from us, so its stdout/stderr go to a pipe; only the unsandboxed parent writes verify.log."""
        start, tmp = time.monotonic(), tempfile.mkdtemp(prefix="veyro-verify-")
        out, stop, pumped = bytearray(), threading.Event(), threading.Event()
        try:
            argv = confine_verifier(self.cfg, run_dir / "verify.sb", tmp, t["verify_cmd"]) + t["verify_cmd"]
            with open(run_dir / "verify.log", "wb") as log:
                try:
                    p = subprocess.Popen(argv, cwd=self.cfg.repo, env={**child_env(), "TMPDIR": tmp}, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
                except OSError as e:
                    log.write(str(e).encode())
                    out[:] = str(e).encode()[-VERIFY_OUT_MAX:]
                    p = None
                if p is not None:
                    def pump():
                        # Polls in short slices (never a flat blocking read) so `stop` can always end the loop between
                        # slices; only then is closing p.stdout below guaranteed not to race a read still in flight,
                        # which on this OS blocks the close itself until the read unblocks - exactly what `stop` must prevent.
                        try:
                            while not stop.is_set():
                                ready, _, _ = select.select([p.stdout], [], [], 0.5)
                                if not ready:
                                    continue
                                chunk = os.read(p.stdout.fileno(), 65536)
                                if not chunk:
                                    break
                                log.write(chunk)
                                out[:] = (out + chunk)[-VERIFY_OUT_MAX:]
                        except (OSError, ValueError):
                            pass
                        finally:
                            pumped.set()
                    pump_thread = threading.Thread(target=pump, daemon=True)
                    pump_thread.start()
                exit_code, deadline = 127, time.monotonic() + self.cfg.verify_timeout
                while p is not None:
                    try:
                        exit_code = p.wait(timeout=0.5)
                        break
                    except subprocess.TimeoutExpired:
                        self.beat()
                    if time.monotonic() > deadline:
                        kill_group(p.pid)
                        p.wait()
                        exit_code = None
                        break
                if p is not None:
                    kill_group(p.pid)  # nothing the verifier backgrounded outlives it
                    pumped.wait(timeout=5)  # drain whatever already arrived; an escaped descendant wedged on the pipe must not block us
                    stop.set()  # force the loop to end even if it never saw EOF, before we touch the fd it polls
                    pump_thread.join(timeout=2)
                    with contextlib.suppress(OSError):
                        p.stdout.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {"argv": t["verify_cmd"], "exit": exit_code, "duration_s": round(time.monotonic() - start, 1),
                "sandboxed": self.cfg.sandbox != "off", "tail": bytes(out)[-1500:].decode(errors="replace")}

    # --- automatic OpenClaw handoff: the runner is only the trigger; OpenClaw chooses the next legal task
    def handoff_fingerprint(self, st):
        """Meaningful state: task lifecycle + repo HEAD + every owner-side input the planner judges by."""
        cfg = self.cfg
        try:
            head = git_run(cfg.repo, "rev-parse", "--verify", "-q", "HEAD").stdout.strip().decode()
        except (OSError, subprocess.SubprocessError):
            head = None
        records = sorted(head_files(cfg.repo, "knowledge/03-Modules/").items())  # COMMITTED blobs only: no worktree symlink/FIFO read
        life = sorted((t["id"], t["status"], t["attempts"], t.get("reason")) for t in st["tasks"].values())
        catalog_sha = head_files(cfg.repo, "tools/mission_runner/module_catalog.json").get(
            "tools/mission_runner/module_catalog.json")
        owner = [records, catalog_sha,
                 _digest(openclaw_config_path(cfg.openclaw_config))]
        return hashlib.sha256(json.dumps([life, head, owner]).encode()).hexdigest()

    def handoff_idle(self, st):
        """No eligible task. Ask OpenClaw once per distinct state; never loop on an answered or failing state."""
        cfg, now = self.cfg, time.time()
        if not HANDOFF_ENABLED:  # production: inert, with an explicit recorded blocker (see HANDOFF_BLOCKER)
            if cfg.orchestrator_bin:
                self.note(HANDOFF_BLOCKER, "handoff-disabled")
            return
        if not cfg.orchestrator_bin or now - self.last_idle < cfg.handoff_poll:
            return
        self.last_idle = now
        if any(t["status"] == "RUNNING" or (t["status"] == "PENDING" and self.waiting_reason(st, t) is None)
               for t in st["tasks"].values()):
            return  # work in progress or a task in retry backoff: not idle
        h, fp = st.get("handoff") or {}, self.handoff_fingerprint(st)
        run = handoff_failure_run(st["tasks"])
        if run >= HANDOFF_MAX_CONSEC_FAILS:  # no planning call at all: the owner decides after repeated handoff failures
            if h.get("status") != "waiting_for_owner" or h.get("fingerprint") != fp:
                with self.store.txn() as cur:
                    self.handoff_update(cur, status="waiting_for_owner", settled=True, fingerprint=fp,
                                        detail=f"HANDOFF_FAILURE_BACKSTOP: {run} consecutive handoff-sourced tasks FAILED; owner review required")
                self.store.event("handoff-backstop", failed_in_a_row=run)
            return
        if fp == h.get("fingerprint") and (h.get("settled") or now < h.get("retry_at", 0)):
            return  # this exact state was already handed off
        if now < h.get("next_at", 0):
            return  # global cooldown between planning calls
        if not self.wlock.acquire({"runner_pid": os.getpid(), "task_id": "handoff"}):
            return self.note("writer lock held", "handoff-waiting")
        try:
            self.handoff_run(fp)
        finally:
            self.wlock.release()

    def handoff_update(self, st, **kw):
        h = st.setdefault("handoff", {"status": "idle", "detail": "no planning call yet", "fingerprint": None,
                                      "settled": True, "tries": 0, "seq": 0, "request": None, "outcome": None, "last": None})
        h.update(kw, updated_at=now_iso())
        return h

    def handoff_run(self, fp):
        cfg = self.cfg
        try:
            pre = repo_state(cfg.repo)  # lets settle prove the read-only turn wrote nothing
        except (OSError, subprocess.SubprocessError) as e:
            return self.note(type(e).__name__, "handoff-waiting")
        with self.store.txn() as st:
            h = self.handoff_update(st)
            tries = h["tries"] + 1 if h["fingerprint"] == fp else 1
            seq = h["seq"] + 1
            req_id = f"handoff-{fp[:12]}-{seq}"
            stem = cfg.home / "v2" / "runs" / req_id
            req = {"id": req_id, "fingerprint": fp, "started_at": now_iso(), "msg": str(stem) + ".msg.md",
                   "out": str(stem) + ".out", "err": str(stem) + ".err", "child": None, "pre": pre}
            summary = ", ".join(f"{i}:{t['status']}" + (f"({t['reason']})" if t.get("reason") else "")
                                for i, t in sorted(st["tasks"].items()))[:1500] or "no tasks recorded"
            atomic_write(Path(req["msg"]), handoff_prompt(cfg, req_id, summary, (h.get("outcome") or {}).get("detail")).encode())
            self.handoff_update(st, fingerprint=fp, settled=False, tries=tries, seq=seq, request=req, status="coordinating",
                                detail=f"planning turn {req_id} in flight")
            h.pop("retry_at", None)
        self.store.event("handoff-request", req_id=req_id, fingerprint=fp[:12], tries=tries)  # durable before the CLI exists
        blocker = planner_policy_blocker(cfg.openclaw_config)
        if blocker:
            return self.handoff_settle(req, "policy-refused", None, blocker)
        try:
            prefix = confine_planner(cfg, Path(req["msg"]).with_suffix(".sb"))
        except SandboxUnavailable as e:
            return self.handoff_settle(req, "sandbox-refused", None, f"ORCHESTRATOR_SANDBOX_UNAVAILABLE: {e}"[:300])
        binpath = str(cfg.orchestrator_bin)
        env = {k: os.environ[k] for k in ORCH_ENV_KEEP if k in os.environ}
        env |= {k: v for k, v in os.environ.items() if k.startswith("OPENCLAW_")}
        env["PATH"] = f"{Path(binpath).parent}:/usr/bin:/bin:/usr/sbin:/sbin"  # node lives next to the CLI
        cmd = [binpath, "agent", "--agent", ORCH_AGENT, "--session-key", ORCH_SESSION, "--message-file", req["msg"],
               "--json", "--timeout", str(int(cfg.handoff_timeout))]
        with open(req["out"], "wb") as fo, open(req["err"], "wb") as fe:
            try:
                p = subprocess.Popen(prefix + cmd, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe, cwd=cfg.home,
                                     start_new_session=True, env=env)
            except OSError as e:
                return self.handoff_settle(req, "spawn-failed", None, f"spawn failed: {e}")
        req["child"] = {"pid": p.pid, "pgid": p.pid, "lstart": _lstart(p.pid)}
        with self.store.txn() as st:
            st["handoff"]["request"] = req
        deadline = time.monotonic() + cfg.handoff_timeout + 30
        while True:
            try:
                rc = p.wait(timeout=0.5)
                kill_group(p.pid)  # the CLI client leaves nothing running behind it
                return self.handoff_settle(req, "exited", rc, f"exit {rc}")
            except subprocess.TimeoutExpired:
                pass
            self.beat()
            why = None
            if self.sig or self.store.load()["control"] != "RUN":
                how, why = "paused", "runner control changed during the planning turn"  # owner wins; output never used
            elif time.monotonic() > deadline:
                how, why = "timeout", f"no result within {int(cfg.handoff_timeout)}s"
            if why:
                kill_group(p.pid)
                p.wait()
                return self.handoff_settle(req, how, None, why)

    def handoff_recover(self, st):
        """Runner died mid-turn: reap any orphan CLI and settle without ever using or repeating the lost turn blindly."""
        req = (st.get("handoff") or {}).get("request")
        if not req:
            return
        reap_recorded(req.get("child"))
        self.handoff_settle(req, "recovered", None, "planning turn interrupted by runner restart")

    def handoff_settle(self, req, how, rc, why):
        cfg, now = self.cfg, time.time()
        try:
            post = repo_state(cfg.repo) if req.get("pre") else None
            wrote = diff_state(req["pre"], post) if post else []
            moved = bool(post) and req["pre"]["head"] != post["head"]
        except (OSError, subprocess.SubprocessError):
            wrote, moved = ["<repo snapshot failed>"], False
        prop, bad = None, None
        if how == "exited" and rc == 0:
            try:
                prop = parse_handoff_proposal(parse_handoff_envelope(Path(req["out"]).read_bytes()), req["id"])
            except OSError:
                bad = "CLI output file unreadable"
            except HandoffError as e:
                bad = str(e)
        enqueued, transient = None, False
        with self.store.txn() as st:
            h = self.handoff_update(st)
            h["request"] = None
            if how == "paused":  # not an answer, not a failed try
                h.update(settled=False, tries=max(0, h["tries"] - 1))
                outcome = {"status": "waiting", "detail": why}
            elif how in ("policy-refused", "sandbox-refused"):
                outcome = {"status": "blocked", "detail": f"{why}; re-asked only when state or config changes"}
            elif how != "exited" or rc != 0:
                transient = True
                err = ""
                with contextlib.suppress(OSError):
                    err = Path(req["err"]).read_bytes()[-200:].decode(errors="replace").strip()
                outcome = {"status": "blocked", "detail": f"ORCHESTRATOR_{how.upper()}: {why}; {err}"}
            elif wrote or moved:
                outcome = {"status": "blocked", "detail": f"UNATTRIBUTED_CHANGES_DURING_HANDOFF: {wrote[:3]}; proposal discarded"}
            elif bad:
                transient = True
                outcome = {"status": "blocked", "detail": f"ORCHESTRATOR_RESPONSE_INVALID: {bad}"}
            elif prop["kind"] == "TASK" and handoff_failure_run(st["tasks"], prop["task"].get("module")) >= HANDOFF_MAX_CONSEC_FAILS:
                n = handoff_failure_run(st["tasks"], prop["task"].get("module"))
                outcome = {"status": "waiting_for_owner", "detail": f"HANDOFF_FAILURE_BACKSTOP: {n} consecutive handoff-sourced "
                           f"tasks for {prop['task'].get('module')} FAILED; no further proposal is enqueued without the owner"}
            elif prop["kind"] == "TASK":
                try:
                    problem = proposal_problem(cfg, prop["task"])
                    if problem:
                        raise ValueError(problem)
                    enqueued = add_task(st, prop["task"], cfg, source="handoff")["id"]
                    outcome = {"status": "waiting", "detail": f"enqueued {enqueued} from a validated proposal"}
                except ValueError as e:
                    outcome = {"status": "blocked", "detail": f"PROPOSAL_REFUSED: {e}"}
            else:
                status = {"BLOCKED": "blocked", "WAITING_FOR_OWNER": "waiting_for_owner", "NO_LEGAL_WORK": "idle"}[prop["kind"]]
                outcome = {"status": status, "detail": f"{prop['kind']}: {prop['reason'].strip()}"}
            outcome["detail"] = outcome["detail"][:300]
            if how != "paused":
                exhausted = transient and h["tries"] >= HANDOFF_TRIES
                if transient and not exhausted:  # bounded retry of the same state with exponential cooldown
                    h.update(settled=False, retry_at=now + cfg.handoff_cooldown * 2 ** (h["tries"] - 1))
                else:
                    h["settled"] = True  # an answered (or exhausted) state is never asked again
                    if exhausted:
                        outcome["detail"] = (outcome["detail"] + "; retries exhausted")[:300]
                h["next_at"] = now + cfg.handoff_cooldown
            h["last"] = {"id": req["id"], "finished_at": now_iso(), "how": how, "exit": rc,
                         "claim": prop["kind"] if prop else None, "new_tasks": [enqueued] if enqueued else []}
            self.handoff_update(st, outcome=outcome, status=outcome["status"], detail=outcome["detail"])
        self.store.event("handoff-result", req_id=req["id"], how=how, exit=rc, claim=h["last"]["claim"],
                         new_tasks=h["last"]["new_tasks"], outcome=outcome["detail"][:160])


# ------------------------------------------------------------------ read-only snapshot
LEGACY_KEYS = ("id", "module", "role", "title", "status", "blocked_reason", "last_error", "created_at", "started_at",
               "finished_at", "updated_at", "route", "evidence")


def legacy_tasks(cfg):
    """v1 history, read-only, from the pinned copy only. Never written, never executed (a v1 RUNNING record is history, not a
    task to replay). ([], reason) when the copy is missing or does not verify; the runner then refuses to start or dispatch."""
    try:
        data = legacy_state_tasks(cfg)
        return [{k: t.get(k) for k in LEGACY_KEYS} for t in data.values() if isinstance(t, dict)], None
    except ValueError as e:
        return [], f"legacy history unverified: {str(e)[:160]}"


def handoff_disabled_view():
    if HANDOFF_ENABLED:
        return None
    return {"status": "disabled", "detail": HANDOFF_BLOCKER, "settled": True, "tries": 0, "last": None, "updated_at": None,
            "next_at": None, "retry_at": None, "fingerprint": "", "request_open": False}


def handoff_view(h):
    if not h:
        return None
    return {k: h.get(k) for k in ("status", "detail", "settled", "tries", "last", "updated_at", "next_at", "retry_at")} | {
        "fingerprint": (h.get("fingerprint") or "")[:12], "request_open": bool(h.get("request"))}


def snapshot(cfg):
    """Read-only view for `status` and the dashboard; creates nothing."""
    store, now = Store(cfg.home, create=False), time.time()
    try:
        st, err = store.load(), None
    except StateCorrupt as e:
        st, err = Store.empty(), str(e)
    r = st.get("runner") or {}
    hb = None
    if r.get("heartbeat_at"):
        hb = now - datetime.datetime.fromisoformat(r["heartbeat_at"]).timestamp()
    alive = bool(r) and not r.get("stopped_at") and pid_alive(r.get("pid")) and hb is not None and hb < 10
    keys = ("id", "module", "role", "title", "status", "stage", "attempts", "max_attempts", "reason", "last_error",
            "waiting", "depends_on", "review_of", "allowed_paths", "verify_cmd", "route", "result", "evidence",
            "created_at", "started_at", "finished_at", "updated_at", "seq", "remediates")
    tasks = [{k: t.get(k) for k in keys} | {"child_pid": (t.get("child") or {}).get("pid"),
                                             "retry_in": max(0, round(t["next_attempt_at"] - now))
                                             if t["status"] == "PENDING" and t.get("next_attempt_at", 0) > now else None}
             for t in sorted(st["tasks"].values(), key=lambda x: x["seq"])]
    lp = writer_lock_path(cfg.home, cfg.repo)
    held = FileLock.probe(lp)
    owner = FileLock(lp).owner() if held == "held" else None
    legacy, legacy_err = legacy_tasks(cfg)
    return {"generated_at": now_iso(), "state_error": err, "runner_alive": alive, "heartbeat_age_s": hb,
            "runner": r or None, "control": st.get("control"), "tasks": tasks, "legacy_tasks": legacy,
            "legacy_error": legacy_err, "handoff": handoff_view(st.get("handoff")) or handoff_disabled_view(), "usage": st.get("usage", {}), "events": store.tail_events(200),
            "writer_lock": {"state": held, "owner": owner,
                            "runner_alive": pid_alive((owner or {}).get("runner_pid")) if owner else None,
                            "child_alive": pid_alive(owner["child_pid"]) if owner and owner.get("child_pid") else None}}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="runner.py", description=__doc__.splitlines()[0])
    ap.add_argument("--home", help="state dir (default: platform state dir or $VEYRO_RUNNER_HOME)")
    ap.add_argument("--repo", default=str(REPO), help="repository root")
    ap.add_argument("--claude-bin", help="absolute path of the protected claude CLI install (default: $VEYRO_CLAUDE_BIN; no PATH "
                                         "lookup, and dispatch is refused while it is unset or fails check_cli_install)")
    ap.add_argument("--tick", type=float, default=1.0)
    ap.add_argument("--openclaw-bin", help="ignored: automatic handoff is disabled (HANDOFF_BLOCKER)")
    ap.add_argument("--owner-home", help="the owner's home directory, which must be untraversable for the worker (default: "
                                         "$VEYRO_OWNER_HOME; mandatory for run)")
    ap.add_argument("--claude-sha256", help="pinned sha256 of the protected claude binary (default: $VEYRO_CLAUDE_SHA256)")
    ap.add_argument("--claude-version", help="pinned `claude --version` token (default: $VEYRO_CLAUDE_VERSION)")
    ap.add_argument("--legacy-state", help="absolute path of the exact copy of the legacy v1 state.json (default: "
                                           "$VEYRO_LEGACY_STATE; mandatory)")
    ap.add_argument("--legacy-sha256", help="pinned sha256 of that copy (default: $VEYRO_LEGACY_SHA256; mandatory)")
    ap.add_argument("--legacy-evidence", help="absolute path of the exact read-only copy of the v1 acceptances/ tree and the review outputs it names "
                                              "(default: $VEYRO_LEGACY_EVIDENCE; mandatory)")
    ap.add_argument("--cutover-proof", help="root-owned cutover proof outside the runner home and checkout (mandatory for run)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the queue (foreground)")
    d = sub.add_parser("dashboard", help="serve the read-only dashboard on 127.0.0.1")
    d.add_argument("--port", type=int, default=8766)
    e = sub.add_parser("enqueue", help="queue a task (the running runner picks it up)")
    e.add_argument("--id", required=True)
    e.add_argument("--module", required=True)
    e.add_argument("--role", required=True, choices=ROLES)
    e.add_argument("--title")
    e.add_argument("--prompt-file", required=True)
    e.add_argument("--allow", action="append", default=[], help="repo path, dir/ prefix or glob an implement/test task may change")
    e.add_argument("--verify-cmd", help='JSON argv list run by the runner after the agent, e.g. \'["python3","-m","unittest"]\'')
    e.add_argument("--depends-on", action="append", default=[], help="task id that must be COMPLETED first")
    e.add_argument("--review-of", help="review only: id of the implement/test task under review")
    e.add_argument("--max-attempts", type=int, default=3)
    e.add_argument("--remediates", help="id of the FAILED task this task corrects (required to resubmit identical failed work)")
    for c in CONTROLS:
        sub.add_parser(c)
    x = sub.add_parser("cancel", help="cancel a PENDING or RUNNING task")
    x.add_argument("task_id")
    sub.add_parser("status")
    sub.add_parser("acknowledge-escaped", help="N1: ask the live runner to re-check the escaped-process gate on its "
                                                "next tick; never force-clears a still-present escaped process")
    a = ap.parse_args(argv)
    try:
        # No sandbox escape hatch exists on any platform. Automatic handoff is never configured from the command line or env.
        cfg = Config(home=a.home, repo=a.repo, claude_bin=a.claude_bin, tick=a.tick, owner_home=a.owner_home,
                     claude_sha256=a.claude_sha256, claude_version=a.claude_version, legacy_state=a.legacy_state,
                     legacy_sha256=a.legacy_sha256, cutover_proof=a.cutover_proof,
                     legacy_evidence=a.legacy_evidence)
    except ValueError as ex:
        print(f"invalid configuration: {ex}", file=sys.stderr)
        return 2
    if a.cmd == "run":
        if a.openclaw_bin or os.environ.get("VEYRO_ORCHESTRATOR_BIN") or os.environ.get("VEYRO_AUTOCONTINUE") == "1":
            print(f"automatic handoff is OFF: {HANDOFF_BLOCKER}", file=sys.stderr)
        return Runner(cfg).run()
    if a.cmd == "dashboard":
        # The dashboard imports and calls into this module's own code; it must not be served from an unprotected,
        # agent-writable install any more than "run" may dispatch from one.
        problem = worker_boundary_problem(cfg) or runner_install_problem(cfg)
        if problem:
            print(f"refusing to serve dashboard: {problem}", file=sys.stderr)
            return EXIT_BOUNDARY
        import dashboard
        return dashboard.serve(cfg, a.port)
    try:
        if a.cmd == "enqueue":
            tid = enqueue(cfg, {"id": a.id, "module": a.module, "role": a.role, "title": a.title,
                                "prompt": Path(a.prompt_file).read_text(), "allowed_paths": a.allow,
                                "verify_cmd": json.loads(a.verify_cmd) if a.verify_cmd else None,
                                "depends_on": a.depends_on, "review_of": a.review_of, "max_attempts": a.max_attempts,
                                "remediates": a.remediates})
            print(f"queued {tid}")
        elif a.cmd in CONTROLS:
            set_control(cfg, a.cmd)
            print(json.dumps({"command": a.cmd, "runner_alive": snapshot(cfg)["runner_alive"]}))
        elif a.cmd == "cancel":
            print(f"{a.task_id}: {cancel_task(cfg, a.task_id)}")
        elif a.cmd == "status":
            s = snapshot(cfg)
            s.pop("events")
            s["legacy_tasks"] = f"{len(s['legacy_tasks'])} read-only history task(s)"
            print(json.dumps(s, indent=1))
        elif a.cmd == "acknowledge-escaped":
            print(acknowledge_escaped(cfg))
    except (ValueError, OSError, StateCorrupt) as ex:
        print(f"{a.cmd} refused: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
