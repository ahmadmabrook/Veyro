"""MOD-001 trusted gate: keyless evaluator (slice 1) and App check publisher (slice 2).

Evaluates an open same-repo PR into main against a pinned `.github` tree OID
and the foundation workflow's push run. It never checks out or executes
candidate code. Only an exact `success` can yield PASS; every error is BLOCKED,
every mismatch FAIL. `--dry-run` is keyless and never publishes.

The `publish` command (slice 2) evaluates first, and only for PASS/FAIL reads
the GitHub App key from the macOS Keychain, signs an App JWT with openssl (key
passed by file descriptor), mints an in-memory installation token limited to
the Veyro repo and `checks:write`, and posts one completed check run named
`veyro-trusted-gate` with conclusion `success` or `failure` only. BLOCKED
never publishes. Config lives outside the repo and pins this file's SHA-256.
"""
import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
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


def http_get(path, opener=urllib.request.urlopen):
    """Bounded unauthenticated GET against api.github.com; returns parsed JSON."""
    req = urllib.request.Request("https://api.github.com" + path, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "veyro-trusted-gate"})
    try:
        with opener(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read(MAX_BODY + 1)
    except urllib.error.HTTPError as e:
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


def git_fetch_pr(repo, pr, run=subprocess.run):
    """Fetch refs/pull/N/head as inert objects into a throwaway bare repo.

    Returns (fetched_head_sha, head:.github tree oid)."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent",
           "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    ref = f"refs/pull/{pr}/head"

    def git(*args):
        try:
            p = run(["git", *args], cwd=tmp, env=env, capture_output=True, text=True,
                    timeout=GIT_TIMEOUT, check=False)
        except (subprocess.TimeoutExpired, OSError):
            raise _blocked("git-error") from None
        if p.returncode != 0:
            raise _blocked("git-error")
        return p.stdout.strip()

    with tempfile.TemporaryDirectory(prefix="veyro-gate-") as tmp:
        git("init", "--bare", "-q", ".")
        git("-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
            "-c", "fetch.fsckObjects=true", "fetch", "--no-tags", "--depth=1", "-q",
            f"https://github.com/{repo}.git", f"+{ref}:{ref}")
        sha = git("rev-parse", "--verify", ref)
        tree = git("rev-parse", "--verify", f"{sha}:.github")
    return sha, tree


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
        raise _fail("job-missing" if not named else "job-ambiguous")
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
        _need(fetched == sha, "head-sha-mismatch")
        _need(tree == pin, "github-tree-mismatch")
        run = _latest_run(cfg, sha, get)
        ev.update(run_id=run.get("id"), run_attempt=run.get("run_attempt"))
        ev["job_id"] = _check_run_and_job(cfg, sha, run, get)
        if _pr_head(cfg, get) != sha:
            raise _fail("head-moved-during-evaluation")
    except Gate as g:
        return {"verdict": g.verdict, "reason": g.reason, "evidence": ev}
    except Exception:  # fail closed on anything unexpected
        return {"verdict": BLOCKED, "reason": "internal-error", "evidence": ev}
    return {"verdict": PASS, "reason": "all-checks-passed", "evidence": ev}


# ---------------------------------------------------------------- slice 2: publishing

CHECK_NAME = "veyro-trusted-gate"
API_HOST = "https://api.github.com"
_SELF = os.path.realpath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SELF)))
SECURITY_BIN = "/usr/bin/security"
OPENSSL_BIN = "/usr/bin/openssl"
TOOL_TIMEOUT = 15
MAX_KEY = 16 * 1024
MAX_CONFIG = 64 * 1024
MAX_STATE = 1024 * 1024
MAX_STATE_ENTRIES = 500
_CONCLUSION = {PASS: "success", FAIL: "failure"}
_SHA256 = re.compile(r"[0-9a-f]{64}")
CONFIG_KEYS = frozenset({"app_id", "installation_id", "repo", "pinned_github_tree", "publisher_sha256",
                         "keychain_service", "keychain_account", "state_path"})


def publisher_digest(path=_SELF):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        raise _blocked("publisher-unreadable") from None


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root


def _posint(v):
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _label(v):
    return (isinstance(v, str) and 0 < len(v) <= 200 and v.isprintable()
            and v == v.strip())


def load_config(path, repo_root=REPO_ROOT):
    """Load and validate the out-of-repo publisher config. Unknown keys are refused."""
    if not (isinstance(path, str) and os.path.isabs(path)):
        raise _blocked("config-path-not-absolute")
    if _inside(path, repo_root):
        raise _blocked("config-inside-repo")
    try:
        st = os.stat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_CONFIG:
            raise _blocked("config-bad-file")
        if st.st_mode & 0o022 or st.st_uid != os.geteuid():
            raise _blocked("config-bad-permissions")
        with open(path, "rb") as f:
            cfg = json.loads(f.read(MAX_CONFIG + 1))
    except (OSError, ValueError):
        raise _blocked("config-unreadable") from None
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
    if not (_label(cfg["keychain_service"]) and _label(cfg["keychain_account"])):
        raise _blocked("config-bad-keychain")
    sp = cfg["state_path"]
    if not (isinstance(sp, str) and os.path.isabs(sp)) or _inside(sp, repo_root):
        raise _blocked("config-bad-state-path")
    return dict(cfg)


def verify_digest(cfg, publisher_path=_SELF):
    if not hmac.compare_digest(publisher_digest(publisher_path), str(cfg.get("publisher_sha256"))):
        raise _blocked("publisher-digest-mismatch")


def external_id(pr, head_sha, tree, digest):
    return f"veyro-gate:v1:pr={pr}:head={head_sha}:tree={tree}:pub={digest}"


def keychain_read(service, account, run=subprocess.run):
    """Return the PEM private key from the macOS Keychain (stdout pipe; never argv/env/disk)."""
    try:
        p = run([SECURITY_BIN, "find-generic-password", "-s", service, "-a", account, "-w"],
                capture_output=True, timeout=TOOL_TIMEOUT, check=False,
                env={"PATH": "/usr/bin:/bin"})
    except (subprocess.TimeoutExpired, OSError):
        raise _blocked("keychain-error") from None
    if p.returncode != 0 or not p.stdout or len(p.stdout) > MAX_KEY * 2:
        raise _blocked("keychain-error")
    raw = p.stdout.strip()
    if not raw.startswith(b"-----BEGIN"):
        try:  # `security` hex-encodes multi-line secrets
            raw = bytes.fromhex(raw.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            raise _blocked("keychain-bad-key") from None
        raw = raw.strip()
    if not (raw.startswith(b"-----BEGIN") and b"PRIVATE KEY-----" in raw and raw.isascii()) \
            or len(raw) > MAX_KEY:
        raise _blocked("keychain-bad-key")
    return raw.decode("ascii")


def openssl_sign(key_pem, message, run=subprocess.run):
    """RS256 signature via openssl. The key goes through a pipe fd, never argv or disk."""
    data = key_pem.encode("ascii")
    if len(data) > MAX_KEY:
        raise _blocked("sign-failed")
    r, w = os.pipe()
    try:
        os.write(w, data)  # well under the pipe buffer
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
    open_ = opener or urllib.request.build_opener(_NoRedirect).open
    try:
        with open_(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read(MAX_BODY + 1)
    except urllib.error.HTTPError as e:
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
    """Out-of-repo intent/result journal under an exclusive non-blocking file lock."""

    def __init__(self, path):
        self.path, self.fd, self.data = path, None, None

    def __enter__(self):
        d = os.path.dirname(self.path)
        try:
            os.makedirs(d, mode=0o700, exist_ok=True)
            self.fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._close()
            raise _blocked("state-locked") from None
        except OSError:
            self._close()
            raise _blocked("state-unavailable") from None
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
            with open(self.path, "rb") as f:
                raw = f.read(MAX_STATE + 1)
        except FileNotFoundError:
            return {"version": 1, "checks": {}}
        except OSError:
            raise _blocked("state-unavailable") from None
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


def publish(cfg, pr, get=http_get, fetch=git_fetch_pr, read_secret=keychain_read, sign=openssl_sign,
            transport=http_api, now=time.time, publisher_path=_SELF):
    """Evaluate then publish. Only PASS->success and FAIL->failure are ever posted."""
    out = {"verdict": BLOCKED, "reason": "internal-error", "published": False, "adopted": False,
           "evidence": {}}
    try:
        verify_digest(cfg, publisher_path)  # before any signing, Keychain read or publish
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
        ext = external_id(pr, sha, cfg["pinned_github_tree"], cfg["publisher_sha256"])
        with _State(cfg["state_path"]) as st:
            entry = {"status": "intent", "repo": cfg["repo"], "pr": pr, "head_sha": sha,
                     "conclusion": conclusion, "app_id": cfg["app_id"], "external_id": ext,
                     "started_at": int(now())}
            st.record(ext, entry)
            key = read_secret(cfg["keychain_service"], cfg["keychain_account"])
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
                title = f"Veyro trusted gate: {res['verdict']}"
                created = transport("POST", f"/repos/{cfg['repo']}/check-runs", token, {
                    "name": CHECK_NAME, "head_sha": sha, "status": "completed",
                    "conclusion": conclusion, "external_id": ext,
                    "output": {"title": title, "summary": f"{title} ({res['reason']})"}})
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
    ap = argparse.ArgumentParser(prog="publisher.py publish",
                                 description="Publish the veyro-trusted-gate check run (config is out-of-repo)")
    ap.add_argument("--config", required=True, help="absolute path to the out-of-repo JSON config")
    ap.add_argument("--pr", required=True, type=int)
    a = ap.parse_args(argv)
    try:
        cfg = load_config(a.config)
    except Gate as g:
        return _emit({"verdict": BLOCKED, "reason": g.reason, "published": False, "evidence": {}})
    return _emit(publish(cfg, a.pr))


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
