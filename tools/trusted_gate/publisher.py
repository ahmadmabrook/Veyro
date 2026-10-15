"""MOD-001 trusted gate: keyless evaluator (slice 1) and App check publisher (slice 2).

Evaluates an open same-repo PR into main against a pinned `.github` tree OID
and the foundation workflow's push run. It never checks out or executes
candidate code. Only an exact `success` can yield PASS; every error is BLOCKED,
every mismatch FAIL. `--dry-run` is keyless and never publishes.

The `publish` command (slice 2) evaluates first, and only for PASS/FAIL reads
the GitHub App private key from a 0400 PEM file owned by the dedicated signer
account, signs an App JWT with openssl (key passed by file descriptor), mints an
in-memory installation token limited to the Veyro repo and `checks:write`, and
posts one completed check run named `veyro-trusted-gate` with conclusion
`success` or `failure` only. BLOCKED never publishes (head mismatch/move and job
ambiguity are BLOCKED). The config is root-owned at one fixed path and pins this
file's SHA-256.

Production entry is exactly `<RUNTIME_ROOT>/bin/python3 -I <installed publisher> publish
--config /Library/VeyroGate/etc/config.json --pr N`, run as the dedicated non-admin signer
account through restricted sudo. Anything else is a fixed `bad-argv`. Before the
key, network or state are touched, it requires: hardened process (no core dumps,
umask 077, cwd `/`), the root-installed Python runtime (exact interpreter realpath,
prefix, every sys.path entry and loaded module root-owned inside the runtime tree),
a root-owned installed copy outside every git worktree
under a root-owned directory chain, a clean environment, and a non-root real and
effective uid equal to both the config `signer_uid` and the uid provisioned into
`EXPECTED_SIGNER_UID`. No key, path, host, workflow or check name comes from the
caller. Live account provisioning and sudo rules are outside this repo.
"""
import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import resource
import stat
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"
EXIT = {PASS: 0, FAIL: 1, BLOCKED: 3}
DEFAULT_WORKFLOW = ".github/workflows/veyro-foundation-ci.yml"
DEFAULT_JOB = "foundation (MOD-000 focused checks)"
HTTP_TIMEOUT = 10
GIT_BIN = "/usr/bin/git"  # keyless --dry-run development only; never used by `publish`
TRUSTED_GIT_BIN = "/Library/VeyroGate/runtime/git/bin/git"  # production: root-installed copy
TRUSTED_GIT_EXEC_PATH = "/Library/VeyroGate/runtime/git/libexec/git-core"
GIT_TIMEOUT = 60
MAX_BODY = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{40}")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class Gate(Exception):
    def __init__(self, verdict, reason):
        super().__init__(reason)
        self.verdict, self.reason = verdict, reason


def _fail(reason):
    return Gate(FAIL, reason)


def _blocked(reason):
    return Gate(BLOCKED, reason)


