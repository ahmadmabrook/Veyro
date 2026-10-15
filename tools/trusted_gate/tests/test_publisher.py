import base64
import contextlib
import copy
import fcntl
import hashlib
import io
import json
import os
import subprocess
import sys
import shutil
import tempfile
import types
import unittest
import unittest.mock
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
        self.verdict(w, (p.BLOCKED, "head-sha-mismatch"))

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
        self.verdict(w, (p.BLOCKED, "job-ambiguous"))
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

    def test_head_moving_during_evaluation_blocks(self):
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
        self.verdict(w, (p.BLOCKED, "head-moved-during-evaluation"))

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
        for argv, kw in calls:
            self.assertEqual(argv[0], "/usr/bin/git")
            self.assertEqual(kw["env"]["PATH"], "/usr/bin:/bin")
            self.assertFalse({k for k in kw["env"] if k.upper().endswith("_PROXY") or k.startswith("SSL_")})
        fetch = [a for a, _ in calls if "fetch" in a][0]
        self.assertIn("http.proxy=", fetch)
        self.assertIn("http.followRedirects=false", fetch)
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


APP_ID, INST_ID = 4242, 777
KEY = "-----BEGIN PRIVATE KEY-----\nSUPERSECRETKEYMATERIAL\n-----END PRIVATE KEY-----\n"
TOKEN = "ghs_SUPERSECRETTOKEN"
SIG = b"s" * 256


