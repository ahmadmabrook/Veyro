#!/usr/bin/env python3
"""Veyro MOD-000 Continuous Mission Runner (Python stdlib only).

Durable single-runner / single-repo-writer task runner. All runtime state lives
in the state dir (default outside the repo); this process never writes to the
repository itself. See knowledge/03-Modules/MOD-000/MOD-000.md.
"""
import argparse
import datetime
import fcntl
import fnmatch
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace
import uuid
from pathlib import Path

SCHEMA = 1
REPO = Path(__file__).resolve().parents[2]
CODE_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

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
                 gate_mode=None):
        self.home = Path(home) if home else default_home()
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
def _git(repo, *args, timeout=120):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, timeout=timeout,
                          env={**{k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}, "GIT_OPTIONAL_LOCKS": "0"})


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
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True, text=True)
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
            self.state["runner"] = {"pid": os.getpid(), "host": socket.gethostname(), "started_at": now_iso(),
                                    "heartbeat_at": now_iso(), "code_sha256": CODE_SHA,
                                    "python": sys.version.split()[0], "executable": sys.executable,
                                    "claude_bin": self.cfg.claude_bin, "repo": str(self.cfg.repo)}
            self.store.event("runner-start", pid=os.getpid(), code_sha256=CODE_SHA)
            self.recover()
            self.apply_commands()
            while not self.sig and self.state["control"] != "STOP":
                self.tick()
                time.sleep(self.cfg.tick)
            self.finish()
            return 0
        finally:
            self.rlock.release()

    def finish(self):
        reason = "STOP" if self.state["control"] == "STOP" else "signal"
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
            self.state["recoveries"] += 1
            t["child"], t["stage"] = None, None
            self.store.event("recovered-interrupted", op, task_id=t["id"], orphan_reaped=reaped)
            self.requeue_or_fail(t, "interrupted by runner crash/restart")
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
        if self.state["control"] == "RUN" and self.state["health"]["status"] == "OK":
            t = self.next_ready()
            if t:
                self.dispatch(t)
        self.refresh_ci()
        self.store.save(self.state)

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
        for f in sorted((self.cfg.home / "queue").glob("*.json")):
            try:
                t = validate_task(json.loads(f.read_text()), self.cfg)
            except Exception as e:
                f.rename(f.with_suffix(".rejected"))
                self.store.event("task-rejected", file=f.name, reason=str(e))
                continue
            if t["id"] not in self.state["tasks"]:  # idempotent re-ingest
                self.state["tasks"][t["id"]] = t
                self.store.save(self.state)  # durable BEFORE the queue file is consumed
                self.store.event("task-queued", f"{t['id']}:0", task_id=t["id"], module=t["module"], role=t["role"])
            f.unlink()

    def apply_commands(self):
        for f in self.store.pending_commands():
            try:
                c = json.loads(f.read_text())
                if not (c["cmd"] in CONTROLS and ID_RE.match(str(c["op_id"]))):
                    raise ValueError("bad command or op_id")
            except Exception as e:
                f.rename(f.with_suffix(".rejected"))
                self.store.event("command-rejected", file=f.name, reason=str(e))
                continue
            if c["op_id"] in self.state["applied_ops"]:
                self.store.event("command-duplicate", c["op_id"], cmd=c["cmd"])
            else:
                prev, self.state["control"] = self.state["control"], CONTROLS[c["cmd"]]
                self.state["applied_ops"] = (self.state["applied_ops"] + [c["op_id"]])[-500:]
                self.store.event("command-applied", c["op_id"], cmd=c["cmd"], prev=prev, now=self.state["control"])
            self.store.save(self.state)  # persist the op id before consuming the file
            f.unlink()

    def next_ready(self):
        ready = [t for t in self.state["tasks"].values()
                 if t["status"] == "QUEUED" and t.get("next_attempt_at", 0) <= time.time()]
        return min(ready, key=lambda t: t["created_at"]) if ready else None

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
        return t["prompt"] + "\n\n---\n" + c + "\n"

    # --- dispatch
    def dispatch(self, t):
        if not self.check_baseline(force=True):
            return
        if not self.wlock.acquire({"pid": os.getpid(), "task_id": t["id"]}):
            if not self.busy_noted:
                self.store.event("writer-lock-busy", owner=self.wlock.owner())
                self.busy_noted = True
            return
        self.busy_noted = False
        try:
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
            alias = required_family(t["role"])
            t["attempts"] += 1
            op = f"{t['id']}:{t['attempts']}"
            t.update(status="RUNNING", stage="child", updated_at=now_iso(), started_at=now_iso(), child=None,
                     blocked_reason=None, finished_at=None)
            self.store.save(self.state)  # RUNNING is durable before the child exists
            self.store.event("dispatch", op, task_id=t["id"], role=t["role"], model_alias=alias, attempt=t["attempts"])
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
                    p.stdin.write(self.child_prompt(t).encode())
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
        changed, head_moved = [], False
        try:
            after = repo_state(self.cfg.repo)
            changed, head_moved = diff_state(before, after), before["head"] != after["head"]
        except Exception as e:
            bad.append(("REPO_SNAPSHOT_UNAVAILABLE", str(e)[:200]))
        write = t["role"] in WRITE_ROLES
        if write and not changed:
            bad.append(("NO_DELIVERABLE_CHANGE", "writing task changed no repository file"))
        if head_moved:
            bad.append(("HEAD_MOVED", "the child changed git HEAD"))
        stray = [c for c in changed if not in_scope(c, t["allowed_paths"])]
        if stray:
            bad.append(("OUT_OF_SCOPE_CHANGE", f"outside declared scope: {stray[:10]}"))
        missing = [e for e in t["expected_changes"] if e not in changed]
        if missing:
            bad.append(("EXPECTED_CHANGE_MISSING", f"declared but unchanged: {missing}"))
        verify = None
        if write and t["verify_cmd"] and not stray and not head_moved:
            verify = self.run_verify(t)
            if verify.get("interrupted"):
                t.update(status="QUEUED", stage="verify_pending", updated_at=now_iso())
                self.store.save(self.state)
                return self.store.event("verification-paused", op, task_id=t["id"], why=verify["interrupted"])
            if verify["exit"] != 0:
                bad.append(("VERIFICATION_FAILED", f"verify_cmd exit {verify['exit']}"))
        review = None
        if not write:
            lines = [ln.strip() for ln in str(parsed.get("result", "")).splitlines() if ln.strip()]
            m = OUTCOME_RE.match(lines[-1]) if lines else None
            review = m.group(1) if m else None
            if review is None:
                bad.append(("NO_REVIEW_OUTCOME", "final line is not an explicit OUTCOME: marker"))
            elif review != "APPROVED":
                bad.append((f"REVIEW_{review}", f"reviewer outcome {review}"))

        base = Path(self.cfg.repo)
        evidence = {"op": op, "at": now_iso(), "subtype": parsed.get("subtype"),
                    "permission_denials": len(denials) if isinstance(denials, list) else None,
                    "route_verdict": route["verdict"], "isolation": iso, "head_moved": head_moved,
                    "changed": [{"path": c, "sha256": _path_hash(base / c)} for c in changed],
                    "expected_changes": t["expected_changes"], "allowed_paths": t["allowed_paths"],
                    "verify": verify, "review_outcome": review, "violations": [c for c, _ in bad]}
        atomic_write(Path(str(out)[:-4] + ".evidence.json"), json.dumps(evidence, indent=1, sort_keys=True).encode())
        t["evidence"], t["stage"], t["result"] = evidence, None, str(parsed.get("result", ""))[:500]
        t.pop("verify_checkpoint", None)
        if bad:
            t.update(status="BLOCKED", blocked_reason=bad[0][0], last_error="; ".join(f"{c}: {d}" for c, d in bad)[:600])
            return self.store.event("task-blocked", op, task_id=t["id"], code=bad[0][0], violations=[c for c, _ in bad])
        t.update(status="DONE", finished_at=now_iso(), blocked_reason=None)
        self.store.event("task-done", op, task_id=t["id"], route=route["verdict"], changed=len(changed))

    def run_verify(self, t):
        env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            p = subprocess.Popen(t["verify_cmd"], cwd=self.cfg.repo, env=env, stdin=subprocess.DEVNULL,
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
                            p.communicate()
                            return {"cmd": t["verify_cmd"], "exit": -1,
                                    "tail": "verification interrupted" if interrupted else "verification timed out",
                                    "interrupted": interrupted}
            finally:
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
        if t["attempts"] >= self.cfg.max_attempts:
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
    return {"id": d["id"], "module": d["module"], "role": d["role"], "title": str(d.get("title") or d["id"])[:120],
            "plan_phase": plan_phase, "prompt": prompt, "allowed_paths": allowed, "expected_changes": expected,
            "verify_cmd": verify, "status": "QUEUED", "stage": None, "attempts": 0, "max_attempts": cfg.max_attempts,
            "next_attempt_at": 0, "created_at": d.get("created_at") or now_iso(), "updated_at": now_iso(),
            "child": None}


def enqueue(cfg, task):
    task = {**task, "created_at": now_iso()}
    validate_task(task, cfg)
    store = Store(cfg.home)
    if task["id"] in store.load()["tasks"]:
        raise ValueError(f"task id already exists: {task['id']}")
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
        try:  # local read only: lets the dashboard refuse to imply CI covers unpushed local work
            local = _git(cfg.repo, "rev-parse", "HEAD", timeout=2).stdout.decode().strip()
        except (subprocess.SubprocessError, OSError):
            local = None
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
            "runner": r or None, "control": st.get("control"), "health": st.get("health"),
            "baseline": st.get("baseline"), "recoveries": st.get("recoveries", 0), "tasks": tasks,
            "baseline_pin": None if pin is None else ({"error": pin["error"]} if pin.get("error") else
                                                      {"pinned_at": pin["pinned_at"], "index_sha256": pin["index_sha256"],
                                                       "sources": len(pin["sources"])}),
            "usage": st.get("usage", {}), "ci": ci, "events": store.tail_events(200),
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
                 "EnvironmentVariables": env, "ProcessType": "Background",
                 "StandardOutPath": str(logs / f"{label}.out.log"), "StandardErrorPath": str(logs / f"{label}.err.log")}
        path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
        if write:
            if path.exists():
                raise SystemExit(f"refusing to overwrite existing {path}; remove it deliberately first")
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, plistlib.dumps(plist))
        out.append((path, plist))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="runner.py", description=__doc__.splitlines()[0])
    ap.add_argument("--home", help="state dir (default: platform state dir or $VEYRO_RUNNER_HOME)")
    ap.add_argument("--repo", default=str(REPO), help="repository root holding PROJECT_INDEX.md")
    ap.add_argument("--claude-bin", help="claude executable (default: $VEYRO_CLAUDE_BIN or `claude`)")
    ap.add_argument("--tick", type=float, default=1.0)
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
    for c in ("pause", "resume", "stop"):
        x = sub.add_parser(c)
        x.add_argument("--op-id")
    sub.add_parser("status")
    sub.add_parser("ci-observe-public", help=argparse.SUPPRESS)  # internal: supervised child of the public observer
    sub.add_parser("verify-baseline", help="check the repo against the out-of-repo pin")
    pb = sub.add_parser("pin-baseline", help="OWNER STEP: pin PROJECT_INDEX.md + source hashes outside the repo (one time)")
    pb.add_argument("--confirm-index-sha256", help="sha256 of the PROJECT_INDEX.md you reviewed (shasum -a 256)")
    la = sub.add_parser("launchagent", help="print (default) or write LaunchAgent plists; never loads them")
    la.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    try:
        cfg = Config(home=a.home, repo=a.repo, claude_bin=a.claude_bin, tick=a.tick)
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
        import dashboard
        return dashboard.serve(cfg, a.port)
    if a.cmd == "enqueue":
        try:
            p = enqueue(cfg, {"id": a.id, "module": a.module, "role": a.role, "title": a.title,
                              "plan_phase": a.plan_phase, "allowed_paths": a.allow, "expected_changes": a.expect,
                              "verify_cmd": json.loads(a.verify_cmd) if a.verify_cmd else None,
                              "prompt": Path(a.prompt_file).read_text()})
        except (ValueError, OSError) as ex:
            print(f"enqueue refused: {ex}", file=sys.stderr)
            return 2
        print(f"queued {a.id} (runner picks it up on its next tick)")
        return 0
    if a.cmd in CONTROLS:
        op = send_command(cfg, a.cmd, a.op_id)
        snap = snapshot(cfg)
        print(json.dumps({"op_id": op, "command": a.cmd, "runner_alive": snap["runner_alive"],
                          "note": None if snap["runner_alive"] else "runner not running; applied when it next starts"}))
        return 0
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