def http_get(path, opener=None):
    """Bounded unauthenticated GET against api.github.com; returns parsed JSON.

    Default transport: no proxy, no redirects, fixed TLS trust file."""
    req = urllib.request.Request("https://api.github.com" + path, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "veyro-trusted-gate"})
    open_ = opener or _build_opener().open
    try:
        with open_(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read(MAX_BODY + 1)
    except urllib.error.HTTPError as e:
        try:
            e.close()
        except Exception:
            pass
        raise _blocked(f"http-{e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise _blocked("http-unreachable") from None
    if len(body) > MAX_BODY:
        raise _blocked("http-too-large")
    try:
        data = json.loads(body)
    except ValueError:
        raise _blocked("http-bad-json") from None
    if not isinstance(data, dict):
        raise _blocked("http-bad-shape")
    return data


def _fetch_pr(repo, pr, run, git_bin, env):
    """Fetch refs/pull/N/head as inert objects into a throwaway bare repo with the given git and env.

    Private: callers are `git_fetch_pr` (keyless development) and `trusted_git_fetch_pr` (production),
    each of which fixes its own `git_bin` and `env`."""
    ref = f"refs/pull/{pr}/head"

    def git(*args):
        try:
            p = run([git_bin, *args], cwd=tmp, env=env, capture_output=True, text=True,
                    timeout=GIT_TIMEOUT, check=False)
        except (subprocess.TimeoutExpired, OSError):
            raise _blocked("git-error") from None
        if p.returncode != 0:
            raise _blocked("git-error")
        return p.stdout.strip()

    with tempfile.TemporaryDirectory(prefix="veyro-gate-") as tmp:
        git("init", "--bare", "-q", "--template=", ".")
        git("-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
            "-c", "http.proxy=", "-c", "http.followRedirects=false",
            "-c", "fetch.fsckObjects=true", "fetch", "--no-tags", "--depth=1", "-q",
            f"https://github.com/{repo}.git", f"+{ref}:{ref}")
        sha = git("rev-parse", "--verify", ref)
        tree = git("rev-parse", "--verify", f"{sha}:.github")
    return sha, tree


def git_fetch_pr(repo, pr, run=subprocess.run):
    """KEYLESS DEVELOPMENT ONLY (`--dry-run`): inert fetch with the system `/usr/bin/git`.

    `/usr/bin/git` is an xcrun shim into an admin-writable Xcode tree, so it is never trusted for
    production. `publish` uses `trusted_git_fetch_pr`. Returns (fetched_head_sha, head:.github tree oid)."""
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
           "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    return _fetch_pr(repo, pr, run, GIT_BIN, env)


def trusted_git_fetch_pr(repo, pr, run=subprocess.run, verify=None):
    """PRODUCTION: inert fetch with only the root-installed `TRUSTED_GIT_BIN` and the fixed
    `TRUSTED_GIT_EXEC_PATH` helper directory. Neither path is a parameter; the trust check is repeated
    immediately before use. Returns (fetched_head_sha, head:.github tree oid)."""
    (check_trusted_git if verify is None else verify)()
    env = {"PATH": os.path.dirname(TRUSTED_GIT_BIN) + ":" + TRUSTED_GIT_EXEC_PATH, "HOME": "/nonexistent",
           "GIT_EXEC_PATH": TRUSTED_GIT_EXEC_PATH, "GIT_TERMINAL_PROMPT": "0",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    return _fetch_pr(repo, pr, run, TRUSTED_GIT_BIN, env)


def _trusted_git_file(path, owners, top):
    if os.path.normpath(path) != path or os.path.realpath(path) != path:
        return False
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode) or st.st_uid not in owners or st.st_mode & 0o022 \
            or not st.st_mode & 0o100:
        return False
    return _strict_chain(os.path.dirname(path), owners, top)


def check_trusted_git(binary=None, exec_path=None, owners=(0,), top="/"):
    """Pre-secret guard: the production git binary, its `git-remote-https` helper and the helper
    directory must be real (no symlink anywhere in the path), root-owned and not group/other writable,
    with a strict root-owned directory chain to `top`. Root ownership of `/usr/bin/git` is not
    transferable: only the installed copy at the fixed paths is accepted.
    Defaults are the production constants; only tests relax them."""
    binary = TRUSTED_GIT_BIN if binary is None else binary
    exec_path = TRUSTED_GIT_EXEC_PATH if exec_path is None else exec_path
    try:
        if not (_trusted_git_file(binary, owners, top)
                and _trusted_git_file(os.path.join(exec_path, "git-remote-https"), owners, top)
                and os.path.realpath(exec_path) == exec_path and _strict_chain(exec_path, owners, top)):
            raise _blocked("git-untrusted")
    except (OSError, ValueError):
        raise _blocked("git-untrusted") from None


def _need(cond, reason):
    if not cond:
        raise _fail(reason)


def _pr_head(cfg, get):
    repo = cfg["repo"].lower()
    pr = get(f"/repos/{cfg['repo']}/pulls/{cfg['pr']}")
    try:
        sha = pr["head"]["sha"]
        _need(pr["state"] == "open", "pr-not-open")
        _need(pr["base"]["ref"] == "main", "base-not-main")
        _need((pr["base"]["repo"] or {}).get("full_name", "").lower() == repo, "base-repo-mismatch")
        _need((pr["head"]["repo"] or {}).get("full_name", "").lower() == repo, "fork-or-deleted-head-repo")
    except (KeyError, TypeError, AttributeError):
        raise _blocked("pr-bad-shape") from None
    _need(isinstance(sha, str) and _SHA.fullmatch(sha), "pr-bad-head-sha")
    return sha


def _latest_run(cfg, sha, get):
    repo = cfg["repo"]
    data = get(f"/repos/{repo}/actions/runs?head_sha={sha}&event=push&per_page=100")
    runs = data.get("workflow_runs")
    if not isinstance(runs, list) or not isinstance(data.get("total_count"), int):
        raise _blocked("runs-bad-shape")
    if data["total_count"] > len(runs):
        raise _blocked("runs-truncated")
    def match(r):
        try:
            return (r["event"] == "push" and r["head_sha"] == sha and r["path"] == cfg["workflow_path"]
                    and r["repository"]["full_name"].lower() == repo.lower()
                    and r["head_repository"]["full_name"].lower() == repo.lower())
        except (KeyError, TypeError, AttributeError):
            return False
    hits = [r for r in runs if isinstance(r, dict) and match(r)]
    if not hits:
        raise _blocked("no-matching-push-run")
    try:
        return max(hits, key=lambda r: (r["run_number"], r["id"]))
    except (KeyError, TypeError):
        raise _blocked("runs-bad-shape") from None


def _check_run_and_job(cfg, sha, run, get):
    rid, attempt = run.get("id"), run.get("run_attempt")
    if not (isinstance(rid, int) and isinstance(attempt, int) and attempt >= 1):
        raise _blocked("run-bad-shape")
    if run.get("status") != "completed":
        raise _blocked("run-in-progress")
    _need(run.get("conclusion") == "success", f"run-{run.get('conclusion')}")
    data = get(f"/repos/{cfg['repo']}/actions/runs/{rid}/attempts/{attempt}/jobs?per_page=100")
    jobs = data.get("jobs")
    if not isinstance(jobs, list) or not isinstance(data.get("total_count"), int):
        raise _blocked("jobs-bad-shape")
    if data["total_count"] > len(jobs):
        raise _blocked("jobs-truncated")
    named = [j for j in jobs if isinstance(j, dict) and j.get("name") == cfg["job_name"]
             and j.get("run_id") == rid and j.get("head_sha") == sha]
    if len(named) != 1:
        if len(named) > 1:
            raise _blocked("job-ambiguous")
        raise _fail("job-missing")
    job = named[0]
    if job.get("status") != "completed":
        raise _blocked("job-in-progress")
    _need(job.get("conclusion") == "success", f"job-{job.get('conclusion')}")
    return job.get("id")


def evaluate(cfg, get=http_get, fetch=git_fetch_pr):
    """Return {verdict, reason, evidence}. `get`/`fetch` are injectable."""
    ev = {"repo": cfg.get("repo"), "pr": cfg.get("pr")}
    try:
        if not (isinstance(cfg.get("repo"), str) and _REPO.fullmatch(cfg["repo"])):
            raise _blocked("bad-config-repo")
        if not (isinstance(cfg.get("pr"), int) and not isinstance(cfg["pr"], bool) and cfg["pr"] > 0):
            raise _blocked("bad-config-pr")
        pin = cfg.get("pinned_github_tree")
        if not (isinstance(pin, str) and _SHA.fullmatch(pin)):
            raise _blocked("bad-config-pin")
        if not (cfg.get("workflow_path") and cfg.get("job_name")):
            raise _blocked("bad-config-workflow")
        sha = ev["head_sha"] = _pr_head(cfg, get)
        fetched, tree = fetch(cfg["repo"], cfg["pr"])
        ev.update(fetched_head=fetched, github_tree=tree, pinned_github_tree=pin)
        if fetched != sha:
            raise _blocked("head-sha-mismatch")
        _need(tree == pin, "github-tree-mismatch")
        run = _latest_run(cfg, sha, get)
        ev.update(run_id=run.get("id"), run_attempt=run.get("run_attempt"))
        ev["job_id"] = _check_run_and_job(cfg, sha, run, get)
        if _pr_head(cfg, get) != sha:
            raise _blocked("head-moved-during-evaluation")
    except Gate as g:
        return {"verdict": g.verdict, "reason": g.reason, "evidence": ev}
    except Exception:  # fail closed on anything unexpected
        return {"verdict": BLOCKED, "reason": "internal-error", "evidence": ev}
    return {"verdict": PASS, "reason": "all-checks-passed", "evidence": ev}


# ---------------------------------------------------------------- slice 2: publishing

CHECK_NAME = "veyro-trusted-gate"
API_HOST = "https://api.github.com"
_SELF = os.path.realpath(__file__)
TLS_CAFILE = "/etc/ssl/cert.pem" if sys.platform == "darwin" else "/etc/ssl/certs/ca-certificates.crt"
CONFIG_PATH = "/Library/VeyroGate/etc/config.json"
EXPECTED_SIGNER_UID = 452  # dedicated _veyrogate uid; provisioning must use this exact unused uid
RUNTIME_ROOT = "/Library/VeyroGate/runtime/Python3.framework/Versions/3.9"  # root-installed interpreter + stdlib
STATE_ANCESTOR_OWNERS = (0,)  # state directory ancestors; only tests relax these two
STATE_TOP = "/"
OPENSSL_BIN = "/usr/bin/openssl"
TOOL_TIMEOUT = 15
MAX_KEY = 16 * 1024
MAX_CONFIG = 64 * 1024
MAX_STATE = 1024 * 1024
MAX_STATE_ENTRIES = 500
_CONCLUSION = {PASS: "success", FAIL: "failure"}
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PR_ARG = re.compile(r"[1-9][0-9]{0,8}")
CONFIG_KEYS = frozenset({"app_id", "installation_id", "repo", "pinned_github_tree", "publisher_sha256",
                         "key_path", "signer_uid", "state_path"})
_SHADOW_CHECKED = ("os", "sys", "json", "hmac", "hashlib", "base64", "subprocess", "tempfile",
                   "fcntl", "ssl", "urllib.request", "urllib.parse", "urllib.error")
_ENV_EXACT = frozenset({"SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
                        "SSLKEYLOGFILE", "NODE_EXTRA_CA_CERTS", "OPENSSL_CONF", "OPENSSL_MODULES"})


def publisher_digest(path=_SELF):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        raise _blocked("publisher-unreadable") from None


def in_git_worktree(path):
    """True if `path` (symlinks resolved) or any ancestor holds a `.git` entry."""
    cur = os.path.realpath(path)
    while True:
        if os.path.lexists(os.path.join(cur, ".git")):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent


def check_env(environ):
    """Refuse proxy, TLS-trust, loader and PYTHON* overrides before any credential access."""
    for k in environ:
        u = k.upper()
        if (u.startswith(("PYTHON", "DYLD_", "LD_", "SSL_", "GIT_")) or u.endswith("_PROXY")
                or u in _ENV_EXACT):
            raise _blocked("env-override-refused")


def _safe_mode(st, owner_ok):
    if st.st_uid not in owner_ok:
        return False
    if st.st_mode & 0o022:
        return st.st_uid == 0 and bool(st.st_mode & stat.S_ISVTX) and stat.S_ISDIR(st.st_mode)
    return True


def _chain_ok(start, owners, stat_fn=os.stat):
    """True if `start` and every ancestor is a directory owned by `owners`, not group/other writable
    (a root-owned sticky directory is tolerated). Raises OSError if a stat fails."""
    cur = start
    while True:
        st = stat_fn(cur)
        if not stat.S_ISDIR(st.st_mode) or not _safe_mode(st, owners):
            return False
        parent = os.path.dirname(cur)
        if parent == cur:
            return True
        cur = parent


def _within(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _strict_chain(start, owners, top):
    """True if `start` and every ancestor up to and including `top` is a real directory (no symlink)
    owned by `owners` and not group/other writable. No sticky-bit exemption. Raises OSError on a
    failed lstat."""
    if not _within(start, top):
        return False
    cur = start
    while True:
        st = os.lstat(cur)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid not in owners or st.st_mode & 0o022:
            return False
        if cur == top:
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent


def _trusted_node(path, root, publisher, owners, top):
    """An existing file or directory that is inside the runtime tree both lexically and after symlink
    resolution (or is exactly the installed publisher), owned by `owners`, not group/other writable,
    under a strict directory chain."""
    if not (isinstance(path, str) and os.path.isabs(path)):
        return False
    lexical, real = os.path.normpath(path), os.path.realpath(path)
    if real == publisher:
        if lexical != publisher:
            return False
    elif not (_within(lexical, root) and _within(real, root)):
        return False
    st = os.lstat(real)
    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
        return False
    if st.st_uid not in owners or st.st_mode & 0o022:
        return False
    return _strict_chain(os.path.dirname(real), owners, top)


def _trusted_location(path, root, publisher, owners, top, allow_missing_zip):
    if not (isinstance(path, str) and os.path.isabs(path)):
        return False
    lexical = os.path.normpath(path)
    if os.path.lexists(lexical):
        return _trusted_node(path, root, publisher, owners, top)
    if allow_missing_zip and lexical.endswith(".zip") and _within(lexical, root):
        parent = os.path.realpath(os.path.dirname(lexical))
        return _within(parent, root) and _strict_chain(parent, owners, top)
    return False


def check_runtime(executable=None, prefix=None, base_prefix=None, paths=None, modules=None,
                  root=RUNTIME_ROOT, publisher=None, owners=(0,), top="/"):
    """Pre-secret guard: the interpreter and standard library must be the root-owned installed runtime.

    The interpreter's realpath must be exactly `<root>/bin/python3`, `sys.prefix` and `sys.base_prefix`
    must equal `root`, every existing `sys.path` entry and every loaded module file must resolve inside
    the runtime tree (or be the installed publisher itself), and all of them, plus their directory
    chains up to `top`, must be owned by `owners` and not group/other writable (no sticky exemption).
    A missing `.zip` entry under the runtime is tolerated only when its parent chain is trusted.
    Imports nothing; the defaults are production values and only tests relax them."""
    executable = sys.executable if executable is None else executable
    prefix = sys.prefix if prefix is None else prefix
    base_prefix = sys.base_prefix if base_prefix is None else base_prefix
    paths = sys.path if paths is None else paths
    modules = sys.modules if modules is None else modules
    publisher = _SELF if publisher is None else publisher
    python = root + "/bin/python3"
    try:
        if not (isinstance(executable, str) and os.path.isabs(executable)
                and os.path.realpath(executable) == python and os.path.realpath(root) == root
                and _trusted_node(python, root, publisher, owners, top)):
            raise _blocked("runtime-bad-interpreter")
        if prefix != root or base_prefix != root:
            raise _blocked("runtime-bad-prefix")
        for entry in list(paths):
            if not _trusted_location(entry, root, publisher, owners, top, True):
                raise _blocked("runtime-untrusted-path")
        for mod in list(modules.values()):
            f = getattr(mod, "__file__", None)
            if f is None:
                continue
            if isinstance(f, str) and not os.path.lexists(f) and ".zip" + os.sep in f:
                f = f[:f.index(".zip" + os.sep) + 4]  # a member of a zip on the stdlib path
            if not _trusted_location(f, root, publisher, owners, top, False):
                raise _blocked("runtime-untrusted-module")
    except (OSError, ValueError):
        raise _blocked("runtime-untrusted") from None


def check_install(path=_SELF, modules=None, file_owner=0, dir_owners=(0,)):
    """The running publisher must be a root-owned, non-group/world-writable file whose whole
    directory chain is root-owned, outside every git worktree, with no shadowing stdlib modules.
    `file_owner`/`dir_owners` default to root; only tests relax them."""
    modules = sys.modules if modules is None else modules
    real = os.path.realpath(path)
    if in_git_worktree(real):
        raise _blocked("publisher-in-worktree")
    try:
        st = os.stat(real)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != file_owner or st.st_mode & 0o022:
            raise _blocked("publisher-bad-installation")
        if not _chain_ok(os.path.dirname(real), dir_owners):
            raise _blocked("publisher-bad-installation")
    except OSError:
        raise _blocked("publisher-bad-installation") from None
    here = os.path.dirname(real)
    for name in _SHADOW_CHECKED:
        f = getattr(modules.get(name), "__file__", None)
        if isinstance(f, str):
            if os.path.dirname(os.path.realpath(f)) == here:
                raise _blocked("module-shadowed")


def check_publish_context(environ=None, path=_SELF, isolated=None, modules=None, cafile=TLS_CAFILE,
                          file_owner=0, dir_owners=(0,), runtime=check_runtime, trusted_git=None):
    """Run first in `publish`: before key, network or state access."""
    if not (sys.flags.isolated if isolated is None else isolated):
        raise _blocked("not-isolated")
    runtime()  # trusted interpreter/stdlib before anything else is believed
    check_env(os.environ if environ is None else environ)
    check_install(path, modules, file_owner, dir_owners)
    (check_trusted_git if trusted_git is None else trusted_git)()  # root-installed git, not /usr/bin/git
    if not os.path.isfile(cafile):
        raise _blocked("tls-trust-unavailable")


def parse_publish_argv(argv):
    """Only `--config <CONFIG_PATH> --pr N` (N plain positive decimal, max 9 digits) is accepted."""
    if not (isinstance(argv, (list, tuple)) and len(argv) == 4 and argv[0] == "--config"
            and argv[1] == CONFIG_PATH and argv[2] == "--pr" and isinstance(argv[3], str)
            and _PR_ARG.fullmatch(argv[3])):
        raise _blocked("bad-argv")
    return int(argv[3])


def harden_process(setrlimit=resource.setrlimit, umask=os.umask, chdir=os.chdir):
    """No core dumps, umask 077 and cwd `/` before any secret is handled."""
    try:
        setrlimit(resource.RLIMIT_CORE, (0, 0))
        umask(0o077)
        chdir("/")
    except (OSError, ValueError):
        raise _blocked("hardening-failed") from None


def check_signer_identity(cfg, expected=None, getuid=os.getuid, geteuid=os.geteuid):
    """Real and effective uid must be one non-root uid equal to config `signer_uid` and to the
    uid provisioned for the dedicated signer account."""
    expected = EXPECTED_SIGNER_UID if expected is None else expected
    if not _posint(expected):
        raise _blocked("signer-uid-unprovisioned")
    ruid, euid = getuid(), geteuid()
    if not (_posint(ruid) and ruid == euid and euid == cfg.get("signer_uid") and euid == expected):
        raise _blocked("signer-uid-mismatch")


def _build_opener(cafile=TLS_CAFILE):
    """No environment proxy, no redirects, and only the fixed TLS trust file."""
    try:
        ctx = ssl.create_default_context(cafile=cafile)
    except (ssl.SSLError, OSError):
        raise _blocked("tls-trust-unavailable") from None
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect,
                                       urllib.request.HTTPSHandler(context=ctx))


def _posint(v):
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _label(v):
    return (isinstance(v, str) and 0 < len(v) <= 200 and v.isprintable()
            and v == v.strip())


def load_config(path, required=CONFIG_PATH, owner_uid=0, dir_owners=(0,)):
    """Load and validate the publisher config: the one fixed path, root-owned, mode 0444 or tighter,
    under a root-owned directory chain, outside any git worktree. Unknown keys are refused.
    `required`/`owner_uid`/`dir_owners` default to production values; only tests relax them."""
    if not (isinstance(path, str) and os.path.isabs(path)):
        raise _blocked("config-path-not-absolute")
    if path != required:
        raise _blocked("config-path-mismatch")
    if in_git_worktree(path):
        raise _blocked("config-inside-repo")
    d = os.path.dirname(path)
    fd = None
    try:
        if os.path.realpath(d) != d or not _chain_ok(d, dir_owners):
            raise _blocked("config-bad-permissions")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_CONFIG:
            raise _blocked("config-bad-file")
        if st.st_uid != owner_uid or stat.S_IMODE(st.st_mode) & ~0o444:
            raise _blocked("config-bad-permissions")
        with os.fdopen(fd, "rb") as f:
            fd = None
            cfg = json.loads(f.read(MAX_CONFIG + 1))
    except (OSError, ValueError):
        raise _blocked("config-unreadable") from None
    finally:
        if fd is not None:
            os.close(fd)
    if not isinstance(cfg, dict) or set(cfg) != CONFIG_KEYS:
        raise _blocked("config-bad-keys")
    if not (_posint(cfg["app_id"]) and _posint(cfg["installation_id"])):
        raise _blocked("config-bad-ids")
    if not (isinstance(cfg["repo"], str) and _REPO.fullmatch(cfg["repo"])):
        raise _blocked("bad-config-repo")
    pin = cfg["pinned_github_tree"]
    if not (isinstance(pin, str) and _SHA.fullmatch(pin)):
        raise _blocked("bad-config-pin")
    dig = cfg["publisher_sha256"]
    if not (isinstance(dig, str) and _SHA256.fullmatch(dig)):
        raise _blocked("config-bad-digest")
    kp = cfg["key_path"]
    if not (_label(kp) and os.path.isabs(kp) and os.path.normpath(kp) == kp) or in_git_worktree(kp):
        raise _blocked("config-bad-key-path")
    if not _posint(cfg["signer_uid"]):  # root (0) is never a signer
        raise _blocked("config-bad-signer-uid")
    sp = cfg["state_path"]
    if not (_label(sp) and os.path.isabs(sp) and os.path.normpath(sp) == sp) or in_git_worktree(sp):
        raise _blocked("config-bad-state-path")
    return dict(cfg)


def verify_digest(cfg, publisher_path=_SELF):
    if not hmac.compare_digest(publisher_digest(publisher_path), str(cfg.get("publisher_sha256"))):
        raise _blocked("publisher-digest-mismatch")


def external_id(pr, head_sha, tree, digest, run_id, attempt, job_id, conclusion):
    """Same-run crash retries reuse this id (adopt); any rerun/attempt/conclusion change gets a new check."""
    return (f"veyro-gate:v2:pr={pr}:head={head_sha}:tree={tree}:pub={digest}"
            f":run={run_id}:attempt={attempt}:job={job_id}:conclusion={conclusion}")


def read_key_file(key_path, euid=None, ancestor_owners=(0,), stat_fn=os.stat, open_fn=os.open,
                  fstat_fn=os.fstat, read_fn=os.read, close_fn=os.close):
    """Return the PEM private key from the signer-owned 0400 file (never argv/env/log/state).

    The key directory must be owned by the effective uid with mode 0700 and every ancestor
    root-owned and not group/other writable. The file is opened without following a symlink and
    must be a regular, single-link, exactly-0400 file owned by the effective uid. Errors carry no
    path or content. `euid`/`ancestor_owners` and the fs callables are injectable for tests."""
    euid = os.geteuid() if euid is None else euid
    if not (isinstance(key_path, str) and os.path.isabs(key_path) and os.path.normpath(key_path) == key_path):
        raise _blocked("key-bad-path")
    kdir = os.path.dirname(key_path)
    fd = None
    try:
        if os.path.realpath(kdir) != kdir or kdir == os.path.dirname(kdir):
            raise _blocked("key-bad-path")
        dst = stat_fn(kdir)
        if not (stat.S_ISDIR(dst.st_mode) and dst.st_uid == euid and stat.S_IMODE(dst.st_mode) == 0o700):
            raise _blocked("key-bad-directory")
        if not _chain_ok(os.path.dirname(kdir), ancestor_owners, stat_fn):
            raise _blocked("key-bad-directory")
        fd = open_fn(key_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        st = fstat_fn(fd)
        if not (stat.S_ISREG(st.st_mode) and st.st_uid == euid and stat.S_IMODE(st.st_mode) == 0o400
                and st.st_nlink == 1 and 0 < st.st_size <= MAX_KEY):
            raise _blocked("key-bad-file")
        chunks, total = [], 0
        while total <= MAX_KEY:
            b = read_fn(fd, MAX_KEY + 1 - total)
            if not b:
                break
            chunks.append(b)
            total += len(b)
        raw = b"".join(chunks).strip()
    except OSError:
        raise _blocked("key-unreadable") from None
    finally:
        if fd is not None:
            close_fn(fd)
    if total > MAX_KEY or not (raw.startswith(b"-----BEGIN") and b"PRIVATE KEY-----" in raw and raw.isascii()):
        raise _blocked("key-bad-key")
    return raw.decode("ascii")


def openssl_sign(key_pem, message, run=subprocess.run, write=os.write):
    """RS256 signature via openssl. The key goes through a pipe fd, never argv or disk."""
    data = key_pem.encode("ascii")
    if len(data) > MAX_KEY:
        raise _blocked("sign-failed")
    r, w = os.pipe()
    try:
        view = memoryview(data)
        while view:  # os.write may be partial; a short or zero write must never sign a truncated key
            n = write(w, view)
            if not (isinstance(n, int) and 0 < n <= len(view)):
                raise _blocked("sign-failed")
            view = view[n:]
        os.close(w)
        w = None
        p = run([OPENSSL_BIN, "dgst", "-sha256", "-sign", f"/dev/fd/{r}"], input=message,
                capture_output=True, timeout=TOOL_TIMEOUT, check=False, pass_fds=(r,),
                env={"PATH": "/usr/bin:/bin"})
    except (subprocess.TimeoutExpired, OSError, ValueError):
        raise _blocked("sign-failed") from None
    finally:
        os.close(r)
        if w is not None:
            os.close(w)
    if p.returncode != 0 or not (256 <= len(p.stdout) <= 1024):
        raise _blocked("sign-failed")
    return p.stdout


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def make_jwt(app_id, key_pem, sign, now):
    t = int(now())
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps({"iat": t - 60, "exp": t + 480, "iss": str(app_id)},
                           separators=(",", ":")).encode())
    sig = sign(key_pem, f"{head}.{body}".encode("ascii"))
    if not (isinstance(sig, bytes) and 256 <= len(sig) <= 1024):
        raise _blocked("sign-failed")
    return f"{head}.{body}.{_b64(sig)}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_api(method, path, bearer, body=None, opener=None):
    """Bounded authenticated call to the fixed GitHub API host; returns parsed JSON.

    The bearer credential is only placed in the request header and never appears
    in errors. Redirects are refused so it cannot leave the host."""
    if not (isinstance(path, str) and path.startswith("/") and not path.startswith("//")
            and re.fullmatch(r"[A-Za-z0-9_./?&=:%-]+", path)):
        raise _blocked("bad-api-path")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(API_HOST + path, data=data, method=method, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "veyro-trusted-gate",
        "Authorization": f"Bearer {bearer}", "X-GitHub-Api-Version": "2022-11-28",
        **({"Content-Type": "application/json"} if data is not None else {})})
    open_ = opener or _build_opener().open
    try:
        with open_(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read(MAX_BODY + 1)
    except urllib.error.HTTPError as e:
        try:
            e.close()
        except Exception:
            pass
        raise _blocked(f"http-{e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise _blocked("http-unreachable") from None
    if len(raw) > MAX_BODY:
        raise _blocked("http-too-large")
    try:
        out = json.loads(raw)
    except ValueError:
        raise _blocked("http-bad-json") from None
    if not isinstance(out, dict):
        raise _blocked("http-bad-shape")
    return out


class _State:
    """Out-of-repo intent/result journal under an exclusive non-blocking file lock.

    The state directory must be a real (non-symlink) 0700 directory owned by the signer, under
    root-owned strict ancestors; its parent is never created. State is a crash-recovery journal, not
    authority: it never grants a verdict, and idempotence is decided from GitHub's own check runs."""

    def __init__(self, path, uid=None, ancestor_owners=None, top=None):
        self.path, self.fd, self.data = path, None, None
        self.uid = os.geteuid() if uid is None else uid
        self.owners = STATE_ANCESTOR_OWNERS if ancestor_owners is None else ancestor_owners
        self.top = STATE_TOP if top is None else top

    def _own_file_ok(self, st):
        return stat.S_ISREG(st.st_mode) and st.st_uid == self.uid and st.st_nlink == 1 \
            and not st.st_mode & 0o077

    def _check_dir(self, d):
        if not (os.path.normpath(self.path) == self.path and os.path.isabs(self.path)):
            raise _blocked("state-unsafe")
        if not _strict_chain(os.path.dirname(d), self.owners, self.top):
            raise _blocked("state-unsafe")
        if not os.path.lexists(d):
            os.mkdir(d, 0o700)
        st = os.lstat(d)
        if not (stat.S_ISDIR(st.st_mode) and st.st_uid == self.uid and stat.S_IMODE(st.st_mode) == 0o700):
            raise _blocked("state-unsafe")

    def __enter__(self):
        d = os.path.dirname(self.path)
        try:
            self._check_dir(d)
            self.fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            if not self._own_file_ok(os.fstat(self.fd)):
                raise _blocked("state-unsafe")
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._close()
            raise _blocked("state-locked") from None
        except OSError:
            self._close()
            raise _blocked("state-unavailable") from None
        except BaseException:
            self._close()
            raise
        try:
            self.data = self._load()
        except BaseException:
            self._close()
            raise
        return self

    def __exit__(self, *exc):
        self._close()
        return False

    def _close(self):
        if self.fd is not None:
            os.close(self.fd)  # releases the flock
            self.fd = None

    def _load(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            return {"version": 1, "checks": {}}
        except OSError:
            raise _blocked("state-unavailable") from None
        try:
            if not self._own_file_ok(os.fstat(fd)):
                raise _blocked("state-unsafe")
            with os.fdopen(fd, "rb") as f:
                fd = None
                raw = f.read(MAX_STATE + 1)
        except OSError:
            raise _blocked("state-unavailable") from None
        finally:
            if fd is not None:
                os.close(fd)
        try:
            data = json.loads(raw) if len(raw) <= MAX_STATE else None
        except ValueError:
            data = None
        if not (isinstance(data, dict) and data.get("version") == 1 and isinstance(data.get("checks"), dict)):
            raise _blocked("state-corrupt")
        return data

    def record(self, key, entry):
        checks = self.data["checks"]
        checks.pop(key, None)
        checks[key] = entry
        while len(checks) > MAX_STATE_ENTRIES:
            checks.pop(next(iter(checks)))
        d = os.path.dirname(self.path)
        try:
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".state-")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self.data, f, sort_keys=True)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            dfd = os.open(d, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            raise _blocked("state-write-failed") from None


def _mint_token(cfg, jwt, transport):
    name = cfg["repo"].split("/", 1)[1]
    res = transport("POST", f"/app/installations/{cfg['installation_id']}/access_tokens", jwt,
                    {"repositories": [name], "permissions": {"checks": "write"}})
    token, perms, repos = res.get("token"), res.get("permissions"), res.get("repositories")
    if not (isinstance(token, str) and token):
        raise _blocked("token-bad-shape")
    if perms != {"checks": "write"} and perms != {"checks": "write", "metadata": "read"}:
        raise _blocked("token-overscoped")
    if not (isinstance(repos, list) and len(repos) == 1 and isinstance(repos[0], dict)
            and str(repos[0].get("full_name", "")).lower() == cfg["repo"].lower()):
        raise _blocked("token-overscoped")
    return token


def _own_runs(cfg, sha, token, transport):
    data = transport("GET", f"/repos/{cfg['repo']}/commits/{sha}/check-runs?check_name={CHECK_NAME}"
                     "&filter=all&per_page=100", token)
    runs = data.get("check_runs")
    if not isinstance(runs, list) or not isinstance(data.get("total_count"), int):
        raise _blocked("checks-bad-shape")
    if data["total_count"] > len(runs):
        raise _blocked("checks-truncated")
    own = []
    for r in runs:
        if not isinstance(r, dict):
            raise _blocked("checks-bad-shape")
        if r.get("name") != CHECK_NAME:
            continue
        app = r.get("app")
        app_id = app.get("id") if isinstance(app, dict) else None
        if not _posint(app_id):
            raise _blocked("checks-bad-shape")
        if app_id == cfg["app_id"]:  # same-name runs from other Apps are never adopted
            own.append(r)
    return own


def _valid_created(cfg, res, sha, ext, conclusion):
    app = res.get("app")
    return (_posint(res.get("id")) and res.get("name") == CHECK_NAME and res.get("head_sha") == sha
            and res.get("external_id") == ext and res.get("status") == "completed"
            and res.get("conclusion") == conclusion
            and isinstance(app, dict) and app.get("id") == cfg["app_id"])


def publish(cfg, pr, get=http_get, fetch=trusted_git_fetch_pr, read_secret=read_key_file, sign=openssl_sign,
            transport=http_api, now=time.time, publisher_path=_SELF, guard=check_publish_context,
            identity=check_signer_identity):
    """Evaluate then publish. Only PASS->success and FAIL->failure are ever posted."""
    out = {"verdict": BLOCKED, "reason": "internal-error", "published": False, "adopted": False,
           "evidence": {}}
    try:
        guard()  # installed/isolated/env checks before key, network or state
        identity(cfg)  # signer uid checks, also before key, network or state
        verify_digest(cfg, publisher_path)  # before any signing, key read or publish
        if not _posint(pr):
            raise _blocked("bad-config-pr")
        res = evaluate({"repo": cfg["repo"], "pr": pr, "pinned_github_tree": cfg["pinned_github_tree"],
                        "workflow_path": DEFAULT_WORKFLOW, "job_name": DEFAULT_JOB}, get, fetch)
        out.update(verdict=res["verdict"], reason=res["reason"], evidence=res["evidence"])
        if res["verdict"] not in _CONCLUSION:
            return out
        sha = res["evidence"].get("head_sha")
        if not (isinstance(sha, str) and _SHA.fullmatch(sha)):
            out.update(verdict=BLOCKED, reason="no-head-sha")
            return out
        conclusion = _CONCLUSION[res["verdict"]]
        ev = res["evidence"]
        run_id, attempt, job_id = ev.get("run_id"), ev.get("run_attempt"), ev.get("job_id")
        if not (_posint(run_id) and _posint(attempt)) or not (job_id is None or _posint(job_id)):
            # e.g. a `.github` tree mismatch is a FAIL verdict reached before any run is looked up:
            # with no run evidence it is BLOCKED and no check is published (never a false PASS).
            raise _blocked("no-run-evidence")
        ext = external_id(pr, sha, cfg["pinned_github_tree"], cfg["publisher_sha256"], run_id, attempt,
                          "none" if job_id is None else job_id, conclusion)
        with _State(cfg["state_path"]) as st:
            entry = {"status": "intent", "repo": cfg["repo"], "pr": pr, "head_sha": sha,
                     "conclusion": conclusion, "app_id": cfg["app_id"], "external_id": ext,
                     "started_at": int(now())}
            st.record(ext, entry)
            key = read_secret(cfg["key_path"])
            jwt = make_jwt(cfg["app_id"], key, sign, now)
            del key
            token = _mint_token(cfg, jwt, transport)
            del jwt
            same = [r for r in _own_runs(cfg, sha, token, transport) if r.get("external_id") == ext]
            if len(same) > 1:
                raise _blocked("ambiguous-duplicate-checks")
            if same:
                created, adopted = same[0], True
                if not _valid_created(cfg, created, sha, ext, conclusion):
                    raise _blocked("existing-check-conflict")
            else:
                try:
                    moved = _pr_head({"repo": cfg["repo"], "pr": pr}, get) != sha
                except Gate:
                    moved = True
                if moved:
                    raise _blocked("head-moved-before-publish")
                title = f"Veyro trusted gate: {res['verdict']}"
                summary = (f"{title} ({res['reason']}). Evidence: pr={pr} head={sha} "
                           f"pinned_tree={cfg['pinned_github_tree']} run_id={run_id} attempt={attempt} "
                           f"job_id={job_id} publisher_sha256={cfg['publisher_sha256']}. "
                           "Scope: attests the pinned .github tree and the foundation workflow run/job "
                           "conclusion only; candidate-controlled test code is not attested.")
                created = transport("POST", f"/repos/{cfg['repo']}/check-runs", token, {
                    "name": CHECK_NAME, "head_sha": sha, "status": "completed",
                    "conclusion": conclusion, "external_id": ext,
                    "output": {"title": title, "summary": summary}})
                adopted = False
                if not _valid_created(cfg, created, sha, ext, conclusion):
                    raise _blocked("check-response-mismatch")
            del token
            st.record(ext, {**entry, "status": "published", "check_run_id": created["id"],
                            "adopted": adopted, "finished_at": int(now())})
        out.update(published=True, adopted=adopted, check_run_id=created["id"])
    except Gate as g:
        out.update(verdict=BLOCKED, reason=g.reason, published=False)
    except Exception:  # fail closed; never surface exception text (could hold secrets)
        out.update(verdict=BLOCKED, reason="internal-error", published=False)
    return out


def _emit(result):
    print(json.dumps(result, indent=2, sort_keys=True))
    return EXIT[result["verdict"]]


def _publish_main(argv):
    try:
        pr = parse_publish_argv(argv)  # exact form only, before anything else
        harden_process()
        check_publish_context()  # before reading config, key, network or state
        cfg = load_config(CONFIG_PATH)
    except Gate as g:
        return _emit({"verdict": BLOCKED, "reason": g.reason, "published": False, "evidence": {}})
    return _emit(publish(cfg, pr))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["publish"]:
        return _publish_main(argv[1:])
    if argv[:1] == ["digest"]:
        print(publisher_digest())
        return 0
    ap = argparse.ArgumentParser(description="MOD-001 trusted gate (keyless --dry-run; see `publish`)")
    ap.add_argument("--dry-run", action="store_true", help="required; never creates a check")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--pinned-github-tree", required=True, help="40-hex .github tree OID")
    ap.add_argument("--workflow-path", default=DEFAULT_WORKFLOW)
    ap.add_argument("--job-name", default=DEFAULT_JOB)
    a = ap.parse_args(argv)
    if not a.dry_run:
        ap.error("--dry-run is required here; use the `publish` command to publish")
    result = evaluate({"repo": a.repo, "pr": a.pr, "pinned_github_tree": a.pinned_github_tree,
                       "workflow_path": a.workflow_path, "job_name": a.job_name})
    print(json.dumps(result, indent=2, sort_keys=True))
    return EXIT[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