class AppWorld:
    """Fake GitHub App API + Keychain + signer for publish()."""

    def __init__(self, state_path):
        self.gh = World()
        self.cfg = {"app_id": APP_ID, "installation_id": INST_ID, "repo": REPO, "pinned_github_tree": TREE,
                    "publisher_sha256": p.publisher_digest(), "keychain_service": "veyro-gate-app",
                    "keychain_account": "app-key", "keychain_path": "/nonexistent/veyro-gate.keychain-db",
                    "state_path": state_path}
        self.checks = []  # check runs on GitHub
        self.calls = []
        self.secret_reads = 0
        self.sign_calls = 0
        self.keychain_fail = False
        self.fail_post = None
        self.crash_after_post = False
        self.token_doc = {"token": TOKEN, "permissions": {"checks": "write"},
                          "repositories": [{"full_name": REPO}]}
        self.next_id = 1

    def read_secret(self, service, account, keychain_path):
        assert keychain_path == self.cfg["keychain_path"]
        self.secret_reads += 1
        if self.keychain_fail:
            raise p.Gate(p.BLOCKED, "keychain-error")
        return KEY

    def sign(self, key, msg):
        self.sign_calls += 1
        assert key == KEY
        return SIG

    def transport(self, method, path, bearer, body=None):
        self.calls.append((method, path, bearer, body))
        if path.startswith("/app/installations/"):
            assert bearer.count(".") == 2 and path == f"/app/installations/{INST_ID}/access_tokens"
            assert body == {"repositories": ["Veyro"], "permissions": {"checks": "write"}}
            return dict(self.token_doc)
        assert bearer == TOKEN
        if method == "GET":
            assert f"check_name={p.CHECK_NAME}" in path
            return {"total_count": len(self.checks), "check_runs": list(self.checks)}
        if self.fail_post:
            raise p.Gate(p.BLOCKED, self.fail_post)
        run = {**body, "id": self.next_id, "app": {"id": APP_ID}}
        self.next_id += 1
        self.checks.append(run)
        if self.crash_after_post:
            raise p.Gate(p.BLOCKED, "http-unreachable")
        return run

    def publish(self, pr=10, **kw):
        args = dict(get=self.gh.get, fetch=self.gh.fetch, read_secret=self.read_secret, sign=self.sign,
                    transport=self.transport, now=lambda: 1_000_000, guard=lambda: None)
        args.update(kw)
        return p.publish(self.cfg, pr, **args)

    def posts(self):
        return [c for c in self.calls if c[0] == "POST" and c[1].endswith("/check-runs")]

    def ext(self, sha=SHA, pr=10, run=100, attempt=1, job=900, conclusion="success"):
        return p.external_id(pr, sha, TREE, self.cfg["publisher_sha256"], run, attempt, job, conclusion)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state", "gate.json")
        self.w = AppWorld(self.state)

    def test_pass_posts_success(self):
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"], r["adopted"]), (p.PASS, True, False))
        (_, _, _, body), = self.w.posts()
        self.assertEqual((body["name"], body["head_sha"], body["status"], body["conclusion"]),
                         ("veyro-trusted-gate", SHA, "completed", "success"))
        self.assertEqual(body["external_id"], self.w.ext())
        for part in (f"pr=10", f"head={SHA}", f"tree={TREE}", f"pub={self.w.cfg['publisher_sha256']}",
                     "run=100", "attempt=1", "job=900", "conclusion=success"):
            self.assertIn(part, body["external_id"])
        summary = body["output"]["summary"]
        for part in ("run_id=100", "attempt=1", "job_id=900", f"head={SHA}", f"pinned_tree={TREE}",
                     "candidate-controlled test code is not attested"):
            self.assertIn(part, summary)

    def test_rerun_on_same_head_creates_new_check_both_directions(self):
        self.w.publish()  # PASS run 100 attempt 1
        self.w.gh.runs = [run_doc(run_attempt=2, conclusion="failure")]  # PASS -> FAIL rerun
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"], r["adopted"]), (p.FAIL, True, False))
        self.w.gh.runs = [run_doc(run_attempt=3)]  # FAIL -> PASS rerun
        self.w.gh.jobs[(100, 3)] = [job_doc()]
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"], r["adopted"]), (p.PASS, True, False))
        self.assertEqual(len(self.w.checks), 3)
        self.assertEqual(len({c["external_id"] for c in self.w.checks}), 3)
        self.assertIn("attempt=2", self.w.checks[1]["external_id"])
        self.assertIn("job=none", self.w.checks[1]["external_id"])
        self.assertIn("conclusion=failure", self.w.checks[1]["external_id"])

    def test_head_move_and_job_ambiguity_never_publish_failure(self):
        w = AppWorld(os.path.join(self.tmp.name, "s5.json"))
        w.gh.fetched = ("e" * 40, TREE)
        r = w.publish()
        self.assertEqual((r["verdict"], r["reason"], r["published"]), (p.BLOCKED, "head-sha-mismatch", False))
        w = AppWorld(os.path.join(self.tmp.name, "s6.json"))
        w.gh.jobs[(100, 1)] = [job_doc(), job_doc(id=901)]
        r = w.publish()
        self.assertEqual((r["verdict"], r["reason"], r["published"]), (p.BLOCKED, "job-ambiguous", False))
        self.assertEqual((w.calls, w.secret_reads), ([], 0))

    def test_head_moving_just_before_post_blocks(self):
        orig, n = self.w.gh.get, []

        def get(path):
            d = orig(path)
            if "/pulls/" in path:
                n.append(1)
                if len(n) == 3:  # evaluation reads twice; third read is the pre-publish recheck
                    d["head"]["sha"] = "9" * 40
            return d
        r = self.w.publish(get=get)
        self.assertEqual((r["reason"], r["published"]), ("head-moved-before-publish", False))
        self.assertEqual(self.w.posts(), [])

    def test_guard_runs_before_keychain_network_and_state(self):
        def refuse():
            raise p.Gate(p.BLOCKED, "publisher-in-worktree")
        r = self.w.publish(guard=refuse)
        self.assertEqual((r["reason"], r["published"]), ("publisher-in-worktree", False))
        self.assertEqual((self.w.calls, self.w.secret_reads, self.w.sign_calls), ([], 0, 0))
        self.assertFalse(os.path.exists(self.state))

    def test_fail_posts_failure(self):
        self.w.gh.runs = [run_doc(conclusion="failure")]
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"]), (p.FAIL, True))
        self.assertEqual(self.w.posts()[0][3]["conclusion"], "failure")

    def test_only_success_or_failure_ever_posted(self):
        for mutate in (lambda w: setattr(w.gh, "fail_http", "http-503"),
                       lambda w: setattr(w.gh, "fail_git", True),
                       lambda w: setattr(w.gh, "runs", [run_doc(status="in_progress")]),
                       lambda w: setattr(w.gh, "runs", [run_doc(conclusion="skipped")]),
                       lambda w: setattr(w.gh, "runs", [run_doc(conclusion="neutral")])):
            w = AppWorld(os.path.join(self.tmp.name, "s2.json"))
            mutate(w)
            r = w.publish()
            if r["published"]:
                self.assertIn(w.posts()[0][3]["conclusion"], ("success", "failure"))
                self.assertEqual(r["verdict"], p.FAIL)
            else:
                self.assertEqual(w.posts(), [])

    def test_blocked_publishes_nothing_and_never_touches_key(self):
        self.w.gh.fail_http = "http-503"
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"]), (p.BLOCKED, False))
        self.assertEqual((self.w.secret_reads, self.w.sign_calls, self.w.calls), (0, 0, []))
        self.assertFalse(os.path.exists(self.state))

    def test_run_in_progress_is_blocked_not_published(self):
        self.w.gh.runs = [run_doc(status="in_progress", conclusion=None)]
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"]), (p.BLOCKED, False))
        self.assertEqual(self.w.calls, [])

    def test_fail_without_head_sha_not_published(self):
        self.w.gh.pr = pr_doc(state="closed")
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["reason"], r["published"]), (p.BLOCKED, "no-head-sha", False))
        self.assertEqual(self.w.calls, [])

    def test_keychain_failure_blocks_without_post(self):
        self.w.keychain_fail = True
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["reason"], r["published"]), (p.BLOCKED, "keychain-error", False))
        self.assertEqual(self.w.calls, [])

    def test_signer_failure_blocks(self):
        def bad(key, msg):
            raise p.Gate(p.BLOCKED, "sign-failed")
        r = self.w.publish(sign=bad)
        self.assertEqual((r["reason"], r["published"]), ("sign-failed", False))
        self.assertEqual(self.w.calls, [])

    def test_short_signature_rejected(self):
        r = self.w.publish(sign=lambda k, m: b"x" * 10)
        self.assertEqual((r["reason"], r["published"]), ("sign-failed", False))

    def test_http_failures_block(self):
        self.w.fail_post = "http-422"
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["reason"], r["published"]), (p.BLOCKED, "http-422", False))
        w2 = AppWorld(os.path.join(self.tmp.name, "s3.json"))

        def boom(*a, **k):
            raise RuntimeError(TOKEN + KEY)
        r2 = w2.publish(transport=boom)
        self.assertEqual((r2["reason"], r2["published"]), ("internal-error", False))
        self.assertNotIn(TOKEN, json.dumps(r2))

    def test_token_must_be_minimally_scoped(self):
        for doc in ({"token": TOKEN, "permissions": {"checks": "write", "contents": "write"},
                     "repositories": [{"full_name": REPO}]},
                    {"token": TOKEN, "permissions": {"checks": "write"}, "repositories": []},
                    {"token": TOKEN, "permissions": {"checks": "write"},
                     "repositories": [{"full_name": REPO}, {"full_name": "x/y"}]},
                    {"token": TOKEN, "permissions": {"checks": "write"},
                     "repositories": [{"full_name": "other/Repo"}]}):
            w = AppWorld(os.path.join(self.tmp.name, "s4.json"))
            w.token_doc = doc
            r = w.publish()
            self.assertEqual((r["reason"], r["published"]), ("token-overscoped", False))
            self.assertEqual(w.posts(), [])

    def test_crash_after_post_then_rerun_adopts_without_duplicate(self):
        self.w.crash_after_post = True
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"]), (p.BLOCKED, False))
        self.assertEqual(len(self.w.checks), 1)
        with open(self.state) as f:
            self.assertEqual(json.load(f)["checks"][self.w.ext()]["status"], "intent")
        self.w.crash_after_post = False
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"], r["adopted"]), (p.PASS, True, True))
        self.assertEqual(len(self.w.checks), 1)
        self.assertEqual(len(self.w.posts()), 1)
        with open(self.state) as f:
            ent = json.load(f)["checks"][self.w.ext()]
        self.assertEqual((ent["status"], ent["adopted"], ent["check_run_id"]), ("published", True, 1))

    def test_second_run_is_idempotent(self):
        self.w.publish()
        r = self.w.publish()
        self.assertEqual((r["published"], r["adopted"]), (True, True))
        self.assertEqual(len(self.w.checks), 1)

    def test_foreign_same_name_check_not_adopted(self):
        self.w.checks.append({"id": 99, "name": p.CHECK_NAME, "head_sha": SHA, "status": "completed",
                              "conclusion": "success", "external_id": self.w.ext(), "app": {"id": 666}})
        r = self.w.publish()
        self.assertEqual((r["published"], r["adopted"]), (True, False))
        self.assertEqual(len(self.w.posts()), 1)
        self.assertNotEqual(r["check_run_id"], 99)

    def test_ambiguous_own_duplicates_rejected(self):
        for i in (1, 2):
            self.w.checks.append({"id": i, "name": p.CHECK_NAME, "head_sha": SHA, "status": "completed",
                                  "conclusion": "success", "external_id": self.w.ext(), "app": {"id": APP_ID}})
        r = self.w.publish()
        self.assertEqual((r["reason"], r["published"]), ("ambiguous-duplicate-checks", False))
        self.assertEqual(self.w.posts(), [])

    def test_existing_own_check_with_other_conclusion_conflicts(self):
        self.w.checks.append({"id": 1, "name": p.CHECK_NAME, "head_sha": SHA, "status": "completed",
                              "conclusion": "failure", "external_id": self.w.ext(), "app": {"id": APP_ID}})
        r = self.w.publish()
        self.assertEqual((r["reason"], r["published"]), ("existing-check-conflict", False))
        self.assertEqual(self.w.posts(), [])

    def test_check_run_without_app_id_blocks(self):
        self.w.checks.append({"id": 1, "name": p.CHECK_NAME, "external_id": self.w.ext()})
        r = self.w.publish()
        self.assertEqual((r["reason"], r["published"]), ("checks-bad-shape", False))

    def test_response_from_wrong_app_rejected(self):
        orig = self.w.transport

        def wrong(method, path, bearer, body=None):
            res = orig(method, path, bearer, body)
            if method == "POST" and path.endswith("/check-runs"):
                res = {**res, "app": {"id": 1}}
            return res
        r = self.w.publish(transport=wrong)
        self.assertEqual((r["reason"], r["published"]), ("check-response-mismatch", False))

    def test_wrong_config_digest_refuses_everything(self):
        self.w.cfg["publisher_sha256"] = "0" * 64
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["reason"], r["published"]), (p.BLOCKED, "publisher-digest-mismatch", False))
        self.assertEqual((self.w.calls, self.w.secret_reads, self.w.sign_calls), ([], 0, 0))
        self.assertFalse(os.path.exists(self.state))

    def test_digest_tracks_publisher_bytes(self):
        path = os.path.join(self.tmp.name, "pub.py")
        with open(path, "wb") as f:
            f.write(b"print(1)\n")
        self.assertEqual(p.publisher_digest(path), hashlib.sha256(b"print(1)\n").hexdigest())
        r = self.w.publish(publisher_path=path)  # config digest is for the real file
        self.assertEqual(r["reason"], "publisher-digest-mismatch")

    def test_new_sha_gets_new_check(self):
        self.w.publish()
        sha2 = "c" * 40
        self.w.gh.pr = pr_doc(head={"sha": sha2, "repo": {"full_name": REPO}})
        self.w.gh.fetched = (sha2, TREE)
        self.w.gh.runs = [run_doc(head_sha=sha2, id=101)]
        self.w.gh.jobs = {(101, 1): [job_doc(run_id=101, head_sha=sha2)]}
        r = self.w.publish()
        self.assertEqual((r["verdict"], r["published"], r["adopted"]), (p.PASS, True, False))
        self.assertEqual([c[3]["head_sha"] for c in self.w.posts()], [SHA, sha2])
        self.assertEqual(len({c[3]["external_id"] for c in self.w.posts()}), 2)

    def test_concurrent_lock_blocks(self):
        os.makedirs(os.path.dirname(self.state))
        holder = os.open(self.state + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, holder)
        fcntl.flock(holder, fcntl.LOCK_EX)
        r = self.w.publish()
        self.assertEqual((r["reason"], r["published"]), ("state-locked", False))
        self.assertEqual(self.w.posts(), [])

    def test_corrupt_state_blocks(self):
        os.makedirs(os.path.dirname(self.state))
        with open(self.state, "w") as f:
            f.write("{not json")
        r = self.w.publish()
        self.assertEqual((r["reason"], r["published"]), ("state-corrupt", False))
        self.assertEqual(self.w.posts(), [])

    def test_no_secret_in_output_state_or_post_body(self):
        r = self.w.publish()
        with open(self.state) as f:
            state_text = f.read()
        blob = json.dumps(r) + state_text + json.dumps([c[3] for c in self.w.calls])
        for secret in (TOKEN, "SUPERSECRETKEYMATERIAL", base64.b64encode(SIG).decode()):
            self.assertNotIn(secret, blob)
        self.assertEqual(os.stat(self.state).st_mode & 0o077, 0)
        self.assertEqual([n for n in os.listdir(os.path.dirname(self.state)) if n.startswith(".state-")], [])

    def test_jwt_shape(self):
        seen = {}

        def sign(key, msg):
            seen["msg"] = msg
            return SIG
        jwt = p.make_jwt(APP_ID, KEY, sign, lambda: 1000)
        h, b, s = jwt.split(".")
        pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
        self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(h))), {"alg": "RS256", "typ": "JWT"})
        claims = json.loads(base64.urlsafe_b64decode(pad(b)))
        self.assertEqual((claims["iss"], claims["iat"], claims["exp"]), (str(APP_ID), 940, 1480))
        self.assertEqual(seen["msg"], f"{h}.{b}".encode())
        self.assertEqual(base64.urlsafe_b64decode(pad(s)), SIG)


