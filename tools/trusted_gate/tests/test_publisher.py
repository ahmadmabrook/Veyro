import copy
import io
import os
import subprocess
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import publisher as p  # noqa: E402

REPO = "ahmadmabrook/Veyro"
SHA = "a" * 40
TREE = "b" * 40
WF = p.DEFAULT_WORKFLOW
JOB = p.DEFAULT_JOB
CFG = {"repo": REPO, "pr": 10, "pinned_github_tree": TREE, "workflow_path": WF, "job_name": JOB}


def pr_doc(**over):
    d = {"state": "open", "base": {"ref": "main", "repo": {"full_name": REPO}},
         "head": {"sha": SHA, "repo": {"full_name": REPO}}}
    d.update(over)
    return d


def run_doc(**over):
    d = {"id": 100, "run_number": 5, "run_attempt": 1, "event": "push", "head_sha": SHA, "path": WF,
         "status": "completed", "conclusion": "success",
         "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO}}
    d.update(over)
    return d


def job_doc(**over):
    d = {"id": 900, "run_id": 100, "head_sha": SHA, "name": JOB, "status": "completed", "conclusion": "success"}
    d.update(over)
    return d


class World:
    """Fake GitHub + git. Mutate fields to build each scenario."""

    def __init__(self):
        self.pr = pr_doc()
        self.runs = [run_doc()]
        self.jobs = {(100, 1): [job_doc()]}
        self.fetched = (SHA, TREE)
        self.fail_http = None
        self.fail_git = False
        self.check_runs_called = False

    def get(self, path):
        if self.fail_http:
            raise p.Gate(p.BLOCKED, self.fail_http)
        if "/check-runs" in path or "/check-suites" in path:
            self.check_runs_called = True
            return {"total_count": 1, "check_runs": [{"name": JOB, "conclusion": "success"}]}
        if "/pulls/" in path:
            return copy.deepcopy(self.pr)
        if "/attempts/" in path:
            rid, att = path.split("/runs/")[1].split("/attempts/")
            return {"total_count": len(self.jobs.get((int(rid), int(att.split("/")[0])), [])),
                    "jobs": self.jobs.get((int(rid), int(att.split("/")[0])), [])}
        if "/actions/runs?" in path:
            return {"total_count": len(self.runs), "workflow_runs": self.runs}
        raise AssertionError(path)

    def fetch(self, repo, pr):
        if self.fail_git:
            raise p.Gate(p.BLOCKED, "git-error")
        return self.fetched

    def eval(self, **cfg):
        return p.evaluate({**CFG, **cfg}, self.get, self.fetch)


class EvaluatorTests(unittest.TestCase):
    def verdict(self, w, reason=None, **cfg):
        r = w.eval(**cfg)
        if reason is None:
            self.assertEqual(r["verdict"], p.PASS, r)
        else:
            self.assertEqual((r["verdict"], r["reason"]), reason, r)
        return r

    def test_honest_pass_with_evidence(self):
        r = self.verdict(World())
        self.assertEqual(r["evidence"]["run_id"], 100)
        self.assertEqual(r["evidence"]["job_id"], 900)
        self.assertEqual(r["evidence"]["head_sha"], SHA)
        self.assertEqual(r["evidence"]["github_tree"], TREE)

    def test_changed_workflow_or_added_sibling_changes_tree(self):
        for tree in ("c" * 40, "d" * 40):  # edited workflow / added spoof sibling both alter the tree OID
            w = World()
            w.fetched = (SHA, tree)
            self.verdict(w, (p.FAIL, "github-tree-mismatch"))

    def test_fetched_sha_mismatch(self):
        w = World()
        w.fetched = ("e" * 40, TREE)
        self.verdict(w, (p.FAIL, "head-sha-mismatch"))

    def test_fork_and_base_mismatch(self):
        w = World()
        w.pr = pr_doc(head={"sha": SHA, "repo": {"full_name": "evil/Veyro"}})
        self.verdict(w, (p.FAIL, "fork-or-deleted-head-repo"))
        w.pr = pr_doc(head={"sha": SHA, "repo": None})
        self.verdict(w, (p.FAIL, "fork-or-deleted-head-repo"))
        w.pr = pr_doc(base={"ref": "dev", "repo": {"full_name": REPO}})
        self.verdict(w, (p.FAIL, "base-not-main"))
        w.pr = pr_doc(base={"ref": "main", "repo": {"full_name": "other/Veyro"}})
        self.verdict(w, (p.FAIL, "base-repo-mismatch"))
        w.pr = pr_doc(state="closed")
        self.verdict(w, (p.FAIL, "pr-not-open"))

    def test_missing_run_blocked(self):
        w = World()
        w.runs = []
        self.verdict(w, (p.BLOCKED, "no-matching-push-run"))

    def test_failed_cancelled_skipped_neutral_run_never_pass(self):
        for c in ("failure", "cancelled", "skipped", "neutral", None):
            w = World()
            w.runs = [run_doc(conclusion=c)]
            self.verdict(w, (p.FAIL, f"run-{c}"))

    def test_in_progress_run_blocked(self):
        w = World()
        w.runs = [run_doc(status="in_progress", conclusion=None)]
        self.verdict(w, (p.BLOCKED, "run-in-progress"))

    def test_wrong_path_event_sha_or_repo_run_ignored(self):
        for over in ({"path": ".github/workflows/spoof.yml"}, {"event": "pull_request"},
                     {"head_sha": "f" * 40}, {"repository": {"full_name": "evil/Veyro"}},
                     {"head_repository": {"full_name": "evil/Veyro"}}):
            w = World()
            w.runs = [run_doc(**over)]
            self.verdict(w, (p.BLOCKED, "no-matching-push-run"))

    def test_newer_failed_run_supersedes_older_success(self):
        w = World()
        w.runs = [run_doc(), run_doc(id=101, run_number=6, conclusion="failure")]
        self.verdict(w, (p.FAIL, "run-failure"))

    def test_rerun_attempt_failure_uses_latest_attempt(self):
        w = World()
        w.runs = [run_doc(run_attempt=2, conclusion="failure")]
        w.jobs[(100, 1)] = [job_doc()]
        self.verdict(w, (p.FAIL, "run-failure"))
        # run says success but the latest attempt's job failed: job decides
        w.runs = [run_doc(run_attempt=2)]
        w.jobs[(100, 2)] = [job_doc(conclusion="failure")]
        self.verdict(w, (p.FAIL, "job-failure"))

    def test_job_failure_skipped_neutral_missing_and_duplicate(self):
        for c in ("failure", "skipped", "neutral", "cancelled"):
            w = World()
            w.jobs[(100, 1)] = [job_doc(conclusion=c)]
            self.verdict(w, (p.FAIL, f"job-{c}"))
        w = World()
        w.jobs[(100, 1)] = [job_doc(name="other")]
        self.verdict(w, (p.FAIL, "job-missing"))
        w.jobs[(100, 1)] = [job_doc(), job_doc(id=901)]
        self.verdict(w, (p.FAIL, "job-ambiguous"))
        w.jobs[(100, 1)] = [job_doc(status="in_progress", conclusion=None)]
        self.verdict(w, (p.BLOCKED, "job-in-progress"))

    def test_job_from_other_sha_or_run_not_accepted(self):
        w = World()
        w.jobs[(100, 1)] = [job_doc(head_sha="f" * 40)]
        self.verdict(w, (p.FAIL, "job-missing"))

    def test_loose_check_run_spoof_does_not_pass(self):
        w = World()
        w.runs = []  # a green check run named like the job exists, but no workflow run does
        self.verdict(w, (p.BLOCKED, "no-matching-push-run"))
        self.assertFalse(w.check_runs_called)

    def test_http_and_git_errors_blocked(self):
        w = World()
        w.fail_http = "http-500"
        self.verdict(w, (p.BLOCKED, "http-500"))
        w = World()
        w.fail_git = True
        self.verdict(w, (p.BLOCKED, "git-error"))

    def test_unexpected_exception_blocked(self):
        w = World()
        w.fetch = lambda repo, pr: 1 / 0
        self.verdict(w, (p.BLOCKED, "internal-error"))

    def test_truncated_results_blocked(self):
        w = World()
        w.get_orig = w.get
        w.get = lambda path: ({**w.get_orig(path), "total_count": 101}
                              if "/actions/runs?" in path else w.get_orig(path))
        self.verdict(w, (p.BLOCKED, "runs-truncated"))

    def test_head_moving_during_evaluation_fails(self):
        w = World()
        calls = []
        orig = w.get

        def get(path):
            d = orig(path)
            if "/pulls/" in path:
                calls.append(1)
                if len(calls) == 2:
                    d["head"]["sha"] = "9" * 40
            return d
        w.get = get
        self.verdict(w, (p.FAIL, "head-moved-during-evaluation"))

    def test_bad_config_blocked(self):
        for over in ({"repo": "nonsense"}, {"pr": 0}, {"pr": "10"}, {"pinned_github_tree": "xyz"},
                     {"job_name": ""}):
            self.verdict(World(), (p.BLOCKED, "bad-config-" + (
                "repo" if "repo" in over else "pr" if "pr" in over
                else "pin" if "pinned_github_tree" in over else "workflow")), **over)

    def test_only_pass_verdict_is_exactly_pass(self):
        self.assertEqual({p.EXIT[p.PASS], p.EXIT[p.FAIL], p.EXIT[p.BLOCKED]}, {0, 1, 3})


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class HttpGitTests(unittest.TestCase):
    def test_http_get_errors_are_blocked(self):
        def raiser(exc):
            def opener(req, timeout):
                raise exc
            return opener
        for exc, reason in ((urllib.error.HTTPError("u", 403, "x", {}, None), "http-403"),
                            (urllib.error.URLError("x"), "http-unreachable"),
                            (TimeoutError(), "http-unreachable")):
            with self.assertRaises(p.Gate) as cm:
                p.http_get("/x", raiser(exc))
            self.assertEqual((cm.exception.verdict, cm.exception.reason), (p.BLOCKED, reason))

    def test_http_get_bounds_and_shape(self):
        for body, reason in ((b"x" * (p.MAX_BODY + 1), "http-too-large"), (b"nope", "http-bad-json"),
                             (b"[]", "http-bad-shape")):
            with self.assertRaises(p.Gate) as cm:
                p.http_get("/x", lambda req, timeout, b=body: FakeResp(b))
            self.assertEqual(cm.exception.reason, reason)
        self.assertEqual(p.http_get("/x", lambda req, timeout: FakeResp(b'{"a": 1}')), {"a": 1})

    def test_http_get_sends_no_credentials_and_uses_timeout(self):
        seen = {}

        def opener(req, timeout):
            seen.update(timeout=timeout, headers={k.lower() for k in req.headers}, url=req.full_url)
            return FakeResp(b"{}")
        p.http_get("/x", opener)
        self.assertEqual(seen["timeout"], p.HTTP_TIMEOUT)
        self.assertNotIn("authorization", seen["headers"])
        self.assertTrue(seen["url"].startswith("https://api.github.com/"))

    def test_git_uses_argv_timeout_and_inert_fetch(self):
        calls = []

        def run(argv, **kw):
            calls.append((argv, kw))
            out = ""
            if argv[-1].endswith(":.github"):
                out = TREE + "\n"
            elif argv[1:2] == ["rev-parse"]:
                out = SHA + "\n"
            return subprocess.CompletedProcess(argv, 0, out, "")
        self.assertEqual(p.git_fetch_pr(REPO, 10, run), (SHA, TREE))
        for argv, kw in calls:
            self.assertIsInstance(argv, list)
            self.assertEqual(kw["timeout"], p.GIT_TIMEOUT)
            self.assertNotIn("shell", kw)
            self.assertNotIn("checkout", argv)
        fetch = [a for a, _ in calls if "fetch" in a][0]
        self.assertIn("+refs/pull/10/head:refs/pull/10/head", fetch)
        self.assertIn("protocol.allow=never", fetch)

    def test_git_failure_and_timeout_blocked(self):
        for run in (lambda argv, **kw: subprocess.CompletedProcess(argv, 128, "", "boom"),
                    lambda argv, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(argv, 1))):
            with self.assertRaises(p.Gate) as cm:
                p.git_fetch_pr(REPO, 10, run)
            self.assertEqual((cm.exception.verdict, cm.exception.reason), (p.BLOCKED, "git-error"))


class CliTests(unittest.TestCase):
    def test_non_dry_run_refused(self):
        with self.assertRaises(SystemExit) as cm:
            p.main(["--repo", REPO, "--pr", "10", "--pinned-github-tree", TREE])
        self.assertEqual(cm.exception.code, 2)

    def test_pin_is_required(self):
        with self.assertRaises(SystemExit):
            p.main(["--dry-run", "--repo", REPO, "--pr", "10"])


if __name__ == "__main__":
    unittest.main()
