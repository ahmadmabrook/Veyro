#!/usr/bin/env python3
"""Veyro MOD-000 Continuous Mission Runner (Python stdlib only).

Durable single-runner / single-repo-writer task runner. All runtime state lives
in the state dir (default outside the repo); this process never writes to the
repository itself. See knowledge/03-Modules/MOD-000/MOD-000.md.
"""
import argparse
import ast
import datetime
import fcntl
import fnmatch
import hashlib
import io
import json
import os
import plistlib
import posixpath
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from types import ModuleType, SimpleNamespace
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = 1
REPO = Path(__file__).resolve().parents[2]
CODE_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_LOADED_CODE_SHA = CODE_SHA  # physical bytes at import; independent of receipt-identity fixtures
_PROCESS_BOOT_NONCE = uuid.uuid4().hex  # fresh per process start; prevents PID reuse from authenticating an old ledger
DASHBOARD_SHA = "d676aa67183d7d8110467cc9c39136aee7a2a0537d022e12cdf05938fe0d3b8a"
_TRUSTED_DASHBOARD = None

# Role -> model family. Opus roles may never be silently satisfied by Sonnet
# (EIP "No-silent-downgrade rule"); unverifiable Opus evidence => BLOCKED.
OPUS_ROLES = {"architecture", "scenario-review", "code-review", "manual-qa",
              "security", "performance", "gatekeeper"}
SONNET_ROLES = {"implement", "test"}
ROLES = OPUS_ROLES | SONNET_ROLES
WRITE_ROLES = SONNET_ROLES  # may change repo files inside their declared scope; every other role is read-only
FAMILIES = ("opus", "sonnet", "haiku")
TOKEN_FIELDS = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
MEANINGFUL_TOKENS = 1  # any observed non-intended model use blocks assurance
OUTCOME_RE = re.compile(r"^OUTCOME:\s*(APPROVED|CHANGES_REQUESTED|BLOCKED)\s*$")
BASELINE_CODES = ("BASELINE_MISMATCH", "BASELINE_NOT_PINNED")
CHILD_ENV_KEEP = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL", "TERM")
CONTROLS = {"pause": "PAUSE", "resume": "RUN", "stop": "STOP"}
MOD004_PROMOTION = {
    "contracts/engineering/staging/mod004-rls.md": ".claude/rules/backend/mod004-rls.md",
    "contracts/engineering/staging/mod004-privileged-console.md": ".claude/rules/admin/mod004-privileged-console.md",
}
OPERATIONAL_DIFF_RETRY_RECEIPTS = {
    # The one audited historical review that lacked the Git baseline; no general phrase-based exception.
    "mod004-cap-provenance-final-opus-review-20261018": {
        "result_sha256": "4d93f76b86dafcab3c1a47dd8b3758c58b518c578421d45e563864fa09ab1b4d",
        "changed": [{"path": "contracts/engineering/module-capabilities.yaml",
                     "sha256": "2958958c1212deafbb9bc3e34673bb4ee145913f655671ae709d4a552dde526a"}],
    },
}
# One owner-authorized fresh accounting write after a source-inaccessible BLOCKED review.
# This is not a retry or an approval of the historical write. No other module or write may use it.
ACCOUNTING_RECOVERY_REVIEW = "mod004-cap-budget-accounting-opus-review-20261019"
ACCOUNTING_RECOVERY_WRITE = "mod004-cap-exception-accounting-recovery-sonnet-20261019"
ACCOUNTING_RECOVERY_PATHS = (
    "contracts/engineering/capability-records/CAP-001-mod004-d123a-prepull.md",
    "contracts/engineering/module-capabilities.yaml",
)
ACCOUNTING_RECOVERY_BASE_HASHES = (
    "f056483119f6468c88d4f2ca321b5bd6f6b2393889ba15eb2f52470bc0b87e77",
    "2958958c1212deafbb9bc3e34673bb4ee145913f655671ae709d4a552dde526a",
)
ACCOUNTING_EIP = ("Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx",
                  "b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f")
ACCOUNTING_SOURCES = {
    "runs/mod004-cap-budget-source-recovery-opus-20261019-1.out": "9860238d0460bfd49fd7bb005d560c17b300ec741aaf30b23977fdefb79713f8",
    "runs/mod004-cap-budget-accounting-opus-review-20261019-1.out": "77ed178effa64a10287b42e1b1cafcb00efcce55d1d1b78a3d149c257637cef8",
    "runs/mod004-cap-budget-accounting-sonnet-20261019-1.evidence.json": "8bd77fb0fd13711fb8a149f77b7bd73523d55a927b9f9ec1814ce31bd7b97ad7",
    "reviews/mod004-d123a-source-verification-opus-20261018.json": "00414c78c4e671e4cb5e271c7fe3f59956808386bdea9955f8e3400b76634cfb",
    "reviews/mod004-supply-chain-metadata-20261018.json": "8e6a42c5dc59271059fb8ffbaee503f317cf62ac891e0f8201a55bcebdb44ca5",
    "runs/mod004-d123a-prepull-bound-opus-review-20261018-1.out": "dbf21d21682615ea86eca61031f66d915763b48474e10e364e5b5288b3b3f9e4",
    "runs/mod004-d123a-prepull-evidence-sonnet-20261018-1.out": "dd32431bbfdf99c34ee9713a85c132476ad590d461617053c5ffc1c28d7f22b6",
    "runs/mod004-d123a-prepull-final-opus-review-20261018-1.out": "512aef3bc8e310a18863e33dcd26a20fa13de20095764ed5eac76ad7c63550a3",
    "runs/mod004-d123a-prepull-final-remed-sonnet-20261018-1.out": "c5cb3d73e2906e96db97289044a6f130a9f7147e3c1bd06820443001512f2bca",
    "runs/mod004-d123a-prepull-remed-opus-review-20261018-1.out": "73448cfabf98a579cb626e86f63fa772f259cf4bf3dc9e32090ad59bb96d3311",
    "runs/mod004-d123a-prepull-remed-sonnet-20261018-1.out": "50f85a2572843ecfcd11c29261aa176e0650f5e1d4b21264a07a05679c877c0e",
}
BASELINE_PREFIXES = ("Gym_OS_Master_Product_Blueprint", "Veyro_Technical_System_Design",
                     "Veyro_Engineering_Implementation_Plan", "veyro-product-experience-design")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MOD_RE = re.compile(r"^MOD-\d{3}$")
EXIT_LOCKED, EXIT_CORRUPT = 3, 4


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def default_home():
    if os.environ.get("VEYRO_RUNNER_HOME"):
        return Path(os.environ["VEYRO_RUNNER_HOME"])
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Veyro/mission-runner"
    return Path.home() / ".local/state/veyro/mission-runner"


class Config:
    def __init__(self, home=None, repo=REPO, claude_bin=None, timeout=3600.0, tick=1.0,
                 backoff_base=5.0, backoff_cap=300.0, max_attempts=3, baseline_every=30.0,
                 sandbox="auto", verify_timeout=600.0, gh_bin=None, ci_every=300.0, ci_mode=None,
                 gate_mode=None, orchestrator_bin=None, handoff_timeout=600.0, review_gate=True):
        self.home = Path(home) if home else default_home()
        # None disables automatic continuation; `main` resolves the OpenClaw CLI for the real runner.
        self.orchestrator_bin = orchestrator_bin or os.environ.get("VEYRO_ORCHESTRATOR_BIN") or None
        self.handoff_timeout = handoff_timeout
        self.review_gate = review_gate  # mandatory Opus review between write tasks; only unit-test fixtures turn it off
        self.repo = Path(repo)
        self.claude_bin = claude_bin or os.environ.get("VEYRO_CLAUDE_BIN", "claude")
        self.timeout, self.tick = timeout, tick
        self.backoff_base, self.backoff_cap = backoff_base, backoff_cap
        self.max_attempts, self.baseline_every = max_attempts, baseline_every
        self.sandbox, self.verify_timeout = sandbox, verify_timeout  # sandbox: auto | off
        self.gh_bin, self.ci_every = gh_bin or os.environ.get("VEYRO_GH_BIN", "gh"), ci_every  # ci_every<=0 disables
        self.ci_mode = ci_mode or os.environ.get("VEYRO_CI_MODE", "gh")
        if self.ci_mode not in ("gh", "public"):  # a typo must fail closed, never silently fall back to gh
            raise ValueError(f"ci_mode must be 'gh' or 'public', got {self.ci_mode!r}")
        self.gate_mode = gate_mode or os.environ.get("VEYRO_GATE_MODE", "off")
        if self.gate_mode != "off":  # trusted-check publishing is retired (owner decision 2026-10-16): fail closed
            raise ValueError(f"gate_mode must be 'off' (trusted gate retired), got {self.gate_mode!r}")


# ---------------------------------------------------------------- durable store
def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, data: bytes):
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    fsync_dir(path.parent)  # make the rename itself durable


class StateCorrupt(Exception):
    pass


class Store:
    def __init__(self, home):
        self.home = Path(home)
        self.state_path = self.home / "state.json"
        self.events_path = self.home / "events.jsonl"
        for d in ("commands", "queue", "runs", "locks", "logs"):
            (self.home / d).mkdir(parents=True, exist_ok=True, mode=0o700)

    def load(self):
        if not self.state_path.exists():
            return {"schema": SCHEMA, "control": "RUN", "health": {"status": "UNKNOWN"}, "tasks": {},
                    "applied_ops": [], "mr_counters": {}, "usage": {}, "recoveries": 0,
                    "baseline": None, "runner": None}
        try:
            st = json.loads(self.state_path.read_text())
            if not (isinstance(st, dict) and st.get("schema") == SCHEMA and isinstance(st.get("tasks"), dict)):
                raise ValueError("unexpected state schema")
            return st
        except Exception as e:  # fail closed: never overwrite unreadable state
            raise StateCorrupt(f"{self.state_path}: {e}")

    def save(self, state):
        atomic_write(self.state_path, json.dumps(state, indent=1, sort_keys=True).encode())

    def event(self, kind, op_id=None, **detail):
        line = json.dumps({"ts": now_iso(), "kind": kind, "op_id": op_id, **detail}, sort_keys=True)
        fd = os.open(self.events_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (line + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def tail_events(self, n=60):
        try:
            with open(self.events_path, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 131072))
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

    def pending_commands(self):
        return sorted((self.home / "commands").glob("*.json"))


class FileLock:
    """Advisory flock; the kernel releases it once every fd on the open file description is closed."""

    def __init__(self, path):
        self.path, self.fd, self.meta = Path(path), None, {}

    def acquire(self, owner):
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
        # close(), not LOCK_UN: a child that inherited this fd keeps the lock after we die or release
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


def writer_lock_path(home, repo):
    return Path(home) / "locks" / f"repo-writer-{hashlib.sha256(str(Path(repo).resolve()).encode()).hexdigest()[:12]}.lock"


# -------------------------------------------------------------------- baseline
class PinError(Exception):
    pass


def dir_hash(root: Path):
    h = hashlib.sha256()
    rels = []
    for d, dirs, fs in os.walk(root):
        for name in dirs:
            if (Path(d) / name).is_symlink():
                raise ValueError(f"symlink in baseline directory: {os.path.relpath(Path(d) / name, root)}")
        for f in fs:
            if f != ".DS_Store":
                rels.append(os.path.relpath(os.path.join(d, f), root))
    for rel in sorted(rels, key=lambda r: r.encode()):
        p = root / rel
        if p.is_symlink():
            raise ValueError(f"symlink in baseline directory: {rel}")
        b, pb = p.read_bytes(), rel.encode()
        h.update(len(pb).to_bytes(4, "big") + pb + len(b).to_bytes(8, "big") + b)
    return h.hexdigest()


def source_hash(repo, name):
    rel = name.rstrip("/")
    if rel.startswith(("/", "..")) or ".." in Path(rel).parts:
        raise ValueError(f"unsafe path {name}")
    p = Path(repo) / rel
    if p.is_symlink() or not p.exists():
        raise ValueError(f"missing or symlink: {name}")
    return dir_hash(p) if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()


def parse_index(text):
    return re.findall(r"^\|\s*`([^`]+)`\s*\|\s*`([0-9a-f]{64})`\s*\|\s*$", text, re.M)


def pin_path(home):
    return Path(home) / "baseline-pin.json"


def load_pin(home):
    """None = never pinned; {'error': ..} = pin unreadable (treated as not trustworthy)."""
    p = pin_path(home)
    try:
        raw = p.read_text()
    except FileNotFoundError:
        return None
    except OSError as e:
        return {"error": str(e)}
    try:
        d = json.loads(raw)
        if not (d["schema"] == SCHEMA and re.fullmatch(r"[0-9a-f]{64}", d["index_sha256"])
                and isinstance(d["sources"], list) and d["sources"]):
            raise ValueError("unexpected pin shape")
        return d
    except Exception as e:
        return {"error": f"pin unreadable: {e}"}


def bootstrap_pin(cfg, confirm_index_sha256):
    """One-time, owner-confirmed pin of the index + every source hash, stored OUTSIDE the repo.

    Never overwrites: rebinding requires the owner to delete the pin file deliberately and re-run.
    """
    Store(cfg.home)
    target = pin_path(cfg.home)
    if target.exists():
        raise PinError(f"baseline already pinned ({target}); rebinding must be a deliberate manual delete")
    idx = Path(cfg.repo) / "PROJECT_INDEX.md"
    if idx.is_symlink() or not idx.is_file():
        raise PinError("PROJECT_INDEX.md missing or a symlink")
    idx_bytes = idx.read_bytes()
    actual = hashlib.sha256(idx_bytes).hexdigest()
    if confirm_index_sha256 != actual:
        raise PinError(f"--confirm-index-sha256 does not match the index on disk (actual {actual})")
    rows = parse_index(idx_bytes.decode())
    missing = [p for p in BASELINE_PREFIXES if not any(n.startswith(p) for n, _ in rows)]
    if missing:
        raise PinError(f"PROJECT_INDEX.md lacks entries: {missing}")
    sources = []
    for name, want in rows:
        try:
            got = source_hash(cfg.repo, name)
        except Exception as e:
            raise PinError(f"cannot hash {name}: {e}")
        if got != want:
            raise PinError(f"source {name} does not match the hash the index declares")
        sources.append({"name": name, "sha256": got})
    pin = {"schema": SCHEMA, "pinned_at": now_iso(), "index_sha256": actual, "sources": sources,
           "repo": str(Path(cfg.repo).resolve())}
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(pin, indent=1, sort_keys=True).encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(tmp, target)  # atomic no-clobber
    except FileExistsError:
        raise PinError("baseline pinned concurrently; refusing to overwrite")
    finally:
        os.unlink(tmp)
    os.chmod(target, 0o400)
    fsync_dir(target.parent)
    Store(cfg.home).event("baseline-pinned", index_sha256=actual, sources=len(sources))
    return pin


def verify_baseline(repo, pin):
    """Return {ok, code, reason, sources, index}. Hashes come from the out-of-repo pin, never from the
    mutable index alone; any parse/IO/hash problem, or a changed index, => ok False."""
    res = {"ok": False, "code": None, "reason": None, "checked_at": now_iso(), "pinned_at": None,
           "index": None, "sources": []}
    if pin is None:
        res.update(code="NOT_PINNED", reason="baseline not pinned: run `runner.py pin-baseline` (owner step)")
        return res
    if pin.get("error"):
        res.update(code="PIN_INVALID", reason=pin["error"])
        return res
    res["pinned_at"] = pin.get("pinned_at")
    try:
        got_idx = hashlib.sha256((Path(repo) / "PROJECT_INDEX.md").read_bytes()).hexdigest()
        res["index"] = {"name": "PROJECT_INDEX.md", "expected": pin["index_sha256"], "actual": got_idx,
                        "match": got_idx == pin["index_sha256"]}
        for s in pin["sources"]:
            got = source_hash(repo, s["name"])
            res["sources"].append({"name": s["name"], "expected": s["sha256"], "actual": got,
                                   "match": got == s["sha256"]})
        bad = ([] if res["index"]["match"] else ["PROJECT_INDEX.md"]) + [s["name"] for s in res["sources"] if not s["match"]]
        res["reason"] = f"hash mismatch vs pin: {bad}" if bad else None
        res["code"] = "MISMATCH" if bad else None
        res["ok"] = not bad
    except Exception as e:
        res.update(code="ERROR", reason=f"baseline check error: {e}")
    return res


# ------------------------------------------------------------ repo change evidence
def git_env():
    """Curated Git environment: no inherited GIT_* overrides and no system/global config, so a model-written
    ~/.gitconfig (e.g. core.fsmonitor) can never make a runner git call execute a script."""
    env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_TERMINAL_PROMPT="0")
    return env


def git_argv(repo, *args):
    return ["git", "-c", "core.fsmonitor=", "-C", str(repo), *args]


def git_run(repo, *args, timeout=120, check=False, text=False):
    return subprocess.run(git_argv(repo, *args), capture_output=True, check=check, timeout=timeout, text=text,
                          env=git_env(), stdin=subprocess.DEVNULL)


def _git(repo, *args, timeout=120):
    return git_run(repo, *args, timeout=timeout, check=True)


def _path_hash(p):
    if p.is_symlink():
        return "link:" + os.readlink(p)
    if p.is_file():
        return hashlib.sha256(p.read_bytes()).hexdigest()
    return None if not p.exists() else "dir"


def repo_state(repo):
    """HEAD + content hash of every path dirty vs HEAD (tracked or untracked, not git-ignored).

    Diffing two states reveals every change a child made; a clean path that stays clean is untouched.
    """
    repo = Path(repo)
    r = git_run(repo, "rev-parse", "--verify", "-q", "HEAD", text=True)
    head = r.stdout.strip() or None
    out = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames").stdout
    files = {}
    for e in out.split(b"\0"):
        if len(e) > 3:
            path = e[3:].decode(errors="surrogateescape")
            files[path] = _path_hash(repo / path)
    return {"head": head, "files": files}


def diff_state(before, after):
    changed = {p for p in set(before["files"]) | set(after["files"])
               if before["files"].get(p, "<clean>") != after["files"].get(p, "<clean>")}
    return sorted(changed)


def in_scope(path, allowed):
    return any(path.startswith(a) if a.endswith("/") else (path == a or fnmatch.fnmatchcase(path, a)) for a in allowed)


# ---------------------------------------------------------------- model routing
def required_family(role):
    return "opus" if role in OPUS_ROLES else "sonnet"


def family_of(model):
    return next((f for f in FAMILIES if f in model.lower()), "unknown")


def _tokens(u, key):
    v = u.get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0


def judge_route(role, parsed):
    """Truthful routing verdict from what the CLI reported it actually used.

    Only real token fields count (contextWindow/maxOutputTokens are model limits, not usage). The model
    name is `canonicalModel` when the CLI gives one, else the modelUsage key. VERIFIED needs every model
    that consumed meaningful tokens - not just the largest - to be the intended family.
    """
    want = required_family(role)
    usage = (parsed or {}).get("modelUsage")
    models = {}
    for key, u in (usage.items() if isinstance(usage, dict) else ()):
        if not isinstance(u, dict):
            continue
        canon = u.get("canonicalModel") if isinstance(u.get("canonicalModel"), str) and u.get("canonicalModel") else key
        m = models.setdefault(canon, {"model": canon, "family": family_of(canon), "tokens": 0, "fresh": 0})
        m["tokens"] += sum(_tokens(u, k) for k in TOKEN_FIELDS)
        m["fresh"] += _tokens(u, "inputTokens") + _tokens(u, "outputTokens")
    used = sorted((m for m in models.values() if m["tokens"] > 0), key=lambda m: -m["tokens"])
    if not used:
        return {"intended": want, "resolved": [], "primary": None, "verdict": "UNVERIFIED", "models": [],
                "basis": "CLI output carried no token usage per model; family not observable"}
    meaningful = [m for m in used if m["tokens"] >= MEANINGFUL_TOKENS]
    off = [m["model"] for m in meaningful if m["family"] != want]
    primary = used[0]
    ok = not off and primary["family"] == want
    basis = (f"all {len(meaningful)} meaningfully-used model(s) are {want}; primary {primary['model']}" if ok else
             f"non-{want} model(s) consumed meaningful tokens: {off or [primary['model']]}")
    return {"intended": want, "resolved": [m["model"] for m in used], "primary": primary["model"],
            "verdict": "VERIFIED" if ok else "MISMATCH", "basis": basis, "models": used}


# ------------------------------------------------------------ read-only CI observation (gh)
CI_CALL_TIMEOUT, CI_BUDGET = 3.0, 7.0  # bounded below the 10s heartbeat-liveness window
CI_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._~/%?=&#:+-]{0,300}$")
CI_ENV_KEEP = ("PATH", "HOME", "GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "GH_CONFIG_DIR", "XDG_CONFIG_HOME")
CI_PUBLIC_ENV_KEEP = ("PATH", "HOME")  # the public observer never needs or inherits a credential
CI_MAX_BYTES = 512 * 1024  # response cap applied before JSON decode
CI_CODE_RE = re.compile(r"^[a-z0-9-]{1,40}$")
CI_BRANCH, CI_SCOPE = "main", "main-push"  # post-push Actions evidence for main, never a pre-push gate
SHA_RE = re.compile(r"[0-9a-f]{40}")
SLUG_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class CIError(Exception):
    """Carries only a short fixed code; raw gh output never reaches state or the browser."""


def _s(v, n=120):
    return v[:n] if isinstance(v, str) else None


def _url(v):
    return v if isinstance(v, str) and CI_URL_RE.match(v) else None


def clean_ci(d):
    """Allowlist every field read from ci.json / gh; anything unknown is dropped. Retired PR/check fields are not carried."""
    if not isinstance(d, dict):
        return None
    runs = d.get("runs") if isinstance(d.get("runs"), list) else []
    other = d.get("runs_other_head")
    out = {"source": _s(d.get("source"), 20), "scope": _s(d.get("scope"), 20), "observed_at": _s(d.get("observed_at"), 40),
           "last_attempt_at": _s(d.get("last_attempt_at"), 40), "error": _s(d.get("error"), 40),
           "repo": _s(d.get("repo"), 100), "repo_url": _url(d.get("repo_url")), "branch": _s(d.get("branch"), 100),
           "head_sha": _s(d.get("head_sha"), 40),
           "runs_other_head": other if type(other) is int and other >= 0 else None,
           "runs": [{"name": _s(x.get("name")), "status": _s(x.get("status"), 30), "conclusion": _s(x.get("conclusion"), 30),
                     "ref": _s(x.get("ref"), 100), "head_sha": _s(x.get("head_sha"), 40), "event": _s(x.get("event"), 30),
                     "created_at": _s(x.get("created_at"), 40), "url": _url(x.get("url"))}
                    for x in runs if isinstance(x, dict)][:10]}
    for k in ("staging", "secrets", "rollback"):  # nothing in gh proves these; always reported as not configured
        out[k] = "not configured"
    return out


def _gh(cfg, run, deadline, *args, ok_codes=(0,)):
    left = deadline - time.monotonic()
    if left <= 0:
        raise CIError("gh-timeout")
    env = {k: os.environ[k] for k in CI_ENV_KEEP if k in os.environ} | {"GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"}
    try:
        p = run([cfg.gh_bin, *args], capture_output=True, text=True, timeout=min(CI_CALL_TIMEOUT, left),
                cwd=str(cfg.repo), env=env, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise CIError("gh-missing")
    except subprocess.TimeoutExpired:
        raise CIError(f"gh-timeout-{args[0]}-{args[1]}")
    except OSError:
        raise CIError("gh-failed")
    if p.returncode not in ok_codes:
        low = (p.stderr or "").lower()
        raise CIError("gh-auth" if "auth" in low or "login" in low or "token" in low else
                      "gh-network" if "dial" in low or "resolve" in low or "connect" in low else "gh-failed")
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise CIError("bad-output")


def main_snapshot(source, slug, head, runs):
    """Build the post-push observation. Only push-event runs on main for the exact observed main head are kept;
    runs for other commits are counted, never shown, so an older green run cannot stand in for the current head."""
    if not isinstance(head, str) or not SHA_RE.fullmatch(head):
        raise CIError("bad-output")
    exact = [x for x in runs if isinstance(x, dict) and x.get("ref") == CI_BRANCH
             and x.get("event") == "push" and x.get("head_sha") == head]
    return clean_ci({"source": source, "scope": CI_SCOPE, "observed_at": now_iso(), "repo": slug,
                     "repo_url": "https://github.com/" + slug, "branch": CI_BRANCH, "head_sha": head,
                     "runs": exact, "runs_other_head": len(runs) - len(exact)})


def fetch_ci(cfg, run=subprocess.run):
    """One bounded, read-only `gh` observation (argv list, no shell) of push runs on main for the exact remote
    main head. No pull-request query is made. Raises CIError(code) on any failure."""
    deadline = time.monotonic() + CI_BUDGET
    try:
        remote = _git(cfg.repo, "remote", "get-url", "origin",
                      timeout=max(0.1, deadline - time.monotonic())).stdout.decode().strip()
    except (subprocess.SubprocessError, OSError):
        remote = ""
    slug_match = re.search(r"(?:github\.com[:/])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$", remote)
    slug = slug_match.group(1) if slug_match else None
    repo_args = ("repo", "view", slug, "--json", "nameWithOwner,url") if slug else (
        "repo", "view", "--json", "nameWithOwner,url")
    repo = _gh(cfg, run, deadline, *repo_args)
    name = repo.get("nameWithOwner") if isinstance(repo, dict) else None
    if not isinstance(name, str) or not SLUG_RE.fullmatch(name):
        raise CIError("bad-output")
    ref = _gh(cfg, run, deadline, "api", f"repos/{name}/git/ref/heads/{CI_BRANCH}")
    head = ref.get("object", {}).get("sha") if isinstance(ref, dict) and isinstance(ref.get("object"), dict) else None
    if not isinstance(head, str) or not SHA_RE.fullmatch(head):
        raise CIError("bad-output")
    runs = _gh(cfg, run, deadline, "run", "list", "--branch", CI_BRANCH, "--event", "push", "--commit", head,
               "--limit", "8", "--json", "name,status,conclusion,headBranch,headSha,event,createdAt,url")
    if not isinstance(runs, list):
        raise CIError("bad-output")
    return main_snapshot("gh", name, head, [
        {"name": x.get("name"), "status": x.get("status"), "conclusion": x.get("conclusion"),
         "ref": x.get("headBranch"), "head_sha": x.get("headSha"), "event": x.get("event"),
         "created_at": x.get("createdAt"), "url": x.get("url")} for x in runs if isinstance(x, dict)])


def fetch_ci_public(cfg, opener=urllib.request.urlopen):
    """Observe a public GitHub repository without exporting a Keychain credential to a LaunchAgent.

    Two REST reads (the main ref, then push runs for that exact SHA), deliberately infrequent (default: five
    minutes) to stay below the unauthenticated API budget. No pull-request endpoint is queried. Private
    repositories fail closed as unavailable.
    """
    deadline = time.monotonic() + CI_BUDGET
    try:
        remote = _git(cfg.repo, "remote", "get-url", "origin", timeout=2).stdout.decode().strip()
    except (subprocess.SubprocessError, OSError):
        raise CIError("git-failed")
    match = re.search(r"(?:github\.com[:/])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$", remote)
    if not match:
        raise CIError("github-origin-unavailable")
    slug = match.group(1)
    base = "https://api.github.com/repos/" + slug

    def read(path):
        left = min(CI_CALL_TIMEOUT, deadline - time.monotonic())
        if left <= 0:
            raise CIError("github-api-timeout")
        req = urllib.request.Request(base + path, headers={"Accept": "application/vnd.github+json",
                                                            "User-Agent": "Veyro-CI-observer"})
        try:
            with opener(req, timeout=left) as response:
                raw = response.read(CI_MAX_BYTES + 1)
            if len(raw) > CI_MAX_BYTES:
                raise CIError("github-api-bad-output")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            hdrs = e.headers if e.headers is not None else {}
            limited = e.code == 429 or (e.code == 403 and (hdrs.get("X-RateLimit-Remaining") == "0"
                                                           or hdrs.get("Retry-After") is not None))
            e.close()
            raise CIError("github-api-rate-limit" if limited else "github-api-unavailable")
        except (urllib.error.URLError, TimeoutError, OSError):
            raise CIError("github-api-unavailable")
        except (ValueError, TypeError):
            raise CIError("github-api-bad-output")

    ref = read(f"/git/ref/heads/{CI_BRANCH}")
    head = ref.get("object", {}).get("sha") if isinstance(ref, dict) and isinstance(ref.get("object"), dict) else None
    if not isinstance(head, str) or not SHA_RE.fullmatch(head):
        raise CIError("github-api-bad-output")
    runs_data = read(f"/actions/runs?branch={CI_BRANCH}&event=push&head_sha={head}&per_page=8")
    if not isinstance(runs_data, dict) or not isinstance(runs_data.get("workflow_runs"), list):
        raise CIError("github-api-bad-output")
    return main_snapshot("github-public-api", slug, head, [
        {"name": x.get("name"), "status": x.get("status"), "conclusion": x.get("conclusion"),
         "ref": x.get("head_branch"), "head_sha": x.get("head_sha"), "event": x.get("event"),
         "created_at": x.get("created_at"), "url": x.get("html_url")}
        for x in runs_data["workflow_runs"] if isinstance(x, dict)])


def observe_public(cfg, popen=subprocess.Popen):
    """Run fetch_ci_public in a supervised child of this script so a DNS stall or slow trickle cannot exceed
    CI_BUDGET wall-clock. The child is read-only, gets only PATH/HOME (no tokens), and its whole process
    group is killed and reaped on timeout. Raises CIError(code); child stdout is size-capped and re-validated."""
    cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "--repo", str(cfg.repo), "ci-observe-public"]
    env = {k: os.environ[k] for k in CI_PUBLIC_ENV_KEEP if k in os.environ}
    try:
        p = popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, env=env,
                  start_new_session=True)
    except OSError:
        raise CIError("github-api-failed")
    try:
        out, _ = p.communicate(timeout=CI_BUDGET)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        p.communicate()
        raise CIError("github-api-timeout")
    except BaseException:
        p.kill()
        p.wait()
        raise
    if out is None or len(out) > 2 * CI_MAX_BYTES:
        raise CIError("github-api-bad-output")
    try:
        data = json.loads(out)
    except ValueError:
        raise CIError("github-api-bad-output" if p.returncode == 0 else "github-api-failed")
    if not isinstance(data, dict):
        raise CIError("github-api-bad-output")
    code = data.get("error")
    if code is not None:
        raise CIError(code if isinstance(code, str) and CI_CODE_RE.match(code) else "github-api-failed")
    if p.returncode != 0:
        raise CIError("github-api-failed")
    ci = clean_ci(data)
    if not ci or ci.get("source") != "github-public-api" or ci.get("scope") != CI_SCOPE or not ci.get("observed_at"):
        raise CIError("github-api-bad-output")
    return ci


def backoff(cfg, attempts):
    return min(cfg.backoff_cap, cfg.backoff_base * 2 ** max(0, attempts - 1))


# ------------------------------------------------------- automatic continuation handoff
ORCH_AGENT = "veyro-continuation-planner"
ORCH_SESSION = "agent:veyro-continuation-planner:mission-continuation"
PLANNER_MODEL = "openai/gpt-6-sol"
PLANNER_TOOLS = frozenset({"read", "ls", "dir_list"})
# The Gateway runs the turn, not the CLI client, so only the planner's configured tool policy confines it. Under the
# Codex runtime a native tool (request_user_input_async) leaked into the inventory despite an explicit deny. The
# owner pinned the SAME model to the built-in OpenClaw runtime at agents.entries.<id>.models[PLANNER_MODEL].agentRuntime.id;
# that exact setting is required before any Gateway call, and the returned agentHarnessId must confirm it.
PLANNER_RUNTIME = "openclaw"
HANDOFF_KINDS = ("TASK", "BLOCKED", "WAITING_FOR_OWNER", "NO_LEGAL_WORK")
HANDOFF_STATUS = {"BLOCKED": "blocked", "WAITING_FOR_OWNER": "waiting_for_owner", "NO_LEGAL_WORK": "idle"}
HANDOFF_OUT_MAX = 1_000_000  # whole CLI stdout; larger output is refused, never truncated into a different document
HANDOFF_TEXT_MAX = 64 * 1024  # the final assistant payload
HANDOFF_TASK_KEYS = {"id", "module", "role", "title", "plan_phase", "prompt", "allowed_paths", "expected_changes",
                     "verify_cmd", "review_of", "remediation_of"}
# Autonomously proposed work may never touch the runner, CI, governance controls or the baseline, nor run an arbitrary verifier.
PROPOSAL_PROTECTED = ("tools/mission_runner/", ".github/", ".githooks/", ".claude/", "governance/", "baseline/", "knowledge/03-Modules/",
                      "PROJECT_INDEX.md", "AGENTS.md", "CLAUDE.md", ".gitignore", ".gitattributes")
VERIFY_TARGET_RE = re.compile(r"(?:backend|tools\.[A-Za-z0-9_]+)\.tests(?:\.[A-Za-z_][A-Za-z0-9_]*){0,3}")
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
ORCH_ENV_KEEP = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "TERM")


class HandoffError(Exception):
    pass


def _has_include(node):
    if isinstance(node, dict):
        return any(k in ("$include", "include", "includes") or _has_include(v) for k, v in node.items())
    return isinstance(node, list) and any(_has_include(v) for v in node)


def planner_policy_blocker(config_path=None):
    """None only if the configured planner entry is provably read/list-only; else a precise blocker string.

    Reads the one config file the Gateway is pointed at. Anything not provable from it (unparseable/JSON5, includes,
    missing or duplicate entry, extra tool keys, a runtime other than the exact model-scoped openclaw one) fails closed.
    Prompt text is never trusted."""
    path = Path(config_path or os.environ.get("OPENCLAW_CONFIG_PATH") or Path.home() / ".openclaw" / "openclaw.json")
    try:
        cfg = strict_json(path.read_text())
    except (OSError, ValueError) as e:
        return f"PLANNER_POLICY_UNPROVEN: cannot read strict-JSON gateway config {path.name} ({str(e)[:60]})"
    if _has_include(cfg):
        return "PLANNER_POLICY_UNPROVEN: config uses include/override layers; effective entry cannot be proven"
    agents = cfg.get("agents") if isinstance(cfg, dict) else None
    if not isinstance(agents, dict) or "list" in agents:
        return "PLANNER_POLICY_UNPROVEN: agents must be an object with an entries map and no legacy list"
    entries = agents.get("entries")
    if not isinstance(entries, dict):
        return "PLANNER_POLICY_UNPROVEN: agents.entries must be an object keyed by agent id"
    mine = [k for k in entries if isinstance(k, str) and k.strip().lower() == ORCH_AGENT]  # case/space variants count as duplicates
    if mine != [ORCH_AGENT]:
        return f"PLANNER_POLICY_UNPROVEN: agent {ORCH_AGENT} is missing or defined {len(mine)} times"
    a = entries[ORCH_AGENT]
    if not isinstance(a, dict):
        return "PLANNER_POLICY_UNPROVEN: planner entry must be an object"
    if set(a) - {"id", "name", "workspace", "model", "models", "tools", "subagents"} or a.get("id", ORCH_AGENT) != ORCH_AGENT:
        return "PLANNER_POLICY_UNPROVEN: unsafe tool or sandbox override on the planner entry"
    model = a.get("model")
    if isinstance(model, dict):
        model = model.get("primary") if set(model) <= {"primary"} else None
    if model != PLANNER_MODEL:
        return f"PLANNER_POLICY_UNPROVEN: model is not exactly {PLANNER_MODEL}"
    tools = a.get("tools")
    if not isinstance(tools, dict) or set(tools) - {"allow", "deny"}:
        return "PLANNER_POLICY_UNPROVEN: tools must be an allow/deny list only (no profile, alsoAllow, elevated or overrides)"
    allow = tools.get("allow")
    if not (isinstance(allow, list) and allow and all(isinstance(x, str) for x in allow)) or not set(allow) <= PLANNER_TOOLS:
        return "PLANNER_POLICY_UNPROVEN: tools.allow must be a non-empty subset of read/ls/dir_list"
    deny = tools.get("deny", [])
    if not isinstance(deny, list) or not all(isinstance(x, str) for x in deny) or set(deny) & set(allow):
        return "PLANNER_POLICY_UNPROVEN: tools.deny must be a list of names that does not contradict allow"
    sub = a.get("subagents")
    if not (isinstance(sub, dict) and sub.get("allowAgents") == []):
        return "PLANNER_POLICY_UNPROVEN: subagents.allowAgents must be an explicit empty list"
    scoped = a.get("models")  # exactly one model-scoped override, and it may only pin the runtime
    if not (isinstance(scoped, dict) and set(scoped) == {PLANNER_MODEL}):
        return f"PLANNER_RUNTIME_UNPROVEN: models must hold exactly one override, for {PLANNER_MODEL}"
    override = scoped[PLANNER_MODEL]
    runtime = override.get("agentRuntime") if isinstance(override, dict) else None
    if not isinstance(override, dict) or set(override) != {"agentRuntime"} or not isinstance(runtime, dict) \
            or set(runtime) != {"id"} or runtime["id"] != PLANNER_RUNTIME:
        return (f"PLANNER_RUNTIME_UNPROVEN: models[{PLANNER_MODEL}] must be exactly "
                f'{{"agentRuntime": {{"id": "{PLANNER_RUNTIME}"}}}} (missing/auto/codex runtime or extra override)')
    return None


def _node_version(binpath):
    parts = binpath.parent.parent.name.lstrip("v").split(".")
    return tuple(int(x) if x.isdigit() else 0 for x in parts)


def discover_orchestrator_bin():
    """Explicit executable for the OpenClaw CLI; the LaunchAgent PATH does not contain it."""
    found = shutil.which("openclaw")
    if found:
        return found
    nvm = sorted(Path.home().glob(".nvm/versions/node/*/bin/openclaw"), key=_node_version)  # numeric: v9 < v22
    return str(nvm[-1]) if nvm else None


def _digest(p):
    try:
        if p.stat().st_size > 8 * 1024 * 1024:
            return f"large:{p.stat().st_size}"
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return "absent" if not p.exists() else "unreadable"


def _tree_digests(root, pattern):
    root = Path(root)
    if not root.is_dir():
        return []
    return [(str(f.relative_to(root)), _digest(f)) for f in sorted(root.glob(pattern)) if f.is_file()]


def state_fingerprint(cfg, tasks):
    """Meaningful state: task lifecycle (incl. gate reasons) + repo HEAD + every owner-side input the orchestrator
    judges by, committed or not: acceptance receipts, module records, blocker dispositions, module catalog, pin."""
    try:
        dispositions = _digest(Path(_trusted_dashboard().DISPOSITIONS_PATH))
    except Exception:
        dispositions = "unavailable"
    owner = [_tree_digests(cfg.home / "acceptances", "*.json"), _tree_digests(Path(cfg.repo) / "knowledge/03-Modules", "**/*"),
             dispositions, _digest(CATALOG_PATH), _digest(pin_path(cfg.home))]
    life = sorted((t["id"], t["status"], t.get("attempts"), t.get("blocked_reason"), t.get("gate_reason"))
                  for t in tasks.values())
    return hashlib.sha256(json.dumps([life, local_head_readonly(cfg.repo), owner]).encode()).hexdigest()


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


def runtime_model(meta):
    """Model identity exactly as the runtime reports it at result.meta.agentMeta; anything else is UNKNOWN."""
    agent = meta.get("agentMeta") if isinstance(meta, dict) else None
    if not isinstance(agent, dict):
        return None
    model, provider = agent.get("model"), agent.get("provider")
    if not (isinstance(model, str) and model.strip() and len(model) <= 80):
        return None
    return f"{provider}/{model}" if isinstance(provider, str) and provider.strip() and len(provider) <= 40 else model


def parse_handoff_envelope(raw):
    """(final assistant payload text, runtime-reported model|None, agentHarnessId|None) from `openclaw agent --json` stdout.

    Only the documented envelope is read: {status:"ok", result:{payloads:[{text}], meta:{aborted:false, agentMeta:{}}}}.
    The raw stdout is never searched for markers or model names.
    """
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
        raise HandoffError("turn aborted, or abort state not reported at result.meta.aborted")
    payloads = result.get("payloads")
    final = payloads[-1] if isinstance(payloads, list) and payloads else None
    text = final.get("text") if isinstance(final, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise HandoffError("no final assistant text payload")
    if len(text) > HANDOFF_TEXT_MAX:
        raise HandoffError("final payload exceeds the size bound")
    harness = agent.get("agentHarnessId")
    return text, runtime_model(meta), harness if isinstance(harness, str) else None


def parse_handoff_proposal(text, req_id):
    """The final payload must be exactly one JSON object: {request_id, kind, reason, task?}; prose/markdown fails."""
    try:
        prop = strict_json(text)
    except ValueError:
        raise HandoffError("final payload is not a single strict JSON object (prose/markdown/multiple documents rejected)")
    if not isinstance(prop, dict) or not {"request_id", "kind", "reason"} <= set(prop) or set(prop) - {"request_id", "kind", "reason", "task"}:
        raise HandoffError("proposal keys must be request_id, kind, reason and (TASK only) task")
    if prop["request_id"] != req_id:
        raise HandoffError("request_id does not match the open request (stale or foreign response)")
    if not isinstance(prop["kind"], str) or prop["kind"] not in HANDOFF_KINDS:
        raise HandoffError("kind must be TASK, BLOCKED, WAITING_FOR_OWNER or NO_LEGAL_WORK")
    if not isinstance(prop["reason"], str) or not 0 < len(prop["reason"].strip()) <= 500:
        raise HandoffError("reason must be a non-empty string of at most 500 chars")
    if (prop["kind"] == "TASK") != ("task" in prop):
        raise HandoffError("a task object is required for TASK and forbidden for every other kind")
    if prop["kind"] == "TASK" and not (isinstance(prop["task"], dict) and set(prop["task"]) <= HANDOFF_TASK_KEYS):
        raise HandoffError("task must be one object with only validate_task fields")
    return prop


def complete_handoff_outer_brace(text):
    """Complete only a TASK envelope missing its final outer brace; all other JSON stays strict."""
    if not isinstance(text, str) or not text.startswith("{") or not text.rstrip().endswith("}}"):
        return text, False
    try:
        strict_json(text)
        return text, False
    except ValueError:
        pass
    candidate = text.rstrip() + "}"
    try:
        obj = strict_json(candidate)
    except ValueError:
        return text, False
    if isinstance(obj, dict) and obj.get("kind") == "TASK" and isinstance(obj.get("task"), dict):
        return candidate, True
    return text, False


VERIFY_PATH = "/usr/bin:/bin"  # a sandboxed verifier's PATH: exec is allowed only for Python and Git anyway
RUNTIME_ARTIFACT_DIRS ={"__pycache__", ".venv", "node_modules", "build", "dist"}


def exact_file_problem(repo, p):
    """Why `p` is not an acceptable exact, canonical, non-runtime-artifact repo file path (None when it is)."""
    if not isinstance(p, str) or not p or p.endswith("/") or any(c in p for c in "*?[") or "\0" in p:
        return "must be an exact file path (no directory prefix or glob)"
    n = posixpath.normpath(p)
    if n != p or p.startswith("/") or n == ".." or n.startswith("../"):
        return "must be a canonical repo-relative path"
    parts = p.split("/")
    if any(x in RUNTIME_ARTIFACT_DIRS or x.startswith(".env") for x in parts) or p.endswith((".pyc", ".pyo")):
        return "ignored runtime artifacts (bytecode, virtualenv, node_modules, build, dist, .env*) are not allowed"
    try:
        r = git_run(repo, "check-ignore", "-q", "--no-index", "--", p)
    except (OSError, subprocess.SubprocessError):
        return "could not prove the path is not git-ignored"
    if r.returncode == 0:
        return "git-ignored paths are not allowed"
    if r.returncode != 1:
        return "could not prove the path is not git-ignored"
    return None


def proposal_restrictions(cfg, t):
    """Extra limits for handoff-source (model-proposed) write tasks only; owner-enqueued tasks are unchanged."""
    if t["role"] not in WRITE_ROLES:
        return
    for p in [*t["allowed_paths"], *t["expected_changes"]]:
        why = exact_file_problem(cfg.repo, p)
        if why:
            raise ValueError(f"proposed scope {p!r}: {why}")
    for p in [*t["allowed_paths"], *t["expected_changes"]]:
        body = p[:-1] if p.endswith("/") else p  # exactly one trailing slash marks a directory scope
        n = posixpath.normpath(body) if body else ""
        if not body or p.startswith("/") or n in (".", "..") or n.startswith("../") or n != body:
            raise ValueError(f"proposed scope {p!r}: must be a canonical POSIX repo-relative path "
                             "(no './', repeated slashes, parent segments or absolute paths)")
        low = p.lower()
        if any(c in p for c in "*?[") or low in (".", "./"):
            raise ValueError(f"proposed scope {p!r}: globs and broad paths are not allowed")
        if any(low.startswith(c.lower()) or (low.endswith("/") and c.lower().startswith(low)) or low == c.lower().rstrip("/")
               for c in PROPOSAL_PROTECTED):
            raise ValueError(f"proposed scope {p!r} touches runner, CI, governance or baseline controls")
    v = t["verify_cmd"]
    if not v:
        raise ValueError("a proposed write task must declare a nonempty verify_cmd from the strict unittest allowlist; "
                         "expected_changes alone is not enough")
    targets = v[3:]
    if not (v[:3] == [sys.executable, "-m", "unittest"] and 0 < len(targets) <= 5
            and all(VERIFY_TARGET_RE.fullmatch(x) for x in targets)):
        raise ValueError("a proposed verify_cmd must be exactly [<runner python>, '-m', 'unittest', <test module>...] "
                         "with targets under backend.tests or tools.<name>.tests; no shell, git, other program or flags")
    shadow, tests_dirs = set(), []
    for x in targets:
        parts = x.split(".")
        pkg = Path(cfg.repo).joinpath(*parts[:parts.index("tests") + 1])
        if not pkg.is_dir():
            raise ValueError(f"verify target {x!r}: no reviewed tests package at {'/'.join(parts[:parts.index('tests') + 1])}")
        tests_dirs.append("/".join(parts[:parts.index("tests") + 1]))
        for i in range(1, len(parts) + 1):  # every directory, module and package __init__ the verifier imports
            base = "/".join(parts[:i])
            shadow |= {base, base + ".py", base + "/__init__.py"}
    for p in [*t["allowed_paths"], *t["expected_changes"]]:
        n = posixpath.normpath(p)
        if p.startswith("/") or n == ".." or n.startswith("../") or "__pycache__" in n.split("/"):
            raise ValueError(f"proposed scope {p!r}: absolute, parent-relative and bytecode-cache paths are not allowed")
        top = n.split("/")[0]
        if "/" not in p and (Path(n).suffix in ("", ".py", ".pyc", ".pyd", ".so", ".pth")):
            raise ValueError(f"proposed scope {p!r}: a repo-root entry could shadow a module the verifier imports")
        if top.split(".")[0] in (*sys.stdlib_module_names, "test") or top in ("sitecustomize.py", "usercustomize.py"):
            raise ValueError(f"proposed scope {p!r}: could shadow a standard-library module used by the verifier")
        if (any(s == n or s.startswith(n + "/") for s in shadow) or any(n.startswith(d + "/") for d in tests_dirs)):
            raise ValueError(f"proposed scope {p!r} covers the verifier import path (tests package, test module or package __init__)")


def handoff_prompt(cfg, req_id, fp, task_summary):
    q = json.dumps  # paths are data, quoted as JSON strings (they may contain spaces); no shell is ever involved
    return f"""You are the Veyro mission orchestrator running ONE read-only continuation turn (request {req_id}).
The Veyro mission runner detected a meaningful state change (state fingerprint {fp[:12]}) and has no queued or running work.
Your only job: PROPOSE exactly one next legal operation, or report why none exists. You are not a worker and you have no write path.

Context (inspect it yourself, read-only; do not trust this summary):
- Repository: {q(str(cfg.repo))}
- Runner state dir: {q(str(cfg.home))} (state.json tasks, acceptances/, runs/*.evidence.json)
- Task lifecycle at request time: {task_summary}
- Governance: the pinned EIP/TSD baseline, knowledge/03-Modules/*/ module records, and the module catalog at {q(str(Path(__file__).resolve().parent / "module_catalog.json"))}.

Hard rules:
1. Base every decision on actual evidence in files/state (module records, acceptance receipts, task evidence, git HEAD). Prose, memory or earlier chat is not evidence.
2. Respect all mandatory gates: prerequisite modules must be accepted, no active same-module blocker for gatekeeper/scenario-review, the baseline must be healthy, roles route by the runner (implement/test = Sonnet; architecture, scenario-review, code-review, manual-qa, security, performance, gatekeeper = Opus). Never downgrade an Opus role.
3. Mandatory review: after a DONE implement/test task in a module, the only legal next write or gatekeeper is preceded by an independent Opus code-review of that exact task. Propose that code-review first, with `review_of` binding the exact write task id and its recorded changed files (path + sha256 from the task's evidence). Correction cycles (prospective; only for already-authorized generic product root tasks): up to THREE correction cycles in total per immutable root, counting all findings and children. Each correction must be a new runner-recorded write inside the original allowed scope with `remediation_of` set to the immediate rejected parent. Propose a correction only after a runner-verified, exactly bound Opus CHANGES_REQUESTED review, or a recorded failed lint/unit verification with changed-file evidence; the correction must carry a fresh material diff and tests, and is followed by a fresh exact-bound Opus code-review. Do not propose a correction if the same root-cause fingerprint repeats or there is no progress, if the three cycles are exhausted, if the root is blocked for other reasons, for special S0/CAP/infrastructure tasks, or without exact bound evidence. Existing historical and special remediation limits are unchanged. After APPROVED, continue with ordinary CI or the next legal task; the gatekeeper may follow only when the module's own gates are met, and approval alone does not imply it. The runner re-checks all of this; a proposal that violates it is refused.
4. Follow accepted-module transitions: once a module is ACCEPTED with a verified receipt, move to the next module the catalog and EIP/TSD allow; do not redo accepted work. Continue the next UNACCEPTED product module (currently MOD-003) from its last valid checkpoint. Owner-approved policy is recorded in "/Users/ahmadmabrouk/Library/Application Support/Veyro/mission-runner/policy/owner-execution-infrastructure-boundary-20261017.md": Execution Infrastructure is separate from Veyro product modules, so never reinterpret historical runner/dashboard maintenance under an accepted product module as an unfinished product review gate, and never propose any task for an accepted module (the runner refuses it). Rule 3 still applies in full to actual Veyro product write tasks.
5. Make no owner decisions. If progress needs an owner approval, acceptance, scope or policy decision, propose nothing and answer WAITING_FOR_OWNER.
6. Do NOT edit, create, delete or commit any file, run the runner CLI, enqueue anything, write queue/command/approval/receipt files, certify or accept any module, or perform the worker task yourself. The runner alone validates and enqueues your proposal.
7. If a task is BLOCKED, propose only unrelated legal work, never a retry of the blocked task unless the evidence shows its blocker is resolved. The only exception is the bounded correction described in rule 3, and only when every one of its conditions holds.

Your final assistant message must be exactly one JSON object and nothing else (no markdown, no code fence, no prose).
The reason value MUST be one non-empty string of at most 500 characters; aim for under 300. Put detailed evidence in the task prompt, not reason:
Before sending, check that all JSON braces close. For a TASK response, close every nested changed entry, its list, review_of, task, and finally the outer proposal.
{{"request_id": "{req_id}", "kind": "TASK" | "BLOCKED" | "WAITING_FOR_OWNER" | "NO_LEGAL_WORK", "reason": "<one line, at most 500 chars>", "task": {{...}}}}
"task" is present only for kind TASK and is one complete object with the fields id (unique, [A-Za-z0-9._-]{{1,64}}), module (MOD-NNN), role, title, prompt (the full worker prompt), allowed_paths, expected_changes, verify_cmd (required and nonempty for writing roles, exactly the JSON argv [{q(sys.executable)}, "-m", "unittest", "<dotted test module under backend.tests or tools.<name>.tests>", ...]; an empty or any other verifier is refused; review roles carry none), allowed_paths (exact files or directory prefixes only: no globs, never tools/mission_runner/, .github/, governance or baseline paths), for a remediation write remediation_of ("<reviewed write task id>") and, for role code-review, review_of {{"task_id": "<write task id>", "changed": [{{"path": "...", "sha256": "..."}}]}}. Writing roles need allowed_paths and a nonempty verify_cmd (plus expected_changes as appropriate); review roles must carry none of the three.
"""


# ------------------------------------------------------- prerequisite / acceptance gate
# Roles that can advance implementation or acceptance need every catalog dependency accepted. The remaining
# roles (architecture, security, performance, code-review) are read-only and certify nothing: they bypass.
GATED_ROLES = WRITE_ROLES | {"gatekeeper", "scenario-review", "manual-qa"}
CATALOG_PATH = Path(__file__).resolve().parent / "module_catalog.json"
RECEIPT_MAX_BYTES = 64 * 1024
REVIEW_MAX_BYTES = 8 * 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}")
RECEIPT_REVIEW_KINDS = ("gatekeeper", "activation-review")
VERDICT_LINE_RE = re.compile(
    r"^(?:OUTCOME:\s*(APPROVED|CHANGES_REQUESTED|BLOCKED)\s*|\*\*OUTCOME:\s*(APPROVED|CHANGES_REQUESTED|BLOCKED)\.?\*\*.*)$")
CI_WORKFLOW_NAME = "Veyro Foundation CI"
LEGACY_MODE = "legacy-mod000-lean-foundation"  # MOD-000 only: accepted before CI existed
MOD000_HEADER_SHA = "85596d904aa36bc30abaac524d846e7454da8b6a"
MOD000_RECORD = "knowledge/03-Modules/MOD-000/MOD-000.md"
MOD000_LEGACY_TASK, MOD000_LEGACY_MR = "mod000-gatekeeper-1", "MR-MOD-000-20261015-004"
MOD000_LEGACY_REVIEW = "runs/mod000-gatekeeper-1-1.out"


class GateError(Exception):
    pass


def _trusted_dashboard():
    """Load the sole project-local gate module from pinned source, never from a mutable pyc.

    The module projects active blockers during enqueue and dispatch. Retain the
    first verified code object and check its source bytes before every use.
    """
    global _TRUSTED_DASHBOARD
    path = Path(__file__).with_name("dashboard.py")
    try:
        source = path.read_bytes()
    except OSError:
        raise GateError("local dashboard gate module is unreadable")
    if hashlib.sha256(source).hexdigest() != DASHBOARD_SHA:
        raise GateError("local dashboard gate module differs from pinned source")
    if _TRUSTED_DASHBOARD is None:
        module = ModuleType("dashboard")
        module.__file__ = str(path)
        # dashboard imports runner for read-only UI helpers. Reuse the loaded,
        # integrity-checked runner instead of importing a second on-disk copy.
        sys.modules.setdefault("runner", sys.modules[__name__])
        exec(compile(source, str(path), "exec"), module.__dict__)
        _TRUSTED_DASHBOARD = module
    return _TRUSTED_DASHBOARD


def catalog_dependencies(module):
    try:
        entries = json.loads(CATALOG_PATH.read_text())
        found = [e for e in entries if isinstance(e, dict) and e.get("id") == module]
        deps = found[0]["dependencies"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise GateError(f"{module}: not found in module catalog or catalog unreadable")
    if not (isinstance(deps, list) and all(isinstance(d, str) and MOD_RE.match(d) for d in deps)):
        raise GateError(f"{module}: malformed dependencies in module catalog")
    return deps


def _read_bounded(path, limit):
    if path.is_symlink() or not path.is_file():
        raise GateError(f"{path.name}: missing or not a regular file")
    with open(path, "rb") as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise GateError(f"{path.name}: larger than {limit} bytes")
    return data


def verify_receipt(cfg, module):
    """Read-only, offline check of the operator-written receipt `<home>/acceptances/<module>.json`.

    The receipt is the operator's claim; it is only trusted once every part is re-verified locally: the
    activation commit must be an ancestor of the repo HEAD (stale => reject), the recorded CI run must be a
    success on exactly that commit, and each review file must hash to the recorded sha256 and be an
    APPROVED, Opus-routed (judge_route VERIFIED) success result. Raises GateError on anything else.
    """
    try:
        r = json.loads(_read_bounded(cfg.home / "acceptances" / f"{module}.json", RECEIPT_MAX_BYTES))
    except ValueError:
        raise GateError(f"{module}: receipt is not valid JSON")
    if not isinstance(r, dict) or r.get("schema") != SCHEMA or r.get("module") != module:
        raise GateError(f"{module}: receipt schema/module mismatch")
    if not (isinstance(r.get("operator"), str) and r["operator"].strip() and isinstance(r.get("recorded_at"), str)):
        raise GateError(f"{module}: receipt lacks operator/recorded_at")
    mode = r.get("mode")
    if mode is not None:
        if mode != LEGACY_MODE or module != "MOD-000":
            raise GateError(f"{module}: receipt mode {mode!r} is not permitted")
        return verify_legacy_mod000(cfg, r)
    sha = r.get("activation_sha")
    if not (isinstance(sha, str) and SHA_RE.fullmatch(sha)):
        raise GateError(f"{module}: activation_sha is not a full commit sha")
    ci = r.get("ci")
    if not (isinstance(ci, dict) and isinstance(ci.get("run_id"), str) and ci["run_id"].isdigit()
            and ci.get("event") == "push" and ci.get("status") == "completed" and ci.get("name") == CI_WORKFLOW_NAME
            and ci.get("head_sha") == sha and ci.get("conclusion") == "success"):
        raise GateError(f"{module}: CI evidence is not a completed successful {CI_WORKFLOW_NAME} push run "
                        "on the activation sha")
    if not _is_ancestor(cfg, sha):
        raise GateError(f"{module}: activation sha {sha[:12]} is not an ancestor of repo HEAD (stale or unknown)")
    reviews = r.get("reviews")
    if not (isinstance(reviews, list) and 0 < len(reviews) <= 10):
        raise GateError(f"{module}: receipt has no reviews")
    home = cfg.home.resolve()
    seen = {}
    for rv in reviews:
        if not (isinstance(rv, dict) and rv.get("kind") in RECEIPT_REVIEW_KINDS and isinstance(rv.get("path"), str)
                and isinstance(rv.get("sha256"), str) and SHA256_RE.fullmatch(rv["sha256"])):
            raise GateError(f"{module}: malformed review entry")
        if rv.get("activation_sha") != sha:  # operator-supplied binding of this review to this activation
            raise GateError(f"{module}: review {rv['path']} is not bound to the activation sha")
        _load_approved_review(home, rv["path"], rv["sha256"], module)
        seen.setdefault(rv["kind"], set()).add(rv["sha256"])
    # Both an independent gatekeeper review and the exact activation-diff review are mandatory, and distinct.
    if set(seen) != set(RECEIPT_REVIEW_KINDS) or seen["gatekeeper"] & seen["activation-review"]:
        raise GateError(f"{module}: receipt needs distinct approved gatekeeper and activation-review evidence")


def _load_approved_review(home, relpath, sha256, module):
    """Hash-match, parse and judge one offline review file: Opus-routed success with a single APPROVED verdict."""
    rel = Path(relpath)
    if rel.is_absolute() or ".." in rel.parts:
        raise GateError(f"{module}: review path escapes runner home")
    path = home / rel
    if home not in path.resolve().parents:
        raise GateError(f"{module}: review path escapes runner home")
    data = _read_bounded(path, REVIEW_MAX_BYTES)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise GateError(f"{module}: review {rel.name} does not match recorded sha256")
    try:
        parsed = json.loads(data)
    except ValueError:
        raise GateError(f"{module}: review {rel.name} is not CLI json")
    if not (isinstance(parsed, dict) and parsed.get("subtype") == "success" and parsed.get("is_error") is not True
            and receipt_outcome(parsed.get("result")) == "APPROVED"
            and judge_route("gatekeeper", parsed)["verdict"] == "VERIFIED"):
        raise GateError(f"{module}: review {rel.name} is not an APPROVED, Opus-verified success")


def receipt_outcome(result):
    """Verdict of an offline review for acceptance receipts only (task-run reviews keep the strict final-line rule).

    Only standalone verdict LINES count: the plain `OUTCOME: X` or the Markdown `**OUTCOME: X.** ...`. Inline prose
    mentions are ignored; multiple or contradictory standalone verdict lines make it unverifiable (None).
    """
    if not isinstance(result, str):
        return None
    found = [m.group(1) or m.group(2) for m in (VERDICT_LINE_RE.match(ln.strip()) for ln in result.splitlines()) if m]
    return found[0] if len(found) == 1 else None


def _is_ancestor(cfg, sha):
    try:
        return git_run(cfg.repo, "merge-base", "--is-ancestor", sha, "HEAD", timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def verify_legacy_mod000(cfg, r):
    """MOD-000 only: accepted as Lean Foundation before CI existed, so no CI is required or invented.

    Re-verifies the exact legacy evidence: the receipt names the initial committed header, which must be an
    ancestor of HEAD and contain the module record; the raw Opus gatekeeper output (hash bound by the operator)
    must be an APPROVED Opus success; the runner state task must be DONE/VERIFIED/APPROVED; and the live
    module record must still say ACCEPTED and cite the gatekeeper MR.
    """
    m = "MOD-000"
    if r.get("module") != m or r.get("activation_sha") != MOD000_HEADER_SHA:
        raise GateError(f"{m}: legacy receipt must name the initial committed header {MOD000_HEADER_SHA[:12]}")
    if not _is_ancestor(cfg, MOD000_HEADER_SHA):
        raise GateError(f"{m}: legacy header commit is not an ancestor of repo HEAD")
    try:
        in_header = git_run(cfg.repo, "cat-file", "-e", f"{MOD000_HEADER_SHA}:{MOD000_RECORD}", timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        in_header = False
    if not in_header:
        raise GateError(f"{m}: header commit does not contain the module record")
    rs = r.get("review_sha256")
    if not (isinstance(rs, str) and SHA256_RE.fullmatch(rs)):
        raise GateError(f"{m}: legacy receipt lacks review_sha256")
    _load_approved_review(cfg.home.resolve(), MOD000_LEGACY_REVIEW, rs, m)
    try:
        st = json.loads(_read_bounded(cfg.home / "state.json", REVIEW_MAX_BYTES))
        task = st["tasks"][MOD000_LEGACY_TASK]
        ev = task["evidence"]
    except (ValueError, KeyError, TypeError, GateError):
        raise GateError(f"{m}: legacy gatekeeper task {MOD000_LEGACY_TASK} not found in runner state")
    if not (task.get("status") == "DONE" and task.get("module") == m and task.get("role") == "gatekeeper"
            and isinstance(ev, dict) and ev.get("route_verdict") == "VERIFIED" and ev.get("review_outcome") == "APPROVED"):
        raise GateError(f"{m}: legacy gatekeeper task is not DONE/VERIFIED/APPROVED")
    try:
        text = _read_bounded(Path(cfg.repo) / MOD000_RECORD, REVIEW_MAX_BYTES).decode(errors="replace")
    except GateError:
        raise GateError(f"{m}: live module record missing")
    head = "\n".join(text.splitlines()[:5])
    if not (MOD000_LEGACY_MR in text and "ACCEPTED" in head and "PENDING" not in head):
        raise GateError(f"{m}: live module record does not show ACCEPTED with {MOD000_LEGACY_MR}")


BLOCKER_GATED_ROLES = {"gatekeeper", "scenario-review"}


def active_module_blockers(cfg, t, tasks):
    """Ids of same-module BLOCKED tasks the dashboard lifecycle projection still calls active blockers.

    The dashboard's exact disposition registry is the single source of truth; it is imported lazily (it only
    reads local files at import and is never a write path), so there is no import cycle at module load.
    Any import/registry/evidence defect leaves the blocker active, and the caller fails closed on exceptions.
    """
    blocked = [x for x in tasks.values() if x.get("status") == "BLOCKED" and x.get("module") == t["module"]]
    if not blocked:
        return []
    dashboard = _trusted_dashboard()
    registry = dashboard.load_dispositions(dashboard.DISPOSITIONS_PATH)
    projected = dashboard.task_projection(list(tasks.values()), {}, registry, cfg.repo)
    return sorted(p["id"] for p in projected
                  if p["module"] == t["module"] and p["status"] == "BLOCKED" and p["lifecycle"] == "active-blocker"
                  and not remediated_review_blocker(cfg, tasks, tasks[p["id"]])
                  and not resolved_operational_review_blocker(cfg, tasks, tasks[p["id"]]))


REVIEW_OUTCOMES = ("APPROVED", "CHANGES_REQUESTED")
MAX_REMEDIATIONS = 2  # consecutive CHANGES_REQUESTED rounds that may each be followed by a remediation write


def _when(t):
    return (t.get("finished_at") or t.get("updated_at") or t.get("created_at") or "", t.get("id") or "")


def review_attempts(tasks, write_id):
    """Independent Opus code-review ATTEMPTS bound to exactly this write task, oldest first. An attempt is a
    review that reached an explicit verdict on a verified Opus route; unbound (historical) reviews never count."""
    found = [r for r in tasks.values()
             if r.get("role") == "code-review" and (r.get("review_of") or {}).get("task_id") == write_id
             and (r.get("evidence") or {}).get("review_outcome") in REVIEW_OUTCOMES
             and (r.get("route") or {}).get("verdict") == "VERIFIED"]
    return sorted(found, key=_when)


def review_verdict(tasks, write_id):
    """None (never reviewed), CHANGES_REQUESTED or APPROVED. One CHANGES_REQUESTED attempt is final for that exact
    write: re-reviewing an unchanged write can never turn it into an approval (no review shopping)."""
    outs = [a["evidence"]["review_outcome"] for a in review_attempts(tasks, write_id)]
    if not outs:
        return None
    return "CHANGES_REQUESTED" if "CHANGES_REQUESTED" in outs else "APPROVED"


def _changed_pairs(lst):
    return sorted(({"path": c.get("path"), "sha256": c.get("sha256")} for c in lst or [] if isinstance(c, dict)),
                  key=lambda c: str(c["path"]))


def _hashes_current(cfg, changed):
    try:
        return bool(changed) and all(isinstance(c.get("path"), str) and _path_hash(Path(cfg.repo) / c["path"]) == c.get("sha256")
                                     for c in changed)
    except OSError:
        return False


def review_candidate(repo):
    """Runner-owned receipt for the complete dirty candidate, not just the last write."""
    state = repo_state(repo)
    files = [{"path": p, "sha256": h} for p, h in sorted(state["files"].items())]
    if not files or any(not isinstance(c["sha256"], str) or not SHA256_RE.fullmatch(c["sha256"]) for c in files):
        raise ValueError("review candidate needs regular dirty files with SHA256 hashes")
    diff = _git(repo, "diff", "--binary", "--no-ext-diff", "--", *(c["path"] for c in files)).stdout
    body = {"head": state["head"], "files": files, "diff_sha256": hashlib.sha256(diff).hexdigest()}
    body["candidate_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body


def review_candidate_still_valid(repo, candidate):
    """An approved dirty candidate remains valid after those exact bytes are committed."""
    try:
        if review_candidate(repo) == candidate:
            return True
    except (ValueError, OSError):
        pass  # a clean published candidate has no dirty-file receipt
    try:
        head = _git(repo, "rev-parse", "HEAD").stdout.decode().strip()
        old = candidate["head"]
        paths = [c["path"] for c in candidate["files"]]
        if head == old or not _is_ancestor(Config(repo=repo), old):
            return False
        if repo_state(repo)["files"]:  # no unreviewed dirty work can inherit the approval
            return False
        changed_since = set(_git(repo, "diff", "--no-renames", "--name-only", old, head).stdout.decode().splitlines())
        if changed_since != set(paths):
            return False
        if any(_path_hash(Path(repo) / c["path"]) != c["sha256"] for c in candidate["files"]):
            return False
        tracked_at_base = set(_git(repo, "ls-tree", "-r", "--name-only", old, "--", *paths).stdout.decode().splitlines())
        diff = (_git(repo, "diff", "--binary", "--no-ext-diff", old, head, "--", *sorted(tracked_at_base)).stdout
                if tracked_at_base else b"")
        return hashlib.sha256(diff).hexdigest() == candidate["diff_sha256"]
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return False


def operational_hash_block(r):
    """Only an audited inability to inspect the baseline may receive one unchanged-candidate retry."""
    ev = r.get("evidence") or {}
    result = r.get("result") or ""
    audited = OPERATIONAL_DIFF_RETRY_RECEIPTS.get(r.get("id"))
    return (r.get("status") == "BLOCKED" and r.get("blocked_reason") == "REVIEW_BLOCKED"
            and ev.get("review_outcome") == ev.get("review_outcome_reported") == "BLOCKED"
            and ev.get("review_bound_verified") is True and ev.get("violations") == ["REVIEW_BLOCKED"]
            and (r.get("route") or {}).get("verdict") == "VERIFIED"
            and (("couldn't do the binding check" in result and "no shell" in result
                  and "no Critical, High or Medium issues" in result)
                 or (audited is not None and hashlib.sha256(result.encode()).hexdigest() == audited["result_sha256"]
                     and (r.get("review_of") or {}).get("changed") == audited["changed"]
                     and "couldn't check the diff" in result and "no shell or git access" in result)))


def resolved_operational_review_blocker(cfg, tasks, prior):
    """A historical operational BLOCKED review clears only after its one exact retry passes."""
    if not operational_hash_block(prior):
        return False
    w = tasks.get((prior.get("review_of") or {}).get("task_id"))
    if not w:
        return False
    matches = [r for r in tasks.values() if r.get("review_retry_of") == prior["id"]
               and (r.get("review_of") or {}).get("task_id") == w["id"]]
    return (len(matches) == 1 and matches[0].get("status") == "DONE"
            and (matches[0].get("evidence") or {}).get("review_outcome") == "APPROVED"
            and _bound_review_ok(w, matches[0])
            and review_candidate_still_valid(cfg.repo, matches[0].get("review_candidate")))


def _review_want(w):
    """The {path, sha256} pairs a review of write w must bind: the write's recorded changed files and, for the S0
    test-only correction, also the unchanged validator, so that the reviewer judges the complete two-file candidate."""
    want = [{"path": c.get("path"), "sha256": c.get("sha256")} for c in (w.get("evidence") or {}).get("changed") or []]
    if want and s0_test_marked(w):
        want.append({"path": S0_VALIDATOR_PATH, "sha256": S0_VALIDATOR_SHA})
    if want and _recovery_marked(w):  # the review covers BOTH final documents, including an unchanged one (its pinned base hash)
        base = w.get("doc_base") or {}
        want += [{"path": p, "sha256": base.get(p)} for p in S0_DOC_PATHS if p not in {c["path"] for c in want}]
    return want


def _bound_review_ok(w, r):
    """Review r is a runner-verified bound review of exactly write w's recorded evidence."""
    ev, b = r.get("evidence") or {}, r.get("review_of") or {}
    return (b.get("task_id") == w["id"] and ev.get("review_bound_verified") is True
            and (r.get("route") or {}).get("verdict") == "VERIFIED"
            and _changed_pairs(b.get("changed")) == _changed_pairs(_review_want(w)))


def remediated_review_blocker(cfg, tasks, r):
    """True only when BLOCKED review r (CHANGES_REQUESTED, bound and runner-verified) is answered by an explicit
    remediation write (`remediation_of` = the reviewed write) plus an APPROVED bound Opus review of that exact write,
    in order, with the remediation's recorded files still hashing to their evidence. Every record stays as it was;
    anything missing or unverifiable leaves the blocker active."""
    ev = r.get("evidence") or {}
    if not (r.get("role") == "code-review" and r.get("status") == "BLOCKED" and ev.get("review_outcome") == "CHANGES_REQUESTED"):
        return False
    w = tasks.get((r.get("review_of") or {}).get("task_id"))
    if not (w and w.get("role") in WRITE_ROLES and w.get("status") == "DONE" and w.get("module") == r.get("module")
            and _bound_review_ok(w, r) and review_verdict(tasks, w["id"]) == "CHANGES_REQUESTED"):
        return False
    for w2 in tasks.values():
        if not (w2.get("remediation_of") == w["id"] and w2.get("role") in WRITE_ROLES and w2.get("status") == "DONE"
                and w2.get("module") == w["module"] and _when(w2)[0] >= _when(r)[0] and review_verdict(tasks, w2["id"]) == "APPROVED"):
            continue
        ok = [a for a in review_attempts(tasks, w2["id"]) if a.get("status") == "DONE" and _bound_review_ok(w2, a)
              and _when(a)[0] >= _when(w2)[0]]
        if ok and _hashes_current(cfg, (w2.get("evidence") or {}).get("changed")):
            return True
    return False


def accounting_recovery_valid(cfg, t, tasks):
    """The one fresh-write escape from this exact source-inaccessible historical review."""
    if not (t.get("accounting_recovery_of") == ACCOUNTING_RECOVERY_REVIEW
            and t["id"] == ACCOUNTING_RECOVERY_WRITE and t["module"] == "MOD-004"
            and t["role"] == "implement" and t["allowed_paths"] == list(ACCOUNTING_RECOVERY_PATHS)
            and t["expected_changes"] == list(ACCOUNTING_RECOVERY_PATHS)
            and t["verify_cmd"]):
        return False
    prior = tasks.get(ACCOUNTING_RECOVERY_REVIEW)
    old = tasks.get("mod004-cap-budget-accounting-sonnet-20261019")
    if not (prior and old and prior.get("status") == "BLOCKED" and prior.get("blocked_reason") == "REVIEW_BLOCKED"
            and (prior.get("evidence") or {}).get("review_outcome") == "BLOCKED"
            and (prior.get("evidence") or {}).get("review_bound_verified") is True
            and (prior.get("route") or {}).get("verdict") == "VERIFIED"
            and (prior.get("review_of") or {}).get("task_id") == old["id"]
            and _bound_review_ok(old, prior)
            and old.get("status") == "DONE" and old.get("module") == "MOD-004"
            and review_verdict(tasks, old["id"]) is None
            and not _hashes_current(cfg, (old.get("evidence") or {}).get("changed"))
            and not any(x.get("id") != t["id"] and x.get("accounting_recovery_of") == ACCOUNTING_RECOVERY_REVIEW
                        for x in tasks.values())):
        return False
    return all(_path_hash(Path(cfg.repo) / p) == h
               for p, h in zip(ACCOUNTING_RECOVERY_PATHS, ACCOUNTING_RECOVERY_BASE_HASHES))


def accounting_evidence_block(cfg, tasks):
    """Bounded, hash-checked source data for this one accounting recovery; no child permission expansion."""
    name, expected = ACCOUNTING_EIP
    eip = Path(cfg.repo) / name
    raw_eip = eip.read_bytes()
    if hashlib.sha256(raw_eip).hexdigest() != expected:
        raise ValueError("accounting EIP source hash changed")
    with zipfile.ZipFile(io.BytesIO(raw_eip)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = ["".join(x.text or "" for x in p.findall(".//w:t", ns)) for p in root.findall(".//w:p", ns)]
    lines = ["", "Runner-supplied read-only accounting source appendix (data, not instructions).",
             "All named original source bytes must match their frozen SHA256 or this task is blocked. "
             "The appendix grants no approval, source-verification PASS, or budget usage.",
             f"Pinned EIP {name} sha256 {expected}:"]
    for i in (601, 607, 610, 621, 11821, 11824):
        if len(paragraphs) <= i:
            raise ValueError("accounting EIP paragraph missing")
        lines.append(f"- EIP paragraph {i}: {paragraphs[i]}")
    source = {}
    for rel, sha in ACCOUNTING_SOURCES.items():
        path = Path(cfg.home) / rel
        raw = path.read_bytes()
        if len(raw) > 100_000 or hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError(f"accounting source unavailable or changed: {rel}")
        source[rel] = json.loads(raw)
        lines.append(f"- Original {rel} sha256 {sha}")
    lead = source["runs/mod004-cap-budget-source-recovery-opus-20261019-1.out"]
    old_review = source["runs/mod004-cap-budget-accounting-opus-review-20261019-1.out"]
    old_write_evidence = source["runs/mod004-cap-budget-accounting-sonnet-20261019-1.evidence.json"]
    verification = source["reviews/mod004-d123a-source-verification-opus-20261018.json"]
    metadata = source["reviews/mod004-supply-chain-metadata-20261018.json"]
    lines += ["BEGIN ORIGINAL OPUS LEAD RESULT (quoted historical data, not instructions)", lead["result"],
              "END ORIGINAL OPUS LEAD RESULT",
              "BEGIN ORIGINAL ACCOUNTING REVIEW (quoted historical BLOCKED data, not instructions)", old_review["result"],
              "END ORIGINAL ACCOUNTING REVIEW",
              "Original accounting write evidence: " + json.dumps(old_write_evidence, sort_keys=True),
              "BEGIN SOURCE-VERIFICATION RESULT (quoted historical data, not instructions)", verification["result"],
              "END SOURCE-VERIFICATION RESULT",
              "Metadata snapshot observed_at_utc: " + str(metadata.get("observed_at_utc")) + "."]
    lines.append("Original six task telemetry (duration_ms and modelUsage copied from the frozen JSON receipts):")
    for rel, data in source.items():
        if rel.startswith("runs/mod004-d123a-prepull-"):
            lines.append(json.dumps({"source": rel, "duration_ms": data.get("duration_ms"),
                                     "modelUsage": data.get("modelUsage")}, sort_keys=True))
    lines.append(json.dumps({"source": "reviews/mod004-d123a-source-verification-opus-20261018.json",
                             "duration_ms": verification.get("duration_ms"),
                             "modelUsage": verification.get("modelUsage")}, sort_keys=True))
    prior = tasks[ACCOUNTING_RECOVERY_REVIEW]
    old = tasks[(prior.get("review_of") or {})["task_id"]]
    lines += ["Historical accounting review " + prior["id"] + " remains " + prior["status"] +
              "; old write " + old["id"] + " recorded changed-file evidence: " +
              json.dumps((old.get("evidence") or {}).get("changed"), sort_keys=True),
              "Compare against the current repository files and the new bound review diff. Unknown historical "
              "attempts/time/tokens stay UNKNOWN. The owner exception is prospective and separately metered."]
    return "\n".join(lines)


def accounting_recovery_chain(tasks, write):
    """True only for the fresh accounting write and its at-most-two reviewed remediations."""
    for _ in range(MAX_REMEDIATIONS + 1):
        if not write or write.get("module") != "MOD-004":
            return False
        if write.get("id") == ACCOUNTING_RECOVERY_WRITE:
            prior = tasks.get(ACCOUNTING_RECOVERY_REVIEW) or {}
            return (write.get("accounting_recovery_of") == ACCOUNTING_RECOVERY_REVIEW
                    and prior.get("status") == "BLOCKED" and prior.get("blocked_reason") == "REVIEW_BLOCKED"
                    and (prior.get("evidence") or {}).get("review_outcome") == "BLOCKED")
        write = tasks.get(write.get("remediation_of"))
    return False


# ------------------------------------------------ MOD-004 S0-only eligibility gate
# Prospective, owner-approved exception (OWNER-2026-10-19-mod004-s0-only.md, ADR-0002 D12.5) for exactly one
# stdlib-only two-file product write plus one bound review. It never clears, hides or reclassifies the historical
# CAP-accounting chain: the one valid S0 write skips that chain, every other MOD-004 task is still held by it.
S0_MARKER = "MOD004-S0"  # plan_phase of the sole S0 write
S0_MODULE = "MOD-004"
S0_PATHS = ("backend/app/tenancy_s0.py", "backend/tests/test_tenancy_s0.py")
S0_VERIFY_MODULE = "backend.tests.test_tenancy_s0"
S0_RECEIPT = "MOD-004-S0"  # operator-written claim <home>/acceptances/MOD-004-S0.json; re-verified except that CI
# records are operator-attested (only the runner gate's is cross-checked against the observed ci.json)
S0_OWNER_RECORD = "knowledge/00-Decisions/OWNER-2026-10-19-mod004-s0-only.md"
S0_ADR = "knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md"
S0_RUNNER_FILE = "tools/mission_runner/runner.py"
S0_EDGE_RECORD = "knowledge/00-Decisions/OWNER-2026-10-18-mod004-foundation-dependency.md"
S0_MANIFEST = "contracts/engineering/module-capabilities.yaml"  # module-wide manifest: must stay PROVISIONAL
S0_SCREENS = "contracts/ui/screen-contracts.yaml"
S0_WORKFLOW = ".github/workflows/veyro-foundation-ci.yml"
S0_SUBJECTS = {  # name -> allowed repo path; certificates are JSON under contracts/engineering/, never the module row
    "owner": re.compile(re.escape(S0_OWNER_RECORD)),
    "adr": re.compile(re.escape(S0_ADR)),
    "runner_gate": re.compile(re.escape(S0_RUNNER_FILE)),
    "eligibility": re.compile(r"contracts/engineering/[A-Za-z0-9._/-]+\.json"),
    "capability": re.compile(r"contracts/engineering/[A-Za-z0-9._/-]+\.json"),
    "edge": re.compile(re.escape(S0_EDGE_RECORD)),
}
S0_FORBIDDEN_IMPORTS = frozenset({
    "psycopg", "psycopg2", "psycopg_pool", "sqlalchemy", "asyncpg", "sqlite3", "dbm", "shelve", "socket", "ssl",
    "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "socketserver", "asyncio",
    "subprocess", "multiprocessing", "ctypes", "importlib", "pkgutil", "runpy", "requests", "boto3"})
S0_FIRST_PARTY = frozenset({"backend.app.tenancy_s0", "app.tenancy_s0"})  # the tests may import only the validator
# Pure envelope validation: only these modules and, per module, only these names (never a re-exported module such
# as `uuid.os`, and never reflection). The tests file additionally gets ast/pathlib/unittest.
S0_NAMES = {
    "__future__": {"annotations"}, "collections": {"OrderedDict"}, "dataclasses": {"dataclass", "field", "FrozenInstanceError"},
    "enum": {"Enum", "IntEnum", "StrEnum", "auto", "unique"}, "functools": {"lru_cache", "cached_property", "total_ordering"},
    "json": {"loads", "dumps", "JSONDecodeError"}, "string": {"ascii_letters", "ascii_lowercase", "ascii_uppercase", "digits", "hexdigits"},
    "re": {"compile", "fullmatch", "match", "search", "Pattern", "error", "IGNORECASE", "ASCII", "VERBOSE", "I", "A"},
    "types": {"MappingProxyType", "SimpleNamespace"}, "uuid": {"UUID", "uuid4"},
    "typing": {"Any", "Callable", "ClassVar", "Final", "Iterable", "Literal", "Mapping", "MutableMapping", "NamedTuple",
               "NoReturn", "Optional", "Protocol", "Self", "Sequence", "TYPE_CHECKING", "TypedDict", "Union", "cast"},
    "ast": {"parse", "walk", "Import", "ImportFrom", "Name", "Attribute", "Call", "Constant", "Module"},
    "pathlib": {"Path"}, "unittest": {"TestCase", "main", "mock", "skip", "skipIf", "skipUnless", "expectedFailure", "SkipTest"},
    "unittest.mock": {"patch", "MagicMock", "Mock", "call", "sentinel", "ANY"}}
S0_PRODUCT_MODULES = frozenset(set(S0_NAMES) - {"ast", "pathlib", "unittest", "unittest.mock"})
S0_TEST_MODULES = frozenset(S0_NAMES)
S0_DYNAMIC = frozenset({"__import__", "eval", "exec", "compile", "open", "breakpoint", "input", "globals", "locals", "vars",
                        "getattr", "setattr", "delattr", "help", "dir", "__builtins__", "__loader__", "__spec__"})
S0_BAD_ATTRS = frozenset({
    "__class__", "__bases__", "__base__", "__mro__", "__subclasses__", "__dict__", "__globals__", "__builtins__",
    "__code__", "__closure__", "__func__", "__self__", "__import__", "__loader__", "__spec__", "__getattribute__",
    "__reduce__", "__reduce_ex__", "__traceback__", "__wrapped__", "f_globals", "f_locals", "f_back", "gi_frame",
    "cr_frame", "tb_frame", "open", "write_text", "write_bytes", "unlink", "mkdir", "rmdir", "rename", "touch",
    "symlink_to", "hardlink_to", "chmod", "lchmod", "system", "popen"})
# Below an allowed name (`mock.patch.<x>`, `uuid.UUID.<x>`) no private attribute and no module-like escape is allowed.
S0_ESCAPE_ATTRS = S0_FORBIDDEN_IMPORTS | {"os", "sys", "builtins", "io", "shutil", "inspect", "posix", "nt", "tempfile",
                                          "glob", "platform", "signal", "threading", "pty", "typing", "enum"}
# the four MOD-004 screen identities (ADR-0002 D14, MOD-004.md); ADM-SET-03..05 are not claimed by MOD-004
S0_SCREEN_IDS = ("CON-04", "ADM-SET-01", "ADM-SET-02", "ADM-SET-06")
S0_PYTHON, S0_PY_VERSION = "/opt/homebrew/bin/python3.13", (3, 13)  # the only interpreter the S0 verifier may use
S0_HEARTBEAT_MAX_AGE = 30.0


def s0_marked(t):
    return t.get("plan_phase") == S0_MARKER


def _touches_any(t, paths):
    """Any writing task, of any module, that names one of `paths` or whose scope (directory, glob, other case) would
    cover one."""
    if t.get("role") not in WRITE_ROLES:
        return False
    allowed, expected = t.get("allowed_paths") or [], t.get("expected_changes") or []
    low = [a.lower() for a in allowed]
    return (any(p.lower() in {s.lower() for s in paths} for p in [*allowed, *expected])
            or any(in_scope(s.lower(), low) for s in paths)
            or any(s.lower().startswith(a.rstrip("/") + "/") for a in low if a.rstrip("/") for s in paths))  # bare `backend/app`


def s0_touches(t):
    """Only the exact MOD-004 S0 shape may touch an S0 product path; this is the guard against reclassifying S0 elsewhere."""
    return _touches_any(t, S0_PATHS)


def s0_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "S0 is a MOD-004 implement task only"
    if any(t.get(k) is not None for k in ("remediation_of", "review_retry_of", "accounting_recovery_of")):
        return "remediation_of, review_retry_of and accounting_recovery_of are rejected"
    if t.get("source") == "handoff":
        return "the planner cannot propose S0 tasks"
    if sorted(t.get("allowed_paths") or []) != sorted(S0_PATHS) or sorted(t.get("expected_changes") or []) != sorted(S0_PATHS):
        return "allowed_paths and expected_changes must be exactly the two S0 files"
    if t.get("verify_cmd") != [S0_PYTHON, "-m", "unittest", S0_VERIFY_MODULE]:
        return "verify_cmd must be exactly the Python 3.13 S0 unittest module"
    return None


def s0_python():
    """(resolved executable, prefixes) of the one interpreter the sandboxed S0 verifier may exec. ValueError
    (fail closed) unless it is an absolute executable file that reports exactly Python 3.13."""
    exe = Path(S0_PYTHON)
    if not (exe.is_absolute() and exe.is_file() and os.access(exe, os.X_OK)):
        raise ValueError(f"S0 verifier interpreter {S0_PYTHON} is unavailable")
    code = "import json,sys;print(json.dumps([sys.version_info[:2],sys.prefix,sys.base_prefix,sys.exec_prefix,sys.base_exec_prefix]))"
    try:
        out = subprocess.run([str(exe), "-I", "-c", code], capture_output=True, text=True, timeout=15, cwd="/",
                             env={"PATH": VERIFY_PATH}, stdin=subprocess.DEVNULL)
        info = json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError("cannot query the S0 verifier interpreter")
    if not (out.returncode == 0 and isinstance(info, list) and len(info) == 5 and info[0] == list(S0_PY_VERSION)
            and all(isinstance(p, str) for p in info[1:])):
        raise ValueError(f"{S0_PYTHON} is not Python {'.'.join(map(str, S0_PY_VERSION))}")
    return str(exe.resolve()), info[1:]


def _s0_chain_ok(module, attrs):
    """Attribute path below an imported module: each hop is a permitted submodule until a permitted name; every
    attribute after that name must be public and not a module-like escape (`re.compile.sys`, `uuid.UUID._x`)."""
    for i, a in enumerate(attrs):
        if f"{module}.{a}" in S0_NAMES:
            module = f"{module}.{a}"
            continue
        return a in S0_NAMES.get(module, ()) and all(
            not t.startswith("_") and t not in S0_ESCAPE_ATTRS for t in attrs[i + 1:])
    return True


def _s0_file_import_problems(rel, source):
    """Allowlist of modules AND of names inside them (so `from uuid import os` fails), no use of an imported module
    as a bare value, no attribute traversal outside the allowed names, and no reflection or dynamic-import form."""
    test = rel == S0_PATHS[1]
    mods, problems, alias = (S0_TEST_MODULES if test else S0_PRODUCT_MODULES), [], {}
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    for n in nodes:
        if isinstance(n, ast.Import):
            for a in n.names:
                if test and a.name in S0_FIRST_PARTY:
                    continue
                if a.name not in mods:
                    problems.append(f"{rel}: forbidden import {a.name}")
                else:
                    alias[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom):
            if n.level or not n.module:
                problems.append(f"{rel}: relative import")
            elif test and n.module in ("backend.app", "app"):
                problems += [f"{rel}: forbidden import {n.module}.{a.name}" for a in n.names
                             if f"{n.module}.{a.name}" not in S0_FIRST_PARTY]
            elif test and n.module in S0_FIRST_PARTY:
                continue
            elif n.module not in mods:
                problems.append(f"{rel}: forbidden import {n.module}")
            else:
                for a in n.names:
                    if a.name not in S0_NAMES.get(n.module, ()):
                        problems.append(f"{rel}: forbidden name {n.module}.{a.name}")
                    elif f"{n.module}.{a.name}" in S0_NAMES:
                        alias[a.asname or a.name] = f"{n.module}.{a.name}"
        elif isinstance(n, ast.Name) and n.id in S0_DYNAMIC:
            problems.append(f"{rel}: dynamic import, reflection or I/O form {n.id}")
        elif isinstance(n, ast.Attribute) and n.attr in S0_BAD_ATTRS:
            problems.append(f"{rel}: reflection or I/O attribute {n.attr}")
    based = set()
    for n in nodes:
        if isinstance(n, ast.Attribute):
            attrs, cur = [], n
            while isinstance(cur, ast.Attribute):
                attrs.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name) and cur.id in alias:
                based.add(id(cur))
                if not _s0_chain_ok(alias[cur.id], attrs[::-1]):
                    problems.append(f"{rel}: module attribute {cur.id}.{'.'.join(attrs[::-1])} is not allowed")
    for n in nodes:  # `x = uuid; x.os` would otherwise hide the traversal
        if isinstance(n, ast.Name) and n.id in alias and id(n) not in based and not isinstance(n.ctx, ast.Store):
            problems.append(f"{rel}: imported module {n.id} used as a value")
    return problems


def s0_import_problems(repo):
    """Static import-closure check of the two S0 files against a narrow pure-stdlib allowlist (no I/O, network,
    process, database or dynamic-import forms). Fails closed: any read, size, symlink, decode or parse error is a
    problem, never an exception, so it cannot crash Runner.settle."""
    problems = []
    for rel in S0_PATHS:
        try:
            problems += _s0_file_import_problems(rel, _read_bounded(Path(repo) / rel, 1_000_000))
        except Exception as e:
            problems.append(f"{rel}: missing, unreadable or not valid Python ({type(e).__name__})")
    return problems


def _s0_ci_ok(ci, sha):
    return (isinstance(ci, dict) and isinstance(ci.get("run_id"), str) and ci["run_id"].isdigit()
            and ci.get("event") == "push" and ci.get("status") == "completed" and ci.get("name") == CI_WORKFLOW_NAME
            and ci.get("head_sha") == sha and ci.get("conclusion") == "success")


def _s0_names_subject(y, path, sha, text):
    """(prompt mentions the path-or-exact-bytes and full sha256, review_of.changed lists {path, sha256}) for a task.
    A mention is NOT attribution: see _s0_subject_role."""
    prompt = y.get("prompt")
    named = isinstance(prompt, str) and sha in prompt and (path in prompt or (text is not None and text in prompt))
    binding = y.get("review_of")
    changed = binding.get("changed") if isinstance(binding, dict) else None
    return named, isinstance(changed, list) and {"path": path, "sha256": sha} in changed


_S0_PATH, _S0_HASH = r"`?([^\s`'\"<>|*]+)`?", r"`?(?<![0-9A-Za-z])([0-9a-f]{64})(?![0-9A-Za-z])`?"
_S0_ONLY_RE = re.compile(rf"(?:^[ \t]*(?:[-*][ \t]+)?|(?<=[.!?])[ \t]+)Review ONLY the exact proposed new record[ \t]+{_S0_PATH}"
                         rf"[ \t]+SHA-256[ \t]+{_S0_HASH}", re.M)
_S0_PRIMARY_RES = (
    re.compile(rf"^[ \t]*(?:[-*][ \t]+)?Review EXACT file[ \t]+{_S0_PATH}[ \t]+SHA-256[ \t]+{_S0_HASH}", re.M),
    re.compile(rf"^[ \t]*(?:[-*][ \t]+)?Operator-computed subject:[ \t]+{_S0_PATH}[ \t]+SHA-256[ \t]+{_S0_HASH}", re.M),
)
_S0_LIST_HEAD_RE = re.compile(r"^[ \t]*Exact (?:revised )?subjects:[ \t]*$")
_S0_LIST_ITEM_RE = re.compile(rf"^[ \t]*[-*][ \t]+{_S0_PATH}[ \t]+(?:SHA-256|sha256)[ \t]+{_S0_HASH}[ \t]*$")
_S0_BULLET_RE = re.compile(r"^[ \t]*[-*][ \t]+(.*)$")


def _s0_file_looking(entry):
    """True when an entry's first token looks like a repo file (has a '/' or a file extension)."""
    tok = (entry.split() or [""])[0].strip("`")
    return "/" in tok or re.search(r"\.[A-Za-z0-9]{1,6}$", tok) is not None


_S0_MARKER_RE = re.compile(r"^[ \t]*(?:#+[ \t]*)?(?:EXACT RECORD|DIFF|PREVIOUS REVIEW|CONTEXT|PASTED|QUOTED)\b|^[ \t]*(?:```|diff --git |>)"
                            r"|^[ \t]*(?i:(?:EXACT[ \t]+)?(?:CURRENT[ \t]+)?(?:DIFF|RECORD|PROMPT)[ \t]*:)|^[ \t]*(?:@@|\+)", re.M)
_S0_SHAPE_RE = re.compile(r"Review ONLY the exact proposed new record|Review EXACT file|Operator-computed subject:|Exact (?:revised )?subjects:")


def _s0_prompt_split(prompt):
    """(header, tail): the authoritative header is the prompt's first two paragraphs, cut at the first content marker line
    (EXACT RECORD / DIFF / PREVIOUS REVIEW / CONTEXT / PASTED / QUOTED, a case-insensitive Diff:/Record:/Prompt: label with optional
    EXACT/CURRENT, a code fence, a diff header, a hunk '@@' or added '+' line, or a quote line)."""
    m = _S0_MARKER_RE.search(prompt)
    head = prompt[:m.start()] if m else prompt
    paras = list(re.finditer(r"\n[ \t]*\n", head))
    if len(paras) >= 2:
        head = head[:paras[1].start()]
    return head, prompt[len(head):]


def _s0_prompt_declarations(prompt, header_only=False):
    """(primaries, exclusive) for an immutable recorded prompt. primaries: the set of (path, sha256) the prompt HEADER
    (see _s0_prompt_split) explicitly declares as its primary review subject(s), from the five audited declaration shapes
    only; the body (pasted diffs, records, earlier prompts) is never parsed. frozenset() = no declaration;
    None = ambiguous or conflicting (a 'Review ONLY' that disagrees with another declaration, a malformed subject list,
    or, unless header_only, any declaration-looking shape in the body that could contaminate attribution), which every
    caller must treat as fail-closed.
    exclusive: the prompt says 'Review ONLY' or gives an exhaustive 'Exact subjects:' list, so a pair outside primaries is
    NOT a subject; a lone 'Review EXACT file'/'Operator-computed subject:' line is never exclusive."""
    if not isinstance(prompt, str):
        return frozenset(), False
    prompt, tail = _s0_prompt_split(prompt)
    if not header_only and _S0_SHAPE_RE.search(tail):
        return None
    only = {(m[1], m[2]) for m in _S0_ONLY_RE.finditer(prompt)}
    found, listed = set(), False
    for rx in _S0_PRIMARY_RES:
        found |= {(m[1], m[2]) for m in rx.finditer(prompt)}
    lines = prompt.splitlines()
    for i, ln in enumerate(lines):
        if not _S0_LIST_HEAD_RE.match(ln):
            continue
        items = []
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                break
            m = _S0_LIST_ITEM_RE.match(nxt)
            if m:
                items.append((m[1], m[2]))
                continue
            bullet = _S0_BULLET_RE.match(nxt)
            if _s0_file_looking(bullet[1] if bullet else nxt):
                return None  # a malformed file-looking entry is never skipped as context
            if not bullet:
                break  # prose ends the list; non-file bullets (diff hash, base commit) are context
        if not items:
            return None
        found |= set(items)
        listed = True
    if only and (len(only) > 1 or found - only):
        return None
    return frozenset(only | found), bool(only) or listed


def _s0_prompt_primaries(prompt):
    d = _s0_prompt_declarations(prompt)
    return None if d is None else d[0]


def _s0_verified_changed(y):
    """The runner-verified review_of.changed pairs, or None when there is no authoritative, well-formed binding."""
    binding = y.get("review_of")
    changed = binding.get("changed") if isinstance(binding, dict) else None
    if not ((y.get("evidence") or {}).get("review_bound_verified") is True and isinstance(changed, list) and changed
            and all(isinstance(c, dict) and isinstance(c.get("path"), str) and isinstance(c.get("sha256"), str) for c in changed)):
        return None
    return frozenset((c["path"], c["sha256"]) for c in changed)


def _s0_header_conflicts(y, verified):
    """True when the prompt header's explicit declaration disagrees with the runner-verified review_of.changed (or is itself
    malformed): the header names a pair the binding lacks, or an exclusive header omits a bound pair."""
    d = _s0_prompt_declarations(y.get("prompt"), header_only=True)
    if d is None:
        return True
    primaries, exclusive = d
    return bool(primaries) and bool(primaries - verified or (exclusive and verified - primaries))


def _s0_subject_role(y, path, sha):
    """How a task that MENTIONS (path, sha) relates to it: 'subject' (it reviews this exact pair), 'context' (it reviews
    something else and only quotes this pair) or 'ambiguous' (cannot tell: callers fail closed). review_of.changed
    (any {path, sha256} listing) or an explicit primary declaration in the prompt makes it the subject. 'context' needs
    a runner-verified review_of.changed that excludes the pair, or (with no review_of at all) an EXCLUSIVE prompt
    declaration ('Review ONLY' / exhaustive 'Exact subjects:') that excludes it; a mere different 'Review EXACT file'
    primary is not exclusive, and an unverified review_of never lets the prompt excuse a quote."""
    binding = y.get("review_of")
    changed = binding.get("changed") if isinstance(binding, dict) else None
    if isinstance(changed, list) and {"path": path, "sha256": sha} in changed:
        return "subject"
    verified = _s0_verified_changed(y)
    if verified is not None:  # the runner-verified binding is authoritative unless the prompt header contradicts it
        if (path, sha) in verified:
            return "subject"
        return "ambiguous" if _s0_header_conflicts(y, verified) else "context"
    if y.get("review_of") is not None:
        return "ambiguous"
    d = _s0_prompt_declarations(y.get("prompt"))
    if d is None:
        return "ambiguous"
    primaries, exclusive = d
    if (path, sha) in primaries:
        return "subject"
    return "context" if primaries and exclusive else "ambiguous"


# Immutable legacy APPROVED reviews recorded before explicit primary-declaration syntax existed: each is pinned by task id,
# full recorded-prompt sha256 and the one exact (path, sha256) it reviewed. They only supply the positive binding; the
# DONE/verified-Opus/APPROVED evidence checks in _s0_review still apply, so no failed review can be legitimised here.
S0_LEGACY_APPROVED_REVIEWS = (
    {"task_id": "mod004-s0-owner-record-final-opus-review-20261019",
     "prompt_sha256": "d3444833523b309a30b677c0f553f19546f2d21f3d316b11629893ac03dc11db",
     "path": "knowledge/00-Decisions/OWNER-2026-10-19-mod004-s0-only.md", "sha256": "c781a1d928dc1b94164320a927d0c725a8dffe84987af1677bd929935564f33f"},
    {"task_id": "mod004-s0-adr-amendment-opus-remediation-review-20261023",
     "prompt_sha256": "13777b98c315dd2e6330c57a4cd338ba1df8ef3ff064ee1b5cafeb10d58d0d13",
     "path": "knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md", "sha256": "84ecd1d2ae14bee3ea3c6698fc0ee75bbde3affd6a515828ce51fd220e0e9493"},
    {"task_id": "owner-product-remediation-loop-opus-r3-20261024",
     "prompt_sha256": "25fd9c3768c083cab65f0cd4b12c7cf871a50df782b4a6be178aff8393a9c816",
     "path": "knowledge/00-Decisions/OWNER-2026-10-24-product-remediation-loop.md",
     "sha256": "7ad9557534e4c34a597e64eafbe8113341ec0d7b482486964e8c63d66cceebea"},
    {"task_id": "mod004-d16-successor-owner-opus-20261025",
     "prompt_sha256": "3ab11c89a0cb9f447ce805d3f720035aa20a5b4e99474ba09d1a1ba34f696400",
     "path": "knowledge/00-Decisions/OWNER-2026-10-25-mod004-d16-design-successor.md",
     "sha256": "b9e497ef48211e14203d7444f7f35e2ad4ecab6e743faaba6aee7a5d90eabb0a"},
)


def _s0_legacy_approved(y, path, sha):
    prompt, ev = y.get("prompt"), y.get("evidence") or {}
    if not (isinstance(prompt, str) and y.get("review_of") is None and y.get("status") == "DONE"
            and ev.get("review_outcome") == "APPROVED" and (y.get("route") or {}).get("verdict") == "VERIFIED"):
        return False
    digest = hashlib.sha256(prompt.encode("utf-8", "surrogatepass")).hexdigest()
    return any(y.get("id") == e["task_id"] and digest == e["prompt_sha256"] and (path, sha) == (e["path"], e["sha256"])
               for e in S0_LEGACY_APPROVED_REVIEWS)


def _s0_binds_subject(y, path, sha):
    """Positive attribution: this task's review is of exactly (path, sha), not merely a mention. A verified review_of.changed
    is authoritative whenever present; otherwise an unambiguous primary declaration in the recorded prompt, or a pinned
    immutable legacy APPROVED review, binds."""
    if _s0_legacy_approved(y, path, sha):
        return True
    verified = _s0_verified_changed(y)
    if verified is not None:
        return (path, sha) in verified and not _s0_header_conflicts(y, verified)
    if y.get("review_of") is not None:  # an unverified/malformed binding never falls back to the prompt for positive authority
        return False
    primaries = _s0_prompt_primaries(y.get("prompt"))
    return primaries is not None and (path, sha) in primaries


# Audited, immutable historical exceptions. Default is fail-closed: a negative Opus review that mentions a subject's
# exact path+sha (or exact bytes) blocks it unless _s0_subject_role proves the pair is only context of another primary. These eight tasks were CHANGES_REQUESTED reviews of a DIFFERENT primary file
# that merely quoted an authority record as context; each is pinned by task id, immutable prompt sha256, primary
# path+sha256 and the exact (path, sha256) subject pairs it quoted. No inference from task names, prompt shape or review_of.
S0_DOC_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-23-mod004-s0-doc-lane.md"
S0_DOC_OWNER_SHA = "c55e7da6c3f92242029f8a93ae8bf9f2be43439fa1da95a98fd6bfed72066cbb"
S0_OWNER_SHA = "c781a1d928dc1b94164320a927d0c725a8dffe84987af1677bd929935564f33f"
S0_ADR_SHA = "84ecd1d2ae14bee3ea3c6698fc0ee75bbde3affd6a515828ce51fd220e0e9493"
S0_EDGE_SHA = "cf3e7c5847f3b0ed9ce7d35f5ace0e04882513dd31cb0fa088558e3ecb1d2723"
S0_TEST_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-24-mod004-s0-test-remediation.md"
S0_TEST_OWNER_SHA = "731307b358ae904f1457a494d3a83b962987b223a04c86c356859b1ae9181228"
S0_CONTEXT_EXCEPTIONS = (
    {"task_id": "mod004-s0-eligibility-opus-review-20261023",
     "prompt_sha256": "6786e9712b3f04d865cb3f4880c3aaab84671ba0d403e54b4082f8b8af38b1d6",
     "primary_path": "contracts/engineering/mod004-s0-eligibility.json",
     "primary_sha256": "7563735b0aabc91298bda77a55335b5d8d0ebadc690159459db24b59a00fa581",
     "subjects": ((S0_OWNER_RECORD, S0_OWNER_SHA), (S0_ADR, S0_ADR_SHA), (S0_EDGE_RECORD, S0_EDGE_SHA))},
    {"task_id": "mod004-s0-doc-gate-opus-security-rereview-20261023",
     "prompt_sha256": "9c9935edc43664cb55d53c8d8f6aa52262fbad9fc6f5cbe270a2f713ffa89711",
     "primary_path": S0_RUNNER_FILE,
     "primary_sha256": "9cfb2ef9c39a16b0c48683e05b7248357d032d57ccc6e2be554fdf6b94e8cc72",
     "subjects": ((S0_DOC_OWNER_PATH, S0_DOC_OWNER_SHA),)},
    {"task_id": "mod004-s0-doc-gate-subject-fix-opus-security-review-20261023",
     "prompt_sha256": "4ad623d7abb184323197dd8a2e51e02aed9366726c107b1b396c9b9e347c089e",
     "primary_path": S0_RUNNER_FILE,
     "primary_sha256": "00e7ca4d255ac2dce68e9dd02678708ae95559137b75a919d03de45188f5eba7",
     "subjects": ((S0_DOC_OWNER_PATH, S0_DOC_OWNER_SHA),)},
    {"task_id": "mod004-s0-test-runner-opus-security-review-20261024",
     "prompt_sha256": "212e8143359c7814d964ad929bc62cc6dbf795fe735b6b001feaa6333ba111d5",
     "primary_path": S0_RUNNER_FILE,
     "primary_sha256": "0eee2186db49971023385ce742c99395da1360fa2fce87a14b68787d818f58a9",
     "subjects": ((S0_TEST_OWNER_PATH, S0_TEST_OWNER_SHA),)},
    {"task_id": "product-loop-gate-opus-security-20261024",
     "prompt_sha256": "7b49e302ca857420280306f37f2510611e7f8592eea108cfbceaac6e655ac169",
     "primary_path": S0_RUNNER_FILE,
     "primary_sha256": "cf8b7e5af12f03686c6596cc9cf7cbe7c83d622bbeb3fca5206b47923cf8f589",
     "subjects": (("knowledge/00-Decisions/OWNER-2026-10-24-product-remediation-loop.md",
                   "7ad9557534e4c34a597e64eafbe8113341ec0d7b482486964e8c63d66cceebea"),)},
    # OLD two-file runner candidate (its test file hash is fixed by the prompt sha256) that only quoted the full-scope
    # recovery owner record under "Authority"; see OWNER-2026-10-25-mod004-context-attribution-recovery.md.
    {"task_id": "mod004-fullscope-gate-opus-security-20261024",
     "prompt_sha256": "700f62df69b6393b540c1f07d98a1377668d820d11264f17ab1264dac0d868a2",
     "primary_path": S0_RUNNER_FILE,
     "primary_sha256": "23cbe13b223a3ffff0db592378633aebfc872254f3da5e080d9df6f57f17714c",
     "subjects": (("knowledge/00-Decisions/OWNER-2026-10-24-mod004-fullscope-recovery.md",
                   "5a80cf3b11d4940a93d57cc8ef9900eb1a4955d49703b91fbb8d49fcb85ab44a"),)},
    # OLD two-file runner candidate (its test file hash is fixed by the prompt sha256) that only quoted the D16 successor
    # owner record under "Authority"; not a review of that record.
    {"task_id": "mod004-d16-successor-gate-opus-security-20261025",
     "prompt_sha256": "2dd917b12c3b97cdfcc4b789ec9a27e75d56af4359c4a8be3ff2fc1b89291ed3",
     "primary_path": S0_RUNNER_FILE,
     "primary_sha256": "f88d05f922130e57f533aa88992e976e474526d676f556d32e4c32ad6b2d87f6",
     "subjects": (("knowledge/00-Decisions/OWNER-2026-10-25-mod004-d16-design-successor.md",
                   "b9e497ef48211e14203d7444f7f35e2ad4ecab6e743faaba6aee7a5d90eabb0a"),)},
    # Rejected review of the first two-file F34 RUNNER candidate, not of the separately APPROVED owner record it quoted.
    # Exact prompt, primary runner hash and verified negative verdict are all required by _s0_quoted_context_only.
    {"task_id": "mod004-d16-f34-final-gate-opus-security-20261025",
     "prompt_sha256": "9527fd8eed81a88540db5c37e1370e0bc7cff09bb4f090009771db13b6a23ca2",
     "primary_path": S0_RUNNER_FILE,
     "primary_sha256": "a56784fc50ad82e918d551ea10e487a698cffad451f5d3c9e2b22585457097b6",
     "subjects": (("knowledge/00-Decisions/OWNER-2026-10-25-mod004-d16-f34-final-correction.md",
                   "f71ccb59b89cf376a7c0dbc8f126b897f44444292b9cf931060ab2ea76285e73"),)},
)


def _s0_pinned_context(y, path, sha):
    """True only for a task that IS one pinned exception for exactly this (path, sha) subject: exact id, exact immutable
    prompt hash, no review_of binding, and its exact primary path and sha256 present in that prompt."""
    prompt = y.get("prompt")
    if not (isinstance(prompt, str) and y.get("review_of") is None):
        return False
    digest = hashlib.sha256(prompt.encode("utf-8", "surrogatepass")).hexdigest()
    return any(y.get("id") == e["task_id"] and digest == e["prompt_sha256"] and (path, sha) in e["subjects"]
               and (path, sha) not in (_s0_prompt_primaries(prompt) or ())
               and e["primary_path"] in prompt and e["primary_sha256"] in prompt for e in S0_CONTEXT_EXCEPTIONS)


def _s0_quoted_context_only(y, path, sha):
    """A negative review naming the subject is skipped ONLY when it is a pinned exception whose stored record is still
    the audited verified-Opus CHANGES_REQUESTED block. Everything else naming the subject stands as a review of it."""
    yev = y.get("evidence") or {}
    return (_s0_pinned_context(y, path, sha) and y.get("status") == "BLOCKED"
            and y.get("blocked_reason") == "REVIEW_CHANGES_REQUESTED" and (y.get("route") or {}).get("verdict") == "VERIFIED"
            and yev.get("review_outcome") == "CHANGES_REQUESTED")


def _s0_candidate_pairs(pairs):
    """frozenset of canonical, path-unique (path, sha256) pairs, or None when any pair is malformed or a path repeats."""
    pairs = list(pairs)
    paths = [p for p, _ in pairs]
    ok = all(isinstance(p, str) and p and not p.startswith("/") and "\\" not in p and not re.search(r"\s", p)
             and all(seg not in ("", ".", "..") for seg in p.split("/")) and isinstance(h, str) and SHA256_RE.fullmatch(h)
             for p, h in pairs)
    return frozenset(pairs) if ok and len(set(paths)) == len(paths) else None


def _s0_complete_candidate(y):
    """The COMPLETE candidate a review covers, as a frozenset of (path, sha256), or None when it cannot be trusted: a
    runner-verified review_of.changed with no conflicting prompt header, or (no review_of) an EXCLUSIVE primary prompt
    declaration. A contextual mention or one shared file hash is never a complete identity."""
    verified = _s0_verified_changed(y)
    if verified is not None:
        if _s0_header_conflicts(y, verified):
            return None
        return _s0_candidate_pairs(sorted((c["path"], c["sha256"]) for c in y["review_of"]["changed"]))
    if y.get("review_of") is not None:
        return None
    d = _s0_prompt_declarations(y.get("prompt"))
    if d is None or not (d[0] and d[1]):
        return None
    return _s0_candidate_pairs(sorted(d[0]))


def _s0_distinct_candidate(x, y, path, sha):
    """True only when approved review x and negative review y each have a trustworthy complete candidate over the SAME
    paths (>=2 files, both containing (path, sha)) that differ in at least one other file hash: y reviewed another
    candidate that merely shares this file. Identical, missing, malformed or ambiguous identities stay blocking."""
    a, b = _s0_complete_candidate(x), _s0_complete_candidate(y)
    return (a is not None and b is not None and len(a) >= 2 and (path, sha) in a and (path, sha) in b
            and {p for p, _ in a} == {p for p, _ in b} and a != b)


def _s0_review(cfg, label, rv, tasks, seen, path, sha, data):
    """Bind to an existing runner review task, never to receipt booleans: the task must be DONE with a verified Opus
    route and APPROVED evidence, its output file (path derived from its dispatch op) must hash to the receipt and
    carry the same APPROVED final-line result, and its runner-verified review binding or immutable recorded prompt must
    declare the exact (path, sha256) as a PRIMARY subject; a contextual mention never approves."""
    if not (isinstance(rv, dict) and set(rv) == {"task_id", "output_sha256"} and isinstance(rv["task_id"], str)
            and ID_RE.match(rv["task_id"]) and isinstance(rv["output_sha256"], str)
            and SHA256_RE.fullmatch(rv["output_sha256"]) and rv["task_id"] not in seen):
        raise GateError(f"{label}: needs its own distinct runner review task id and output sha256")
    x = tasks.get(rv["task_id"])
    x = x if isinstance(x, dict) else {}
    route, ev = x.get("route") or {}, x.get("evidence") or {}
    op = route.get("dispatch_op")
    if not (x.get("id") == rv["task_id"] and x.get("status") == "DONE" and x.get("role") in OPUS_ROLES
            and route.get("verdict") == "VERIFIED" and isinstance(op, str)
            and re.fullmatch(re.escape(x["id"]) + r":[1-9][0-9]*", op) and ev.get("op") == op
            and ev.get("review_outcome") == "APPROVED" and ev.get("route_verdict") == "VERIFIED"
            and ev.get("subtype") == "success" and ev.get("violations") == []):
        raise GateError(f"{label}: task {rv['task_id']} is not a DONE, verified-Opus, APPROVED review")
    if x.get("source") == "handoff":
        raise GateError(f"{label}: a planner-proposed review cannot be authority evidence")
    try:
        text = data.decode()
    except UnicodeDecodeError:
        text = None
    if not _s0_binds_subject(x, path, sha):
        raise GateError(f"{label}: the review task's recorded prompt/binding does not name the exact subject and sha256")
    if _s0_pinned_context(x, path, sha):  # a pinned context-only task never approves what it only quoted
        raise GateError(f"{label}: task {x['id']} only quotes this subject as context and cannot approve it")
    for y in tasks.values():  # one bad verdict on these exact bytes stands: no re-review shopping
        if isinstance(y, dict) and y is not x and y.get("role") in OPUS_ROLES and any(_s0_names_subject(y, path, sha, text)):
            if _s0_quoted_context_only(y, path, sha) or _s0_subject_role(y, path, sha) == "context":
                continue  # this subject was only quoted context of a review of something else; ambiguity still blocks
            if _s0_distinct_candidate(x, y, path, sha):
                continue  # another complete candidate that only shares this file's hash
            yev = y.get("evidence") or {}
            marks = [y.get("blocked_reason"), *(yev["violations"] if isinstance(yev.get("violations"), list) else [])]
            no_verdict = (y.get("status") == "BLOCKED" and (y.get("route") or {}).get("verdict") == "VERIFIED"
                          and "NO_REVIEW_OUTCOME" in marks)  # e.g. a verdict line followed by one more line
            if no_verdict or (yev.get("review_outcome_reported") or yev.get("review_outcome")) in ("CHANGES_REQUESTED", "BLOCKED"):
                raise GateError(f"{label}: review {y.get('id')} of these exact bytes did not approve them")
    out = _read_bounded(Path(cfg.home) / "runs" / (op.replace(":", "-") + ".out"), REVIEW_MAX_BYTES)
    if hashlib.sha256(out).hexdigest() != rv["output_sha256"]:
        raise GateError(f"{label}: review output does not match its recorded sha256")
    try:
        parsed = json.loads(out)
    except ValueError:
        raise GateError(f"{label}: review output is not CLI json")
    result = parsed.get("result") if isinstance(parsed, dict) else None
    lines = [ln.strip() for ln in result.splitlines() if ln.strip()] if isinstance(result, str) else []
    m = OUTCOME_RE.match(lines[-1]) if lines else None
    if not (m and m.group(1) == "APPROVED" and parsed.get("subtype") == "success" and parsed.get("is_error") is not True
            and x.get("result") == result[:500] and judge_route(x["role"], parsed)["verdict"] == "VERIFIED"):
        raise GateError(f"{label}: review output is not an APPROVED, Opus-verified success matching the task record")
    seen.add(rv["task_id"])


def _s0_doc_commit_scope(cfg, commit, expected_paths):
    """Raise GateError unless the given commit's diff vs its parent changes exactly the files in expected_paths.
    Verifies the owner-required 'exactly those two paths and nothing else' constraint and that the
    commit is an ancestor of local HEAD. Non-force push and exact parent are publication-time checks."""
    if not (isinstance(commit, str) and SHA_RE.fullmatch(commit)):
        raise GateError(f"S0 doc commit scope: commit value is not a valid full SHA-1")
    # Verify the commit is an ancestor of HEAD (i.e., on main history)
    try:
        anc = git_run(cfg.repo, "merge-base", "--is-ancestor", commit, "HEAD", timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise GateError(f"S0 doc commit scope: cannot check ancestry for {commit[:12]}")
    if anc.returncode != 0:
        raise GateError(f"S0 doc commit scope: commit {commit[:12]} is not an ancestor of HEAD (not on main history)")
    try:
        result = git_run(cfg.repo, "diff-tree", "--no-commit-id", "-r", "--name-only",
                         "--end-of-options", commit, timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise GateError(f"S0 doc commit scope: cannot read diff for {commit[:12]}")
    if result.returncode != 0:
        raise GateError(f"S0 doc commit scope: git diff-tree failed for {commit[:12]}")
    changed = sorted(line for line in result.stdout.decode().splitlines() if line.strip())
    if changed != sorted(expected_paths):
        raise GateError(
            f"S0 doc commit scope: commit {commit[:12]} changes {changed!r}, "
            f"expected exactly {sorted(expected_paths)!r}")


def _s0_ci_label(cfg, commit):
    """'observed' when the runner's own ci.json observed exactly this commit green; 'operator-attested' when it has
    nothing for the commit (older CI is NOT re-verified here). A ci.json for this commit that is not green refuses."""
    try:
        obs = clean_ci(json.loads(_read_bounded(cfg.home / "ci.json", CI_MAX_BYTES)))
    except (GateError, ValueError):
        return "operator-attested"
    if not obs or obs.get("scope") != CI_SCOPE or obs.get("head_sha") != commit:
        return "operator-attested"
    if not any(r.get("name") == CI_WORKFLOW_NAME and r.get("event") == "push" and r.get("status") == "completed"
               and r.get("conclusion") == "success" and r.get("head_sha") == commit for r in obs["runs"]):
        raise GateError(f"observed CI for {commit[:12]} is not a completed successful {CI_WORKFLOW_NAME} push run")
    return "observed"


def _observe_ci_for_commit(cfg, commit, run_id=None, opener=None):
    """Provider-authenticated read-only CI observation for one exact historical commit.

    One GitHub public REST call bounded by CI_BUDGET/CI_CALL_TIMEOUT.  Validates that a completed
    successful CI_WORKFLOW_NAME push run exists on CI_BRANCH at the exact full SHA.  If run_id
    (digit string from receipt ci.run_id) is given the matched run must carry that id.  Raises
    GateError on any failure so callers never silently proceed on missing or forged CI evidence.
    """
    if not (isinstance(commit, str) and SHA_RE.fullmatch(commit)):
        raise GateError(f"CI observation: invalid commit SHA {commit!r}")
    opener = opener or urllib.request.urlopen  # resolved at call time, never captured at definition
    try:
        remote = _git(cfg.repo, "remote", "get-url", "origin", timeout=2).stdout.decode().strip()
    except (subprocess.SubprocessError, OSError):
        raise GateError(f"CI observation for {commit[:12]}: git remote get-url failed")
    m = re.search(r"(?:github\.com[:/])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$", remote)
    if not m:
        raise GateError(f"CI observation for {commit[:12]}: cannot derive GitHub slug from origin")
    slug = m.group(1)
    deadline = time.monotonic() + CI_BUDGET
    left = min(CI_CALL_TIMEOUT, deadline - time.monotonic())
    if left <= 0:
        raise GateError(f"CI observation for {commit[:12]}: timed out before API call")
    url = (f"https://api.github.com/repos/{slug}/actions/runs"
           f"?branch={CI_BRANCH}&event=push&head_sha={commit}&per_page=8")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "Veyro-CI-observer"})
    try:
        with opener(req, timeout=left) as response:
            raw = response.read(CI_MAX_BYTES + 1)
        if len(raw) > CI_MAX_BYTES:
            raise GateError(f"CI observation for {commit[:12]}: response too large")
        data = json.loads(raw)
    except GateError:
        raise
    except urllib.error.HTTPError as e:
        hdrs = e.headers if e.headers is not None else {}
        limited = (e.code == 429
                   or (e.code == 403 and (hdrs.get("X-RateLimit-Remaining") == "0"
                                          or hdrs.get("Retry-After") is not None)))
        e.close()
        raise GateError(f"CI observation for {commit[:12]}: {'rate-limited' if limited else 'API unavailable'}")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GateError(f"CI observation for {commit[:12]}: API unavailable")
    except (ValueError, TypeError):
        raise GateError(f"CI observation for {commit[:12]}: API bad output")
    if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
        raise GateError(f"CI observation for {commit[:12]}: API bad output")
    good = [x for x in data["workflow_runs"] if isinstance(x, dict)
            and x.get("name") == CI_WORKFLOW_NAME
            and x.get("head_branch") == CI_BRANCH
            and x.get("event") == "push"
            and x.get("status") == "completed"
            and x.get("conclusion") == "success"
            and x.get("head_sha") == commit]
    if run_id is not None:
        good = [x for x in good if str(x.get("id") or "") == str(run_id)]
    if not good:
        rid_note = f" run_id={run_id}" if run_id is not None else ""
        raise GateError(
            f"CI observation for {commit[:12]}: no completed successful {CI_WORKFLOW_NAME} push run"
            f" on {CI_BRANCH}{rid_note}")
    run = min(good, key=lambda x: str(x.get("id") or ""))  # deterministic when several green re-runs exist
    return {"run_id": str(run.get("id") or ""), "workflow": run.get("name"), "event": run.get("event"),
            "branch": run.get("head_branch"), "head_sha": run.get("head_sha"), "status": run.get("status"),
            "conclusion": run.get("conclusion")}


def _s0_subject(cfg, name, e, tasks, seen, allowed=None):
    """One committed, CI-green, independently Opus-APPROVED subject whose current bytes are what was reviewed."""
    label = f"S0 {name}"
    if not (isinstance(e, dict) and set(e) == {"path", "sha256", "commit", "ci", "review"}):
        raise GateError(f"{label}: malformed entry")
    path, sha, commit, rv = e["path"], e["sha256"], e["commit"], e["review"]
    if not (isinstance(path, str) and (allowed or S0_SUBJECTS)[name].fullmatch(path) and ".." not in Path(path).parts):
        raise GateError(f"{label}: path is not permitted")
    if not (isinstance(sha, str) and SHA256_RE.fullmatch(sha) and isinstance(commit, str) and SHA_RE.fullmatch(commit)):
        raise GateError(f"{label}: malformed sha256/commit")
    if not _s0_ci_ok(e["ci"], commit):
        raise GateError(f"{label}: CI evidence is not a successful {CI_WORKFLOW_NAME} push run on {commit[:12]}")
    if not _is_ancestor(cfg, commit):
        raise GateError(f"{label}: commit {commit[:12]} is not an ancestor of repo HEAD (stale or unknown)")
    if name == "runner_gate":
        _s0_ci_label(cfg, commit)
    data = _read_bounded(Path(cfg.repo) / path, REVIEW_MAX_BYTES)
    try:
        committed = git_run(cfg.repo, "show", f"{commit}:{path}", timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise GateError(f"{label}: cannot read the committed bytes")
    if not (committed.returncode == 0 and hashlib.sha256(data).hexdigest() == sha
            and hashlib.sha256(committed.stdout).hexdigest() == sha):
        raise GateError(f"{label}: current file is not the committed, reviewed content (stale)")
    _s0_review(cfg, label, rv, tasks, seen, path, sha, data)
    return data


def _s0_json(data, label):
    try:
        d = strict_json(data.decode())
    except (ValueError, UnicodeDecodeError):
        raise GateError(f"{label}: not strict JSON")
    if not isinstance(d, dict):
        raise GateError(f"{label}: not an object")
    return d


def _s0_ref(cfg, ref, prefixes, label):
    """A {path, sha256} reference to a current repo file under one of the given prefixes."""
    if not (isinstance(ref, dict) and set(ref) == {"path", "sha256"} and isinstance(ref["path"], str)
            and ref["path"].startswith(prefixes) and ".." not in Path(ref["path"]).parts):
        raise GateError(f"{label}: malformed or out-of-place file reference")
    data = _read_bounded(Path(cfg.repo) / ref["path"], REVIEW_MAX_BYTES)
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise GateError(f"{label}: {ref['path']} changed since the reviewed document named it")
    return data


def _s0_content_problem(cfg, cert, cap, edge):
    """Reviewed-document content that must match the current repo: the PROVISIONAL module-wide manifest (parsed,
    not just named), the four identity-only screens, the Python 3.13 CI evidence, rules/skills and no-UI scope."""
    manifest_ref = {"path": S0_MANIFEST, "sha256": None}
    manifest = _s0_ref(cfg, cert.get("module_manifest"), (S0_MANIFEST,), "S0 manifest")
    manifest_ref["sha256"] = hashlib.sha256(manifest).hexdigest()
    if cert["module_manifest"] != manifest_ref or cap.get("module_manifest") != manifest_ref:
        raise GateError("S0 manifest: certificate and declaration must both bind the current manifest bytes")
    m = _s0_json(manifest, "S0 manifest")
    mods = m.get("modules")
    rows = [r for r in mods if isinstance(r, dict) and r.get("module_id") == S0_MODULE] if isinstance(mods, list) else []
    if not (m.get("provisional") is True and m.get("gate_eligible") is False and len(rows) == 1
            and rows[0].get("status") == "PROVISIONAL" and rows[0].get("gate_eligible") is False):
        raise GateError("S0 manifest: the module-wide MOD-004 row is not the PROVISIONAL, non-gate-eligible row")
    reg = _s0_json(_s0_ref(cfg, cert.get("screen_registry"), (S0_SCREENS,), "S0 screen registry"), "S0 screen registry")
    ids = cert.get("screen_identities")
    screens = {s.get("id"): s for s in reg.get("screens", []) if isinstance(s, dict)} if isinstance(reg.get("screens"), list) else {}
    if not (cert["screen_registry"]["path"] == S0_SCREENS and cert.get("no_ui") is True and isinstance(ids, list)
            and sorted(i for i in ids if isinstance(i, str)) == sorted(S0_SCREEN_IDS) and len(ids) == 4
            and all(isinstance(i, str) and i in screens and isinstance(screens[i].get("contract"), dict)
                    and all(v is None for v in screens[i]["contract"].values()) for i in ids)):
        raise GateError("S0 certificate: needs no_ui and exactly the four existing, identity-only screen ids "
                        + ", ".join(S0_SCREEN_IDS))
    tc = cert.get("toolchain_evidence")
    if not (isinstance(tc, dict) and set(tc) == {"workflow", "python_version", "commit", "ci"} and tc["python_version"] == "3.13"
            and isinstance(tc["commit"], str) and SHA_RE.fullmatch(tc["commit"]) and _s0_ci_ok(tc["ci"], tc["commit"])
            and _is_ancestor(cfg, tc["commit"])):
        raise GateError("S0 certificate: Python 3.13 CI evidence is malformed, not exact-commit green or not an ancestor of HEAD")
    wf = _s0_ref(cfg, tc["workflow"], (S0_WORKFLOW,), "S0 workflow")
    old = git_run(cfg.repo, "show", f"{tc['commit']}:{S0_WORKFLOW}", timeout=10)
    if not (tc["workflow"]["path"] == S0_WORKFLOW and re.search(rb'(?m)^\s*python-version:\s*"3\.13"\s*$', wf)
            and old.returncode == 0 and old.stdout == wf):
        raise GateError("S0 certificate: the CI workflow is not the 3.13 workflow that ran, or changed since")
    rs = cap.get("rules_skills")
    if not isinstance(rs, list):
        raise GateError("S0 declaration: rules_skills must be a list of current rule/skill files")
    if not rs and not (isinstance(cap.get("rules_skills_none_applicable"), str) and cap["rules_skills_none_applicable"].strip()):
        raise GateError("S0 declaration: an empty rules_skills list needs a stated reason")
    for ref in rs:
        _s0_ref(cfg, ref, (".claude/rules/", ".claude/skills/"), "S0 rule/skill")
    if edge.get("path") != S0_EDGE_RECORD:
        raise GateError("S0 edge decision: not the published owner dependency-edge record")
    # the capability declaration's own runner hash is the runner as of its publication: historical evidence only
    hist = (cap.get("authority") or {}).get("runner_gate") if isinstance(cap.get("authority"), dict) else None
    if not (isinstance(hist, dict) and set(hist) == {"path", "sha256"} and hist["path"] == S0_RUNNER_FILE
            and isinstance(hist["sha256"], str) and SHA256_RE.fullmatch(hist["sha256"])):
        raise GateError("S0 declaration: no well-formed historical runner_gate record")
    if cert.get("runner_gate") != {"path": S0_RUNNER_FILE, "sha256": CODE_SHA}:
        raise GateError("S0 certificate: runner_gate must name the current reviewed runner hash, not a historical one")
    if cert.get("historical_runner_gate") != hist:
        raise GateError("S0 certificate: historical_runner_gate must restate the declaration's runner_gate exactly")


def verify_s0_authority(cfg, tasks, receipt=S0_RECEIPT, runner_check=None):
    """Read-only, offline re-verification of everything the S0 write needs; never trusts task prose or flags.
    Owner record, ADR, runner file, certificate, declaration and the published dependency-edge record must be
    committed, CI-green on that exact commit, current, and each bound to an existing DONE, verified-Opus, APPROVED
    runner review task whose recorded prompt names the exact subject. The S0_ELIGIBLE certificate and the
    ACTIVE_FOR_S0_ONLY declaration must additionally state the exact two paths and a valid lifecycle, and agree
    with the current MOD-001/MOD-002 receipts, the PROVISIONAL module manifest bytes and the edge decision."""
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{receipt}.json", RECEIPT_MAX_BYTES), "S0 receipt")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "subjects"} and r["schema"] == SCHEMA
            and r["module"] == S0_MODULE and r["kind"] == "mod004-s0-authority" and isinstance(r["operator"], str)
            and r["operator"].strip() and isinstance(r["recorded_at"], str)
            and isinstance(r["subjects"], dict) and set(r["subjects"]) == set(S0_SUBJECTS)):
        raise GateError("S0 receipt schema mismatch")
    seen, data = set(), {}
    for name in S0_SUBJECTS:
        if name == "runner_gate" and runner_check is not None:  # the 2026-10-28 recovery's replacement runner: pre-load review bound in the overlay
            data[name] = runner_check(r["subjects"][name])
        else:
            data[name] = _s0_subject(cfg, name, r["subjects"][name], tasks, seen)
    subj = r["subjects"]
    if hashlib.sha256(data["runner_gate"]).hexdigest() != CODE_SHA:
        raise GateError("S0 runner_gate: the loaded runner is not the reviewed, CI-green runner file")
    if b"D12.5" not in data["adr"]:
        raise GateError("S0 adr: no D12.5 S0 amendment")
    if subj["eligibility"]["path"] == subj["capability"]["path"]:
        raise GateError("S0 receipt: contradictory subject paths")
    paths = sorted(S0_PATHS)
    cert, cap = _s0_json(data["eligibility"], "S0 eligibility"), _s0_json(data["capability"], "S0 capability")
    receipts = {}
    for dep in ("MOD-001", "MOD-002"):
        verify_receipt(cfg, dep)
        receipts[dep] = hashlib.sha256(_read_bounded(cfg.home / "acceptances" / f"{dep}.json", RECEIPT_MAX_BYTES)).hexdigest()
    if not (cert.get("schema") == SCHEMA and cert.get("module") == S0_MODULE and cert.get("status") == "S0_ELIGIBLE"
            and cert.get("lifecycle") == "EFFECTIVE" and cert.get("paths") == paths
            and cert.get("dependency_receipts") == receipts
            and cert.get("edge_decision") == {"path": subj["edge"]["path"], "sha256": subj["edge"]["sha256"]}):
        raise GateError("S0 eligibility certificate is not S0_ELIGIBLE/EFFECTIVE for the exact paths and current receipts")
    zero = ("third_party_caps", "database_profiles", "console_profiles")
    if not (cap.get("schema") == SCHEMA and cap.get("module") == S0_MODULE and cap.get("status") == "ACTIVE_FOR_S0_ONLY"
            and cap.get("paths") == paths and cap.get("toolchain") == "python3.13-stdlib"
            and cap.get("module_row_status") == "PROVISIONAL"
            and all(type(cap.get(k)) is int and cap[k] == 0 for k in zero)
            and isinstance(cap.get("forbidden_imports"), list) and S0_FORBIDDEN_IMPORTS <= set(cap["forbidden_imports"])):
        raise GateError("S0 capability declaration is not ACTIVE_FOR_S0_ONLY for the exact paths with a zero-CAP stdlib closure")
    _s0_content_problem(cfg, cert, cap, subj["edge"])
    # only the runner gate is cross-checked against observed ci.json; every other CI record is the operator's attestation
    return {"ci": {n: _s0_ci_label(cfg, subj[n]["commit"]) if n == "runner_gate" and runner_check is None else "operator-attested"
                   for n in S0_SUBJECTS}}


def s0_gate_reason(cfg, t, tasks):
    """None for a task outside S0 or a fully authorised sole S0 write; else an explicit S0_* reason."""
    if s0_test_marked(t):  # admitted only by its own, stricter gate (s0_test_gate_reason); the shape is checked there
        return None
    if not (s0_marked(t) or s0_touches(t)):
        return None
    if not s0_marked(t):
        return f"S0_UNTAGGED {t['id']}: a write naming the S0 files must carry plan_phase {S0_MARKER}"
    problem = s0_shape_problem(t)
    if problem:
        return f"S0_INVALID_TASK {t['id']}: {problem}"
    writes = {x["id"] for x in tasks.values() if x.get("id") != t["id"] and s0_marked(x) and x.get("role") in WRITE_ROLES}
    for rv in tasks.values():
        if (rv.get("role") == "code-review" and (rv.get("review_of") or {}).get("task_id") in writes
                and not (rv.get("status") == "DONE" and (rv.get("evidence") or {}).get("review_outcome") == "APPROVED")):
            return f"S0_PRIOR_REVIEW_NOT_APPROVED: {rv['id']} stops automatic S0 writes"
    if writes:
        return f"S0_SECOND_WRITE: S0 write {sorted(writes)[0]} already exists; only one S0 write is authorised"
    if t.get("attempts") and t.get("stage") != "verify_pending":  # one child attempt, whatever ended it: no transport retry
        return f"S0_ATTEMPT_USED {t['id']}: the single S0 write attempt was already started"
    try:
        verify_s0_authority(cfg, tasks)
    except GateError as e:
        return f"S0_AUTHORITY_UNVERIFIED: {e}"
    return None


def s0_review_reason(t, tasks):
    """The one bound review of the one S0 write: any other review task bound to it, in any status (failed, blocked
    without a verdict, stale, timed out, mis-formatted), has used the slot; and there is no retry lineage."""
    wid = (t.get("review_of") or {}).get("task_id")
    w = tasks.get(wid)
    if not (w and s0_marked(w)):
        return None
    if t.get("review_retry_of"):
        return "S0_REVIEW_RETRY: the S0 write gets one bound review and no retry"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == wid)
    if used:
        return f"S0_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review S0 write {wid}"
    return None


def s0_runner_problem(state):
    """Why the live sole runner may not be the one that loaded this reviewed code (None when it did): its recorded
    code_sha256 must equal this file, with a fresh heartbeat and a live pid. An old runner is rejected here."""
    r = (state or {}).get("runner")
    if not (isinstance(r, dict) and r.get("code_sha256") == CODE_SHA):
        return "S0_RUNNER_NOT_LOADED: the live runner has not loaded this reviewed runner code"
    try:
        age = time.time() - datetime.datetime.fromisoformat(r["heartbeat_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        age = None
    if r.get("stopped_at") or age is None or not 0 <= age <= S0_HEARTBEAT_MAX_AGE \
            or not (type(r.get("pid")) is int and pid_alive(r["pid"])):
        return "S0_RUNNER_NOT_LIVE: no fresh heartbeat from a live runner"
    return None


def s0_probe(cfg):
    """Read-only gate probe: reads state.json and the repo, queues nothing, takes no lock, writes nothing.
    Returns None when the exact canonical S0 route would be admitted now, else the refusing reason. It is a probe of
    the gate only: it grants no PASS, review or dispatch."""
    try:
        state = json.loads(_read_bounded(cfg.home / "state.json", 64 * 1024 * 1024))
        t = validate_task({"id": "s0-gate-probe", "module": S0_MODULE, "role": "implement", "prompt": "read-only probe",
                           "plan_phase": S0_MARKER, "allowed_paths": list(S0_PATHS), "expected_changes": list(S0_PATHS),
                           "verify_cmd": [S0_PYTHON, "-m", "unittest", S0_VERIFY_MODULE]}, cfg)
        return s0_runner_problem(state) or gate_reason(cfg, t, state["tasks"])
    except Exception as e:
        return f"S0_PROBE_UNVERIFIABLE: {type(e).__name__}"


# ------------------------------------------------ MOD-004 S0 document lane
# Owner-authorized document routing for the two S0 slice documents only (OWNER-2026-10-19-mod004-s0-only.md item 2,
# ADR-0002 D12.5, and the 2026-10-23 document-lane decision OWNER-2026-10-23-mod004-s0-doc-lane.md): one Sonnet write of exactly the eligibility certificate and the scenario/QA packet, one exact-bound
# Opus review per write, and at most MAX_REMEDIATIONS remediations of a CHANGES_REQUESTED verdict. It is a separate
# chain: it never joins the CAP review chain, never becomes its `last`, never spends or resets its remediation count,
# and makes no other MOD-004 write eligible. It is not the S0 product write and is never counted as one.
S0_DOC_MARKER = "MOD004-S0-DOC"
S0_DOC_PATHS = ("contracts/engineering/mod004-s0-eligibility.json", "contracts/engineering/mod004-s0-scenario-qa.md")
S0_DOC_OWNER_RECORD = S0_DOC_OWNER_PATH
S0_DOC_RECEIPT = "MOD-004-S0-DOC"  # operator-written <home>/acceptances/MOD-004-S0-DOC.json: owner, adr, runner_gate, doc_owner
S0_DOC_SUBJECTS = {  # name -> allowed repo path; owner/adr/runner_gate are the S0 subjects, doc_owner is this lane's own decision
    "owner": S0_SUBJECTS["owner"], "adr": S0_SUBJECTS["adr"], "runner_gate": S0_SUBJECTS["runner_gate"],
    "doc_owner": re.compile(re.escape(S0_DOC_OWNER_RECORD)),
}


def s0_doc_marked(t):
    return t.get("plan_phase") == S0_DOC_MARKER


def s0_doc_touches(t):
    """Any writing task, of any module, that names a slice document or whose scope (directory, glob, other case) would
    cover one. Only the exact MOD004-S0-DOC shape may do so, and nothing else offers another way to write them."""
    return _touches_any(t, S0_DOC_PATHS)


def s0_single_attempt(t):
    return (t.get("id") == TRANSFER_REVIEW_ID or s0_marked(t) or s0_doc_marked(t) or s0_refresh_marked(t) or s0_rebind_marked(t) or s0_test_marked(t)
            or s0_loop_marked(t) or s0_qa_marked(t) or s0_dual_rebind_marked(t) or _recovery_marked(t))


def s0_doc_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the S0 document lane is a MOD-004 implement task only"
    if t.get("source") == "handoff":
        return "the planner cannot propose S0 document tasks"
    if t.get("review_retry_of") is not None or t.get("accounting_recovery_of") is not None:
        return "review_retry_of and accounting_recovery_of are rejected"
    if t.get("review_of") is not None or t.get("review_candidate") is not None:
        return "a document write cannot carry review binding fields"
    if sorted(t.get("allowed_paths") or []) != sorted(S0_DOC_PATHS) or sorted(t.get("expected_changes") or []) != sorted(S0_DOC_PATHS):
        return "allowed_paths and expected_changes must be exactly the two S0 document files"
    if t.get("verify_cmd") != []:
        return "the document lane runs no verifier"
    base = t.get("doc_base")
    if not (isinstance(base, dict) and set(base) == set(S0_DOC_PATHS)
            and all(v is None or (isinstance(v, str) and SHA256_RE.fullmatch(v)) for v in base.values())):
        return "doc_base (the exact current sha256, or null if absent, of both documents) is required"
    return None


def verify_s0_doc_authority(cfg, tasks):
    """Offline re-verification that the S0 owner record, the ADR D12.5 amendment, this lane's own owner record
    (doc_owner) and this very runner file are each the committed, non-force-published, exact-SHA CI-green,
    independently Opus-APPROVED bytes, every one bound through _s0_subject. It never trusts task prose, and needs no
    slice document."""
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{S0_DOC_RECEIPT}.json", RECEIPT_MAX_BYTES), "S0 doc receipt")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "subjects"} and r["schema"] == SCHEMA
            and r["module"] == S0_MODULE and r["kind"] == "mod004-s0-doc-authority" and isinstance(r["operator"], str)
            and r["operator"].strip() and isinstance(r["recorded_at"], str)
            and isinstance(r["subjects"], dict) and set(r["subjects"]) == set(S0_DOC_SUBJECTS)):
        raise GateError("S0 doc receipt schema mismatch")
    seen = set()
    data = {name: _s0_subject(cfg, name, r["subjects"][name], tasks, seen, S0_DOC_SUBJECTS) for name in S0_DOC_SUBJECTS}
    if hashlib.sha256(data["runner_gate"]).hexdigest() != CODE_SHA:
        raise GateError("S0 doc runner_gate: the loaded runner is not the reviewed, CI-green runner file")
    if b"D12.5" not in data["adr"]:
        raise GateError("S0 doc adr: no D12.5 S0 amendment")


def _s0_doc_chain(tasks, write):
    """The doc-lane writes from `write` back to its root through remediation_of, newest first, or None if any link
    is not a DONE doc-lane implement write of MOD-004 whose single bound verified review requested changes."""
    chain = []
    while write is not None:
        if len(chain) >= MAX_REMEDIATIONS:
            return None
        if not (s0_doc_marked(write) and write.get("module") == S0_MODULE and write.get("role") == "implement"
                and write.get("status") == "DONE" and write["id"] not in {w["id"] for w in chain}):
            return None
        reviews = [r for r in tasks.values() if (r.get("review_of") or {}).get("task_id") == write["id"]]
        if not (len(reviews) == 1 and reviews[0].get("source") != "handoff"
                and review_verdict(tasks, write["id"]) == "CHANGES_REQUESTED"
                and _bound_review_ok(write, reviews[0])):
            return None
        chain.append(write)
        nxt = write.get("remediation_of")
        write = tasks.get(nxt) if nxt else None
        if nxt and write is None:
            return None
    return chain


def s0_doc_gate_reason(cfg, t, tasks):
    """None for a task outside the lane or a fully authorised document write; else an explicit S0_DOC_* reason."""
    if not s0_doc_marked(t):
        if (s0_doc_touches(t) and not s0_refresh_marked(t) and not s0_rebind_marked(t)
                and not s0_loop_marked(t) and not s0_qa_marked(t)
                and not s0_dual_rebind_marked(t) and not _recovery_marked(t)):  # the refresh, rebind, loop rebind, QA and fixed-ID dual rebind lanes are admitted only by their own, stricter gates
            return f"S0_DOC_UNTAGGED {t['id']}: a write naming or covering the S0 slice documents is not admitted"
        return None
    problem = s0_doc_shape_problem(t)
    if problem:
        return f"S0_DOC_INVALID_TASK {t['id']}: {problem}"
    if any(s0_marked(x) and x.get("role") in WRITE_ROLES for x in tasks.values()):
        return "S0_DOC_CLOSED: an S0 product write exists; the slice documents may no longer change"
    if os.path.lexists(cfg.home / "acceptances" / f"{S0_RECEIPT}.json"):
        return "S0_DOC_CLOSED: the S0 authority receipt exists and binds the slice documents"
    if any(s0_refresh_marked(x) and x.get("role") in WRITE_ROLES for x in tasks.values()):
        return "S0_DOC_CLOSED: the one-time document refresh exists; the original document lane stays consumed"
    if t.get("attempts"):
        return f"S0_DOC_ATTEMPT_USED {t['id']}: the single document write attempt was already started"
    others = [x for x in tasks.values() if x.get("id") != t["id"] and s0_doc_marked(x) and x.get("role") in WRITE_ROLES]
    parent = t.get("remediation_of")
    if parent is None:
        if others:
            return f"S0_DOC_SECOND_WRITE: document write {sorted(x['id'] for x in others)[0]} already exists; only bounded remediation may follow"
        want = None
    else:
        chain = _s0_doc_chain(tasks, tasks.get(parent))
        if not chain:
            return ("S0_DOC_REMEDIATION_INVALID: remediation_of must name a DONE document write whose one exact-bound "
                    f"review requested changes, within {MAX_REMEDIATIONS} rounds")
        if {x["id"] for x in others} != {w["id"] for w in chain}:
            return "S0_DOC_DUPLICATE_WORK: another document write exists outside this remediation chain"
        want = {c["path"]: c["sha256"] for c in (chain[0].get("evidence") or {}).get("changed") or []}
        if want != t["doc_base"]:
            return "S0_DOC_STALE_DRAFT: doc_base is not the exact content the review requested changes to"
    now = {p: _path_hash(Path(cfg.repo) / p) for p in S0_DOC_PATHS}
    if now != t["doc_base"]:
        return "S0_DOC_STALE_DRAFT: a document changed since doc_base was pinned"
    try:
        verify_s0_doc_authority(cfg, tasks)
    except GateError as e:
        return f"S0_DOC_AUTHORITY_UNVERIFIED: {e}"
    return None


def s0_doc_review_reason(cfg, t, tasks):
    """The one exact-bound Opus review of a document write: any other review task bound to it, in any status, has
    used the slot; there is no retry lineage; the bound hashes are exactly the write's two recorded files."""
    w = tasks.get((t.get("review_of") or {}).get("task_id"))
    if not (w and s0_doc_marked(w)):
        return None
    if t.get("source") == "handoff":
        return "S0_DOC_REVIEW_UNSUPPORTED: the planner cannot propose a document-lane review; it is owner-routed"
    if t.get("review_retry_of") or t.get("review_candidate"):
        return "S0_DOC_REVIEW_UNSUPPORTED: a document write gets one bound review and no retry"
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement" and w.get("status") == "DONE"):
        return "S0_DOC_REVIEW_UNSUPPORTED: only a DONE MOD-004 document write can be reviewed here"
    want = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if not (len(want) == len(S0_DOC_PATHS) and sorted(c["path"] for c in want) == sorted(S0_DOC_PATHS)
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) for c in want)
            and _changed_pairs((t.get("review_of") or {}).get("changed")) == want):
        return "S0_DOC_REVIEW_UNSUPPORTED: review must bind the exact changed hashes of both document files"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_DOC_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review document write {w['id']}"
    if not _hashes_current(cfg, (w.get("evidence") or {}).get("changed")):
        return "S0_DOC_REVIEW_BINDING_STALE: the document files no longer match the write's recorded hashes"
    return None


# ------------------------------------------------ MOD-004 S0 one-time document refresh (edge-context recovery)
# Owner-authorised by OWNER-2026-10-24-mod004-s0-edge-context-recovery.md item 2/3: ONE further runner-recorded Sonnet
# write of exactly the two S0 slice documents, starting from the pinned published hashes, with ONE exact-bound Opus
# review and no retry, remediation or review shopping. It is not the consumed MOD004-S0-DOC lane, never the S0 product
# write, and never joins the CAP chain. Its authority is the separately named MOD-004-S0-RECOVERY.json receipt, which
# is machine-verified like every other S0 authority (committed bytes, exact-commit CI, distinct Opus-APPROVED reviews)
# and additionally requires the old MOD-004-S0.json to be preserved out of acceptances/ and absent from it.
S0_REFRESH_MARKER = "MOD004-S0-DOC-REFRESH"
S0_REFRESH_BASE = {
    "contracts/engineering/mod004-s0-eligibility.json": "0adce2c8590a1c26124fa94b286155b66cba301d1f7d88a387ea4ae17a627ff9",
    "contracts/engineering/mod004-s0-scenario-qa.md": "349fc85b5b24c7556e291826894aea075660dbf80c004049cb706db166c57e45"}
S0_RECOVERY_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-24-mod004-s0-edge-context-recovery.md"
S0_RECOVERY_RECEIPT = "MOD-004-S0-RECOVERY"  # operator-written <home>/acceptances/MOD-004-S0-RECOVERY.json
S0_OLD_RECEIPT_SHA = "0bb98e348496413779ce83414325d8286a678dccf982c304ca257316dd30894f"  # the invalid MOD-004-S0.json
S0_RECOVERY_CHECKPOINT = "checkpoints/MOD-004-S0.pre-recovery.json"  # fixed path under the runner home
S0_RECOVERY_SUBJECTS = {  # five distinct exact subjects, each with its own distinct Opus-APPROVED review
    "owner": S0_SUBJECTS["owner"], "adr": S0_SUBJECTS["adr"], "doc_owner": S0_DOC_SUBJECTS["doc_owner"],
    "recovery_owner": re.compile(re.escape(S0_RECOVERY_OWNER_PATH)), "runner_gate": S0_SUBJECTS["runner_gate"],
}


def s0_refresh_marked(t):
    return t.get("plan_phase") == S0_REFRESH_MARKER


def s0_refresh_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the S0 document refresh is a MOD-004 implement task only"
    if t.get("source") == "handoff":
        return "the planner cannot propose the S0 document refresh"
    if any(t.get(k) is not None for k in ("remediation_of", "review_retry_of", "accounting_recovery_of", "review_of",
                                          "review_candidate")):
        return "remediation_of, review_retry_of, accounting_recovery_of and review binding fields are rejected"
    if sorted(t.get("allowed_paths") or []) != sorted(S0_DOC_PATHS) or sorted(t.get("expected_changes") or []) != sorted(S0_DOC_PATHS):
        return "allowed_paths and expected_changes must be exactly the two S0 document files"
    if t.get("verify_cmd") != []:
        return "the document refresh runs no verifier"
    if t.get("doc_base") != S0_REFRESH_BASE:
        return "doc_base must be exactly the two pinned published document hashes"
    return None


def _s0_preserved_receipt(cfg, e, path=None, sha=None):
    """A superseded S0 receipt must sit, byte-identical, at its one fixed regular non-symlink checkpoint under the home
    (default: the pre-recovery checkpoint and the pinned old receipt)."""
    path, sha = path or S0_RECOVERY_CHECKPOINT, sha or S0_OLD_RECEIPT_SHA
    if not (isinstance(e, dict) and set(e) == {"path", "sha256"} and e["path"] == path and e["sha256"] == sha):
        raise GateError("S0 recovery: preserved_receipt must be the fixed checkpoint path and the pinned old receipt sha256")
    cur = Path(cfg.home)
    for part in Path(e["path"]).parts[:-1]:
        cur = cur / part
        if cur.is_symlink() or not cur.is_dir():
            raise GateError("S0 recovery: the preserved receipt checkpoint directory is missing or a symlink")
    data = _read_bounded(Path(cfg.home) / e["path"], RECEIPT_MAX_BYTES)
    if hashlib.sha256(data).hexdigest() != sha:
        raise GateError("S0 recovery: the preserved old S0 receipt does not hash to the pinned sha256")


def verify_s0_refresh_authority(cfg, tasks):
    """Offline re-verification of the recovery authority: no S0 receipt in acceptances/, the old one preserved at its
    fixed checkpoint, and the five distinct subjects (original owner, ADR D12.5, 2026-10-23 doc owner, 2026-10-24
    recovery owner, this very runner file) each bound through _s0_subject. It never trusts task prose and never
    treats the old document-lane receipt as authority; it grants nothing to the S0 product gate."""
    if os.path.lexists(cfg.home / "acceptances" / f"{S0_RECEIPT}.json"):
        raise GateError("S0 recovery: an S0 authority receipt exists in acceptances/; the refresh runs only while it is absent")
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{S0_RECOVERY_RECEIPT}.json", RECEIPT_MAX_BYTES), "S0 recovery receipt")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "preserved_receipt", "subjects"}
            and r["schema"] == SCHEMA and r["module"] == S0_MODULE and r["kind"] == "mod004-s0-recovery-authority"
            and isinstance(r["operator"], str) and r["operator"].strip() and isinstance(r["recorded_at"], str)
            and isinstance(r["subjects"], dict) and set(r["subjects"]) == set(S0_RECOVERY_SUBJECTS)):
        raise GateError("S0 recovery receipt schema mismatch")
    _s0_preserved_receipt(cfg, r["preserved_receipt"])
    seen = set()
    data = {name: _s0_subject(cfg, name, r["subjects"][name], tasks, seen, S0_RECOVERY_SUBJECTS) for name in S0_RECOVERY_SUBJECTS}
    if hashlib.sha256(data["runner_gate"]).hexdigest() != CODE_SHA:
        raise GateError("S0 recovery runner_gate: the loaded runner is not the reviewed, CI-green runner file")
    if b"D12.5" not in data["adr"]:
        raise GateError("S0 recovery adr: no D12.5 S0 amendment")


def s0_refresh_gate_reason(cfg, t, tasks):
    """None for a task outside the refresh or the one fully authorised refresh write; else an explicit S0_REFRESH_* reason."""
    if not s0_refresh_marked(t):
        return None
    problem = s0_refresh_shape_problem(t)
    if problem:
        return f"S0_REFRESH_INVALID_TASK {t['id']}: {problem}"
    if any(s0_marked(x) and x.get("role") in WRITE_ROLES for x in tasks.values()):
        return "S0_REFRESH_CLOSED: an S0 product write exists; the slice documents may no longer change"
    if os.path.lexists(cfg.home / "acceptances" / f"{S0_RECEIPT}.json"):
        return "S0_REFRESH_CLOSED: an S0 authority receipt exists in acceptances/ and binds the slice documents"
    if t.get("attempts"):
        return f"S0_REFRESH_ATTEMPT_USED {t['id']}: the single refresh write attempt was already started"
    others = sorted(x["id"] for x in tasks.values() if x.get("id") != t["id"] and s0_refresh_marked(x) and x.get("role") in WRITE_ROLES)
    if others:
        return f"S0_REFRESH_SECOND_WRITE: refresh write {others[0]} already exists; the refresh is one-time"
    busy = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t["id"]
                  and x.get("status") in ("QUEUED", "RUNNING") and s0_doc_touches(x))
    if busy:
        return f"S0_REFRESH_CONCURRENT_WRITE: {busy[0]} is a pending write that touches the slice documents"
    if {p: _path_hash(Path(cfg.repo) / p) for p in S0_DOC_PATHS} != S0_REFRESH_BASE:
        return "S0_REFRESH_STALE_DRAFT: a document is not the pinned published content"
    try:
        verify_s0_refresh_authority(cfg, tasks)
    except GateError as e:
        return f"S0_REFRESH_AUTHORITY_UNVERIFIED: {e}"
    return None


def s0_refresh_review_reason(cfg, t, tasks):
    """The one exact-bound Opus review of the refresh write: any other review task bound to it, in any status, has used
    the slot; there is no retry; the bound hashes are exactly the two documents, both different from the pinned base."""
    w = tasks.get((t.get("review_of") or {}).get("task_id"))
    if not (w and s0_refresh_marked(w)):
        return None
    if t.get("source") == "handoff":
        return "S0_REFRESH_REVIEW_UNSUPPORTED: the planner cannot propose a refresh review; it is owner-routed"
    if t.get("review_retry_of") or t.get("review_candidate"):
        return "S0_REFRESH_REVIEW_UNSUPPORTED: the refresh write gets one bound review and no retry"
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement" and w.get("status") == "DONE"):
        return "S0_REFRESH_REVIEW_UNSUPPORTED: only a DONE MOD-004 refresh write can be reviewed here"
    want = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if not (len(want) == len(S0_DOC_PATHS) and sorted(c["path"] for c in want) == sorted(S0_DOC_PATHS)
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) and c["sha256"] != S0_REFRESH_BASE[c["path"]]
                    for c in want)
            and _changed_pairs((t.get("review_of") or {}).get("changed")) == want):
        return "S0_REFRESH_REVIEW_UNSUPPORTED: review must bind the exact changed hashes of both document files"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_REFRESH_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review refresh write {w['id']}"
    if not _hashes_current(cfg, (w.get("evidence") or {}).get("changed")):
        return "S0_REFRESH_REVIEW_BINDING_STALE: the document files no longer match the write's recorded hashes"
    return None


# ------------------------------------------------ MOD-004 S0 test-only remediation (OWNER-2026-10-24-mod004-s0-test-remediation.md)
# Infrastructure eligibility only; it performs no correction and approves no product. Two further separate chains, neither
# the original MOD004-S0 entitlement nor the CAP chain; only the one repair of the rebind uses remediation_of:
#   * MOD004-S0-DOC-REBIND: ONE Sonnet write of exactly the two slice documents (from their published hashes), ONE
#     exact-bound Opus review, no retry. It may run although the historical S0 product write exists, but only while the
#     recovery authority holds and no S0 receipt sits in acceptances/.
#   * MOD004-S0-TEST-REMEDIATION: ONE Sonnet write of exactly backend/tests/test_tenancy_s0.py with the pinned Python 3.13
#     verifier and ONE Opus review bound to BOTH the corrected test and the unchanged validator. It starts only after the
#     recovery authority and the full (rebuilt, current-runner) six-subject S0 authority verify, and the rebuilt receipt's
#     eligibility subject is the rebound certificate with both rebound documents clean and committed at its commit.
# Owner, ADR, test-owner and runner CI fields in the receipts are operator-attested exact-commit records; the runner
# cross-checks only its own file's CI against its observed ci.json and does no network or remote verification here.
# The original write, its CHANGES_REQUESTED review and the generic S0 gate are untouched: s0_probe must keep refusing.
S0_REBIND_MARKER = "MOD004-S0-DOC-REBIND"
S0_TEST_MARKER = "MOD004-S0-TEST-REMEDIATION"
S0_REBIND_BASE = {
    "contracts/engineering/mod004-s0-eligibility.json": "17d5120ef0e99b5a36cabf62e5a2c6f86349ad5d9c73e0ad294d43b54479c8d1",
    "contracts/engineering/mod004-s0-scenario-qa.md": "08334df3280e834becd45332f75b170741f612f98d623cc8e99d246b1634f680"}
# The one bounded repair of the incomplete rebind (cert packet hash was a placeholder; runner evidence stale after this
# runner changed): same marker, remediation_of the DONE two-file root write at these exact bytes, one more Sonnet write
# of the same two files, one Opus review bound to the repair's two changed hashes. The root is never reviewed.
S0_REBIND_ROOT_ID = "mod004-s0-test-doc-rebind-sonnet-20261024"
S0_REBIND_REPAIR_ID = "mod004-s0-test-doc-rebind-repair-sonnet-20261024"
S0_REBIND_ROOT_DONE = {
    "contracts/engineering/mod004-s0-eligibility.json": "4dff29375ecb75cad21fe1a14897397e9a0d2840b64b115bb890fadf46b738e4",
    "contracts/engineering/mod004-s0-scenario-qa.md": "ee4aea12fc9ad4a08bf90138570859f0e0ebad56b9a428aec4a0cb88b3c354e6"}
S0_TEST_RECOVERY_RECEIPT = "MOD-004-S0-TEST-RECOVERY"  # operator-written <home>/acceptances/MOD-004-S0-TEST-RECOVERY.json
S0_TEST_CHECKPOINT = "checkpoints/MOD-004-S0.pre-test-remediation.json"  # fixed path under the runner home
S0_PRE_TEST_RECEIPT_SHA = "a02beb42243981ed2997a8a9525db99e410201e31b90cfce6de83d9f1589876f"  # the current six-subject receipt
S0_RECOVERY_RECEIPT_SHA = "1b21fe3d6201b5d65e545e3a4190fd891f673120177724c2dfb025fcb7d3ec20"  # historical, stays byte-identical
S0_DOC_RECEIPT_SHA = "2f3e909576a2bcacb1c19544bb6411bff835dace10ad2d5b2bcc395397b59380"  # historical, stays byte-identical
S0_ORIG_WRITE = "mod004-s0-product-sonnet-20261024"
S0_ORIG_REVIEW = "mod004-s0-product-opus-code-review-20261024"
S0_ORIG_REVIEW_OUTPUT_SHA = "638a07e242f6dbcd5030809f5f4685276ad0baecdada62524e09a76bac1a1976"
S0_VALIDATOR_PATH, S0_TEST_PATH = S0_PATHS
S0_VALIDATOR_SHA = "5543353a0b95250bcde2b59681c8295f7ecb2c99f88097f793db1a7761196314"
S0_TEST_START_SHA = "a610232abb813b2981ccd9d5c68ec720ff17c72d544f55ad8c0d5b8dbcf52969"
S0_LOOP_MARKER = "MOD004-S0-LOOP-REBIND"
S0_LOOP_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-24-product-remediation-loop.md"
S0_LOOP_OWNER_SHA = "7ad9557534e4c34a597e64eafbe8113341ec0d7b482486964e8c63d66cceebea"
S0_LOOP_PRIOR_RECEIPT_SHA = "4a59bc08d501d2e3be0303be1950329bf225dbe57f833471a64299e9e440d1fe"  # the S0 receipt to be preserved
S0_LOOP_CHECKPOINT = "checkpoints/MOD-004-S0.pre-product-loop.json"  # fixed path under the runner home
S0_LOOP_RECOVERY_RECEIPT = "MOD-004-S0-LOOP-RECOVERY"  # operator-written <home>/acceptances/MOD-004-S0-LOOP-RECOVERY.json
S0_LOOP_BASE = {
    "contracts/engineering/mod004-s0-eligibility.json": "b8da4817ff24298eb70138d41edf119c80ec4a01d3afc0045affa6ffc8d5c667",
    "contracts/engineering/mod004-s0-scenario-qa.md": "78e1c8ecc3da2167e5f4feff736ff7873a04979964ee6b69f8ef123b56f83e58"}
S0_TEST_SUBJECTS = {  # four distinct exact subjects, each with its own distinct Opus-APPROVED review
    "owner": S0_SUBJECTS["owner"], "adr": S0_SUBJECTS["adr"], "test_owner": re.compile(re.escape(S0_TEST_OWNER_PATH)),
    "runner_gate": S0_SUBJECTS["runner_gate"],
}


def s0_rebind_marked(t):
    return t.get("plan_phase") == S0_REBIND_MARKER


def s0_rebind_repair_marked(t):
    return s0_rebind_marked(t) and t.get("id") == S0_REBIND_REPAIR_ID


def s0_test_marked(t):
    return t.get("plan_phase") == S0_TEST_MARKER


def s0_loop_marked(t):
    return t.get("plan_phase") == S0_LOOP_MARKER


def s0_loop_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the S0 loop document rebind is a MOD-004 implement task only"
    if t.get("source") is not None:
        return "the S0 loop document rebind is admitted only from the owner CLI"
    if any(t.get(k) is not None for k in ("remediation_of", "review_retry_of", "accounting_recovery_of", "review_of",
                                          "review_candidate")):
        return "remediation_of, review_retry_of, accounting_recovery_of and review binding fields are rejected"
    if sorted(t.get("allowed_paths") or []) != sorted(S0_DOC_PATHS) or sorted(t.get("expected_changes") or []) != sorted(S0_DOC_PATHS):
        return "allowed_paths and expected_changes must be exactly the two S0 document files"
    if t.get("verify_cmd") != []:
        return "the S0 loop document rebind runs no verifier"
    if t.get("doc_base") != S0_LOOP_BASE:
        return "doc_base must be exactly the two pinned published document hashes"
    return None


def _s0_original_pins(cfg, tasks):
    """The runner-recorded original S0 write and its sole CHANGES_REQUESTED review, exactly as pinned by the owner
    record, and the still-unchanged validator on disk. Raises GateError on any deviation."""
    w, r = tasks.get(S0_ORIG_WRITE), tasks.get(S0_ORIG_REVIEW)
    pins = _changed_pairs([{"path": S0_VALIDATOR_PATH, "sha256": S0_VALIDATOR_SHA},
                           {"path": S0_TEST_PATH, "sha256": S0_TEST_START_SHA}])
    if not (isinstance(w, dict) and w.get("id") == S0_ORIG_WRITE and s0_marked(w) and w.get("module") == S0_MODULE
            and w.get("role") == "implement" and w.get("status") == "DONE"
            and _changed_pairs((w.get("evidence") or {}).get("changed")) == pins):
        raise GateError("S0 original write is not the pinned DONE write at the pinned validator and test hashes")
    route, ev = (r or {}).get("route") or {}, (r or {}).get("evidence") or {}
    op = route.get("dispatch_op")
    if not (isinstance(r, dict) and r.get("id") == S0_ORIG_REVIEW and r.get("role") == "code-review"
            and r.get("status") == "BLOCKED" and r.get("blocked_reason") == "REVIEW_CHANGES_REQUESTED"
            and ev.get("review_outcome") == "CHANGES_REQUESTED" and route.get("verdict") == "VERIFIED"
            and (r.get("review_of") or {}).get("task_id") == S0_ORIG_WRITE and _bound_review_ok(w, r)
            and isinstance(op, str) and re.fullmatch(re.escape(r["id"]) + r":[1-9][0-9]*", op)):
        raise GateError("S0 original review is not the pinned verified-Opus CHANGES_REQUESTED review of the original write")
    if [x["id"] for x in tasks.values() if isinstance(x, dict) and (x.get("review_of") or {}).get("task_id") == S0_ORIG_WRITE] != [S0_ORIG_REVIEW]:
        raise GateError("S0 original write has a review task besides the pinned one")
    out = _read_bounded(Path(cfg.home) / "runs" / (op.replace(":", "-") + ".out"), REVIEW_MAX_BYTES)
    if hashlib.sha256(out).hexdigest() != S0_ORIG_REVIEW_OUTPUT_SHA:
        raise GateError("S0 original review output does not hash to the pinned sha256")
    try:
        if _path_hash(Path(cfg.repo) / S0_VALIDATOR_PATH) != S0_VALIDATOR_SHA:
            raise GateError("S0 validator changed from its pinned sha256")
    except OSError:
        raise GateError("S0 validator cannot be read")


def verify_s0_test_recovery_authority(cfg, tasks):
    """Offline re-verification of the test-remediation recovery authority: the pre-test-remediation checkpoint holds the
    pinned a02b... receipt byte-identically, the earlier recovery history is preserved (the old checkpoint and the
    recovery and document receipts, each byte-identical to its pinned sha256), the four distinct subjects (S0 owner,
    ADR D12.5, this owner record, this very runner file) are committed with operator-attested exact-commit CI fields
    (only the runner file's is cross-checked against the runner's own observed ci.json; nothing here queries the
    network) and independently Opus-APPROVED, and the original write/review pins hold. It grants nothing to the S0
    product gate."""
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{S0_TEST_RECOVERY_RECEIPT}.json", RECEIPT_MAX_BYTES),
                 "S0 test-recovery receipt")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "preserved_receipt", "subjects"}
            and r["schema"] == SCHEMA and r["module"] == S0_MODULE and r["kind"] == "mod004-s0-test-recovery-authority"
            and isinstance(r["operator"], str) and r["operator"].strip() and isinstance(r["recorded_at"], str)
            and isinstance(r["subjects"], dict) and set(r["subjects"]) == set(S0_TEST_SUBJECTS)):
        raise GateError("S0 test-recovery receipt schema mismatch")
    _s0_preserved_receipt(cfg, r["preserved_receipt"], S0_TEST_CHECKPOINT, S0_PRE_TEST_RECEIPT_SHA)
    _s0_preserved_receipt(cfg, {"path": S0_RECOVERY_CHECKPOINT, "sha256": S0_OLD_RECEIPT_SHA})
    for name, pin in ((S0_RECOVERY_RECEIPT, S0_RECOVERY_RECEIPT_SHA), (S0_DOC_RECEIPT, S0_DOC_RECEIPT_SHA)):
        kept = _read_bounded(cfg.home / "acceptances" / f"{name}.json", RECEIPT_MAX_BYTES)
        if hashlib.sha256(kept).hexdigest() != pin:
            raise GateError(f"S0 test recovery: the historical {name}.json receipt is not byte-identical to its pinned sha256")
    owner = r["subjects"]["test_owner"]
    if not (isinstance(owner, dict) and owner.get("path") == S0_TEST_OWNER_PATH and owner.get("sha256") == S0_TEST_OWNER_SHA):
        raise GateError("S0 test recovery: test_owner is not the pinned committed owner record")
    seen = set()
    data = {name: _s0_subject(cfg, name, r["subjects"][name], tasks, seen, S0_TEST_SUBJECTS) for name in S0_TEST_SUBJECTS}
    if hashlib.sha256(data["runner_gate"]).hexdigest() != CODE_SHA:
        raise GateError("S0 test recovery runner_gate: the loaded runner is not the reviewed, CI-green runner file")
    if b"D12.5" not in data["adr"]:
        raise GateError("S0 test recovery adr: no D12.5 S0 amendment")
    _s0_original_pins(cfg, tasks)


def verify_s0_rebind_authority(cfg, tasks):
    """The document rebind runs only while no S0 receipt of any kind sits in acceptances/ and the recovery authority holds."""
    if os.path.lexists(cfg.home / "acceptances" / f"{S0_RECEIPT}.json"):
        raise GateError("S0 rebind: an S0 authority receipt exists in acceptances/; the rebind runs only while it is absent")
    verify_s0_test_recovery_authority(cfg, tasks)


S0_LOOP_SUBJECTS = {  # three-plus-one distinct exact subjects, each with its own distinct Opus-APPROVED review
    "owner": S0_SUBJECTS["owner"], "adr": S0_SUBJECTS["adr"], "loop_owner": re.compile(re.escape(S0_LOOP_OWNER_PATH)),
    "runner_gate": S0_SUBJECTS["runner_gate"],
}
S0_LOOP_OWNER_REVIEW = "owner-product-remediation-loop-opus-r3-20261024"
S0_LOOP_OWNER_REVIEW_OUTPUT_SHA = "614c73fab45a57b2e0eba71822ea15a0967bfcc99cab4fd47cea314282e6c64e"
S0_LOOP_OWNER_COMMIT = "7a877c7b6075d91928c4a6b465716a2b9430f8ea"
S0_LOOP_OWNER_CI_RUN = "40079271823"


def verify_s0_loop_authority(cfg, tasks, require_base=True):
    """Offline re-verification of the product-remediation-loop recovery authority: no active S0 receipt, the pre-loop
    checkpoint holds the pinned receipt byte-identically, the four distinct subjects (S0 owner, ADR D12.5, the loop
    owner record, this very runner file) are committed, CI-green and independently Opus-APPROVED, the loop owner record
    is bound to its pinned sha256, review task, output, commit and CI run, and (only with require_base, i.e. for the
    write gate) the two S0 documents are still the pinned starting content. It grants nothing to the S0 product gate."""
    if os.path.lexists(cfg.home / "acceptances" / f"{S0_RECEIPT}.json"):
        raise GateError("S0 loop: an S0 authority receipt exists in acceptances/; the loop rebind runs only while it is absent")
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{S0_LOOP_RECOVERY_RECEIPT}.json", RECEIPT_MAX_BYTES),
                 "S0 loop-recovery receipt")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "preserved_receipt", "subjects"}
            and r["schema"] == SCHEMA and r["module"] == S0_MODULE and r["kind"] == "mod004-s0-loop-recovery-authority"
            and isinstance(r["operator"], str) and r["operator"].strip() and isinstance(r["recorded_at"], str)
            and isinstance(r["subjects"], dict) and set(r["subjects"]) == set(S0_LOOP_SUBJECTS)):
        raise GateError("S0 loop-recovery receipt schema mismatch")
    _s0_preserved_receipt(cfg, r["preserved_receipt"], S0_LOOP_CHECKPOINT, S0_LOOP_PRIOR_RECEIPT_SHA)
    owner = r["subjects"]["loop_owner"]
    rv, ci = (owner.get("review"), owner.get("ci")) if isinstance(owner, dict) else (None, None)
    if not (isinstance(rv, dict) and isinstance(ci, dict) and owner.get("path") == S0_LOOP_OWNER_PATH
            and owner.get("sha256") == S0_LOOP_OWNER_SHA and owner.get("commit") == S0_LOOP_OWNER_COMMIT
            and ci.get("run_id") == S0_LOOP_OWNER_CI_RUN and rv.get("task_id") == S0_LOOP_OWNER_REVIEW
            and rv.get("output_sha256") == S0_LOOP_OWNER_REVIEW_OUTPUT_SHA):
        raise GateError("S0 loop recovery: loop_owner is not the pinned committed owner record, review and CI run")
    seen = set()
    data = {name: _s0_subject(cfg, name, r["subjects"][name], tasks, seen, S0_LOOP_SUBJECTS) for name in S0_LOOP_SUBJECTS}
    if hashlib.sha256(data["runner_gate"]).hexdigest() != CODE_SHA:
        raise GateError("S0 loop recovery runner_gate: the loaded runner is not the reviewed, CI-green runner file")
    if b"D12.5" not in data["adr"]:
        raise GateError("S0 loop recovery adr: no D12.5 S0 amendment")
    if not require_base:
        return
    try:
        docs = {p: _path_hash(Path(cfg.repo) / p) for p in S0_DOC_PATHS}
    except OSError:
        raise GateError("S0 loop recovery: an S0 document cannot be read")
    if docs != S0_LOOP_BASE:
        raise GateError("S0 loop recovery: a starting S0 document is not the pinned content")


def _s0_competing_writes(tasks, t):
    return sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t["id"]
                  and x.get("role") in WRITE_ROLES and x.get("status") in ("QUEUED", "RUNNING")
                  and (s0_touches(x) or s0_doc_touches(x) or s0_marked(x) or s0_doc_marked(x) or s0_refresh_marked(x)
                       or s0_rebind_marked(x) or s0_test_marked(x) or s0_loop_marked(x) or s0_qa_marked(x)
                       or s0_dual_rebind_marked(x) or _recovery_marked(x)))


def s0_rebind_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the S0 document rebind is a MOD-004 implement task only"
    if t.get("source") == "handoff":
        return "the planner cannot propose the S0 document rebind"
    if any(t.get(k) is not None for k in ("remediation_of", "review_retry_of", "accounting_recovery_of", "review_of",
                                          "review_candidate")):
        return "remediation_of, review_retry_of, accounting_recovery_of and review binding fields are rejected"
    if sorted(t.get("allowed_paths") or []) != sorted(S0_DOC_PATHS) or sorted(t.get("expected_changes") or []) != sorted(S0_DOC_PATHS):
        return "allowed_paths and expected_changes must be exactly the two S0 document files"
    if t.get("verify_cmd") != []:
        return "the document rebind runs no verifier"
    if t.get("doc_base") != S0_REBIND_BASE:
        return "doc_base must be exactly the two pinned published document hashes"
    return None


def s0_rebind_repair_shape_problem(t):
    if t.get("id") != S0_REBIND_REPAIR_ID:
        return f"the only admitted repair task id is {S0_REBIND_REPAIR_ID}"
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the S0 document rebind repair is a MOD-004 implement task only"
    if t.get("source") == "handoff":
        return "the planner cannot propose the S0 document rebind repair"
    if t.get("remediation_of") != S0_REBIND_ROOT_ID:
        return "remediation_of must be exactly the incomplete rebind write"
    if any(t.get(k) is not None for k in ("review_retry_of", "accounting_recovery_of", "review_of", "review_candidate")):
        return "review_retry_of, accounting_recovery_of and review binding fields are rejected"
    if sorted(t.get("allowed_paths") or []) != sorted(S0_DOC_PATHS) or sorted(t.get("expected_changes") or []) != sorted(S0_DOC_PATHS):
        return "allowed_paths and expected_changes must be exactly the two S0 document files"
    if t.get("verify_cmd") != []:
        return "the document rebind repair runs no verifier"
    if t.get("doc_base") != S0_REBIND_ROOT_DONE:
        return "doc_base must be exactly the two document hashes the incomplete rebind write left"
    return None


def _s0_rebind_root_pairs():
    return _changed_pairs([{"path": p, "sha256": h} for p, h in S0_REBIND_ROOT_DONE.items()])


def _s0_rebind_is_pinned_root(w):
    return w.get("id") == S0_REBIND_ROOT_ID or _changed_pairs((w.get("evidence") or {}).get("changed")) == _s0_rebind_root_pairs()


def _s0_rebind_root_problem(tasks):
    """The incomplete root write must stay exactly as recorded (DONE, one attempt, the two pinned hashes, never reviewed).
    Record-only: it does not look at the working tree, which the repair legitimately changes."""
    w = tasks.get(S0_REBIND_ROOT_ID)
    if not (isinstance(w, dict) and w.get("id") == S0_REBIND_ROOT_ID and s0_rebind_marked(w) and not s0_rebind_repair_marked(w)
            and w.get("role") == "implement" and w.get("status") == "DONE" and w.get("attempts") == 1
            and s0_rebind_shape_problem(w) is None and (w.get("evidence") or {}).get("violations") == []
            and _changed_pairs((w.get("evidence") or {}).get("changed")) == _s0_rebind_root_pairs()):
        return "the incomplete rebind write is not the pinned DONE two-file write with one attempt"
    if any(isinstance(x, dict) and (x.get("review_of") or {}).get("task_id") == S0_REBIND_ROOT_ID for x in tasks.values()):
        return "the incomplete rebind write has a review task; it is repaired, never reviewed"
    return None


def _s0_rebind_repair_write_problem(w):
    """Record-only: the repair write is DONE, one attempt, and changed exactly both documents to bytes that differ from
    the root write's."""
    ev = w.get("evidence") or {}
    changed = _changed_pairs(ev.get("changed"))
    if not (s0_rebind_repair_marked(w) and w.get("status") == "DONE" and w.get("attempts") == 1
            and s0_rebind_repair_shape_problem(w) is None and ev.get("violations") == []
            and sorted(str(c["path"]) for c in changed) == sorted(S0_DOC_PATHS)
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) and c["sha256"] != S0_REBIND_ROOT_DONE[c["path"]]
                    for c in changed)):
        return "the repair write is not DONE with one attempt and both documents changed from the root write's bytes"
    return None


def _s0_rebind_packet_problem(cfg, hashes=None):
    """The certificate's scenario_qa_packet names the packet file and its exact current sha256 (never a placeholder).
    With `hashes`, both documents must also be exactly those bytes."""
    cert_path, qa_path = S0_DOC_PATHS
    try:
        cert_bytes = _read_bounded(Path(cfg.repo) / cert_path, REVIEW_MAX_BYTES)
        qa_sha = hashlib.sha256(_read_bounded(Path(cfg.repo) / qa_path, REVIEW_MAX_BYTES)).hexdigest()
        if hashes is not None and (hashlib.sha256(cert_bytes).hexdigest() != hashes.get(cert_path) or qa_sha != hashes.get(qa_path)):
            return "a document is not the repair's recorded content"
        ref = _s0_json(cert_bytes, "S0 certificate").get("scenario_qa_packet")
    except (GateError, OSError) as e:
        return f"cannot read the repaired documents: {str(e)[:100]}"
    if not (isinstance(ref, dict) and ref.get("path") == qa_path and isinstance(ref.get("sha256"), str)
            and SHA256_RE.fullmatch(ref["sha256"]) and ref["sha256"] == qa_sha):
        return "certificate scenario_qa_packet.sha256 is not the final packet hash (or is a placeholder)"
    return None


def s0_rebind_repair_gate_reason(cfg, t, tasks):
    """The one fully authorised repair of the incomplete rebind write; else an explicit S0_REBIND_REPAIR_* reason."""
    problem = s0_rebind_repair_shape_problem(t)
    if problem:
        return f"S0_REBIND_REPAIR_INVALID_TASK {t['id']}: {problem}"
    if any(s0_test_marked(x) and x.get("role") in WRITE_ROLES for x in tasks.values()):
        return "S0_REBIND_REPAIR_CLOSED: the test-only correction exists; the slice documents may no longer change"
    if os.path.lexists(cfg.home / "acceptances" / f"{S0_RECEIPT}.json"):
        return "S0_REBIND_REPAIR_CLOSED: an S0 authority receipt exists in acceptances/ and binds the slice documents"
    if t.get("attempts"):
        return f"S0_REBIND_REPAIR_ATTEMPT_USED {t['id']}: the single repair write attempt was already started"
    others = sorted(x["id"] for x in tasks.values() if x.get("id") not in (t["id"], S0_REBIND_ROOT_ID)
                    and s0_rebind_marked(x) and x.get("role") in WRITE_ROLES)
    if others:
        return f"S0_REBIND_REPAIR_SECOND_WRITE: rebind write {others[0]} already exists; the repair is one-time"
    problem = _s0_rebind_root_problem(tasks)
    if problem:
        return f"S0_REBIND_REPAIR_ROOT_INVALID: {problem}"
    busy = _s0_competing_writes(tasks, t)
    if busy:
        return f"S0_REBIND_REPAIR_CONCURRENT_WRITE: {busy[0]} is a pending write in an S0 chain or touching S0 files"
    if {p: _path_hash(Path(cfg.repo) / p) for p in S0_DOC_PATHS} != S0_REBIND_ROOT_DONE:
        return "S0_REBIND_REPAIR_STALE_DRAFT: a document is not the content the incomplete rebind write left"
    try:
        verify_s0_rebind_authority(cfg, tasks)
    except GateError as e:
        return f"S0_REBIND_REPAIR_AUTHORITY_UNVERIFIED: {e}"
    return None


def _s0_rebind_repair_review_reason(cfg, t, w, tasks):
    """The one Opus review of the repair write, bound to its two changed hashes; the incomplete root is never reviewed."""
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement" and w.get("status") == "DONE"):
        return "S0_REBIND_REVIEW_UNSUPPORTED: only the DONE MOD-004 repair write can be reviewed here"
    problem = _s0_rebind_root_problem(tasks) or _s0_rebind_repair_write_problem(w)
    if problem:
        return f"S0_REBIND_REVIEW_UNSUPPORTED: {problem}"
    ids = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and s0_rebind_marked(x) and x.get("role") in WRITE_ROLES)
    if ids != sorted([S0_REBIND_ROOT_ID, S0_REBIND_REPAIR_ID]):
        return "S0_REBIND_REVIEW_UNSUPPORTED: only the incomplete root write and its one repair may exist"
    want = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if _changed_pairs((t.get("review_of") or {}).get("changed")) != want:
        return "S0_REBIND_REVIEW_UNSUPPORTED: review must bind the exact changed hashes of both document files"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_REBIND_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review rebind repair {w['id']}"
    if not _hashes_current(cfg, (w.get("evidence") or {}).get("changed")):
        return "S0_REBIND_REVIEW_BINDING_STALE: the document files no longer match the write's recorded hashes"
    problem = _s0_rebind_packet_problem(cfg, {c["path"]: c["sha256"] for c in want})
    if problem:
        return f"S0_REBIND_REVIEW_UNSUPPORTED: {problem}; the one review slot is not spent on an unfinished repair"
    try:
        verify_s0_rebind_authority(cfg, tasks)
    except GateError as e:
        return f"S0_REBIND_REVIEW_AUTHORITY_UNVERIFIED: {e}"
    return None


def s0_rebind_gate_reason(cfg, t, tasks):
    """None for a task outside the rebind or the one fully authorised rebind write; else an explicit S0_REBIND_* reason."""
    if not s0_rebind_marked(t):
        return None
    if s0_rebind_repair_marked(t):
        return s0_rebind_repair_gate_reason(cfg, t, tasks)
    problem = s0_rebind_shape_problem(t)
    if problem:
        return f"S0_REBIND_INVALID_TASK {t['id']}: {problem}"
    if any(s0_test_marked(x) and x.get("role") in WRITE_ROLES for x in tasks.values()):
        return "S0_REBIND_CLOSED: the test-only correction exists; the slice documents may no longer change"
    if os.path.lexists(cfg.home / "acceptances" / f"{S0_RECEIPT}.json"):
        return "S0_REBIND_CLOSED: an S0 authority receipt exists in acceptances/ and binds the slice documents"
    if t.get("attempts"):
        return f"S0_REBIND_ATTEMPT_USED {t['id']}: the single rebind write attempt was already started"
    others = sorted(x["id"] for x in tasks.values() if x.get("id") != t["id"] and s0_rebind_marked(x) and x.get("role") in WRITE_ROLES)
    if others:
        return f"S0_REBIND_SECOND_WRITE: rebind write {others[0]} already exists; the rebind is one-time"
    busy = _s0_competing_writes(tasks, t)
    if busy:
        return f"S0_REBIND_CONCURRENT_WRITE: {busy[0]} is a pending write in an S0 chain or touching S0 files"
    if {p: _path_hash(Path(cfg.repo) / p) for p in S0_DOC_PATHS} != S0_REBIND_BASE:
        return "S0_REBIND_STALE_DRAFT: a document is not the pinned published content"
    try:
        verify_s0_rebind_authority(cfg, tasks)
    except GateError as e:
        return f"S0_REBIND_AUTHORITY_UNVERIFIED: {e}"
    return None


def s0_rebind_review_reason(cfg, t, tasks):
    """The one exact-bound Opus review of the rebind write: any other review task bound to it, in any status, has used
    the slot; there is no retry; the bound hashes are exactly the two documents, both different from the pinned base."""
    w = tasks.get((t.get("review_of") or {}).get("task_id"))
    if not (w and s0_rebind_marked(w)):
        return None
    if t.get("source") == "handoff":
        return "S0_REBIND_REVIEW_UNSUPPORTED: the planner cannot propose a rebind review; it is owner-routed"
    if t.get("review_retry_of") or t.get("review_candidate"):
        return "S0_REBIND_REVIEW_UNSUPPORTED: the rebind write gets one bound review and no retry"
    if s0_rebind_repair_marked(w):
        return _s0_rebind_repair_review_reason(cfg, t, w, tasks)
    if any(isinstance(x, dict) and s0_rebind_marked(x) and (s0_rebind_repair_marked(x) or _s0_rebind_is_pinned_root(x))
           for x in tasks.values()):
        return "S0_REBIND_REVIEW_UNSUPPORTED: the incomplete root rebind write is repaired, never reviewed"
    problem = s0_rebind_shape_problem(w)
    if problem:
        return f"S0_REBIND_REVIEW_UNSUPPORTED: {problem}"
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement" and w.get("status") == "DONE"):
        return "S0_REBIND_REVIEW_UNSUPPORTED: only a DONE MOD-004 rebind write can be reviewed here"
    want = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if not (len(want) == len(S0_DOC_PATHS) and sorted(c["path"] for c in want) == sorted(S0_DOC_PATHS)
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) and c["sha256"] != S0_REBIND_BASE[c["path"]]
                    for c in want)
            and _changed_pairs((t.get("review_of") or {}).get("changed")) == want):
        return "S0_REBIND_REVIEW_UNSUPPORTED: review must bind the exact changed hashes of both document files"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_REBIND_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review rebind write {w['id']}"
    if not _hashes_current(cfg, (w.get("evidence") or {}).get("changed")):
        return "S0_REBIND_REVIEW_BINDING_STALE: the document files no longer match the write's recorded hashes"
    return None


S0_LOOP_REF_COMMIT = "5f3b0de66eebf0f44894430ad9770958c51f1e7a"  # the published commit holding the pinned starting documents
S0_LOOP_PACKET_STATUS = b"**Review and recovery status:**"


def _s0_loop_ref_blob(cfg, path):
    if path not in S0_LOOP_BASE:
        raise GateError(f"S0 loop reference: {path} is not a pinned starting S0 document")
    data = _s0_git_blob(cfg, S0_LOOP_REF_COMMIT, path, "S0 loop reference")
    if len(data) > REVIEW_MAX_BYTES or hashlib.sha256(data).hexdigest() != S0_LOOP_BASE[path]:
        raise GateError(f"S0 loop reference: {path} at {S0_LOOP_REF_COMMIT[:12]} is not the pinned starting content")
    return data


def _s0_loop_runner_subject(cfg):
    """The loop-recovery receipt's runner_gate subject (sha256, commit, CI), shape-checked; fail closed when the receipt is
    missing or malformed. Full subject verification stays in verify_s0_loop_authority."""
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{S0_LOOP_RECOVERY_RECEIPT}.json", RECEIPT_MAX_BYTES),
                 "S0 loop-recovery receipt")
    subjects = r.get("subjects")
    e = subjects.get("runner_gate") if isinstance(subjects, dict) else None
    if not (isinstance(e, dict) and e.get("path") == "tools/mission_runner/runner.py" and e.get("sha256") == CODE_SHA
            and isinstance(e.get("commit"), str) and SHA_RE.fullmatch(e["commit"]) and isinstance(e.get("ci"), dict)):
        raise GateError("S0 loop-recovery receipt has no well-formed runner_gate subject for the loaded runner")
    return e


def _s0_loop_docs_problem(cfg):
    """The cert differs from the pinned starting cert only in its current-runner evidence (top-level runner_gate.sha256,
    authority.runner_gate.sha256, authority.published_runner_gate_commit, authority.runner_gate_ci and the whole
    authority_publication.runner_gate, taken from the loop-recovery receipt's runner_gate subject, plus
    immediate_prior_runner_gate.sha256 moving the former top-level sha to history with a note naming it, and the
    runner_load_observation's observed_at/reload_status/loaded_runner_sha256/sole_loaded_runner) and in
    scenario_qa_packet.sha256/sha256_note; the packet differs from the pinned starting packet only in
    its `**Review and recovery status:**` paragraph, so every scenario row and the PASS rule stay byte-identical."""
    cert_path, qa_path = S0_DOC_PATHS
    try:
        base_qa, base_cert = _s0_loop_ref_blob(cfg, qa_path), _s0_loop_ref_blob(cfg, cert_path)
        cur_qa = _read_bounded(Path(cfg.repo) / qa_path, REVIEW_MAX_BYTES)
        cur_cert = _read_bounded(Path(cfg.repo) / cert_path, REVIEW_MAX_BYTES)
        want = _s0_json(base_cert, "S0 loop starting certificate")
        got = _s0_json(cur_cert, "S0 loop certificate")
        subject = _s0_loop_runner_subject(cfg)
    except (GateError, OSError) as e:
        return f"cannot verify the loop documents: {str(e)[:120]}"
    top, auth, prior, packet = (want.get("runner_gate"), want.get("authority"), want.get("immediate_prior_runner_gate"),
                                want.get("scenario_qa_packet"))
    obs, pub = want.get("runner_load_observation"), want.get("authority_publication")
    if not (isinstance(top, dict) and isinstance(auth, dict) and isinstance(auth.get("runner_gate"), dict)
            and isinstance(prior, dict) and isinstance(packet, dict) and isinstance(obs, dict)
            and isinstance(pub, dict) and isinstance(pub.get("runner_gate"), dict)):
        return "the pinned starting certificate lacks its runner evidence objects"
    old_top_sha = top.get("sha256")
    top["sha256"] = auth["runner_gate"]["sha256"] = CODE_SHA
    auth["published_runner_gate_commit"] = subject["commit"]
    auth["runner_gate_ci"] = subject["ci"]
    prior["sha256"] = old_top_sha
    packet["sha256"] = hashlib.sha256(cur_qa).hexdigest()
    gp = got.get("scenario_qa_packet")
    if not (isinstance(gp, dict) and isinstance(gp.get("sha256_note"), str) and gp["sha256_note"].strip()):
        return "the certificate's scenario_qa_packet has no sha256_note"
    packet["sha256_note"] = gp["sha256_note"]
    nonempty = lambda v: isinstance(v, str) and bool(v.strip())
    go, gprior, gpub = got.get("runner_load_observation"), got.get("immediate_prior_runner_gate"), got.get("authority_publication")
    if not (isinstance(go, dict) and go.get("loaded_runner_sha256") == CODE_SHA and go.get("sole_loaded_runner") is True
            and obs.get("loaded_runner_sha256") == old_top_sha and nonempty(go.get("observed_at"))
            and nonempty(go.get("reload_status"))):
        return ("the certificate's runner_load_observation must name the loaded runner, sole_loaded_runner true, "
                "and a nonempty observed_at and reload_status")
    for k in ("observed_at", "reload_status", "loaded_runner_sha256", "sole_loaded_runner"):
        obs[k] = go[k]
    if not (isinstance(gprior, dict) and nonempty(gprior.get("note")) and isinstance(old_top_sha, str)
            and old_top_sha in gprior["note"]):
        return "the certificate's immediate_prior_runner_gate.note must be nonempty and name the former runner sha256"
    prior["note"] = gprior["note"]
    rv = subject.get("review")
    if not (isinstance(rv, dict) and nonempty(rv.get("task_id")) and nonempty(rv.get("output_sha256"))):
        return "the loop-recovery receipt's runner_gate subject has no review task_id/output_sha256"
    pub["runner_gate"] = {"commit": subject["commit"], "push": "non-force", "ci": subject["ci"],
                          "review": {"task_id": rv["task_id"], "output_sha256": rv["output_sha256"],
                                     "route": "verified Opus", "outcome": "APPROVED"}}
    if old_top_sha == CODE_SHA or got != want:
        return ("the certificate differs from the pinned starting one beyond the current-runner evidence "
                "(runner_gate.sha256, authority.runner_gate.sha256/published_runner_gate_commit/runner_gate_ci and "
                "authority_publication.runner_gate taken from the receipt's runner_gate subject, immediate_prior_runner_gate."
                "sha256/note, runner_load_observation current-runner fields) and scenario_qa_packet.sha256/sha256_note")
    old, new = base_qa.split(b"\n\n"), cur_qa.split(b"\n\n")
    oi = [i for i, x in enumerate(old) if x.startswith(S0_LOOP_PACKET_STATUS)]
    ni = [i for i, x in enumerate(new) if x.startswith(S0_LOOP_PACKET_STATUS)]
    if not (len(oi) == len(ni) == 1 and len(old) == len(new)
            and old[:oi[0]] + old[oi[0] + 1:] == new[:ni[0]] + new[ni[0] + 1:] and oi[0] == ni[0]):
        return "the packet differs from the pinned starting one beyond its one `**Review and recovery status:**` paragraph"
    return None


def s0_loop_gate_reason(cfg, t, tasks):
    """None for a task outside the loop or the one fully authorised loop write; else an explicit S0_LOOP_* reason."""
    if not s0_loop_marked(t):
        return None
    problem = s0_loop_shape_problem(t)
    if problem:
        return f"S0_LOOP_INVALID_TASK {t['id']}: {problem}"
    if os.path.lexists(cfg.home / "acceptances" / f"{S0_RECEIPT}.json"):
        return "S0_LOOP_CLOSED: an S0 authority receipt exists in acceptances/ and binds the slice documents"
    if t.get("attempts"):
        return f"S0_LOOP_ATTEMPT_USED {t['id']}: the single loop write attempt was already started"
    others = sorted(x["id"] for x in tasks.values() if x.get("id") != t["id"] and s0_loop_marked(x) and x.get("role") in WRITE_ROLES)
    if others:
        return f"S0_LOOP_SECOND_WRITE: loop write {others[0]} already exists; the loop rebind is one-time"
    busy = _s0_competing_writes(tasks, t)
    if busy:
        return f"S0_LOOP_CONCURRENT_WRITE: {busy[0]} is a pending write in an S0 chain or touching S0 files"
    try:
        if {p: _path_hash(Path(cfg.repo) / p) for p in S0_DOC_PATHS} != S0_LOOP_BASE:
            return "S0_LOOP_STALE_DRAFT: a document is not the pinned current content"
        verify_s0_loop_authority(cfg, tasks, require_base=True)
    except GateError as e:
        return f"S0_LOOP_AUTHORITY_UNVERIFIED: {e}"
    return None


def s0_loop_review_reason(cfg, t, tasks):
    """The one exact-bound owner-CLI Opus review of the sole DONE loop write: any other review task bound to it, in any
    status, has used the slot; there is no retry or review shopping."""
    w = tasks.get((t.get("review_of") or {}).get("task_id"))
    if not (w and s0_loop_marked(w)):
        return None
    if t.get("source") is not None:
        return "S0_LOOP_REVIEW_UNSUPPORTED: the loop review is owner-CLI routed only"
    if t.get("review_retry_of") or t.get("review_candidate"):
        return "S0_LOOP_REVIEW_UNSUPPORTED: the loop write gets one bound review and no retry"
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement" and w.get("status") == "DONE"
            and w.get("attempts") == 1 and (w.get("evidence") or {}).get("violations") == []):
        return "S0_LOOP_REVIEW_UNSUPPORTED: only a DONE one-attempt MOD-004 loop write can be reviewed here"
    problem = s0_loop_shape_problem(w)
    if problem:
        return f"S0_LOOP_REVIEW_UNSUPPORTED: {problem}"
    if [x["id"] for x in tasks.values() if isinstance(x, dict) and s0_loop_marked(x) and x.get("role") in WRITE_ROLES] != [w["id"]]:
        return "S0_LOOP_REVIEW_UNSUPPORTED: the loop write must be the only loop write"
    want = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if not (len(want) == len(S0_DOC_PATHS) and sorted(c["path"] for c in want) == sorted(S0_DOC_PATHS)
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) and c["sha256"] != S0_LOOP_BASE[c["path"]]
                    for c in want)
            and _changed_pairs((t.get("review_of") or {}).get("changed")) == want):
        return "S0_LOOP_REVIEW_UNSUPPORTED: review must bind the exact changed hashes of both document files, each different from the base"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_LOOP_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review loop write {w['id']}"
    if not _hashes_current(cfg, (w.get("evidence") or {}).get("changed")):
        return "S0_LOOP_REVIEW_BINDING_STALE: the document files no longer match the write's recorded hashes"
    problem = _s0_loop_docs_problem(cfg)
    if problem:
        return f"S0_LOOP_REVIEW_UNSUPPORTED: {problem}; the one review slot is not spent on an unfinished write"
    try:
        verify_s0_loop_authority(cfg, tasks, require_base=False)
    except GateError as e:
        return f"S0_LOOP_REVIEW_AUTHORITY_UNVERIFIED: {e}"
    return None


def _s0_rebind_one_approved_review(tasks, w):
    reviews = [x for x in tasks.values() if isinstance(x, dict) and (x.get("review_of") or {}).get("task_id") == w["id"]]
    return (len(reviews) == 1 and reviews[0].get("role") == "code-review" and reviews[0].get("status") == "DONE"
            and reviews[0].get("module") == w.get("module") == S0_MODULE
            and reviews[0].get("source") != "handoff" and not reviews[0].get("review_retry_of")
            and (reviews[0].get("evidence") or {}).get("review_outcome") == "APPROVED"
            and review_verdict(tasks, w["id"]) == "APPROVED" and _bound_review_ok(w, reviews[0]))


def _s0_rebind_repair_done(cfg, tasks, ws):
    """The pinned incomplete root plus its one repair, no other rebind write; the repair is DONE, its one bound review
    APPROVED both changed documents, they still hash to what was reviewed, and the certificate carries the final packet hash."""
    if sorted(x["id"] for x in ws) != sorted([S0_REBIND_ROOT_ID, S0_REBIND_REPAIR_ID]):
        raise GateError("S0 rebind: exactly the incomplete root write and its one repair must exist")
    problem = _s0_rebind_root_problem(tasks) or _s0_rebind_repair_write_problem(tasks[S0_REBIND_REPAIR_ID])
    if problem:
        raise GateError(f"S0 rebind: {problem}")
    w = tasks[S0_REBIND_REPAIR_ID]
    if not _hashes_current(cfg, (w.get("evidence") or {}).get("changed")):
        raise GateError("S0 rebind: the repair write's documents are not still current")
    if not _s0_rebind_one_approved_review(tasks, w):
        raise GateError("S0 rebind: the repair write lacks its one exact-bound, verified-Opus APPROVED review")
    hashes = {c["path"]: c["sha256"] for c in _changed_pairs((w.get("evidence") or {}).get("changed"))}
    problem = _s0_rebind_packet_problem(cfg, hashes)
    if problem:
        raise GateError(f"S0 rebind: {problem}")
    return hashes


def _s0_rebind_done(cfg, tasks):
    """The rebind is complete and approved; the documents still hash to what was reviewed. Returns the approved
    {path: sha256} of both documents. Once the pinned incomplete root exists or any repair exists, ONLY the exact
    root+repair lineage completes it (the root is never reviewed). Raises GateError otherwise."""
    ws = [x for x in tasks.values() if isinstance(x, dict) and s0_rebind_marked(x) and x.get("role") in WRITE_ROLES]
    if any(s0_rebind_repair_marked(x) or _s0_rebind_is_pinned_root(x) for x in ws):
        return _s0_rebind_repair_done(cfg, tasks, ws)
    if len(ws) != 1:
        raise GateError("S0 rebind: exactly one document rebind write must exist")
    w = ws[0]
    changed = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if not (w.get("status") == "DONE" and s0_rebind_shape_problem(w) is None
            and sorted(c["path"] for c in changed) == sorted(S0_DOC_PATHS)
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) and c["sha256"] != S0_REBIND_BASE[c["path"]]
                    for c in changed)
            and _hashes_current(cfg, (w.get("evidence") or {}).get("changed"))):
        raise GateError("S0 rebind: the rebind write is not DONE with both documents changed and still current")
    if not _s0_rebind_one_approved_review(tasks, w):
        raise GateError("S0 rebind: the rebind write lacks its one exact-bound, verified-Opus APPROVED review")
    return {c["path"]: c["sha256"] for c in changed}


def _s0_git_blob(cfg, commit, path, label):
    try:
        shown = git_run(cfg.repo, "show", f"{commit}:{path}", timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise GateError(f"{label}: cannot read {path} at {commit[:12]}")
    if shown.returncode != 0:
        raise GateError(f"{label}: {path} is not committed at {commit[:12]}")
    return shown.stdout


def _s0_git_blob_sha(cfg, commit, path, label):
    return hashlib.sha256(_s0_git_blob(cfg, commit, path, label)).hexdigest()


def _s0_rebound_docs_published(cfg, receipt, rebound):
    """The rebuilt receipt's eligibility subject IS the rebound certificate (same path, same bytes), and both rebound
    documents are clean, tracked, and committed byte-for-byte at that subject's operator-attested-CI ancestor commit,
    so the correction cannot start while the reviewed documents are merely uncommitted or CI-pending."""
    cert_path, qa_path = S0_DOC_PATHS
    label = "S0 test rebound documents"
    e = _s0_json(receipt, "S0 receipt").get("subjects", {}).get("eligibility")
    if not (isinstance(e, dict) and e.get("path") == cert_path and e.get("sha256") == rebound.get(cert_path)):
        raise GateError(f"{label}: the receipt's eligibility subject is not the rebound certificate {cert_path}")
    commit = e.get("commit")
    if not (isinstance(commit, str) and SHA_RE.fullmatch(commit) and _s0_ci_ok(e.get("ci"), commit) and _is_ancestor(cfg, commit)):
        raise GateError(f"{label}: the eligibility commit is not an ancestor with exact-commit CI evidence")
    for path in (cert_path, qa_path):
        if hashlib.sha256(_read_bounded(Path(cfg.repo) / path, REVIEW_MAX_BYTES)).hexdigest() != rebound.get(path):
            raise GateError(f"{label}: {path} is not the approved rebound content")
        if _s0_git_blob_sha(cfg, commit, path, label) != rebound.get(path):
            raise GateError(f"{label}: {path} at the eligibility commit is not the approved rebound content")
    try:
        status = git_run(cfg.repo, "status", "--porcelain=v1", "--untracked-files=all", "--", cert_path, qa_path, timeout=20)
        flags = git_run(cfg.repo, "ls-files", "-v", "--", cert_path, qa_path, timeout=20)
    except (OSError, subprocess.SubprocessError):
        raise GateError(f"{label}: cannot check the document working-tree state")
    tracked = [ln[:2] for ln in flags.stdout.decode("utf-8", "replace").splitlines()]
    if not (status.returncode == 0 and status.stdout == b"" and flags.returncode == 0 and tracked == ["H "] * 2):
        raise GateError(f"{label}: the rebound documents are not clean, tracked and committed")


def verify_s0_test_authority(cfg, tasks):
    """Everything the test-only correction needs, before it starts and again before it may be DONE: the recovery
    authority, a completed and approved document rebind, a rebuilt (never the preserved) six-subject S0 receipt that
    fully verifies for THIS runner and whose eligibility subject is exactly the rebound certificate, the rebound
    documents clean and committed at that subject's commit, and the original write/review pins."""
    verify_s0_test_recovery_authority(cfg, tasks)
    rebound = _s0_rebind_done(cfg, tasks)
    path = cfg.home / "acceptances" / f"{S0_RECEIPT}.json"
    receipt = _read_bounded(path, RECEIPT_MAX_BYTES)
    if hashlib.sha256(receipt).hexdigest() in (S0_PRE_TEST_RECEIPT_SHA, S0_OLD_RECEIPT_SHA):
        raise GateError("S0 test: acceptances/ holds a preserved, stale S0 receipt, not a rebuilt one")
    verify_s0_authority(cfg, tasks)
    if _read_bounded(path, RECEIPT_MAX_BYTES) != receipt:
        raise GateError("S0 test: the S0 receipt changed while it was being verified")
    _s0_rebound_docs_published(cfg, receipt, rebound)


def s0_test_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the S0 test correction is a MOD-004 implement task only"
    if t.get("source") == "handoff":
        return "the planner cannot propose the S0 test correction"
    if any(t.get(k) is not None for k in ("remediation_of", "review_retry_of", "accounting_recovery_of", "review_of",
                                          "review_candidate", "doc_base")):
        return "remediation_of, review_retry_of, accounting_recovery_of, doc_base and review binding fields are rejected"
    if t.get("allowed_paths") != [S0_TEST_PATH] or t.get("expected_changes") != [S0_TEST_PATH]:
        return "allowed_paths and expected_changes must be exactly the S0 test file"
    if t.get("verify_cmd") != [S0_PYTHON, "-m", "unittest", S0_VERIFY_MODULE]:
        return "verify_cmd must be exactly the Python 3.13 S0 unittest module"
    return None


def s0_test_gate_reason(cfg, t, tasks):
    """None for a task outside the correction or the one fully authorised test-only write; else an explicit S0_TEST_* reason."""
    if not s0_test_marked(t):
        return None
    problem = s0_test_shape_problem(t)
    if problem:
        return f"S0_TEST_INVALID_TASK {t['id']}: {problem}"
    others = sorted(x["id"] for x in tasks.values() if x.get("id") != t["id"] and s0_test_marked(x) and x.get("role") in WRITE_ROLES)
    if others:
        return f"S0_TEST_SECOND_WRITE: test correction {others[0]} already exists; the correction is one-time"
    if t.get("attempts") and t.get("stage") != "verify_pending":  # one child attempt, whatever ended it
        return f"S0_TEST_ATTEMPT_USED {t['id']}: the single test correction attempt was already started"
    busy = _s0_competing_writes(tasks, t)
    if busy:
        return f"S0_TEST_CONCURRENT_WRITE: {busy[0]} is a pending write in an S0 chain or touching S0 files"
    try:
        if _path_hash(Path(cfg.repo) / S0_VALIDATOR_PATH) != S0_VALIDATOR_SHA:
            return "S0_TEST_VALIDATOR_CHANGED: the validator is not the pinned sha256"
        if _path_hash(Path(cfg.repo) / S0_TEST_PATH) != S0_TEST_START_SHA:
            return "S0_TEST_STALE_START: the test file is not the pinned starting sha256"
    except OSError as e:
        return f"S0_TEST_UNVERIFIABLE: {type(e).__name__}"
    try:
        verify_s0_test_authority(cfg, tasks)
    except GateError as e:
        return f"S0_TEST_AUTHORITY_UNVERIFIED: {e}"
    return None


def s0_test_review_reason(cfg, t, tasks):
    """The one Opus review of the test-only correction. It must bind BOTH the corrected test (hash from the write's
    runner evidence) and the unchanged validator, and name both path/hash pairs. Any other review task bound to the
    write, in any status, has used the slot; there is no retry. The original CHANGES_REQUESTED review stays as it was."""
    w = tasks.get((t.get("review_of") or {}).get("task_id"))
    if not (w and s0_test_marked(w)):
        return None
    if t.get("source") == "handoff":
        return "S0_TEST_REVIEW_UNSUPPORTED: the planner cannot propose a test-correction review; it is owner-routed"
    if t.get("review_retry_of") or t.get("review_candidate"):
        return "S0_TEST_REVIEW_UNSUPPORTED: the test correction gets one bound review and no retry"
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement" and w.get("status") == "DONE"):
        return "S0_TEST_REVIEW_UNSUPPORTED: only a DONE MOD-004 test correction can be reviewed here"
    changed = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if not (len(changed) == 1 and changed[0]["path"] == S0_TEST_PATH and isinstance(changed[0]["sha256"], str)
            and SHA256_RE.fullmatch(changed[0]["sha256"]) and changed[0]["sha256"] != S0_TEST_START_SHA):
        return "S0_TEST_REVIEW_UNSUPPORTED: the correction write must have changed exactly the test file"
    want = _changed_pairs(_review_want(w))
    if _changed_pairs((t.get("review_of") or {}).get("changed")) != want:
        return "S0_TEST_REVIEW_UNSUPPORTED: review must bind the corrected test AND the unchanged validator hashes"
    prompt = t.get("prompt")
    if not (isinstance(prompt, str) and all(c["path"] in prompt and c["sha256"] in prompt for c in want)):
        return "S0_TEST_REVIEW_UNSUPPORTED: the review prompt must name both path/sha256 pairs of the complete candidate"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_TEST_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review test correction {w['id']}"
    try:
        _s0_original_pins(cfg, tasks)
    except GateError as e:
        return f"S0_TEST_REVIEW_ORIGINAL_CHANGED: {e}"
    if not _hashes_current(cfg, want):
        return "S0_TEST_REVIEW_BINDING_STALE: the test file or the validator no longer matches the bound candidate"
    try:
        verify_s0_test_authority(cfg, tasks)
    except GateError as e:
        return f"S0_TEST_REVIEW_AUTHORITY_UNVERIFIED: {e}"
    return None


MAX_PRODUCT_CORRECTIONS = 3  # total correction cycles per root product task, across all findings, ids, sessions and restarts
CAP_ACCOUNTING_WRITES = (ACCOUNTING_RECOVERY_WRITE, "mod004-cap-budget-accounting-sonnet-20261019")
_FINDING_NOISE = re.compile(r"[0-9a-f]{7,}|\d+")


def product_loop_eligible(tasks, t):
    """Generic product writes only: never MOD-000 infrastructure, any S0 lane, the CAP accounting chain or a review retry."""
    if t.get("role") not in WRITE_ROLES or t.get("module") in (None, "MOD-000"):
        return False
    if t.get("accounting_recovery_of") or t.get("review_retry_of") or t.get("id") in CAP_ACCOUNTING_WRITES:
        return False
    if any(f(t) for f in (s0_marked, s0_test_marked, s0_touches, s0_doc_marked, s0_refresh_marked, s0_rebind_marked,
                          s0_loop_marked, s0_doc_touches, s0_qa_marked)):
        return False
    return not accounting_recovery_chain(tasks, t)


def product_policy_root(tasks, t):
    """True when t's remediation ancestry (walked iteratively, no recursion into the chain validators) ends at a root
    stamped by the new loop policy. Unmarked historical roots and their corrections keep the old MAX_REMEDIATIONS rule."""
    seen = set()
    while isinstance(t, dict) and t.get("id") not in seen and len(seen) <= 64:
        seen.add(t.get("id"))
        if not t.get("remediation_of"):
            return t.get("remediation_root") == t.get("id") and t.get("remediation_cycle") == 0
        t = tasks.get(t["remediation_of"])
    return False


def product_new_policy(tasks, t):
    """True for a product write that belongs to the new loop: a correction of a policy-stamped chain, a stamped root, or a
    root not yet recorded (newly proposed or ingested). A recorded unstamped root is historical."""
    if t.get("remediation_of"):
        return product_policy_root(tasks, tasks.get(t["remediation_of"]))
    return "remediation_root" in t or t.get("id") not in tasks


def _finding_fingerprint(kind, text):
    """Conservative textual fingerprint of recorded review/verifier output (lowercased, digits and hex ids masked,
    whitespace collapsed). Equal fingerprints stop the loop; different wording of one root cause is NOT detected
    (only the cycle cap bounds that). Missing or empty evidence yields None, which callers treat as unverifiable."""
    norm = " ".join(_FINDING_NOISE.sub("#", text.lower()).split()) if isinstance(text, str) else ""
    return hashlib.sha256(f"{kind}\0{norm}".encode()).hexdigest() if norm else None


def product_rejection(tasks, w):
    """(kind, fingerprint) when write w was rejected by a runner-verified bound Opus CHANGES_REQUESTED review or by a
    recorded failed verification (verifier genuinely executed, exit > 0) that left changed-file evidence and NO other violation; else None. A BLOCKED write
    with any mixed or other violation is not correctable. Never relabels any verdict."""
    ev = w.get("evidence") or {}
    if w.get("status") == "DONE":
        cr = [a for a in review_attempts(tasks, w["id"]) if _bound_review_ok(w, a)
              and a.get("status") == "BLOCKED" and a.get("blocked_reason") == "REVIEW_CHANGES_REQUESTED"
              and (a.get("evidence") or {}).get("violations") == ["REVIEW_CHANGES_REQUESTED"]
              and a["evidence"]["review_outcome"] == "CHANGES_REQUESTED"]
        return ("CHANGES_REQUESTED", _finding_fingerprint("review", cr[0].get("result"))) if cr else None
    v = ev.get("verify") or {}
    if (w.get("status") == "BLOCKED" and w.get("blocked_reason") == "VERIFICATION_FAILED"
            and ev.get("violations") == ["VERIFICATION_FAILED"] and ev.get("changed")
            and isinstance(v.get("exit"), int) and not isinstance(v["exit"], bool) and v["exit"] > 0):  # -1 = sandbox refusal/timeout/could not run
        return "VERIFICATION_FAILED", _finding_fingerprint("verify", " ".join(map(str, v.get("cmd") or [])) + "\n" + str(v.get("tail") or ""))
    return None


def _candidate(pairs):
    return frozenset((c["path"], c["sha256"]) for c in _changed_pairs(pairs))


def product_chain(tasks, w):
    """Root-first remediation ancestry of w, reconstructed from state. Raises ValueError (message starts with its
    REMEDIATION_ code) for a cycle, a missing/foreign/ineligible ancestor, a disagreeing persisted counter or a
    correction whose changed bytes equal an earlier candidate of the same root."""
    chain, seen = [], set()
    while w is not None:
        if w["id"] in seen or len(chain) > 64:
            raise ValueError("REMEDIATION_LINEAGE_INVALID: cyclic remediation ancestry")
        seen.add(w["id"])
        chain.append(w)
        parent = w.get("remediation_of")
        if not parent:
            break
        w = tasks.get(parent)
        if w is None:
            raise ValueError(f"REMEDIATION_LINEAGE_INVALID: remediation_of {parent} is not recorded")
    chain.reverse()
    root, earlier = chain[0], []
    for i, n in enumerate(chain):
        if not product_loop_eligible(tasks, n) or n.get("module") != root.get("module"):
            raise ValueError(f"REMEDIATION_LINEAGE_INVALID: {n['id']} is not a product write of the root's module")
        if "remediation_root" in n and (n["remediation_root"], n.get("remediation_cycle")) != (root["id"], i):
            raise ValueError(f"REMEDIATION_COUNTER_MISMATCH: persisted counter of {n['id']} disagrees with its ancestry")
        cand = _candidate((n.get("evidence") or {}).get("changed"))
        if i and cand and cand in earlier:
            raise ValueError(f"REMEDIATION_NO_PROGRESS: {n['id']} changed the same bytes as an earlier candidate")
        earlier.append(cand)
    return chain


def product_progress_problem(tasks, t, new_changed):
    """None, or why the just-written correction t carries no new bytes relative to its own ancestry."""
    cand = _candidate(new_changed)
    if not cand:
        return "the correction changed no files"
    w = tasks.get(t.get("remediation_of"))
    for _ in range(64):
        if w is None:
            return None
        if _candidate((w.get("evidence") or {}).get("changed")) == cand:
            return f"identical changed bytes to {w['id']}"
        w = tasks.get(w.get("remediation_of"))
    return "remediation ancestry too deep"


def product_correction_reason(cfg, tasks, t, tip):
    """Gate for a product correction t of the rejected write `tip`; None when allowed, else an explicit reason."""
    module = t["module"]
    if t.get("remediation_of") != tip["id"]:
        return (f"REMEDIATION_LINEAGE_REQUIRED {module}: a correction must name the rejected write {tip['id']} "
                "as remediation_of; a new task id never starts a new budget")
    try:
        chain = product_chain(tasks, tip)
    except ValueError as e:
        return str(e)
    rej = [product_rejection(tasks, w) for w in chain]
    if not all(rej):
        return (f"REMEDIATION_LINEAGE_INVALID {module}: every ancestor of {tip['id']} must be a bound Opus "
                "CHANGES_REQUESTED review or a recorded failed verification")
    if tip.get("status") == "DONE" and not _hashes_current(cfg, (tip.get("evidence") or {}).get("changed")):
        return f"REMEDIATION_BINDING_STALE {module}: files of {tip['id']} no longer match the rejected candidate"
    if len(chain) > MAX_PRODUCT_CORRECTIONS:
        if len(chain) == MAX_PRODUCT_CORRECTIONS + 1 and t.get("id") == D16_F34_WRITE:
            try:
                verify_d16_f34_authority(cfg, tasks, t)
            except (GateError, OSError) as e:
                return f"D16_F34_UNVERIFIED {t['id']}: {e}"
        else:
            return (f"REMEDIATION_LIMIT {module}: root {chain[0]['id']} already used {MAX_PRODUCT_CORRECTIONS} "
                    "correction cycles")
    fps = [r[1] for r in rej]
    if None in fps:
        return f"REMEDIATION_FINGERPRINT_UNVERIFIABLE {module}: a rejection of {chain[0]['id']} left no recorded finding text"
    if len(set(fps)) < len(fps):
        return (f"REMEDIATION_NO_PROGRESS {module}: root {chain[0]['id']} was rejected again with an identical "
                "recorded finding/failure")
    if any(x.get("remediation_of") == tip["id"] and x.get("id") != t.get("id") for x in tasks.values()):
        return f"REMEDIATION_BRANCH {module}: {tip['id']} already has another correction"
    if "remediation_root" in t and (t["remediation_root"], t.get("remediation_cycle")) != (chain[0]["id"], len(chain)):
        return f"REMEDIATION_COUNTER_MISMATCH {module}: persisted counter disagrees with the task ancestry"
    if not all(in_scope(p, chain[0].get("allowed_paths") or []) for p in t.get("allowed_paths") or []):
        return f"REMEDIATION_OUT_OF_SCOPE {module}: a correction must stay inside root {chain[0]['id']}'s allowed paths"
    return None


def stamp_product_remediation(tasks, t):
    """Persist the root identity and cycle derived from ancestry on a newly accepted eligible product write."""
    if not product_loop_eligible(tasks, t):
        return
    if not t.get("remediation_of"):
        t["remediation_root"], t["remediation_cycle"] = t["id"], 0
        return
    parent = tasks.get(t["remediation_of"])
    if not product_policy_root(tasks, parent):
        return  # a correction of an unmarked historical root stays under the old rule
    try:
        chain = product_chain(tasks, parent)
    except ValueError:
        return  # left unstamped: the gate refuses it with the precise reason
    t["remediation_root"], t["remediation_cycle"] = chain[0]["id"], len(chain)


def product_lineage_reason(cfg, tasks, t, set_aside=frozenset()):
    """(decided, reason) from a durable per-root inspection for a new eligible product write t: every stamped root of t's module is rebuilt
    from state and its single leaf judged. A BLOCKED/FAILED leaf that is not a genuine product rejection blocks every
    new root and correction of the module; a genuinely rejected leaf (failed verification, or DONE with a bound
    CHANGES_REQUESTED) admits only a correction naming it; approved leaves do not block. An unfinished (QUEUED/RUNNING/unknown) leaf, or a DONE leaf without a bound review, blocks
    every other new root, sibling and correction; t itself is excluded, so its own legitimate correction can still run.
    Only roots stamped by the new policy are inspected. `set_aside` (ids, only ever the verified exhausted D16 chain, for the
    one verified D16 successor root) are not inspected."""
    module = t["module"]
    nodes = {}
    for x in tasks.values():
        if (isinstance(x, dict) and x.get("id") != t.get("id") and x.get("id") not in set_aside
                and x.get("module") == module and x.get("role") in WRITE_ROLES
                and ("remediation_root" in x or x.get("remediation_of")) and product_loop_eligible(tasks, x)):
            try:
                nodes[x["id"]] = (product_chain(tasks, x)[0]["id"], x)
            except ValueError as e:
                if "remediation_root" in x:
                    return True, str(e)
    groups = {}
    for root, x in nodes.values():
        groups.setdefault(root, []).append(x)
    blocked, tips = [], {}
    for root in sorted(groups):
        members = groups[root]
        if not product_policy_root(tasks, members[0]):
            continue
        parents = {}
        for x in members:
            if x.get("remediation_of"):
                parents.setdefault(x["remediation_of"], []).append(x["id"])
        branched = sorted(p for p, kids in parents.items() if len(kids) > 1)
        if branched:
            return True, f"REMEDIATION_BRANCH {module}: {branched[0]} already has more than one correction"
        leaves = [x for x in members if x["id"] not in parents]
        if len(leaves) != 1:
            return True, f"REMEDIATION_LINEAGE_INVALID {module}: root {root} does not have exactly one leaf"
        leaf = leaves[0]
        if leaf.get("status") not in ("BLOCKED", "FAILED", "DONE"):
            return True, (f"REMEDIATION_ROOT_PENDING {module}: root {root} has unfinished leaf {leaf['id']} "
                          f"({leaf.get('status')}); no new root, sibling or correction is admitted until it ends")
        if product_rejection(tasks, leaf):
            tips[leaf["id"]] = leaf
        elif leaf["status"] != "DONE":
            blocked.append((root, leaf))
        elif not any(_bound_review_ok(leaf, a) and (a.get("evidence") or {}).get("review_outcome") in ("APPROVED", "CHANGES_REQUESTED")
                     for a in review_attempts(tasks, leaf["id"])):
            return True, (f"REVIEW_REQUIRED {module}: root {root} leaf {leaf['id']} has no independent Opus code-review "
                          "attempt bound to it; no new root is admitted until it is reviewed")
    if blocked:
        root, leaf = blocked[0]
        return True, (f"REMEDIATION_ROOT_BLOCKED {module}: root {root} ended at {leaf['id']} ({leaf['status']}"
                f"{'/' + str(leaf['blocked_reason']) if leaf.get('blocked_reason') else ''}) which is not a correctable "
                "product rejection; no new root or correction is admitted until it is resolved")
    if t.get("remediation_of") in tips:
        return True, product_correction_reason(cfg, tasks, t, tips[t["remediation_of"]])
    if tips:
        return True, (f"REMEDIATION_LINEAGE_REQUIRED {module}: rejected write {sorted(tips)[0]} must be corrected "
                "through remediation_of; a new task id never starts a new budget")
    return False, None


# ------------------------------------------------ MOD-004 non-CAP design/documentation admission
# OWNER-2026-10-24-mod004-fullscope-recovery.md: the terminal CAP-accounting write (and its BLOCKED review) is a closed,
# immutable historical chain. It must not be the predecessor of a NEW non-CAP documentation/design write, but it stays
# blocked for every CAP path and is never rewritten. Pure read-only checks; admission fails closed on any doubt.
NONCAP_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-24-mod004-fullscope-recovery.md"
NONCAP_OWNER_SHA = "5a80cf3b11d4940a93d57cc8ef9900eb1a4955d49703b91fbb8d49fcb85ab44a"
NONCAP_OWNER_COMMIT = "9c7289e389463a8b780cf41c15c54f40ec46c496"
NONCAP_OWNER_CI_RUN = "40126487225"
NONCAP_RECEIPT = "MOD-004-NONCAP-DESIGN"  # operator-written <home>/acceptances/MOD-004-NONCAP-DESIGN.json: one noncap_owner subject
NONCAP_TERMINAL_WRITE = "mod004-cap-exception-accounting-remed2-sonnet-20261019"
NONCAP_TERMINAL_REVIEW = "mod004-cap-exception-accounting-remed2-opus-review-20261019"
NONCAP_CAP_CHAIN = ("mod004-cap-budget-accounting-sonnet-20261019", ACCOUNTING_RECOVERY_WRITE,
                    "mod004-cap-exception-accounting-remed-sonnet-20261019", NONCAP_TERMINAL_WRITE)
# exactly the three files the owner record Covers for design work; no directory wildcard or name heuristic widens this
NONCAP_DESIGN_PATHS = frozenset({"knowledge/03-Modules/MOD-004/MOD-004.md", "knowledge/03-Modules/MOD-004/REQUIREMENTS.md",
                                 "knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md"})
NONCAP_FORBIDDEN_NAME = re.compile(r"(?i)(?:^|[^a-z])(?:cap|manifest|lock|rules?|candidates?)(?:[^a-z]|$)")


def _noncap_path_ok(p):
    return (isinstance(p, str) and p in NONCAP_DESIGN_PATHS and ".." not in Path(p).parts
            and not NONCAP_FORBIDDEN_NAME.search(Path(p).name))


def noncap_cli_remediation_shape(a):
    """Owner-CLI prefilter ONLY (no authority): True for a plain MOD-004 implement write confined to the exact non-CAP
    design paths. Whether the correction is allowed (parent, bound review, root/cycle, fingerprints, max-three, fresh
    diff, sole writer) is decided only by enqueue -> gate_reason -> product_lineage_reason / noncap_shape_problem."""
    paths = (a.allow or []) + (a.expect or [])
    return (a.module == "MOD-004" and a.role == "implement" and not a.plan_phase and bool(a.allow) and bool(a.expect)
            and not (a.review_of or a.review_retry_of or a.accounting_recovery_of or a.doc_base)
            and all(_noncap_path_ok(p) for p in paths))


def noncap_shape_problem(tasks, t):
    """None only for a NEW MOD-004 implement write confined to exact design/documentation files; never a planner task,
    S0 or CAP-accounting task, review retry, or a correction whose ancestry touches the CAP chain or other paths."""
    if t.get("module") != "MOD-004" or t.get("role") != "implement":
        return "a MOD-004 implement task only"
    if t.get("source") is not None or t.get("review_retry_of") or t.get("accounting_recovery_of") or t.get("review_of"):
        return "planner, retry, accounting-recovery and review-bound tasks are excluded"
    if t.get("id") in NONCAP_CAP_CHAIN:
        return "a CAP-accounting task id"
    if t.get("plan_phase") and re.search(r"(?i)cap|s0", str(t["plan_phase"])):
        return "CAP or S0 plan phase"
    if any(f(t) for f in (s0_marked, s0_test_marked, s0_touches, s0_doc_marked, s0_refresh_marked, s0_rebind_marked,
                          s0_loop_marked, s0_doc_touches, s0_qa_marked)):
        return "S0 task"
    allowed, expected = t.get("allowed_paths") or [], t.get("expected_changes") or []
    if not (allowed and expected and all(_noncap_path_ok(p) for p in allowed + expected)):
        return "paths must be exact owner-covered design/documentation files"
    anc, seen = t.get("remediation_of"), set()
    while anc:
        a = tasks.get(anc)
        if not (isinstance(a, dict) and anc not in seen and len(seen) < 64 and anc not in NONCAP_CAP_CHAIN
                and a.get("module") == "MOD-004" and all(_noncap_path_ok(p) for p in a.get("allowed_paths") or [])):
            return "remediation ancestry is not a non-CAP design chain"
        seen.add(anc)
        anc = a.get("remediation_of")
    return None


def verify_noncap_authority(cfg, tasks):
    """Offline re-verification (read-only, no queue/lock/write): the exact historical CAP chain is terminal and
    unchanged in meaning, and the pinned owner record is committed, CI-green and independently Opus-APPROVED."""
    ws = [tasks.get(i) for i in NONCAP_CAP_CHAIN]
    if not all(isinstance(w, dict) and w.get("module") == "MOD-004" and w.get("role") in WRITE_ROLES
               and w.get("status") == "DONE" for w in ws):
        raise GateError("non-CAP: the historical CAP-accounting writes are not the exact DONE chain")
    term = tasks[NONCAP_TERMINAL_WRITE]
    if not accounting_recovery_chain(tasks, term) or any(x.get("remediation_of") == NONCAP_TERMINAL_WRITE
                                                         for x in tasks.values() if isinstance(x, dict)):
        raise GateError("non-CAP: the terminal CAP-accounting write is not the terminal link of the audited chain")
    bound = [r for r in tasks.values() if isinstance(r, dict) and r.get("role") == "code-review"
             and (r.get("review_of") or {}).get("task_id") == NONCAP_TERMINAL_WRITE]
    rv = bound[0] if len(bound) == 1 else {}
    ev = rv.get("evidence") or {}
    if not (rv.get("id") == NONCAP_TERMINAL_REVIEW and rv.get("status") == "BLOCKED" and rv.get("blocked_reason") == "REVIEW_BLOCKED"
            and ev.get("review_outcome") == "BLOCKED" and ev.get("review_bound_verified") is True
            and _bound_review_ok(term, rv) and review_verdict(tasks, NONCAP_TERMINAL_WRITE) is None):
        raise GateError("non-CAP: the terminal CAP-accounting review is missing, ambiguous or not the bound BLOCKED review")
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{NONCAP_RECEIPT}.json", RECEIPT_MAX_BYTES), "non-CAP receipt")
    sub = r.get("subjects")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "subjects"} and r["schema"] == SCHEMA
            and r["module"] == "MOD-004" and r["kind"] == "mod004-noncap-design-authority"
            and isinstance(r["operator"], str) and r["operator"].strip() and isinstance(sub, dict)
            and set(sub) == {"noncap_owner"}):
        raise GateError("non-CAP receipt schema mismatch")
    o = sub["noncap_owner"]
    if not (isinstance(o, dict) and o.get("path") == NONCAP_OWNER_PATH and o.get("sha256") == NONCAP_OWNER_SHA
            and o.get("commit") == NONCAP_OWNER_COMMIT and (o.get("ci") or {}).get("run_id") == NONCAP_OWNER_CI_RUN):
        raise GateError("non-CAP: the owner record is not the pinned file, commit and CI run")
    _s0_subject(cfg, "noncap_owner", o, tasks, set(), {"noncap_owner": re.compile(re.escape(NONCAP_OWNER_PATH))})


def noncap_probe(cfg):
    """Read-only gate probe (reads state.json and the repo; queues, locks and writes nothing, consumes no entitlement).
    Returns {case: refusal-or-None}; a healthy gate admits only 'design' and refuses every other case."""
    state = json.loads(_read_bounded(cfg.home / "state.json", 64 * 1024 * 1024))
    base = {"module": "MOD-004", "role": "implement", "prompt": "read-only probe"}
    d = "knowledge/03-Modules/MOD-004/MOD-004.md"
    cases = {"design": {"allowed_paths": [d], "expected_changes": [d]},
             "cap": {"allowed_paths": list(ACCOUNTING_RECOVERY_PATHS), "expected_changes": list(ACCOUNTING_RECOVERY_PATHS)},
             "s0_product": {"allowed_paths": list(S0_PATHS), "expected_changes": list(S0_PATHS)}}
    out = {}
    for name, extra in cases.items():
        try:
            out[name] = gate_reason(cfg, validate_task(base | {"id": f"noncap-probe-{name}"} | extra, cfg), state["tasks"])
        except Exception as e:
            out[name] = f"NONCAP_PROBE_UNVERIFIABLE: {type(e).__name__}"
    return out


# ------------------------------------------------ MOD-004 D16 design successor (single-use admission)
# OWNER-2026-10-25-mod004-d16-design-successor.md: ONE owner-CLI, non-CAP, ADR-only design root with a fixed id may start although
# the exhausted D16 root is a rejected tip. Read-only and fail-closed; it consumes nothing, rewrites no history, opens no other
# root, and the successor's own corrections stay under the ordinary per-root three-cycle policy.
D16_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-25-mod004-d16-design-successor.md"
D16_OWNER_SHA = "b9e497ef48211e14203d7444f7f35e2ad4ecab6e743faaba6aee7a5d90eabb0a"
D16_OWNER_COMMIT = "65ef7f00d6c05d0b4ec343f05ebb6526fbc36be9"
D16_OWNER_CI_RUN = "40169965655"
D16_OWNER_REVIEW = "mod004-d16-successor-owner-opus-20261025"
D16_RECEIPT = "MOD-004-D16-SUCCESSOR"  # operator-written <home>/acceptances/MOD-004-D16-SUCCESSOR.json: one d16_owner subject
D16_ADR_PATH = "knowledge/00-Decisions/ADR-0002-mod004-control-plane-isolation.md"
D16_SUCCESSOR_ID = "mod004-d16-db-command-successor-sonnet-20261025"
D16_OLD_ROOT = "mod004-fullscope-contained-adr-sonnet-20261025"
D16_OLD_TERMINAL = "mod004-fullscope-contained-adr-remed3-sonnet-20261025"
D16_OLD_TERMINAL_REVIEW = "mod004-fullscope-contained-adr-remed3-opus-review-20261025"


def d16_successor_shape_problem(t, fixed_id=None):
    """None only for the exact fixed-id, owner-CLI, ADR-only MOD-004 implement root with no lineage, phase or binding field."""
    if not (t.get("id") == (fixed_id or D16_SUCCESSOR_ID) and t.get("module") == "MOD-004" and t.get("role") == "implement"):
        return "only the fixed MOD-004 implement successor id"
    if t.get("source") is not None:
        return "the successor is admitted only from the owner CLI"
    if any(t.get(k) is not None for k in ("plan_phase", "remediation_of", "review_retry_of", "accounting_recovery_of", "review_of",
                                          "review_candidate", "doc_base")):
        return "plan_phase, remediation, retry, accounting-recovery, review and doc_base fields are rejected"
    if t.get("allowed_paths") != [D16_ADR_PATH] or t.get("expected_changes") != [D16_ADR_PATH]:
        return "allowed_paths and expected_changes must be exactly the ADR-0002 design file"
    if any(f(t) for f in (s0_marked, s0_test_marked, s0_touches, s0_doc_marked, s0_refresh_marked, s0_rebind_marked,
                          s0_loop_marked, s0_doc_touches, s0_qa_marked)):
        return "S0 task"
    return None


def d16_successor_lineage(tasks, t):
    """True when t is the fixed successor id or its remediation ancestry (walked iteratively by name and recorded id) reaches it.
    Fails closed: an ancestry too deep to walk counts as reaching it; a missing parent or a cycle that never meets the fixed id does
    not (the existing lineage validation refuses those)."""
    roots = (D16_SUCCESSOR_ID, D16_ARCH_ID)  # the original successor and the separately pinned architecture root
    seen, cur = set(), t
    for _ in range(66):
        if not isinstance(cur, dict):
            return False
        if cur.get("id") in roots:
            return True
        parent = cur.get("remediation_of")
        if not parent:
            return False
        if parent in roots:
            return True
        if parent in seen:
            return False
        seen.add(parent)
        cur = tasks.get(parent)
    return True


def _d16_exhausted_chain(tasks, root=None, terminal_id=None, terminal_review=None):
    """The exact exhausted historical root chain (root-first) rebuilt from immutable state, or GateError. Defaults to the
    original D16 root; the architecture exception passes the exhausted successor chain and its pinned terminal review explicitly."""
    root, terminal_id = root or D16_OLD_ROOT, terminal_id or D16_OLD_TERMINAL
    terminal_review = terminal_review or D16_OLD_TERMINAL_REVIEW
    terminal = tasks.get(terminal_id)
    if not (isinstance(terminal, dict) and product_policy_root(tasks, terminal)):
        raise GateError("D16: the historical root is not a recorded, policy-stamped chain")
    try:
        chain = product_chain(tasks, terminal)
    except ValueError as e:
        raise GateError(f"D16: {e}")
    if not (len(chain) == MAX_PRODUCT_CORRECTIONS + 1 and chain[0]["id"] == root and chain[-1]["id"] == terminal_id):
        raise GateError("D16: the historical root is not the exact exhausted chain of the root and its three corrections")
    ids, fps = {w["id"] for w in chain}, []
    for i, w in enumerate(chain):
        changed = _changed_pairs((w.get("evidence") or {}).get("changed"))
        if not (w.get("module") == "MOD-004" and w.get("role") == "implement" and w.get("status") == "DONE"
                and (w.get("remediation_root"), w.get("remediation_cycle")) == (root, i)
                and w.get("allowed_paths") and all(p in NONCAP_DESIGN_PATHS for p in w["allowed_paths"])
                and changed and all(c["path"] in NONCAP_DESIGN_PATHS and isinstance(c["sha256"], str)
                                    and SHA256_RE.fullmatch(c["sha256"]) for c in changed)):
            raise GateError(f"D16: {w['id']} is not a DONE, counter-stamped, design-scoped write with changed-file evidence")
        bound = [r for r in tasks.values() if isinstance(r, dict) and isinstance(r.get("review_of"), dict)
                 and r["review_of"].get("task_id") == w["id"]]
        rej = product_rejection(tasks, w)
        if not (len(bound) == 1 and bound[0].get("role") == "code-review" and rej and rej[0] == "CHANGES_REQUESTED" and rej[1]):
            raise GateError(f"D16: {w['id']} needs exactly one bound, verified Opus CHANGES_REQUESTED review and no other review task")
        if w["id"] == terminal_id and bound[0].get("id") != terminal_review:
            raise GateError("D16: the terminal rejection is not the pinned terminal review")
        kids = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("remediation_of") == w["id"])
        if kids != ([chain[i + 1]["id"]] if i + 1 < len(chain) else []):
            raise GateError(f"D16: {w['id']} has a branch or an extra correction")
        fps.append(rej[1])
    if len(set(fps)) != len(fps):
        raise GateError("D16: the historical rejections are not four distinct recorded findings")
    if any(isinstance(x, dict) and x.get("remediation_root") == root and x.get("id") not in ids for x in tasks.values()):
        raise GateError("D16: a foreign task claims the historical root")
    return chain


def _d16_adr_problem(cfg, t, chain):
    """The design file must not be a rejected candidate and, before the successor's first attempt, must be the clean published ADR."""
    rejected = {c["sha256"] for w in chain for c in _changed_pairs((w.get("evidence") or {}).get("changed"))
                if c["path"] == D16_ADR_PATH}
    try:
        current = _path_hash(Path(cfg.repo) / D16_ADR_PATH)
        if current is None or current in rejected:
            raise GateError("D16: the design file is missing or is a rejected historical candidate (stale)")
        if not t.get("attempts"):
            _s0_qa_git_clean(cfg, [D16_ADR_PATH], "D16 design file")
            if _s0_git_blob_sha(cfg, "HEAD", D16_ADR_PATH, "D16 design file") != current:
                raise GateError("D16: the design file is not the published ADR at HEAD (stale)")
    except OSError as e:
        raise GateError(f"D16: cannot read the design file ({type(e).__name__})")


def verify_d16_successor(cfg, tasks, t):
    """Read-only. Returns the frozenset of historical root ids the successor sets aside, or raises GateError. Single-use: any
    recorded task with the fixed id other than t (any status) consumed the entitlement."""
    problem = d16_successor_shape_problem(t)
    if problem:
        raise GateError(problem)
    recorded = tasks.get(D16_SUCCESSOR_ID)
    if (recorded is not None and recorded is not t) or any(
            isinstance(x, dict) and x.get("id") == D16_SUCCESSOR_ID and x is not t for x in tasks.values()):
        raise GateError("the single-use successor entitlement is already consumed")
    chain = _d16_exhausted_chain(tasks)
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{D16_RECEIPT}.json", RECEIPT_MAX_BYTES), "D16 receipt")
    sub = r.get("subjects")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "subjects"} and r["schema"] == SCHEMA
            and r["module"] == "MOD-004" and r["kind"] == "mod004-d16-successor-authority"
            and isinstance(r["operator"], str) and r["operator"].strip() and isinstance(sub, dict) and set(sub) == {"d16_owner"}):
        raise GateError("D16 receipt schema mismatch")
    o = sub["d16_owner"]
    if not (isinstance(o, dict) and o.get("path") == D16_OWNER_PATH and o.get("sha256") == D16_OWNER_SHA
            and o.get("commit") == D16_OWNER_COMMIT and (o.get("ci") or {}).get("run_id") == D16_OWNER_CI_RUN
            and (o.get("review") or {}).get("task_id") == D16_OWNER_REVIEW):
        raise GateError("D16: the owner record is not the pinned file, commit, CI run and review")
    _s0_subject(cfg, "d16_owner", o, tasks, set(), {"d16_owner": re.compile(re.escape(D16_OWNER_PATH))})
    approvals = [x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("role") in OPUS_ROLES
                 and (x.get("evidence") or {}).get("review_outcome") == "APPROVED" and _s0_binds_subject(x, D16_OWNER_PATH, D16_OWNER_SHA)]
    if approvals != [D16_OWNER_REVIEW]:
        raise GateError("D16: the owner record needs exactly one APPROVED exact-subject Opus review")
    _d16_adr_problem(cfg, t, chain)
    return frozenset(w["id"] for w in chain)


def d16_successor_probe(cfg):
    """Read-only gate probe (reads state.json and the repo; queues, locks and writes nothing, consumes no entitlement).
    Returns {case: refusal-or-None}; a healthy, unconsumed gate admits only 'successor' and refuses every other case."""
    state = json.loads(_read_bounded(cfg.home / "state.json", 64 * 1024 * 1024))
    adr, cap = [D16_ADR_PATH], list(ACCOUNTING_RECOVERY_PATHS)
    base = {"module": "MOD-004", "role": "implement", "prompt": "read-only probe", "allowed_paths": adr, "expected_changes": adr}
    cases = {"successor": {"id": D16_SUCCESSOR_ID},
             "other_id": {"id": "d16-probe-other-id"},
             "cap": {"id": D16_SUCCESSOR_ID, "allowed_paths": cap, "expected_changes": cap},
             "old_root_fourth": {"id": "d16-probe-fourth", "remediation_of": D16_OLD_TERMINAL}}
    out = {}
    for name, extra in cases.items():
        try:
            out[name] = gate_reason(cfg, validate_task(base | extra, cfg), state["tasks"])
        except Exception as e:
            out[name] = f"D16_PROBE_UNVERIFIABLE: {type(e).__name__}"
    return out


# ------------------------------------------------ MOD-004 D16 architecture root (second, separately pinned single-use admission)
# OWNER-2026-10-25-mod004-d16-architecture-reassessment.md: ONE more owner-CLI, non-CAP, ADR-only design root with its own fixed id
# may start although BOTH the exhausted original D16 chain and the exhausted successor chain are rejected tips. It is not a
# correction of either, never changes the consumed D16_SUCCESSOR_ID entitlement, sets aside only those two verified chains for this
# one root, and its own corrections stay under the ordinary per-root three-cycle policy. Read-only and fail-closed.
D16_ARCH_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-25-mod004-d16-architecture-reassessment.md"
D16_ARCH_OWNER_SHA = "c2b5c7016b65d6f1e1073dfb5e940f505193dad40c785aef5e5e9bd590933a42"
D16_ARCH_OWNER_COMMIT = "7c07abab5e9e361e711d6d48e47fc91f7bf5c9a3"
D16_ARCH_OWNER_CI_RUN = "40196359396"
D16_ARCH_OWNER_REVIEW = "mod004-d16-architecture-owner-opus-r3-20261025"
D16_ARCH_RECEIPT = "MOD-004-D16-ARCHITECTURE"  # operator-written <home>/acceptances/MOD-004-D16-ARCHITECTURE.json: one d16_arch_owner subject
D16_ARCH_ID = "mod004-d16-assurance-architecture-sonnet-20261025"
D16_SUCC_TERMINAL = "mod004-d16-db-command-successor-remed3-sonnet-20261025"
D16_SUCC_TERMINAL_REVIEW = "mod004-d16-db-command-successor-remed3-opus-review-20261025"

# One owner-approved fourth correction of the SAME D16 architecture root. This is not a general limit increase.
D16_F34_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-25-mod004-d16-f34-final-correction.md"
D16_F34_OWNER_SHA = "f71ccb59b89cf376a7c0dbc8f126b897f44444292b9cf931060ab2ea76285e73"
D16_F34_OWNER_COMMIT = "2f69abe36b30de2930d252f139863b9117ee4bcb"
D16_F34_OWNER_CI_RUN = "40202958073"
D16_F34_OWNER_REVIEW = "mod004-d16-f34-final-owner-opus-r3-20261025"
D16_F34_RECEIPT = "MOD-004-D16-F34-FINAL"
D16_F34_WRITE = "mod004-d16-assurance-architecture-remed4-sonnet-20261025"
D16_F34_REVIEW = "mod004-d16-assurance-architecture-remed4-opus-review-20261025"
D16_F34_ROOT = D16_ARCH_ID
D16_F34_TIP = "mod004-d16-assurance-architecture-remed3-sonnet-20261025"
D16_F34_START_SHA = "e286d581dd74da74309e03859fb04105cb5de522b1a01aa2fe5c2f411fcfeb80"
D16_F34_RESULT_SHA = "f5338001b4e2eb5a5122419d381171447ed3de34ceebd2be226d4ecb1accca82"
D16_F34_HISTORY = (
    (D16_F34_ROOT, "8996ee6f36747c2cd7a126fdbfe8f9947aebdca99bff36e276a1b40891ec0f48", "mod004-d16-assurance-architecture-opus-review-20261025"),
    ("mod004-d16-assurance-architecture-remed1-sonnet-20261025", "f109b1c435e2f8f2f7eeff2b1504f373489d59a72de3fa52275b936d5465f245", "mod004-d16-assurance-architecture-remed1-opus-review-20261025"),
    ("mod004-d16-assurance-architecture-remed2-sonnet-20261025", "e8b73d0836c3f29894ccbe02c4d97252d023d6eac84977ceb9a6c6f0d621de23", "mod004-d16-assurance-architecture-remed2-opus-review-20261025"),
    (D16_F34_TIP, D16_F34_START_SHA, "mod004-d16-assurance-architecture-remed3-opus-review-20261025"),
)

# ------------------------------------------------ S0/D16 quarantine ledger (2026-10-26 controlled-reload sequencing)
# OWNER-2026-10-26-mod004-d16-admission-s0-quarantined-reload.md: one default-deny quarantined reload,
# one fixed-ID S0 document rebind lane, one fixed-ID D16 ADR-only admission root (≤2 corrections).
S0_D16_QLED_NAME = "s0_d16_quarantine.json"
S0_DUAL_REBIND_MARKER = "MOD004-S0-D16-EVIDENCE-REBIND"
S0_DUAL_REBIND_ID = "mod004-s0-d16-evidence-rebind-sonnet-20261026"
S0_DUAL_REBIND_RECEIPT = "MOD-004-S0-D16-REBIND"
D16_DUAL_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-26-mod004-d16-admission-s0-quarantined-reload.md"
D16_DUAL_OWNER_SHA = "a36e27640d214a128179e60ffe4c91769864f7736874ba85e66bf9ad02efde48"
D16_DUAL_OWNER_CI_RUN = 40271026654
D16_DUAL_OWNER_REVIEW = "owner-decision-prep/20261026-d16-dual-version/quarantine-owner-opus-r2-response.txt"
D16_DUAL_OWNER_REVIEW_SHA = "c8154039d10746f31b5237e8b8ff41a13a7fda15572f77ed4bf820135076f216"
D16_DUAL_DESIGN_PATH = "knowledge/00-Decisions/OWNER-2026-10-26-mod004-d16-dual-version-design.md"
D16_DUAL_DESIGN_SHA = "35c2695657535033334904a69d9438ddd15cffb181c627b0257ecb2bc0042f78"
D16_DUAL_DESIGN_COMMIT = "4e7074a8f39dfc9f7fcc1e977242e369266fd6de"
D16_DUAL_DESIGN_CI_RUN = 40241251887
D16_DUAL_DESIGN_REVIEW = "owner-decision-prep/20261026-d16-dual-version/owner-record-opus-r2-response.txt"
D16_DUAL_DESIGN_REVIEW_SHA = "b7a922fe5ae38f784ab7fbcf2fa943082c41d60f5b295d619724655f7bce2719"
D16_DUAL_ID = "mod004-d16-dual-version-sonnet-20261026"
D16_DUAL_RECEIPT = "MOD-004-D16-DUAL"
D16_DUAL_MAX_CORRECTIONS = 2
D16_BOOT_ACTIVATION_NAME = "s0_d16_boot_activation.json"
# D16_BOOT_COMMIT is the published owner-record HEAD and the root of the pinned runner-amendment lineage.
# The activation commit is a DIRECT CHILD of D16_BOOT_PRIOR_TIP and must satisfy:
#   D16_BOOT_COMMIT -> D16_BOOT_FIRST_AMENDMENT -> D16_BOOT_PRIOR_TIP -> activation commit
# (each link the sole parent of the next). The activation commit's runner.py blob hash equals CODE_SHA and its
# CI was observed green on that exact commit; the prior tip's runner blob and CI are verified too. The first
# amendment's own CI failed (fixed by the prior tip), so none is required for it.
D16_BOOT_COMMIT = "c11d4208f36e00c0f47cf1a7b86164d10a9b625c"
D16_BOOT_FIRST_AMENDMENT = "39887257f780df5dda57402238af2ce6a85134ae"
D16_BOOT_PRIOR_TIP = "3a7acabb00ff043eb00cf0b76e60a3ee17925d21"
D16_BOOT_PRIOR_RUNNER_SHA = "6d8ff2ca1f9898a4f1234ea9805d2a74468c4b25e79f4cce05e18c95d6a54394"
# The verified successful Foundation push run for the prior tip. The first amendment's run (40305049317) FAILED
# and is never a green observation.
D16_BOOT_PRIOR_CI_RUN = "40312084619"
_RAW_COMMIT_FIELDS = (b"tree", b"parent", b"author", b"committer", b"encoding", b"gpgsig", b"gpgsig-sha256")


def _raw_commit_parents(sha, body):
    """Parents from a raw commit object body, or None when it fails integrity or shape checks.

    The body must hash to its own 40-hex SHA-1 object id (local object storage is mutable), and the header
    (before the first blank line) may hold only known fields, with `tree` first. Unlike rev-list this reads
    no graft, replace or commit-graph metadata."""
    if not (isinstance(sha, str) and SHA_RE.fullmatch(sha) and isinstance(body, bytes)):
        return None
    if hashlib.sha1(b"commit " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest() != sha:
        return None
    header, sep, _msg = body.partition(b"\n\n")
    if not sep:
        return None
    parents, in_sig = [], False
    for i, line in enumerate(header.split(b"\n")):
        if line.startswith(b" "):
            if not in_sig:
                return None
            continue
        key, _, val = line.partition(b" ")
        if key not in _RAW_COMMIT_FIELDS or (i == 0) != (key == b"tree"):
            return None
        in_sig = key in (b"gpgsig", b"gpgsig-sha256")
        if key == b"parent":
            if not SHA_RE.fullmatch(val.decode("ascii", "replace")):
                return None
            parents.append(val.decode("ascii"))
    return parents
S0_DUAL_REBIND_SUBJECTS = {
    "dual_rebind_runner": re.compile(re.escape(S0_RUNNER_FILE)),
    "dual_rebind_owner": re.compile(re.escape(D16_DUAL_OWNER_PATH)),
    "s0_cert": re.compile(re.escape(S0_DOC_PATHS[0])),
    "s0_qa": re.compile(re.escape(S0_DOC_PATHS[1])),
}


def verify_d16_f34_authority(cfg, tasks, t):
    """Fail-closed read-only authorization for exactly one original-root cycle-four F34 correction."""
    if not (t.get("id") == D16_F34_WRITE and t.get("module") == "MOD-004" and t.get("role") == "implement"
            and t.get("source") is None and t.get("plan_phase") is None
            and t.get("remediation_of") == D16_F34_TIP
            and t.get("allowed_paths") == [D16_ADR_PATH] and t.get("expected_changes") == [D16_ADR_PATH]
            and t.get("verify_cmd") == []
            and all(t.get(k) is None for k in ("review_of", "review_retry_of", "accounting_recovery_of", "doc_base"))):
        raise GateError("F34 task shape is not the fixed owner-CLI, ADR-only, cycle-four correction")
    recorded = tasks.get(D16_F34_WRITE)
    if recorded is not None and recorded is not t:
        raise GateError("F34 single-use task id was already consumed")
    prior = {k: v for k, v in tasks.items() if v is not t}
    chain = _d16_exhausted_chain(prior, D16_F34_ROOT, D16_F34_TIP, D16_F34_HISTORY[-1][2])
    for w, (wid, sha, rid) in zip(chain, D16_F34_HISTORY):
        if w["id"] != wid or (w.get("evidence") or {}).get("changed") != [{"path": D16_ADR_PATH, "sha256": sha}]:
            raise GateError("F34 historical write ids or exact changed bytes disagree with the preserved lineage")
        reviews = [r for r in prior.values() if isinstance(r, dict) and (r.get("review_of") or {}).get("task_id") == wid]
        if len(reviews) != 1 or reviews[0].get("id") != rid:
            raise GateError("F34 historical review ids disagree with the preserved lineage")
    if (t.get("remediation_root"), t.get("remediation_cycle")) not in ((None, None), (D16_F34_ROOT, 4)):
        raise GateError("F34 persisted root/cycle disagrees with the single fourth correction")
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{D16_F34_RECEIPT}.json", RECEIPT_MAX_BYTES), "D16 F34 receipt")
    sub = r.get("subjects")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "subjects"}
            and r["schema"] == SCHEMA and r["module"] == "MOD-004" and r["kind"] == "mod004-d16-f34-final-authority"
            and isinstance(r["operator"], str) and r["operator"].strip()
            and isinstance(sub, dict) and set(sub) == {"d16_f34_owner"}):
        raise GateError("D16 F34 receipt schema mismatch")
    o = sub["d16_f34_owner"]
    if not (isinstance(o, dict) and o.get("path") == D16_F34_OWNER_PATH and o.get("sha256") == D16_F34_OWNER_SHA
            and o.get("commit") == D16_F34_OWNER_COMMIT and (o.get("ci") or {}).get("run_id") == D16_F34_OWNER_CI_RUN
            and (o.get("review") or {}).get("task_id") == D16_F34_OWNER_REVIEW):
        raise GateError("D16 F34 owner record is not the pinned file, commit, CI run and exact review")
    _s0_subject(cfg, "d16_f34_owner", o, tasks, set(), {"d16_f34_owner": re.compile(re.escape(D16_F34_OWNER_PATH))})
    approvals = [x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("role") in OPUS_ROLES
                 and (x.get("evidence") or {}).get("review_outcome") == "APPROVED"
                 and _s0_binds_subject(x, D16_F34_OWNER_PATH, D16_F34_OWNER_SHA)]
    if approvals != [D16_F34_OWNER_REVIEW]:
        raise GateError("D16 F34 owner record needs its single pinned APPROVED exact-subject Opus review")
    if _path_hash(Path(cfg.repo) / D16_ADR_PATH) != D16_F34_START_SHA:
        raise GateError("D16 F34 starting ADR is not the exact preserved rejected candidate")
    return True


def d16_f34_review_reason(t, tasks):
    """The one final candidate has exactly one named, bound review slot; other reviews remain unaffected."""
    b = t.get("review_of") or {}
    if t.get("id") != D16_F34_REVIEW and b.get("task_id") != D16_F34_WRITE:
        return None
    if t.get("id") != D16_F34_REVIEW or b.get("task_id") != D16_F34_WRITE or t.get("module") != "MOD-004":
        return "D16_F34_REVIEW_INVALID: only the fixed review id may review the final F34 write"
    w = tasks.get(D16_F34_WRITE)
    if not (isinstance(w, dict) and w.get("status") == "DONE" and w.get("remediation_root") == D16_F34_ROOT
            and w.get("remediation_cycle") == 4 and (w.get("evidence") or {}).get("changed") ==
            [{"path": D16_ADR_PATH, "sha256": D16_F34_RESULT_SHA}]):
        return "D16_F34_REVIEW_INVALID: corrected design is not the exact DONE cycle-four candidate"
    if b.get("changed") != [{"path": D16_ADR_PATH, "sha256": D16_F34_RESULT_SHA}]:
        return "D16_F34_REVIEW_INVALID: review binding is not the exact final ADR hash"
    return None


def d16_f34_result_problem(repo, changed):
    """The single final write must leave precisely the owner-approved complete ADR bytes."""
    if changed != [D16_ADR_PATH]:
        return "final F34 write changed a path other than the sole ADR, or did not change the ADR"
    try:
        actual = _path_hash(Path(repo) / D16_ADR_PATH)
    except OSError:
        return "final F34 ADR could not be hashed"
    return None if actual == D16_F34_RESULT_SHA else "final F34 ADR hash differs from the owner-approved result"


def verify_d16_architecture(cfg, tasks, t):
    """Read-only. Returns the frozenset of the eight historical write ids (both exhausted chains) the architecture root sets
    aside, or raises GateError. Single-use: any recorded task with the fixed id other than t (any status) consumed it."""
    problem = d16_successor_shape_problem(t, D16_ARCH_ID)
    if problem:
        raise GateError(problem)
    recorded = tasks.get(D16_ARCH_ID)
    if (recorded is not None and recorded is not t) or any(
            isinstance(x, dict) and x.get("id") == D16_ARCH_ID and x is not t for x in tasks.values()):
        raise GateError("the single-use architecture entitlement is already consumed")
    # the old successor entitlement stays consumed: its root must be the recorded, exhausted root of the second chain
    old = _d16_exhausted_chain(tasks)
    succ = _d16_exhausted_chain(tasks, D16_SUCCESSOR_ID, D16_SUCC_TERMINAL, D16_SUCC_TERMINAL_REVIEW)
    chain = old + succ
    ids = [w["id"] for w in chain]
    fps = [product_rejection(tasks, w)[1] for w in chain]
    if len(set(ids)) != len(chain) or len(set(fps)) != len(chain):
        raise GateError("D16: the eight historical rejections are not eight distinct writes with distinct recorded findings")
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{D16_ARCH_RECEIPT}.json", RECEIPT_MAX_BYTES), "D16 architecture receipt")
    sub = r.get("subjects")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "subjects"} and r["schema"] == SCHEMA
            and r["module"] == "MOD-004" and r["kind"] == "mod004-d16-architecture-authority"
            and isinstance(r["operator"], str) and r["operator"].strip() and isinstance(sub, dict) and set(sub) == {"d16_arch_owner"}):
        raise GateError("D16 architecture receipt schema mismatch")
    o = sub["d16_arch_owner"]
    if not (isinstance(o, dict) and o.get("path") == D16_ARCH_OWNER_PATH and o.get("sha256") == D16_ARCH_OWNER_SHA
            and o.get("commit") == D16_ARCH_OWNER_COMMIT and (o.get("ci") or {}).get("run_id") == D16_ARCH_OWNER_CI_RUN
            and (o.get("review") or {}).get("task_id") == D16_ARCH_OWNER_REVIEW):
        raise GateError("D16: the architecture owner record is not the pinned file, commit, CI run and review")
    _s0_subject(cfg, "d16_arch_owner", o, tasks, set(), {"d16_arch_owner": re.compile(re.escape(D16_ARCH_OWNER_PATH))})
    approvals = [x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("role") in OPUS_ROLES
                 and (x.get("evidence") or {}).get("review_outcome") == "APPROVED"
                 and _s0_binds_subject(x, D16_ARCH_OWNER_PATH, D16_ARCH_OWNER_SHA)]
    if approvals != [D16_ARCH_OWNER_REVIEW]:
        raise GateError("D16: the architecture owner record needs exactly one APPROVED exact-subject Opus review")
    _d16_adr_problem(cfg, t, chain)  # the ADR must be neither any of the eight rejected candidates nor stale
    return frozenset(ids)


# ------------------------------------------------ MOD-004 S0 evidence-only QA lane
# OWNER-2026-10-24-mod004-fullscope-recovery.md "S0 evidence-only route": ONE owner-CLI runner-recorded Sonnet write of the
# scenario/QA packet (the eligibility certificate only to rebind its packet hash), ONE bound Opus review of the exact
# resulting changed-file set, no retry, correction or second write. It has its own marker: the consumed S0 product,
# document, refresh, rebind and loop lanes stay closed and are never reused. The packet may change only in the evidence
# and disposition cells of its 14 table rows, its status paragraph and one appended evidence section; every scenario ID,
# category, stimulus, boundary and the PASS rule stay byte-identical. A row claiming PASS must carry the structural
# evidence the PASS rule names (the reviewer judges whether it is true). No product code, CAP file or history changes.
S0_QA_MARKER = "MOD004-S0-QA-EVIDENCE"
S0_QA_CERT, S0_QA_PACKET = S0_DOC_PATHS
S0_QA_RECEIPT = "MOD-004-S0-QA"  # operator-written <home>/acceptances/MOD-004-S0-QA.json: qa_owner (the pinned owner record), runner_gate
S0_QA_SUBJECTS = {"qa_owner": re.compile(re.escape(NONCAP_OWNER_PATH)), "runner_gate": S0_SUBJECTS["runner_gate"]}
S0_QA_SCOPES = (sorted([S0_QA_PACKET]), sorted(S0_DOC_PATHS))  # packet only, or packet plus the certificate that binds its hash
S0_QA_PROTECTED = tuple(S0_PATHS) + tuple(ACCOUNTING_RECOVERY_PATHS)  # published S0 product and the CAP files: never changed here
S0_QA_IDS = tuple(f"S0-{i:02d}" for i in range(1, 15))
S0_QA_HEADING = "\n## QA execution evidence\n"
S0_QA_STATUS = "**Review and recovery status:**"


def s0_qa_marked(t):
    return t.get("plan_phase") == S0_QA_MARKER


def s0_qa_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the S0 evidence-only QA write is a MOD-004 implement task only"
    if t.get("source") is not None:
        return "the S0 evidence-only QA write is admitted only from the owner CLI"
    if any(t.get(k) is not None for k in ("remediation_of", "review_retry_of", "accounting_recovery_of", "review_of",
                                          "review_candidate")):
        return "remediation_of, review_retry_of, accounting_recovery_of and review binding fields are rejected"
    allowed, expected = t.get("allowed_paths"), t.get("expected_changes")
    if not (isinstance(allowed, list) and isinstance(expected, list) and sorted(allowed) in S0_QA_SCOPES
            and sorted(expected) == sorted(allowed)):
        return "allowed_paths and expected_changes must be exactly the scenario/QA packet, optionally with the eligibility certificate"
    if t.get("verify_cmd") != []:
        return "the S0 evidence-only QA write runs no verifier"
    base = t.get("doc_base")
    if not (isinstance(base, dict) and set(base) == set(allowed)
            and all(isinstance(v, str) and SHA256_RE.fullmatch(v) for v in base.values())):
        return "doc_base must pin the exact starting sha256 of the packet (and of the certificate when it is named)"
    return None


def _s0_qa_git_clean(cfg, paths, label):
    try:
        status = git_run(cfg.repo, "status", "--porcelain=v1", "--untracked-files=all", "--", *paths, timeout=20)
        flags = git_run(cfg.repo, "ls-files", "-v", "--", *paths, timeout=20)
    except (OSError, subprocess.SubprocessError):
        raise GateError(f"{label}: cannot check the working-tree state")
    tracked = [ln[:2] for ln in flags.stdout.decode("utf-8", "replace").splitlines()]
    if not (status.returncode == 0 and status.stdout == b"" and flags.returncode == 0 and tracked == ["H "] * len(paths)):
        raise GateError(f"{label}: the files must be clean, tracked and committed")


def _s0_qa_split(data, label):
    """(skeleton, rows, evidence tail or None) of a packet. The skeleton is the packet with each table row's evidence and
    disposition cells and the status paragraph blanked and the appended evidence section cut off, so two packets with
    equal skeletons agree on every ID, category, stimulus, boundary and the PASS rule."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise GateError(f"{label}: not UTF-8")
    head, sep, tail = text.partition(S0_QA_HEADING)
    if S0_QA_HEADING in tail:
        raise GateError(f"{label}: more than one QA execution evidence section")
    out, rows, status = [], {}, 0
    for para in head.split("\n\n"):
        if para.startswith(S0_QA_STATUS):
            status, para = status + 1, "<status>"
        lines = []
        for ln in para.split("\n"):
            if re.match(r"\| S0-\d\d \| ", ln):
                cells = ln[2:-2].split(" | ") if ln.endswith(" |") else []
                if len(cells) != 5 or cells[0] in rows:
                    raise GateError(f"{label}: a scenario row must have exactly five cells and a unique ID")
                rows[cells[0]] = cells
                ln = "| " + " | ".join(cells[:3]) + " | <evidence> |"
            lines.append(ln)
        out.append("\n".join(lines))
    if status != 1 or tuple(rows) != S0_QA_IDS:
        raise GateError(f"{label}: needs exactly one status paragraph and the fourteen rows S0-01..S0-14 in order")
    return "\n\n".join(out).rstrip("\n"), rows, tail if sep else None


def _s0_qa_missing(cfg, text):
    """The structural PASS-rule evidence absent from a row's evidence/disposition text (a presence check, not a judgement)."""
    miss = []
    if not re.search(r"\btests\.test_tenancy_s0\.\w+\.test\w*", text):
        miss.append("exact unittest test IDs")
    if not any(_is_ancestor(cfg, c) for c in re.findall(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", text)):
        miss.append("a published product commit")
    if not re.search(r"(?i)\bverifier\b", text):
        miss.append("the runner verifier result")
    if not (re.search(r"\bCI\b", text) and re.search(r"(?<![0-9A-Za-z])[0-9]{8,}(?![0-9A-Za-z])", text)):
        miss.append("the exact-SHA CI run")
    if not (re.search(r"\bAPPROVED\b", text) and any("review" in w for w in re.findall(r"[a-z0-9][a-z0-9._-]{7,}", text))):
        miss.append("the bound APPROVED product review task")
    if not re.search(r"(?i)\bmanual\b", text):
        miss.append("manual-step evidence")
    return miss


def _s0_qa_packet_problem(cfg, base, cur):
    try:
        bskel, _, btail = _s0_qa_split(base, "S0 QA starting packet")
        cskel, rows, ctail = _s0_qa_split(cur, "S0 QA packet")
    except GateError as e:
        return str(e)
    if btail is not None:
        return "the starting packet already carries an evidence section"
    if bskel != cskel:
        return ("the packet differs from its pinned start beyond the evidence/disposition cells, the status paragraph and one "
                "appended evidence section (scenario IDs, categories, stimuli, boundaries and the PASS rule must not change)")
    if ctail is not None and re.search(r"(?m)^\| S0-", ctail):
        return "the appended evidence section must not hold scenario rows"
    for sid, cells in rows.items():
        verdicts = [" ".join(v.upper().split()) for v in
                    re.findall(r"(?i)(?<![A-Za-z])(?:NOT[ \t]+)?PASS(?![A-Za-z])", cells[4])]
        if len(verdicts) > 1:
            return f"{sid} disposition holds more than one PASS/NOT PASS token; it must be one unambiguous disposition"
        if verdicts == ["PASS"]:
            miss = _s0_qa_missing(cfg, " ".join(cells[3:]))
            if miss:
                return f"{sid} claims PASS without {', '.join(miss)}"
    return None


def _s0_qa_cert_problem(base, cur, packet):
    try:
        want, got = _s0_json(base, "S0 QA starting certificate"), _s0_json(cur, "S0 QA certificate")
    except GateError as e:
        return str(e)
    bp, gp = want.get("scenario_qa_packet"), got.get("scenario_qa_packet")
    if not (isinstance(bp, dict) and isinstance(gp, dict) and gp.get("sha256") == hashlib.sha256(packet).hexdigest()
            and isinstance(gp.get("sha256_note"), str) and gp["sha256_note"].strip()):
        return "the certificate must bind the new packet sha256 with a nonempty sha256_note"
    bp["sha256"], bp["sha256_note"] = gp["sha256"], gp["sha256_note"]
    if want != got:
        return "the certificate differs from its pinned start beyond scenario_qa_packet.sha256/sha256_note"
    return None


def _s0_qa_result_problem(cfg, w):
    """None only while the S0 product, CAP files and any unnamed document are untouched and committed, HEAD still holds the
    pinned doc_base, and the current documents keep the packet structure (and, if named, the certificate binding)."""
    base, repo = w["doc_base"], Path(cfg.repo)
    try:
        _s0_qa_git_clean(cfg, [*S0_QA_PROTECTED, *(p for p in S0_DOC_PATHS if p not in w["allowed_paths"])], "S0 QA protected files")
        blobs = {p: _s0_git_blob(cfg, "HEAD", p, "S0 QA start") for p in w["allowed_paths"]}
        if any(hashlib.sha256(b).hexdigest() != base[p] for p, b in blobs.items()):
            return "the documents at HEAD are not the pinned doc_base"
        cur = {p: _read_bounded(repo / p, REVIEW_MAX_BYTES) for p in w["allowed_paths"]}
    except (GateError, OSError) as e:
        return f"cannot verify the S0 QA documents: {str(e)[:120]}"
    return (_s0_qa_packet_problem(cfg, blobs[S0_QA_PACKET], cur[S0_QA_PACKET])
            or (_s0_qa_cert_problem(blobs[S0_QA_CERT], cur[S0_QA_CERT], cur[S0_QA_PACKET]) if S0_QA_CERT in cur else None))


def verify_s0_qa_authority(cfg, tasks):
    """Offline re-verification (read-only): the pinned owner record is committed, CI-green and independently Opus-APPROVED,
    and the runner file the receipt names is this loaded, reviewed, CI-green runner. A mechanical runner_gate rebind after a
    reload changes only that one subject; the owner subject stays pinned to the constants above. Grants nothing else."""
    r = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{S0_QA_RECEIPT}.json", RECEIPT_MAX_BYTES), "S0 QA receipt")
    sub = r.get("subjects")
    if not (set(r) == {"schema", "module", "kind", "operator", "recorded_at", "subjects"} and r["schema"] == SCHEMA
            and r["module"] == S0_MODULE and r["kind"] == "mod004-s0-qa-authority"
            and isinstance(r["operator"], str) and r["operator"].strip() and isinstance(r["recorded_at"], str)
            and isinstance(sub, dict) and set(sub) == set(S0_QA_SUBJECTS)):
        raise GateError("S0 QA receipt schema mismatch")
    o = sub["qa_owner"]
    if not (isinstance(o, dict) and o.get("path") == NONCAP_OWNER_PATH and o.get("sha256") == NONCAP_OWNER_SHA
            and o.get("commit") == NONCAP_OWNER_COMMIT and (o.get("ci") or {}).get("run_id") == NONCAP_OWNER_CI_RUN):
        raise GateError("S0 QA: the owner record is not the pinned file, commit and CI run")
    seen = set()
    data = {name: _s0_subject(cfg, name, sub[name], tasks, seen, S0_QA_SUBJECTS) for name in S0_QA_SUBJECTS}
    if hashlib.sha256(data["runner_gate"]).hexdigest() != CODE_SHA:
        raise GateError("S0 QA runner_gate: the loaded runner is not the reviewed, CI-green runner file")


def s0_qa_gate_reason(cfg, t, tasks):
    """None for a task outside the lane or the one fully authorised evidence-only write; else an explicit S0_QA_* reason."""
    if not s0_qa_marked(t):
        return None
    problem = s0_qa_shape_problem(t)
    if problem:
        return f"S0_QA_INVALID_TASK {t['id']}: {problem}"
    if t.get("attempts"):
        return f"S0_QA_ATTEMPT_USED {t['id']}: the single evidence-only write attempt was already started"
    others = sorted(x["id"] for x in tasks.values() if x.get("id") != t["id"] and s0_qa_marked(x) and x.get("role") in WRITE_ROLES)
    if others:
        return f"S0_QA_SECOND_WRITE: evidence-only write {others[0]} already exists; the lane is one-shot"
    busy = _s0_competing_writes(tasks, t)
    if busy:
        return f"S0_QA_CONCURRENT_WRITE: {busy[0]} is a pending write in an S0 chain or touching S0 files"
    try:
        _s0_qa_git_clean(cfg, [*S0_QA_PROTECTED, *S0_DOC_PATHS], "S0 QA start")
        for p, sha in t["doc_base"].items():
            if _path_hash(Path(cfg.repo) / p) != sha or _s0_git_blob_sha(cfg, "HEAD", p, "S0 QA start") != sha:
                return "S0_QA_STALE_BASE: a document is not the pinned published doc_base"
        problem = _s0_qa_packet_problem(cfg, _s0_git_blob(cfg, "HEAD", S0_QA_PACKET, "S0 QA start"),
                                        _s0_git_blob(cfg, "HEAD", S0_QA_PACKET, "S0 QA start"))
        if problem:
            return f"S0_QA_BASE_UNSOUND: {problem}"
        verify_s0_qa_authority(cfg, tasks)
    except GateError as e:
        return f"S0_QA_AUTHORITY_UNVERIFIED: {e}"
    except OSError as e:
        return f"S0_QA_AUTHORITY_UNVERIFIED: {type(e).__name__}"
    return None


def s0_qa_review_reason(cfg, t, tasks):
    """The one exact-bound owner-CLI Opus review of the sole DONE evidence-only write: any other review task bound to it, in
    any status, has used the slot; there is no retry, correction or review shopping."""
    w = tasks.get((t.get("review_of") or {}).get("task_id"))
    if not (w and s0_qa_marked(w)):
        return None
    if t.get("source") is not None:
        return "S0_QA_REVIEW_UNSUPPORTED: the evidence-only review is owner-CLI routed only"
    if t.get("review_retry_of") or t.get("review_candidate"):
        return "S0_QA_REVIEW_UNSUPPORTED: the evidence-only write gets one bound review and no retry"
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement" and w.get("status") == "DONE"
            and w.get("attempts") == 1 and (w.get("evidence") or {}).get("violations") == []):
        return "S0_QA_REVIEW_UNSUPPORTED: only a DONE one-attempt MOD-004 evidence-only write can be reviewed here"
    problem = s0_qa_shape_problem(w)
    if problem:
        return f"S0_QA_REVIEW_UNSUPPORTED: {problem}"
    if [x["id"] for x in tasks.values() if isinstance(x, dict) and s0_qa_marked(x) and x.get("role") in WRITE_ROLES] != [w["id"]]:
        return "S0_QA_REVIEW_UNSUPPORTED: the evidence-only write must be the only one in the lane"
    want = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if not (sorted(c["path"] for c in want) == sorted(w["allowed_paths"])
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) and c["sha256"] != w["doc_base"][c["path"]]
                    for c in want)
            and _changed_pairs((t.get("review_of") or {}).get("changed")) == want):
        return "S0_QA_REVIEW_UNSUPPORTED: review must bind the exact changed hashes of every named document, each different from its base"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_QA_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review evidence-only write {w['id']}"
    if not _hashes_current(cfg, (w.get("evidence") or {}).get("changed")):
        return "S0_QA_REVIEW_BINDING_STALE: the documents no longer match the write's recorded hashes"
    problem = _s0_qa_result_problem(cfg, w)
    if problem:
        return f"S0_QA_REVIEW_UNSUPPORTED: {problem}; the one review slot is not spent on an unsound candidate"
    try:
        verify_s0_qa_authority(cfg, tasks)
    except GateError as e:
        return f"S0_QA_REVIEW_AUTHORITY_UNVERIFIED: {e}"
    except OSError as e:
        return f"S0_QA_REVIEW_AUTHORITY_UNVERIFIED: {type(e).__name__}"
    return None


# ------------------------------------------------ quarantine ledger helpers (2026-10-26)

def _qled_path(cfg):
    return cfg.home / S0_D16_QLED_NAME


def _load_qled(cfg):
    """Load the S0/D16 quarantine ledger. Returns None when the file is absent; raises GateError on corrupt/truncated state."""
    try:
        data = _qled_path(cfg).read_bytes()
    except FileNotFoundError:
        return None
    return _parse_qled(data)


def _parse_qled(data):
    """Validate quarantine-ledger bytes; GateError on corrupt or malformed content."""
    try:
        d = json.loads(data.decode())
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise GateError("S0/D16 quarantine ledger is corrupt or not valid JSON")
    if not (isinstance(d, dict) and d.get("schema") == 1
            and isinstance(d.get("entered_at"), str) and isinstance(d.get("runner_pid"), int)
            and isinstance(d.get("runner_boot_nonce"), str) and bool(d.get("runner_boot_nonce"))
            and isinstance(d.get("code_sha256"), str) and SHA256_RE.fullmatch(d.get("code_sha256") or "")
            and isinstance(d.get("dual_rebind_consumed"), bool)):
        raise GateError("S0/D16 quarantine ledger schema is invalid or missing required fields")
    return d


def _write_qled(cfg, d):
    atomic_write(_qled_path(cfg), json.dumps(d, sort_keys=True).encode())


def _qled_runner_is_live(cfg, qled):
    """True when qled's recorded runner is still the running process.
    In runner dispatch context (same PID + matching boot nonce) this is immediate. In CLI context,
    authenticate via state.json: the runner must be alive, have a fresh heartbeat, matching PID and code
    hash. Fail-closed: any exception or missing state returns False. A ledger with no runner_boot_nonce
    or a mismatched nonce is rejected in the dispatch path; PID reuse by a new process cannot authenticate
    an old ledger whose nonce no longer matches."""
    if qled.get("runner_pid") == os.getpid():
        # Same-PID dispatch path: nonce must match so PID reuse does not re-authenticate old ledger
        return qled.get("runner_boot_nonce") == _PROCESS_BOOT_NONCE
    try:
        state = json.loads(_read_bounded(cfg.home / "state.json", 64 * 1024 * 1024))
    except Exception:
        return False
    runner = (state or {}).get("runner", {})
    return (s0_runner_problem(state) is None
            and runner.get("pid") == qled.get("runner_pid")
            and isinstance(qled.get("runner_boot_nonce"), str)
            and runner.get("boot_nonce") == qled.get("runner_boot_nonce"))


def _boot_activation_path(cfg):
    return cfg.home / D16_BOOT_ACTIVATION_NAME


# Quarantine state constants used by quarantine_state() and callers.
_QS_NONE = "NONE"            # no activation token and no ledger: pre-reload, normal operation
_QS_ENTERED_LIVE = "ENTERED_LIVE"  # ledger present, runner live, code hash matches
_QS_RESTARTED = "RESTARTED"  # ledger present but recorded runner is no longer live
_QS_DENY = "DENY"            # corrupt/consumed-token-no-ledger/contradictory state


def _qled_entered_event(cfg):
    """Prior entry evidence; a live ledger also needs the exact PID/boot-nonce event."""
    return any(e.get("kind") == "s0-d16-quarantine-entered" and e.get("code_sha256") == CODE_SHA
               for e in _qled_events(cfg))


def _qled_events(cfg):
    try:
        data = _read_bounded(cfg.home / "events.jsonl", 32 * 1024 * 1024)
    except Exception:
        return []
    out = []
    for line in data.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def _qled_failed_event(cfg):
    return any(e.get("kind") == "s0-d16-quarantine-activation-failed" and e.get("code_sha256") == CODE_SHA
               for e in _qled_events(cfg))


def _qled_bound_entry(cfg, qled):
    return any(e.get("kind") == "s0-d16-quarantine-entered"
               and e.get("code_sha256") == qled.get("code_sha256")
               and e.get("pid") == qled.get("runner_pid")
               and e.get("boot_nonce") == qled.get("runner_boot_nonce")
               for e in _qled_events(cfg))


def _prior_start_same_code(cfg):
    return any(e.get("kind") == "runner-start" and e.get("code_sha256") == CODE_SHA
               for e in _qled_events(cfg))


def _d16_policy_active(cfg):
    """The published owner-record commit is present; test repos lacking it stay pre-policy."""
    if (Path(cfg.repo) / D16_DUAL_OWNER_PATH).exists():
        return True
    try:
        return git_run(cfg.repo, "cat-file", "-e", f"{D16_BOOT_COMMIT}^{{commit}}", timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def quarantine_state(cfg):
    """Authoritative quarantine status. Returns (_QS_*, qled_or_reason).
    NONE → pre-reload, no quarantine active; ENTERED_LIVE → active, live runner;
    RESTARTED → active but runner died; DENY → any corrupt/missing/contradictory state.

    Default-deny: any absent, corrupt, truncated, or contradictory token or ledger
    denies all affected lanes. Deletion of both files after entry is also denied when
    the quarantine-entered event is present in events.jsonl.

    Under the quarantine-transfer lineage the authoritative transition record decides; the legacy ledger and
    token are preserved untouched and never consulted again."""
    try:
        rec = _load_transition(cfg)
    except GateError as e:
        return _QS_DENY, f"transition record is invalid: {e}"
    if rec is not None:
        return _transition_quarantine_state(cfg, rec)
    if _transfer_lineage_active(cfg):
        return _QS_DENY, "QUARANTINED: the verified transfer has not been consumed"
    tok_consumed = False
    tok_exists = False
    tok_path = _boot_activation_path(cfg)
    if tok_path.exists():
        tok_exists = True
        try:
            tok = json.loads(tok_path.read_bytes().decode())
            tok_consumed = bool(isinstance(tok, dict) and tok.get("consumed"))
        except Exception:
            return _QS_DENY, "activation token is unreadable or corrupt"
    try:
        qled = _load_qled(cfg)
    except GateError as e:
        return _QS_DENY, f"quarantine ledger is corrupt: {e}"
    if _qled_failed_event(cfg):
        return _QS_DENY, "a prior one-shot quarantine activation failed"
    if qled is None:
        if tok_consumed:
            return _QS_DENY, "activation token was consumed but quarantine ledger is absent (interrupted entry)"
        if _qled_entered_event(cfg):
            return _QS_DENY, "quarantine was previously entered (event record exists) but both activation files are absent"
        return _QS_NONE, None
    # Ledger is present — the consumed token must also be present; any discrepancy is denied
    if not tok_exists:
        return _QS_DENY, "quarantine ledger is present but activation token is absent (token deleted after entry)"
    if not tok_consumed:
        return _QS_DENY, "quarantine ledger is present but activation token is not consumed (contradictory state)"
    if qled.get("activation_failed") is True:
        return _QS_DENY, "the one-shot quarantine activation failed and cannot be retried"
    if not _qled_bound_entry(cfg, qled):
        return _QS_DENY, "quarantine ledger lacks its exact entered event"
    if qled.get("code_sha256") != CODE_SHA:
        return _QS_DENY, "quarantine ledger code hash disagrees with the loaded runner"
    if not _qled_runner_is_live(cfg, qled):
        return _QS_RESTARTED, qled
    return _QS_ENTERED_LIVE, qled


def _enter_quarantine_from_activation(cfg):
    """Consume the one-shot boot activation token and write the quarantine ledger.
    Absent token: no-op (default deny applies at gate checks). Corrupt/invalid: raises GateError.
    Any second call (consumed==True) raises GateError. Write order: mark consumed first, then write ledger
    so an interrupted write never leaves an unconsumed token paired with an absent ledger.
    Authentication: the token's commit must have observed push-event CI, must contain runner.py at CODE_SHA,
    and must be a direct child of D16_BOOT_PRIOR_TIP, whose exact ancestry is pinned back to D16_BOOT_COMMIT."""
    p = _boot_activation_path(cfg)
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        return  # no activation evidence — quarantine not entered; gate checks deny both lanes
    try:
        tok = json.loads(raw.decode())
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise GateError("S0/D16 boot activation token is corrupt or not valid JSON")
    if not (isinstance(tok, dict) and tok.get("schema") == 1
            and isinstance(tok.get("code_sha256"), str) and SHA256_RE.fullmatch(tok.get("code_sha256") or "")
            and isinstance(tok.get("commit"), str) and SHA_RE.fullmatch(tok.get("commit") or "")
            and isinstance(tok.get("consumed"), bool)):
        raise GateError("S0/D16 boot activation token schema is invalid or missing required fields")
    if tok.get("consumed"):
        raise GateError("S0/D16 boot activation token was already consumed; no second reload is authorized")
    if tok.get("code_sha256") != CODE_SHA:
        raise GateError("S0/D16 boot activation token code_sha256 does not match the loaded runner")
    # A controlled startup spends its token before external observations. A CI outage or
    # interrupted validation cannot turn a later process start into an unauthorized retry.
    atomic_write(p, json.dumps({**tok, "consumed": True}, sort_keys=True).encode())
    # Authenticate via provider-observed CI: live GitHub API call, not operator-attested ci.json
    _observe_ci_for_commit(cfg, tok["commit"])
    # Authentication reads use --no-replace-objects so local replace refs cannot substitute pinned objects.
    # Verify runner.py at the activation commit has the exact loaded hash
    try:
        blob_result = git_run(cfg.repo, "--no-replace-objects", "show", f"{tok['commit']}:tools/mission_runner/runner.py", timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise GateError("S0/D16 boot activation: cannot read runner.py at the activation commit")
    if not (blob_result.returncode == 0 and hashlib.sha256(blob_result.stdout).hexdigest() == CODE_SHA):
        raise GateError(
            "S0/D16 boot activation: runner.py at the activation commit does not match the loaded code hash")
    # Verify the exact pinned lineage: activation -> prior tip -> first amendment -> owner-record commit,
    # each commit having exactly one parent, so no arbitrary descendant or interposed commit is accepted.
    for child, want in ((tok["commit"], D16_BOOT_PRIOR_TIP), (D16_BOOT_PRIOR_TIP, D16_BOOT_FIRST_AMENDMENT),
                        (D16_BOOT_FIRST_AMENDMENT, D16_BOOT_COMMIT)):
        try:
            raw_commit = git_run(cfg.repo, "--no-replace-objects", "-c", "core.commitGraph=false",
                                 "cat-file", "commit", child, timeout=10)
        except (OSError, subprocess.SubprocessError):
            raise GateError("S0/D16 boot activation: cannot determine commit ancestry")
        parents = _raw_commit_parents(child, raw_commit.stdout) if raw_commit.returncode == 0 else None
        if parents != [want]:
            raise GateError(
                f"S0/D16 boot activation: commit {child[:12]} must have the single parent {want[:12]} "
                f"in the pinned runner-amendment lineage")
    # The prior tip must carry the exact reviewed runner blob and have provider-observed successful CI.
    try:
        prior_blob = git_run(cfg.repo, "--no-replace-objects", "show", f"{D16_BOOT_PRIOR_TIP}:tools/mission_runner/runner.py", timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise GateError("S0/D16 boot activation: cannot read runner.py at the prior runner-amendment tip")
    if not (prior_blob.returncode == 0 and hashlib.sha256(prior_blob.stdout).hexdigest() == D16_BOOT_PRIOR_RUNNER_SHA):
        raise GateError("S0/D16 boot activation: prior runner-amendment tip runner.py blob hash mismatch")
    _observe_ci_for_commit(cfg, D16_BOOT_PRIOR_TIP, run_id=D16_BOOT_PRIOR_CI_RUN)
    # A crash before the ledger write leaves the token consumed and no ledger: both lanes stay blocked.
    _write_qled(cfg, {"schema": 1, "entered_at": now_iso(), "runner_pid": os.getpid(),
                      "runner_boot_nonce": _PROCESS_BOOT_NONCE,
                      "code_sha256": CODE_SHA, "dual_rebind_consumed": False})


# ------------------------------------------------ quarantine-transfer replacement (2026-10-26)
# OWNER-2026-10-26-quarantine-transfer-replacement.md: QUARANTINED -> VERIFIED_TRANSFER_READY (read-only preflight
# result, never persisted) -> TRANSFER_CONSUMED -> S0_REBIND -> VERIFIED -> ACTIVE. ONE authoritative atomic, fsynced
# record at the runner home spends the transfer; events are audit evidence subordinate to it.
TRANSFER_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-26-quarantine-transfer-replacement.md"
TRANSFER_OWNER_SHA = "37c1614dbb8b099d5a51bfb0156f01277fae042f96c54db6bb4e4a03cd88c83d"
TRANSFER_OWNER_COMMIT = "ffbeb38cf09720ccc07fdc61cf213e29f38ae0d5"
TRANSFER_AMEND_PATH = "knowledge/00-Decisions/OWNER-2026-10-27-quarantine-transfer-review-only-amendment.md"
TRANSFER_AMEND_SHA = "028bce4b091f169bbb2520d75a4c62590178b91473103e1bf37dc6a62298cdf8"
TRANSFER_AMEND_COMMIT = "3cf1eac1334dad55b88cd404c0c1f2427d2860df"  # B: effective review-only amendment; sole parent of A
# OWNER-2026-10-27-quarantine-transfer-authorization-chain.md: B -> A (record-only); the Lifecycle contract record D (record-only,
# sole parent A) then precedes the successor C (exactly runner.py + test_runner.py, sole parent D): B -> A -> D -> C.
TRANSFER_AUTH_PATH = "knowledge/00-Decisions/OWNER-2026-10-27-quarantine-transfer-authorization-chain.md"
TRANSFER_AUTH_SHA = "f0c760c2d408629f54fcb2c935df5f8dcc18ae672ec2617faff1046aa7ab69d7"
TRANSFER_AUTH_COMMIT = "886c9e85fcc545173fa3a41c2ee16840a2900a94"  # A: the authorization commit; the record-only D is its direct child
TRANSFER_AUTH_CI_RUN = "40499369211"  # A's provider CI run, pinned; only a post-consumption live observation can confirm it
TRANSFER_LIFECYCLE_PATH = "knowledge/00-Decisions/OWNER-2026-10-27-quarantine-transfer-lifecycle-contract.md"
TRANSFER_LIFECYCLE_SHA = "f8e4540c69d0650f8cc17c80054569f3e89333bd114b2c8bc706bc28e900ce3a"
TRANSFER_LIFECYCLE_COMMIT = "fdf437e93369549d30789895c340aa2e18e8a60e"  # D: the Lifecycle contract record; the successor C is its direct child
TRANSFER_LIFECYCLE_CI_RUN = "40516265059"  # D's provider CI run, pinned; consistency binding only, confirmed post-consumption
TRANSFER_OLD_COMMIT = "8e56f2ebcd1ace3f76f4ce2a1554bfa5067278aa"
TRANSFER_OLD_CODE_SHA = "11de6aecf1db79f45ff8265a990b7f8b0155bce13d10559163e5fbbc37ff0782"
TRANSFER_TEST_FILE = "tools/mission_runner/tests/test_runner.py"
TRANSFER_CHECKPOINT = "checkpoints/20261026-quarantine-transfer-replacement"
TRANSFER_PREWRITE = "authorization-prewrite.json"
TRANSFER_PREWRITE_SHA = "288cc8b2bb2b11e439ea3310b5e8757b708cc2f9de1b44cdf49d8f27ab43e4ac"  # reviewed pre-write inventory
TRANSFER_RECORD_NAME = "s0_d16_transition.json"
TRANSFER_BOOT_NAME = "s0_d16_successor_boot.json"  # the one pre-consumption window: created exclusively by the first successor boot
TRANSFER_PRELOAD_NAME = "preload-opus-review.json"  # externally verified pre-load Opus evidence (checkpoint dir): bound, never granting
TRANSFER_REVIEW_ID = "mod004-transfer-successor-review-opus-20261027"
TRANSFER_KIND = "s0-d16-quarantine-transfer"
TRANSFER_STAGES = ("TRANSFER_CONSUMED", "S0_REBIND", "VERIFIED", "ACTIVE")
TRANSFER_READY = "VERIFIED_TRANSFER_READY"  # read-only preflight result; no durable record ever carries it
TRANSFER_STEP_EVERY = 15.0
_TR_ORDER = {s: i for i, s in enumerate(TRANSFER_STAGES)}
_TR_KEYS = {"schema", "kind", "transition_id", "stage", "consumed", "created_at", "pre_image", "old", "new",
            "first_boot", "attested", "boot_epoch", "restart_used", "ci", "s0_slot", "verified", "checksum"}
_TR_REVIEW_KEYS = ("task_id", "op", "session_id", "model", "out_sha256", "evidence_sha256", "subject_sha256", "prompt_sha256",
                   "dispatch_offset", "dispatch_sha256", "route_offset", "route_sha256", "done_offset", "done_sha256",
                   "recorded_offset", "recorded_sha256", "preload_sha256", "preload_output_sha256")
_TR_IMMUTABLE = ("schema", "kind", "transition_id", "consumed", "created_at", "pre_image", "old", "new", "first_boot")
_QS_ACTIVE = "ACTIVE"  # transfer complete and operational; S0 product and the D16 dual-version ID stay denied


class TransitionHold(Exception):
    """A queue file the current transition stage does not admit; it is held aside, never rejected or consumed."""


def _transition_path(cfg):
    return cfg.home / TRANSFER_RECORD_NAME


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _transition_checksum(rec):
    return _sha(_canon({k: v for k, v in rec.items() if k != "checksum"}))


def _is_hex(v, n):
    return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{%d}" % n, v) is not None


def _is_int(v):
    return type(v) is int


def _tr_dict(v, keys, label):
    if not (isinstance(v, dict) and set(v) == set(keys)):
        raise GateError(f"transition record: {label} has the wrong shape")
    return v


_TR_CI_RUN_KEYS = ("run_id", "workflow", "event", "branch", "head_sha", "status", "conclusion")


def _transition_ci_runs_validate(runs, c_commit):
    """The post-consumption provider observations (A, D and C) must be persisted with their full identity and be exactly
    the completed successful push run of the expected workflow on main at the expected SHA (A and D at their pinned run IDs)."""
    if not (isinstance(runs, dict) and set(runs) == {"A", "D", "C"}):
        raise GateError("transition record: the CI observation must bind A, D and C")
    for name, head in (("A", TRANSFER_AUTH_COMMIT), ("D", TRANSFER_LIFECYCLE_COMMIT), ("C", c_commit)):
        r = _tr_dict(runs[name], _TR_CI_RUN_KEYS, f"ci run {name}")
        if not (isinstance(r["run_id"], str) and r["run_id"].isdigit() and r["workflow"] == CI_WORKFLOW_NAME
                and r["event"] == "push" and r["branch"] == CI_BRANCH and r["head_sha"] == head
                and r["status"] == "completed" and r["conclusion"] == "success"):
            raise GateError(f"transition record: the CI run observed for {name} is not a completed successful push run on {CI_BRANCH}")
    if runs["A"]["run_id"] != TRANSFER_AUTH_CI_RUN:
        raise GateError("transition record: A's CI run ID is not the pinned run")
    if runs["D"]["run_id"] != TRANSFER_LIFECYCLE_CI_RUN:
        raise GateError("transition record: D's CI run ID is not the pinned run")


def _transition_validate(rec):
    """Strict schema and cross-field check; raises GateError so no caller sees an uncaught exception."""
    if not (isinstance(rec, dict) and set(rec) == _TR_KEYS):
        raise GateError("transition record: unexpected or missing fields")
    if not (rec["schema"] == 1 and rec["kind"] == TRANSFER_KIND and _is_hex(rec["transition_id"], 32)
            and rec["stage"] in _TR_ORDER and rec["consumed"] is True and isinstance(rec["created_at"], str)):
        raise GateError("transition record: header fields are invalid")
    pi = _tr_dict(rec["pre_image"], ("dir", "digest", "manifest_sha256"), "pre_image")
    if not (isinstance(pi["dir"], str) and pi["dir"] and _is_hex(pi["digest"], 64) and _is_hex(pi["manifest_sha256"], 64)):
        raise GateError("transition record: pre_image is invalid")
    old = _tr_dict(rec["old"], ("code_sha256", "commit", "pid", "boot_nonce", "entered_offset", "entered_event_sha256"), "old")
    if not (old["code_sha256"] == TRANSFER_OLD_CODE_SHA and old["commit"] == TRANSFER_OLD_COMMIT and _is_int(old["pid"])
            and old["pid"] > 0 and isinstance(old["boot_nonce"], str) and old["boot_nonce"]
            and _is_int(old["entered_offset"]) and old["entered_offset"] >= 0 and _is_hex(old["entered_event_sha256"], 64)):
        raise GateError("transition record: old binding is invalid")
    new = _tr_dict(rec["new"], ("code_sha256", "commit", "parent", "test_sha256", "diff_sha256", "review"), "new")
    if not (_is_hex(new["code_sha256"], 64) and _is_hex(new["commit"], 40) and new["parent"] == TRANSFER_LIFECYCLE_COMMIT
            and _is_hex(new["test_sha256"], 64) and _is_hex(new["diff_sha256"], 64)):
        raise GateError("transition record: new binding is invalid")
    rv = _tr_dict(new["review"], _TR_REVIEW_KEYS, "review")
    if not (rv["task_id"] == TRANSFER_REVIEW_ID and rv["op"] == f"{TRANSFER_REVIEW_ID}:1"
            and isinstance(rv["session_id"], str) and rv["session_id"] and isinstance(rv["model"], str) and "opus" in rv["model"].lower()
            and all(_is_hex(rv[k], 64) for k in _TR_REVIEW_KEYS if k.endswith("_sha256"))
            and all(_is_int(rv[k]) and rv[k] >= 0 for k in _TR_REVIEW_KEYS if k.endswith("_offset"))):
        raise GateError("transition record: review evidence chain is invalid")
    for name in ("first_boot", "attested"):
        b = _tr_dict(rec[name], ("pid", "boot_nonce", "code_sha256", "at"), name)
        if not (_is_int(b["pid"]) and b["pid"] > 0 and isinstance(b["boot_nonce"], str) and b["boot_nonce"]
                and _is_hex(b["code_sha256"], 64) and isinstance(b["at"], str)):
            raise GateError(f"transition record: {name} evidence is invalid")
    if not (_is_int(rec["boot_epoch"]) and rec["boot_epoch"] >= 1 and isinstance(rec["restart_used"], bool)
            and (not rec["restart_used"] or rec["boot_epoch"] >= 2)):
        raise GateError("transition record: boot epoch accounting is invalid")
    ci = _tr_dict(rec["ci"], ("observed", "at", "runs"), "ci")
    slot = _tr_dict(rec["s0_slot"], ("state", "task_id", "at"), "s0_slot")
    ver = _tr_dict(rec["verified"], ("docs", "receipt_sha256", "commit", "at"), "verified")
    if not (isinstance(ci["observed"], bool) and (ci["at"] is None or isinstance(ci["at"], str))):
        raise GateError("transition record: ci observation is invalid")
    if ci["observed"]:
        _transition_ci_runs_validate(ci["runs"], rec["new"]["commit"])
    elif ci["at"] is not None or ci["runs"] is not None:
        raise GateError("transition record: an unobserved CI carries evidence")
    if slot["state"] == "UNUSED":
        if slot["task_id"] is not None or slot["at"] is not None:
            raise GateError("transition record: an unused S0 slot carries a task")
    elif not (slot["state"] == "CONSUMED" and slot["task_id"] == S0_DUAL_REBIND_ID and isinstance(slot["at"], str)):
        raise GateError("transition record: S0 slot state is invalid")
    rank = _TR_ORDER[rec["stage"]]
    if rank >= 1 and not ci["observed"]:
        raise GateError("transition record: S0_REBIND or later requires the post-consumption CI observation")
    if rank >= 2 and slot["state"] != "CONSUMED":
        raise GateError("transition record: VERIFIED or later requires the consumed S0 slot")
    if rank >= 2:
        if not (isinstance(ver["docs"], dict) and set(ver["docs"]) == set(S0_DOC_PATHS)
                and all(_is_hex(v, 64) for v in ver["docs"].values()) and _is_hex(ver["receipt_sha256"], 64)
                and _is_hex(ver["commit"], 40) and isinstance(ver["at"], str)):
            raise GateError("transition record: VERIFIED evidence is invalid")
    elif any(v is not None for v in ver.values()):
        raise GateError("transition record: premature VERIFIED evidence")
    if rec["checksum"] != _transition_checksum(rec):
        raise GateError("transition record: checksum mismatch (corrupt or tampered)")
    return rec


def _load_transition(cfg):
    """None when no record exists; the validated record otherwise. Any problem raises GateError."""
    path = _transition_path(cfg)
    if not os.path.lexists(path):
        return None
    try:
        rec = json.loads(_read_bounded(path, 1 << 20).decode())
    except GateError:
        raise
    except Exception:
        raise GateError("transition record is unreadable or not valid JSON")
    return _transition_validate(rec)


def _atomic_create_exclusive(path, data):
    """Create `path` atomically and durably, failing if it already exists (a spent transfer is never replaced)."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(tmp, path)
    except FileExistsError:
        os.unlink(tmp)
        raise GateError("a transition record already exists; the transfer is never minted twice")
    os.unlink(tmp)
    fsync_dir(path.parent)


def _transition_check_monotonic(cur, new):
    for k in _TR_IMMUTABLE:
        if cur[k] != new[k]:
            raise GateError(f"transition record: immutable field {k} may not change")
    a, b = _TR_ORDER[cur["stage"]], _TR_ORDER[new["stage"]]
    if not a <= b <= a + 1:
        raise GateError("transition record: stages only advance one step at a time")
    if not cur["boot_epoch"] <= new["boot_epoch"] <= cur["boot_epoch"] + 1:
        raise GateError("transition record: boot epoch may only advance by one")
    if cur["restart_used"] and not new["restart_used"]:
        raise GateError("transition record: a spent recovery restart cannot be restored")
    if cur["ci"]["observed"] and new["ci"] != cur["ci"]:
        raise GateError("transition record: the CI observation is immutable once recorded")
    if cur["s0_slot"]["state"] == "CONSUMED" and new["s0_slot"] != cur["s0_slot"]:
        raise GateError("transition record: a consumed S0 slot cannot be restored")
    if cur["verified"]["docs"] is not None and new["verified"] != cur["verified"]:
        raise GateError("transition record: VERIFIED evidence is immutable")


def _transition_write(cfg, rec, create=False):
    """The only writer of the authoritative record: validated, monotonic, atomic and fsynced."""
    rec = {k: v for k, v in rec.items() if k != "checksum"}
    rec["checksum"] = _transition_checksum(rec)
    _transition_validate(rec)
    data = json.dumps(rec, sort_keys=True, indent=1).encode()
    if create:
        _atomic_create_exclusive(_transition_path(cfg), data)
        return rec
    cur = _load_transition(cfg)
    if cur is None:
        raise GateError("transition record is absent")
    _transition_check_monotonic(cur, rec)
    atomic_write(_transition_path(cfg), data)
    return rec


# --- authenticated raw Git reads (no replace refs, no commit-graph, every object re-hashed)
def _tgit(cfg, *args, timeout=30):
    try:
        return git_run(cfg.repo, "--no-replace-objects", "-c", "core.commitGraph=false", *args, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        raise GateError(f"git {args[0]} is unavailable")


_TR_OBJ_MEMO = None  # per-evaluation memo of hash-verified objects (set only inside _tr_memoized; never spans two gate evaluations)


def _tr_memoized(fn):
    """One gate evaluation re-reads the same few raw objects many times; memoize them for that evaluation only."""
    def wrapper(*a, **k):
        global _TR_OBJ_MEMO
        outer = _TR_OBJ_MEMO
        if outer is None:
            _TR_OBJ_MEMO = {}
        try:
            return fn(*a, **k)
        finally:
            if outer is None:
                _TR_OBJ_MEMO = None
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    return wrapper


def _transfer_raw_object(cfg, oid, kind):
    if not (isinstance(oid, str) and SHA_RE.fullmatch(oid)):
        raise GateError(f"invalid {kind} object id")
    memo = _TR_OBJ_MEMO
    if memo is not None and (kind, oid) in memo:
        return memo[(kind, oid)]
    p = _tgit(cfg, "cat-file", kind, oid)
    if p.returncode != 0:
        raise GateError(f"cannot read {kind} {oid[:12]}")
    if hashlib.sha1(kind.encode() + b" " + str(len(p.stdout)).encode() + b"\0" + p.stdout).hexdigest() != oid:
        raise GateError(f"{kind} {oid[:12]} failed object integrity")
    if memo is not None:
        memo[(kind, oid)] = p.stdout
    return p.stdout


def _transfer_commit(cfg, oid):
    """(tree id, parents) of an authenticated commit object."""
    body = _transfer_raw_object(cfg, oid, "commit")
    parents = _raw_commit_parents(oid, body)
    first = body.split(b"\n", 1)[0].decode("ascii", "replace")
    if parents is None or not first.startswith("tree ") or not SHA_RE.fullmatch(first[5:]):
        raise GateError(f"commit {oid[:12]} has an unsupported shape")
    return first[5:], parents


def _transfer_blob_oid(cfg, tree_oid, path):
    cur, parts = tree_oid, path.split("/")
    for i, part in enumerate(parts):
        body = _transfer_raw_object(cfg, cur, "tree")
        found, pos = None, 0
        try:
            while pos < len(body):
                sp = body.index(b" ", pos)
                nul = body.index(b"\0", sp)
                mode, name, oid = body[pos:sp], body[sp + 1:nul], body[nul + 1:nul + 21].hex()
                pos = nul + 21
                if name == part.encode():
                    found = (mode, oid)
                    break
        except ValueError:
            raise GateError("malformed tree object")
        if found is None:
            raise GateError(f"{path} is not in tree {tree_oid[:12]}")
        if i < len(parts) - 1:
            if found[0] != b"40000":
                raise GateError(f"{path}: {part} is not a directory")
            cur = found[1]
        elif found[0] not in (b"100644", b"100755"):
            raise GateError(f"{path} is not a regular file")
        else:
            return found[1]


def _transfer_blob(cfg, commit_oid, path):
    tree, _parents = _transfer_commit(cfg, commit_oid)
    return _transfer_raw_object(cfg, _transfer_blob_oid(cfg, tree, path), "blob")


def _transfer_diff(cfg, commit):
    """THE canonical D-to-C diff bytes (one command for every review, admission, preflight, transition and restart):
    git --no-replace-objects diff --binary --no-ext-diff --no-textconv --src-prefix=a/ --dst-prefix=b/ D C -- runner test"""
    p = _tgit(cfg, "diff", "--binary", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/",
              TRANSFER_LIFECYCLE_COMMIT, commit, "--", S0_RUNNER_FILE, TRANSFER_TEST_FILE)
    if p.returncode != 0:
        raise GateError("cannot compute the successor diff")
    return p.stdout


def _transfer_subject_sha(successor):
    return _sha(_canon({k: successor[k] for k in ("parent", "commit", "code_sha256", "test_sha256", "diff_sha256")}))


# --- old (quarantined) evidence
def _transfer_prewrite(cfg):
    p = Path(cfg.home) / TRANSFER_CHECKPOINT / TRANSFER_PREWRITE
    try:
        raw = _read_bounded(p, 1 << 20)
        d = json.loads(raw.decode())
    except GateError:
        raise GateError("transfer checkpoint authorization-prewrite.json is missing or not a regular file")
    except Exception:
        raise GateError("transfer checkpoint authorization-prewrite.json is malformed")
    if _sha(raw) != TRANSFER_PREWRITE_SHA:
        raise GateError("transfer checkpoint authorization-prewrite.json differs from the reviewed pinned inventory")
    ev = d.get("evidence") if isinstance(d, dict) else None
    if not (isinstance(ev, dict) and d.get("head") == TRANSFER_OLD_COMMIT and d.get("git_status") == ""
            and all(isinstance(e, dict) and _is_hex(e.get("sha256"), 64) and _is_int(e.get("size")) for e in ev.values())):
        raise GateError("transfer checkpoint authorization-prewrite.json contradicts the pinned incident")
    return ev, _sha(raw)


def _prewrite_entry(ev, path):
    e = ev.get(str(path))
    if e is None:
        raise GateError(f"authorization-prewrite.json has no entry for {Path(path).name}")
    return e


def _transfer_read(path, label, limit=64 * 1024 * 1024):
    try:
        return _read_bounded(Path(path), limit)
    except GateError:
        raise GateError(f"{label} is missing or not a regular file")


def _transfer_receipts(cfg):
    base = Path(cfg.home) / "acceptances"
    out = {}
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_symlink():
                raise GateError("a receipt path is a symlink")
            if p.is_file():
                out[p.relative_to(base).as_posix()] = _sha(p.read_bytes())
    return out


def _transfer_event_lines(evt):
    """[(offset, line, event)] of a complete events log; GateError on a partial, malformed or non-object line."""
    chunks, out, offset = evt.split(b"\n"), [], 0
    if chunks[-1] != b"":
        raise GateError("events log ends with a partial line")
    for line in chunks[:-1]:
        try:
            e = json.loads(line.decode())
        except Exception:
            raise GateError(f"events log has a malformed line at offset {offset}")
        if not isinstance(e, dict):
            raise GateError(f"events log has a non-object line at offset {offset}")
        out.append((offset, line, e))
        offset += len(line) + 1
    return out


@_tr_memoized
def _transfer_old_evidence(cfg):
    """Authenticate the quarantined incident evidence. Pure and read-only; raises GateError on any missing,
    malformed or contradictory item. The returned digest binds the immutable evidence (state.json drifts with
    every heartbeat, so its pre-image is preserved and recorded but is not part of the review-bound digest)."""
    home = Path(cfg.home)
    ev, prewrite_sha = _transfer_prewrite(cfg)
    tok_p, led_p, evt_p, st_p = home / D16_BOOT_ACTIVATION_NAME, _qled_path(cfg), home / "events.jsonl", home / "state.json"
    tok_b = _transfer_read(tok_p, "old consumed boot token")
    led_b = _transfer_read(led_p, "old quarantine ledger")
    evt_b = _transfer_read(evt_p, "events log", 32 * 1024 * 1024)
    st_b = _transfer_read(st_p, "state.json")
    for label, path, data in (("boot token", tok_p, tok_b), ("quarantine ledger", led_p, led_b)):
        e = _prewrite_entry(ev, path)
        if _sha(data) != e["sha256"] or len(data) != e["size"]:
            raise GateError(f"old {label} differs from authorization-prewrite.json")
    try:
        tok = json.loads(tok_b.decode())
    except Exception:
        raise GateError("old boot token is not valid JSON")
    if not (isinstance(tok, dict) and set(tok) == {"code_sha256", "commit", "consumed", "schema"} and tok["schema"] == 1
            and tok["consumed"] is True and tok["code_sha256"] == TRANSFER_OLD_CODE_SHA and tok["commit"] == TRANSFER_OLD_COMMIT):
        raise GateError("old boot token is not the pinned consumed token")
    qled = _parse_qled(led_b)
    if not (qled["code_sha256"] == TRANSFER_OLD_CODE_SHA and qled["runner_pid"] > 0
            and not qled.get("activation_failed") and qled["dual_rebind_consumed"] is False):
        raise GateError("old quarantine ledger is not the pinned entered, unused ledger")
    pe = _prewrite_entry(ev, evt_p)
    if len(evt_b) < pe["size"] or _sha(evt_b[:pe["size"]]) != pe["sha256"]:
        raise GateError("events log does not extend the authorization-prewrite.json prefix")
    entered, kinds = [], []
    for offset, line, e in _transfer_event_lines(evt_b):
        kinds.append(e.get("kind"))
        if e.get("kind") == "s0-d16-quarantine-entered":
            entered.append((offset, line, e))
    if "s0-d16-quarantine-activation-failed" in kinds or any(k in ("quarantine-transfer-stage", "quarantine-transfer-slot-consumed") for k in kinds):  # refusals/denials consume nothing and never block a retry
        raise GateError("events log records a failed activation or a prior transfer")
    if len(entered) != 1:
        raise GateError("events log must hold exactly one old quarantine-entered event")
    e_off, e_line, e = entered[0]
    if not (e.get("code_sha256") == TRANSFER_OLD_CODE_SHA and e.get("pid") == qled["runner_pid"]
            and e.get("boot_nonce") == qled["runner_boot_nonce"] and e_off + len(e_line) + 1 <= pe["size"]):
        raise GateError("old entered event does not bind the old PID/nonce/code inside the pre-write prefix")
    runner_old = _transfer_blob(cfg, TRANSFER_OLD_COMMIT, S0_RUNNER_FILE)
    test_old = _transfer_blob(cfg, TRANSFER_OLD_COMMIT, TRANSFER_TEST_FILE)
    for label, data, path in (("old runner", runner_old, Path(cfg.repo) / S0_RUNNER_FILE),
                              ("old test", test_old, Path(cfg.repo) / TRANSFER_TEST_FILE)):
        if _sha(data) != _prewrite_entry(ev, path)["sha256"]:
            raise GateError(f"{label} blob at the pinned old commit differs from authorization-prewrite.json")
    if _sha(runner_old) != TRANSFER_OLD_CODE_SHA:
        raise GateError("old runner bytes do not match the pinned old code hash")
    try:
        state = json.loads(st_b.decode())
    except Exception:
        raise GateError("state.json is not valid JSON")
    tasks = state.get("tasks") if isinstance(state, dict) else None
    runner = state.get("runner") if isinstance(state, dict) else None
    # The old PID/nonce/code are authenticated by the hash-pinned ledger and the entered event above, NOT by the mutable
    # live state: the successor's own heartbeat legitimately replaces state["runner"]. That block may only carry the old
    # identity or the first successor boot's identity (any other value is a contradiction).
    boot = _transfer_first_boot(cfg)
    if not (isinstance(tasks, dict) and isinstance(runner, dict)
            and ((runner.get("code_sha256") == TRANSFER_OLD_CODE_SHA and runner.get("pid") == qled["runner_pid"]
                  and runner.get("boot_nonce") == qled["runner_boot_nonce"])
                 or (boot is not None and runner.get("code_sha256") == CODE_SHA and runner.get("pid") == boot["pid"]
                     and runner.get("boot_nonce") == boot["boot_nonce"]))):
        raise GateError("state.json binds neither the old runner PID/nonce/code nor the first successor boot")
    if len(st_b) < _prewrite_entry(ev, st_p)["size"]:
        raise GateError("state.json is smaller than the authorization-prewrite.json inventory")
    # The S0 slot is unused: the fixed task was refused before creation, so prove absence, not existence.
    if S0_DUAL_REBIND_ID in tasks or any(isinstance(x, dict) and ((x.get("review_of") or {}).get("task_id") == S0_DUAL_REBIND_ID
                                                                   or x.get("id") == S0_DUAL_REBIND_ID) for x in tasks.values()):
        raise GateError("the fixed S0 rebind ID already exists in state or has a bound review")
    for d in ("queue", "commands"):
        base = home / d
        if base.is_dir() and any(S0_DUAL_REBIND_ID.encode() in p.read_bytes() for p in base.iterdir() if p.is_file()):
            raise GateError("the fixed S0 rebind ID is already queued")
    binding = {"token_sha256": _sha(tok_b), "ledger_sha256": _sha(led_b), "entered_offset": e_off,
               "entered_event_sha256": _sha(e_line), "events_prefix_size": pe["size"], "events_prefix_sha256": pe["sha256"],
               "old_runner_sha256": _sha(runner_old), "old_test_sha256": _sha(test_old), "old_commit": TRANSFER_OLD_COMMIT,
               "old_pid": qled["runner_pid"], "old_nonce": qled["runner_boot_nonce"], "prewrite_sha256": prewrite_sha}
    return {"binding": binding, "digest": _sha(_canon(binding)), "qled": qled, "state": state, "tasks": tasks,
            "files": {"boot-token.json": tok_b, "quarantine-ledger.json": led_b, "events.jsonl": evt_b, "state.json": st_b,
                      "old-runner.py": runner_old, "old-test_runner.py": test_old,
                      TRANSFER_PREWRITE: _transfer_read(Path(cfg.home) / TRANSFER_CHECKPOINT / TRANSFER_PREWRITE, "prewrite")}}


def _transfer_write_pre_image(cfg, tid, old, extra=None):
    """Out-of-repo byte-for-byte pre-image: built under a temporary name, fsynced, then renamed into place."""
    root = Path(cfg.home) / TRANSFER_CHECKPOINT
    final, tmp = root / f"pre-image-{tid}", root / f".pre-image-{tid}.tmp"
    if final.exists() or tmp.exists():
        raise GateError("pre-image directory already exists")
    receipts = _transfer_receipts(cfg)
    files = {**old["files"], **(extra or {})}
    for rel in receipts:
        files["receipts/" + rel] = (Path(cfg.home) / "acceptances" / rel).read_bytes()
    manifest = {"transition_id": tid, "digest": old["digest"],
                "files": {n: {"sha256": _sha(b), "size": len(b)} for n, b in sorted(files.items())},
                "receipts": receipts}
    tmp.mkdir(mode=0o700)
    for n, b in files.items():
        p = tmp / n
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, b)
            os.fsync(fd)
        finally:
            os.close(fd)
    mb = json.dumps(manifest, sort_keys=True, indent=1).encode()
    fd = os.open(tmp / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, mb)
        os.fsync(fd)
    finally:
        os.close(fd)
    for d in {p.parent for p in tmp.rglob("*") if p.is_file()} | {tmp}:
        fsync_dir(d)
    os.rename(tmp, final)
    fsync_dir(root)
    return {"dir": str(final.relative_to(Path(cfg.home))), "digest": old["digest"], "manifest_sha256": _sha(mb)}


def _transfer_pre_image_problem(cfg, rec, full):
    """None when the recorded pre-image is intact. The cheap form checks the manifest; `full` re-hashes every file."""
    pi = rec["pre_image"]
    d = Path(cfg.home) / pi["dir"]
    if ".." in Path(pi["dir"]).parts or Path(pi["dir"]).is_absolute() or not d.is_dir() or d.is_symlink():
        return "pre-image directory is missing"
    try:
        mb = _read_bounded(d / "manifest.json", 8 * 1024 * 1024)
        if _sha(mb) != pi["manifest_sha256"]:
            return "pre-image manifest differs from the record"
        m = json.loads(mb.decode())
        if m.get("digest") != pi["digest"] or m.get("transition_id") != rec["transition_id"]:
            return "pre-image manifest binds a different transfer"
        if full:
            for n, e in m["files"].items():
                if _sha(_read_bounded(d / n, 64 * 1024 * 1024)) != e["sha256"]:
                    return f"pre-image file {n} was altered"
            # The record's own bindings must still hold against the preserved bytes, not only the manifest.
            evt, off = _read_bounded(d / "events.jsonl", 32 * 1024 * 1024), rec["old"]["entered_offset"]
            if off >= len(evt) or _sha(evt[off:evt.index(b"\n", off)]) != rec["old"]["entered_event_sha256"]:
                return "pre-image does not hold the exact entered event at the recorded offset"
            # the runner-recorded review chain is re-derived from the PRESERVED output, evidence and event log
            new, rd = rec["new"], d / "review"
            chain = _transfer_review_chain(evt, _read_bounded(rd / "review.out", 8 * 1024 * 1024),
                                           _read_bounded(rd / "review.evidence.json", 8 * 1024 * 1024),
                                           _transfer_subject_sha(new), _transfer_preload_bind(
                                               _read_bounded(rd / "preload.json", 1 << 20), _read_bounded(rd / "preload.out", 8 * 1024 * 1024), new))
            if chain != new["review"]:
                return "pre-image review evidence chain does not match the recorded binding"
    except Exception as e:
        return f"pre-image is unreadable: {type(e).__name__}"
    return None


# --- successor binding, review evidence and process checks
_TR_BOOT_KEYS = {"schema", "kind", "pid", "boot_nonce", "code_sha256", "at"}


def _transfer_first_boot(cfg, me=False):
    """The first-successor-boot marker (the one pre-consumption window), or None. `me` also requires that THIS process
    created it: a later process under the same code never inherits the window."""
    try:
        d = json.loads(_read_bounded(Path(cfg.home) / TRANSFER_BOOT_NAME, 1 << 16).decode())
    except Exception:
        return None
    if not (isinstance(d, dict) and set(d) == _TR_BOOT_KEYS and d["schema"] == 1 and d["kind"] == "s0-d16-successor-first-boot"
            and _is_int(d["pid"]) and d["pid"] > 0 and isinstance(d["boot_nonce"], str) and d["boot_nonce"]
            and d["code_sha256"] == CODE_SHA):
        return None
    return d if not me or (d["pid"] == os.getpid() and d["boot_nonce"] == _PROCESS_BOOT_NONCE) else None


def _transfer_changed(cfg, parent, child):
    """The COMPLETE, unfiltered changed-path set between two commits (no pathspec can hide an extra file)."""
    p = _tgit(cfg, "diff-tree", "-r", "-z", "--no-renames", "--name-only", "--no-commit-id", parent, child)
    if p.returncode != 0:
        raise GateError("cannot list the changed paths")
    return sorted(x for x in p.stdout.decode("utf-8", "surrogateescape").split("\0") if x)


def _transfer_no_replacements(cfg):
    """Replace refs, grafts and shallow boundaries could present a different history than the raw objects; refuse them."""
    refs = _tgit(cfg, "for-each-ref", "--format=%(refname)", "refs/replace")
    graft = _tgit(cfg, "rev-parse", "--git-path", "info/grafts")
    shallow = _tgit(cfg, "rev-parse", "--is-shallow-repository")
    if refs.returncode != 0 or graft.returncode != 0 or shallow.returncode != 0:
        raise GateError("cannot prove the repository has no replacements, grafts or shallow boundary")
    gp = Path(graft.stdout.decode().strip())
    gp = gp if gp.is_absolute() else Path(cfg.repo) / gp
    if refs.stdout.strip() or os.path.lexists(gp) or shallow.stdout.strip() != b"false":
        raise GateError("the repository has replace refs, a grafts file or a shallow boundary")


@_tr_memoized
def _transfer_successor(cfg):
    """Deterministic local binding of the loaded successor C to the authorization chain B -> A -> D -> C (direct, single-parent
    raw Git objects; the changed-path sets of B->A, A->D and D->C are checked separately and unfiltered). Nothing here
    consults a provider or an operator-held file."""
    runner_p, test_p = Path(cfg.repo) / S0_RUNNER_FILE, Path(cfg.repo) / TRANSFER_TEST_FILE
    runner_b, test_b = _transfer_read(runner_p, "successor runner.py"), _transfer_read(test_p, "successor test_runner.py")
    if not (_sha(runner_b) == CODE_SHA == _LOADED_CODE_SHA):
        raise GateError("on-disk runner.py differs from the loaded successor code (stale disk)")
    _transfer_no_replacements(cfg)
    st = _tgit(cfg, "--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=all")
    if st.returncode != 0 or st.stdout != b"":
        raise GateError("the successor working tree is not clean")
    head = _tgit(cfg, "rev-parse", "--verify", "HEAD")
    head = head.stdout.decode().strip() if head.returncode == 0 else ""
    tree, parents = _transfer_commit(cfg, head)
    if parents != [TRANSFER_LIFECYCLE_COMMIT]:
        raise GateError("the successor commit C is not a direct, single-parent child of the Lifecycle contract commit D")
    _tree_d, parents_d = _transfer_commit(cfg, TRANSFER_LIFECYCLE_COMMIT)
    if parents_d != [TRANSFER_AUTH_COMMIT]:
        raise GateError("the Lifecycle contract commit D is not a direct, single-parent child of the authorization commit A")
    if _transfer_changed(cfg, TRANSFER_AUTH_COMMIT, TRANSFER_LIFECYCLE_COMMIT) != [TRANSFER_LIFECYCLE_PATH]:
        raise GateError("the Lifecycle contract commit D must change exactly its owner record")
    _tree_a, parents_a = _transfer_commit(cfg, TRANSFER_AUTH_COMMIT)
    if parents_a != [TRANSFER_AMEND_COMMIT]:
        raise GateError("the authorization commit A is not a direct, single-parent child of the effective amendment commit B")
    if _transfer_changed(cfg, TRANSFER_AMEND_COMMIT, TRANSFER_AUTH_COMMIT) != [TRANSFER_AUTH_PATH]:
        raise GateError("the authorization commit A must change exactly its owner record")
    auth = _transfer_blob(cfg, TRANSFER_AUTH_COMMIT, TRANSFER_AUTH_PATH)
    if (_sha(auth) != TRANSFER_AUTH_SHA or _transfer_blob(cfg, TRANSFER_LIFECYCLE_COMMIT, TRANSFER_AUTH_PATH) != auth
            or _transfer_blob(cfg, head, TRANSFER_AUTH_PATH) != auth):
        raise GateError("the authorization-chain owner record is not the pinned, unchanged published record")
    life = _transfer_blob(cfg, TRANSFER_LIFECYCLE_COMMIT, TRANSFER_LIFECYCLE_PATH)
    if _sha(life) != TRANSFER_LIFECYCLE_SHA or _transfer_blob(cfg, head, TRANSFER_LIFECYCLE_PATH) != life:
        raise GateError("the Lifecycle contract owner record is not the pinned, unchanged published record")
    if _sha(_transfer_blob(cfg, head, S0_RUNNER_FILE)) != CODE_SHA:
        raise GateError("the committed runner.py blob is not the loaded successor code")
    if _sha(_transfer_blob(cfg, head, TRANSFER_TEST_FILE)) != _sha(test_b):
        raise GateError("the committed test blob differs from the on-disk test file")
    # the two earlier owner records: at their own commit, unchanged at B, at A, at D and at C
    for path, sha, commit in ((TRANSFER_OWNER_PATH, TRANSFER_OWNER_SHA, TRANSFER_OWNER_COMMIT),
                              (TRANSFER_AMEND_PATH, TRANSFER_AMEND_SHA, TRANSFER_AMEND_COMMIT)):
        rec = _transfer_blob(cfg, commit, path)
        if _sha(rec) != sha or any(_transfer_blob(cfg, c, path) != rec for c in (TRANSFER_AMEND_COMMIT, TRANSFER_AUTH_COMMIT, TRANSFER_LIFECYCLE_COMMIT, head)):
            raise GateError(f"the owner record {Path(path).name} is not the pinned, unchanged published record")
    if _transfer_changed(cfg, TRANSFER_LIFECYCLE_COMMIT, head) != sorted([S0_RUNNER_FILE, TRANSFER_TEST_FILE]):
        raise GateError("the successor commit must change exactly runner.py and test_runner.py")
    return {"commit": head, "parent": TRANSFER_LIFECYCLE_COMMIT, "code_sha256": CODE_SHA, "test_sha256": _sha(test_b),
            "diff_sha256": _sha(_transfer_diff(cfg, head))}


def _transfer_preload_bind(raw, output, successor):
    """The externally verified PRE-LOAD Opus review evidence (checkpoint dir). It must name this exact subject, and its
    hashes are bound into the transition record, but it is operator-authored text and never grants the transfer."""
    try:
        d = json.loads(raw.decode())
    except Exception:
        raise GateError("pre-load Opus review evidence is not valid JSON")
    keys = {"schema", "kind", "commit", "code_sha256", "test_sha256", "diff_sha256", "model", "session_id", "output_file",
            "output_sha256", "outcome"}
    if isinstance(d, dict) and "c_ci_run_id" in d:  # optional operator-held run ID of C's CI: a post-consumption pin only
        if not (isinstance(d["c_ci_run_id"], str) and d["c_ci_run_id"].isdigit()):
            raise GateError("pre-load Opus review evidence carries a malformed C CI run ID")
        keys = keys | {"c_ci_run_id"}
    if not (isinstance(d, dict) and set(d) == keys and d["schema"] == 1 and d["kind"] == "preload-opus-review"
            and all(d[k] == successor[k] for k in ("commit", "code_sha256", "test_sha256", "diff_sha256"))
            and isinstance(d["model"], str) and "opus" in d["model"].lower() and isinstance(d["session_id"], str) and d["session_id"]
            and d["outcome"] == "APPROVED" and d["output_sha256"] == _sha(output)):
        raise GateError("pre-load Opus review evidence does not bind the exact successor subject and an Opus APPROVED output")
    return {"preload_sha256": _sha(raw), "preload_output_sha256": _sha(output)}


def _transfer_preload(cfg, successor):
    base = Path(cfg.home) / TRANSFER_CHECKPOINT
    raw = _transfer_read(base / TRANSFER_PRELOAD_NAME, "pre-load Opus review evidence", 1 << 20)
    try:
        name = json.loads(raw.decode())["output_file"]
    except Exception:
        raise GateError("pre-load Opus review evidence is not valid JSON")
    if not (isinstance(name, str) and name == Path(name).name and name not in ("", ".", "..")):
        raise GateError("pre-load Opus review output_file must be a plain file name")
    out = _transfer_read(base / name, "pre-load Opus review output", 8 * 1024 * 1024)
    return _transfer_preload_bind(raw, out, successor), {"preload.json": raw, "preload.out": out}


def _transfer_review_chain(evt, out_b, ev_b, subject_sha, preload):
    """Authenticate the ONE post-load, runner-recorded Opus review from DURABLE artifacts only (the run output, its
    evidence file and the append-only event log), never from state.json. Returns the chain binding or raises GateError."""
    op, lines = f"{TRANSFER_REVIEW_ID}:1", _transfer_event_lines(evt)
    mine = [x for x in lines if x[2].get("task_id") == TRANSFER_REVIEW_ID or x[2].get("op_id") == op]
    if any(x[2].get("kind") not in ("transfer-review-created", "task-gated", "task-gate-cleared", "dispatch", "route-evidence",
                                    "task-done", "transfer-review-recorded") for x in mine):
        raise GateError("the review has a failed, blocked, retried or otherwise ambiguous event")

    def one(kind, pool):
        m = [x for x in pool if x[2].get("kind") == kind]
        if len(m) != 1:
            raise GateError(f"the review chain needs exactly one {kind} event")
        return m[0]
    boot, disp, route, done, rec = (one("quarantine-transfer-first-boot", lines), one("dispatch", mine),
                                    one("route-evidence", mine), one("task-done", mine), one("transfer-review-recorded", mine))
    if not boot[0] < disp[0] < route[0] < done[0] < rec[0]:
        raise GateError("the review events are out of order")
    if any(x[2].get("kind") == "dispatch" and x[0] > boot[0] and x is not disp for x in lines):
        raise GateError("another task was dispatched after the first successor boot")
    d, r, e = disp[2], route[2], done[2]
    if not (d.get("op_id") == op and d.get("role") == "code-review" and d.get("model_alias") == "opus" and d.get("attempt") == 1
            and d.get("subject_sha256") == subject_sha and _is_hex(d.get("prompt_sha256"), 64)
            and d.get("pid") == boot[2].get("pid") and d.get("boot_nonce") == boot[2].get("boot_nonce")):
        raise GateError("the review dispatch event does not bind the first boot, the Opus alias and the exact subject")
    try:
        out = json.loads(out_b.decode())
        evidence = json.loads(ev_b.decode())
    except Exception:
        raise GateError("the review run output or evidence is not valid JSON")
    lastline = [ln.strip() for ln in str(out.get("result", "")).splitlines() if ln.strip()] if isinstance(out, dict) else []
    verdict = OUTCOME_RE.match(lastline[-1]) if lastline else None
    judged = judge_route("code-review", out) if isinstance(out, dict) else {}
    sid = out.get("session_id") if isinstance(out, dict) else None
    if not (isinstance(out, dict) and out.get("subtype") == "success" and not out.get("is_error") and out.get("permission_denials") == []
            and isinstance(sid, str) and sid and verdict and verdict.group(1) == "APPROVED"
            and judged.get("verdict") == "VERIFIED" and judged.get("intended") == "opus" and family_of(judged.get("primary") or "") == "opus"):
        raise GateError("the review run output is not a successful Opus APPROVED result with a verified route")
    if not (r.get("op_id") == op and r.get("session_id") == sid and r.get("verdict") == "VERIFIED" and r.get("intended") == "opus"
            and r.get("primary") == judged["primary"] and r.get("dispatch_op") == op
            and e.get("op_id") == op and e.get("route") == "VERIFIED" and e.get("changed") == 0):
        raise GateError("the review route and settlement events do not match the run output and provider session")
    if not (isinstance(evidence, dict) and evidence.get("op") == op and evidence.get("review_outcome") == "APPROVED"
            and evidence.get("violations") == [] and evidence.get("changed") == [] and evidence.get("head_moved") is False
            and evidence.get("route_verdict") == "VERIFIED" and evidence.get("subtype") == "success"):
        raise GateError("the review evidence file is not a clean, read-only APPROVED settlement")
    if not (rec[2].get("op_id") == op and rec[2].get("out_sha256") == _sha(out_b) and rec[2].get("evidence_sha256") == _sha(ev_b)):
        raise GateError("the review output or evidence differs from what the runner recorded at settlement")
    return {"task_id": TRANSFER_REVIEW_ID, "op": op, "session_id": sid, "model": judged["primary"], "out_sha256": _sha(out_b),
            "evidence_sha256": _sha(ev_b), "subject_sha256": subject_sha, "prompt_sha256": d["prompt_sha256"],
            "dispatch_offset": disp[0], "dispatch_sha256": _sha(disp[1]), "route_offset": route[0], "route_sha256": _sha(route[1]),
            "done_offset": done[0], "done_sha256": _sha(done[1]), "recorded_offset": rec[0], "recorded_sha256": _sha(rec[1]),
            **preload}


def _transfer_review_files(cfg):
    stem = Path(cfg.home) / "runs" / f"{TRANSFER_REVIEW_ID}-1"
    return (_transfer_read(Path(f"{stem}.out"), "review run output", 8 * 1024 * 1024),
            _transfer_read(Path(f"{stem}.evidence.json"), "review evidence", 8 * 1024 * 1024))


def _transfer_review_evidence(cfg, old, successor):
    """Chain the post-load review (artifacts + event log) and bind the pre-load evidence. Returns (binding, files)."""
    t = old["tasks"].get(TRANSFER_REVIEW_ID)
    if not (isinstance(t, dict) and t.get("status") == "DONE" and t.get("attempts") == 1):
        raise GateError("the one runner-recorded successor review is absent, unfinished, retried or not DONE")
    out_b, ev_b = _transfer_review_files(cfg)
    preload, pfiles = _transfer_preload(cfg, successor)
    chain = _transfer_review_chain(old["files"]["events.jsonl"], out_b, ev_b, _transfer_subject_sha(successor), preload)
    return chain, {"review/review.out": out_b, "review/review.evidence.json": ev_b,
                   **{"review/" + n: b for n, b in pfiles.items()}}


def _transfer_ci_observe(cfg, rec):
    """The post-consumption LIVE provider observations of A and D (each at its pinned run ID) and C (at the operator-held
    run ID from the bound pre-load evidence, when supplied). Raises GateError on any outage, mismatch or ambiguity."""
    c_run = None
    try:
        pre = json.loads(_read_bounded(Path(cfg.home) / rec["pre_image"]["dir"] / "review" / "preload.json", 1 << 20).decode())
        c_run = pre.get("c_ci_run_id") if isinstance(pre, dict) else None
    except Exception:
        raise GateError("the preserved pre-load evidence is unreadable for the CI pin")
    runs = {"A": _observe_ci_for_commit(cfg, TRANSFER_AUTH_COMMIT, run_id=TRANSFER_AUTH_CI_RUN, opener=_ci_opener),
            "D": _observe_ci_for_commit(cfg, TRANSFER_LIFECYCLE_COMMIT, run_id=TRANSFER_LIFECYCLE_CI_RUN, opener=_ci_opener),
            "C": _observe_ci_for_commit(cfg, rec["new"]["commit"], run_id=c_run, opener=_ci_opener)}
    _transition_ci_runs_validate(runs, rec["new"]["commit"])
    return runs


def _runner_pids_from_ps(text, self_pid):
    """PIDs of runner `run` processes in `ps -axo pid=,command=` output (a false positive only denies)."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit() or int(parts[0]) == self_pid:
            continue
        argv = parts[1:]
        if any(a.endswith("mission_runner/runner.py") for a in argv) and "run" in argv and "dashboard" not in argv:
            out.append(int(parts[0]))
    return out


def _other_runner_pids(cfg):
    try:
        p = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise GateError("cannot enumerate processes")
    if p.returncode != 0:
        raise GateError("cannot enumerate processes")
    return _runner_pids_from_ps(p.stdout, os.getpid())


def transfer_preflight(cfg, rlock_held=False, wlock_held=False):
    """Deterministic, read-only local preflight. Returns the VERIFIED_TRANSFER_READY result (never persisted, never an
    authorization) or raises GateError. Provider CI is deliberately NOT consulted here."""
    if _load_transition(cfg) is not None:
        raise GateError("a transition record already exists; the transfer cannot be minted again")
    old = _transfer_old_evidence(cfg)
    successor = _transfer_successor(cfg)
    if pid_alive(old["binding"]["old_pid"]):
        raise GateError("the old runner PID is still alive")
    if _other_runner_pids(cfg):
        raise GateError("another runner process exists")
    if not rlock_held and FileLock.probe(Path(cfg.home) / "locks" / "runner.lock") == "free":
        raise GateError("the sole runner lock is not held by the successor")
    if not wlock_held and FileLock.probe(writer_lock_path(cfg.home, cfg.repo)) != "free":
        raise GateError("the repository writer lock is held")
    tasks, state = old["tasks"], old["state"]
    h = state.get("handoff") or {}
    if h.get("request") or h.get("quarantine"):
        raise GateError("an orchestrator handoff or gateway turn is open")
    if any(isinstance(t, dict) and (t.get("status") == "RUNNING" or t.get("child")) for t in tasks.values()):
        raise GateError("a worker task is running")
    if any(isinstance(t, dict) and t.get("stage") == "verify_pending" for t in tasks.values()):
        raise GateError("an inherited verify_pending task exists; a saved verification may not resume under the transfer")
    chain, files = _transfer_review_evidence(cfg, old, successor)
    return {"stage": TRANSFER_READY, "old": old, "successor": successor, "review": chain, "review_files": files}


# --- stage evaluation shared by the gates
def _transfer_lineage_active(cfg):
    """UNCONDITIONAL for any code other than the quarantined old runner: no file under the runner home (record, ledger,
    token, pre-image, events) can switch the lineage off, so deleting all of them still leaves every lane default-deny."""
    return CODE_SHA != TRANSFER_OLD_CODE_SHA


def _transition_live(cfg, rec):
    try:
        ov = _transition_overlay(cfg, rec)
    except GateError:
        return False
    att = ov["attested"] if ov else rec["attested"]  # under the recovery overlay the NEW attestation governs liveness
    if att["code_sha256"] != CODE_SHA:
        return False
    if att["pid"] == os.getpid():
        return att["boot_nonce"] == _PROCESS_BOOT_NONCE
    try:
        state = json.loads(_read_bounded(Path(cfg.home) / "state.json", 64 * 1024 * 1024))
    except Exception:
        return False
    runner = (state or {}).get("runner") or {}
    return (s0_runner_problem(state) is None and runner.get("pid") == att["pid"]
            and runner.get("boot_nonce") == att["boot_nonce"])


def _transition_replay_problem(cfg, rec):
    """Audit events are only ever appended AFTER the record reaches a stage, so a record that trails its own audit
    trail was rolled back or replayed. Fail-closed only: events never grant anything."""
    rank = _TR_ORDER[rec["stage"]]
    for e in _qled_events(cfg):
        if e.get("transition_id") != rec["transition_id"]:
            continue
        if e.get("kind") == "quarantine-transfer-stage" and _TR_ORDER.get(e.get("stage"), -1) > rank:
            return "the transition record is behind its audit trail (rolled back or replayed)"
        if e.get("kind") == "quarantine-transfer-slot-consumed" and rec["s0_slot"]["state"] != "CONSUMED":
            return "the S0 slot was consumed per the audit trail but the record restores it (replayed)"
    return None


def _transition_bound_problem(cfg, rec, full=True):
    """Every admission re-authenticates the preserved bytes and the audit trail; a positive result is never cached."""
    if rec["new"]["code_sha256"] != CODE_SHA:
        try:
            ov = _recovery_load(cfg)
        except GateError as e:
            return f"the recovery record is invalid: {e}"
        if ov is None:
            return "the transition record binds different successor code"
        return _recovery_bound_problem(cfg, rec, ov, full)
    if os.path.lexists(_recovery_path(cfg)):
        return "a recovery record exists for different replacement runner code"
    bad = _transfer_pre_image_problem(cfg, rec, full)
    return bad or (_transition_replay_problem(cfg, rec) if full else None)


def _transition_mode(cfg):
    """(NONE|HOLD|LANE|ACTIVE, reason). NONE: no transfer lineage. HOLD: everything but stop/pause is closed.
    LANE: only the fixed S0 rebind write and its bound review. ACTIVE: ordinary live gates."""
    if not _transfer_lineage_active(cfg):
        return "NONE", None  # only the quarantined old runner itself
    try:
        rec = _load_transition(cfg)
    except GateError as e:
        return "HOLD", str(e)
    if rec is None:
        return "HOLD", "QUARANTINED: the verified transfer has not been consumed"
    bad = _transition_bound_problem(cfg, rec)
    if bad:
        return "HOLD", bad
    if not _transition_live(cfg, rec):
        return "HOLD", "the attested successor runner is not live (PID/boot nonce)"
    ov = _transition_overlay(cfg, rec)  # the recovery overlay's stage governs once replacement code is loaded
    if ov is not None:
        stage = ov["stage"]
        if stage in ("BOUND", "CORRECTION_CONSUMED"):
            return "RECOVERY", None
        return ("ACTIVE", None) if stage == "ACTIVE" else ("HOLD", f"recovery stage {stage} does not admit ingress")
    if rec["stage"] == "S0_REBIND":
        return "LANE", None
    if rec["stage"] == "ACTIVE":
        return "ACTIVE", None
    return "HOLD", f"transition stage {rec['stage']} does not admit ingress"


def _transition_quarantine_state(cfg, rec):
    bad = _transition_bound_problem(cfg, rec)
    if bad:
        return _QS_DENY, bad
    stage, live = rec["stage"], _transition_live(cfg, rec)
    ov = _transition_overlay(cfg, rec)
    att = ov["attested"] if ov else rec["attested"]
    if ov is not None:  # the overlay's stage governs: BOUND/CORRECTION_CONSUMED look like the open S0_REBIND window
        stage = "S0_REBIND" if ov["stage"] in ("BOUND", "CORRECTION_CONSUMED") else ov["stage"]
    if stage == "TRANSFER_CONSUMED":
        return _QS_DENY, "TRANSFER_CONSUMED: awaiting the provider CI observation; quarantine stays closed"
    if not live:
        return _QS_RESTARTED, "the attested successor runner is no longer live"
    if stage == "S0_REBIND":
        return _QS_ENTERED_LIVE, {"schema": 1, "entered_at": rec["created_at"], "runner_pid": att["pid"],
                                  "runner_boot_nonce": att["boot_nonce"], "code_sha256": CODE_SHA,
                                  "dual_rebind_consumed": rec["s0_slot"]["state"] == "CONSUMED",
                                  "transition_id": rec["transition_id"]}
    if stage == "VERIFIED":
        return _QS_DENY, "VERIFIED: awaiting read-only probes before ACTIVE"
    return _QS_ACTIVE, rec


def _transition_gate_reason(cfg, t, tasks):
    """None, or why the transfer lineage denies task t. D16 dual-version and S0 product are denied at every stage."""
    if not _transfer_lineage_active(cfg):
        return None
    parent = tasks.get((t.get("review_of") or {}).get("task_id")) if t.get("role") == "code-review" else None
    if t.get("id") == D16_DUAL_ID or d16_dual_lineage(tasks, t) or (isinstance(parent, dict) and d16_dual_lineage(tasks, parent)):
        return f"D16_DUAL_DENIED {t.get('id')}: the old D16 dual-version admission does not survive into the transfer lineage"
    if s0_marked(t):
        return f"S0_PRODUCT_DENIED {t.get('id')}: ACTIVE is operational only; S0 product admission stays refused"
    if t.get("id") == TRANSFER_REVIEW_ID:  # the single pre-consumption review-only bridge; admitted by nothing else
        return _transfer_review_gate(cfg, t, tasks)
    mode, why = _transition_mode(cfg)
    if mode == "HOLD":
        return f"TRANSFER_HOLD {t.get('id')}: {why}"
    if mode == "RECOVERY" and not (_recovery_marked(t) or (isinstance(parent, dict) and _recovery_marked(parent))):
        return f"TRANSFER_HOLD {t.get('id')}: only the one S0 recovery correction and its bound review are admitted before ACTIVE"
    if mode == "LANE" and not (s0_dual_rebind_marked(t) or (isinstance(parent, dict) and s0_dual_rebind_marked(parent))):
        return f"TRANSFER_HOLD {t.get('id')}: only the fixed S0 rebind lane is admitted before ACTIVE"
    return None


_TRANSFER_REVIEW_PROMPT = (
    "Independent read-only security review of the quarantine-transfer SUCCESSOR candidate (runner.py and test_runner.py). "
    "Judge only the runner-bound subject below against the effective owner records (B, A and D). Report CHANGES_REQUESTED for any fail-open "
    "path in the successor lineage, the single-use transfer, the review-only bridge or the S0/D16 gates, or if the subject "
    "does not match the bound hashes. You make no file changes and your verdict authorizes nothing else.")


def _transfer_review_task(cfg):
    return validate_task({"id": TRANSFER_REVIEW_ID, "module": S0_MODULE, "role": "code-review", "title": "successor transfer review",
                          "prompt": _TRANSFER_REVIEW_PROMPT, "allowed_paths": [], "expected_changes": [], "verify_cmd": []}, cfg)


def _transfer_review_gate(cfg, t, tasks):
    """None only for the exact runner-created, never-dispatched review task, in the first successor process, before any
    transition record exists. Every other task, every later state and every lookalike is held."""
    def deny(why):
        return f"TRANSFER_HOLD {t.get('id')}: {why}"
    if os.path.lexists(_transition_path(cfg)):
        return deny("a transition record exists: the review-only window is closed")
    if _transfer_first_boot(cfg, me=True) is None:
        return deny("not the first successor process: there is no pre-consumption review window or restart")
    want = _transfer_review_task(cfg)
    if not (all(t.get(k) == want[k] for k in ("id", "module", "role", "title", "prompt", "allowed_paths", "expected_changes",
                                               "verify_cmd", "review_of", "plan_phase"))
            and all(t.get(k) is None for k in ("source", "remediation_of", "review_retry_of", "review_candidate",
                                                "accounting_recovery_of", "doc_base"))):
        return deny("not the exact runner-created review task")
    if t.get("status") != "QUEUED" or t.get("attempts") != 0 or any(
            e.get("task_id") == TRANSFER_REVIEW_ID and e.get("kind") == "dispatch" for e in _qled_events(cfg)):
        return deny("the single review attempt is spent")
    if any(isinstance(x, dict) and x is not t and (x.get("status") == "RUNNING" or x.get("child")) for x in tasks.values()):
        return deny("another worker is running")
    _transfer_successor(cfg)  # raises GateError (held as GATE_UNVERIFIABLE) unless the exact successor is clean and committed
    return None


def _transition_audit(store, rec):
    """Audit events are subordinate: append the stage event iff the authoritative record reached it and it is absent."""
    try:
        have = {(e.get("transition_id"), e.get("stage")) for e in _qled_events(SimpleNamespace(home=store.home))
                if e.get("kind") == "quarantine-transfer-stage"}
        if (rec["transition_id"], rec["stage"]) not in have:
            store.event("quarantine-transfer-stage", transition_id=rec["transition_id"], stage=rec["stage"],
                        boot_epoch=rec["boot_epoch"], pre_image_digest=rec["pre_image"]["digest"])
    except OSError:
        pass  # the record, not the log, is authoritative; the next boot reconciles


def _ci_opener(*a, **k):
    return urllib.request.urlopen(*a, **k)


# --- verification of the S0 rebind outcome and the read-only probes before ACTIVE
def _transition_verified(cfg, rec, tasks):
    """The VERIFIED evidence when the S0 rebind outcome is fully evidenced; otherwise raises GateError (not yet)."""
    w = tasks.get(S0_DUAL_REBIND_ID)
    if not (isinstance(w, dict) and s0_dual_rebind_marked(w) and w.get("status") == "DONE" and w.get("attempts") == 1
            and (w.get("evidence") or {}).get("violations") == [] and s0_dual_rebind_shape_problem(w) is None):
        raise GateError("the fixed S0 rebind write is not DONE")
    changed = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if sorted(c["path"] for c in changed) != sorted(S0_DOC_PATHS) or any(c["sha256"] == w["doc_base"][c["path"]] for c in changed):
        raise GateError("the S0 rebind write did not change exactly the two documents")
    reviews = [x for x in tasks.values() if isinstance(x, dict) and (x.get("review_of") or {}).get("task_id") == w["id"]]
    if not (len(reviews) == 1 and reviews[0].get("status") == "DONE" and reviews[0].get("source") is None
            and _bound_review_ok(w, reviews[0]) and review_verdict(tasks, w["id"]) == "APPROVED"
            and (reviews[0].get("route") or {}).get("intended") == "opus"):
        raise GateError("the one exact-bound Opus review of the S0 rebind write is not APPROVED")
    docs = {c["path"]: c["sha256"] for c in changed}
    try:
        _s0_qa_git_clean(cfg, S0_DOC_PATHS, "S0 rebind publication")
        for path, sha in docs.items():
            if _s0_git_blob_sha(cfg, "HEAD", path, "S0 rebind publication") != sha or _path_hash(Path(cfg.repo) / path) != sha:
                raise GateError("the reviewed document bytes are not what HEAD publishes")
        head = _tgit(cfg, "rev-parse", "--verify", "HEAD").stdout.decode().strip()
        pub = _tgit(cfg, "diff", "--no-renames", "--name-only", rec["new"]["commit"], head)
        if (pub.returncode != 0 or sorted(pub.stdout.decode().split()) != sorted(S0_DOC_PATHS)
                or not _is_ancestor(cfg, rec["new"]["commit"])):
            raise GateError("the publication must change exactly the two S0 documents after the successor commit")
        _observe_ci_for_commit(cfg, head, opener=_ci_opener)
    except (GateError, OSError, subprocess.SubprocessError) as e:
        raise GateError(f"publication/CI is not verified: {str(e)[:120]}")
    rp = Path(cfg.home) / "acceptances" / f"{S0_DUAL_REBIND_RECEIPT}.json"
    try:
        rb = _read_bounded(rp, RECEIPT_MAX_BYTES)
        r = json.loads(rb.decode())
    except Exception:
        raise GateError("the new out-of-repo S0 rebind receipt is missing or unreadable")
    if not (isinstance(r, dict) and set(r) == {"schema", "kind", "transition_id", "runner_sha256", "documents", "recorded_at"}
            and r["schema"] == SCHEMA and r["kind"] == "mod004-s0-d16-rebind" and r["transition_id"] == rec["transition_id"]
            and r["runner_sha256"] == CODE_SHA and r["documents"] == docs and isinstance(r["recorded_at"], str)):
        raise GateError("the S0 rebind receipt does not bind the successor runner, transition and reviewed documents")
    # Historical receipts and reviews must be byte-for-byte what the pre-image preserved.
    try:
        pre = Path(cfg.home) / rec["pre_image"]["dir"]
        manifest = json.loads((pre / "manifest.json").read_text())
        now = _transfer_receipts(cfg)
        if any(now.get(n) != h for n, h in manifest["receipts"].items()):
            raise GateError("a historical receipt changed since the pre-image")
        old_tasks = json.loads((pre / "state.json").read_text())["tasks"]
        for tid, ot in old_tasks.items():
            nt = tasks.get(tid)
            if ot.get("role") == "code-review" and not (isinstance(nt, dict) and all(
                    nt.get(k) == ot.get(k) for k in ("status", "review_of", "route")) and
                    (nt.get("evidence") or {}).get("review_outcome") == (ot.get("evidence") or {}).get("review_outcome")):
                raise GateError("a historical review changed since the pre-image")
    except GateError:
        raise
    except Exception as e:
        raise GateError(f"historical preservation cannot be proven: {type(e).__name__}")
    return {"docs": docs, "receipt_sha256": _sha(rb), "commit": head}


def _transition_probe_problem(cfg, rec, tasks):
    """Positive and negative read-only probes before ACTIVE; None when all hold."""
    full = _transition_bound_problem(cfg, rec, full=True)
    if full:
        return full
    if not _transition_live(cfg, rec):
        return "positive probe: the attested runner is not live"
    base = {"module": S0_MODULE, "role": "implement", "status": "QUEUED", "attempts": 0, "allowed_paths": [],
            "expected_changes": [], "verify_cmd": [], "prompt": "probe", "title": "probe", "source": None}
    probes = ({**base, "id": D16_DUAL_ID}, {**base, "id": "transfer-probe-s0-product", "plan_phase": S0_MARKER})
    for p in probes:
        try:
            if gate_reason(cfg, p, tasks) is None:
                return f"negative probe: {p['id']} would be admitted"
        except Exception:
            continue  # an unverifiable gate is a refusal
    return None


# ------------------------------------------------ S0 rebind hash recovery overlay (2026-10-28)
# OWNER-2026-10-28-s0-rebind-hash-recovery.md: ONE separate, distinct, single-use recovery record (the overlay) cross-binds the
# immutable original transition record (never rewritten; its S0 slot stays CONSUMED and bound to the original task ID), the
# published owner record E, the replacement runner C (direct child of E), one new boot attestation and ONE new owner-CLI
# correction of the two S0 documents. Stages: BOUND -> CORRECTION_CONSUMED -> VERIFIED -> ACTIVE. Any inconsistency denies all ingress.
RECOVERY_OWNER_PATH = "knowledge/00-Decisions/OWNER-2026-10-28-s0-rebind-hash-recovery.md"
RECOVERY_OWNER_SHA = "e86906ed5d6ed21f58fbd4fcc354146082ac59c70847bf033fb5a410f52e63d3"
RECOVERY_OWNER_COMMIT = "be679d7480cdf9de068356c2d3f7a1376113a8a5"  # E: record-only, direct child of the original successor
RECOVERY_OWNER_CI_RUN = "40608546209"
RECOVERY_ORIG_COMMIT = "26708dab4cf230304067d08a516b4d7a2d9ccb34"  # the original successor (the transition record's new.commit)
RECOVERY_ORIG_CODE_SHA = "2e3efbc65894742c4575801a754a1c6d4d7e3bc4c245b5f532213d2383b9ac90"
RECOVERY_ORIG_DOCS = {"contracts/engineering/mod004-s0-eligibility.json": "2bb182644c5151db19a340c31ca7c8567fc3f8e3f884150d1f59418c22b6fc8a",
                      "contracts/engineering/mod004-s0-scenario-qa.md": "a146c060a175b62d80f6a2f830ca7d8f56a47a11ac7cbb9f9d5d93df3d527c6c"}
RECOVERY_ID = "mod004-s0-d16-rebind-hash-recovery-sonnet-20261028"
RECOVERY_MARKER = "MOD004-S0-D16-REBIND-HASH-RECOVERY"
RECOVERY_RECEIPT = "MOD-004-S0-D16-REBIND-RECOVERY"
RECOVERY_S0_RECEIPT = "MOD-004-S0-D16-REBIND-RECOVERY-S0"  # the fresh six-subject S0 receipt; MOD-004-S0 and MOD-004-S0-QA stay historical
RECOVERY_RECORD_NAME = "s0_d16_rebind_recovery.json"
RECOVERY_BOOT_NAME = "s0_d16_rebind_recovery_boot.json"  # the one reload window: created exclusively by the first replacement boot
RECOVERY_CHECKPOINT = "checkpoints/20261028-s0-rebind-hash-recovery"
RECOVERY_KIND = "s0-d16-rebind-hash-recovery"
RECOVERY_STAGES = ("BOUND", "CORRECTION_CONSUMED", "VERIFIED", "ACTIVE")
_RC_ORDER = {s: i for i, s in enumerate(RECOVERY_STAGES)}
_RC_KEYS = {"schema", "kind", "recovery_id", "stage", "created_at", "orig", "owner", "pre_image", "runner", "attested",
            "correction", "verified", "checksum"}
_RC_IMMUTABLE = ("schema", "kind", "recovery_id", "created_at", "orig", "owner", "pre_image", "runner", "attested")


def _recovery_marked(t):
    return t.get("plan_phase") == RECOVERY_MARKER or t.get("id") == RECOVERY_ID


def _recovery_path(cfg):
    return cfg.home / RECOVERY_RECORD_NAME


def _recovery_ci_validate(r, head, run_id=None):
    r = _tr_dict(r, _TR_CI_RUN_KEYS, "recovery ci run")
    if not (isinstance(r["run_id"], str) and r["run_id"].isdigit() and (run_id is None or r["run_id"] == run_id)
            and r["workflow"] == CI_WORKFLOW_NAME and r["event"] == "push" and r["branch"] == CI_BRANCH
            and r["head_sha"] == head and r["status"] == "completed" and r["conclusion"] == "success"):
        raise GateError("recovery record: a CI run is not a completed successful push run on main at the exact SHA")


def _recovery_validate(rec):
    """Strict schema and cross-field check; raises GateError so no caller sees an uncaught exception."""
    if not (isinstance(rec, dict) and set(rec) == _RC_KEYS):
        raise GateError("recovery record: unexpected or missing fields")
    if not (rec["schema"] == 1 and rec["kind"] == RECOVERY_KIND and _is_hex(rec["recovery_id"], 32)
            and rec["stage"] in _RC_ORDER and isinstance(rec["created_at"], str)):
        raise GateError("recovery record: header fields are invalid")
    o = _tr_dict(rec["orig"], ("transition_id", "checksum", "file_sha256", "task_id", "docs"), "orig")
    if not (_is_hex(o["transition_id"], 32) and _is_hex(o["checksum"], 64) and _is_hex(o["file_sha256"], 64)
            and o["task_id"] == S0_DUAL_REBIND_ID and o["docs"] == RECOVERY_ORIG_DOCS):
        raise GateError("recovery record: the original transition binding is invalid")
    ow = _tr_dict(rec["owner"], ("path", "sha256", "commit", "ci"), "owner")
    if not (ow["path"] == RECOVERY_OWNER_PATH and ow["sha256"] == RECOVERY_OWNER_SHA and ow["commit"] == RECOVERY_OWNER_COMMIT):
        raise GateError("recovery record: the owner record binding is invalid")
    _recovery_ci_validate(ow["ci"], RECOVERY_OWNER_COMMIT, RECOVERY_OWNER_CI_RUN)
    pi = _tr_dict(rec["pre_image"], ("dir", "digest", "manifest_sha256"), "pre_image")
    if not (isinstance(pi["dir"], str) and pi["dir"] and _is_hex(pi["digest"], 64) and _is_hex(pi["manifest_sha256"], 64)):
        raise GateError("recovery record: pre_image is invalid")
    rn = _tr_dict(rec["runner"], ("code_sha256", "commit", "parent", "test_sha256", "diff_sha256", "preload_sha256",
                                  "preload_output_sha256", "ci"), "runner")
    if not (_is_hex(rn["code_sha256"], 64) and rn["code_sha256"] != RECOVERY_ORIG_CODE_SHA and _is_hex(rn["commit"], 40)
            and rn["parent"] == RECOVERY_OWNER_COMMIT and all(_is_hex(rn[k], 64) for k in (
                "test_sha256", "diff_sha256", "preload_sha256", "preload_output_sha256"))):
        raise GateError("recovery record: the replacement runner binding is invalid")
    _recovery_ci_validate(rn["ci"], rn["commit"])
    at = _tr_dict(rec["attested"], ("pid", "boot_nonce", "code_sha256", "at"), "attested")
    if not (_is_int(at["pid"]) and at["pid"] > 0 and isinstance(at["boot_nonce"], str) and at["boot_nonce"]
            and at["code_sha256"] == rn["code_sha256"] and isinstance(at["at"], str)):
        raise GateError("recovery record: the attestation is invalid")
    cor = _tr_dict(rec["correction"], ("state", "task_id", "at"), "correction")
    ver = _tr_dict(rec["verified"], ("docs", "receipt_sha256", "commit", "at"), "verified")
    if cor["state"] == "UNUSED":
        if cor["task_id"] is not None or cor["at"] is not None:
            raise GateError("recovery record: an unused correction slot carries a task")
    elif not (cor["state"] == "CONSUMED" and cor["task_id"] == RECOVERY_ID and isinstance(cor["at"], str)):
        raise GateError("recovery record: the correction slot state is invalid")
    rank = _RC_ORDER[rec["stage"]]
    if (rank >= 1) != (cor["state"] == "CONSUMED"):
        raise GateError("recovery record: the stage and the correction slot disagree")
    if rank >= 2:
        if not (isinstance(ver["docs"], dict) and set(ver["docs"]) == set(S0_DOC_PATHS) and all(_is_hex(v, 64) for v in ver["docs"].values())
                and _is_hex(ver["receipt_sha256"], 64) and _is_hex(ver["commit"], 40) and isinstance(ver["at"], str)):
            raise GateError("recovery record: VERIFIED evidence is invalid")
    elif any(v is not None for v in ver.values()):
        raise GateError("recovery record: premature VERIFIED evidence")
    if rec["checksum"] != _transition_checksum(rec):
        raise GateError("recovery record: checksum mismatch (corrupt or tampered)")
    return rec


def _recovery_load(cfg):
    """None when no overlay exists; the validated overlay otherwise. Any problem raises GateError."""
    path = _recovery_path(cfg)
    if not os.path.lexists(path):
        return None
    try:
        rec = json.loads(_read_bounded(path, 1 << 20).decode())
    except GateError:
        raise
    except Exception:
        raise GateError("recovery record is unreadable or not valid JSON")
    return _recovery_validate(rec)


def _recovery_write(cfg, rec, create=False):
    """The only writer of the overlay: validated, monotonic, atomic and fsynced. It never touches the original record."""
    rec = {k: v for k, v in rec.items() if k != "checksum"}
    rec["checksum"] = _transition_checksum(rec)
    _recovery_validate(rec)
    data = json.dumps(rec, sort_keys=True, indent=1).encode()
    if create:
        _atomic_create_exclusive(_recovery_path(cfg), data)
        return rec
    cur = _recovery_load(cfg)
    if cur is None:
        raise GateError("recovery record is absent")
    for k in _RC_IMMUTABLE:
        if cur[k] != rec[k]:
            raise GateError(f"recovery record: immutable field {k} may not change")
    a, b = _RC_ORDER[cur["stage"]], _RC_ORDER[rec["stage"]]
    if not a <= b <= a + 1:
        raise GateError("recovery record: stages only advance one step at a time")
    if cur["correction"]["state"] == "CONSUMED" and rec["correction"] != cur["correction"]:
        raise GateError("recovery record: a consumed correction slot cannot be restored")
    if cur["verified"]["docs"] is not None and rec["verified"] != cur["verified"]:
        raise GateError("recovery record: VERIFIED evidence is immutable")
    atomic_write(_recovery_path(cfg), data)
    return rec


def _recovery_diff(cfg, commit):
    """THE canonical E-to-C diff bytes of the replacement runner and its focused test (the review subject)."""
    p = _tgit(cfg, "diff", "--binary", "--no-ext-diff", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/",
              RECOVERY_OWNER_COMMIT, commit, "--", S0_RUNNER_FILE, TRANSFER_TEST_FILE)
    if p.returncode != 0:
        raise GateError("cannot compute the replacement runner diff")
    return p.stdout


def _recovery_tree_problem(cfg, docs):
    """None when the ONLY dirty paths are exactly `docs` (modified, unstaged, tracked, with exactly those bytes)."""
    st = _tgit(cfg, "--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames")
    cached = _tgit(cfg, "diff", "--cached", "--name-only", "-z")
    flags = _tgit(cfg, "ls-files", "-v", "--", *docs) if docs else None
    if st.returncode != 0 or cached.returncode != 0 or (flags is not None and flags.returncode != 0):
        return "cannot read the working-tree state"
    got = sorted(e.decode("utf-8", "surrogateescape") for e in st.stdout.split(b"\0") if e)
    if got != sorted(f" M {p}" for p in docs) or cached.stdout != b"":
        return "the working tree is not exactly the pinned unstaged document paths"
    if flags is not None and [ln[:2] for ln in flags.stdout.decode("utf-8", "replace").splitlines()] != ["H "] * len(docs):
        return "a pinned document is not an ordinary tracked path"
    try:
        if any(_path_hash(Path(cfg.repo) / p) != h for p, h in docs.items()):
            return "a pinned document differs from its recorded bytes"
    except OSError:
        return "a pinned document cannot be read"
    return None


@_tr_memoized
def _recovery_successor(cfg):
    """Deterministic local binding of the loaded replacement runner C to E -> C (direct, single-parent raw Git objects; the
    changed-path sets are checked separately and unfiltered). The two documents may be dirty; nothing else may be."""
    runner_p, test_p = Path(cfg.repo) / S0_RUNNER_FILE, Path(cfg.repo) / TRANSFER_TEST_FILE
    runner_b, test_b = _transfer_read(runner_p, "replacement runner.py"), _transfer_read(test_p, "replacement test_runner.py")
    if not (_sha(runner_b) == CODE_SHA == _LOADED_CODE_SHA):
        raise GateError("on-disk runner.py differs from the loaded replacement code (stale disk)")
    _transfer_no_replacements(cfg)
    head = _tgit(cfg, "rev-parse", "--verify", "HEAD")
    head = head.stdout.decode().strip() if head.returncode == 0 else ""
    _tree, parents = _transfer_commit(cfg, head)
    if parents != [RECOVERY_OWNER_COMMIT]:
        raise GateError("the replacement commit C is not a direct, single-parent child of the owner-record commit E")
    _tree_e, parents_e = _transfer_commit(cfg, RECOVERY_OWNER_COMMIT)
    if parents_e != [RECOVERY_ORIG_COMMIT]:
        raise GateError("the owner-record commit E is not a direct, single-parent child of the original successor")
    if _transfer_changed(cfg, RECOVERY_ORIG_COMMIT, RECOVERY_OWNER_COMMIT) != [RECOVERY_OWNER_PATH]:
        raise GateError("the owner-record commit E must change exactly its owner record")
    owner = _transfer_blob(cfg, RECOVERY_OWNER_COMMIT, RECOVERY_OWNER_PATH)
    if _sha(owner) != RECOVERY_OWNER_SHA or _transfer_blob(cfg, head, RECOVERY_OWNER_PATH) != owner:
        raise GateError("the recovery owner record is not the pinned, unchanged published record")
    if _sha(_transfer_blob(cfg, head, S0_RUNNER_FILE)) != CODE_SHA:
        raise GateError("the committed runner.py blob is not the loaded replacement code")
    if _sha(_transfer_blob(cfg, head, TRANSFER_TEST_FILE)) != _sha(test_b):
        raise GateError("the committed test blob differs from the on-disk test file")
    if _transfer_changed(cfg, RECOVERY_OWNER_COMMIT, head) != sorted([S0_RUNNER_FILE, TRANSFER_TEST_FILE]):
        raise GateError("the replacement commit must change exactly runner.py and test_runner.py")
    return {"commit": head, "parent": RECOVERY_OWNER_COMMIT, "code_sha256": CODE_SHA, "test_sha256": _sha(test_b),
            "diff_sha256": _sha(_recovery_diff(cfg, head))}


def _recovery_preload(cfg, successor):
    base = Path(cfg.home) / RECOVERY_CHECKPOINT
    raw = _transfer_read(base / TRANSFER_PRELOAD_NAME, "recovery Opus review evidence", 1 << 20)
    try:
        d = json.loads(raw.decode())
        name = d["output_file"]
    except Exception:
        raise GateError("recovery Opus review evidence is not valid JSON")
    if not (isinstance(name, str) and name == Path(name).name and name not in ("", ".", "..")):
        raise GateError("recovery Opus review output_file must be a plain file name")
    if not (isinstance(d.get("c_ci_run_id"), str) and d["c_ci_run_id"].isdigit()):
        raise GateError("recovery Opus review evidence must pin the replacement runner's CI run ID")
    out = _transfer_read(base / name, "recovery Opus review output", 8 * 1024 * 1024)
    return _transfer_preload_bind(raw, out, successor), d["c_ci_run_id"], {"preload.json": raw, "preload.out": out}


def _recovery_orig_task_problem(tasks):
    """The original consumed task is untouched: DONE, one attempt, no violations, the recorded two document hashes."""
    w = tasks.get(S0_DUAL_REBIND_ID)
    if not (isinstance(w, dict) and s0_dual_rebind_marked(w) and w.get("status") == "DONE" and w.get("attempts") == 1
            and (w.get("evidence") or {}).get("violations") == [] and s0_dual_rebind_shape_problem(w) is None
            and _changed_pairs((w.get("evidence") or {}).get("changed")) == _changed_pairs(
                [{"path": p, "sha256": h} for p, h in RECOVERY_ORIG_DOCS.items()])):
        return "the original S0 rebind task is not the DONE one-attempt task with the pinned document hashes"
    return None


def _recovery_orig_problem(cfg, rec, ov):
    o = ov["orig"]
    try:
        raw = _read_bounded(_transition_path(cfg), 1 << 20)
    except GateError:
        return "the original transition record is unreadable"
    if not (rec["transition_id"] == o["transition_id"] and rec["checksum"] == o["checksum"] and _sha(raw) == o["file_sha256"]):
        return "the original transition record differs from what the recovery record binds"
    if not (rec["stage"] == "S0_REBIND" and rec["s0_slot"]["state"] == "CONSUMED" and rec["s0_slot"]["task_id"] == o["task_id"]
            and rec["new"]["commit"] == RECOVERY_ORIG_COMMIT and rec["new"]["code_sha256"] == RECOVERY_ORIG_CODE_SHA):
        return "the original transition is not the pinned consumed S0_REBIND record"
    return None


@_tr_memoized
def _recovery_runner_problem(cfg, ov, full):
    rn = ov["runner"]
    try:
        if not (rn["code_sha256"] == CODE_SHA == _LOADED_CODE_SHA):
            return "the recovery record binds different replacement runner code"
        if _sha(_transfer_read(Path(cfg.repo) / S0_RUNNER_FILE, "runner.py")) != CODE_SHA:
            return "on-disk runner.py differs from the loaded replacement code"
        if not full:
            return None
        c = rn["commit"]
        if _transfer_commit(cfg, c)[1] != [RECOVERY_OWNER_COMMIT]:
            return "the replacement commit is not a direct child of the owner-record commit"
        if _transfer_changed(cfg, RECOVERY_OWNER_COMMIT, c) != sorted([S0_RUNNER_FILE, TRANSFER_TEST_FILE]):
            return "the replacement commit changes more than runner.py and test_runner.py"
        if _sha(_transfer_blob(cfg, c, S0_RUNNER_FILE)) != CODE_SHA or _sha(_transfer_blob(cfg, c, TRANSFER_TEST_FILE)) != rn["test_sha256"]:
            return "the committed replacement blobs differ from the recorded hashes"
        if _sha(_recovery_diff(cfg, c)) != rn["diff_sha256"]:
            return "the replacement diff differs from the reviewed subject"
        owner = _transfer_blob(cfg, RECOVERY_OWNER_COMMIT, RECOVERY_OWNER_PATH)
        if _sha(owner) != RECOVERY_OWNER_SHA or _transfer_blob(cfg, c, RECOVERY_OWNER_PATH) != owner:
            return "the recovery owner record changed"
        if not _is_ancestor(cfg, c):
            return "the replacement commit is not an ancestor of HEAD"
    except GateError as e:
        return str(e)
    return None


def _recovery_pre_image_problem(cfg, ov, full):
    pi = ov["pre_image"]
    d = Path(cfg.home) / pi["dir"]
    if ".." in Path(pi["dir"]).parts or Path(pi["dir"]).is_absolute() or not d.is_dir() or d.is_symlink():
        return "recovery pre-image directory is missing"
    try:
        mb = _read_bounded(d / "manifest.json", 8 * 1024 * 1024)
        if _sha(mb) != pi["manifest_sha256"]:
            return "recovery pre-image manifest differs from the record"
        m = json.loads(mb.decode())
        if m.get("digest") != pi["digest"] or m.get("transition_id") != ov["recovery_id"]:
            return "recovery pre-image manifest binds a different recovery"
        if full:
            for n, e in m["files"].items():
                if _sha(_read_bounded(d / n, 64 * 1024 * 1024)) != e["sha256"]:
                    return f"recovery pre-image file {n} was altered"
            if m["files"][TRANSFER_RECORD_NAME]["sha256"] != ov["orig"]["file_sha256"]:
                return "recovery pre-image does not hold the original transition record bytes"
    except Exception as e:
        return f"recovery pre-image is unreadable: {type(e).__name__}"
    return None


def _recovery_replay_problem(cfg, ov):
    """Audit events are only appended AFTER the overlay reaches a stage, so an overlay that trails its own audit trail was rolled
    back or replayed (even with a valid earlier checksum). Fail-closed only: events never grant anything."""
    rank = _RC_ORDER[ov["stage"]]
    for e in _qled_events(cfg):
        if e.get("kind") == "quarantine-recovery-stage" and e.get("recovery_id") == ov["recovery_id"] and _RC_ORDER.get(e.get("stage"), -1) > rank:
            return "the recovery record is behind its audit trail (rolled back or replayed)"
        if (e.get("kind") == "dispatch" and e.get("task_id") == RECOVERY_ID) and ov["correction"]["state"] != "CONSUMED":
            return "the correction was dispatched per the audit trail but the record restores its slot (replayed)"
    return None


def _recovery_bound_problem(cfg, rec, ov, full=True):
    """Every admission re-authenticates the original record, the replacement runner and the preserved bytes; never cached."""
    try:
        return (_recovery_orig_problem(cfg, rec, ov) or _recovery_runner_problem(cfg, ov, full)
                or _transfer_pre_image_problem(cfg, rec, full) or _recovery_pre_image_problem(cfg, ov, full)
                or (_transition_replay_problem(cfg, rec) or _recovery_replay_problem(cfg, ov) if full else None))
    except (GateError, OSError) as e:
        return f"recovery binding cannot be verified: {str(e)[:200]}"


def _transition_overlay(cfg, rec):
    """The recovery overlay governing record `rec` (replacement code loaded), else None. Raises GateError if it is invalid."""
    return _recovery_load(cfg) if rec["new"]["code_sha256"] != CODE_SHA else None


def _recovery_write_pre_image(cfg, rid, rec, docs, files):
    """Out-of-repo byte-for-byte pre-image of state, events, receipts, the original record and the two pinned documents."""
    root = Path(cfg.home) / RECOVERY_CHECKPOINT
    final, tmp = root / f"pre-image-{rid}", root / f".pre-image-{rid}.tmp"
    if final.exists() or tmp.exists():
        raise GateError("recovery pre-image directory already exists")
    root.mkdir(parents=True, exist_ok=True)
    home = Path(cfg.home)
    allf = {"state.json": _transfer_read(home / "state.json", "state.json"),
            "events.jsonl": _transfer_read(home / "events.jsonl", "events log", 32 * 1024 * 1024),
            TRANSFER_RECORD_NAME: _transfer_read(_transition_path(cfg), "original transition record"),
            "doc-0": docs[0], "doc-1": docs[1], **files}
    receipts = _transfer_receipts(cfg)
    for rel in receipts:
        allf["receipts/" + rel] = (home / "acceptances" / rel).read_bytes()
    digest = _sha(_canon({"orig": rec["checksum"], "docs": RECOVERY_ORIG_DOCS}))
    manifest = {"transition_id": rid, "digest": digest,
                "files": {n: {"sha256": _sha(b), "size": len(b)} for n, b in sorted(allf.items())}, "receipts": receipts}
    tmp.mkdir(mode=0o700)
    for n, b in list(allf.items()) + [("manifest.json", json.dumps(manifest, sort_keys=True, indent=1).encode())]:
        p = tmp / n
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, b)
            os.fsync(fd)
        finally:
            os.close(fd)
    for d in {p.parent for p in tmp.rglob("*") if p.is_file()} | {tmp}:
        fsync_dir(d)
    os.rename(tmp, final)
    fsync_dir(root)
    return {"dir": str(final.relative_to(home)), "digest": digest,
            "manifest_sha256": _sha((final / "manifest.json").read_bytes())}


def _recovery_first_boot(cfg, me=False):
    """The first-replacement-boot marker (the one reload window), or None. `me` also requires that THIS process created it."""
    try:
        d = json.loads(_read_bounded(Path(cfg.home) / RECOVERY_BOOT_NAME, 1 << 16).decode())
    except Exception:
        return None
    if not (isinstance(d, dict) and set(d) == _TR_BOOT_KEYS and d["schema"] == 1 and d["kind"] == "s0-d16-rebind-recovery-first-boot"
            and _is_int(d["pid"]) and d["pid"] > 0 and isinstance(d["boot_nonce"], str) and d["boot_nonce"]
            and d["code_sha256"] == CODE_SHA):
        return None
    return d if not me or (d["pid"] == os.getpid() and d["boot_nonce"] == _PROCESS_BOOT_NONCE) else None


def recovery_preflight(cfg, state, rlock_held=False, wlock_held=False):
    """Deterministic local preflight for creating the overlay. Raises GateError on anything but the exact pinned incident.
    Provider CI is observed by the caller; this never consults the network and writes nothing."""
    rec = _load_transition(cfg)
    if rec is None or rec["new"]["code_sha256"] == CODE_SHA or CODE_SHA == RECOVERY_ORIG_CODE_SHA:
        raise GateError("the original transition does not bind different, older runner code")
    if _recovery_load(cfg) is not None or any(e.get("kind") == "quarantine-recovery-stage" for e in _qled_events(cfg)):
        raise GateError("a recovery record already exists or was minted; the recovery is never minted twice")
    stub = {"orig": {"transition_id": rec["transition_id"], "checksum": rec["checksum"],
                     "file_sha256": _sha(_read_bounded(_transition_path(cfg), 1 << 20)), "task_id": S0_DUAL_REBIND_ID,
                     "docs": dict(RECOVERY_ORIG_DOCS)}}
    bad = _recovery_orig_problem(cfg, rec, stub) or _transfer_pre_image_problem(cfg, rec, True) or _transition_replay_problem(cfg, rec)
    if bad:
        raise GateError(bad)
    att = rec["attested"]
    if (att["pid"], att["boot_nonce"]) == (os.getpid(), _PROCESS_BOOT_NONCE) or (att["pid"] != os.getpid() and pid_alive(att["pid"])):
        raise GateError("the original attested runner is still alive or is this process")
    tasks = (state or {}).get("tasks")
    if not isinstance(tasks, dict):
        raise GateError("no task state")
    bad = _recovery_orig_task_problem(tasks)
    if bad:
        raise GateError(bad)
    if any(isinstance(x, dict) and (_recovery_marked(x) or (x.get("review_of") or {}).get("task_id") == RECOVERY_ID) for x in tasks.values()):
        raise GateError("a recovery task or review already exists")
    for d in ("queue", "commands"):
        base = Path(cfg.home) / d
        if base.is_dir() and any(RECOVERY_ID.encode() in p.read_bytes() for p in base.iterdir() if p.is_file()):
            raise GateError("the recovery correction ID is already queued")
    h = (state or {}).get("handoff") or {}
    if h.get("request") or h.get("quarantine"):
        raise GateError("an orchestrator handoff or gateway turn is open")
    if any(isinstance(t, dict) and (t.get("status") == "RUNNING" or t.get("child") or t.get("stage") == "verify_pending")
           for t in tasks.values()):
        raise GateError("a worker task is running or a verification is pending")
    if _other_runner_pids(cfg):
        raise GateError("another runner process exists")
    if not rlock_held and FileLock.probe(Path(cfg.home) / "locks" / "runner.lock") == "free":
        raise GateError("the sole runner lock is not held by the replacement")
    if not wlock_held and FileLock.probe(writer_lock_path(cfg.home, cfg.repo)) != "free":
        raise GateError("the repository writer lock is held")
    successor = _recovery_successor(cfg)
    bad = _recovery_tree_problem(cfg, RECOVERY_ORIG_DOCS)
    if bad:
        raise GateError(bad)
    preload, c_run, pfiles = _recovery_preload(cfg, successor)
    return {"rec": rec, "successor": successor, "preload": preload, "c_run": c_run, "preload_files": pfiles, "stub": stub}


# --- gate: the one separately identified correction and its single bound review
def _recovery_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the recovery correction is a MOD-004 implement task only"
    if t.get("source") is not None:
        return "the recovery correction is owner-CLI only"
    if t.get("id") != RECOVERY_ID or t.get("plan_phase") != RECOVERY_MARKER:
        return f"id must be {RECOVERY_ID} with plan_phase {RECOVERY_MARKER}"
    if any(t.get(k) is not None for k in ("remediation_of", "review_retry_of", "accounting_recovery_of", "review_of", "review_candidate")):
        return "remediation, retry, accounting-recovery and review fields are rejected"
    if sorted(t.get("allowed_paths") or []) != sorted(S0_DOC_PATHS) or t.get("expected_changes") != [S0_DOC_PATHS[0]]:
        return "allowed_paths must be exactly the two S0 documents and expected_changes exactly the certificate"
    if t.get("verify_cmd") != []:
        return "the recovery correction runs no verifier"
    if t.get("doc_base") != RECOVERY_ORIG_DOCS:
        return "doc_base must be exactly the original task's two recorded document hashes"
    return None


def recovery_gate_reason(cfg, t, tasks):
    """None outside the lane or for the one fully authorised correction; else an explicit S0_RECOVERY_* reason."""
    if not _recovery_marked(t):
        return None
    problem = _recovery_shape_problem(t)
    if problem:
        return f"S0_RECOVERY_INVALID_TASK {t['id']}: {problem}"
    mode, why = _transition_mode(cfg)
    if mode == "ACTIVE":
        return "S0_RECOVERY_CLOSED: the recovery is ACTIVE; the correction lane is spent"
    if mode != "RECOVERY":
        return f"S0_RECOVERY_NOT_ADMITTED: {why or mode}"
    try:
        ov = _recovery_load(cfg)
    except GateError as e:
        return f"S0_RECOVERY_UNVERIFIABLE: {e}"
    if ov is None or ov["stage"] != "BOUND" or ov["correction"]["state"] != "UNUSED":
        return "S0_RECOVERY_CONSUMED: the single correction attempt was already started or consumed"
    if t.get("attempts") or t.get("status", "QUEUED") != "QUEUED":
        return f"S0_RECOVERY_ATTEMPT_USED {t['id']}: the single correction attempt was already started"
    others = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                    and _recovery_marked(x) and x.get("role") in WRITE_ROLES)
    if others:
        return f"S0_RECOVERY_SECOND_WRITE: correction {others[0]} already exists; the lane is one-shot"
    busy = _s0_competing_writes(tasks, t)
    if busy:
        return f"S0_RECOVERY_CONCURRENT_WRITE: {busy[0]} is a pending write in an S0 chain or touching S0 files"
    problem = _recovery_orig_task_problem(tasks)
    if problem:
        return f"S0_RECOVERY_ORIGINAL_CHANGED: {problem}"
    try:
        bad = _recovery_tree_problem(cfg, RECOVERY_ORIG_DOCS)
        head = _tgit(cfg, "rev-parse", "--verify", "HEAD").stdout.decode().strip()
    except GateError as e:
        return f"S0_RECOVERY_STALE_BASE: {e}"
    if bad or head != ov["runner"]["commit"]:
        return f"S0_RECOVERY_STALE_BASE: {bad or 'HEAD is not the bound replacement runner commit'}"
    return None


def recovery_review_reason(cfg, t, tasks):
    """The one exact-bound owner-CLI Opus review of the DONE correction; it must cover BOTH final document paths and hashes."""
    w = tasks.get((t.get("review_of") or {}).get("task_id"))
    if not (w and _recovery_marked(w)):
        return None
    if t.get("source") is not None:
        return "S0_RECOVERY_REVIEW_UNSUPPORTED: the recovery review is owner-CLI routed only"
    if t.get("review_retry_of") or t.get("review_candidate"):
        return "S0_RECOVERY_REVIEW_UNSUPPORTED: the correction gets one bound review and no retry"
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement" and w.get("status") == "DONE"
            and w.get("attempts") == 1 and (w.get("evidence") or {}).get("violations") == []):
        return "S0_RECOVERY_REVIEW_UNSUPPORTED: only the DONE one-attempt recovery correction can be reviewed here"
    problem = _recovery_shape_problem(w)
    if problem:
        return f"S0_RECOVERY_REVIEW_UNSUPPORTED: {problem}"
    want = _changed_pairs(_review_want(w))
    ch = {c["path"]: c["sha256"] for c in _changed_pairs((w.get("evidence") or {}).get("changed"))}
    if not (sorted(c["path"] for c in want) == sorted(S0_DOC_PATHS) and list(ch) == [S0_DOC_PATHS[0]]
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) for c in want)
            and ch[S0_DOC_PATHS[0]] != RECOVERY_ORIG_DOCS[S0_DOC_PATHS[0]]
            and _changed_pairs((t.get("review_of") or {}).get("changed")) == want):
        return "S0_RECOVERY_REVIEW_UNSUPPORTED: review must bind the exact final hashes of BOTH documents"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_RECOVERY_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review the correction"
    if not _hashes_current(cfg, want):
        return "S0_RECOVERY_REVIEW_BINDING_STALE: the documents no longer match the correction's recorded hashes"
    try:
        ov = _recovery_load(cfg)
    except GateError as e:
        return f"S0_RECOVERY_REVIEW_UNVERIFIABLE: {e}"
    if _transition_mode(cfg)[0] != "RECOVERY" or ov is None or ov["stage"] != "CORRECTION_CONSUMED" or ov["correction"]["task_id"] != w["id"]:
        return "S0_RECOVERY_REVIEW_UNSUPPORTED: the recovery record does not hold the consumed correction"
    return None


def recovery_note(packet_sha):
    """The ONE sha256_note the corrected certificate may carry: derived solely from the actual packet hash, so the allowed field
    cannot smuggle any other claim (PASS, waiver, acceptance)."""
    return (f"SHA-256 {packet_sha} is computed from the exact S0 QA evidence-candidate packet bytes; "
            "this hash alone grants no S0 product or module acceptance.")


def _recovery_cert_problem(base, cur, packet):
    """The corrected certificate may differ from the PINNED ORIGINAL bytes in exactly three values, each derived from authenticated
    facts, never from the writer: scenario_qa_packet.sha256 (the actual packet), the deterministic scenario_qa_packet.sha256_note
    (recovery_note), and the
    top-level runner_gate.sha256 (the loaded replacement runner). Everything else, including every nested historical observation,
    scenario/PASS/acceptance statement and security or eligibility field, must be equal. Compared as canonical JSON, so a type
    change such as 1 -> true is a difference."""
    try:
        want, got = _s0_json(base, "S0 original certificate"), _s0_json(cur, "S0 corrected certificate")
    except GateError as e:
        return str(e)
    bp, gp, brg, grg = want.get("scenario_qa_packet"), got.get("scenario_qa_packet"), want.get("runner_gate"), got.get("runner_gate")
    packet_sha = hashlib.sha256(packet).hexdigest()
    if not (isinstance(bp, dict) and isinstance(gp, dict) and gp.get("sha256") == packet_sha and set(gp) == set(bp) | {"sha256_note"}
            and gp.get("sha256_note") == recovery_note(packet_sha)):
        return "the certificate must bind the exact packet sha256 with exactly the deterministic sha256_note derived from it"
    if not (isinstance(brg, dict) and isinstance(grg, dict) and set(brg) == set(grg) == {"path", "sha256"}
            and grg == {"path": S0_RUNNER_FILE, "sha256": CODE_SHA} and brg.get("path") == S0_RUNNER_FILE):
        return "the certificate runner_gate must name exactly the loaded replacement runner"
    bp["sha256"], bp["sha256_note"], brg["sha256"] = gp["sha256"], gp["sha256_note"], grg["sha256"]
    if _canon(want) != _canon(got):
        return "the certificate differs from the pinned original beyond the packet sha256, its note and runner_gate.sha256"
    return None


def _recovery_result_problem(cfg, tasks, changed):
    """Post-run check of the correction: ONLY the certificate changed, the packet is byte-identical, the certificate names the
    exact packet hash and the loaded replacement runner, and neither the overlay nor the original record moved."""
    cert_p, qa_p = S0_DOC_PATHS
    if changed != [cert_p]:
        return "the correction must change exactly the certificate"
    if _path_hash(Path(cfg.repo) / qa_p) != RECOVERY_ORIG_DOCS[qa_p]:
        return "the scenario/QA packet is not byte-identical to the original task's recorded bytes"
    problem = _s0_rebind_packet_problem(cfg)
    if problem:
        return problem
    rec, ov = _load_transition(cfg), _recovery_load(cfg)
    if ov is None:
        return "the recovery record is absent"
    base = _read_bounded(Path(cfg.home) / ov["pre_image"]["dir"] / "doc-0", REVIEW_MAX_BYTES)  # preserved ORIGINAL certificate bytes
    if _sha(base) != RECOVERY_ORIG_DOCS[cert_p]:
        return "the preserved original certificate is not the pinned bytes"
    problem = _recovery_cert_problem(base, _read_bounded(Path(cfg.repo) / cert_p, REVIEW_MAX_BYTES),
                                     _read_bounded(Path(cfg.repo) / qa_p, REVIEW_MAX_BYTES))
    if problem:
        return problem
    if rec is None or _recovery_bound_problem(cfg, rec, ov, full=True) or _recovery_orig_task_problem(tasks):
        return "the original transition, its task or the recovery binding changed"
    if ov["stage"] != "CORRECTION_CONSUMED":
        return "the correction slot is not the consumed one"
    return None


# --- verification of the recovery outcome and the read-only probes before ACTIVE
def _recovery_verified(cfg, rec, ov, tasks):
    """The VERIFIED evidence when the corrected pair is fully reviewed, published, CI-green and receipted; else GateError."""
    w = tasks.get(RECOVERY_ID)
    if not (isinstance(w, dict) and _recovery_marked(w) and w.get("status") == "DONE" and w.get("attempts") == 1
            and (w.get("evidence") or {}).get("violations") == [] and _recovery_shape_problem(w) is None
            and ov["correction"]["task_id"] == w["id"]):
        raise GateError("the recovery correction is not DONE")
    cert_p, qa_p = S0_DOC_PATHS
    changed = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if [c["path"] for c in changed] != [cert_p] or changed[0]["sha256"] == RECOVERY_ORIG_DOCS[cert_p]:
        raise GateError("the recovery correction did not change exactly the certificate")
    docs = {cert_p: changed[0]["sha256"], qa_p: RECOVERY_ORIG_DOCS[qa_p]}
    reviews = [x for x in tasks.values() if isinstance(x, dict) and (x.get("review_of") or {}).get("task_id") == w["id"]]
    if not (len(reviews) == 1 and reviews[0].get("status") == "DONE" and reviews[0].get("source") is None
            and _bound_review_ok(w, reviews[0]) and review_verdict(tasks, w["id"]) == "APPROVED"
            and (reviews[0].get("route") or {}).get("intended") == "opus"
            and _changed_pairs((reviews[0].get("review_of") or {}).get("changed")) == _changed_pairs(
                [{"path": p, "sha256": h} for p, h in docs.items()])):
        raise GateError("the one exact-bound Opus review of BOTH final documents is not APPROVED")
    try:
        bad = _recovery_tree_problem(cfg, {})
        if bad:
            raise GateError(bad)
        for path, sha in docs.items():
            if _s0_git_blob_sha(cfg, "HEAD", path, "recovery publication") != sha or _path_hash(Path(cfg.repo) / path) != sha:
                raise GateError("the reviewed document bytes are not what HEAD publishes")
        head = _tgit(cfg, "rev-parse", "--verify", "HEAD").stdout.decode().strip()
        if (_transfer_commit(cfg, head)[1] != [ov["runner"]["commit"]]
                or _transfer_changed(cfg, ov["runner"]["commit"], head) != sorted(S0_DOC_PATHS)):
            raise GateError("the publication P must be a direct child of C changing exactly both S0 documents")
        problem = _s0_rebind_packet_problem(cfg, docs)
        if problem:
            raise GateError(problem)
        base = _read_bounded(Path(cfg.home) / ov["pre_image"]["dir"] / "doc-0", REVIEW_MAX_BYTES)
        if _sha(base) != RECOVERY_ORIG_DOCS[cert_p]:
            raise GateError("the preserved original certificate is not the pinned bytes")
        problem = _recovery_cert_problem(base, _s0_git_blob(cfg, head, cert_p, "recovery publication"),
                                         _s0_git_blob(cfg, head, qa_p, "recovery publication"))
        if problem:
            raise GateError(problem)
        _observe_ci_for_commit(cfg, head, opener=_ci_opener)
    except (GateError, OSError, subprocess.SubprocessError) as e:
        raise GateError(f"publication/CI is not verified: {str(e)[:120]}")
    pre = Path(cfg.home) / ov["pre_image"]["dir"]
    try:
        rb = _read_bounded(Path(cfg.home) / "acceptances" / f"{RECOVERY_RECEIPT}.json", RECEIPT_MAX_BYTES)
        r = json.loads(rb.decode())
        manifest = json.loads((pre / "manifest.json").read_text())
    except Exception:
        raise GateError("the recovery receipt or the recovery pre-image is missing or unreadable")
    if f"{RECOVERY_RECEIPT}.json" in manifest["receipts"]:
        raise GateError("the recovery receipt is not new")
    if not (isinstance(r, dict) and set(r) == {"schema", "kind", "recovery_id", "transition_id", "runner_sha256", "documents",
                                                 "commit", "s0_receipt", "recorded_at"}
            and r["schema"] == SCHEMA and r["kind"] == "mod004-s0-d16-rebind-recovery" and r["recovery_id"] == ov["recovery_id"]
            and r["transition_id"] == rec["transition_id"] and r["runner_sha256"] == CODE_SHA and r["documents"] == docs
            and r["commit"] == head and isinstance(r["recorded_at"], str)):
        raise GateError("the recovery receipt does not bind the replacement runner, transition and reviewed documents")
    s0name = f"{RECOVERY_S0_RECEIPT}.json"
    if s0name in manifest["receipts"]:
        raise GateError("the fresh S0 receipt is not new")
    try:
        s0b = _read_bounded(Path(cfg.home) / "acceptances" / s0name, RECEIPT_MAX_BYTES)
    except GateError:
        raise GateError("the fresh six-subject S0 receipt is missing")
    if r["s0_receipt"] != {"name": RECOVERY_S0_RECEIPT, "sha256": _sha(s0b)}:
        raise GateError("the recovery receipt does not bind the exact fresh S0 receipt bytes")
    try:  # the established S0 predicate: per-subject CI, ancestry, committed bytes, runner-recorded Opus review and content checks
        verify_s0_authority(cfg, tasks, receipt=RECOVERY_S0_RECEIPT, runner_check=lambda e: _recovery_runner_subject(cfg, ov, e))
        sub = _s0_json(s0b, "fresh S0 receipt")["subjects"]
        if not (sub["eligibility"]["path"] == cert_p and sub["eligibility"]["sha256"] == docs[cert_p] and sub["eligibility"]["commit"] == head):
            raise GateError("the fresh S0 eligibility subject is not the final certificate published at P")
    except (GateError, OSError, subprocess.SubprocessError) as e:
        raise GateError(f"the fresh S0 receipt does not verify: {str(e)[:160]}")
    try:  # historical receipts, reviews and the original task must be byte-for-byte what the pre-images preserved
        now = _transfer_receipts(cfg)
        if any(now.get(n) != h for n, h in manifest["receipts"].items()):
            raise GateError("a historical receipt changed since the recovery pre-image")
        if any(now.get(f"{n}.json") != manifest["receipts"].get(f"{n}.json") for n in (S0_RECEIPT, S0_QA_RECEIPT)):
            raise GateError("a historical S0 receipt was created or changed")
        old_tasks = json.loads((pre / "state.json").read_text())["tasks"]
        for tid, ot in old_tasks.items():
            nt = tasks.get(tid)
            if ot.get("role") == "code-review" and not (isinstance(nt, dict) and all(
                    nt.get(k) == ot.get(k) for k in ("status", "review_of", "route")) and
                    (nt.get("evidence") or {}).get("review_outcome") == (ot.get("evidence") or {}).get("review_outcome")):
                raise GateError("a historical review changed since the recovery pre-image")
        if tasks.get(S0_DUAL_REBIND_ID) != old_tasks.get(S0_DUAL_REBIND_ID):
            raise GateError("the original S0 rebind task changed since the recovery pre-image")
    except GateError:
        raise
    except Exception as e:
        raise GateError(f"historical preservation cannot be proven: {type(e).__name__}")
    return {"docs": docs, "receipt_sha256": _sha(rb), "commit": head}


def _recovery_runner_subject(cfg, ov, e):
    """The fresh S0 receipt's runner_gate subject: the replacement runner is authenticated by the overlay's pre-load Opus review
    (re-derived from the preserved evidence) and its exact-SHA CI, observed again now. Returns the committed runner bytes."""
    rn = ov["runner"]
    if not (isinstance(e, dict) and set(e) == {"path", "sha256", "commit", "ci", "review"} and e["path"] == S0_RUNNER_FILE
            and e["sha256"] == CODE_SHA and e["commit"] == rn["commit"] and e["ci"] == rn["ci"]
            and e["review"] == {"preload_sha256": rn["preload_sha256"], "output_sha256": rn["preload_output_sha256"]}):
        raise GateError("S0 runner_gate: not the overlay-bound replacement runner, CI and pre-load review")
    pre = Path(cfg.home) / ov["pre_image"]["dir"] / "review"
    bind = _transfer_preload_bind(_read_bounded(pre / "preload.json", 1 << 20), _read_bounded(pre / "preload.out", 8 * 1024 * 1024),
                                  {"commit": rn["commit"], "code_sha256": rn["code_sha256"], "test_sha256": rn["test_sha256"],
                                   "diff_sha256": rn["diff_sha256"]})
    if bind != {"preload_sha256": rn["preload_sha256"], "preload_output_sha256": rn["preload_output_sha256"]}:
        raise GateError("S0 runner_gate: the preserved pre-load review differs from the overlay binding")
    if not _is_ancestor(cfg, rn["commit"]):
        raise GateError("S0 runner_gate: the replacement commit is not an ancestor of HEAD")
    _observe_ci_for_commit(cfg, rn["commit"], run_id=rn["ci"]["run_id"], opener=_ci_opener)
    blob = _transfer_blob(cfg, rn["commit"], S0_RUNNER_FILE)
    if _sha(blob) != CODE_SHA:
        raise GateError("S0 runner_gate: the committed runner is not the loaded replacement")
    return blob


def _recovery_probe_problem(cfg, rec, ov, tasks):
    """Positive and negative read-only probes before ACTIVE; None when all hold."""
    full = _transition_bound_problem(cfg, rec, full=True)
    if full:
        return full
    if not _transition_live(cfg, rec):
        return "positive probe: the attested replacement runner is not live"
    base = {"module": S0_MODULE, "role": "implement", "status": "QUEUED", "attempts": 0, "allowed_paths": [],
            "expected_changes": [], "verify_cmd": [], "prompt": "probe", "title": "probe", "source": None}
    probes = ({**base, "id": D16_DUAL_ID}, {**base, "id": "transfer-probe-s0-product", "plan_phase": S0_MARKER},
              {**base, "id": S0_DUAL_REBIND_ID, "plan_phase": S0_DUAL_REBIND_MARKER})
    for p in probes:
        try:
            if gate_reason(cfg, p, tasks) is None:
                return f"negative probe: {p['id']} would be admitted"
        except Exception:
            continue  # an unverifiable gate is a refusal
    return None


# ------------------------------------------------ S0 dual rebind lane (2026-10-26)

def s0_dual_rebind_marked(t):
    return t.get("plan_phase") == S0_DUAL_REBIND_MARKER and t.get("id") == S0_DUAL_REBIND_ID


def s0_dual_rebind_shape_problem(t):
    if t.get("module") != S0_MODULE or t.get("role") != "implement":
        return "the dual rebind lane is a MOD-004 implement task only"
    if t.get("source") is not None:
        return "the dual rebind lane is owner-CLI only"
    if t.get("id") != S0_DUAL_REBIND_ID:
        return f"id must be {S0_DUAL_REBIND_ID}"
    if any(t.get(k) is not None for k in ("remediation_of", "review_retry_of", "accounting_recovery_of",
                                           "review_of", "review_candidate")):
        return "remediation, retry, accounting-recovery and review fields are rejected"
    if (sorted(t.get("allowed_paths") or []) != sorted(S0_DOC_PATHS)
            or sorted(t.get("expected_changes") or []) != sorted(S0_DOC_PATHS)):
        return "allowed_paths and expected_changes must be exactly the two S0 document files"
    if t.get("verify_cmd") != []:
        return "the dual rebind lane runs no verifier"
    base = t.get("doc_base")
    if not (isinstance(base, dict) and set(base) == set(S0_DOC_PATHS)
            and all(isinstance(v, str) and SHA256_RE.fullmatch(v) for v in base.values())):
        return "doc_base must map each S0 document path to its sha256 hex string"
    return None


def s0_dual_rebind_gate_reason(cfg, t, tasks):
    """None for a task outside the lane or the one fully authorised evidence-only rebind write; else an explicit reason."""
    if not s0_dual_rebind_marked(t):
        return None
    problem = s0_dual_rebind_shape_problem(t)
    if problem:
        return f"S0_DUAL_REBIND_INVALID_TASK {t['id']}: {problem}"
    # Quarantine state: fail closed on any non-ENTERED_LIVE state
    qs, qled_or_reason = quarantine_state(cfg)
    if qs == _QS_NONE:
        return "S0_DUAL_REBIND_QUARANTINE_NOT_ENTERED: quarantine has not been entered for this reload"
    if qs == _QS_DENY:
        return f"S0_DUAL_REBIND_QUARANTINE_UNVERIFIABLE: {qled_or_reason}"
    if qs == _QS_RESTARTED:
        return "S0_DUAL_REBIND_QUARANTINE_RESTARTED: the recorded runner is no longer live (any process restart blocks both lanes)"
    if qs == _QS_ACTIVE:
        return "S0_DUAL_REBIND_CLOSED: the transfer is ACTIVE; the fixed S0 rebind lane is spent"
    qled = qled_or_reason  # _QS_ENTERED_LIVE
    if qled.get("dual_rebind_consumed"):
        return "S0_DUAL_REBIND_CONSUMED: the single evidence-only write attempt was already started or consumed"
    if t.get("attempts"):
        return f"S0_DUAL_REBIND_ATTEMPT_USED {t['id']}: the single evidence-only write attempt was already started"
    others = sorted(x["id"] for x in tasks.values()
                    if x.get("id") != t.get("id") and s0_dual_rebind_marked(x) and x.get("role") in WRITE_ROLES)
    if others:
        return f"S0_DUAL_REBIND_SECOND_WRITE: evidence-only write {others[0]} already exists; the lane is one-shot"
    busy = _s0_competing_writes(tasks, t)
    if busy:
        return f"S0_DUAL_REBIND_CONCURRENT_WRITE: {busy[0]} is a pending write in an S0 chain or touching S0 files"
    try:
        _s0_qa_git_clean(cfg, S0_DOC_PATHS, "S0 dual rebind start")
        for path, sha in t["doc_base"].items():
            if (_path_hash(Path(cfg.repo) / path) != sha
                    or _s0_git_blob_sha(cfg, "HEAD", path, "S0 dual rebind start") != sha):
                return "S0_DUAL_REBIND_STALE_BASE: document bytes or HEAD do not match doc_base"
    except (GateError, OSError) as e:
        return f"S0_DUAL_REBIND_STALE_BASE: {e}"
    return None


def s0_dual_rebind_review_reason(cfg, t, tasks):
    """The one exact-bound owner-CLI Opus review of the sole DONE evidence-only dual rebind write."""
    w = tasks.get((t.get("review_of") or {}).get("task_id"))
    if not (w and s0_dual_rebind_marked(w)):
        return None
    if t.get("source") is not None:
        return "S0_DUAL_REBIND_REVIEW_UNSUPPORTED: the rebind review is owner-CLI routed only"
    if t.get("review_retry_of") or t.get("review_candidate"):
        return "S0_DUAL_REBIND_REVIEW_UNSUPPORTED: the dual rebind write gets one bound review and no retry"
    if not (t.get("module") == w.get("module") == S0_MODULE and w.get("role") == "implement"
            and w.get("status") == "DONE" and w.get("attempts") == 1
            and (w.get("evidence") or {}).get("violations") == []):
        return "S0_DUAL_REBIND_REVIEW_UNSUPPORTED: only a DONE one-attempt MOD-004 dual rebind write can be reviewed here"
    problem = s0_dual_rebind_shape_problem(w)
    if problem:
        return f"S0_DUAL_REBIND_REVIEW_UNSUPPORTED: {problem}"
    want = _changed_pairs((w.get("evidence") or {}).get("changed"))
    if not (sorted(c["path"] for c in want) == sorted(w["allowed_paths"])
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"])
                    and c["sha256"] != w["doc_base"][c["path"]] for c in want)
            and _changed_pairs((t.get("review_of") or {}).get("changed")) == want):
        return "S0_DUAL_REBIND_REVIEW_UNSUPPORTED: review must bind the exact changed hashes of every named document"
    used = sorted(x["id"] for x in tasks.values() if isinstance(x, dict) and x.get("id") != t.get("id")
                  and (x.get("review_of") or {}).get("task_id") == w["id"])
    if used:
        return f"S0_DUAL_REBIND_REVIEW_SLOT_USED: {used[0]} already reviewed or tried to review the dual rebind write"
    if not _hashes_current(cfg, (w.get("evidence") or {}).get("changed")):
        return "S0_DUAL_REBIND_REVIEW_BINDING_STALE: the documents no longer match the write's recorded hashes"
    return None


# ------------------------------------------------ D16 dual-version admission (2026-10-26)

def d16_dual_lineage(tasks, t):
    """True when t is D16_DUAL_ID or its remediation ancestry traces back to it (depth-bounded, deny on overflow)."""
    seen, cur = set(), t
    for _ in range(66):
        if not isinstance(cur, dict):
            return False
        if cur.get("id") == D16_DUAL_ID:
            return True
        parent = cur.get("remediation_of")
        if not parent:
            return False
        if parent == D16_DUAL_ID:
            return True
        if parent in seen:
            return True  # malformed ancestry must enter the fail-closed D16 verifier
        seen.add(parent)
        cur = tasks.get(parent)
    return True  # overflow is denied by the D16 verifier, never treated as an unrelated task


def d16_single_attempt(tasks, t):
    """The one-shot rebind/D16 writes and their bound reviews never transport-retry."""
    if s0_dual_rebind_marked(t) or _recovery_marked(t) or d16_dual_lineage(tasks, t):
        return True
    parent = tasks.get((t.get("review_of") or {}).get("task_id"))
    return bool(t.get("role") in OPUS_ROLES and isinstance(parent, dict)
                and (s0_dual_rebind_marked(parent) or _recovery_marked(parent) or d16_dual_lineage(tasks, parent)))


def verify_d16_published_owners(cfg, rebind_owner_commit):
    """Bind both published owner decisions to committed bytes, pinned Opus reviews and provider CI.

    These owner-record reviews predate this runner amendment and were performed
    outside the runner; their exact response bytes are pinned here. They are not
    presented as runner-recorded product reviews or as approval of this code.
    """
    if rebind_owner_commit != D16_BOOT_COMMIT:
        raise GateError("D16 dual: rebind owner receipt does not name the published quarantine decision commit")
    for label, path, sha, commit, run_id, review_path, review_sha in (
        ("quarantine", D16_DUAL_OWNER_PATH, D16_DUAL_OWNER_SHA, D16_BOOT_COMMIT,
         D16_DUAL_OWNER_CI_RUN, D16_DUAL_OWNER_REVIEW, D16_DUAL_OWNER_REVIEW_SHA),
        ("design", D16_DUAL_DESIGN_PATH, D16_DUAL_DESIGN_SHA, D16_DUAL_DESIGN_COMMIT,
         D16_DUAL_DESIGN_CI_RUN, D16_DUAL_DESIGN_REVIEW, D16_DUAL_DESIGN_REVIEW_SHA),
    ):
        if _path_hash(Path(cfg.repo) / path) != sha:
            raise GateError(f"D16 dual: {label} owner record working bytes differ from the approved subject")
        shown = git_run(cfg.repo, "show", f"{commit}:{path}", timeout=10)
        if shown.returncode != 0 or hashlib.sha256(shown.stdout).hexdigest() != sha:
            raise GateError(f"D16 dual: {label} owner record committed bytes differ from the approved subject")
        if not _is_ancestor(cfg, commit):
            raise GateError(f"D16 dual: {label} owner record commit is not an ancestor of HEAD")
        review = _read_bounded(Path(cfg.home) / review_path, REVIEW_MAX_BYTES)
        if (hashlib.sha256(review).hexdigest() != review_sha
                or not review.rstrip().endswith(b"OUTCOME: APPROVED")):
            raise GateError(f"D16 dual: {label} owner record lacks its pinned independent Opus APPROVED review")
        _observe_ci_for_commit(cfg, commit, run_id=run_id)


def verify_d16_dual(cfg, tasks, t):
    """Read-only gate for the dual-version D16 admission root and its corrections.
    Returns frozenset of set-aside historical ids, or raises GateError.
    Verifies the full S0/D16 predicate at both enqueue and dispatch."""
    root = t if t.get("id") == D16_DUAL_ID else tasks.get(D16_DUAL_ID)
    if not isinstance(root, dict) or not d16_dual_lineage(tasks, t):
        raise GateError("D16 dual: task is not linked to the fixed design root")
    problem = d16_successor_shape_problem(root, D16_DUAL_ID)
    if problem:
        raise GateError(problem)
    # Single-use root: any recorded task with the fixed id other than t consumed the entitlement
    if any(isinstance(x, dict) and x.get("id") == D16_DUAL_ID and x is not root for x in tasks.values()):
        raise GateError("the single-use dual-version entitlement is already consumed")
    if t is not root:
        # A correction is never a second root. Every predecessor must be a DONE,
        # exactly reviewed rejection in this same lineage, with no third cycle.
        cur, depth, seen = t, 0, set()
        while cur is not root:
            depth += 1
            if depth > D16_DUAL_MAX_CORRECTIONS or cur.get("id") in seen:
                raise GateError("D16 dual: correction limit or ancestry cycle")
            seen.add(cur.get("id"))
            parent = tasks.get(cur.get("remediation_of"))
            if not (isinstance(parent, dict) and parent.get("module") == "MOD-004"
                    and parent.get("role") == "implement" and parent.get("status") == "DONE"):
                raise GateError("D16 dual: correction parent is not a DONE design write")
            if depth == 1 and not _hashes_current(cfg, (parent.get("evidence") or {}).get("changed")):
                raise GateError("D16 dual: correction parent no longer matches its rejected ADR bytes")
            reviews = [rv for rv in review_attempts(tasks, parent["id"])
                       if rv.get("status") == "BLOCKED"
                       and rv.get("blocked_reason") == "REVIEW_CHANGES_REQUESTED"
                       and (rv.get("evidence") or {}).get("violations") == ["REVIEW_CHANGES_REQUESTED"]
                       and _bound_review_ok(parent, rv)]
            if not (len(reviews) == 1 and reviews[0]["evidence"]["review_outcome"] == "CHANGES_REQUESTED"):
                raise GateError("D16 dual: correction parent lacks one exact-bound CHANGES_REQUESTED review")
            cur = parent
    # On-disk hash: runner.py identity must not have drifted since load
    try:
        disk_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        raise GateError("D16 dual: cannot read on-disk runner.py for integrity check")
    if disk_sha != CODE_SHA:
        raise GateError(f"D16 dual: on-disk runner.py hash differs from the loaded code hash (drift detected)")
    # Quarantine predicate: must be actively quarantined with a live runner and consumed rebind
    qs, qled_or_reason = quarantine_state(cfg)
    if qs == _QS_NONE:
        raise GateError("D16 dual: quarantine has not been entered for this reload")
    if qs == _QS_DENY:
        raise GateError(f"D16 dual: quarantine state is DENY: {qled_or_reason}")
    if qs == _QS_RESTARTED:
        raise GateError("D16 dual: the recorded runner is no longer live (any restart blocks both lanes)")
    qled = qled_or_reason  # _QS_ENTERED_LIVE
    if not qled.get("dual_rebind_consumed"):
        raise GateError("D16 dual: rebind lane not yet consumed; complete rebind before D16 admission")
    # Full F34-exhausted history: the four prior chains must be intact
    old_chain = _d16_exhausted_chain(tasks)
    succ_chain = _d16_exhausted_chain(tasks, D16_SUCCESSOR_ID, D16_SUCC_TERMINAL, D16_SUCC_TERMINAL_REVIEW)
    # The generic exhausted-chain verifier expects its named tip to be terminal.
    # F34 is the separately authorized fourth child of that tip, verified below.
    pre_f34 = {k: v for k, v in tasks.items() if k not in (D16_F34_WRITE, D16_F34_REVIEW)}
    arch_chain = _d16_exhausted_chain(pre_f34, D16_F34_ROOT, D16_F34_TIP,
                                      "mod004-d16-assurance-architecture-remed3-opus-review-20261025")
    # F34 write is DONE; its independent CHANGES_REQUESTED review is durably BLOCKED.
    f34 = tasks.get(D16_F34_WRITE)
    if not (isinstance(f34, dict) and f34.get("status") == "DONE"
            and f34.get("remediation_root") == D16_F34_ROOT and f34.get("remediation_of") == D16_F34_TIP):
        raise GateError("D16 dual: the F34 final write is not DONE or its ancestry is wrong")
    f34_review = tasks.get(D16_F34_REVIEW)
    if not (isinstance(f34_review, dict) and f34_review.get("status") == "BLOCKED"
            and f34_review.get("blocked_reason") == "REVIEW_CHANGES_REQUESTED"
            and (f34_review.get("evidence") or {}).get("review_outcome") == "CHANGES_REQUESTED"
            and (f34_review.get("evidence") or {}).get("violations") == ["REVIEW_CHANGES_REQUESTED"]
            and _bound_review_ok(f34, f34_review)):
        raise GateError("D16 dual: the F34 review is not the bound BLOCKED CHANGES_REQUESTED verdict")
    # Dual rebind write must be DONE, one attempt, no violations, changes exactly the two S0 docs
    rebind = tasks.get(S0_DUAL_REBIND_ID)
    if not (isinstance(rebind, dict) and rebind.get("id") == S0_DUAL_REBIND_ID
            and s0_dual_rebind_marked(rebind) and rebind.get("module") == S0_MODULE
            and rebind.get("role") == "implement" and rebind.get("status") == "DONE"
            and rebind.get("attempts") == 1 and (rebind.get("evidence") or {}).get("violations") == []):
        raise GateError("D16 dual: the dual rebind write is not a DONE one-attempt MOD-004 write with no violations")
    rebind_changed = _changed_pairs((rebind.get("evidence") or {}).get("changed"))
    if not (sorted(c["path"] for c in rebind_changed) == sorted(S0_DOC_PATHS)
            and all(isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"]) for c in rebind_changed)):
        raise GateError("D16 dual: the rebind write did not change exactly the two S0 document files with valid hashes")
    rebind_hashes = {c["path"]: c["sha256"] for c in rebind_changed}
    # Exactly one DONE APPROVED Opus review bound to the dual rebind write
    rebind_reviews = [x for x in tasks.values() if isinstance(x, dict) and x.get("role") in OPUS_ROLES
                      and (x.get("evidence") or {}).get("review_outcome") == "APPROVED"
                      and _bound_review_ok(rebind, x) and x.get("status") == "DONE"
                      and not (x.get("evidence") or {}).get("violations")]
    if len(rebind_reviews) != 1:
        raise GateError("D16 dual: exactly one DONE APPROVED Opus review bound to the dual rebind write is required")
    rv = rebind_reviews[0]
    # Review binding must match the rebind write's evidence hashes
    review_changed = _changed_pairs((rv.get("review_of") or {}).get("changed"))
    rebind_changed_sorted = sorted([{"path": c["path"], "sha256": c["sha256"]} for c in rebind_changed],
                                   key=lambda x: str(x["path"]))
    if review_changed != rebind_changed_sorted:
        raise GateError("D16 dual: the Opus review binding does not match the rebind write's S0 doc hashes")
    # Historical negative S0 product review must not have been relabeled
    s0_product_approved = [x for x in tasks.values() if isinstance(x, dict) and x.get("role") in OPUS_ROLES
                           and (x.get("evidence") or {}).get("review_outcome") == "APPROVED"
                           and s0_marked(tasks.get((x.get("review_of") or {}).get("task_id")) or {})]
    if s0_product_approved:
        raise GateError("D16 dual: an S0 product write review is recorded as APPROVED; historical negatives may not be relabeled")
    # Rebind authority receipt (MOD-004-S0-D16-REBIND): verifies runner hash, owner record, and S0 doc subjects.
    # No operator field: evidence derives from runner-recorded tasks and authenticated CI only.
    r_data = _read_bounded(cfg.home / "acceptances" / f"{S0_DUAL_REBIND_RECEIPT}.json", RECEIPT_MAX_BYTES)
    r = _s0_json(r_data, "D16 dual rebind receipt")
    sub = r.get("subjects")
    if not (isinstance(r, dict) and r.get("schema") == SCHEMA and r.get("module") == "MOD-004"
            and r.get("kind") == "mod004-s0-d16-rebind-authority"
            and isinstance(sub, dict) and set(sub) == set(S0_DUAL_REBIND_SUBJECTS)):
        raise GateError("D16 dual: rebind receipt schema mismatch or wrong subject set")
    # --- Runner subject: verify by CODE_SHA at activation commit with observed CI (no review required) ---
    runner_entry = sub.get("dual_rebind_runner") or {}
    runner_commit = runner_entry.get("commit") or ""
    if not (isinstance(runner_entry, dict) and runner_entry.get("sha256") == CODE_SHA
            and isinstance(runner_commit, str) and SHA_RE.fullmatch(runner_commit)):
        raise GateError("D16 dual: receipt runner entry is malformed or sha256 does not match the loaded code hash")
    try:
        blob_result = git_run(cfg.repo, "show", f"{runner_commit}:tools/mission_runner/runner.py", timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise GateError("D16 dual: cannot read runner.py at the receipt runner commit")
    if not (blob_result.returncode == 0 and hashlib.sha256(blob_result.stdout).hexdigest() == CODE_SHA):
        raise GateError("D16 dual: runner.py at the receipt runner commit does not match the loaded code hash")
    if not _is_ancestor(cfg, runner_commit):
        raise GateError(f"D16 dual: receipt runner commit {runner_commit[:12]} is not an ancestor of HEAD")
    # --- Both owner decisions: exact reviewed and published bytes, with provider-observed CI ---
    owner_entry = sub.get("dual_rebind_owner") or {}
    owner_commit = owner_entry.get("commit") or ""
    if not (isinstance(owner_entry, dict) and owner_entry.get("path") == D16_DUAL_OWNER_PATH
            and owner_entry.get("sha256") == D16_DUAL_OWNER_SHA
            and isinstance(owner_commit, str) and SHA_RE.fullmatch(owner_commit)):
        raise GateError("D16 dual: receipt owner entry is malformed or sha256 does not match the pinned owner record hash")
    verify_d16_published_owners(cfg, owner_commit)
    # --- S0 cert and qa subjects: each verified with _s0_subject using separate seen sets ---
    # Separate sets allow both cert and qa to bind to the same combined Opus review.
    cert_path, qa_path = S0_DOC_PATHS
    seen_cert = set()
    _s0_subject(cfg, "s0_cert", sub["s0_cert"], tasks, seen_cert, S0_DUAL_REBIND_SUBJECTS)
    seen_qa = set()
    _s0_subject(cfg, "s0_qa", sub["s0_qa"], tasks, seen_qa, S0_DUAL_REBIND_SUBJECTS)
    # S0 doc hashes in receipt must match the rebind write's evidence
    if (sub["s0_cert"].get("sha256") != rebind_hashes.get(cert_path)
            or sub["s0_qa"].get("sha256") != rebind_hashes.get(qa_path)):
        raise GateError("D16 dual: receipt S0 doc hashes do not match the rebind write's evidence")
    # S0 cert and qa must be on the same commit; that commit's diff must change exactly those two doc paths
    if (sub["s0_cert"].get("commit") != sub["s0_qa"].get("commit")
            or sub["s0_cert"].get("ci") != sub["s0_qa"].get("ci")):
        raise GateError("D16 dual: receipt cert and qa subjects do not share one commit and CI run")
    _s0_doc_commit_scope(cfg, sub["s0_cert"]["commit"], S0_DOC_PATHS)
    # The supplemental two-document binding cannot replace either established S0 receipt.
    # Both legacy verifiers recheck every subject against committed bytes and runner-recorded
    # Opus output; in particular the new runner_gate needs its own recorded security review.
    verify_s0_authority(cfg, tasks)
    verify_s0_qa_authority(cfg, tasks)
    offline = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{S0_RECEIPT}.json", RECEIPT_MAX_BYTES),
                       "MOD-004-S0 offline receipt")
    live = _s0_json(_read_bounded(cfg.home / "acceptances" / f"{S0_QA_RECEIPT}.json", RECEIPT_MAX_BYTES),
                    "MOD-004-S0-QA live receipt")
    offline_sub = offline["subjects"]
    live_sub = live["subjects"]
    runner_subject = offline_sub["runner_gate"]
    if not (runner_subject == live_sub["runner_gate"]
            and runner_subject["path"] == S0_RUNNER_FILE
            and runner_subject["sha256"] == CODE_SHA
            and runner_subject["commit"] == runner_commit):
        raise GateError("D16 dual: offline and live S0 receipts do not bind the same reviewed runner commit/hash")
    _observe_ci_for_commit(cfg, runner_commit, run_id=runner_subject["ci"]["run_id"])
    if offline_sub["eligibility"] != sub["s0_cert"]:
        raise GateError("D16 dual: offline S0 certificate subject is not the exact rebind subject")
    _observe_ci_for_commit(cfg, sub["s0_cert"]["commit"],
                           run_id=offline_sub["eligibility"]["ci"]["run_id"])
    # ADR must not be a rejected candidate from any prior chain
    # The root alone must begin from the published ADR rather than a rejected old candidate.
    # Only the root begins from the published ADR. An authorized correction
    # begins from its rejected, review-bound root/correction candidate.
    if t is root:
        _d16_adr_problem(cfg, t, old_chain + succ_chain + arch_chain + [f34])
    all_ids = frozenset(w["id"] for w in old_chain + succ_chain + arch_chain) | {D16_F34_WRITE, D16_F34_REVIEW}
    return all_ids


def d16_dual_gate_reason(cfg, t, tasks):
    """None for a task outside the dual-version lineage; else the predicate gate result. Checked at enqueue and dispatch."""
    if not d16_dual_lineage(tasks, t):
        return None
    if t.get("id") == D16_DUAL_ID and t.get("role") != "implement":
        return f"D16_DUAL_INVALID {t['id']}: the fixed dual-version id is reserved for the implement root"
    # The narrow hold: release only while the full predicate holds, restore on any mismatch
    try:
        verify_d16_dual(cfg, tasks, t)
    except GateError as e:
        return f"D16_DUAL_PREDICATE_NOT_MET {t['id']}: {e}"
    except OSError as e:
        return f"D16_DUAL_PREDICATE_NOT_MET {t['id']}: {type(e).__name__}"
    return None


def review_gate_reason(cfg, t, tasks):
    """Mandatory review between write tasks. Only writes created under this gate (`review_gate` marker) are
    bound by it; earlier history, including MOD-003 S1's existing review and owner record, is left untouched."""
    if t.get("id") in (D16_SUCCESSOR_ID, D16_ARCH_ID) and not cfg.review_gate:
        return f"D16_SUCCESSOR_INVALID {t['id']}: the fixed successor id is admitted only under the mandatory review gate"
    if not cfg.review_gate or t["role"] not in WRITE_ROLES | {"gatekeeper"}:
        return None
    if s0_marked(t) or s0_test_marked(t) or s0_touches(t):  # only gate_reason's S0 admission may skip this chain
        return f"S0_INVALID_TASK {t['id']}: S0 tasks are admitted only by the S0 gate"
    if (s0_doc_marked(t) or s0_refresh_marked(t) or s0_rebind_marked(t) or s0_loop_marked(t) or s0_qa_marked(t)
            or s0_dual_rebind_marked(t) or _recovery_marked(t) or s0_doc_touches(t)):
        return f"S0_DOC_INVALID_TASK {t['id']}: document tasks are admitted only by the S0 document gate"
    module = t["module"]
    cap_chain = ()  # the closed historical CAP chain is set aside only for a verified new non-CAP design task
    if NONCAP_TERMINAL_WRITE in tasks and not noncap_shape_problem(tasks, t):
        try:
            verify_noncap_authority(cfg, tasks)
        except GateError as e:
            return f"NONCAP_DESIGN_UNVERIFIED {t['id']}: {e}"
        cap_chain = NONCAP_CAP_CHAIN
    elif module == "MOD-004" and NONCAP_TERMINAL_WRITE in tasks:
        # fail closed regardless of the historical review's status: a design-only owner authority never reopens CAP/product/other
        # MOD-004 work, even if that review is later tampered to APPROVED, missing or malformed (separate owner authority required)
        return (f"REVIEW_REQUIRED {module}: write task {NONCAP_TERMINAL_WRITE} has no independent Opus code-review attempt "
                f"bound to it (terminal review {NONCAP_TERMINAL_REVIEW} is BLOCKED); {t['id']} is refused, only an exact "
                "owner-covered design task is admitted under the non-CAP owner record")
    set_aside = frozenset()  # the exhausted D16 root is set aside only for the one verified successor root
    if t.get("id") == D16_SUCCESSOR_ID:
        if not cap_chain:
            return f"D16_SUCCESSOR_INVALID {t['id']}: the fixed successor id is admitted only as a verified MOD-004 non-CAP design task"
        try:
            set_aside = verify_d16_successor(cfg, tasks, t)
        except GateError as e:
            return f"D16_SUCCESSOR_UNVERIFIED {t['id']}: {e}"
        except OSError as e:
            return f"D16_SUCCESSOR_UNVERIFIED {t['id']}: {type(e).__name__}"
    elif t.get("id") == D16_ARCH_ID:  # a separately pinned exception: sets aside both verified exhausted chains for this one root
        if not cap_chain:
            return f"D16_SUCCESSOR_INVALID {t['id']}: the fixed architecture id is admitted only as a verified MOD-004 non-CAP design task"
        try:
            set_aside = verify_d16_architecture(cfg, tasks, t)
        except GateError as e:
            return f"D16_ARCH_UNVERIFIED {t['id']}: {e}"
        except OSError as e:
            return f"D16_ARCH_UNVERIFIED {t['id']}: {type(e).__name__}"
    elif d16_dual_lineage(tasks, t):
        # D16 dual-version admission: sets aside the exhausted F34/arch/succ/old chains; governs root and all corrections
        if not cap_chain:
            return f"D16_DUAL_INVALID {t['id']}: the dual-version id is admitted only as a verified MOD-004 non-CAP design task"
        try:
            set_aside = verify_d16_dual(cfg, tasks, t)
        except GateError as e:
            return f"D16_DUAL_UNVERIFIED {t['id']}: {e}"
        except OSError as e:
            return f"D16_DUAL_UNVERIFIED {t['id']}: {type(e).__name__}"
    # the S0, document and refresh chains are separate chains: they never become `last`, so they cannot unblock any other MOD-004 task
    writes = sorted((x for x in tasks.values() if x.get("module") == module and x.get("role") in WRITE_ROLES
                     and x.get("id") not in cap_chain and x.get("id") not in set_aside
                     and x.get("status") == "DONE" and x.get("review_gate") and not s0_marked(x)
                     and not s0_doc_marked(x) and not s0_refresh_marked(x) and not s0_rebind_marked(x)
                     and not s0_test_marked(x) and not s0_loop_marked(x) and not s0_qa_marked(x)
                     and not s0_dual_rebind_marked(x) and not _recovery_marked(x)), key=_when)
    product_t = product_loop_eligible(tasks, t) and product_new_policy(tasks, t)
    if product_t:
        decided, lineage = product_lineage_reason(cfg, tasks, t, set_aside)
        if decided:
            return lineage
        if not t.get("remediation_of") and "remediation_root" in t and (t["remediation_root"], t.get("remediation_cycle")) != (t.get("id"), 0):
            return f"REMEDIATION_COUNTER_MISMATCH {module}: persisted counter disagrees with the task ancestry"
    if cap_chain and t.get("remediation_of"):
        # a verified non-CAP correction is admitted only through product_lineage_reason's decided path (stamped rejected tip,
        # returned above); a stamped approved/mid-chain parent or an unstamped (legacy) parent never reaches the legacy branch
        return (f"NONCAP_REMEDIATION_ANCESTRY_UNSTAMPED {t['id']}: parent {t['remediation_of']} is not the sole "
                "product-policy-stamped rejected tip of a remediation chain; refused")
    if not writes:
        return None
    last = writes[-1]
    if t.get("accounting_recovery_of"):
        return None if last["id"] == "mod004-cap-budget-accounting-sonnet-20261019" and accounting_recovery_valid(cfg, t, tasks) else "ACCOUNTING_RECOVERY_INVALID"
    if product_loop_eligible(tasks, last) and product_policy_root(tasks, last):  # created under the product loop: bound reviews only
        try:
            product_chain(tasks, last)
        except ValueError as e:
            return str(e)
        bound = [a["evidence"]["review_outcome"] for a in review_attempts(tasks, last["id"]) if _bound_review_ok(last, a)]
        verdict = None if not bound else "CHANGES_REQUESTED" if "CHANGES_REQUESTED" in bound else "APPROVED"
    else:
        verdict = review_verdict(tasks, last["id"])
    if verdict is None:
        return f"REVIEW_REQUIRED {module}: write task {last['id']} has no independent Opus code-review attempt bound to it"
    if verdict == "APPROVED":
        if not _hashes_current(cfg, (last.get("evidence") or {}).get("changed")):
            return (f"REVIEW_BINDING_STALE {module}: files of {last['id']} no longer match the content that was "
                    "reviewed and approved")
        return None
    if t["role"] == "gatekeeper":
        return f"REVIEW_CHANGES_REQUESTED {module}: a review of {last['id']} requests changes; only a remediation write may follow"
    if product_t and product_loop_eligible(tasks, last) and product_policy_root(tasks, last):
        return product_correction_reason(cfg, tasks, t, last)
    # The historical source-inaccessible write is not a remediation round of the new candidate.
    # This leaves MAX_REMEDIATIONS unchanged and applies only to the exact audited recovery chain.
    if accounting_recovery_chain(tasks, last):
        writes = writes[next(i for i, w in enumerate(writes) if w["id"] == ACCOUNTING_RECOVERY_WRITE):]
    rounds = 0
    for w in writes:
        rounds = 0 if review_verdict(tasks, w["id"]) == "APPROVED" else rounds + 1
    correction_limit = D16_DUAL_MAX_CORRECTIONS if d16_dual_lineage(tasks, t) else MAX_REMEDIATIONS
    if rounds > correction_limit:
        return f"REMEDIATION_LIMIT {module}: {correction_limit} remediation rounds already used after CHANGES_REQUESTED"
    if not all(in_scope(p, last.get("allowed_paths") or []) for p in t.get("allowed_paths") or []):
        return f"REMEDIATION_OUT_OF_SCOPE {module}: remediation must stay inside {last['id']}'s allowed paths"
    return None


def review_binding(cfg, t, tasks, require_changed):
    """Validate (and for the owner CLI, fill) the exact write task + changed-file hashes a code-review binds to."""
    b = t.get("review_of")
    if not b:
        return
    w = tasks.get(b["task_id"])
    if not (w and w.get("role") in WRITE_ROLES and w.get("status") == "DONE" and w.get("module") == t["module"]):
        raise ValueError("review_of must name a DONE write task of the same module")
    want = _review_want(w)
    if not want:
        raise ValueError("the write task recorded no changed-file evidence to bind to")
    if b.get("changed") is None:
        if require_changed:
            raise ValueError("review_of.changed (path + sha256 of every changed file) is required")
        b["changed"] = want
    elif sorted(b["changed"], key=lambda c: c["path"]) != sorted(want, key=lambda c: c["path"]):
        raise ValueError("review_of.changed does not match the write task's recorded changed files")
    for c in want:
        if _path_hash(Path(cfg.repo) / c["path"]) != c["sha256"]:
            raise ValueError(f"{c['path']} changed since the write task finished: stale binding")
    prior = [o for o in tasks.values() if o.get("id") != t.get("id")
             and (o.get("review_of") or {}).get("task_id") == b["task_id"]
             and (o.get("status") in ("QUEUED", "RUNNING") or review_attempts({o["id"]: o}, b["task_id"])
                  or (o.get("evidence") or {}).get("review_outcome_reported") in ("APPROVED", "CHANGES_REQUESTED", "BLOCKED"))]
    retry_of = t.get("review_retry_of")
    if retry_of:
        if not (len(prior) == 1 and prior[0].get("id") == retry_of and operational_hash_block(prior[0])):
            raise ValueError("review retry requires exactly one operational no-hash-tool BLOCKED review, with no substantive verdict or prior retry")
        if t.get("review_candidate") != review_candidate(cfg.repo):
            raise ValueError("review retry candidate is missing or changed")
    elif prior:  # substantive verdicts and approved reviews are never review-shopped
        raise ValueError(f"write task {b['task_id']} already has a bound review ({prior[0]['id']}); "
                         "only a new remediation write can be reviewed again")


def bound_review_problems(cfg, tasks, t):
    """Empty when the bound write and every changed-file hash are still exactly what the review was bound to."""
    b = t.get("review_of")
    if not b:
        return []
    w = tasks.get(b.get("task_id"))
    if not (w and w.get("role") in WRITE_ROLES and w.get("status") == "DONE" and w.get("module") == t["module"]):
        return ["bound write task is not a DONE write of the module"]
    want = _changed_pairs(_review_want(w))
    if not want or _changed_pairs(b.get("changed")) != want:
        return ["bound changed-file evidence no longer matches the write task"]
    try:
        problems = [f"{c['path']} changed since the write finished" for c in want
                    if _path_hash(Path(cfg.repo) / c["path"]) != c["sha256"]]
        if t.get("review_retry_of") and t.get("review_candidate") != review_candidate(cfg.repo):
            problems.append("complete review candidate changed since retry enqueue")
        return problems
    except OSError as e:
        return [f"cannot hash bound files: {str(e)[:80]}"]


def gate_reason(cfg, t, tasks):
    """None when the task may run, else an explicit reason. Fails closed on any error."""
    try:
        transfer = _transition_gate_reason(cfg, t, tasks)  # quarantine-transfer lineage: D16/S0 product denied, stage holds
        if transfer:
            return transfer
        if t.get("id") == TRANSFER_REVIEW_ID and _transfer_lineage_active(cfg):
            return None  # admitted by _transfer_review_gate above; no legacy lane applies to the review-only bridge
        if t.get("id") in (D16_SUCCESSOR_ID, D16_ARCH_ID, D16_F34_WRITE, D16_DUAL_ID) and t["role"] != "implement":
            return f"D16_SUCCESSOR_INVALID {t['id']}: the fixed successor id is reserved for the one reviewed implement root"
        if t.get("id") == D16_F34_REVIEW and t["role"] != "code-review":
            return f"D16_F34_REVIEW_INVALID {t['id']}: the fixed final review id is reserved for code-review"
        if t["role"] in WRITE_ROLES and t.get("verify_cmd") != [] and (d16_successor_lineage(tasks, t) or d16_dual_lineage(tasks, t)):
            return (f"D16_SUCCESSOR_INVALID {t['id']}: verify_cmd must be empty for the ADR-only successor and its corrections "
                    "(the owner-CLI verifier runs unsandboxed after the scope check)")
        if t["role"] == "code-review":
            parent = tasks.get((t.get("review_of") or {}).get("task_id"))
            if isinstance(parent, dict) and (s0_dual_rebind_marked(parent) or d16_dual_lineage(tasks, parent)):
                qs, detail = quarantine_state(cfg)
                if qs != _QS_ENTERED_LIVE:
                    return f"S0_D16_REVIEW_QUARANTINED {t['id']}: quarantine state={qs}: {detail}"
            return (d16_f34_review_reason(t, tasks) or s0_review_reason(t, tasks) or s0_doc_review_reason(cfg, t, tasks) or s0_refresh_review_reason(cfg, t, tasks)
                    or s0_rebind_review_reason(cfg, t, tasks) or s0_test_review_reason(cfg, t, tasks)
                    or s0_loop_review_reason(cfg, t, tasks) or s0_qa_review_reason(cfg, t, tasks)
                    or s0_dual_rebind_review_reason(cfg, t, tasks) or recovery_review_reason(cfg, t, tasks))
        if t["role"] not in GATED_ROLES:
            return None
        # D16 dual-lineage tasks must satisfy the full D16 predicate at enqueue/dispatch (P0-1)
        if d16_dual_lineage(tasks, t):
            dr = d16_dual_gate_reason(cfg, t, tasks)
            if dr:
                return dr
        # S0 product admission is denied while quarantined (P0-2)
        if s0_marked(t):
            qs, qled_or_reason = quarantine_state(cfg)
            if qs in (_QS_ENTERED_LIVE, _QS_RESTARTED, _QS_DENY) or _d16_policy_active(cfg):
                return (f"S0_PRODUCT_QUARANTINED {t['id']}: S0 product admission is blocked while the runner is in "
                        f"S0/D16 quarantine (state={qs})")
        reason = (s0_gate_reason(cfg, t, tasks) or s0_doc_gate_reason(cfg, t, tasks) or s0_refresh_gate_reason(cfg, t, tasks)
                  or s0_rebind_gate_reason(cfg, t, tasks) or s0_test_gate_reason(cfg, t, tasks)
                  or s0_loop_gate_reason(cfg, t, tasks) or s0_qa_gate_reason(cfg, t, tasks)
                  or s0_dual_rebind_gate_reason(cfg, t, tasks) or recovery_gate_reason(cfg, t, tasks))
        if reason:
            return reason
        for dep in catalog_dependencies(t["module"]):
            try:
                verify_receipt(cfg, dep)
            except GateError as e:
                return f"PREREQ_NOT_ACCEPTED {dep}: {e}"
        if t["role"] in BLOCKER_GATED_ROLES:
            active = active_module_blockers(cfg, t, tasks)
            if active:
                return f"ACTIVE_BLOCKER {t['module']}: {', '.join(active)}"
        if (s0_marked(t) or s0_doc_marked(t) or s0_refresh_marked(t) or s0_rebind_marked(t)
                or s0_test_marked(t) or s0_loop_marked(t) or s0_qa_marked(t) or s0_dual_rebind_marked(t) or _recovery_marked(t)):
            # the sole S0 write and the document, refresh, rebind, test, QA and dual-rebind evidence chains:
            # separate chains, historical blockers stay untouched
            return None
        return review_gate_reason(cfg, t, tasks)
    except GateError as e:
        return f"GATE_UNVERIFIABLE: {e}"
    except Exception as e:
        return f"GATE_UNVERIFIABLE: {type(e).__name__}"


# ---------------------------------------------------------------------- runner
class Runner:
    def __init__(self, cfg):
        self.cfg, self.store = cfg, Store(cfg.home)
        self.rlock = FileLock(cfg.home / "locks" / "runner.lock")
        self.wlock = FileLock(writer_lock_path(cfg.home, cfg.repo))
        self.state, self.sig, self.last_baseline, self.last_hb, self.busy_noted = None, False, 0.0, 0.0, False
        self.last_ci, self.ci_run = 0.0, subprocess.run  # ci_run/ci_popen: injectable subprocess layers for tests
        self.ci_seeded = False
        self.ci_popen = subprocess.Popen
        self.hp = None  # in-flight orchestrator CLI handle (durable record lives in state["handoff"])
        self._tr_last, self._tr_held_cmds = None, set()  # quarantine-transfer step throttle; held-command log-once
        self._rc_last = None  # recovery step throttle
        self._tr_review_last, self._tr_refused = None, None  # pre-consumption review/consume throttle; refusal log-once

    # --- lifecycle
    def run(self):
        if not self.rlock.acquire({"pid": os.getpid(), "host": socket.gethostname()}):
            print(f"another runner holds the lock: {self.rlock.owner()}", file=sys.stderr)
            return EXIT_LOCKED
        try:
            self.state = self.store.load()
        except StateCorrupt as e:
            print(f"refusing to start, state unreadable: {e}", file=sys.stderr)
            self.rlock.release()
            return EXIT_CORRUPT
        for s in (signal.SIGTERM, signal.SIGINT):
            signal.signal(s, lambda *_: setattr(self, "sig", True))
        try:
            transfer = _transfer_lineage_active(self.cfg)  # the transition stage branches before any legacy boot logic
            prior_boot = ((self.state.get("runner") or {}).get("code_sha256") == CODE_SHA
                          or _prior_start_same_code(self.cfg))
            self.state["runner"] = {"pid": os.getpid(), "boot_nonce": _PROCESS_BOOT_NONCE,
                                    "host": socket.gethostname(), "started_at": now_iso(),
                                    "heartbeat_at": now_iso(), "code_sha256": CODE_SHA,
                                    "python": sys.version.split()[0], "executable": sys.executable,
                                    "claude_bin": self.cfg.claude_bin, "repo": str(self.cfg.repo)}
            self.store.event("runner-start", pid=os.getpid(), code_sha256=CODE_SHA)
            # Enter S0/D16 default-deny quarantine on the one authorized reload.
            # Requires intact one-shot activation evidence; absent token = no ledger written (default deny).
            # Fail-closed: a corrupt ledger or corrupt token is never cleared here; gate checks handle per-task.
            try:
                qled = _load_qled(self.cfg)
            except GateError:
                qled = False  # sentinel: corrupt state, don't overwrite
            if transfer:
                qled = False  # the transition record governs; the legacy ledger and token stay preserved, untouched
                self._transition_boot()
            if qled is None:
                try:
                    if _d16_policy_active(self.cfg) and (prior_boot or not _boot_activation_path(self.cfg).exists()):
                        raise GateError("first startup of the amended runner lacked its activation token or this code has already booted")
                    _enter_quarantine_from_activation(self.cfg)
                    # Reload qled to determine whether activation succeeded
                    try:
                        qled2 = _load_qled(self.cfg)
                    except GateError:
                        qled2 = None
                    if qled2 is not None:
                        self.store.event("s0-d16-quarantine-entered", pid=os.getpid(),
                                         boot_nonce=_PROCESS_BOOT_NONCE, code_sha256=CODE_SHA)
                except GateError as e:
                    # A malformed or mismatched token also spends this startup. Keep a
                    # durable deny marker so a later process cannot retry activation.
                    _write_qled(self.cfg, {"schema": 1, "entered_at": now_iso(),
                                           "runner_pid": os.getpid(), "runner_boot_nonce": _PROCESS_BOOT_NONCE,
                                           "code_sha256": CODE_SHA, "dual_rebind_consumed": False,
                                           "activation_failed": True})
                    self.store.event("s0-d16-quarantine-activation-failed", reason=str(e),
                                     pid=os.getpid(), boot_nonce=_PROCESS_BOOT_NONCE, code_sha256=CODE_SHA)
            _trusted_dashboard()  # pin the local gate module before recovery or dispatch
            self.recover()
            self.apply_commands()
            while not self.sig and self.state["control"] != "STOP":
                self.tick()
                time.sleep(self.cfg.tick)
            self.finish()
            return 0
        finally:
            self.rlock.release()

    # --- quarantine-transfer lifecycle (2026-10-26): the authoritative record is written first, events follow
    def _tr_event(self, kind, **detail):
        try:
            self.store.event(kind, **detail)
        except OSError:
            pass  # audit only; the record is authoritative and the next boot reconciles the stage event

    def _transition_boot(self):
        """Branch on the transition stage BEFORE legacy activation, commands, queue, handoff or worker recovery."""
        try:
            rec = _load_transition(self.cfg)
        except GateError as e:
            return self._tr_event("quarantine-transfer-denied", reason=str(e)[:300])
        if rec is None:
            return self._transfer_first_boot()
        if rec["new"]["code_sha256"] != CODE_SHA:
            return self._recovery_boot(rec)  # replacement code under the original record: the overlay path, never a restart
        self._transition_reboot(rec)

    def _transfer_first_boot(self):
        """Open the ONE pre-consumption window for this process. A later process finds the marker (or its audit event) and
        has no review window and no restart: pre-consumption recovery is not permitted, and nothing is consumed at boot."""
        cfg, me = self.cfg, {"schema": 1, "kind": "s0-d16-successor-first-boot", "pid": os.getpid(),
                             "boot_nonce": _PROCESS_BOOT_NONCE, "code_sha256": CODE_SHA, "at": now_iso()}
        if _transfer_first_boot(cfg, me=True) is not None:
            return  # this very process (PID + boot nonce) already holds the window
        try:
            if any(e.get("kind") == "quarantine-transfer-first-boot" for e in _qled_events(cfg)):
                raise GateError("a successor process already used the pre-consumption window")
            _atomic_create_exclusive(Path(cfg.home) / TRANSFER_BOOT_NAME, json.dumps(me, sort_keys=True).encode())
        except (GateError, OSError) as e:
            return self._tr_event("quarantine-transfer-denied", reason=f"no pre-consumption restart: {str(e)[:200]}")
        self._tr_event("quarantine-transfer-first-boot", pid=me["pid"], boot_nonce=me["boot_nonce"], code_sha256=CODE_SHA)

    def _tr_refuse(self, reason):
        if reason != self._tr_refused:  # log once per distinct reason; the sole runner never spams the audit log
            self._tr_refused = reason
            self._tr_event("quarantine-transfer-refused", reason=reason)

    def transfer_review_step(self):
        """QUARANTINED, before any record, first successor process only: create the ONE review task once; when it settled
        DONE, try the (never-retried-by-restart) transfer. Throttled; a refusal consumes nothing."""
        cfg = self.cfg
        if not _transfer_lineage_active(cfg) or os.path.lexists(_transition_path(cfg)) or _transfer_first_boot(cfg, me=True) is None:
            return
        now = time.monotonic()
        if self._tr_review_last is not None and now - self._tr_review_last < TRANSFER_STEP_EVERY:
            return
        self._tr_review_last = now
        t = self.state["tasks"].get(TRANSFER_REVIEW_ID)
        if t is None:
            if any(e.get("task_id") == TRANSFER_REVIEW_ID for e in _qled_events(cfg)):
                return  # a review was already created once: never a second
            if (self.state.get("handoff") or {}).get("request") or any(
                    isinstance(x, dict) and (x.get("status") == "RUNNING" or x.get("child")) for x in self.state["tasks"].values()):
                return
            try:
                _transfer_successor(cfg)
                self.state["tasks"][TRANSFER_REVIEW_ID] = _transfer_review_task(cfg)
            except (GateError, ValueError, OSError) as e:
                return self._tr_refuse(f"review not created: {str(e)[:200]}")
            self.store.save(self.state)
            return self._tr_event("transfer-review-created", task_id=TRANSFER_REVIEW_ID)
        if t.get("status") == "DONE":
            return self._transition_consume()
        if t.get("status") in ("BLOCKED", "FAILED"):
            self._tr_refuse("the single successor review did not end APPROVED: quarantine stays closed, no retry")

    def _transition_attestation(self):
        return {"pid": os.getpid(), "boot_nonce": _PROCESS_BOOT_NONCE, "code_sha256": CODE_SHA, "at": now_iso()}

    def _transition_consume(self):
        cfg = self.cfg
        if not self.wlock.acquire({"pid": os.getpid(), "transition": "consume"}):
            return self._tr_refuse("the repository writer lock is held")
        created = None
        try:
            try:  # local deterministic preflight only; provider CI is observed AFTER consumption
                ready = transfer_preflight(cfg, rlock_held=True, wlock_held=True)
            except Exception as e:
                return self._tr_refuse(f"{type(e).__name__}: {str(e)[:300]}")
            try:
                tid = uuid.uuid4().hex
                pre = _transfer_write_pre_image(cfg, tid, ready["old"], ready["review_files"])
                old, new, me = ready["old"]["binding"], ready["successor"], self._transition_attestation()
                created = _transition_write(cfg, {
                    "schema": 1, "kind": TRANSFER_KIND, "transition_id": tid, "stage": "TRANSFER_CONSUMED",
                    "consumed": True, "created_at": now_iso(), "pre_image": pre,
                    "old": {"code_sha256": TRANSFER_OLD_CODE_SHA, "commit": TRANSFER_OLD_COMMIT, "pid": old["old_pid"],
                            "boot_nonce": old["old_nonce"], "entered_offset": old["entered_offset"],
                            "entered_event_sha256": old["entered_event_sha256"]},
                    "new": {"code_sha256": new["code_sha256"], "commit": new["commit"], "parent": new["parent"],
                            "test_sha256": new["test_sha256"], "diff_sha256": new["diff_sha256"], "review": ready["review"]},
                    "first_boot": me, "attested": dict(me), "boot_epoch": 1, "restart_used": False,
                    "ci": {"observed": False, "at": None, "runs": None}, "s0_slot": {"state": "UNUSED", "task_id": None, "at": None},
                    "verified": {"docs": None, "receipt_sha256": None, "commit": None, "at": None}}, create=True)
                self.store.save(self.state)  # state save stays under the writer lock
                _transition_audit(self.store, created)
            except Exception as e:  # nothing is retried here: a created record is spent, an absent one consumed nothing
                self._tr_event("quarantine-transfer-failed", reason=f"{type(e).__name__}: {str(e)[:300]}")
        finally:
            self.wlock.release()
        if created is not None:
            self._transition_ci(created)

    def _transition_ci(self, rec):
        """The post-consumption provider observations of A and D (pinned runs) and C; all are persisted before S0_REBIND."""
        if rec["stage"] != "TRANSFER_CONSUMED" or rec["ci"]["observed"]:
            return rec
        try:
            runs = _transfer_ci_observe(self.cfg, rec)
        except Exception as e:  # an outage never mints a new transfer: quarantine simply stays closed
            self._tr_event("quarantine-transfer-ci-unavailable", transition_id=rec["transition_id"], reason=str(e)[:300])
            return rec
        if not self.wlock.acquire({"pid": os.getpid(), "transition": "ci"}):
            self._tr_event("quarantine-transfer-refused", reason="the repository writer lock is held")
            return rec
        try:
            rec = _transition_write(self.cfg, {**rec, "stage": "S0_REBIND", "ci": {"observed": True, "at": now_iso(), "runs": runs}})
            _transition_audit(self.store, rec)
        except Exception as e:
            self._tr_event("quarantine-transfer-failed", reason=f"{type(e).__name__}: {str(e)[:300]}")
        finally:
            self.wlock.release()
        return rec

    def _transition_reboot(self, rec):
        """A later process under an existing record: at most one same-code recovery restart, and only before the S0 slot
        consumption is persisted. After that (VERIFIED, ACTIVE) every restart is denied; the record is left untouched."""
        cfg = self.cfg
        _transition_audit(self.store, rec)

        def deny(why):
            self._tr_event("quarantine-transfer-denied", transition_id=rec["transition_id"], stage=rec["stage"], reason=why)

        bad = _transition_bound_problem(cfg, rec, full=True)
        if bad:
            return deny(bad)
        if rec["s0_slot"]["state"] == "CONSUMED" or rec["stage"] in ("VERIFIED", "ACTIVE"):
            return deny("restart after S0 slot consumption is not permitted")
        if rec["restart_used"]:
            return deny("the single same-code recovery restart is already spent")
        if not self.wlock.acquire({"pid": os.getpid(), "transition": "reattest"}):
            return deny("the repository writer lock is held")
        try:
            successor = _transfer_successor(cfg)
            if any(successor[k] != rec["new"][k] for k in ("commit", "parent", "test_sha256", "diff_sha256")) \
                    or successor["code_sha256"] != rec["new"]["code_sha256"]:
                return deny("the successor commit/hash binding drifted")
            h = self.state.get("handoff") or {}
            if _other_runner_pids(cfg) or h.get("request") or h.get("quarantine") or any(
                    isinstance(t, dict) and (t.get("status") == "RUNNING" or t.get("child")) for t in self.state["tasks"].values()):
                return deny("another runner, a worker or an open handoff exists")
            rec = _transition_write(cfg, {**rec, "attested": self._transition_attestation(),
                                          "boot_epoch": rec["boot_epoch"] + 1,
                                          "restart_used": True})
            self.store.save(self.state)
            _transition_audit(self.store, rec)
        except Exception as e:
            return deny(f"{type(e).__name__}: {str(e)[:300]}")
        finally:
            self.wlock.release()
        self._transition_ci(rec)

    def _transition_consume_slot(self, t):
        """Persist the S0 slot consumption BEFORE dispatch (the caller holds the writer lock)."""
        rec = _load_transition(self.cfg)
        att = rec["attested"] if rec else {}
        if not (rec and rec["stage"] == "S0_REBIND" and rec["s0_slot"]["state"] == "UNUSED"
                and att["pid"] == os.getpid() and att["boot_nonce"] == _PROCESS_BOOT_NONCE
                and _transition_bound_problem(self.cfg, rec, full=True) is None):
            raise GateError("dual rebind slot invalid or already consumed")
        _transition_write(self.cfg, {**rec, "s0_slot": {"state": "CONSUMED", "task_id": t["id"], "at": now_iso()}})
        self._tr_event("quarantine-transfer-slot-consumed", transition_id=rec["transition_id"], task_id=t["id"])

    # --- S0 rebind hash recovery overlay (2026-10-28): ONE reload, one overlay, one correction; nothing here rewrites the original record
    def _recovery_boot(self, rec):
        """Replacement code under the original record. Opens the ONE reload window for this process only; any later process,
        or any process once the overlay exists, is denied (no second reload, no restart)."""
        cfg = self.cfg
        try:
            ov = _recovery_load(cfg)
        except GateError as e:
            return self._tr_event("quarantine-recovery-denied", reason=str(e)[:300])
        me = {"schema": 1, "kind": "s0-d16-rebind-recovery-first-boot", "pid": os.getpid(), "boot_nonce": _PROCESS_BOOT_NONCE,
              "code_sha256": CODE_SHA, "at": now_iso()}
        if ov is not None:
            return self._tr_event("quarantine-recovery-denied", transition_id=rec["transition_id"],
                                  reason="restart after the recovery record exists is not permitted")
        if _recovery_first_boot(cfg, me=True) is not None:
            return  # this very process (PID + boot nonce) already holds the window
        try:
            if os.path.lexists(Path(cfg.home) / RECOVERY_BOOT_NAME) or any(
                    e.get("kind") == "quarantine-recovery-first-boot" for e in _qled_events(cfg)):
                raise GateError("a replacement process already used the one reload window")
            _atomic_create_exclusive(Path(cfg.home) / RECOVERY_BOOT_NAME, json.dumps(me, sort_keys=True).encode())
        except (GateError, OSError) as e:
            return self._tr_event("quarantine-recovery-denied", reason=f"no second reload: {str(e)[:200]}")
        self._tr_event("quarantine-recovery-first-boot", pid=me["pid"], boot_nonce=me["boot_nonce"], code_sha256=CODE_SHA)

    def _recovery_create(self, rec):
        """Create the overlay once: local preflight, then provider CI for E and C, then the exclusive atomic create."""
        cfg = self.cfg
        if _recovery_first_boot(cfg, me=True) is None:
            return
        if not self.wlock.acquire({"pid": os.getpid(), "transition": "recovery"}):
            return self._tr_refuse("the repository writer lock is held")
        try:
            try:
                ready = recovery_preflight(cfg, self.state, rlock_held=True, wlock_held=True)
                succ = ready["successor"]
                owner_ci = _observe_ci_for_commit(cfg, RECOVERY_OWNER_COMMIT, run_id=RECOVERY_OWNER_CI_RUN, opener=_ci_opener)
                runner_ci = _observe_ci_for_commit(cfg, succ["commit"], run_id=ready["c_run"], opener=_ci_opener)
            except Exception as e:  # nothing is consumed: this process may retry; no other process can
                return self._tr_refuse(f"recovery not bound: {type(e).__name__}: {str(e)[:300]}")
            try:
                rid, me = uuid.uuid4().hex, self._transition_attestation()
                docs = tuple((Path(cfg.repo) / p).read_bytes() for p in S0_DOC_PATHS)
                pre = _recovery_write_pre_image(cfg, rid, ready["rec"], docs, {"review/" + n: b for n, b in ready["preload_files"].items()})
                created = _recovery_write(cfg, {
                    "schema": 1, "kind": RECOVERY_KIND, "recovery_id": rid, "stage": "BOUND", "created_at": now_iso(),
                    "orig": ready["stub"]["orig"],
                    "owner": {"path": RECOVERY_OWNER_PATH, "sha256": RECOVERY_OWNER_SHA, "commit": RECOVERY_OWNER_COMMIT, "ci": owner_ci},
                    "pre_image": pre,
                    "runner": {"code_sha256": succ["code_sha256"], "commit": succ["commit"], "parent": succ["parent"],
                               "test_sha256": succ["test_sha256"], "diff_sha256": succ["diff_sha256"],
                               "preload_sha256": ready["preload"]["preload_sha256"],
                               "preload_output_sha256": ready["preload"]["preload_output_sha256"], "ci": runner_ci},
                    "attested": me, "correction": {"state": "UNUSED", "task_id": None, "at": None},
                    "verified": {"docs": None, "receipt_sha256": None, "commit": None, "at": None}}, create=True)
                self.store.save(self.state)
                self._tr_event("quarantine-recovery-stage", recovery_id=created["recovery_id"], stage=created["stage"])
            except Exception as e:  # a created overlay is spent; an absent one consumed nothing
                self._tr_event("quarantine-recovery-failed", reason=f"{type(e).__name__}: {str(e)[:300]}")
        finally:
            self.wlock.release()

    def _recovery_consume_correction(self, t):
        """Persist the correction attempt BEFORE dispatch (the caller holds the writer lock). Never touches the original slot."""
        rec, ov = _load_transition(self.cfg), _recovery_load(self.cfg)
        att = ov["attested"] if ov else {}
        if not (rec and ov and ov["stage"] == "BOUND" and ov["correction"]["state"] == "UNUSED" and t.get("id") == RECOVERY_ID
                and att["pid"] == os.getpid() and att["boot_nonce"] == _PROCESS_BOOT_NONCE
                and _transition_bound_problem(self.cfg, rec, full=True) is None):
            raise GateError("recovery correction slot invalid or already consumed")
        _recovery_write(self.cfg, {**ov, "stage": "CORRECTION_CONSUMED",
                                   "correction": {"state": "CONSUMED", "task_id": t["id"], "at": now_iso()}})
        self._tr_event("quarantine-recovery-stage", recovery_id=ov["recovery_id"], stage="CORRECTION_CONSUMED")

    def recovery_step(self):
        """Create the overlay (first replacement process only), then advance CORRECTION_CONSUMED -> VERIFIED -> ACTIVE from
        evidence, never from a command; throttled and lock-gated."""
        cfg = self.cfg
        if not _transfer_lineage_active(cfg):
            return
        now = time.monotonic()
        if self._rc_last is not None and now - self._rc_last < TRANSFER_STEP_EVERY:
            return
        self._rc_last = now
        try:
            rec, ov = _load_transition(cfg), None
            if rec is None or rec["new"]["code_sha256"] == CODE_SHA:
                return
            ov = _recovery_load(cfg)
        except GateError:
            return
        if ov is None:
            return self._recovery_create(rec)
        att = ov["attested"]
        if not (ov["stage"] in ("CORRECTION_CONSUMED", "VERIFIED") and att["pid"] == os.getpid()
                and att["boot_nonce"] == _PROCESS_BOOT_NONCE):
            return
        if any(t.get("status") == "RUNNING" for t in self.state["tasks"].values()):
            return
        if not self.wlock.acquire({"pid": os.getpid(), "transition": "recovery-advance"}):
            return
        try:
            if ov["stage"] == "CORRECTION_CONSUMED":
                try:
                    ev = _recovery_verified(cfg, rec, ov, self.state["tasks"])
                except GateError:
                    return
                new = {**ov, "stage": "VERIFIED", "verified": {**ev, "at": now_iso()}}
            else:
                problem = _recovery_probe_problem(cfg, rec, ov, self.state["tasks"])
                if problem:
                    return self._tr_event("quarantine-recovery-probe-failed", recovery_id=ov["recovery_id"], reason=problem[:300])
                new = {**ov, "stage": "ACTIVE"}
            done = _recovery_write(cfg, new)
            self._tr_event("quarantine-recovery-stage", recovery_id=done["recovery_id"], stage=done["stage"])
        except Exception as e:
            self._tr_event("quarantine-recovery-failed", reason=f"{type(e).__name__}: {str(e)[:300]}")
        finally:
            self.wlock.release()

    def transition_step(self):
        """Advance S0_REBIND -> VERIFIED -> ACTIVE from evidence, never from a command; throttled and lock-gated."""
        now = time.monotonic()
        if self._tr_last is not None and now - self._tr_last < TRANSFER_STEP_EVERY:
            return
        self._tr_last = now
        try:
            rec = _load_transition(self.cfg)
        except GateError:
            return
        att = rec["attested"] if rec else {}
        if rec and rec["new"]["code_sha256"] != CODE_SHA:
            return  # the overlay (recovery_step) governs; the original record is never advanced by replacement code
        if not (rec and rec["stage"] in ("S0_REBIND", "VERIFIED") and att["pid"] == os.getpid()
                and att["boot_nonce"] == _PROCESS_BOOT_NONCE) or rec["s0_slot"]["state"] != "CONSUMED":
            return
        if any(t.get("status") == "RUNNING" for t in self.state["tasks"].values()):
            return
        if not self.wlock.acquire({"pid": os.getpid(), "transition": "advance"}):
            return
        try:
            if rec["stage"] == "S0_REBIND":
                try:
                    ev = _transition_verified(self.cfg, rec, self.state["tasks"])
                except GateError:
                    return
                new = {**rec, "stage": "VERIFIED", "verified": {**ev, "at": now_iso()}}
            else:
                problem = _transition_probe_problem(self.cfg, rec, self.state["tasks"])
                if problem:
                    return self._tr_event("quarantine-transfer-probe-failed", transition_id=rec["transition_id"], reason=problem[:300])
                new = {**rec, "stage": "ACTIVE"}
            _transition_audit(self.store, _transition_write(self.cfg, new))
        except Exception as e:
            self._tr_event("quarantine-transfer-failed", reason=f"{type(e).__name__}: {str(e)[:300]}")
        finally:
            self.wlock.release()

    def finish(self):
        reason = "STOP" if self.state["control"] == "STOP" else "signal"
        hp = getattr(self, "hp", None)
        if hp is not None and hp.poll() is None:  # request stays durable; the next start reconciles it
            self.stop_handoff_child(hp)
        self.state["runner"]["heartbeat_at"] = now_iso()
        self.state["runner"]["stopped_at"] = now_iso()
        self.store.event("runner-exit", reason=reason)
        self.store.save(self.state)

    def recover(self):
        """Idempotent: RUNNING tasks only exist if a prior runner died mid-attempt."""
        for t in self.state["tasks"].values():
            if t["status"] != "RUNNING":
                continue
            if t.get("verify_checkpoint") and t.get("stage") == "verifying":
                self.reap(t.get("verify_child"))
                t["verify_child"] = None
                t.update(status="QUEUED", stage="verify_pending", child=None)
                self.state["recoveries"] += 1
                self.store.event("verification-recovered", t["verify_checkpoint"]["op"], task_id=t["id"])
                continue
            reaped = self.reap(t.get("child"))
            op = f"{t['id']}:{t['attempts']}"
            if s0_dual_rebind_marked(t) or _recovery_marked(t) or t["id"] == TRANSFER_REVIEW_ID:  # one-shot: never requeued or retried after an interruption
                self.state["recoveries"] += 1
                t.update(status="BLOCKED", blocked_reason=("TRANSFER_REVIEW_INTERRUPTED" if t["id"] == TRANSFER_REVIEW_ID
                                                           else "S0_RECOVERY_INTERRUPTED" if _recovery_marked(t)
                                                           else "S0_DUAL_REBIND_INTERRUPTED"), child=None, stage=None,
                         updated_at=now_iso(), last_error="interrupted by runner crash/restart; the single attempt is spent")
                self.store.event("recovered-interrupted", op, task_id=t["id"], orphan_reaped=reaped, blocked=True)
                continue
            self.state["recoveries"] += 1
            t["child"], t["stage"] = None, None
            self.store.event("recovered-interrupted", op, task_id=t["id"], orphan_reaped=reaped)
            self.requeue_or_fail(t, "interrupted by runner crash/restart")
        if (self.state.get("handoff") or {}).get("request"):  # even if continuation was switched off since: never dispatch under it
            self.handoff_recover()
        self.store.save(self.state)
        lp = writer_lock_path(self.cfg.home, self.cfg.repo)
        if FileLock.probe(lp) == "held":  # an orphan we could not reap still owns the repo: dispatch will wait
            self.store.event("writer-lock-held-after-recovery", owner=FileLock(lp).owner())

    def reap(self, child):
        if not child:
            return False
        try:
            os.kill(child["pid"], 0)
            start = subprocess.run(["ps", "-o", "lstart=", "-p", str(child["pid"])],
                                   capture_output=True, text=True).stdout.strip()
        except OSError:
            return False
        if start != child.get("lstart"):
            return False  # pid reused by an unrelated process: leave it alone
        self.kill_group(child["pid"])
        return True

    @staticmethod
    def kill_group(pid, grace=5.0):
        for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 2.0)):
            try:
                os.killpg(pid, sig)
            except OSError:
                return
            end = time.time() + wait
            while time.time() < end:
                try:
                    os.killpg(pid, 0)
                except OSError:
                    return
                time.sleep(0.1)

    # --- per-tick work
    def tick(self):
        self.ingest_queue()
        self.apply_commands()
        self.check_baseline()
        self.heartbeat()
        self.transition_step()
        self.recovery_step()
        self.transfer_review_step()
        if self.state["control"] == "RUN" and self.state["health"]["status"] == "OK" and not self.handoff_open() \
                and not (self.state.get("handoff") or {}).get("quarantine"):
            t = self.next_ready()
            if t:
                self.dispatch(t)
        self.handoff_step()
        self.refresh_ci()
        self.store.save(self.state)

    # --- automatic continuation: the runner is only the mechanical trigger; OpenClaw chooses the task
    def handoff_state(self):
        return self.state.setdefault("handoff", {"status": "idle", "detail": "no continuation requested yet", "fingerprint": None,
                                                 "settled": True, "attempts": 0, "request": None, "quarantine": None,
                                                 "outcome": None, "last": None, "updated_at": now_iso()})

    def handoff_open(self):
        """True while an orchestrator request is open: nothing may ingest, dispatch or enqueue meanwhile."""
        return bool((self.state.get("handoff") or {}).get("request"))

    def set_handoff(self, status, detail):
        h = self.handoff_state()
        if (h["status"], h["detail"]) != (status, detail):
            self.store.event("handoff-state", status=status, detail=detail[:300])
            h.update(status=status, detail=detail[:300], updated_at=now_iso())

    def handoff_step(self):
        if not self.cfg.orchestrator_bin:
            return
        h = self.handoff_state()
        if h["request"]:
            return self.handoff_poll(h)
        if h.get("quarantine"):  # a late gateway turn may be alive: no turn, no ingress, whatever else changes; only `rearm` lifts it
            self.hold_queue(h["quarantine"])
            return
        if _transition_mode(self.cfg)[0] in ("HOLD", "LANE", "RECOVERY"):  # no continuation turn before the transfer is ACTIVE
            return
        st = self.state
        if st["control"] != "RUN":
            return self.set_handoff("waiting", f"runner control is {st['control']}; no continuation started")
        if st["health"]["status"] != "OK":
            return self.set_handoff("blocked", f"baseline unhealthy ({st['health'].get('code') or st['health']['status']}); no continuation")
        live = [t for t in st["tasks"].values() if t["status"] == "RUNNING" or (t["status"] == "QUEUED" and not t.get("gate_reason"))]
        if live:  # a QUEUED task the gate holds (gate_reason set) is not work in progress: it must not stall selection forever
            return self.set_handoff("waiting", "worker task queued or running; continuation deferred")
        if self.store.pending_commands() or any((self.cfg.home / "queue").glob("*.json")):
            return  # let the next tick apply commands / ingest before deciding
        if FileLock.probe(writer_lock_path(self.cfg.home, self.cfg.repo)) != "free":
            return self.set_handoff("waiting", "repo writer lock held; continuation deferred")
        fp = state_fingerprint(self.cfg, st["tasks"])
        if fp == h["fingerprint"]:
            if h["settled"] and (h.get("outcome") or {}).get("detail", "").startswith("ORCHESTRATOR_RESPONSE_INVALID:") \
                    and h["attempts"] < 2:
                h["settled"] = False  # one bounded retry of an invalid envelope; no task was adopted
                h["retry_at"] = time.time() + min(self.cfg.backoff_cap, self.cfg.backoff_base * 2)
                self.store.event("handoff-invalid-retry-scheduled", attempts=h["attempts"], retry_at=h["retry_at"])
            if h["settled"]:  # this exact state was already handed off once: never loop on unchanged state
                if h["outcome"]:
                    self.set_handoff(**h["outcome"])
                return
        else:
            h.update(fingerprint=fp, settled=False, attempts=0, outcome=None)  # a new state is offered; quarantine was handled above
        if time.time() < h.get("retry_at", 0):
            return
        h.pop("retry_at", None)
        self.handoff_start(h, fp)

    def handoff_rearm(self):
        """Owner command: forget the settled outcome so the current state is offered to the orchestrator once more."""
        h = self.handoff_state()
        if h["request"]:
            return self.store.event("handoff-rearm-refused", reason="a request is open")
        if self.state["control"] != "RUN" or FileLock.probe(writer_lock_path(self.cfg.home, self.cfg.repo)) != "free":
            return self.store.event("handoff-rearm-refused", reason="runner not running or writer lock held: nothing verified")
        try:
            repo_state(self.cfg.repo)
        except Exception as e:
            return self.store.event("handoff-rearm-refused", reason=f"repo snapshot unavailable: {str(e)[:80]}")
        h.update(fingerprint=None, settled=False, attempts=0, outcome=None, quarantine=None)
        h.pop("retry_at", None)
        self.set_handoff("waiting", "re-armed by owner; continuation will be requested on the next idle tick")
        self.store.event("handoff-rearmed")

    def handoff_start(self, h, fp):
        try:
            pre_repo = repo_state(self.cfg.repo)  # lets settle prove the read-only turn wrote nothing
        except Exception as e:
            return self.set_handoff("blocked", f"REPO_SNAPSHOT_UNAVAILABLE: cannot prove a read-only turn ({str(e)[:100]})")
        h["attempts"] += 1
        h["seq"] = h.get("seq", 0) + 1  # never reused, even after a re-arm: a request id names exactly one turn
        req_id = f"handoff-{fp[:12]}-{h['seq']}"
        stem = self.cfg.home / "runs" / req_id
        msg, out, err = Path(f"{stem}.msg.md"), Path(f"{stem}.out"), Path(f"{stem}.err")
        tasks = self.state["tasks"]
        summary = ", ".join(f"{i}:{t['status']}" + (f"({t['blocked_reason']})" if t.get("blocked_reason") else "")
                            for i, t in sorted(tasks.items()))[:1500] or "no tasks recorded"
        atomic_write(msg, handoff_prompt(self.cfg, req_id, fp, summary).encode())
        h["request"] = {"id": req_id, "fingerprint": fp, "started_at": now_iso(), "pre_ids": sorted(tasks),
                        "deadline": time.time() + self.cfg.handoff_timeout + 30, "msg": str(msg), "out": str(out),
                        "err": str(err), "child": None, "pre_repo": pre_repo, "foreign_cmds": []}
        self.set_handoff("coordinating", f"orchestrator turn {req_id} in flight")
        self.store.save(self.state)  # request is durable BEFORE the CLI exists, so a crash reconciles instead of duplicating
        self.store.event("handoff-request", req_id, fingerprint=fp[:12], seq=h["seq"])
        binpath = str(self.cfg.orchestrator_bin)
        env = {k: os.environ[k] for k in ORCH_ENV_KEEP if k in os.environ}
        env |= {k: v for k, v in os.environ.items() if k.startswith("OPENCLAW_")}
        env["PATH"] = f"{Path(binpath).parent}:/usr/bin:/bin:/usr/sbin:/sbin"  # node lives next to the CLI
        blocker = planner_policy_blocker()  # the Gateway enforces the tool policy, not the CLI sandbox below
        if blocker:
            return self.handoff_settle(h, "policy-refused", None, blocker)
        prefix, why = self.handoff_sandbox_prefix(req_id)
        if prefix is None:  # defense-in-depth only: confines this CLI client, NOT the separate Gateway turn
            return self.handoff_settle(h, "sandbox-refused", None, why)
        cmd = [*prefix, binpath, "agent", "--agent", ORCH_AGENT, "--session-key", ORCH_SESSION, "--message-file", str(msg),
               "--json", "--timeout", str(int(self.cfg.handoff_timeout))]  # argv list, no shell: paths with spaces are safe
        with open(out, "wb") as fo, open(err, "wb") as fe:
            try:
                p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe, cwd=self.cfg.home,
                                     start_new_session=True, env=env)
            except OSError as e:
                return self.handoff_settle(h, "spawn-failed", None, f"spawn failed: {e}")
        lstart = subprocess.run(["ps", "-o", "lstart=", "-p", str(p.pid)], capture_output=True, text=True).stdout.strip()
        h["request"]["child"] = {"pid": p.pid, "lstart": lstart}
        self.hp = p
        self.store.save(self.state)

    def handoff_sandbox_prefix(self, req_id):
        """Defense-in-depth Seatbelt for the orchestrator CLI client only: no file writes under the runner home (queue,
        commands, state, acceptances) or .git from this process. It does NOT confine the separate Gateway turn; that
        is bounded only by the planner tool and runtime policy checked in planner_policy_blocker. Reads and network stay open
        (the CLI must reach the Gateway). Returns (argv prefix, None), or (None, reason) when it cannot be applied."""
        if self.cfg.sandbox == "off":
            return None, "sandbox is off (sandbox=off); a sandbox is required for the orchestrator turn"
        if sys.platform != "darwin" or not os.access(SANDBOX_EXEC, os.X_OK):
            return None, f"{SANDBOX_EXEC} unavailable; a sandbox is required for the orchestrator turn"
        deny = [str(Path(self.cfg.home).resolve()), str((Path(self.cfg.repo) / ".git").resolve())]
        q = lambda p: '"' + p.replace("\\", "\\\\").replace('"', '\\"') + '"'
        prof = Path(self.cfg.home) / "runs" / f"{req_id}.sb"
        try:
            atomic_write(prof, ("(version 1)\n(allow default)\n(deny file-write* " +
                                " ".join(f"(subpath {q(d)})" for d in deny) + ")\n").encode())
        except OSError as e:
            return None, f"could not write the sandbox profile: {e}"[:200]
        return [SANDBOX_EXEC, "-f", str(prof)], None

    def handoff_poll(self, h):
        req, p = h["request"], getattr(self, "hp", None)
        if p is None or p.pid != (req.get("child") or {}).get("pid"):
            return self.handoff_recover()  # request without a live handle in this process: reconcile, never re-call blindly
        rc = p.poll()
        if rc is None:
            if self.state["control"] != "RUN":  # owner PAUSE/STOP wins: the turn is killed and its output never used
                self.stop_handoff_child(p)
                return self.handoff_settle(h, "paused", None, f"runner control became {self.state['control']} during the turn")
            if time.time() > req["deadline"]:
                self.stop_handoff_child(p)
                self.handoff_settle(h, "timeout", None, f"no result within {int(self.cfg.handoff_timeout)}s")
            return
        self.handoff_settle(h, "exited", rc, f"exit {rc}")

    @staticmethod
    def stop_handoff_child(p):
        """The orchestrator turn is read-only, so its whole process group is simply killed and reaped."""
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        p.wait()

    def handoff_recover(self):
        """Crash/restart (or lost handle): reap any orphan CLI, then judge the request by queue evidence first."""
        h = self.handoff_state()
        req = h.get("request")
        if not req:
            return
        self.reap(req.get("child"))
        self.hp = None
        self.handoff_settle(h, "recovered", None, "orchestrator turn interrupted by runner restart")

    def handoff_settle(self, h, how, rc, why):
        req = h["request"]
        clean = how == "exited" and rc == 0
        # Anything that reached the runner's inputs while the request was open was not produced by the proposal.
        held = self.hold_queue(f"external queue ingress while {req['id']} was open")
        foreign = req.get("foreign_cmds") or []
        try:
            wrote = diff_state(req["pre_repo"], repo_state(self.cfg.repo)) if req.get("pre_repo") else ["<no pre-snapshot>"]
        except Exception as e:
            wrote = [f"<snapshot failed: {str(e)[:60]}>"]
        drift = state_fingerprint(self.cfg, self.state["tasks"]) != req["fingerprint"]
        model, prop, why_bad, harness_bad = None, None, None, None
        if clean:
            try:
                raw = Path(req["out"]).read_bytes()
                text, model, harness = parse_handoff_envelope(raw)
                if harness != PLANNER_RUNTIME:  # the turn ran under another runtime than the one the policy check proved
                    harness_bad = f"agentHarnessId {str(harness)[:40]!r} is not {PLANNER_RUNTIME!r}"
                    raise HandoffError(harness_bad)
                text, completed_brace = complete_handoff_outer_brace(text)
                prop = parse_handoff_proposal(text, req["id"])
                if completed_brace:
                    self.store.event("handoff-json-brace-completed", req["id"],
                                     reason="single missing outer TASK brace; strict schema and task gates still applied")
            except OSError:
                why_bad = "CLI output file unreadable"
            except HandoffError as e:
                why_bad = str(e)
        h["request"], self.hp = None, None
        h["quarantine"] = None
        enqueued = None
        if how != "exited" or rc != 0:
            if how not in ("spawn-failed", "sandbox-refused", "policy-refused"):  # no CLI ran for those; otherwise the gateway may keep running a turn whose CLI was killed or failed
                h["quarantine"] = f"{how}: late gateway turn possible; owner re-arm required before any enqueue"
            err = ""
            try:
                err = Path(req["err"]).read_bytes()[-200:].decode(errors="replace").strip()
            except OSError:
                pass
            code = {"timeout": "ORCHESTRATOR_TIMEOUT", "recovered": "ORCHESTRATOR_TURN_INTERRUPTED",
                    "paused": "ORCHESTRATOR_TURN_ABORTED_BY_OWNER", "sandbox-refused": "ORCHESTRATOR_SANDBOX_UNAVAILABLE"}.get(how, "ORCHESTRATOR_CALL_FAILED")
            outcome = {"status": "blocked", "detail": f"{code}: {why}; no automatic retry; {err}"[:300]}
            if how == "policy-refused":
                outcome["detail"] = f"{why}; no automatic retry"[:300]
        elif harness_bad:
            # a non-openclaw turn may have had tools the policy never covered: its proposal is discarded and the owner re-arms
            h["quarantine"] = "RUNTIME_HARNESS_MISMATCH: owner re-arm required before any turn or enqueue"
            outcome = {"status": "blocked", "detail": f"RUNTIME_HARNESS_MISMATCH: {harness_bad}; proposal discarded"[:300]}
        elif held or foreign or wrote or drift:
            # nothing in the runner's own lifecycle moves during a request, so any change came from outside it
            # (the gateway turn, or an owner edit that cannot be told apart): never re-ask or adopt, quarantine
            h["quarantine"] = "UNATTRIBUTED_CHANGES_DURING_HANDOFF: owner re-arm required before any turn or enqueue"
            outcome = {"status": "blocked", "detail": ("UNATTRIBUTED_CHANGES_DURING_HANDOFF: "
                       f"queue files held {held[:3]}, commands {foreign[:3]}, repo paths {wrote[:3]}"
                       f"{', owner/acceptance/repo state drift' if drift else ''}; proposal discarded")[:300]}
        elif why_bad:
            outcome = {"status": "blocked", "detail": f"ORCHESTRATOR_RESPONSE_INVALID: {why_bad}"[:300]}
        elif prop["kind"] == "TASK":
            try:
                enqueued = self.enqueue_proposal(prop["task"])
                outcome = {"status": "waiting", "detail": f"enqueued {enqueued} by the runner from a validated proposal"}
            except (ValueError, OSError) as e:
                outcome = {"status": "blocked", "detail": f"PROPOSAL_REFUSED: {e}"[:300]}
        else:
            outcome = {"status": HANDOFF_STATUS[prop["kind"]], "detail": f"{prop['kind']}: {prop['reason'].strip()}"[:300]}
        h["last"] = {"id": req["id"], "finished_at": now_iso(), "how": how, "exit": rc,
                     "claim": prop["kind"] if prop else None, "new_tasks": [enqueued] if enqueued else [],
                     "model_reported": model}
        self.store.event("handoff-result", req["id"], how=how, exit=rc, claim=h["last"]["claim"], new_tasks=h["last"]["new_tasks"],
                         outcome=outcome["detail"][:120], quarantine=h["quarantine"])
        h.update(settled=True, outcome=outcome)
        self.set_handoff(**outcome)
        self.store.save(self.state)  # the enqueued task and the closed request become durable in ONE atomic write

    def hold_queue(self, why):
        """Move every pending queue file aside so it is never ingested or credited to a handoff; returns the names."""
        held = []
        for f in sorted((self.cfg.home / "queue").glob("*.json")):
            try:
                f.rename(f.with_suffix(".held"))
            except OSError:
                continue
            held.append(f.name)
            self.store.event("queue-held", file=f.name, reason=why)
        return held

    def enqueue_proposal(self, raw_task):
        """The runner itself validates one proposed task, applies the gate and records it durably (no queue file)."""
        task = {**raw_task, "created_at": now_iso()}
        t = validate_task(task, self.cfg)
        if t["id"] in self.state["tasks"]:
            raise ValueError(f"task id already exists: {t['id']}")
        try:
            verify_receipt(self.cfg, t["module"])
        except GateError:
            pass  # no verified acceptance: the module is still open for work
        else:
            raise ValueError(f"{t['module']} already has a verified accepted receipt: no orchestrator-proposed task of any role")
        if t["role"] == "code-review" and not t["review_of"]:
            raise ValueError("an orchestrator-proposed code-review must bind review_of (write task id + changed-file hashes)")
        if t.get("review_retry_of"):
            raise ValueError("operational review retries require the owner CLI and an audited prior BLOCKED record")
        if t.get("accounting_recovery_of"):
            raise ValueError("the one accounting recovery requires the owner CLI and its audited prior BLOCKED record")
        if (s0_marked(t) or s0_touches(t) or s0_doc_marked(t) or s0_refresh_marked(t) or s0_doc_touches(t)
                or s0_rebind_marked(t) or s0_test_marked(t) or s0_loop_marked(t) or s0_qa_marked(t)
                or s0_dual_rebind_marked(t) or _recovery_marked(t)):
            raise ValueError("tasks for the MOD004-S0, MOD004-S0-DOC, MOD004-S0-DOC-REFRESH, MOD004-S0-DOC-REBIND, "
                             "MOD004-S0-TEST-REMEDIATION, MOD004-S0-LOOP-REBIND, MOD004-S0-QA-EVIDENCE or "
                             "MOD004-S0-D16-EVIDENCE-REBIND files require the owner CLI; the planner cannot propose them")
        proposal_restrictions(self.cfg, t)
        review_binding(self.cfg, t, self.state["tasks"], require_changed=True)
        if t.get("remediation_of"):
            w = self.state["tasks"].get(t["remediation_of"])
            if product_loop_eligible(self.state["tasks"], t) and product_policy_root(self.state["tasks"], w):
                if not (w and w.get("module") == t["module"] and w.get("role") in WRITE_ROLES
                        and product_rejection(self.state["tasks"], w)):
                    raise ValueError("remediation_of must name a write of this module whose bound review requested changes "
                                     "or whose recorded verification failed")
            elif not (w and w.get("module") == t["module"] and w.get("role") in WRITE_ROLES and w.get("status") == "DONE"
                      and review_verdict(self.state["tasks"], w["id"]) == "CHANGES_REQUESTED"):
                raise ValueError("remediation_of must name a DONE write of this module whose bound review requested changes")
            if not all(in_scope(p, w.get("allowed_paths") or []) for p in t["allowed_paths"]):
                raise ValueError("remediation must stay inside the reviewed write's allowed paths")
        t["source"] = "handoff"
        reason = gate_reason(self.cfg, t, self.state["tasks"])
        if reason:
            raise ValueError(f"refused by gate: {reason}")
        stamp_product_remediation(self.state["tasks"], t)
        self.state["tasks"][t["id"]] = t  # persisted by the caller together with the closed request
        self.store.event("task-queued", f"{t['id']}:0", task_id=t["id"], module=t["module"], role=t["role"], source="handoff")
        return t["id"]

    def refresh_ci(self):
        """Periodic read-only gh observation, persisted to out-of-repo ci.json. Bounded by CI_BUDGET and never
        raises; on failure the last successful observation is kept and tagged with an error code."""
        if self.cfg.ci_every <= 0 or time.time() - self.last_ci < self.cfg.ci_every:
            return
        path = self.cfg.home / "ci.json"
        try:
            prev = clean_ci(json.loads(path.read_text()))
        except (OSError, ValueError):
            prev = None
        if prev and prev.get("scope") != CI_SCOPE:  # pre-2026-10-16 branch/PR observation: never carried forward
            prev = None
        first_poll = not self.ci_seeded
        self.ci_seeded = True
        if first_poll and prev and prev.get("source") == ("github-public-api" if self.cfg.ci_mode == "public" else "gh"):
            # first poll of this process: a recent persisted attempt (e.g. LaunchAgent restart) suppresses a redundant poll
            try:
                age = time.time() - datetime.datetime.fromisoformat(prev["last_attempt_at"]).timestamp()
            except (KeyError, TypeError, ValueError):
                age = None
            if age is not None and 0 <= age < self.cfg.ci_every:
                self.last_ci = time.time() - age
                return
        self.heartbeat(force=True)
        self.last_ci = time.time()
        try:
            new = observe_public(self.cfg, self.ci_popen) if self.cfg.ci_mode == "public" else fetch_ci(self.cfg, self.ci_run)
            err = None
        except CIError as e:
            new, err = None, str(e.args[0])
        except Exception:
            new, err = None, "github-api-failed" if self.cfg.ci_mode == "public" else "gh-failed"
        if new:
            data = new | {"last_attempt_at": now_iso(), "error": None}
        else:
            data = (prev or {"source": "github-public-api" if self.cfg.ci_mode == "public" else "gh"}) | {"last_attempt_at": now_iso(), "error": err}
        try:
            atomic_write(path, json.dumps(data).encode())
        except OSError:
            return
        if err and (prev or {}).get("error") != err:
            self.store.event("ci-unavailable", code=err)
        self.heartbeat(force=True)
        return new

    def heartbeat(self, force=False):
        if force or time.time() - self.last_hb >= 2:
            self.state["runner"]["heartbeat_at"] = now_iso()
            self.last_hb = time.time()
            self.store.save(self.state)

    def check_baseline(self, force=False):
        if not force and time.time() - self.last_baseline < self.cfg.baseline_every and self.state["baseline"]:
            return self.state["health"]["status"] == "OK"
        self.last_baseline = time.time()
        res = verify_baseline(self.cfg.repo, load_pin(self.cfg.home))
        self.state["baseline"] = res
        h = self.state["health"]
        if res["ok"]:
            if h["status"] != "OK":
                self.store.event("baseline-verified" if h["status"] == "UNKNOWN" else "baseline-restored")
                self.state["health"] = {"status": "OK"}
                for t in self.state["tasks"].values():
                    if t["status"] == "BLOCKED" and t.get("blocked_reason") in BASELINE_CODES:
                        t["status"], t["blocked_reason"] = "QUEUED", None
        else:
            code = "BASELINE_NOT_PINNED" if res["code"] == "NOT_PINNED" else "BASELINE_MISMATCH"
            if h.get("status") != "BLOCKED" or h.get("code") != code or h.get("detail") != res["reason"]:
                self.store.event("baseline-blocked", code=code, reason=res["reason"])
                self.state["health"] = {"status": "BLOCKED", "code": code, "detail": res["reason"], "since": now_iso()}
        return res["ok"]

    def ingest_queue(self):
        h = self.state.get("handoff") or {}
        if h.get("request"):
            return  # held untouched: an open orchestrator request may not be credited with, or race, any ingress
        if h.get("quarantine"):  # a late gateway turn may still be alive: nothing but an owner re-arm reopens ingress
            self.hold_queue(h["quarantine"])
            return
        # S0/D16 quarantine: default-deny; any corrupt/absent/mismatched state holds the queue
        mode, why = _transition_mode(self.cfg)
        if mode == "HOLD":
            self.hold_queue(f"TRANSFER_HOLD: {why}")
            return
        qs, qled_or_reason = quarantine_state(self.cfg)
        if qs == _QS_DENY:
            self.hold_queue(f"S0_D16_QUARANTINE_DENY: {qled_or_reason}")
            return
        if qs == _QS_RESTARTED:
            self.hold_queue("S0_D16_QUARANTINE_RESTARTED: process restart after quarantined reload blocks all ingress")
            return
        for f in sorted((self.cfg.home / "queue").glob("*.json")):
            try:
                t = validate_task(json.loads(f.read_text()), self.cfg)
                review_binding(self.cfg, t, self.state["tasks"], require_changed=False)
                parent = self.state["tasks"].get((t.get("review_of") or {}).get("task_id"))
                if mode == "LANE" and not (s0_dual_rebind_marked(t) or isinstance(parent, dict) and s0_dual_rebind_marked(parent)):
                    raise TransitionHold()
                if mode == "RECOVERY" and not (_recovery_marked(t) or isinstance(parent, dict) and _recovery_marked(parent)):
                    raise TransitionHold()
                if (s0_marked(t) or s0_dual_rebind_marked(t) or _recovery_marked(t) or d16_dual_lineage(self.state["tasks"], t)
                        or isinstance(parent, dict) and (s0_dual_rebind_marked(parent) or _recovery_marked(parent)
                                                         or d16_dual_lineage(self.state["tasks"], parent))):
                    reason = gate_reason(self.cfg, t, self.state["tasks"])
                    if reason:
                        raise GateError(reason)
            except TransitionHold:
                f.rename(f.with_suffix(".held"))
                self.store.event("queue-held", file=f.name, reason="TRANSFER_HOLD: only the fixed S0 rebind or recovery lane is admitted before ACTIVE")
                continue
            except Exception as e:
                f.rename(f.with_suffix(".rejected"))
                self.store.event("task-rejected", file=f.name, reason=str(e))
                continue
            if t["id"] not in self.state["tasks"]:  # idempotent re-ingest
                stamp_product_remediation(self.state["tasks"], t)
                self.state["tasks"][t["id"]] = t
                self.store.save(self.state)  # durable BEFORE the queue file is consumed
                self.store.event("task-queued", f"{t['id']}:0", task_id=t["id"], module=t["module"], role=t["role"])
            f.unlink()

    def apply_commands(self):
        held = _transition_mode(self.cfg)[0] in ("HOLD", "LANE", "RECOVERY")  # before ACTIVE only stop/pause apply
        for f in self.store.pending_commands():
            try:
                c = json.loads(f.read_text())
                if not ((c["cmd"] in CONTROLS or c["cmd"] in ("rearm", "promote-mod004-capability"))
                        and ID_RE.match(str(c["op_id"]))):
                    raise ValueError("bad command or op_id")
            except Exception as e:
                f.rename(f.with_suffix(".rejected"))
                self.store.event("command-rejected", file=f.name, reason=str(e))
                continue
            if held and c["cmd"] not in ("pause", "stop"):  # stays pending, untouched, until the transfer is ACTIVE
                if f.name not in self._tr_held_cmds:
                    self._tr_held_cmds.add(f.name)
                    self.store.event("command-held", c["op_id"], cmd=c["cmd"], reason="TRANSFER_HOLD: transition is not ACTIVE")
                continue
            req = (self.state.get("handoff") or {}).get("request")
            if c["op_id"] in self.state["applied_ops"]:
                self.store.event("command-duplicate", c["op_id"], cmd=c["cmd"])
            elif req and c["cmd"] not in ("pause", "stop"):
                # resume/rearm cannot be told apart from a command the read-only turn wrote: recorded, not applied
                req["foreign_cmds"] = (req.get("foreign_cmds") or []) + [c["cmd"]]
                self.store.event("command-held", c["op_id"], cmd=c["cmd"], reason="orchestrator request open")
            elif c["cmd"] == "promote-mod004-capability":
                try:
                    self.promote_mod004_capability(c)
                except (ValueError, OSError, TypeError) as e:
                    self.store.event("capability-promotion-refused", c["op_id"], reason=str(e)[:300])
                self.state["applied_ops"] = (self.state["applied_ops"] + [c["op_id"]])[-500:]
            elif c["cmd"] == "rearm":
                self.state["applied_ops"] = (self.state["applied_ops"] + [c["op_id"]])[-500:]
                self.handoff_rearm()
                self.store.event("command-applied", c["op_id"], cmd="rearm")
            else:
                prev, self.state["control"] = self.state["control"], CONTROLS[c["cmd"]]
                self.state["applied_ops"] = (self.state["applied_ops"] + [c["op_id"]])[-500:]
                self.store.event("command-applied", c["op_id"], cmd=c["cmd"], prev=prev, now=self.state["control"])
            self.store.save(self.state)  # persist the op id before consuming the file
            f.unlink()

    def promote_mod004_capability(self, c):
        """Promote one independently reviewed Sonnet staging task, never a caller-selected path."""
        if set(c) != {"cmd", "op_id", "task_id", "hashes", "ts"}:
            raise ValueError("promotion command fields differ from the fixed contract")
        if not isinstance(c["task_id"], str) or not ID_RE.fullmatch(c["task_id"]):
            raise ValueError("promotion task id is invalid")
        hashes = c["hashes"]
        if not isinstance(hashes, dict) or set(hashes) != set(MOD004_PROMOTION) or not all(
                isinstance(h, str) and SHA256_RE.fullmatch(h) for h in hashes.values()):
            raise ValueError("promotion requires exactly two named staging SHA256 values")
        if self.state["control"] != "RUN" or self.state["health"].get("status") != "OK":
            raise ValueError("runner is not healthy and running")
        handoff = self.state.get("handoff") or {}
        if handoff.get("request") or handoff.get("quarantine"):
            raise ValueError("promotion refused while orchestrator handoff is open or quarantined")
        if not self.check_baseline(force=True):
            raise ValueError("baseline is not pinned and current")
        w = self.state["tasks"].get(c["task_id"])
        if not (w and w.get("module") == "MOD-004" and w.get("role") == "implement"
                and w.get("status") == "DONE" and (w.get("route") or {}).get("verdict") == "VERIFIED"
                and w.get("allowed_paths") == list(MOD004_PROMOTION)
                and set(w.get("expected_changes") or []) == set(MOD004_PROMOTION)
                and (w.get("evidence") or {}).get("violations") == []):
            raise ValueError("staging task is not a verified exact-two-file Sonnet write")
        changed = _changed_pairs((w["evidence"] or {}).get("changed"))
        if changed != _changed_pairs([{"path": p, "sha256": hashes[p]} for p in MOD004_PROMOTION]):
            raise ValueError("staging hashes differ from runner-recorded write evidence")
        approved = [r for r in self.state["tasks"].values() if r.get("status") == "DONE"
                    and r.get("module") == "MOD-004" and r.get("role") == "code-review"
                    and (r.get("evidence") or {}).get("review_outcome") == "APPROVED"
                    and _bound_review_ok(w, r)]
        if review_verdict(self.state["tasks"], w["id"]) != "APPROVED" or len(approved) != 1:
            raise ValueError("exact staging write lacks one independent bound APPROVED Opus review")
        if not self.wlock.acquire({"pid": os.getpid(), "promotion": c["op_id"]}):
            raise ValueError("repo writer lock is held")
        try:
            repo = self.cfg.repo.resolve()
            payload = {}
            for src, dst in MOD004_PROMOTION.items():
                sp, dp = repo / src, repo / dst
                for path in (sp, dp):
                    for parent in list(path.relative_to(repo).parents)[:-1]:
                        ancestor = repo / parent
                        if ancestor.is_symlink():
                            raise ValueError(f"symlink forbidden in promotion ancestor: {ancestor.relative_to(repo)}")
                    if path.is_symlink():
                        raise ValueError(f"symlink forbidden in promotion path: {path.relative_to(repo)}")
                if not sp.is_file() or dp.exists() or not dp.parent.is_dir():
                    raise ValueError(f"staging missing or destination already exists: {dst}")
                data = sp.read_bytes()
                if not data or len(data) > 100_000 or hashlib.sha256(data).hexdigest() != hashes[src]:
                    raise ValueError(f"staging bytes changed or invalid: {src}")
                payload[dst] = data
            self.store.event("capability-promotion-prepared", c["op_id"], task_id=w["id"],
                             review_id=approved[0]["id"], sources=hashes,
                             destinations={dst: hashes[src] for src, dst in MOD004_PROMOTION.items()})
            installed = []
            try:
                for dst, data in payload.items():
                    target = repo / dst
                    temporary = target.with_name(f".{target.name}.{c['op_id']}.tmp")
                    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                    try:
                        remaining = memoryview(data)
                        while remaining:
                            remaining = remaining[os.write(fd, remaining):]
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                    try:
                        os.link(temporary, target, follow_symlinks=False)  # never replace an existing rule
                        installed.append((target, hashlib.sha256(data).hexdigest()))
                        fsync_dir(target.parent)
                        if _path_hash(target) != installed[-1][1]:
                            raise ValueError(f"installed destination hash mismatch: {dst}")
                    finally:
                        temporary.unlink(missing_ok=True)
            except (ValueError, OSError):
                for target, expected in reversed(installed):
                    if _path_hash(target) == expected:
                        target.unlink()
                        fsync_dir(target.parent)
                self.store.event("capability-promotion-rolled-back", c["op_id"], task_id=w["id"])
                raise
            self.store.event("capability-promotion-installed", c["op_id"], task_id=w["id"],
                             review_id=approved[0]["id"], destinations={dst: hashlib.sha256(data).hexdigest()
                                                                           for dst, data in payload.items()})
        finally:
            self.wlock.release()

    def next_ready(self):
        ready = sorted((t for t in self.state["tasks"].values()
                        if t["status"] == "QUEUED" and t.get("next_attempt_at", 0) <= time.time()),
                       key=lambda t: t["created_at"])
        for t in ready:  # a gated item is skipped, never BLOCKED/DONE, so it cannot starve eligible work behind it
            if not self.gated(t):
                return t
        return None

    def gated(self, t):
        """True (and records why) if the prerequisite gate holds the task. A resumed verification already ran, so it skips the
        prerequisite gate but never the transfer lineage's HOLD; an evaluation error denies."""
        if t.get("stage") == "verify_pending":
            try:
                reason = _transition_gate_reason(self.cfg, t, self.state["tasks"])
            except Exception as e:
                reason = f"TRANSFER_HOLD {t.get('id')}: transfer gate evaluation failed: {e}"[:300]
        else:
            reason = gate_reason(self.cfg, t, self.state["tasks"])
        if reason != t.get("gate_reason"):
            t["gate_reason"] = reason
            self.store.event("task-gated" if reason else "task-gate-cleared", task_id=t["id"], reason=reason)
        return reason is not None

    # --- child isolation
    def child_env(self):
        env = {k: os.environ[k] for k in CHILD_ENV_KEEP if k in os.environ}
        env["VEYRO_MISSION_CHILD"] = "1"  # no ANTHROPIC_*/VEYRO_RUNNER_* etc: auth stays the user's own login
        return env

    def child_settings(self, t):
        """Explicit minimal permissions for the child. dontAsk = anything not allowed here is denied."""
        pats = [a + "**" if a.endswith("/") else a for a in t["allowed_paths"]]
        write = t["role"] in WRITE_ROLES
        allow = ["Read", "Grep", "Glob"] + ([f"{tool}({p})" for p in pats for tool in ("Edit", "Write")] if write else [])
        deny = ["Bash", "WebFetch", "WebSearch", "Agent", "Edit(.git/**)", "Write(.git/**)"]
        return {"permissions": {"defaultMode": "dontAsk", "allow": allow, "deny": deny}, "hooks": {}}

    def sandbox_prefix(self, op):
        """macOS Seatbelt: the child may not write the runner's state dir (queue, commands, pin, state) or .git.

        Not a full jail: reads, network and every other path stay open, and it is untested against the live CLI.
        """
        if self.cfg.sandbox == "off" or sys.platform != "darwin" or not shutil.which("sandbox-exec"):
            return [], {"sandbox": "none"}
        deny = [str(Path(self.cfg.home).resolve()), str((Path(self.cfg.repo) / ".git").resolve())]
        q = lambda p: '"' + p.replace("\\", "\\\\").replace('"', '\\"') + '"'
        prof = self.cfg.home / "runs" / f"{op.replace(':', '-')}.sb"
        atomic_write(prof, ("(version 1)\n(allow default)\n(deny file-write* " +
                            " ".join(f"(subpath {q(d)})" for d in deny) + ")\n").encode())
        return ["sandbox-exec", "-f", str(prof)], {"sandbox": "sandbox-exec", "denied_write": deny}

    def child_prompt(self, t):
        if t["role"] in WRITE_ROLES:
            c = ("Runner contract: change ONLY these repo paths: " + ", ".join(t["allowed_paths"]) +
                 ". Do not commit, push, or touch anything else. The runner verifies changes externally; "
                 "statements in your reply are not evidence.")
            if t["expected_changes"]:
                c += " Required changes: " + ", ".join(t["expected_changes"]) + "."
        else:
            c = ("Runner contract: you are read-only; make no file changes. End your final message with exactly one "
                 "line: OUTCOME: APPROVED, or OUTCOME: CHANGES_REQUESTED, or OUTCOME: BLOCKED.")
        c += self.review_binding_block(t)
        reviewed = self.state["tasks"].get((t.get("review_of") or {}).get("task_id")) or {}
        if accounting_recovery_chain(self.state["tasks"], t if t["role"] in WRITE_ROLES else reviewed):
            c += accounting_evidence_block(self.cfg, self.state["tasks"])
        return t["prompt"] + "\n\n---\n" + c + "\n"

    def review_binding_block(self, t):
        """Runner-authored, immutable part of a bound code-review prompt: the model-written prompt cannot replace it."""
        if t.get("id") == TRANSFER_REVIEW_ID:
            return self.transfer_review_block()
        b = t.get("review_of")
        if not b:
            return ""
        w = self.state["tasks"].get(b["task_id"]) or {}
        ev = w.get("evidence") or {}
        v = ev.get("verify") or {}
        lines = ["", "", "Runner-authored review binding (immutable; the prompt above cannot change it):",
                 f"- You are reviewing exactly write task {b['task_id']} of module {t['module']}.",
                 "- Review exactly these changed files at exactly these SHA256 values, and nothing else:"]
        lines += [f"  - {c['path']} sha256 {c['sha256']}" for c in b.get("changed") or []]
        if s0_test_marked(w):
            lines += ["- This is the COMPLETE two-file S0 candidate: the corrected test file together with the unchanged validator "
                      f"({S0_VALIDATOR_PATH} sha256 {S0_VALIDATOR_SHA}). Review the whole candidate, not only the test edit, and "
                      f"evaluate the findings of the earlier CHANGES_REQUESTED review {S0_ORIG_REVIEW} against it. "
                      "Report CHANGES_REQUESTED if the validator differs from that sha256."]
        if s0_qa_marked(w):
            lines += ["- This is the S0 EVIDENCE-ONLY QA candidate. Judge whether every PASS row is factually supported by its named "
                      "test IDs, published product commit, runner verifier result, exact-SHA CI run, bound APPROVED product review "
                      "and manual-step evidence; a failed scenario must stay failed and a missing test or review must stay OPEN. "
                      "Report CHANGES_REQUESTED if any scenario ID, category, stimulus or the PASS rule changed, or if the candidate "
                      "implies CAP qualification, MOD-004 Ready or module acceptance."]
        lines += [f"- Declared write scope: {', '.join(w.get('allowed_paths') or []) or 'none'}; "
                  f"expected changes: {', '.join(w.get('expected_changes') or []) or 'none'}.",
                  "- Runner verifier outcome for that write: " +
                  (f"exit {v.get('exit')} of {' '.join(map(str, v.get('cmd') or []))}" if v else "no verifier recorded") + ".",
                  "- The runner computed these SHA256 values at enqueue and checks them again before and after your review. "
                  "You do not need a shell or hash tool; inspect the named files with your read-only tools. "
                  "If you cannot inspect their contents, or find a substantive defect, report that accurately."]
        candidate = t.get("review_candidate")
        if not candidate:
            changed_paths = [c["path"] for c in b.get("changed") or []]
            head = _git(self.cfg.repo, "rev-parse", "HEAD").stdout.decode().strip()
            diff = _git(self.cfg.repo, "diff", "--binary", "--no-ext-diff", "--", *changed_paths).stdout
            lines += ["- Runner-computed read-only Git diff of those bound files against HEAD " + head +
                      "; diff SHA256 " + hashlib.sha256(diff).hexdigest() + ". Compare it with the current file contents:",
                      "```diff", diff.decode("utf-8", errors="replace"), "```"]
            tracked = set(_git(self.cfg.repo, "ls-tree", "-r", "--name-only", "HEAD", "--", *changed_paths).stdout.decode().splitlines())
            lines += ["- NEW FILE absent from HEAD (not present in Git diff): " + p +
                      "; read its complete current contents at the bound SHA256 above."
                      for p in changed_paths if p not in tracked]
        if candidate:
            lines += ["- Operational retry of prior BLOCKED review " + t["review_retry_of"] + "; its verdict remains historical.",
                      "- Runner-verified COMPLETE dirty product candidate: head " + candidate["head"] +
                      "; diff SHA256 " + candidate["diff_sha256"] + "; candidate SHA256 " + candidate["candidate_sha256"] + ".",
                      "- Inspect every candidate file below, including files from earlier writes:"]
            lines += [f"  - {c['path']} sha256 {c['sha256']}" for c in candidate["files"]]
            diff = _git(self.cfg.repo, "diff", "--binary", "--no-ext-diff", "--",
                        *(c["path"] for c in candidate["files"])).stdout
            if hashlib.sha256(diff).hexdigest() != candidate["diff_sha256"]:
                raise ValueError("review candidate diff changed while constructing bound prompt")
            lines += ["- Runner-computed Git diff against that exact HEAD follows. It is read-only evidence; compare it "
                      "with the current file contents and the bound hashes:",
                      "```diff", diff.decode("utf-8", errors="replace"), "```"]
            paths = [c["path"] for c in candidate["files"]]
            tracked = set(_git(self.cfg.repo, "ls-tree", "-r", "--name-only", candidate["head"], "--", *paths).stdout.decode().splitlines())
            lines += ["- NEW FILE absent from the candidate HEAD (not present in Git diff): " + p +
                      "; read its complete current contents at the bound SHA256 above."
                      for p in paths if p not in tracked]
            lines += ["- The runner rechecks this entire manifest after your review. A missing personal hash tool alone is not "
                      "a reason to block; inability to inspect the files or a substantive defect is."]
        return "\n".join(lines)

    def transfer_review_block(self):
        """Runner-authored subject of the one pre-consumption review (nothing a model wrote can replace it)."""
        sj = _transfer_successor(self.cfg)
        diff = _transfer_diff(self.cfg, sj["commit"])
        if len(diff) > 2_000_000:
            raise ValueError("the successor diff is too large to review in one bounded prompt")
        return "\n".join(["", "", "Runner-authored review subject (immutable; the prompt above cannot change it):",
                          f"- Chain: effective amendment B {TRANSFER_AMEND_COMMIT} -> authorization commit A {TRANSFER_AUTH_COMMIT} -> "
                          f"Lifecycle contract record D (sole parent of C) {sj['parent']} -> successor commit C {sj['commit']}.",
                          f"- {S0_RUNNER_FILE} sha256 {sj['code_sha256']}; {TRANSFER_TEST_FILE} sha256 {sj['test_sha256']}.",
                          f"- Owner records to judge against: {TRANSFER_OWNER_PATH}, {TRANSFER_AMEND_PATH}, {TRANSFER_AUTH_PATH} "
                          f"and {TRANSFER_LIFECYCLE_PATH}.",
                          f"- Canonical D-to-C diff SHA256 {sj['diff_sha256']}:", "```diff",
                          diff.decode("utf-8", errors="replace"), "```"])

    def transfer_review_event_fields(self, t, prompt_text):
        if t["id"] != TRANSFER_REVIEW_ID:
            return {}
        try:
            subject = _transfer_subject_sha(_transfer_successor(self.cfg))
        except GateError:
            subject = None
        return {"subject_sha256": subject, "prompt_sha256": _sha(prompt_text.encode()), "pid": os.getpid(),
                "boot_nonce": _PROCESS_BOOT_NONCE}

    def transfer_review_record(self, t, op, out):
        """After settlement: pin the exact run output and evidence file bytes the settlement produced (DONE only)."""
        if t.get("status") != "DONE":
            return
        try:
            self.store.event("transfer-review-recorded", op, task_id=t["id"], out_sha256=_sha(Path(out).read_bytes()),
                             evidence_sha256=_sha(Path(str(out)[:-4] + ".evidence.json").read_bytes()))
        except OSError:
            pass  # without the recorded event the chain cannot verify: quarantine simply stays closed

    # --- dispatch
    def dispatch(self, t):
        h = self.state.get("handoff") or {}
        if h.get("request") or h.get("quarantine"):  # no worker while a request is open or a late gateway turn is possible
            return
        if not self.check_baseline(force=True):
            return
        if not self.wlock.acquire({"pid": os.getpid(), "task_id": t["id"]}):
            if not self.busy_noted:
                self.store.event("writer-lock-busy", owner=self.wlock.owner())
                self.busy_noted = True
            return
        self.busy_noted = False
        try:
            if self.gated(t):  # recheck under the writer lock, immediately before any child can start
                return
            # On-disk identity check: halt dispatch on any code drift (runner.py bytes only, no project modules)
            try:
                disk_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            except OSError:
                disk_sha = None
            if disk_sha != _LOADED_CODE_SHA:
                t.update(status="BLOCKED", blocked_reason="RUNNER_CODE_DRIFT", stage=None, updated_at=now_iso(),
                         last_error=f"on-disk runner.py no longer matches the loaded code (disk: {(disk_sha or 'unreadable')[:16]})")
                self.store.event("task-blocked", f"{t['id']}:{t['attempts'] + 1}", task_id=t["id"],
                                 code="RUNNER_CODE_DRIFT")
                return
            try:
                _trusted_dashboard()
            except GateError as e:
                t.update(status="BLOCKED", blocked_reason="LOCAL_GATE_CODE_DRIFT", stage=None,
                         updated_at=now_iso(), last_error=str(e))
                self.store.event("task-blocked", f"{t['id']}:{t['attempts'] + 1}", task_id=t["id"],
                                 code="LOCAL_GATE_CODE_DRIFT")
                return
            # Consume the dual rebind slot durably before dispatch (partial write never becomes eligible again)
            if s0_dual_rebind_marked(t):
                try:
                    if _transfer_lineage_active(self.cfg):  # the authoritative transition record spends the slot
                        self._transition_consume_slot(t)
                    else:
                        qled = _load_qled(self.cfg)
                        if not (isinstance(qled, dict) and qled.get("runner_pid") == os.getpid()
                                and qled.get("runner_boot_nonce") == _PROCESS_BOOT_NONCE
                                and qled.get("code_sha256") == CODE_SHA and not qled.get("dual_rebind_consumed")):
                            raise GateError("dual rebind slot invalid or already consumed")
                        _write_qled(self.cfg, {**qled, "dual_rebind_consumed": True})
                except (GateError, OSError) as e:
                    t.update(status="BLOCKED", blocked_reason="S0_DUAL_REBIND_SLOT_CONSUMED", stage=None,
                             updated_at=now_iso(), last_error=f"consumption of dual rebind slot failed: {e}")
                    self.store.event("task-blocked", f"{t['id']}:{t['attempts'] + 1}", task_id=t["id"],
                                     code="S0_DUAL_REBIND_SLOT_CONSUMED")
                    return
            if _recovery_marked(t):  # the recovery attempt is spent durably BEFORE dispatch; an interruption never re-arms it
                try:
                    self._recovery_consume_correction(t)
                except (GateError, OSError) as e:
                    t.update(status="BLOCKED", blocked_reason="S0_RECOVERY_SLOT_CONSUMED", stage=None,
                             updated_at=now_iso(), last_error=f"consumption of the recovery correction slot failed: {e}")
                    self.store.event("task-blocked", f"{t['id']}:{t['attempts'] + 1}", task_id=t["id"],
                                     code="S0_RECOVERY_SLOT_CONSUMED")
                    return
            stale = bound_review_problems(self.cfg, self.state["tasks"], t)
            if stale:  # the bound files moved before the reviewer could see them: no review, no approval credit
                t.update(status="BLOCKED", blocked_reason="REVIEW_BINDING_STALE", stage=None, updated_at=now_iso(),
                         last_error="; ".join(stale)[:300])
                ev = {"op": f"{t['id']}:{t['attempts']}", "at": now_iso(), "review_outcome": None, "review_bound_verified": False,
                      "violations": ["REVIEW_BINDING_STALE"], "stale": stale[:10]}
                t["evidence"] = ev
                atomic_write(self.cfg.home / "runs" / f"{t['id']}.stale-binding.evidence.json",
                             json.dumps(ev, indent=1, sort_keys=True).encode())
                return self.store.event("task-blocked", f"{t['id']}:{t['attempts']}", task_id=t["id"],
                                        code="REVIEW_BINDING_STALE", violations=stale[:10])
            if t.get("stage") == "verify_pending" and t.get("verify_checkpoint"):
                cp = t["verify_checkpoint"]
                t.update(status="RUNNING", stage="verifying")
                self.store.save(self.state)
                self.store.event("verification-resumed", cp["op"], task_id=t["id"])
                self.settle(t, cp["op"], "exited", SimpleNamespace(returncode=0),
                            Path(cp["out"]), Path(cp["err"]), self.task_base_state(t), cp["isolation"])
                return
            try:
                before = self.task_base_state(t)
            except Exception as e:  # cannot prove what the child changes => do not run it
                t.update(status="BLOCKED", blocked_reason="REPO_SNAPSHOT_UNAVAILABLE", last_error=str(e)[:300],
                         updated_at=now_iso())
                return self.store.event("task-blocked", f"{t['id']}:{t['attempts'] + 1}", task_id=t["id"],
                                        code="REPO_SNAPSHOT_UNAVAILABLE")
            try:
                prompt_text = self.child_prompt(t)  # all Git reads finish before RUNNING and before any child exists
            except Exception as e:  # a prompt must never terminate the sole runner after it owns the lease
                code = "REVIEW_BINDING_STALE" if isinstance(e, ValueError) else "REPO_SNAPSHOT_UNAVAILABLE"
                t.update(status="BLOCKED", blocked_reason=code, stage=None, updated_at=now_iso(),
                         last_error=f"review prompt unavailable: {e}"[:300],
                         evidence={"op": f"{t['id']}:{t['attempts']}", "at": now_iso(),
                                   "review_outcome": None, "review_bound_verified": False, "violations": [code]})
                return self.store.event("task-blocked", f"{t['id']}:{t['attempts']}", task_id=t["id"], code=code)
            alias = required_family(t["role"])
            t["attempts"] += 1
            op = f"{t['id']}:{t['attempts']}"
            t.update(status="RUNNING", stage="child", updated_at=now_iso(), started_at=now_iso(), child=None,
                     blocked_reason=None, finished_at=None)
            self.store.save(self.state)  # RUNNING is durable before the child exists
            self.store.event("dispatch", op, task_id=t["id"], role=t["role"], model_alias=alias, attempt=t["attempts"],
                             **self.transfer_review_event_fields(t, prompt_text))
            stem = self.cfg.home / "runs" / op.replace(":", "-")
            out, err, sett = Path(f"{stem}.out"), Path(f"{stem}.err"), Path(f"{stem}.settings.json")
            atomic_write(sett, json.dumps(self.child_settings(t), indent=1).encode())
            prefix, iso = self.sandbox_prefix(op)
            tools = "Read,Grep,Glob,Edit,Write" if t["role"] in WRITE_ROLES else "Read,Grep,Glob"
            cmd = [*prefix, self.cfg.claude_bin, "-p", "--safe-mode", "--setting-sources=", f"--settings={sett}",
                   "--permission-mode=dontAsk", "--permission-prompts=none", "--strict-mcp-config",
                   "--disable-slash-commands", f"--tools={tools}", "--model", alias, "--output-format=json"]
            iso.update(settings=str(sett), permission_mode="dontAsk", tools=tools)
            with open(out, "wb") as fo, open(err, "wb") as fe:
                try:
                    # the writer-lock fd is inherited: if this runner dies the orphan still holds the lock
                    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=fo, stderr=fe, cwd=self.cfg.repo,
                                         start_new_session=True, env=self.child_env(), pass_fds=(self.wlock.fd,))
                except OSError as e:
                    return self.failure(t, f"spawn failed: {e}", op)
                try:
                    p.stdin.write(prompt_text.encode())
                    p.stdin.close()
                except BrokenPipeError:
                    pass
                lstart = subprocess.run(["ps", "-o", "lstart=", "-p", str(p.pid)], capture_output=True,
                                        text=True).stdout.strip()
                t["child"] = {"pid": p.pid, "lstart": lstart}
                self.wlock.update({"child_pid": p.pid, "runner_pid": os.getpid()})
                self.store.save(self.state)
                outcome = self.supervise(p, t)
            try:
                os.killpg(p.pid, signal.SIGKILL)  # strays from the child's own group must not outlive the attempt
            except OSError:
                pass
            t["child"] = None
            if outcome == "exited" and p.returncode == 0:
                t["stage"] = "verifying"
                t["verify_checkpoint"] = {"op": op, "out": str(out), "err": str(err), "isolation": iso}
                self.store.save(self.state)
            self.settle(t, op, outcome, p, out, err, before, iso)
            if t["id"] == TRANSFER_REVIEW_ID:
                self.transfer_review_record(t, op, out)
        finally:
            # terminal/settled state is durable BEFORE the writer lock frees, so a concurrent enqueue never reads stale state
            try:
                self.store.save(self.state)
            finally:
                self.wlock.release()

    def task_base_state(self, t):
        """Repo state at the task's FIRST attempt, kept on disk: later attempts are judged against it, so partial
        edits left by an interrupted/killed earlier attempt stay attributed to the task instead of being forgiven."""
        f = self.cfg.home / "runs" / f"{t['id']}.base.json"
        try:
            return json.loads(f.read_text())
        except FileNotFoundError:
            st = repo_state(self.cfg.repo)
            atomic_write(f, json.dumps(st, sort_keys=True).encode())
            return st

    def supervise(self, p, t):
        deadline, last_bl = time.time() + self.cfg.timeout, time.time()
        while p.poll() is None:
            time.sleep(min(0.2, self.cfg.tick))
            self.heartbeat()
            self.apply_commands()
            why = ("signal" if self.sig else "stopped" if self.state["control"] == "STOP" else
                   "timeout" if time.time() > deadline else None)
            if not why and time.time() - last_bl >= self.cfg.baseline_every:
                last_bl = time.time()
                if not self.check_baseline(force=True):
                    why = "baseline"
            if why:
                self.kill_group(p.pid)
                p.wait()
                return why
        return "exited"

    # --- settle: DONE is earned only by external evidence, never by exit code or prose
    def settle(self, t, op, outcome, p, out, err, before, iso):
        t["updated_at"] = now_iso()
        if outcome in ("stopped", "signal") and (s0_single_attempt(t)
                                                  or t["id"] in (D16_F34_WRITE, D16_F34_REVIEW)
                                                  or d16_single_attempt(self.state["tasks"], t)):
            # No retry after an interrupted one-shot write or review; partial edits or a review judgement may exist.
            code = ("TRANSFER_REVIEW_ATTEMPT_INTERRUPTED" if t["id"] == TRANSFER_REVIEW_ID else
                    "D16_F34_ATTEMPT_INTERRUPTED" if t["id"] in (D16_F34_WRITE, D16_F34_REVIEW) else
                    "D16_DUAL_ATTEMPT_INTERRUPTED" if d16_single_attempt(self.state["tasks"], t) and not s0_dual_rebind_marked(t) and not _recovery_marked(t) else
                    "S0_ATTEMPT_INTERRUPTED" if s0_marked(t) else
                    "S0_REFRESH_ATTEMPT_INTERRUPTED" if s0_refresh_marked(t) else
                    "S0_REBIND_ATTEMPT_INTERRUPTED" if s0_rebind_marked(t) else
                    "S0_TEST_ATTEMPT_INTERRUPTED" if s0_test_marked(t) else
                    "S0_LOOP_ATTEMPT_INTERRUPTED" if s0_loop_marked(t) else
                    "S0_QA_ATTEMPT_INTERRUPTED" if s0_qa_marked(t) else
                    "S0_DUAL_REBIND_ATTEMPT_INTERRUPTED" if s0_dual_rebind_marked(t) else
                    "S0_RECOVERY_ATTEMPT_INTERRUPTED" if _recovery_marked(t) else "S0_DOC_ATTEMPT_INTERRUPTED")
            t.update(status="BLOCKED", blocked_reason=code, stage=None,
                     last_error="the only authorized attempt was interrupted; partial edits or a review judgement may exist")
            return self.store.event("task-blocked", op, task_id=t["id"], code=code)
        if outcome in ("stopped", "signal"):  # operator/launchd action is not a task failure
            t.update(status="QUEUED", attempts=t["attempts"] - 1, stage=None)
            return self.store.event("attempt-interrupted", op, task_id=t["id"], why=outcome)
        if outcome == "baseline":  # child killed mid-run: the tree may hold partial edits => human triage, no auto-requeue
            t.update(status="BLOCKED", blocked_reason="RUN_ABORTED_BASELINE_MISMATCH", stage=None,
                     last_error="baseline changed while the child ran; child killed; repo may hold partial edits")
            return self.store.event("task-blocked", op, task_id=t["id"], code="RUN_ABORTED_BASELINE_MISMATCH")
        if outcome == "timeout":
            return self.failure(t, f"timeout after {self.cfg.timeout}s", op)
        raw = out.read_bytes()[-2_000_000:].decode(errors="replace")
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
        except Exception:
            parsed = None
        if p.returncode != 0 or parsed is None or parsed.get("is_error"):
            tail = err.read_bytes()[-300:].decode(errors="replace").strip()
            return self.failure(t, f"exit {p.returncode}; {tail or 'no/invalid JSON result'}"[:400], op)

        t["stage"] = "verifying"
        self.store.save(self.state)
        route = t.get("route") if (t.get("route") or {}).get("dispatch_op") == op else None
        if route is None:
            route = judge_route(t["role"], parsed)
            n = self.state["mr_counters"].get(t["module"] + today(), 0) + 1
            self.state["mr_counters"][t["module"] + today()] = n
            route.update(mr_id=f"MR-{t['module']}-{today()}-{n:03d}", task_class=t["role"], lifecycle_role=t["role"],
                         session_id=parsed.get("session_id"), dispatch_op=op, runner_pid=os.getpid())
            t["route"] = route
            self.record_usage(parsed)
            self.store.event("route-evidence", op, **{k: v for k, v in route.items() if k != "models"})

        bad = []  # (code, detail) - first entry is the blocked_reason
        if parsed.get("subtype") != "success":
            bad.append(("RESULT_NOT_SUCCESS", f"subtype={parsed.get('subtype')!r}"))
        denials = parsed.get("permission_denials")
        if not isinstance(denials, list):
            bad.append(("PERMISSION_DENIALS_UNVERIFIED", "result carried no permission_denials list"))
        elif denials:
            bad.append(("PERMISSION_DENIED", f"{len(denials)} tool call(s) denied by the permission mode"))
        if route["verdict"] != "VERIFIED":
            bad.append(("MODEL_ASSURANCE_UNVERIFIED", f"{route['verdict']}: {route['basis']}"))
        if not self.check_baseline(force=True):
            bad.append(("POST_RUN_BASELINE_MISMATCH", str(self.state["health"].get("detail"))))
        changed, head_moved, after = [], False, None
        try:
            after = repo_state(self.cfg.repo)
            changed, head_moved = diff_state(before, after), before["head"] != after["head"]
        except Exception as e:
            bad.append(("REPO_SNAPSHOT_UNAVAILABLE", str(e)[:200]))
        write = t["role"] in WRITE_ROLES
        if write and not changed:
            bad.append(("NO_DELIVERABLE_CHANGE", "writing task changed no repository file"))
        if write and t["id"] == D16_F34_WRITE:
            problem = d16_f34_result_problem(self.cfg.repo, changed)
            if problem:
                bad.append(("D16_F34_RESULT_MISMATCH", problem))
        if head_moved:
            bad.append(("HEAD_MOVED", "the child changed git HEAD"))
        stray = [c for c in changed if not in_scope(c, t["allowed_paths"])]
        if stray:
            bad.append(("OUT_OF_SCOPE_CHANGE", f"outside declared scope: {stray[:10]}"))
        missing = [e for e in t["expected_changes"] if e not in changed]
        if missing:
            bad.append(("EXPECTED_CHANGE_MISSING", f"declared but unchanged: {missing}"))
        s0_bad = s0_import_problems(self.cfg.repo) if write and (s0_marked(t) or s0_test_marked(t)) else []
        if s0_bad:  # forbidden closure: never executed by the verifier and never credited
            bad.append(("S0_FORBIDDEN_IMPORT", "; ".join(s0_bad)[:300]))
        verify = None
        if write and t["verify_cmd"] and not stray and not head_moved and not s0_bad:
            verify = self.run_verify(t)
            if verify.get("interrupted"):
                t.update(status="QUEUED", stage="verify_pending", updated_at=now_iso())
                self.store.save(self.state)
                return self.store.event("verification-paused", op, task_id=t["id"], why=verify["interrupted"])
            if verify["exit"] != 0:
                bad.append(("VERIFICATION_FAILED", f"verify_cmd exit {verify['exit']}"))
            if t.get("source") == "handoff" and after is not None:  # a model-proposed verifier may not mutate or commit: judge a fresh snapshot
                try:
                    after2 = repo_state(self.cfg.repo)
                    mutated = diff_state(after, after2)
                    if mutated or after2["head"] != after["head"]:
                        bad.append(("VERIFY_MUTATED_REPO", f"verification changed {mutated[:10]}"
                                    + (" and moved HEAD" if after2["head"] != after["head"] else "")))
                except Exception as e:
                    bad.append(("REPO_SNAPSHOT_UNAVAILABLE", f"after verification: {str(e)[:150]}"))
        review = reported = None
        bound_ok = False
        if not write:
            lines = [ln.strip() for ln in str(parsed.get("result", "")).splitlines() if ln.strip()]
            m = OUTCOME_RE.match(lines[-1]) if lines else None
            review = reported = m.group(1) if m else None
            if t.get("review_of"):  # the bound files must be exactly what the reviewer was told to review, still
                stale = bound_review_problems(self.cfg, self.state["tasks"], t)
                bound_ok = not stale
                if stale:
                    review = None  # no verdict credit, in either direction; the raw claim stays in the evidence
                    bad.append(("REVIEW_BINDING_STALE", "; ".join(stale)[:200]))
            if review is None and reported is None:
                bad.append(("NO_REVIEW_OUTCOME", "final line is not an explicit OUTCOME: marker"))
            elif review is not None and review != "APPROVED":
                bad.append((f"REVIEW_{review}", f"reviewer outcome {review}"))

        if write and s0_marked(t):  # authority may have been withdrawn during the child or a paused verification
            try:
                verify_s0_authority(self.cfg, self.state["tasks"])
            except GateError as e:
                bad.append(("S0_AUTHORITY_WITHDRAWN", str(e)[:200]))
            except Exception as e:
                bad.append(("S0_AUTHORITY_WITHDRAWN", type(e).__name__))
        if write and s0_doc_marked(t):  # authority may have been withdrawn during the child
            try:
                verify_s0_doc_authority(self.cfg, self.state["tasks"])
            except GateError as e:
                bad.append(("S0_DOC_AUTHORITY_WITHDRAWN", str(e)[:200]))
            except Exception as e:
                bad.append(("S0_DOC_AUTHORITY_WITHDRAWN", type(e).__name__))
        if write and s0_refresh_marked(t):  # recovery authority may have been withdrawn, or an S0 receipt installed, during the child
            try:
                verify_s0_refresh_authority(self.cfg, self.state["tasks"])
            except GateError as e:
                bad.append(("S0_REFRESH_AUTHORITY_WITHDRAWN", str(e)[:200]))
            except Exception as e:
                bad.append(("S0_REFRESH_AUTHORITY_WITHDRAWN", type(e).__name__))
        if write and s0_rebind_marked(t):  # recovery authority may have been withdrawn, or an S0 receipt installed, during the child
            try:
                verify_s0_rebind_authority(self.cfg, self.state["tasks"])
            except GateError as e:
                bad.append(("S0_REBIND_AUTHORITY_WITHDRAWN", str(e)[:200]))
            except Exception as e:
                bad.append(("S0_REBIND_AUTHORITY_WITHDRAWN", type(e).__name__))
        if write and s0_loop_marked(t):  # recovery authority may have been withdrawn, or an S0 receipt installed, during the child; the documents must keep their pinned shape
            try:
                verify_s0_loop_authority(self.cfg, self.state["tasks"], require_base=False)
            except GateError as e:
                bad.append(("S0_LOOP_AUTHORITY_WITHDRAWN", str(e)[:200]))
            except Exception as e:
                bad.append(("S0_LOOP_AUTHORITY_WITHDRAWN", type(e).__name__))
            try:
                problem = _s0_loop_docs_problem(self.cfg)
                if problem:
                    bad.append(("S0_LOOP_DOCUMENT_SHAPE", problem[:200]))
            except Exception as e:
                bad.append(("S0_LOOP_DOCUMENT_SHAPE", type(e).__name__))
        if write and s0_qa_marked(t):  # authority may have been withdrawn during the child; product, CAP files and the packet structure must hold
            try:
                verify_s0_qa_authority(self.cfg, self.state["tasks"])
            except GateError as e:
                bad.append(("S0_QA_AUTHORITY_WITHDRAWN", str(e)[:200]))
            except Exception as e:
                bad.append(("S0_QA_AUTHORITY_WITHDRAWN", type(e).__name__))
            try:
                problem = _s0_qa_result_problem(self.cfg, t)
                if problem:
                    bad.append(("S0_QA_RESULT_UNSOUND", problem[:200]))
            except Exception as e:
                bad.append(("S0_QA_RESULT_UNSOUND", type(e).__name__))
        if write and _recovery_marked(t):  # only the certificate changed; it names the exact packet hash and the loaded runner
            try:
                problem = _recovery_result_problem(self.cfg, self.state["tasks"], changed)
                if problem:
                    bad.append(("S0_RECOVERY_RESULT_UNSOUND", problem[:200]))
            except Exception as e:
                bad.append(("S0_RECOVERY_RESULT_UNSOUND", type(e).__name__))
        if write and s0_rebind_repair_marked(t):  # the root record must be untouched and the certificate must carry the final packet hash
            try:
                problem = _s0_rebind_root_problem(self.state["tasks"])
                if problem:
                    bad.append(("S0_REBIND_REPAIR_ROOT_CHANGED", problem[:200]))
                problem = _s0_rebind_packet_problem(self.cfg)
                if problem:
                    bad.append(("S0_REBIND_REPAIR_PACKET_UNBOUND", problem[:200]))
            except Exception as e:
                bad.append(("S0_REBIND_REPAIR_PACKET_UNBOUND", type(e).__name__))
        if write and s0_test_marked(t):  # recovery/full S0 authority or the validator may have changed during the child
            try:
                verify_s0_test_authority(self.cfg, self.state["tasks"])
            except GateError as e:
                bad.append(("S0_TEST_AUTHORITY_WITHDRAWN", str(e)[:200]))
            except Exception as e:
                bad.append(("S0_TEST_AUTHORITY_WITHDRAWN", type(e).__name__))
            try:
                if _path_hash(Path(self.cfg.repo) / S0_VALIDATOR_PATH) != S0_VALIDATOR_SHA:
                    bad.append(("S0_TEST_VALIDATOR_CHANGED", "the validator is not the pinned sha256"))
            except OSError:
                bad.append(("S0_TEST_VALIDATOR_CHANGED", "the validator cannot be read"))
        if (write and t.get("remediation_of") and product_loop_eligible(self.state["tasks"], t)
                and product_policy_root(self.state["tasks"], t)):
            try:
                problem = product_progress_problem(self.state["tasks"], t, [
                    {"path": c, "sha256": _path_hash(Path(self.cfg.repo) / c)} for c in changed])
                if problem:
                    bad.append(("REMEDIATION_NO_PROGRESS", problem[:200]))
            except Exception as e:
                bad.append(("REMEDIATION_NO_PROGRESS", type(e).__name__))
        base = Path(self.cfg.repo)
        evidence = {"op": op, "at": now_iso(), "subtype": parsed.get("subtype"),
                    "permission_denials": len(denials) if isinstance(denials, list) else None,
                    "route_verdict": route["verdict"], "isolation": iso, "head_moved": head_moved,
                    "changed": [{"path": c, "sha256": _path_hash(base / c)} for c in changed],
                    "expected_changes": t["expected_changes"], "allowed_paths": t["allowed_paths"],
                    "verify": verify, "review_outcome": review, "violations": [c for c, _ in bad]}
        if t.get("review_of"):
            evidence |= {"review_outcome_reported": reported, "review_bound_verified": bound_ok}
        atomic_write(Path(str(out)[:-4] + ".evidence.json"), json.dumps(evidence, indent=1, sort_keys=True).encode())
        t["evidence"], t["stage"], t["result"] = evidence, None, str(parsed.get("result", ""))[:500]
        t.pop("verify_checkpoint", None)
        if bad:
            t.update(status="BLOCKED", blocked_reason=bad[0][0], last_error="; ".join(f"{c}: {d}" for c, d in bad)[:600])
            return self.store.event("task-blocked", op, task_id=t["id"], code=bad[0][0], violations=[c for c, _ in bad])
        t.update(status="DONE", finished_at=now_iso(), blocked_reason=None)
        self.store.event("task-done", op, task_id=t["id"], route=route["verdict"], changed=len(changed))

    def verify_sandbox_prefix(self, t, tmpdir, git=None, python=None):
        """REQUIRED Seatbelt for a model-proposed verifier: `(deny default)`, so no network, Mach/LaunchServices/Apple
        Events or other system-mediated launch.

        Allowed: file reads (including Git); writes only to the private tmpdir (its TMPDIR) and /dev/null. The
        repository is read-only, even for the task's declared source files: a verifier must not alter what was just
        written and reviewed. `.git` and the runner home stay denied (the later deny wins); process-exec only inside
        the runner Python's prefixes and the trusted Git binaries (so `open`, `osascript`, `launchctl` and shells fail
        at exec). The declared paths are still validated as exact files. Raises ValueError when the scope is not
        exact or the policy cannot be built; returns None when no sandbox exists (the caller fails closed).
        """
        if self.cfg.sandbox == "off" or sys.platform != "darwin" or not shutil.which("sandbox-exec"):
            return None
        repo, tmp = Path(self.cfg.repo).resolve(), Path(tmpdir).resolve()
        files = []
        for rel in t["allowed_paths"]:
            why = exact_file_problem(repo, rel)
            if why:
                raise ValueError(f"declared write scope {rel!r} is not exact: {why}")
            f = (repo / rel).resolve()
            if repo not in f.parents or ".git" in f.relative_to(repo).parts:
                raise ValueError(f"declared write scope {rel!r} resolves outside the repo worktree")
            files.append(f)
        execs = set()
        exe, prefixes = python or (sys.executable, {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix})
        for pre in set(prefixes):  # `python` is the S0 verifier's pinned interpreter; default is the runner's own
            p = Path(pre).resolve()
            if len(p.parts) < 3 or str(p) in ("/usr", "/usr/local", "/opt", "/System", "/Library", "/Applications"):
                raise ValueError(f"python prefix {p} is too broad to allow process-exec under")
            execs.add(f'(subpath {json.dumps(str(p))})')
        execs.add(f'(literal {json.dumps(str(Path(exe).resolve()))})')
        for g in self.verify_git_paths(git or self.trusted_git()):
            execs.add(g)
        q = json.dumps  # Seatbelt string literals accept the same quoting for the characters that can occur in paths
        deny = [str(Path(self.cfg.home).resolve()), str((repo / ".git").resolve())]
        prof = self.cfg.home / "runs" / f"verify-{t['id']}.sb"
        atomic_write(prof, ("(version 1)\n(deny default)\n(allow file-read*)\n(allow sysctl-read)\n"
                            "(allow process-fork)\n(allow signal (target self))\n"
                            "(allow process-exec " + " ".join(sorted(execs)) + ")\n"
                            "(allow file-write* " + f"(subpath {q(str(tmp))}) " + '(literal "/dev/null")' + ")\n"
                            "(deny file-write* " + " ".join(f"(subpath {q(d)})" for d in deny) + ")\n").encode())
        return ["sandbox-exec", "-f", str(prof)]

    @staticmethod
    def trusted_git():
        """The developer-dir Git (`xcrun -f git`), resolved in the parent: the /usr/bin/git shim cannot locate the
        developer dir from inside the sandbox. Raises ValueError unless it is an absolute, existing, executable file
        under an Xcode*.app or CommandLineTools developer directory (fail closed)."""
        env = {"PATH": VERIFY_PATH}
        if "HOME" in os.environ:
            env["HOME"] = os.environ["HOME"]
        try:
            out = subprocess.run(["/usr/bin/xcrun", "-f", "git"], capture_output=True, text=True, timeout=10, env=env)
        except (OSError, subprocess.SubprocessError) as e:
            raise ValueError(f"cannot resolve the developer Git: {e}"[:200])
        raw = out.stdout.strip()
        if out.returncode != 0 or not raw or not os.path.isabs(raw):
            raise ValueError("xcrun did not return an absolute developer Git path")
        git = Path(raw).resolve()
        ok = (len(git.parts) >= 4 and git.parts[-3:] == ("usr", "bin", "git") and git.is_file()
              and os.access(git, os.X_OK)
              and (str(git).startswith("/Library/Developer/CommandLineTools/usr/bin/")
                   or re.fullmatch(r"/Applications/Xcode[^/]*\.app/Contents/Developer/usr/bin/git", str(git))))
        if not ok:
            raise ValueError(f"developer Git {git} is not an executable under Xcode.app or CommandLineTools")
        return git

    @staticmethod
    def verify_git_paths(git):
        """Seatbelt exec filters for exactly the trusted Git binary and its git-core helpers."""
        return [f'(literal {json.dumps(str(git))})',
                f'(subpath {json.dumps(str(git.parent.parent / "libexec" / "git-core"))})']

    def run_verify(self, t):
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        argv = list(t["verify_cmd"])
        tmpdir = None
        s0 = s0_marked(t) or s0_test_marked(t)
        if t.get("source") == "handoff" or s0:  # owner/manual verifiers keep their unsandboxed behaviour; S0 never does
            try:
                tmpdir = tempfile.mkdtemp(prefix="veyro-verify-")  # mode 0700, unique, created by the parent
                git = self.trusted_git()
                if s0 and argv[:1] != [S0_PYTHON]:
                    raise ValueError("the S0 verifier must be the pinned Python 3.13")
                prefix = self.verify_sandbox_prefix(t, tmpdir, git, s0_python() if s0 else None)
            except (OSError, ValueError) as e:
                prefix = None
                why = f"could not prepare the sandbox: {e}"[:200]
            else:
                why = "sandbox-exec unavailable or sandbox=off"
            if prefix is None:
                if tmpdir:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                return {"cmd": t["verify_cmd"], "exit": -1, "tail": f"verification refused, sandbox required: {why}"}
            argv = [*prefix, *argv]
            env["TMPDIR"] = str(Path(tmpdir).resolve())
            env["PATH"] = f"{git.parent}:{VERIFY_PATH}"  # plain `git` resolves to the developer Git, not the shim
        try:
            return self.run_verify_child(t, argv, env)
        finally:
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)

    def run_verify_child(self, t, argv, env):
        try:
            p = subprocess.Popen(argv, cwd=self.cfg.repo, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
                                 pass_fds=(self.wlock.fd,) if self.wlock.fd is not None else ())
            lstart = subprocess.run(["ps", "-o", "lstart=", "-p", str(p.pid)], capture_output=True,
                                    text=True).stdout.strip()
            t["verify_child"] = {"pid": p.pid, "lstart": lstart}
            self.store.save(self.state)
            deadline = time.monotonic() + self.cfg.verify_timeout
            try:
                while True:
                    try:
                        stdout, stderr = p.communicate(timeout=1)
                        return {"cmd": t["verify_cmd"], "exit": p.returncode, "tail": (stdout + stderr)[-1500:]}
                    except subprocess.TimeoutExpired:
                        self.heartbeat()
                        self.apply_commands()
                        interrupted = "signal" if self.sig else "stop" if self.state["control"] == "STOP" else None
                        if interrupted or time.monotonic() >= deadline:
                            self.kill_group(p.pid)
                            try:
                                stdout, stderr = p.communicate(timeout=5)
                            except subprocess.TimeoutExpired:  # a leaked grandchild still holds the pipes
                                stdout, stderr = "", ""
                            head = "verification interrupted" if interrupted else "verification timed out"
                            return {"cmd": t["verify_cmd"], "exit": -1,
                                    "tail": head + ("\n" + ((stdout or "") + (stderr or ""))[-1400:] if (stdout or stderr) else ""),
                                    "interrupted": interrupted}
            finally:
                self.kill_group(p.pid)  # unconditional, also after abnormal exits; no-op when the group is gone
                t["verify_child"] = None
                self.store.save(self.state)
        except OSError as e:
            return {"cmd": t["verify_cmd"], "exit": -1, "tail": f"could not run: {e}"[:300]}

    def record_usage(self, parsed):
        for m, u in (parsed.get("modelUsage") or {}).items():
            if not isinstance(u, dict):
                continue
            m = u.get("canonicalModel") if isinstance(u.get("canonicalModel"), str) and u.get("canonicalModel") else m
            agg = self.state["usage"].setdefault(m, {"runs": 0, "input": 0, "output": 0, "cache": 0, "cost_usd": 0.0})
            agg["runs"] += 1
            agg["input"] += _tokens(u, "inputTokens")
            agg["output"] += _tokens(u, "outputTokens")
            agg["cache"] += _tokens(u, "cacheReadInputTokens") + _tokens(u, "cacheCreationInputTokens")
            agg["cost_usd"] += _tokens(u, "costUSD")

    def failure(self, t, reason, op=None):
        t["stage"] = None
        self.store.event("attempt-failed", op, task_id=t["id"], reason=reason)
        self.requeue_or_fail(t, reason)

    def requeue_or_fail(self, t, reason):
        t["last_error"], t["updated_at"] = reason, now_iso()
        if (t["attempts"] >= self.cfg.max_attempts or s0_single_attempt(t)
                or t["id"] in (D16_F34_WRITE, D16_F34_REVIEW)
                or d16_single_attempt(self.state["tasks"], t)):
            # The owner's final F34 write, its sole review, and the dual-version admission have no transport retry entitlement.
            t["status"] = "FAILED"
            self.store.event("task-failed", f"{t['id']}:{t['attempts']}", task_id=t["id"], reason=reason)
        else:
            delay = backoff(self.cfg, t["attempts"])
            t.update(status="QUEUED", next_attempt_at=time.time() + delay)
            self.store.event("retry-scheduled", f"{t['id']}:{t['attempts']}", task_id=t["id"], delay_s=delay)


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")


# ---------------------------------------------------------- client-side helpers
def _paths(v, name, globs):
    if v in (None, []):
        return []
    if not (isinstance(v, list) and len(v) <= 200 and all(isinstance(x, str) and x for x in v)):
        raise ValueError(f"{name} must be a list of non-empty strings")
    for x in v:
        parts = Path(x).parts
        if (x.startswith("/") or ".." in parts or "\0" in x or parts[0] == ".git" or x == "PROJECT_INDEX.md"
                or x.startswith(BASELINE_PREFIXES)):
            raise ValueError(f"{name}: unsafe or protected path {x!r}")
        if not globs and (x.endswith("/") or any(c in x for c in "*?[")):
            raise ValueError(f"{name}: must be exact file paths, got {x!r}")
    return list(v)


def validate_task(d, cfg):
    """A task must declare how it will be externally verified; prose can never complete it."""
    if not (ID_RE.match(str(d.get("id", ""))) and MOD_RE.match(str(d.get("module", ""))) and d.get("role") in ROLES):
        raise ValueError("bad id/module/role")
    prompt = d.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000:
        raise ValueError("prompt must be a non-empty string under 100k chars")
    allowed, expected = _paths(d.get("allowed_paths"), "allowed_paths", True), _paths(d.get("expected_changes"), "expected_changes", False)
    verify = d.get("verify_cmd")
    if verify in (None, []):
        verify = []
    elif not (isinstance(verify, list) and len(verify) <= 50 and all(isinstance(x, str) and 0 < len(x) <= 500 for x in verify)):
        raise ValueError("verify_cmd must be an argv list of strings (no shell string)")
    if d["role"] in WRITE_ROLES:
        if not allowed:
            raise ValueError("a writing task must declare allowed_paths")
        if not (expected or verify):
            raise ValueError("a writing task needs expected_changes and/or verify_cmd; prose cannot complete it")
        if not all(in_scope(e, allowed) for e in expected):
            raise ValueError("expected_changes must lie within allowed_paths")
    elif allowed or expected or verify:
        raise ValueError("review roles are read-only: they are completed by an explicit OUTCOME marker only")
    plan_phase = d.get("plan_phase")
    if plan_phase is not None and not (isinstance(plan_phase, str) and ID_RE.match(plan_phase)):
        raise ValueError("plan_phase must be a short id")
    remediation_of = d.get("remediation_of")
    if remediation_of is not None and not (d["role"] in WRITE_ROLES and isinstance(remediation_of, str) and ID_RE.match(remediation_of)):
        raise ValueError("remediation_of must name the reviewed write task id and is only for writing roles")
    accounting_recovery_of = d.get("accounting_recovery_of")
    if accounting_recovery_of is not None and not (accounting_recovery_of == ACCOUNTING_RECOVERY_REVIEW
                                                   and d["id"] == ACCOUNTING_RECOVERY_WRITE
                                                   and d["role"] == "implement" and d["module"] == "MOD-004"):
        raise ValueError("accounting_recovery_of is restricted to the audited MOD-004 accounting incident")
    if accounting_recovery_of and (remediation_of or d.get("review_retry_of")):
        raise ValueError("accounting recovery cannot also be a remediation or review retry")
    review_of = d.get("review_of")
    if review_of is not None:
        changed = review_of.get("changed") if isinstance(review_of, dict) else None
        if not (d["role"] == "code-review" and isinstance(review_of, dict) and set(review_of) <= {"task_id", "changed"}
                and ID_RE.match(str(review_of.get("task_id", ""))) and
                (changed is None or (isinstance(changed, list) and len(changed) <= 200 and all(
                    isinstance(c, dict) and set(c) == {"path", "sha256"} and isinstance(c["path"], str) and c["path"]
                    and (c["sha256"] is None or (isinstance(c["sha256"], str) and SHA256_RE.fullmatch(c["sha256"])))
                    for c in changed)))):
            raise ValueError("review_of is only for code-review: {task_id, changed:[{path, sha256}]}")
        review_of = {"task_id": review_of["task_id"], "changed": None if changed is None else [dict(c) for c in changed]}
    retry_of = d.get("review_retry_of")
    if retry_of is not None and not (d["role"] == "code-review" and review_of and
                                     isinstance(retry_of, str) and ID_RE.match(retry_of)):
        raise ValueError("review_retry_of is only for a bound code-review")
    doc_base = d.get("doc_base")
    if doc_base is not None and not (plan_phase in (S0_DOC_MARKER, S0_REFRESH_MARKER, S0_REBIND_MARKER, S0_LOOP_MARKER, S0_DUAL_REBIND_MARKER, RECOVERY_MARKER) and d["role"] in WRITE_ROLES and isinstance(doc_base, dict)
                                     and set(doc_base) == set(S0_DOC_PATHS)
                                     and all(v is None or (isinstance(v, str) and SHA256_RE.fullmatch(v)) for v in doc_base.values())
                                     or plan_phase == S0_QA_MARKER and d["role"] in WRITE_ROLES and isinstance(doc_base, dict)
                                     and S0_QA_PACKET in doc_base and set(doc_base) <= set(S0_DOC_PATHS)
                                     and all(isinstance(v, str) and SHA256_RE.fullmatch(v) for v in doc_base.values())):
        raise ValueError("doc_base is only for a MOD004-S0-DOC, MOD004-S0-DOC-REFRESH, MOD004-S0-DOC-REBIND, MOD004-S0-LOOP-REBIND or MOD004-S0-D16-EVIDENCE-REBIND write: {path: sha256} for exactly the two document paths; "
                         "a MOD004-S0-QA-EVIDENCE write pins the packet sha256 (and the certificate's when named)")
    candidate = d.get("review_candidate")
    if candidate is not None and not (retry_of and isinstance(candidate, dict)
                                      and set(candidate) == {"head", "files", "diff_sha256", "candidate_sha256"}):
        raise ValueError("review_candidate is only for an operational review retry")
    return {"review_of": review_of, "review_gate": 1, "id": d["id"], "module": d["module"], "role": d["role"], "title": str(d.get("title") or d["id"])[:120],
            "plan_phase": plan_phase, "prompt": prompt, "allowed_paths": allowed, "expected_changes": expected,
            "verify_cmd": verify, "status": "QUEUED", "stage": None, "attempts": 0, "max_attempts": cfg.max_attempts,
            "next_attempt_at": 0, "created_at": d.get("created_at") or now_iso(), "updated_at": now_iso(),
            "child": None} | ({"remediation_of": remediation_of} if remediation_of else {}) | (
                {"accounting_recovery_of": accounting_recovery_of} if accounting_recovery_of else {}) | (
                {"review_retry_of": retry_of, "review_candidate": candidate} if retry_of else {}) | (
                {"doc_base": dict(doc_base)} if doc_base is not None else {})


def parse_doc_base(pairs):
    """`PATH=SHA256` or `PATH=absent`, one per document, as the doc_base mapping."""
    out = {}
    for x in pairs:
        path, sep, value = x.partition("=")
        if not sep or path in out:
            raise ValueError(f"--doc-base must be PATH=SHA256|absent, once per document: {x!r}")
        out[path] = None if value == "absent" else value
    return out


def enqueue(cfg, task):
    task = {**task, "created_at": now_iso()}
    if task.get("review_retry_of"):
        task["review_candidate"] = review_candidate(cfg.repo)
    t = validate_task(task, cfg)
    store = Store(cfg.home)
    state = store.load()
    handoff = state.get("handoff") or {}
    if handoff.get("request"):
        raise ValueError("an orchestrator handoff request is open: only the runner may enqueue until it settles")
    if handoff.get("quarantine"):
        raise ValueError(f"enqueue refused ({handoff['quarantine']}); run `rearm` once the owner has checked the gateway")
    # The same authoritative state used by dispatch governs owner-CLI ingress.
    # A consumed token with a missing ledger is DENY, never pre-activation NONE.
    qs, qreason = quarantine_state(cfg)
    if qs in (_QS_DENY, _QS_RESTARTED):
        raise ValueError(f"enqueue refused: S0/D16 quarantine {qs}: {qreason}")
    mode, why = _transition_mode(cfg)
    if mode == "HOLD":
        raise ValueError(f"enqueue refused: TRANSFER_HOLD: {why}")
    if task["id"] in state["tasks"]:
        raise ValueError(f"task id already exists: {task['id']}")
    if (s0_marked(t) or s0_doc_marked(t) or s0_refresh_marked(t) or s0_rebind_marked(t)
            or s0_test_marked(t) or s0_loop_marked(t) or s0_qa_marked(t)
            or s0_dual_rebind_marked(t) or _recovery_marked(t)):  # no S0 task may be queued for a runner that has not loaded this reviewed gate
        problem = s0_runner_problem(state)
        if problem:
            raise ValueError(f"task refused by S0 gate: {problem}")
    review_binding(cfg, t, state["tasks"], require_changed=False)  # fills the exact changed-file hashes from runner evidence
    task = {**task, "review_of": t["review_of"]}
    reason = gate_reason(cfg, t, state["tasks"])
    if reason:
        raise ValueError(f"task refused by prerequisite gate: {reason}")
    path = cfg.home / "queue" / f"{time.time_ns():020d}-{task['id']}.json"
    atomic_write(path, json.dumps(task).encode())
    return path


def send_command(cfg, cmd, op_id=None):
    op_id = op_id or f"cmd-{uuid.uuid4().hex[:12]}"
    Store(cfg.home)  # ensure dirs exist
    atomic_write(cfg.home / "commands" / f"{time.time_ns():020d}-{op_id}.json",
                 json.dumps({"cmd": cmd, "op_id": op_id, "ts": now_iso()}).encode())
    return op_id


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def child_alive(child):
    """Liveness of a recorded child: the pid must exist AND still carry the recorded start time (pid reuse is not alive)."""
    if not isinstance(child, dict) or not pid_alive(child.get("pid")):
        return False
    try:
        start = subprocess.run(["ps", "-o", "lstart=", "-p", str(child["pid"])], capture_output=True, text=True,
                               timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(start) and start == child.get("lstart")


def orchestrator_receipt(home):
    """Read an optional decision receipt from the actual orchestrating session.

    The runner does not make module-planning decisions. Missing or malformed
    evidence is UNKNOWN; this file never authorizes a dispatch.
    """
    path = Path(home) / "orchestrator.json"
    try:
        if path.stat().st_size > 16_384:
            raise ValueError("receipt too large")
        record = json.loads(path.read_text())
        if record.get("schema") != 1 or not record.get("decision_at") or not record.get("identity"):
            raise ValueError("invalid receipt")
        age = time.time() - datetime.datetime.fromisoformat(record["decision_at"]).timestamp()
        if age < -60:
            raise ValueError("future decision")
        keys = ("identity", "model", "model_evidence", "runtime", "session_key", "state", "decision",
                "last_action", "decision_at", "next_legal_action", "worker_task_id", "source")
        return {k: record.get(k) for k in keys} | {"age_s": max(0, round(age)), "evidence": "recorded"}
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return {"identity": "UNKNOWN", "model": "UNKNOWN", "state": "unknown", "evidence": "missing"}


def local_head_readonly(repo):
    """Resolve local HEAD without forking git from dashboard request threads."""
    try:
        gitdir = Path(repo) / ".git"
        if gitdir.is_file():  # worktree gitdir pointer
            pointer = gitdir.read_text().strip()
            if not pointer.startswith("gitdir: "):
                return None
            gitdir = (Path(repo) / pointer[8:]).resolve()
        head = (gitdir / "HEAD").read_text().strip()
        if head.startswith("ref: "):
            ref = head[5:]
            if not ref.startswith("refs/") or any(part in ("", ".", "..") for part in ref.split("/")):
                return None
            loose = gitdir / ref
            if loose.is_file():
                head = loose.read_text().strip()
            else:
                head = next((sha for line in (gitdir / "packed-refs").read_text().splitlines()
                             if not line.startswith(("#", "^"))
                             for sha, sep, name in (line.partition(" "),) if sep and name == ref), "")
        return head if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head) else None
    except (OSError, UnicodeError, ValueError):
        return None


def handoff_view(h):
    """Dashboard telemetry for the continuation handoff. Role (orchestrator) and model identity are separate fields."""
    if not isinstance(h, dict):
        return None
    req, last = h.get("request") or {}, h.get("last") or {}
    reported = last.get("model_reported")
    # The current turn's model is unknowable until the runtime reports it; a previous turn's model is never shown as current.
    model = ("UNKNOWN (current turn not yet reported)" if req else
             f"{reported} (runtime-reported by turn {last.get('id')})" if reported else "UNKNOWN (not reported by the runtime)")
    return {"status": h.get("status"), "detail": h.get("detail"), "updated_at": h.get("updated_at"),
            "role": "orchestrator", "agent": ORCH_AGENT, "attempts": h.get("attempts"),
            "fingerprint": (h.get("fingerprint") or "")[:12] or None, "quarantine": h.get("quarantine"),
            "retry_at": h.get("retry_at"),
            "model": model,
            "request": ({"id": req.get("id"), "started_at": req.get("started_at"),
                         "child_alive": child_alive(req.get("child"))} if req else None),
            "last": {k: last.get(k) for k in ("id", "finished_at", "how", "exit", "claim", "new_tasks")} if last else None}


def progress_state(st, runner_alive):
    """A heartbeat is liveness, not evidence of forward progress."""
    if st.get("control") in ("STOP", "PAUSE") or not runner_alive:
        return "STOPPED"
    h = st.get("handoff") or {}
    if st.get("health", {}).get("status") != "OK" or h.get("quarantine"):
        return "BLOCKED"
    if h.get("request") or any(t.get("status") == "RUNNING" or
                              (t.get("status") == "QUEUED" and not t.get("gate_reason"))
                              for t in st.get("tasks", {}).values()):
        return "WORKING"
    if h.get("status") == "waiting_for_owner":
        return "WAITING_FOR_OWNER"
    if h.get("status") == "blocked":
        return "BLOCKED"
    return "IDLE"


def snapshot(cfg):
    """Read-only truthful view used by `status` and the dashboard. Nothing here is verified by the reader:
    every field is what the runner last recorded (or, for lock/pid liveness, a passive probe)."""
    store, now = Store(cfg.home), time.time()
    try:
        st = store.load()
        err = None
    except StateCorrupt as e:
        st, err = {"tasks": {}, "usage": {}}, str(e)
    r = st.get("runner") or {}
    hb = None
    if r.get("heartbeat_at"):
        hb = now - datetime.datetime.fromisoformat(r["heartbeat_at"]).timestamp()
    alive = bool(r) and not r.get("stopped_at") and pid_alive(r.get("pid")) and hb is not None and hb < 10
    keys = ("id", "module", "role", "title", "plan_phase", "status", "stage", "attempts", "max_attempts", "last_error",
            "blocked_reason", "route", "result", "evidence", "allowed_paths", "expected_changes", "verify_cmd",
            "created_at", "started_at", "finished_at", "updated_at")
    tasks = []
    for t in st.get("tasks", {}).values():
        tasks.append({k: t.get(k) for k in keys}
                     | {"child_pid": (t.get("child") or {}).get("pid"),
                        "retry_in": max(0, round(t["next_attempt_at"] - now)) if t["status"] == "QUEUED"
                        and t.get("next_attempt_at", 0) > now else None})
    ci = None
    try:
        ci = clean_ci(json.loads((cfg.home / "ci.json").read_text()))
    except (OSError, ValueError):
        pass
    if ci is not None and ci.get("scope") != CI_SCOPE:  # legacy branch/PR cache: not evidence about main
        ci = clean_ci({"source": ci.get("source"), "last_attempt_at": ci.get("last_attempt_at"),
                       "error": ci.get("error") or "legacy-scope"})
    if ci is not None:
        local = local_head_readonly(cfg.repo)  # never fork git on a live dashboard request
        ci["local_head"] = local
        ci["head_matches_local"] = None if not local or not ci.get("head_sha") else ci["head_sha"] == local
        # Fresh requires a recent successful observation and no error on the latest attempt.
        obs = ci.get("observed_at")
        age = None
        try:
            age = now - datetime.datetime.fromisoformat(obs).timestamp() if obs else None
        except ValueError:
            pass
        limit = max(3 * cfg.ci_every, 30)
        ci["age_s"] = None if age is None else max(0, round(age))
        ci["state"] = "unavailable" if age is None else "stale" if age > limit or ci.get("error") else "fresh"
    pin = load_pin(cfg.home)
    lp = writer_lock_path(cfg.home, cfg.repo)
    held = FileLock.probe(lp)
    owner = FileLock(lp).owner() if held == "held" else None
    wl = {"state": held, "owner": owner,
          "runner_alive": pid_alive((owner or {}).get("runner_pid") or (owner or {}).get("pid")) if owner else None,
          "child_alive": pid_alive((owner or {}).get("child_pid")) if owner and owner.get("child_pid") else None}
    return {"generated_at": now_iso(), "state_error": err, "runner_alive": alive, "heartbeat_age_s": hb,
            "progress_state": progress_state(st, alive),
            "runner": r or None, "control": st.get("control"), "health": st.get("health"),
            "baseline": st.get("baseline"), "recoveries": st.get("recoveries", 0), "tasks": tasks,
            "baseline_pin": None if pin is None else ({"error": pin["error"]} if pin.get("error") else
                                                      {"pinned_at": pin["pinned_at"], "index_sha256": pin["index_sha256"],
                                                       "sources": len(pin["sources"])}),
            "usage": st.get("usage", {}), "ci": ci, "events": store.tail_events(200),
            "orchestrator": orchestrator_receipt(cfg.home), "handoff": handoff_view(st.get("handoff")),
            "pending_commands": len(store.pending_commands()), "writer_lock": wl}


def write_launchagents(cfg, write):
    py, me = sys.executable, str(Path(__file__).resolve())
    logs = cfg.home / "logs"
    env = {"PATH": f"{Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin", "HOME": str(Path.home()),
           "VEYRO_RUNNER_HOME": str(cfg.home), "VEYRO_CI_MODE": "public"}
    jobs = {"com.veyro.mod000-runner": ["run"], "com.veyro.mod000-dashboard": ["dashboard"]}
    out = []
    for label, args in jobs.items():
        plist = {"Label": label, "ProgramArguments": [py, me, *args], "WorkingDirectory": str(cfg.repo),
                 "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 30,
                 "EnvironmentVariables": env | {"PYTHONPYCACHEPREFIX": str(cfg.home / "pycache" / label)}  # never import repo __pycache__
                                         | ({"VEYRO_AUTOCONTINUE": "1"} if args == ["run"] else {}),  # explicit opt-in, runner only
                 "ProcessType": "Interactive" if label == "com.veyro.mod000-dashboard" else "Standard",  # Background throttled verifiers ~10x
                 "StandardOutPath": str(logs / f"{label}.out.log"), "StandardErrorPath": str(logs / f"{label}.err.log")}
        path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
        if write:
            if path.exists():
                raise SystemExit(f"refusing to overwrite existing {path}; remove it deliberately first")
            path.parent.mkdir(parents=True, exist_ok=True)
            Path(plist["EnvironmentVariables"]["PYTHONPYCACHEPREFIX"]).mkdir(parents=True, mode=0o700, exist_ok=True)
            atomic_write(path, plistlib.dumps(plist))
        out.append((path, plist))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="runner.py", description=__doc__.splitlines()[0])
    ap.add_argument("--home", help="state dir (default: platform state dir or $VEYRO_RUNNER_HOME)")
    ap.add_argument("--repo", default=str(REPO), help="repository root holding PROJECT_INDEX.md")
    ap.add_argument("--claude-bin", help="claude executable (default: $VEYRO_CLAUDE_BIN or `claude`)")
    ap.add_argument("--tick", type=float, default=1.0)
    ap.add_argument("--openclaw-bin", help="OpenClaw CLI for automatic continuation (default: $VEYRO_ORCHESTRATOR_BIN, PATH, nvm)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the mission loop (foreground)")
    d = sub.add_parser("dashboard", help="serve the read-only dashboard on 127.0.0.1")
    d.add_argument("--port", type=int, default=8766)  # 8765 was the retired epoch's board
    e = sub.add_parser("enqueue", help="queue a task (does not start anything by itself)")
    e.add_argument("--id", required=True)
    e.add_argument("--module", required=True)
    e.add_argument("--role", required=True, choices=sorted(ROLES))
    e.add_argument("--title")
    e.add_argument("--prompt-file", required=True)
    e.add_argument("--plan-phase", help="owner-declared phase label shown on the dashboard")
    e.add_argument("--allow", action="append", default=[], help="repo path/prefix/ (or glob) a writing task may change")
    e.add_argument("--expect", action="append", default=[], help="exact file that must change")
    e.add_argument("--verify-cmd", help='JSON argv list run by the runner after the child, e.g. \'["python3","-m","unittest"]\'')
    e.add_argument("--review-of", help="code-review only: id of the DONE write task this review is bound to (changed-file hashes are filled from runner evidence)")
    e.add_argument("--review-retry-of", help="owner-audited operational BLOCKED review id; permits one unchanged-candidate retry only")
    e.add_argument("--accounting-recovery-of", help="one audited MOD-004 source-inaccessible accounting review id; fresh write only")
    e.add_argument("--remediation-of", help="MOD004-S0-DOC: the document write whose exact-bound review requested changes; or the one MOD004-S0-DOC-REBIND repair (its exact id only): the incomplete rebind write")
    e.add_argument("--doc-base", action="append", default=[], metavar="PATH=SHA256|absent",
                   help="MOD004-S0-DOC / -REFRESH / -REBIND / MOD004-S0-LOOP-REBIND / MOD004-S0-QA-EVIDENCE (packet, +certificate if named) only, once per document: the exact current content hash this write starts from")
    for c in ("pause", "resume", "stop"):
        x = sub.add_parser(c)
        x.add_argument("--op-id")
    pm = sub.add_parser("promote-mod004-capability", help="queue exact-two-file reviewed MOD-004 rule promotion")
    pm.add_argument("--task-id", required=True)
    pm.add_argument("--rls-sha256", required=True)
    pm.add_argument("--console-sha256", required=True)
    x = sub.add_parser("rearm", help="OWNER STEP: offer the current state to the orchestrator again after a settled/blocked handoff")
    x.add_argument("--op-id")
    sub.add_parser("status")
    sub.add_parser("ci-observe-public", help=argparse.SUPPRESS)  # internal: supervised child of the public observer
    sub.add_parser("verify-baseline", help="check the repo against the out-of-repo pin")
    sub.add_parser("s0-probe", help="read-only MOD-004 S0 gate probe: queues, locks and writes nothing; exit 0 only if open")
    sub.add_parser("d16-successor-probe", help="read-only MOD-004 D16 successor gate probe: queues, locks and writes nothing; exit 0 only if open and every other case is refused")
    sub.add_parser("noncap-probe", help="read-only MOD-004 non-CAP design gate probe: queues, locks and writes nothing; exit 0 only if healthy")
    pb =sub.add_parser("pin-baseline", help="OWNER STEP: pin PROJECT_INDEX.md + source hashes outside the repo (one time)")
    pb.add_argument("--confirm-index-sha256", help="sha256 of the PROJECT_INDEX.md you reviewed (shasum -a 256)")
    la = sub.add_parser("launchagent", help="print (default) or write LaunchAgent plists; never loads them")
    la.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    try:
        cfg = Config(home=a.home, repo=a.repo, claude_bin=a.claude_bin, tick=a.tick,
                     orchestrator_bin=(a.openclaw_bin or os.environ.get("VEYRO_ORCHESTRATOR_BIN") or
                                       (discover_orchestrator_bin() if a.cmd == "run" and os.environ.get("VEYRO_AUTOCONTINUE") == "1"
                                        else None)))  # continuation is an explicit owner opt-in, never implied by the binary existing
    except ValueError as ex:
        print(f"invalid configuration: {ex}", file=sys.stderr)
        return 2

    if a.cmd == "ci-observe-public":  # read-only; prints one JSON object, never raw server text
        try:
            print(json.dumps(fetch_ci_public(cfg)))
            return 0
        except CIError as ex:
            print(json.dumps({"error": str(ex.args[0])}))
        except Exception:
            print(json.dumps({"error": "github-api-failed"}))
        return 1
    if a.cmd == "run":
        return Runner(cfg).run()
    if a.cmd == "dashboard":
        dashboard = _trusted_dashboard()
        return dashboard.serve(cfg, a.port)
    if a.cmd == "enqueue":
        try:
            repair = (a.plan_phase, a.id, a.remediation_of) == (S0_REBIND_MARKER, S0_REBIND_REPAIR_ID, S0_REBIND_ROOT_ID)
            if a.remediation_of and a.plan_phase != S0_DOC_MARKER and not repair and not noncap_cli_remediation_shape(a):
                raise ValueError("--remediation-of is accepted here only for MOD004-S0-DOC document writes, the one "
                                 "MOD004-S0-DOC-REBIND repair task and exact MOD-004 non-CAP design/documentation writes")
            p = enqueue(cfg, {"id": a.id, "module": a.module, "role": a.role, "title": a.title,
                              "plan_phase": a.plan_phase, "allowed_paths": a.allow, "expected_changes": a.expect,
                              "verify_cmd": json.loads(a.verify_cmd) if a.verify_cmd else None,
                              "review_of": {"task_id": a.review_of} if a.review_of else None,
                              "review_retry_of": a.review_retry_of,
                              "accounting_recovery_of": a.accounting_recovery_of,
                              "remediation_of": a.remediation_of,
                              "doc_base": parse_doc_base(a.doc_base) if a.doc_base else None,
                              "prompt": Path(a.prompt_file).read_text()})
        except (ValueError, OSError) as ex:
            print(f"enqueue refused: {ex}", file=sys.stderr)
            return 2
        print(f"queued {a.id} (runner picks it up on its next tick)")
        return 0
    if a.cmd in CONTROLS or a.cmd == "rearm":
        op = send_command(cfg, a.cmd, a.op_id)
        snap = snapshot(cfg)
        print(json.dumps({"op_id": op, "command": a.cmd, "runner_alive": snap["runner_alive"],
                          "note": None if snap["runner_alive"] else "runner not running; applied when it next starts"}))
        return 0
    if a.cmd == "promote-mod004-capability":
        if not ID_RE.fullmatch(a.task_id) or not all(SHA256_RE.fullmatch(h) for h in
                                                     (a.rls_sha256, a.console_sha256)):
            print("promotion refused: invalid task id or SHA256", file=sys.stderr)
            return 2
        op = f"promotion-{uuid.uuid4().hex[:12]}"
        command = {"cmd": a.cmd, "op_id": op, "task_id": a.task_id, "ts": now_iso(),
                   "hashes": {list(MOD004_PROMOTION)[0]: a.rls_sha256,
                              list(MOD004_PROMOTION)[1]: a.console_sha256}}
        atomic_write(cfg.home / "commands" / f"{time.time_ns():020d}-{op}.json",
                     json.dumps(command, sort_keys=True).encode())
        print(json.dumps({"op_id": op, "status": "queued; runner will validate review and hashes under writer lock"}))
        return 0
    if a.cmd == "s0-probe":
        reason = s0_probe(cfg)
        print(json.dumps({"s0_route": "open" if reason is None else "closed", "reason": reason}))
        return 0 if reason is None else 1
    if a.cmd == "d16-successor-probe":
        res = d16_successor_probe(cfg)
        ok = res.get("successor") is None and all(res.get(k) for k in ("other_id", "cap", "old_root_fourth"))
        print(json.dumps({"d16_successor_route": "open" if ok else "closed", "cases": res}))
        return 0 if ok else 1
    if a.cmd == "noncap-probe":
        res = noncap_probe(cfg)
        ok = res.get("design") is None and all(res.get(k) for k in ("cap", "s0_product"))
        print(json.dumps({"noncap_route": "healthy" if ok else "closed", "cases": res}))
        return 0 if ok else 1
    if a.cmd == "status":
        s = snapshot(cfg)
        s.pop("events")
        print(json.dumps(s, indent=1))
        return 0
    if a.cmd == "verify-baseline":
        res = verify_baseline(cfg.repo, load_pin(cfg.home))
        print(json.dumps(res, indent=1))
        return 0 if res["ok"] else 1
    if a.cmd == "pin-baseline":
        idx = Path(cfg.repo) / "PROJECT_INDEX.md"
        try:
            actual = hashlib.sha256(idx.read_bytes()).hexdigest()
        except OSError as ex:
            print(f"cannot read {idx}: {ex}", file=sys.stderr)
            return 2
        if not a.confirm_index_sha256:
            print(f"Review {idx}, then re-run with --confirm-index-sha256 {actual}\n"
                  f"Rows that would be pinned:\n" + "\n".join(f"  {n}  {h}" for n, h in parse_index(idx.read_text())),
                  file=sys.stderr)
            return 2
        try:
            pin = bootstrap_pin(cfg, a.confirm_index_sha256)
        except PinError as ex:
            print(f"pin refused: {ex}", file=sys.stderr)
            return 2
        print(f"pinned {len(pin['sources'])} sources + index {pin['index_sha256']} -> {pin_path(cfg.home)}")
        return 0
    if a.cmd == "launchagent":
        for path, plist in write_launchagents(cfg, a.write):
            print(f"# {path}" + (" (written, NOT loaded)" if a.write else ""))
            if not a.write:
                print(plistlib.dumps(plist).decode())
        print(f"# to load: launchctl bootstrap gui/{os.getuid()} <plist>   # to remove: launchctl bootout gui/{os.getuid()}/<label>")
        return 0


if __name__ == "__main__":
    sys.exit(main())