class FakeProc:
    def __init__(self, stdout=b"", returncode=0):
        self.stdout, self.returncode = stdout, returncode


class SecretToolTests(unittest.TestCase):
    def test_keychain_read_uses_stdout_not_env(self):
        seen = {}

        def run(argv, **kw):
            seen.update(argv=argv, kw=kw)
            return FakeProc(KEY.encode())
        self.assertEqual(p.keychain_read("svc", "acct", "/k/gate.keychain-db", run), KEY.rstrip("\n"))
        self.assertEqual(seen["argv"][:2], [p.SECURITY_BIN, "find-generic-password"])
        self.assertIn("-w", seen["argv"])
        self.assertEqual(seen["argv"][-1], "/k/gate.keychain-db")  # explicit keychain, never the default
        self.assertNotIn("SUPERSECRETKEYMATERIAL", " ".join(seen["argv"]))
        self.assertEqual(set(seen["kw"]["env"]), {"PATH"})
        self.assertTrue(seen["kw"]["capture_output"])

    def test_keychain_hex_output_decoded(self):
        run = lambda argv, **kw: FakeProc(KEY.encode().hex().encode() + b"\n")  # noqa: E731
        self.assertEqual(p.keychain_read("s", "a", "/k", run), KEY.rstrip("\n"))

    def test_keychain_errors_blocked(self):
        for proc in (FakeProc(b"", 44), FakeProc(b"not a key"), FakeProc(b"")):
            with self.assertRaises(p.Gate) as cm:
                p.keychain_read("s", "a", "/k", lambda argv, **kw: proc)
            self.assertEqual(cm.exception.verdict, p.BLOCKED)

        def timeout(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 1)
        with self.assertRaises(p.Gate):
            p.keychain_read("s", "a", "/k", timeout)

    def test_partial_writes_deliver_whole_key(self):
        seen = {}

        def run(argv, **kw):
            seen["key"] = os.read(int(argv[-1].rsplit("/", 1)[1]), 65536)
            return FakeProc(SIG)
        self.assertEqual(p.openssl_sign(KEY, b"m", run, lambda fd, b: os.write(fd, bytes(b[:7]))), SIG)
        self.assertEqual(seen["key"], KEY.encode())

    def test_zero_or_failing_write_fails_closed_and_closes_fds(self):
        opened = []
        real_pipe = os.pipe

        def pipe():
            fds = real_pipe()
            opened.extend(fds)
            return fds
        for write in (lambda fd, b: 0, lambda fd, b: (_ for _ in ()).throw(OSError("pipe"))):
            with unittest.mock.patch("os.pipe", pipe):
                with self.assertRaises(p.Gate) as cm:
                    p.openssl_sign(KEY, b"m", lambda *a, **k: self.fail("signed truncated key"), write)
            self.assertEqual(cm.exception.reason, "sign-failed")
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_openssl_sign_passes_key_by_fd_not_argv(self):
        seen = {}

        def run(argv, **kw):
            fd = int(argv[-1].rsplit("/", 1)[1])
            seen.update(argv=argv, kw=kw, key=os.read(fd, 65536))
            return FakeProc(SIG)
        self.assertEqual(p.openssl_sign(KEY, b"msg", run), SIG)
        self.assertEqual(seen["key"], KEY.encode())
        self.assertNotIn("SUPERSECRETKEYMATERIAL", " ".join(seen["argv"]))
        self.assertTrue(seen["argv"][-1].startswith("/dev/fd/"))
        self.assertEqual(seen["kw"]["input"], b"msg")
        self.assertEqual(len(seen["kw"]["pass_fds"]), 1)
        with self.assertRaises(OSError):  # fds closed afterwards
            os.fstat(seen["kw"]["pass_fds"][0])

    def test_openssl_failure_blocked_without_leak(self):
        with self.assertRaises(p.Gate) as cm:
            p.openssl_sign(KEY, b"m", lambda argv, **kw: FakeProc(b"", 1))
        self.assertNotIn("SUPERSECRET", str(cm.exception))

    @unittest.skipUnless(os.path.exists(p.OPENSSL_BIN), "openssl not available")
    def test_real_openssl_signature_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            kp, pp, sp, mp = (os.path.join(d, n) for n in ("k.pem", "p.pem", "s.bin", "m.bin"))
            gen = subprocess.run([p.OPENSSL_BIN, "genrsa", "-out", kp, "2048"], capture_output=True)
            if gen.returncode != 0:
                self.skipTest("openssl genrsa unavailable")
            subprocess.run([p.OPENSSL_BIN, "rsa", "-in", kp, "-pubout", "-out", pp], capture_output=True, check=True)
            with open(kp) as f:
                pem = f.read()
            sig = p.openssl_sign(pem, b"hello")
            with open(sp, "wb") as f:
                f.write(sig)
            with open(mp, "wb") as f:
                f.write(b"hello")
            v = subprocess.run([p.OPENSSL_BIN, "dgst", "-sha256", "-verify", pp, "-signature", sp, mp],
                               capture_output=True)
            self.assertEqual(v.returncode, 0)


