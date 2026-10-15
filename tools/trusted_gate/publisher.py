"""MOD-001 trusted gate, slice 1: keyless dry-run evaluator.

Evaluates an open same-repo PR into main against a pinned `.github` tree OID
and the foundation workflow's push run. It never checks out or executes
candidate code, never publishes a check and uses no credentials. Only an
exact `success` can yield PASS; every error is BLOCKED, every mismatch FAIL.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="MOD-001 trusted gate (slice 1: dry-run only)")
    ap.add_argument("--dry-run", action="store_true", help="required; never creates a check")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--pinned-github-tree", required=True, help="40-hex .github tree OID")
    ap.add_argument("--workflow-path", default=DEFAULT_WORKFLOW)
    ap.add_argument("--job-name", default=DEFAULT_JOB)
    a = ap.parse_args(argv)
    if not a.dry_run:
        ap.error("publishing is not implemented; --dry-run is required")
    result = evaluate({"repo": a.repo, "pr": a.pr, "pinned_github_tree": a.pinned_github_tree,
                       "workflow_path": a.workflow_path, "job_name": a.job_name})
    print(json.dumps(result, indent=2, sort_keys=True))
    return EXIT[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
