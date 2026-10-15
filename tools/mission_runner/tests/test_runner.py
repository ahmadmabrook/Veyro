"""Focused control-plane safety tests. Run: python3 -m unittest discover -s tools/mission_runner/tests -t tools/mission_runner"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dashboard  # noqa: E402
import runner as R  # noqa: E402

# Fake `claude` emitting the real `-p --output-format json` result shape (modelUsage carries contextWindow /
# maxOutputTokens limits next to the token counters). Behaviour is steered by KEY=VALUE lines in the prompt.
FAKE = '''#!/usr/bin/env python3
import json, os, subprocess, sys, time
args = sys.argv[1:]
alias = args[args.index("--model") + 1]
prompt = sys.stdin.read()
d = dict(l.split("=", 1) for l in prompt.splitlines() if "=" in l)
if "ARGSFILE" in d:
    json.dump({"args": args, "env": dict(os.environ), "cwd": os.getcwd()}, open(d["ARGSFILE"], "w"))
if "SLEEP" in d:
    open(d["PIDFILE"], "w").write(str(os.getpid()))
    time.sleep(float(d["SLEEP"]))
if "FAIL_UNTIL" in d:
    c = d["COUNTER"]; n = int(open(c).read()) if os.path.exists(c) else 0
    open(c, "w").write(str(n + 1))
    if n < int(d["FAIL_UNTIL"]):
        sys.stderr.write("simulated overload"); sys.exit(1)
def put(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    open(path, "w").write(text)
if "WRITE" in d:
    put(d["WRITE"], d.get("CONTENT", "changed"))
if "WRITE2" in d:
    put(d["WRITE2"], "second")
if "TAMPER" in d:
    open(d["TAMPER"], "ab").write(b"x")
if "WRITE_ABS" in d:
    try:
        put(d["WRITE_ABS"], "pwned"); open(d["ESCAPE_LOG"], "w").write("wrote")
    except OSError as e:
        open(d["ESCAPE_LOG"], "w").write("denied")
if "COMMIT" in d:
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=n", "commit", "-qam", "child", "--allow-empty"], check=True)
model = d.get("MODEL", "claude-%s-5-5" % alias)
tok = {"inputTokens": 10, "outputTokens": 20, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
       "webSearchRequests": 0, "costUSD": 0.01, "contextWindow": 200000, "maxOutputTokens": 32000}
usage = {model: tok}
if "BIG" in d:
    tok.update(inputTokens=5000, outputTokens=3000)
if "MODEL2" in d:
    usage[d["MODEL2"]] = dict(tok, inputTokens=int(d.get("TOK2", 2000)), outputTokens=0)
if "LIMITS_ONLY" in d:
    usage = {model: dict(tok, inputTokens=0, outputTokens=0)}
result = "done"
if "OUTCOME_LINE" in d:
    result = "looks fine\\nOUTCOME: " + d["OUTCOME_LINE"]
out = {"type": "result", "subtype": d.get("SUBTYPE", "success"), "is_error": False, "result": result,
       "session_id": "sess-1", "permission_denials": [{"tool_name": "Bash"}] if "DENIALS" in d else []}
if "NODENIALKEY" in d:
    del out["permission_denials"]
if "NOUSAGE" not in d:
    out["modelUsage"] = usage
print(json.dumps(out))
'''


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                           "-c", "core.hooksPath=/dev/null", *a], check=True, capture_output=True, text=True)


def make_repo(root: Path):
    """Minimal fixture baseline in the exact PROJECT_INDEX.md shape, committed in a throwaway git repo."""
    rows = []
    for n in ("Gym_OS_Master_Product_Blueprint_v1.docx", "Veyro_Technical_System_Design_x.docx",
              "Veyro_Engineering_Implementation_Plan_x.docx"):
        (root / n).write_bytes(n.encode())
        rows.append((n, hashlib.sha256(n.encode()).hexdigest()))
    ux = root / "veyro-product-experience-design"
    (ux / "project").mkdir(parents=True)
    (ux / "README.md").write_text("ux")
    (ux / "project" / "a.txt").write_text("a")
    rows.append(("veyro-product-experience-design/", R.dir_hash(ux)))
    (root / "PROJECT_INDEX.md").write_text("| Source | SHA-256 |\n| --- | --- |\n" +
                                           "".join(f"| `{n}` | `{h}` |\n" for n, h in rows))
    (root / "src").mkdir()
    (root / "src" / "keep.txt").write_text("keep")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")


def index_sha(repo):
    return hashlib.sha256((Path(repo) / "PROJECT_INDEX.md").read_bytes()).hexdigest()


class Base(unittest.TestCase):
    pin = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name).resolve()
        self.repo, self.home = t / "repo", t / "home"
        self.repo.mkdir()
        make_repo(self.repo)
        self.bin = t / "claude"
        self.bin.write_text(FAKE)
        self.bin.chmod(0o755)
        self.cfg = R.Config(home=self.home, repo=self.repo, claude_bin=str(self.bin), tick=0.05,
                            backoff_base=0, max_attempts=3, baseline_every=0, ci_every=0)
        if self.pin:
            R.bootstrap_pin(self.cfg, index_sha(self.repo))

    def runner(self, **kw):
        for k, v in kw.items():
            setattr(self.cfg, k, v)
        r = R.Runner(self.cfg)
        r.state = r.store.load()
        r.state["runner"] = {"pid": os.getpid(), "heartbeat_at": R.now_iso()}
        return r

    def add(self, r, role="implement", prompt=None, id="t1", module="MOD-000", **extra):
        """Default implement task makes one narrow, declared change; review roles end with an outcome line."""
        if role in R.WRITE_ROLES:
            spec = {"allowed_paths": ["out/"], "expected_changes": ["out/a.txt"]} | extra
            prompt = "WRITE=out/a.txt\nCONTENT=hi" if prompt is None else prompt
        else:
            spec = extra
            prompt = "OUTCOME_LINE=APPROVED" if prompt is None else prompt
        R.enqueue(self.cfg, {"id": id, "module": module, "role": role, "prompt": prompt, **spec})
        r.ingest_queue()
        return r.state["tasks"][id]


class Routing(unittest.TestCase):
    """judge_route against the real modelUsage shape."""

    def u(self, **models):
        base = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                "webSearchRequests": 0, "costUSD": 0.0, "contextWindow": 200000, "maxOutputTokens": 32000}
        return {"modelUsage": {m: base | v for m, v in models.items()}}

    def test_limits_are_not_usage(self):
        # sonnet reports a huge contextWindow but spent nothing; opus did the work
        j = R.judge_route("code-review", self.u(**{"claude-sonnet-5-5": {"contextWindow": 1_000_000},
                                                   "claude-opus-5-5": {"inputTokens": 900, "outputTokens": 100}}))
        self.assertEqual((j["verdict"], j["primary"], j["resolved"]), ("VERIFIED", "claude-opus-5-5", ["claude-opus-5-5"]))

    def test_only_limits_means_unverified(self):
        self.assertEqual(R.judge_route("implement", self.u(**{"claude-sonnet-5-5": {}}))["verdict"], "UNVERIFIED")

    def test_mixed_usage_blocks_opus_assurance(self):
        j = R.judge_route("security", self.u(**{"claude-opus-5-5": {"inputTokens": 9000, "outputTokens": 1000},
                                                "claude-sonnet-5-5": {"inputTokens": 400, "outputTokens": 100}}))
        self.assertEqual(j["verdict"], "MISMATCH")
        self.assertIn("claude-sonnet-5-5", j["basis"])

    def test_even_tiny_non_opus_use_blocks_assurance(self):
        j = R.judge_route("security", self.u(**{"claude-opus-5-5": {"inputTokens": 9000, "outputTokens": 1000},
                                                "claude-haiku-5-5": {"inputTokens": 30, "outputTokens": 10}}))
        self.assertEqual(j["verdict"], "MISMATCH")
        self.assertIn("claude-haiku-5-5", j["resolved"])

    def test_cache_tokens_count_as_consumption(self):
        j = R.judge_route("gatekeeper", self.u(**{"claude-opus-5-5": {"outputTokens": 500},
                                                  "claude-haiku-5-5": {"cacheReadInputTokens": 50000}}))
        self.assertEqual(j["verdict"], "MISMATCH")

    def test_sonnet_role_mismatch_when_opus_is_primary(self):
        self.assertEqual(R.judge_route("implement", self.u(**{"claude-opus-5-5": {"outputTokens": 900}}))["verdict"], "MISMATCH")

    def test_canonical_model_wins_over_key(self):
        j = R.judge_route("code-review", self.u(**{"opus": {"outputTokens": 900, "canonicalModel": "claude-opus-5-5"}}))
        self.assertEqual((j["verdict"], j["primary"]), ("VERIFIED", "claude-opus-5-5"))
        j = R.judge_route("code-review", self.u(**{"opus": {"outputTokens": 900, "canonicalModel": "claude-sonnet-5-5"}}))
        self.assertEqual(j["verdict"], "MISMATCH")

    def test_unknown_family_with_tokens_is_mismatch(self):
        self.assertEqual(R.judge_route("implement", self.u(**{"mystery-model": {"outputTokens": 900}}))["verdict"], "MISMATCH")

    def test_no_usage_or_garbage(self):
        for p in (None, {}, {"modelUsage": {}}, {"modelUsage": "x"}, {"modelUsage": {"m": 5}}):
            self.assertEqual(R.judge_route("implement", p)["verdict"], "UNVERIFIED")


class Baseline(Base):
    def test_unpinned_fails_closed_and_blocks_dispatch(self):
        (self.home / "baseline-pin.json").chmod(0o600)
        (self.home / "baseline-pin.json").unlink()
        res = R.verify_baseline(self.repo, R.load_pin(self.home))
        self.assertEqual((res["ok"], res["code"]), (False, "NOT_PINNED"))
        r = self.runner()
        t = self.add(r)
        r.tick()
        self.assertEqual((r.state["health"]["code"], t["status"], t["attempts"]), ("BASELINE_NOT_PINNED", "QUEUED", 0))

    def test_verify_ok_then_fail_closed_on_each_tamper(self):
        pin = R.load_pin(self.home)
        self.assertTrue(R.verify_baseline(self.repo, pin)["ok"])
        (self.repo / "veyro-product-experience-design" / "project" / "a.txt").write_text("changed")
        res = R.verify_baseline(self.repo, pin)
        self.assertFalse(res["ok"])
        self.assertIn("mismatch", res["reason"])
        (self.repo / "PROJECT_INDEX.md").unlink()
        self.assertFalse(R.verify_baseline(self.repo, pin)["ok"])

    def test_index_and_source_changed_together_still_fail_closed(self):
        """The old design re-read hashes from the mutable index, so editing both passed. The pin defeats that."""
        pin = R.load_pin(self.home)
        src = self.repo / "Veyro_Technical_System_Design_x.docx"
        src.write_bytes(b"tampered")
        idx = self.repo / "PROJECT_INDEX.md"
        idx.write_text(idx.read_text().replace(hashlib.sha256(b"Veyro_Technical_System_Design_x.docx").hexdigest(),
                                                hashlib.sha256(b"tampered").hexdigest()))
        res = R.verify_baseline(self.repo, pin)
        self.assertFalse(res["ok"])
        self.assertFalse(res["index"]["match"])
        self.assertFalse(next(s for s in res["sources"] if s["name"].startswith("Veyro_Technical"))["match"])

    def test_symlink_rejected(self):
        (self.repo / "veyro-product-experience-design" / "ln").symlink_to(self.repo / "PROJECT_INDEX.md")
        self.assertFalse(R.verify_baseline(self.repo, R.load_pin(self.home))["ok"])

    def test_symlinked_directory_rejected(self):
        (self.repo / "veyro-product-experience-design" / "linked-dir").symlink_to(self.repo, target_is_directory=True)
        self.assertFalse(R.verify_baseline(self.repo, R.load_pin(self.home))["ok"])

    def test_pin_bootstrap_is_guarded_and_never_rebinds(self):
        (self.home / "baseline-pin.json").chmod(0o600)
        (self.home / "baseline-pin.json").unlink()
        with self.assertRaises(R.PinError):  # wrong confirmation hash
            R.bootstrap_pin(self.cfg, "0" * 64)
        (self.repo / "Gym_OS_Master_Product_Blueprint_v1.docx").write_bytes(b"drifted")
        with self.assertRaises(R.PinError):  # source disagrees with what the index declares
            R.bootstrap_pin(self.cfg, index_sha(self.repo))
        self.assertIsNone(R.load_pin(self.home))
        (self.repo / "Gym_OS_Master_Product_Blueprint_v1.docx").write_bytes(b"Gym_OS_Master_Product_Blueprint_v1.docx")
        R.bootstrap_pin(self.cfg, index_sha(self.repo))
        with self.assertRaises(R.PinError):  # second bootstrap refuses
            R.bootstrap_pin(self.cfg, index_sha(self.repo))
        self.assertEqual(oct((self.home / "baseline-pin.json").stat().st_mode & 0o777), "0o400")

    def test_real_repo_index_matches_its_sources_when_present(self):
        if not (R.REPO / "PROJECT_INDEX.md").exists():
            self.skipTest("no real index")
        with tempfile.TemporaryDirectory() as h:
            pin = R.bootstrap_pin(R.Config(home=h, repo=R.REPO), index_sha(R.REPO))
            self.assertTrue(R.verify_baseline(R.REPO, pin)["ok"])

    def test_mismatch_blocks_dispatch_and_recovery_resumes(self):
        r = self.runner()
        t = self.add(r)
        src = self.repo / "Veyro_Technical_System_Design_x.docx"
        src.write_bytes(b"tampered")
        r.tick()
        self.assertEqual(r.state["health"]["code"], "BASELINE_MISMATCH")
        self.assertEqual((t["status"], t["attempts"]), ("QUEUED", 0))
        src.write_bytes(b"Veyro_Technical_System_Design_x.docx")
        git(self.repo, "checkout", "--", ".")
        r.tick()
        r.tick()
        self.assertEqual(t["status"], "DONE")

    def test_health_is_unknown_not_ok_before_any_check(self):
        self.assertEqual(R.Store(self.home).load()["health"]["status"], "UNKNOWN")
        self.assertEqual(R.snapshot(self.cfg)["health"]["status"], "UNKNOWN")


class Dispatch(Base):
    def test_sonnet_implement_done_with_real_change_and_persisted_evidence(self):
        r = self.runner()
        t = self.add(r)
        r.tick()
        self.assertEqual(t["status"], "DONE", t.get("last_error"))
        self.assertEqual((self.repo / "out" / "a.txt").read_text(), "hi")
        self.assertEqual(t["route"]["verdict"], "VERIFIED")
        self.assertTrue(t["route"]["mr_id"].startswith("MR-MOD-000-"))
        ev = t["evidence"]
        self.assertEqual([c["path"] for c in ev["changed"]], ["out/a.txt"])
        self.assertEqual(ev["changed"][0]["sha256"], hashlib.sha256(b"hi").hexdigest())
        disk = json.loads((self.home / "runs" / "t1-1.evidence.json").read_text())
        self.assertEqual(disk["changed"], ev["changed"])
        self.assertEqual(r.state["usage"]["claude-sonnet-5-5"]["output"], 20)

    def test_exit_zero_with_no_change_is_not_done(self):
        r = self.runner()
        t = self.add(r, prompt="nothing=here")
        r.tick()
        self.assertEqual((t["status"], t["blocked_reason"]), ("BLOCKED", "NO_DELIVERABLE_CHANGE"))

    def test_out_of_scope_change_blocks(self):
        r = self.runner()
        t = self.add(r, prompt="WRITE=out/a.txt\nWRITE2=src/other.txt")
        r.tick()
        self.assertEqual((t["status"], t["blocked_reason"]), ("BLOCKED", "OUT_OF_SCOPE_CHANGE"))
        self.assertIn("src/other.txt", t["last_error"])

    def test_tracked_file_edit_outside_scope_blocks_even_if_already_dirty(self):
        (self.repo / "src" / "keep.txt").write_text("dirty before")  # pre-existing local edit
        r = self.runner()
        t = self.add(r, prompt="WRITE=out/a.txt\nWRITE2=src/keep.txt")
        r.tick()
        self.assertEqual(t["blocked_reason"], "OUT_OF_SCOPE_CHANGE")

    def test_preexisting_dirty_file_untouched_by_child_is_not_blamed(self):
        (self.repo / "src" / "keep.txt").write_text("dirty before")
        r = self.runner()
        t = self.add(r)
        r.tick()
        self.assertEqual(t["status"], "DONE")
        self.assertEqual([c["path"] for c in t["evidence"]["changed"]], ["out/a.txt"])

    def test_child_commit_is_caught_even_without_the_sandbox(self):
        r = self.runner(sandbox="off")
        t = self.add(r, prompt="WRITE=out/a.txt\nCOMMIT=1")
        r.tick()
        self.assertEqual(t["blocked_reason"], "HEAD_MOVED")

    @unittest.skipUnless(sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists(), "needs sandbox-exec")
    def test_sandbox_stops_child_commit(self):
        head = git(self.repo, "rev-parse", "HEAD").stdout
        r = self.runner(max_attempts=1)
        t = self.add(r, prompt="WRITE=out/a.txt\nCOMMIT=1")
        r.tick()
        self.assertNotEqual(t["status"], "DONE")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").stdout, head)

    def test_partial_edits_of_an_interrupted_attempt_stay_attributed(self):
        r = self.runner()
        t = self.add(r, prompt="WRITE=out/a.txt\nWRITE2=src/leak.txt")
        r.dispatch(t)
        self.assertEqual(t["blocked_reason"], "OUT_OF_SCOPE_CHANGE")
        # simulate an interrupted first attempt that leaked a file, then a clean second attempt
        t2 = self.add(r, id="t2", prompt="WRITE=out/b.txt", allowed_paths=["out/"], expected_changes=["out/b.txt"])
        base = r.task_base_state(t2)
        (self.repo / "src" / "partial.txt").write_text("left by killed attempt")
        t2["prompt"] = "WRITE=out/b.txt"
        r.dispatch(t2)
        self.assertEqual((t2["status"], t2["blocked_reason"]), ("BLOCKED", "OUT_OF_SCOPE_CHANGE"))
        self.assertIn("src/partial.txt", t2["last_error"])
        self.assertNotIn("src/partial.txt", base["files"])

    def test_baseline_tampered_during_child_blocks_done(self):
        r = self.runner(baseline_every=1000)  # only the post-run check can see it
        t = self.add(r, prompt="WRITE=out/a.txt\nTAMPER=Veyro_Technical_System_Design_x.docx")
        r.tick()
        self.assertEqual(t["status"], "BLOCKED")
        self.assertEqual(t["blocked_reason"], "POST_RUN_BASELINE_MISMATCH")
        self.assertEqual(r.state["health"]["code"], "BASELINE_MISMATCH")

    def test_verify_cmd_runs_externally_and_gates_done(self):
        ok = [sys.executable, "-c", "import sys,pathlib; sys.exit(0 if pathlib.Path('out/a.txt').read_text()=='hi' else 1)"]
        r = self.runner()
        t = self.add(r, verify_cmd=ok)
        r.tick()
        self.assertEqual((t["status"], t["evidence"]["verify"]["exit"]), ("DONE", 0))
        bad = [sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"]
        t2 = self.add(r, id="t2", prompt="WRITE=out/b.txt", allowed_paths=["out/"], expected_changes=["out/b.txt"],
                      verify_cmd=bad)
        r.tick()
        self.assertEqual((t2["status"], t2["blocked_reason"]), ("BLOCKED", "VERIFICATION_FAILED"))
        self.assertIn("boom", t2["evidence"]["verify"]["tail"])

    def test_verify_only_task_without_expected_change_list(self):
        r = self.runner()
        t = self.add(r, expected_changes=[], verify_cmd=[sys.executable, "-c", "pass"])
        r.tick()
        self.assertEqual(t["status"], "DONE")

    def test_verify_command_pass_without_a_change_is_not_done(self):
        r = self.runner()
        t = self.add(r, prompt="nothing=here", expected_changes=[],
                     verify_cmd=[sys.executable, "-c", "pass"])
        r.tick()
        self.assertEqual((t["status"], t["blocked_reason"]), ("BLOCKED", "NO_DELIVERABLE_CHANGE"))

    def test_result_subtype_and_permission_denials_gate_done(self):
        r = self.runner()
        t = self.add(r, id="a", prompt="WRITE=out/a.txt\nSUBTYPE=error_max_turns")
        r.tick()
        self.assertEqual(t["blocked_reason"], "RESULT_NOT_SUCCESS")
        t = self.add(r, id="b", prompt="WRITE=out/a.txt\nDENIALS=1")
        r.tick()
        self.assertEqual(t["blocked_reason"], "PERMISSION_DENIED")
        t = self.add(r, id="c", prompt="WRITE=out/a.txt\nNODENIALKEY=1")
        r.tick()
        self.assertEqual(t["blocked_reason"], "PERMISSION_DENIALS_UNVERIFIED")

    def test_validation_refuses_tasks_that_could_only_finish_on_prose(self):
        base = {"id": "x", "module": "MOD-000", "role": "implement", "prompt": "p"}
        for bad in ({}, {"allowed_paths": ["out/"]}, {"expected_changes": ["out/a"]},
                    {"allowed_paths": ["out/"], "expected_changes": ["elsewhere/a"]},
                    {"allowed_paths": ["../x"], "verify_cmd": ["true"]}, {"allowed_paths": ["/etc/"], "verify_cmd": ["true"]},
                    {"allowed_paths": [".git/"], "verify_cmd": ["true"]},
                    {"allowed_paths": ["PROJECT_INDEX.md"], "verify_cmd": ["true"]},
                    {"allowed_paths": ["out/"], "verify_cmd": "pytest -q"},
                    {"allowed_paths": ["out/"], "expected_changes": ["out/*.txt"]}):
            with self.assertRaises(ValueError, msg=str(bad)):
                R.enqueue(self.cfg, base | bad)
        with self.assertRaises(ValueError):  # review roles are read-only
            R.enqueue(self.cfg, base | {"role": "code-review", "allowed_paths": ["out/"]})

    # ---- model assurance applies to every role
    def test_opus_role_never_passes_on_sonnet_fallback(self):
        r = self.runner()
        t = self.add(r, role="code-review", prompt="MODEL=claude-sonnet-5-5\nBIG=1\nOUTCOME_LINE=APPROVED")
        r.tick()
        self.assertEqual((t["status"], t["blocked_reason"]), ("BLOCKED", "MODEL_ASSURANCE_UNVERIFIED"))
        self.assertEqual(t["route"]["verdict"], "MISMATCH")

    def test_mixed_usage_through_real_cli_shape_blocks_opus_role(self):
        r = self.runner()
        t = self.add(r, role="security", prompt="BIG=1\nMODEL2=claude-sonnet-5-5\nTOK2=2000\nOUTCOME_LINE=APPROVED")
        r.tick()
        self.assertEqual((t["status"], t["route"]["verdict"]), ("BLOCKED", "MISMATCH"))

    def test_opus_role_without_model_evidence_is_blocked_not_passed(self):
        r = self.runner()
        t = self.add(r, role="gatekeeper", prompt="NOUSAGE=1\nOUTCOME_LINE=APPROVED")
        r.tick()
        self.assertEqual((t["status"], t["route"]["verdict"]), ("BLOCKED", "UNVERIFIED"))

    def test_sonnet_role_unverified_or_mismatched_is_blocked_too(self):
        r = self.runner()
        t = self.add(r, prompt="WRITE=out/a.txt\nNOUSAGE=1")
        r.tick()
        self.assertEqual((t["status"], t["route"]["verdict"], t["blocked_reason"]),
                         ("BLOCKED", "UNVERIFIED", "MODEL_ASSURANCE_UNVERIFIED"))
        t = self.add(r, id="t2", prompt="WRITE=out/a.txt\nMODEL=claude-opus-5-5\nBIG=1")
        r.tick()
        self.assertEqual((t["status"], t["route"]["verdict"]), ("BLOCKED", "MISMATCH"))

    # ---- review outcome
    def test_review_done_only_with_explicit_approved_outcome(self):
        r = self.runner()
        t = self.add(r, role="security", prompt="BIG=1\nOUTCOME_LINE=APPROVED")
        r.tick()
        self.assertEqual((t["status"], t["route"]["verdict"], t["evidence"]["review_outcome"]), ("DONE", "VERIFIED", "APPROVED"))

    def test_review_without_or_with_negative_outcome_is_blocked(self):
        r = self.runner()
        t = self.add(r, id="a", role="security", prompt="BIG=1")
        r.tick()
        self.assertEqual(t["blocked_reason"], "NO_REVIEW_OUTCOME")
        t = self.add(r, id="b", role="security", prompt="BIG=1\nOUTCOME_LINE=CHANGES_REQUESTED")
        r.tick()
        self.assertEqual(t["blocked_reason"], "REVIEW_CHANGES_REQUESTED")

    def test_review_that_writes_a_file_is_blocked(self):
        r = self.runner()
        t = self.add(r, role="code-review", prompt="BIG=1\nWRITE=src/new.txt\nOUTCOME_LINE=APPROVED")
        r.tick()
        self.assertEqual(t["blocked_reason"], "OUT_OF_SCOPE_CHANGE")

    # ---- retries
    def test_bounded_retry_with_backoff_then_success(self):
        r = self.runner(backoff_base=100)
        ctr = Path(self.tmp.name) / "ctr"
        t = self.add(r, prompt=f"WRITE=out/a.txt\nFAIL_UNTIL=1\nCOUNTER={ctr}")
        r.tick()
        self.assertEqual((t["status"], t["attempts"]), ("QUEUED", 1))
        self.assertGreater(t["next_attempt_at"], time.time() + 50)
        r.tick()  # still backing off: no new attempt
        self.assertEqual(t["attempts"], 1)
        t["next_attempt_at"] = 0
        r.tick()
        self.assertEqual((t["status"], t["attempts"]), ("DONE", 2))
        self.assertEqual(R.backoff(self.cfg, 3), 300)  # 100*4 capped at 300

    def test_retries_exhaust_to_failed(self):
        r = self.runner()
        ctr = Path(self.tmp.name) / "ctr"
        t = self.add(r, prompt=f"FAIL_UNTIL=99\nCOUNTER={ctr}")
        for _ in range(6):
            t["next_attempt_at"] = 0
            r.tick()
        self.assertEqual((t["status"], t["attempts"]), ("FAILED", 3))
        self.assertIn("simulated overload", t["last_error"])

    def test_missing_claude_binary_is_bounded_failure(self):
        r = self.runner(claude_bin="/nonexistent/claude")
        t = self.add(r)
        for _ in range(5):
            t["next_attempt_at"] = 0
            r.tick()
        self.assertEqual(t["status"], "FAILED")

    def test_timeout_kills_child(self):
        r = self.runner(timeout=0.5, max_attempts=1)
        pidfile = Path(self.tmp.name) / "pid"
        t = self.add(r, prompt=f"SLEEP=30\nPIDFILE={pidfile}")
        r.tick()
        self.assertEqual(t["status"], "FAILED")
        self.assertIn("timeout", t["last_error"])
        time.sleep(0.3)
        with self.assertRaises(OSError):
            os.kill(int(pidfile.read_text()), 0)

    def test_every_dispatch_has_operation_id(self):
        r = self.runner()
        self.add(r)
        r.tick()
        ev = [e for e in r.store.tail_events(50) if e["kind"] in ("dispatch", "task-done")]
        self.assertTrue(ev and all(e["op_id"] == "t1:1" for e in ev))


class Isolation(Base):
    def run_probe(self, **kw):
        r = self.runner(**kw)
        argsfile = Path(self.tmp.name) / "args.json"
        t = self.add(r, prompt=f"WRITE=out/a.txt\nARGSFILE={argsfile}")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "EXAMPLE_NOT_A_REAL_KEY", "VEYRO_RUNNER_HOME": "/x"}):
            r.tick()
        return t, json.loads(argsfile.read_text())

    def test_child_gets_explicit_minimal_settings_and_clean_env(self):
        t, seen = self.run_probe()
        args = seen["args"]
        self.assertEqual(t["status"], "DONE", t.get("last_error"))
        for want in ("--safe-mode", "--setting-sources=", "--permission-mode=dontAsk", "--permission-prompts=none",
                     "--strict-mcp-config", "--tools=Read,Grep,Glob,Edit,Write"):
            self.assertIn(want, args)
        self.assertFalse([a for a in args if "bypass" in a.lower() or "skip-permissions" in a])
        sett = Path(next(a for a in args if a.startswith("--settings=")).split("=", 1)[1])
        self.assertTrue(str(sett).startswith(str(self.home)))  # outside the repo
        cfg = json.loads(sett.read_text())["permissions"]
        self.assertEqual(cfg["defaultMode"], "dontAsk")
        self.assertIn("Edit(out/**)", cfg["allow"])
        self.assertIn("Bash", cfg["deny"])
        self.assertFalse([a for a in cfg["allow"] if "npx" in a or "claude-flow" in a])
        self.assertNotIn("ANTHROPIC_API_KEY", seen["env"])
        self.assertNotIn("VEYRO_RUNNER_HOME", seen["env"])
        self.assertEqual(Path(seen["cwd"]).resolve(), self.repo)

    def test_review_child_is_read_only_toolset(self):
        r = self.runner()
        argsfile = Path(self.tmp.name) / "args.json"
        self.add(r, role="code-review", prompt=f"BIG=1\nOUTCOME_LINE=APPROVED\nARGSFILE={argsfile}")
        r.tick()
        args = json.loads(argsfile.read_text())["args"]
        self.assertIn("--tools=Read,Grep,Glob", args)
        self.assertNotIn("--tools=Read,Grep,Glob,Edit,Write", args)

    @unittest.skipUnless(sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists(), "needs sandbox-exec")
    def test_sandbox_denies_child_writes_to_runner_state(self):
        r = self.runner()
        log = Path(self.tmp.name) / "escape.log"
        t = self.add(r, prompt=f"WRITE=out/a.txt\nWRITE_ABS={self.home}/queue/evil.json\nESCAPE_LOG={log}")
        r.tick()
        self.assertEqual(log.read_text(), "denied")
        self.assertFalse((self.home / "queue" / "evil.json").exists())
        self.assertEqual((t["status"], t["evidence"]["isolation"]["sandbox"]), ("DONE", "sandbox-exec"))

    def test_unsandboxed_run_is_recorded_as_such(self):
        r = self.runner(sandbox="off")
        log = Path(self.tmp.name) / "escape.log"
        t = self.add(r, prompt=f"WRITE=out/a.txt\nWRITE_ABS={self.home}/queue/evil.json\nESCAPE_LOG={log}")
        r.tick()
        self.assertEqual(t["evidence"]["isolation"]["sandbox"], "none")  # honest: nothing stopped the write
        self.assertEqual(log.read_text(), "wrote")


class Control(Base):
    def test_pause_blocks_dispatch_resume_continues_duplicate_op_ignored(self):
        r = self.runner()
        t = self.add(r)
        R.send_command(self.cfg, "pause", "op-pause-1")
        r.tick()
        self.assertEqual((r.state["control"], t["status"]), ("PAUSE", "QUEUED"))
        R.send_command(self.cfg, "resume", "op-res-1")
        R.send_command(self.cfg, "pause", "op-pause-1")  # replayed op id
        r.tick()
        self.assertEqual((r.state["control"], t["status"]), ("RUN", "DONE"))
        self.assertTrue(any(e["kind"] == "command-duplicate" for e in r.store.tail_events(50)))

    def test_invalid_command_rejected_not_applied(self):
        r = self.runner()
        (self.home / "commands" / "0-bad.json").write_text('{"cmd":"rm -rf","op_id":"x"}')
        r.apply_commands()
        self.assertEqual(r.state["control"], "RUN")
        self.assertTrue((self.home / "commands" / "0-bad.rejected").exists())

    def test_enqueue_validation(self):
        for bad in ({"id": "../x", "module": "MOD-000", "role": "implement", "prompt": "p"},
                    {"id": "a", "module": "mod0", "role": "implement", "prompt": "p"},
                    {"id": "a", "module": "MOD-000", "role": "root", "prompt": "p"},
                    {"id": "a", "module": "MOD-000", "role": "implement", "prompt": " "}):
            with self.assertRaises(ValueError):
                R.enqueue(self.cfg, bad)
        r = self.runner()
        self.add(r)
        r.store.save(r.state)
        with self.assertRaises(ValueError):  # duplicate id
            R.enqueue(self.cfg, {"id": "t1", "module": "MOD-000", "role": "review", "prompt": "p"})

    def test_second_runner_refused_and_writer_lock_serialises(self):
        r1 = R.Runner(self.cfg)
        self.assertTrue(r1.rlock.acquire({"pid": 1}))
        self.assertEqual(R.Runner(self.cfg).run(), R.EXIT_LOCKED)
        r1.rlock.release()
        r = self.runner()
        t = self.add(r)
        other = R.FileLock(R.writer_lock_path(self.home, self.repo))
        self.assertTrue(other.acquire({"pid": 2}))
        r.tick()
        self.assertEqual((t["status"], t["attempts"]), ("QUEUED", 0))
        other.release()
        r.tick()
        self.assertEqual(t["status"], "DONE")

    def test_corrupt_state_fails_closed_without_overwrite(self):
        R.Store(self.home)
        (self.home / "state.json").write_text("{broken")
        self.assertEqual(R.Runner(self.cfg).run(), R.EXIT_CORRUPT)
        self.assertEqual((self.home / "state.json").read_text(), "{broken")
        (self.home / "state.json").write_text('{"schema": 99, "tasks": {}}')  # wrong schema is also corrupt
        self.assertEqual(R.Runner(self.cfg).run(), R.EXIT_CORRUPT)


class QueueDurability(Base):
    def test_queue_file_survives_a_crash_before_state_is_persisted(self):
        r = self.runner()
        R.enqueue(self.cfg, {"id": "q1", "module": "MOD-000", "role": "implement", "prompt": "WRITE=out/a.txt",
                             "allowed_paths": ["out/"], "expected_changes": ["out/a.txt"]})
        qfile = next((self.home / "queue").glob("*.json"))
        with mock.patch.object(r.store, "save", side_effect=OSError("disk full / crash")):
            with self.assertRaises(OSError):
                r.ingest_queue()
        self.assertTrue(qfile.exists())  # not consumed: nothing lost
        self.assertNotIn("q1", R.Store(self.home).load()["tasks"])
        r2 = self.runner()  # next runner picks it up
        r2.ingest_queue()
        self.assertFalse(qfile.exists())
        self.assertIn("q1", R.Store(self.home).load()["tasks"])  # persisted before unlink

    def test_crash_after_persist_before_unlink_does_not_duplicate(self):
        r = self.runner()
        R.enqueue(self.cfg, {"id": "q1", "module": "MOD-000", "role": "implement", "prompt": "WRITE=out/a.txt",
                             "allowed_paths": ["out/"], "expected_changes": ["out/a.txt"]})
        with mock.patch.object(Path, "unlink", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                r.ingest_queue()
        self.assertEqual(len(list((self.home / "queue").glob("*.json"))), 1)
        r2 = self.runner()
        r2.ingest_queue()
        self.assertEqual(list(r2.state["tasks"]), ["q1"])
        self.assertEqual(len(list((self.home / "queue").glob("*.json"))), 0)


class Lifecycle(Base):
    """Real runner processes: end-to-end smoke, stop/resume, crash recovery."""

    def spawn(self):
        return subprocess.Popen([sys.executable, str(HERE.parent / "runner.py"), "--home", str(self.home),
                                 "--repo", str(self.repo), "--claude-bin", str(self.bin), "--tick", "0.1", "run"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def cli(self, *a):
        return subprocess.run([sys.executable, str(HERE.parent / "runner.py"), "--home", str(self.home),
                               "--repo", str(self.repo), *a], capture_output=True, text=True)

    def wait(self, pred, secs=15):
        end = time.time() + secs
        while time.time() < end:
            s = R.snapshot(self.cfg)
            if pred(s):
                return s
            time.sleep(0.1)
        self.fail(f"condition not reached; last snapshot: {json.dumps(R.snapshot(self.cfg))[:800]}")

    def test_smoke_stop_resume_and_status(self):
        p = self.spawn()
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.wait(lambda s: s["runner_alive"])
        self.assertEqual(self.cli("run").returncode, R.EXIT_LOCKED)  # a second live runner must be refused
        Path(self.tmp.name, "prompt.txt").write_text("WRITE=out/s.txt")
        self.assertEqual(self.cli("enqueue", "--id", "s1", "--module", "MOD-000", "--role", "implement",
                                  "--allow", "out/", "--expect", "out/s.txt", "--plan-phase", "P1",
                                  "--prompt-file", str(Path(self.tmp.name, "prompt.txt"))).returncode, 0)
        s = self.wait(lambda s: any(t["status"] == "DONE" for t in s["tasks"]))
        self.assertEqual(s["tasks"][0]["plan_phase"], "P1")
        self.assertEqual(json.loads(self.cli("status").stdout)["control"], "RUN")
        self.cli("stop")
        self.assertEqual(p.wait(timeout=10), 0)
        self.assertEqual(R.snapshot(self.cfg)["control"], "STOP")
        self.assertEqual(self.cli("run").returncode, 0)  # persisted STOP: exits immediately
        self.cli("resume")
        p = self.spawn()
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.wait(lambda s: s["runner_alive"] and s["control"] == "RUN")
        os.kill(p.pid, signal.SIGTERM)
        self.assertEqual(p.wait(timeout=10), 0)

    def test_heartbeat_is_persisted_during_child_and_verification(self):
        r = self.runner()
        pidfile = Path(self.tmp.name) / "child.pid"
        self.add(r, prompt=f"SLEEP=5\nPIDFILE={pidfile}\nWRITE=out/a.txt")
        p = self.spawn()
        self.addCleanup(lambda: p.poll() is None and p.kill())
        first = self.wait(lambda s: s["tasks"] and s["tasks"][0]["status"] == "RUNNING" and pidfile.exists())
        old = first["runner"]["heartbeat_at"]
        advanced = self.wait(lambda s: s["runner"]["heartbeat_at"] != old, secs=4)
        self.assertTrue(advanced["runner_alive"])
        self.wait(lambda s: s["tasks"][0]["status"] == "DONE", secs=8)
        self.cli("stop")
        self.assertEqual(p.wait(timeout=10), 0)
        r = self.runner()
        r.state["control"] = "RUN"
        r.state["runner"]["heartbeat_at"] = "2000-01-01T00:00:00+00:00"
        r.last_hb = time.time()
        r.store.save(r.state)
        out = r.run_verify({"verify_cmd": [sys.executable, "-c", "import time; time.sleep(3)"]})
        self.assertEqual(out["exit"], 0)
        self.assertNotEqual(r.store.load()["runner"]["heartbeat_at"], "2000-01-01T00:00:00+00:00")

    def _check_verification_interruption(self, by_stop):
        marker = Path(self.tmp.name) / "verify-started"
        counter = Path(self.tmp.name) / "child-count"
        verify = [sys.executable, "-c", f"from pathlib import Path; import time; p=Path({str(marker)!r}); "
                  "p.exists() or (p.write_text('1'), time.sleep(60))"]
        r = self.runner()
        self.add(r, prompt=f"COUNTER={counter}\nFAIL_UNTIL=0\nWRITE=out/a.txt", verify_cmd=verify)
        p = self.spawn()
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.wait(lambda s: s["tasks"] and s["tasks"][0].get("stage") == "verifying" and marker.exists())
        if by_stop:
            self.cli("stop")
        else:
            os.kill(p.pid, signal.SIGTERM)
        self.assertEqual(p.wait(timeout=12), 0)
        paused = R.snapshot(self.cfg)["tasks"][0]
        self.assertEqual((paused["status"], paused["stage"], paused["attempts"]),
                         ("QUEUED", "verify_pending", 1))
        self.assertEqual(counter.read_text(), "1")
        if by_stop:
            self.cli("resume")
        p = self.spawn()
        self.addCleanup(lambda: p.poll() is None and p.kill())
        done = self.wait(lambda s: s["tasks"][0]["status"] == "DONE", secs=10)["tasks"][0]
        self.assertEqual(done["attempts"], 1)
        self.assertEqual(counter.read_text(), "1")  # completed Claude edit was not re-dispatched
        self.cli("stop")
        self.assertEqual(p.wait(timeout=10), 0)

    def test_stop_during_verification_resumes_checkpoint(self):
        self._check_verification_interruption(by_stop=True)

    def test_sigterm_during_verification_resumes_checkpoint(self):
        self._check_verification_interruption(by_stop=False)

    def test_crash_during_verification_reaps_orphan_and_resumes(self):
        marker = Path(self.tmp.name) / "verify-started"
        counter = Path(self.tmp.name) / "child-count"
        verify = [sys.executable, "-c", f"from pathlib import Path; import time; p=Path({str(marker)!r}); "
                  "p.exists() or (p.write_text('1'), time.sleep(60))"]
        r = self.runner()
        self.add(r, prompt=f"COUNTER={counter}\nFAIL_UNTIL=0\nWRITE=out/a.txt", verify_cmd=verify)
        p = self.spawn()
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.wait(lambda s: s["tasks"] and s["tasks"][0].get("stage") == "verifying" and marker.exists()
                  and R.Store(self.home).load()["tasks"]["t1"].get("verify_child"))
        os.kill(p.pid, signal.SIGKILL)
        p.wait()
        self.assertEqual(R.FileLock.probe(R.writer_lock_path(self.home, self.repo)), "held")
        p = self.spawn()
        self.addCleanup(lambda: p.poll() is None and p.kill())
        done = self.wait(lambda s: s["tasks"][0]["status"] == "DONE", secs=15)["tasks"][0]
        self.assertEqual(done["attempts"], 1)
        self.assertEqual(counter.read_text(), "1")
        self.cli("stop")
        self.assertEqual(p.wait(timeout=10), 0)

    def test_pin_baseline_cli_is_two_step_and_guarded(self):
        (self.home / "baseline-pin.json").chmod(0o600)
        (self.home / "baseline-pin.json").unlink()
        first = self.cli("pin-baseline")
        self.assertEqual(first.returncode, 2)
        self.assertIn(index_sha(self.repo), first.stderr)
        self.assertIsNone(R.load_pin(self.home))
        self.assertEqual(self.cli("pin-baseline", "--confirm-index-sha256", index_sha(self.repo)).returncode, 0)
        self.assertEqual(self.cli("pin-baseline", "--confirm-index-sha256", index_sha(self.repo)).returncode, 2)
        self.assertEqual(self.cli("verify-baseline").returncode, 0)

    def test_crash_recovery_orphan_keeps_writer_lock_until_reaped(self):
        pidfile = Path(self.tmp.name) / "child.pid"
        lock = R.writer_lock_path(self.home, self.repo)
        p = self.spawn()
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.wait(lambda s: s["runner_alive"])
        R.enqueue(self.cfg, {"id": "c1", "module": "MOD-000", "role": "implement", "prompt": f"SLEEP=60\nPIDFILE={pidfile}",
                             "allowed_paths": ["out/"], "expected_changes": ["out/a.txt"]})
        self.wait(lambda s: any(t["status"] == "RUNNING" for t in s["tasks"]) and pidfile.exists())
        child = int(pidfile.read_text())
        os.kill(p.pid, signal.SIGKILL)  # hard crash: no cleanup runs
        p.wait()
        os.kill(child, 0)  # orphan still alive (it could still be writing to the repo)
        self.assertEqual(R.FileLock.probe(lock), "held")  # ...and it still holds the writer lock via the inherited fd
        wl = R.snapshot(self.cfg)["writer_lock"]
        self.assertEqual((wl["state"], wl["runner_alive"], wl["child_alive"]), ("held", False, True))
        r = R.Runner(self.cfg)
        r.state = r.store.load()
        self.assertEqual(r.state["tasks"]["c1"]["status"], "RUNNING")
        r.state["runner"] = {"pid": os.getpid(), "heartbeat_at": R.now_iso()}
        r.recover()
        t = r.state["tasks"]["c1"]
        self.assertEqual((t["status"], t["attempts"], r.state["recoveries"]), ("QUEUED", 1, 1))
        time.sleep(0.3)
        with self.assertRaises(OSError):
            os.kill(child, 0)
        self.assertEqual(R.FileLock.probe(lock), "free")  # lock released only once the orphan is gone
        r.recover()  # second pass changes nothing
        self.assertEqual((t["status"], t["attempts"], r.state["recoveries"]), ("QUEUED", 1, 1))


class DashboardTests(Base):
    def setUp(self):
        super().setUp()
        self.srv = dashboard.make_server(self.cfg, 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def req(self, path, method="GET", host=None):
        rq = urllib.request.Request(self.base + path, method=method, data=b"x" if method != "GET" else None)
        if host:
            rq.add_header("Host", host)
        try:
            with urllib.request.urlopen(rq) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_loopback_only_and_truthful_empty_state(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")
        code, body = self.req("/api/state")
        s = json.loads(body)
        self.assertEqual(code, 200)
        self.assertFalse(s["runner_alive"])
        self.assertEqual((s["tasks"], s["usage"], s["ci"]), ([], {}, None))
        self.assertEqual(s["health"]["status"], "UNKNOWN")  # never a fabricated "OK" before a runner checked
        self.assertIsNone(s["baseline"])
        self.assertEqual(s["writer_lock"]["state"], "free")

    def test_read_only_and_host_guard(self):
        for m in ("POST", "PUT", "DELETE", "PATCH"):
            self.assertEqual(self.req("/api/state", m)[0], 405)
        self.assertEqual(self.req("/api/state", host="evil.example")[0], 403)
        self.assertEqual(self.req("/nope")[0], 404)
        code, html = self.req("/")
        self.assertIn("Veyro Mission Runner", html)
        self.assertEqual(self.req("/app.js")[0], 200)
        self.assertEqual(dashboard.make_server.__defaults__, (8766,))

    def test_kanban_columns_are_the_requested_six(self):
        js = self.req("/app.js")[1]
        cols = ["NOT STARTED", "READY", "IN PROGRESS", "IN REVIEW", "BLOCKED", "DONE"]
        pos = [js.index(f"'{c}'") for c in cols]
        self.assertEqual(pos, sorted(pos))

    def test_dashboard_reflects_live_state_and_never_mutates_it(self):
        r = self.runner()
        self.add(r)
        r.tick()
        r.store.save(r.state)
        before = (self.home / "state.json").read_bytes()
        s = json.loads(self.req("/api/state")[1])
        self.assertEqual(s["tasks"][0]["status"], "DONE")
        self.assertTrue(s["runner_alive"])
        self.assertEqual(s["baseline_pin"]["sources"], 4)
        self.assertEqual((self.home / "state.json").read_bytes(), before)


class CIFeed(Base):
    """gh is injected as the subprocess layer; nothing here touches the network."""
    SHA = "a" * 40

    def fake_gh(self, fail=None, calls=None):
        def run(argv, **kw):
            if calls is not None:
                calls.append((argv, kw))
            a = " ".join(argv[1:3])
            if fail == "missing":
                raise FileNotFoundError(argv[0])
            if fail == "timeout":
                raise subprocess.TimeoutExpired(argv, 1)
            if fail == "auth":
                return subprocess.CompletedProcess(argv, 1, "", "gh auth login required SECRET-TOKEN-xyz")
            if fail == "no-pr" and a == "pr view":
                return subprocess.CompletedProcess(argv, 1, "", 'no pull requests found for branch "token-login"')
            if fail == "no-checks" and a == "pr checks":
                return subprocess.CompletedProcess(argv, 1, "", "no required checks reported on this branch")
            if fail == "rate" and a == "pr view":
                return subprocess.CompletedProcess(argv, 1, "", "HTTP 403 rate limit exceeded")
            out = {"repo view": {"nameWithOwner": "o/r", "url": "https://github.com/o/r", "extra": "leak"},
                   "run list": [{"name": "CI", "status": "completed", "conclusion": "success", "headBranch": "b",
                                 "headSha": self.SHA, "event": "push", "createdAt": "2026-01-01T00:00:00Z",
                                 "url": "https://github.com/o/r/actions/runs/1", "token": "leak"},
                                {"name": "Bad", "status": "completed", "conclusion": "success", "headBranch": "b",
                                 "headSha": self.SHA, "url": "javascript:alert(1)"}],
                   "pr view": {"number": 7, "url": "https://github.com/o/r/pull/7", "state": "OPEN",
                               "reviewDecision": "", "isDraft": False, "headRefOid": self.SHA},
                   "pr checks": [{"name": "Veyro Foundation CI", "state": "SUCCESS", "link": "https://github.com/o/r/runs/2"}]}[a]
            return subprocess.CompletedProcess(argv, 0, json.dumps(out), "")
        return run

    def test_success_snapshot_is_persisted_allowlisted_and_read_only(self):
        r, calls = self.runner(ci_every=60), []
        r.ci_run = self.fake_gh(calls=calls)
        r.refresh_ci()
        ci = dashboard.runner.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["state"], ci["error"], ci["source"], ci["head_sha"]), ("fresh", None, "gh", self.SHA))
        self.assertEqual((ci["pr"]["number"], ci["pr"]["review"], ci["checks"][0]["state"]), (7, "none", "SUCCESS"))
        self.assertEqual(ci["runs"][0]["url"], "https://github.com/o/r/actions/runs/1")
        self.assertIsNone(ci["runs"][1]["url"])  # non-https url dropped
        self.assertNotIn("leak", json.dumps(ci))
        self.assertEqual((ci["staging"], ci["secrets"], ci["rollback"]), ("not configured",) * 3)
        for argv, kw in calls:  # argv list, no shell, bounded, read-only verbs only
            self.assertIsInstance(argv, list)
            self.assertFalse(kw.get("shell"))
            self.assertLessEqual(kw["timeout"], R.CI_CALL_TIMEOUT)
            self.assertIn(argv[1:3], (["repo", "view"], ["run", "list"], ["pr", "view"], ["pr", "checks"]))

    def test_failures_keep_last_success_but_mark_stale_and_leak_nothing(self):
        r = self.runner(ci_every=60)
        r.ci_run = self.fake_gh()
        r.refresh_ci()
        for fail, code in (("missing", "gh-missing"), ("timeout", "gh-timeout"), ("auth", "gh-auth")):
            r.last_ci = 0
            r.ci_run = self.fake_gh(fail=fail)
            r.refresh_ci()
            ci = R.snapshot(self.cfg)["ci"]
            self.assertEqual((ci["state"], ci["error"]), ("stale", code))
            self.assertEqual(ci["head_sha"], self.SHA)  # last observation retained, clearly marked
            self.assertNotIn("SECRET", (self.home / "ci.json").read_text())

    def test_never_succeeded_is_unavailable_and_old_success_goes_stale(self):
        r = self.runner(ci_every=60)
        r.ci_run = self.fake_gh(fail="missing")
        r.refresh_ci()
        ci = R.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["state"], ci["observed_at"], ci["runs"], ci["pr"]), ("unavailable", None, [], None))
        r.last_ci, r.ci_run = 0, self.fake_gh()
        r.refresh_ci()
        d = json.loads((self.home / "ci.json").read_text()) | {"observed_at": "2020-01-01T00:00:00+00:00"}
        (self.home / "ci.json").write_text(json.dumps(d))
        self.assertEqual(R.snapshot(self.cfg)["ci"]["state"], "stale")

    def test_no_pr_and_no_checks_are_absence_but_rate_limit_is_not(self):
        r = self.runner(ci_every=60)
        r.ci_run = self.fake_gh(fail="no-pr")
        r.refresh_ci()
        ci = R.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["state"], ci["pr"], ci["checks"]), ("fresh", None, []))
        r.last_ci, r.ci_run = 0, self.fake_gh(fail="no-checks")
        r.refresh_ci()
        ci = R.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["state"], ci["pr"]["number"], ci["checks"]), ("fresh", 7, []))
        r.last_ci, r.ci_run = 0, self.fake_gh(fail="rate")
        r.refresh_ci()
        ci = R.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["state"], ci["error"]), ("stale", "gh-failed"))

    def test_malformed_ci_cache_lists_do_not_crash_reader_or_runner(self):
        (self.home / "ci.json").write_text(json.dumps({"source": "gh", "checks": 123, "runs": {"bad": 1}}))
        self.assertEqual(R.snapshot(self.cfg)["ci"]["state"], "unavailable")
        r = self.runner(ci_every=60)
        r.ci_run = self.fake_gh(fail="missing")
        r.refresh_ci()
        self.assertEqual(R.snapshot(self.cfg)["ci"]["error"], "gh-missing")

    def test_tick_is_throttled_and_disabled_by_default_in_tests(self):
        r, calls = self.runner(ci_every=60), []
        r.ci_run = self.fake_gh(calls=calls)
        r.tick()
        n = len(calls)
        r.tick()
        self.assertGreater(n, 0)
        self.assertEqual(len(calls), n)  # second tick inside the interval does not call gh again

    def test_dashboard_ci_ui_uses_textcontent_and_not_configured_wording(self):
        js = dashboard.JS
        self.assertIn("function ciView", js)
        self.assertIn("not configured", js)
        self.assertNotIn("innerHTML", js)


if __name__ == "__main__":
    unittest.main()