class HttpApiTests(unittest.TestCase):
    def test_header_and_fixed_host(self):
        seen = {}

        def opener(req, timeout):
            seen.update(url=req.full_url, auth=req.get_header("Authorization"), timeout=timeout,
                        method=req.get_method(), data=req.data)
            return FakeResp(b'{"ok": 1}')
        self.assertEqual(p.http_api("POST", "/x/y", TOKEN, {"a": 1}, opener), {"ok": 1})
        self.assertEqual(seen["url"], "https://api.github.com/x/y")
        self.assertEqual((seen["auth"], seen["timeout"], seen["method"]), (f"Bearer {TOKEN}", p.HTTP_TIMEOUT, "POST"))

    def test_arbitrary_host_paths_refused(self):
        for bad in ("https://evil.example/x", "//evil.example/x", "x", "/a b", "/a\r\nHost: x"):
            with self.assertRaises(p.Gate) as cm:
                p.http_api("GET", bad, TOKEN, None, lambda *a, **k: self.fail("called"))
            self.assertEqual(cm.exception.reason, "bad-api-path")

    def test_errors_do_not_contain_token(self):
        def opener(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, TOKEN, {}, io.BytesIO(TOKEN.encode()))
        with self.assertRaises(p.Gate) as cm:
            p.http_api("GET", "/x", TOKEN, None, opener)
        self.assertEqual(cm.exception.reason, "http-401")
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_redirects_refused(self):
        h = p._NoRedirect()
        self.assertIsNone(h.redirect_request(None, None, 302, "Found", {}, "https://evil.example/"))


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(self.root, ".git"))  # any directory holding `.git` is a worktree
        self.good = {"app_id": APP_ID, "installation_id": INST_ID, "repo": REPO, "pinned_github_tree": TREE,
                     "publisher_sha256": "d" * 64, "keychain_service": "svc", "keychain_account": "acct",
                     "keychain_path": os.path.join(self.tmp.name, "gate.keychain-db"),
                     "state_path": os.path.join(self.tmp.name, "state.json")}

    def write(self, doc, name="cfg.json", mode=0o600):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as f:
            json.dump(doc, f)
        os.chmod(path, mode)
        return path

    def reason(self, path):
        with self.assertRaises(p.Gate) as cm:
            p.load_config(path)
        return cm.exception.reason

    def test_good_config_loads(self):
        self.assertEqual(p.load_config(self.write(self.good)), self.good)

    def test_missing_and_unknown_keys_refused(self):
        for k in self.good:
            doc = {x: v for x, v in self.good.items() if x != k}
            self.assertEqual(self.reason(self.write(doc)), "config-bad-keys", k)
        self.assertEqual(self.reason(self.write({**self.good, "api_url": "https://evil.example"})), "config-bad-keys")

    def test_bad_values_refused(self):
        for key, val in (("app_id", "1"), ("app_id", True), ("installation_id", 0), ("repo", "nope"),
                         ("pinned_github_tree", "xyz"), ("publisher_sha256", "abc"),
                         ("keychain_service", ""), ("keychain_account", "a\nb"), ("state_path", "rel.json"),
                         ("keychain_path", ""), ("keychain_path", "login.keychain-db")):
            self.assertTrue(self.reason(self.write({**self.good, key: val})), key)

    def test_in_repo_paths_refused(self):
        inside = os.path.join(self.root, "cfg.json")
        with open(inside, "w") as f:
            json.dump(self.good, f)
        os.chmod(inside, 0o600)
        self.assertEqual(self.reason(inside), "config-inside-repo")
        self.assertEqual(self.reason(self.write({**self.good, "state_path": os.path.join(self.root, "s.json")})),
                         "config-bad-state-path")
        self.assertEqual(self.reason(self.write({**self.good, "keychain_path": os.path.join(self.root, "k")})),
                         "config-bad-keychain")
        self.assertEqual(self.reason("cfg.json"), "config-path-not-absolute")

    def test_symlink_into_worktree_and_nested_worktree_refused(self):
        deep = os.path.join(self.root, "a", "b")
        os.makedirs(deep)
        link = os.path.join(self.tmp.name, "link")
        os.symlink(deep, link)
        self.assertTrue(p.in_git_worktree(deep))
        self.assertTrue(p.in_git_worktree(os.path.join(link, "new", "state.json")))
        self.assertEqual(self.reason(self.write({**self.good, "state_path": os.path.join(link, "s.json")})),
                         "config-bad-state-path")
        self.assertFalse(p.in_git_worktree(os.path.join(self.tmp.name, "elsewhere", "s.json")))

    def test_keychain_path_is_mandatory(self):
        doc = {k: v for k, v in self.good.items() if k != "keychain_path"}
        self.assertEqual(self.reason(self.write(doc)), "config-bad-keys")

    def test_writable_config_refused(self):
        self.assertEqual(self.reason(self.write(self.good, mode=0o666)), "config-bad-permissions")

    def test_unreadable_or_garbage_refused(self):
        self.assertEqual(self.reason(os.path.join(self.tmp.name, "missing.json")), "config-unreadable")
        path = os.path.join(self.tmp.name, "bad.json")
        with open(path, "w") as f:
            f.write("nope")
        os.chmod(path, 0o600)
        self.assertEqual(self.reason(path), "config-unreadable")


class PublishCliTests(unittest.TestCase):
    def test_publish_requires_config_and_pr(self):
        with self.assertRaises(SystemExit):
            p.main(["publish", "--pr", "10"])
        with self.assertRaises(SystemExit):
            p.main(["publish", "--config", "/tmp/x.json"])

    def test_bad_config_is_blocked_exit_3_without_publishing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = p.main(["publish", "--config", "relative.json", "--pr", "10"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out.getvalue())["published"], False)

    def test_digest_command(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(p.main(["digest"]), 0)
        self.assertEqual(out.getvalue().strip(), p.publisher_digest())

    def test_no_generic_url_option(self):
        with self.assertRaises(SystemExit):
            p.main(["publish", "--config", "/tmp/x.json", "--pr", "10", "--api-url", "https://evil.example"])


class InstallContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.realpath(self.tmp.name)

    def install(self, where, mode=0o600):
        os.makedirs(where, exist_ok=True)
        dest = os.path.join(where, "publisher.py")
        shutil.copy(p._SELF, dest)
        os.chmod(dest, mode)
        return dest

    def reason(self, **kw):
        with self.assertRaises(p.Gate) as cm:
            p.check_publish_context(**{"cafile": __file__, "environ": {}, **kw})
        return cm.exception.reason

    def test_installed_copy_outside_worktree_passes(self):
        dest = self.install(os.path.join(self.base, "inst"))
        p.check_publish_context(environ={}, path=dest, isolated=True, cafile=__file__)

    def test_unisolated_python_refused(self):
        dest = self.install(os.path.join(self.base, "inst"))
        self.assertEqual(self.reason(path=dest, isolated=False), "not-isolated")

    def test_in_repo_copy_refused(self):
        wt = os.path.join(self.base, "wt")
        os.makedirs(os.path.join(wt, ".git"))
        dest = self.install(os.path.join(wt, "tools", "trusted_gate"))
        self.assertEqual(self.reason(path=dest, isolated=True), "publisher-in-worktree")

    def test_group_world_writable_or_foreign_install_refused(self):
        inst = os.path.join(self.base, "inst")
        dest = self.install(inst, mode=0o620)
        self.assertEqual(self.reason(path=dest, isolated=True), "publisher-bad-installation")
        os.chmod(dest, 0o600)
        os.chmod(inst, 0o777)
        self.addCleanup(os.chmod, inst, 0o700)
        self.assertEqual(self.reason(path=dest, isolated=True), "publisher-bad-installation")
        os.chmod(inst, 0o700)
        with unittest.mock.patch("os.geteuid", return_value=os.geteuid() + 1):
            self.assertEqual(self.reason(path=dest, isolated=True), "publisher-bad-installation")

    def test_sibling_shadow_modules_refused(self):
        dest = self.install(os.path.join(self.base, "inst"))
        for name in ("hmac", "json", "subprocess"):
            fake = {name: types.SimpleNamespace(__file__=os.path.join(os.path.dirname(dest), name + ".py"))}
            self.assertEqual(self.reason(path=dest, isolated=True, modules=fake), "module-shadowed", name)

    def test_env_overrides_refused_before_anything_else(self):
        dest = self.install(os.path.join(self.base, "inst"))
        for k in ("HTTPS_PROXY", "http_proxy", "ALL_PROXY", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
                  "PYTHONPATH", "PYTHONSTARTUP", "DYLD_INSERT_LIBRARIES", "GIT_SSL_NO_VERIFY"):
            self.assertEqual(self.reason(path=dest, isolated=True, environ={k: "x", "PATH": "/usr/bin"}),
                             "env-override-refused", k)

    def test_missing_tls_trust_file_refused(self):
        dest = self.install(os.path.join(self.base, "inst"))
        self.assertEqual(self.reason(path=dest, isolated=True, cafile="/nonexistent/ca.pem"),
                         "tls-trust-unavailable")

    def run_script(self, script, *extra, isolated=True):
        argv = [sys.executable] + (["-I"] if isolated else []) + [script, "publish", "--config", "relative.json",
                                                                   "--pr", "1"] + list(extra)
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=os.path.dirname(script),
                              env={"PATH": "/usr/bin:/bin"}, timeout=60)
        return proc, (json.loads(proc.stdout) if proc.stdout.strip() else {})

    def test_subprocess_shadow_hmac_and_repo_copy_cannot_publish(self):
        inst = os.path.join(self.base, "inst")
        dest = self.install(inst)
        with open(os.path.join(inst, "hmac.py"), "w") as f:
            f.write("import sys\nsys.stderr.write('SHADOW-LOADED')\n"
                    "def compare_digest(a, b):\n    return True\n")
        proc, out = self.run_script(dest, isolated=False)  # script dir would shadow hmac
        self.assertEqual((proc.returncode, out.get("reason"), out.get("published")), (3, "not-isolated", False))
        proc, out = self.run_script(dest, isolated=True)  # -I: shadow never imported, install accepted
        self.assertNotIn("SHADOW-LOADED", proc.stderr)
        self.assertEqual((out.get("reason"), out.get("published")), ("config-path-not-absolute", False))
        wt = os.path.join(self.base, "wt")
        os.makedirs(os.path.join(wt, ".git"))
        proc, out = self.run_script(self.install(os.path.join(wt, "tools")), isolated=True)
        self.assertEqual((proc.returncode, out.get("reason"), out.get("published")),
                         (3, "publisher-in-worktree", False))


class TransportTests(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(p.TLS_CAFILE), "system CA bundle not present")
    def test_opener_ignores_env_proxy_refuses_redirect_and_pins_trust(self):
        env = {"HTTPS_PROXY": "http://evil.example:3128", "HTTP_PROXY": "http://evil.example:3128",
               "SSL_CERT_FILE": "/nonexistent"}
        with unittest.mock.patch.dict(os.environ, env), unittest.mock.patch.object(
                p.urllib.request, "build_opener", wraps=p.urllib.request.build_opener) as build:
            opener = p._build_opener()
        kinds = {type(h) for h in opener.handlers}
        # urllib omits an empty ProxyHandler from opener.handlers, but passing it
        # suppresses build_opener's environment-derived default proxy handler.
        self.assertIsInstance(build.call_args.args[0], p.urllib.request.ProxyHandler)
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIn(p._NoRedirect, kinds)
        self.assertNotIn(p.urllib.request.HTTPRedirectHandler, kinds)
        https = [h for h in opener.handlers if isinstance(h, p.urllib.request.HTTPSHandler)]
        self.assertEqual(len(https), 1)
        ctx = https[0]._context
        self.assertEqual((ctx.verify_mode, ctx.check_hostname), (p.ssl.CERT_REQUIRED, True))

    def test_missing_trust_file_blocks_opener(self):
        with self.assertRaises(p.Gate) as cm:
            p._build_opener("/nonexistent/ca.pem")
        self.assertEqual(cm.exception.reason, "tls-trust-unavailable")

    def test_default_get_and_api_use_secure_opener(self):
        built = []

        class Opener:
            def open(self, req, timeout):
                return FakeResp(b"{}")
        with unittest.mock.patch.object(p, "_build_opener", lambda: built.append(1) or Opener()):
            p.http_get("/x")
            p.http_api("GET", "/x", TOKEN)
        self.assertEqual(len(built), 2)


if __name__ == "__main__":
    unittest.main()
