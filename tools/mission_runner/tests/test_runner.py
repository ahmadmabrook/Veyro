"""Focused control-plane safety tests. Run: python3 -m unittest discover -s tools/mission_runner/tests -t tools/mission_runner"""
import datetime
import hashlib
import json
import os
import re
import shutil
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
import workflow_check as WC  # noqa: E402

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
                            backoff_base=0, max_attempts=3, baseline_every=0, ci_every=0, ci_mode="gh")
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
    """The read-only dashboard projects module decisions, task lifecycle, and CI separately."""

    def setUp(self):
        super().setUp()
        self.srv = dashboard.make_server(self.cfg, 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def test_worktree_clean_reads_real_git_status(self):
        self.assertTrue(dashboard.worktree_clean(self.repo))
        scratch = self.repo / "scratch.txt"
        scratch.write_text("untracked")
        self.assertFalse(dashboard.worktree_clean(self.repo))
        scratch.unlink()
        tracked = self.repo / "src" / "keep.txt"
        tracked.write_text("modified")
        self.assertFalse(dashboard.worktree_clean(self.repo))

    def req(self, path, method="GET", host=None):
        rq = urllib.request.Request(self.base + path, method=method, data=b"x" if method != "GET" else None)
        if host:
            rq.add_header("Host", host)
        try:
            with urllib.request.urlopen(rq) as r:
                return r.status, dict(r.headers), r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, dict(e.headers), e.read().decode()

    def write_module(self, module, status_line, symlink=False):
        folder = self.repo / "knowledge" / "03-Modules" / module
        folder.mkdir(parents=True, exist_ok=True)
        body = f"# {module} — Test\n\n{status_line}\n\n## Requirements\n- first\n- second\n"
        if symlink:
            (self.repo / "elsewhere.md").write_text(body)
            (folder / f"{module}.md").symlink_to(self.repo / "elsewhere.md")
        else:
            (folder / f"{module}.md").write_text(body)

    def test_loopback_empty_state_and_read_only_routes(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")
        code, _, body = self.req("/api/state")
        state = json.loads(body)
        self.assertEqual(code, 200)
        self.assertFalse(state["runner_alive"])
        self.assertEqual((state["tasks"], state["usage"], state["ci"]), ([], {}, None))
        self.assertEqual(state["health"]["status"], "UNKNOWN")
        self.assertEqual(state["accepted_count"], 0)
        self.assertEqual(state["total_modules"], 75)
        self.assertEqual(state["writer_lock"]["state"], "free")
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            self.assertEqual(self.req("/api/state", method)[0], 405)
        self.assertEqual(self.req("/api/state", host="evil.example")[0], 403)
        self.assertEqual(self.req("/nope")[0], 404)

    def test_fixed_assets_and_security_headers(self):
        code, headers, html = self.req("/")
        self.assertEqual(code, 200)
        self.assertIn("Engineering Mission Control", html)
        self.assertIn('href="/app.css"', html)
        self.assertIn('src="/app.js"', html)
        self.assertEqual(self.req("/app.css")[2], dashboard.CSS)
        self.assertEqual(self.req("/app.js")[2], dashboard.JS)
        self.assertIn("text/css", self.req("/app.css")[1]["Content-Type"])
        for path in ("/", "/app.js", "/app.css", "/api/state"):
            headers = self.req(path)[1]
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertEqual(re.findall(r"<script\b[^>]*>", html), ['<script src="/app.js">'])
        self.assertNotIn("innerHTML", dashboard.JS)
        self.assertNotRegex(dashboard.JS, r"method\s*:\s*['\"](?:POST|PUT|DELETE|PATCH)")
        for path in ("/dashboard.py", "/runner.py", "/module_catalog.json", "/../runner.py", "/.git/config"):
            self.assertEqual(self.req(path)[0], 404)
        self.assertEqual(self.req("/app.js?x=1")[0], 200)
        for view in ("overview", "kanban", "modules", "quality", "activity", "usage"):
            self.assertIn(f'id="{view}"', html)

    def test_live_state_is_projected_without_mutation(self):
        instance = self.runner()
        self.add(instance)
        instance.tick()
        instance.store.save(instance.state)
        before = (self.home / "state.json").read_bytes()
        state = json.loads(self.req("/api/state")[2])
        self.assertEqual(state["tasks"][0]["status"], "DONE")
        self.assertTrue(state["runner_alive"])
        self.assertEqual(state["baseline_pin"]["sources"], 4)
        self.assertEqual((self.home / "state.json").read_bytes(), before)

    def test_module_parser_handles_status_and_rejects_symlinks(self):
        self.write_module("MOD-001", "**Status: PROGRESS — NOT PASS, NOT ACCEPTED.**")
        self.write_module("MOD-000", "**Status: ACCEPTED — LEAN FOUNDATION.** gatekeeper approved")
        records = dashboard.module_records(self.repo)
        self.assertFalse(records["MOD-001"]["accepted"])
        self.assertTrue(records["MOD-000"]["accepted"])
        self.assertEqual(records["MOD-001"]["requirements"], ["first", "second"])
        state = json.loads(self.req("/api/state")[2])
        self.assertEqual(state["recorded_accepted_count"], 1)
        self.assertEqual(state["accepted_count"], 0)
        self.write_module("MOD-002", "**Status: ACCEPTED**", symlink=True)
        self.assertNotIn("MOD-002", dashboard.module_records(self.repo))

    def test_stale_ci_does_not_revoke_recorded_acceptance(self):
        self.write_module("MOD-001", "**Status: ACCEPTED — FOUNDATION ONLY.**")
        cached = {"source": "gh", "scope": "main-push", "branch": "main", "head_sha": "a" * 40,
                  "observed_at": "2000-01-01T00:00:00+00:00", "error": "github-api-timeout", "runs": []}
        (self.home / "ci.json").write_text(json.dumps(cached))
        state = json.loads(self.req("/api/state")[2])
        self.assertTrue(state["module_records"]["MOD-001"]["recorded_accepted"])
        self.assertFalse(state["module_records"]["MOD-001"]["accepted"])
        self.assertEqual(state["recorded_accepted_count"], 1)
        self.assertEqual(state["accepted_count"], 0)
        self.assertEqual(state["ci"]["state"], "stale")

    def test_ci_verdict_requires_fresh_exact_main_push_success(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node unavailable")
        js = dashboard.JS
        fn = js[js.index("function ciVerdict"):js.index("\nlet data=", js.index("function ciVerdict"))]
        run = {"name": "Veyro Foundation CI", "status": "completed", "conclusion": "success", "ref": "main",
               "head_sha": "a" * 40, "event": "push"}
        base = {"scope": "main-push", "branch": "main", "head_sha": "a" * 40, "state": "fresh",
                "error": None, "head_matches_local": True, "runs": [run]}
        cases = [base, base | {"state": "stale"}, base | {"head_matches_local": False},
                 base | {"runs": [run | {"status": "in_progress", "conclusion": None}]},
                 base | {"runs": [run | {"conclusion": "failure"}]}, base | {"runs": []}]
        result = subprocess.run([node, "-e", fn + "\nconsole.log(JSON.stringify(JSON.parse(require('fs').readFileSync(0,'utf8')).map(ciVerdict)));"],
                                input=json.dumps(cases), capture_output=True, text=True, check=True, timeout=10)
        labels = [x["label"] for x in json.loads(result.stdout)]
        self.assertEqual(labels, ["PASS", "STALE", "HEAD MISMATCH", "PENDING", "FAILED", "NO FOUNDATION RUN"])


class TrustedGateRetired(Base):
    """Owner decision 2026-10-16: the runner never invokes the optional trusted gate, even if asked to."""

    def test_publish_and_any_other_gate_mode_are_refused_fail_closed(self):
        self.assertEqual(self.cfg.gate_mode, "off")
        for mode in ("publish", "maybe"):
            with self.assertRaises(ValueError):
                R.Config(home=self.home, repo=self.repo, gate_mode=mode)
            with mock.patch.dict(os.environ, {"VEYRO_GATE_MODE": mode}), self.assertRaises(ValueError):
                R.Config(home=self.home, repo=self.repo)

    def test_tick_never_spawns_a_signer_or_sudo_even_with_a_pr_shaped_observation(self):
        r = self.runner(ci_every=60)
        spawned, real_popen = [], subprocess.Popen

        def spy(argv, *a, **k):  # records every child the tick starts, still delegating to the real Popen
            spawned.append(" ".join(map(str, argv)))
            return real_popen(argv, *a, **k)

        with mock.patch.object(subprocess, "Popen", side_effect=spy), \
                mock.patch.object(r, "refresh_ci", return_value={"pr": {"number": 7, "state": "open"}}):
            r.tick()
        self.assertFalse([c for c in spawned if "sudo" in c or "_veyrogate" in c or "publisher" in c], spawned)
        self.assertFalse(hasattr(r, "refresh_gate"))
        self.assertFalse((self.home / "gate.json").exists())
        self.assertFalse(any(n.startswith("GATE_") for n in dir(R)))


class CIFeed(Base):
    """gh is injected as the subprocess layer; nothing here touches the network."""
    SHA = "a" * 40

    OLD = "b" * 40
    RUN_URL = "https://github.com/o/r/actions/runs/1"

    def public_opener(self, calls, runs, head=None):
        class Response:
            def __init__(self, obj): self.data = json.dumps(obj).encode()
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, *_): return self.data
        def open_url(req, timeout):
            calls.append((req.full_url, req.get_method(), timeout))
            if "/git/ref/heads/main" in req.full_url:
                return Response({"object": {"sha": head or self.SHA}})
            return Response({"workflow_runs": runs})
        return open_url

    def mk_run(self, sha=None, event="push", branch="main", conclusion="success"):
        return {"name": "Veyro Foundation CI", "status": "completed", "conclusion": conclusion, "head_branch": branch,
                "head_sha": sha or self.SHA, "event": event, "html_url": self.RUN_URL}

    def test_public_observation_reads_only_main_ref_and_push_runs_never_a_pull_request(self):
        self.public_origin()
        calls = []
        runs = [self.mk_run(), self.mk_run(sha=self.OLD), self.mk_run(event="pull_request"),
                self.mk_run(branch="feature/x")]
        ci = R.fetch_ci_public(self.cfg, self.public_opener(calls, runs))
        self.assertEqual((ci["source"], ci["scope"], ci["branch"], ci["head_sha"]),
                         ("github-public-api", "main-push", "main", self.SHA))
        self.assertEqual([(x["head_sha"], x["event"], x["ref"]) for x in ci["runs"]], [(self.SHA, "push", "main")])
        self.assertEqual(ci["runs_other_head"], 3)  # older/other-event/other-branch runs are hidden, only counted
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(method == "GET" and timeout <= R.CI_CALL_TIMEOUT for _, method, timeout in calls))
        for url, _, _ in calls:
            self.assertNotIn("/pulls", url)
            self.assertNotIn("check-runs", url)
        self.assertIn(f"branch=main&event=push&head_sha={self.SHA}", calls[1][0])
        for key in ("pr", "checks"):
            self.assertNotIn(key, ci)
        self.assertNotIn("token", json.dumps(ci).lower())

    def test_public_main_head_without_push_run_is_not_a_pass(self):
        self.public_origin()
        ci = R.fetch_ci_public(self.cfg, self.public_opener([], [self.mk_run(sha=self.OLD)]))
        self.assertEqual((ci["head_sha"], ci["runs"], ci["runs_other_head"]), (self.SHA, [], 1))

    def test_malformed_main_ref_is_rejected(self):
        self.public_origin()
        for head in ("main", "A" * 40, "a" * 39):
            with self.assertRaises(R.CIError) as e:
                R.fetch_ci_public(self.cfg, self.public_opener([], [], head=head))
            self.assertEqual(str(e.exception), "github-api-bad-output")

    def test_public_api_failure_is_explicit(self):
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin", "https://github.com/o/r.git"], check=True)
        def fail(*_args, **_kwargs): raise TimeoutError()
        with self.assertRaises(R.CIError) as e:
            R.fetch_ci_public(self.cfg, fail)
        self.assertEqual(str(e.exception), "github-api-unavailable")

    def public_origin(self):
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin", "https://github.com/o/r.git"], check=True)

    def test_public_rate_limit_needs_proof_and_never_exposes_server_text(self):
        self.public_origin()
        def failing(code, hdrs):
            def open_url(req, timeout):
                raise urllib.error.HTTPError(req.full_url, code, "SERVER-SECRET-TEXT", hdrs, None)
            return open_url
        for code, hdrs, want in ((403, {}, "github-api-unavailable"),
                                 (403, {"X-RateLimit-Remaining": "0"}, "github-api-rate-limit"),
                                 (403, {"Retry-After": "60"}, "github-api-rate-limit"),
                                 (429, {}, "github-api-rate-limit")):
            with self.assertRaises(R.CIError) as e:
                R.fetch_ci_public(self.cfg, failing(code, hdrs))
            self.assertEqual(str(e.exception), want)
            self.assertNotIn("SECRET", str(e.exception))

    def test_public_bad_and_oversized_output_are_rejected_before_use(self):
        self.public_origin()
        class Raw:
            def __init__(self, data): self.data = data
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, n=-1): return self.data[:n] if n >= 0 else self.data
        for data in (b"<html>not json", b" " * (R.CI_MAX_BYTES + 10), b'{"object": 3}'):
            with self.assertRaises(R.CIError) as e:
                R.fetch_ci_public(self.cfg, lambda req, timeout, d=data: Raw(d))
            self.assertEqual(str(e.exception), "github-api-bad-output")

    class FakePopen:
        """Stands in for the supervised child; never starts a process."""
        made = []

        def __init__(self, cmd, out=b"", hang=False, returncode=0, **kw):
            self.cmd, self.kw, self.out, self.hang, self.returncode = cmd, kw, out, hang, returncode
            self.pid, self.killed = 424242, False
            type(self).made.append(self)

        def communicate(self, timeout=None):
            if self.hang and timeout is not None:
                raise subprocess.TimeoutExpired(self.cmd, timeout)
            return self.out, None

        def kill(self): self.killed = True

        def wait(self): return self.returncode

    def popen_factory(self, **kw):
        self.FakePopen.made = []
        return lambda cmd, **k: self.FakePopen(cmd, **kw, **k)

    def test_public_observer_is_supervised_with_hard_cap_and_no_credentials(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"GH_TOKEN": "tok", "GITHUB_TOKEN": "tok", "PATH": os.environ.get("PATH", "")}):
            with mock.patch.object(R.os, "killpg", side_effect=ProcessLookupError) as killpg:
                with self.assertRaises(R.CIError) as e:
                    R.observe_public(self.cfg, self.popen_factory(hang=True))
        self.assertEqual(str(e.exception), "github-api-timeout")
        p = self.FakePopen.made[0]
        killpg.assert_called_once_with(p.pid, R.signal.SIGKILL)
        self.assertTrue(p.killed)  # falls back to killing the child when the group is already gone
        self.assertTrue(p.kw["start_new_session"])
        self.assertLessEqual(set(p.kw["env"]), {"PATH", "HOME"})
        self.assertIn("ci-observe-public", p.cmd)

    def test_public_observer_maps_child_results_to_fixed_codes(self):
        ok = json.dumps({"source": "github-public-api", "scope": "main-push", "observed_at": R.now_iso(),
                         "repo": "o/r", "extra": "leak"}).encode()
        ci = R.observe_public(self.cfg, self.popen_factory(out=ok))
        self.assertEqual((ci["repo"], "extra" in ci), ("o/r", False))
        legacy = json.dumps({"source": "github-public-api", "observed_at": R.now_iso(), "repo": "o/r"}).encode()
        with self.assertRaises(R.CIError) as e:  # an observation without the main-push scope is never accepted
            R.observe_public(self.cfg, self.popen_factory(out=legacy))
        self.assertEqual(str(e.exception), "github-api-bad-output")
        for out, rc, want in ((b'{"error": "github-api-rate-limit"}', 1, "github-api-rate-limit"),
                              (b'{"error": "Bad <script> text"}', 1, "github-api-failed"),
                              (b"garbage", 0, "github-api-bad-output"),
                              (b"garbage", 1, "github-api-failed"),
                              (b"x" * (2 * R.CI_MAX_BYTES + 1), 0, "github-api-bad-output")):
            with self.assertRaises(R.CIError) as e:
                R.observe_public(self.cfg, self.popen_factory(out=out, returncode=rc))
            self.assertEqual(str(e.exception), want)

    def test_public_refresh_persists_and_suppresses_redundant_polls_across_restart(self):
        ok = json.dumps({"source": "github-public-api", "scope": "main-push", "observed_at": R.now_iso(),
                         "repo": "o/r"}).encode()
        r = self.runner(ci_mode="public", ci_every=300)
        r.ci_popen = self.popen_factory(out=ok)
        r.refresh_ci()
        r.refresh_ci()  # inside the cadence window
        self.assertEqual(len(self.FakePopen.made), 1)
        saved = json.loads((self.home / "ci.json").read_text())
        self.assertEqual((saved["repo"], saved["error"]), ("o/r", None))
        r2 = self.runner()  # LaunchAgent restart: fresh process, last_ci back at 0
        r2.ci_popen = self.popen_factory(out=ok)
        r2.refresh_ci()
        self.assertEqual(self.FakePopen.made, [])
        for stamp in ("2000-01-01T00:00:00+00:00", "garbage",
                      (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()):
            (self.home / "ci.json").write_text(json.dumps(saved | {"last_attempt_at": stamp}))
            r3 = self.runner()
            r3.ci_popen = self.popen_factory(out=ok)
            r3.refresh_ci()
            self.assertEqual(len(self.FakePopen.made), 1, stamp)

    def test_public_refresh_failure_keeps_last_good_observation_with_error_code(self):
        ok = json.dumps({"source": "github-public-api", "scope": "main-push", "observed_at": R.now_iso(),
                         "repo": "o/r"}).encode()
        r = self.runner(ci_mode="public", ci_every=300)
        r.ci_popen = self.popen_factory(out=ok)
        r.refresh_ci()
        r.last_ci = 0.0
        (self.home / "ci.json").write_text(json.dumps(json.loads((self.home / "ci.json").read_text())
                                                     | {"last_attempt_at": "2000-01-01T00:00:00+00:00"}))
        r.ci_popen = self.popen_factory(out=b'{"error": "github-api-rate-limit"}', returncode=1)
        r.refresh_ci()
        saved = json.loads((self.home / "ci.json").read_text())
        self.assertEqual((saved["repo"], saved["error"]), ("o/r", "github-api-rate-limit"))

    def test_unknown_ci_mode_fails_closed(self):
        with self.assertRaises(ValueError):
            R.Config(home=self.home, repo=self.repo, ci_mode="pubic")

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
            if fail == "rate" and a == "run list":
                return subprocess.CompletedProcess(argv, 1, "", "HTTP 403 rate limit exceeded")
            out = {"repo view": {"nameWithOwner": "o/r", "url": "https://github.com/o/r", "extra": "leak"},
                   "api repos/o/r/git/ref/heads/main": {"object": {"sha": self.SHA}},
                   "run list": [{"name": "CI", "status": "completed", "conclusion": "success", "headBranch": "main",
                                 "headSha": self.SHA, "event": "push", "createdAt": "2026-01-01T00:00:00Z",
                                 "url": "https://github.com/o/r/actions/runs/1", "token": "leak"},
                                {"name": "Bad", "status": "completed", "conclusion": "success", "headBranch": "main",
                                 "headSha": self.SHA, "event": "push", "url": "javascript:alert(1)"},
                                {"name": "OldHead", "status": "completed", "conclusion": "success",
                                 "headBranch": "main", "headSha": self.OLD, "event": "push"},
                                {"name": "PR", "status": "completed", "conclusion": "success", "headBranch": "main",
                                 "headSha": self.SHA, "event": "pull_request"}]}[a]
            return subprocess.CompletedProcess(argv, 0, json.dumps(out), "")
        return run

    def test_success_snapshot_is_persisted_allowlisted_and_read_only(self):
        r, calls = self.runner(ci_every=60), []
        r.ci_run = self.fake_gh(calls=calls)
        r.refresh_ci()
        ci = dashboard.runner.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["state"], ci["error"], ci["source"], ci["head_sha"]), ("fresh", None, "gh", self.SHA))
        self.assertEqual((ci["scope"], ci["branch"]), ("main-push", "main"))
        self.assertEqual([x["name"] for x in ci["runs"]], ["CI", "Bad"])  # other head / other event never shown
        self.assertEqual(ci["runs_other_head"], 2)
        self.assertEqual(ci["runs"][0]["url"], "https://github.com/o/r/actions/runs/1")
        self.assertIsNone(ci["runs"][1]["url"])  # non-https url dropped
        self.assertNotIn("leak", json.dumps(ci))
        self.assertNotIn("pr", ci)
        self.assertEqual((ci["staging"], ci["secrets"], ci["rollback"]), ("not configured",) * 3)
        for argv, kw in calls:  # argv list, no shell, bounded, read-only verbs only, no PR query
            self.assertIsInstance(argv, list)
            self.assertFalse(kw.get("shell"))
            self.assertLessEqual(kw["timeout"], R.CI_CALL_TIMEOUT)
            self.assertIn(argv[1:3], (["repo", "view"], ["run", "list"], ["api", "repos/o/r/git/ref/heads/main"]))
        self.assertFalse(any("pr" in argv[1:2] or "pulls" in " ".join(argv) for argv, _ in calls))
        run_list = next(argv for argv, _ in calls if argv[1:3] == ["run", "list"])
        self.assertEqual(run_list[run_list.index("--branch") + 1], "main")
        self.assertEqual(run_list[run_list.index("--event") + 1], "push")
        self.assertEqual(run_list[run_list.index("--commit") + 1], self.SHA)

    def test_repo_slug_is_taken_from_local_origin_without_network_discovery(self):
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin", "https://github.com/o/r.git"], check=True)
        r, calls = self.runner(ci_every=60), []
        r.ci_run = self.fake_gh(calls=calls)
        r.refresh_ci()
        repo_call = next(argv for argv, _ in calls if argv[1:3] == ["repo", "view"])
        self.assertEqual(repo_call[3], "o/r")

    def test_failures_keep_last_success_but_mark_stale_and_leak_nothing(self):
        r = self.runner(ci_every=60)
        r.ci_run = self.fake_gh()
        r.refresh_ci()
        for fail, code in (("missing", "gh-missing"), ("timeout", "gh-timeout-repo-view"), ("auth", "gh-auth"),
                           ("rate", "gh-failed")):
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
        self.assertEqual((ci["state"], ci["observed_at"], ci["runs"]), ("unavailable", None, []))
        r.last_ci, r.ci_run = 0, self.fake_gh()
        r.refresh_ci()
        d = json.loads((self.home / "ci.json").read_text()) | {"observed_at": "2020-01-01T00:00:00+00:00"}
        (self.home / "ci.json").write_text(json.dumps(d))
        self.assertEqual(R.snapshot(self.cfg)["ci"]["state"], "stale")

    def test_snapshot_flags_local_head_mismatch_and_pushless_main_head(self):
        r = self.runner(ci_every=60)
        r.ci_run = self.fake_gh()
        r.refresh_ci()
        ci = R.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["state"], ci["head_matches_local"]), ("fresh", False))  # local repo head is not remote main
        local = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                               check=True).stdout.strip()
        d = json.loads((self.home / "ci.json").read_text()) | {"head_sha": local, "runs": []}
        (self.home / "ci.json").write_text(json.dumps(d))
        ci = R.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["head_matches_local"], ci["runs"]), (True, []))  # matching head, but no push run: no pass

    def test_local_head_readonly_resolves_loose_packed_and_detached_without_git(self):
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            gitdir = repo / ".git"
            gitdir.mkdir()
            (gitdir / "HEAD").write_text("ref: refs/heads/main\n")
            loose = gitdir / "refs/heads/main"
            loose.parent.mkdir(parents=True)
            loose.write_text(sha + "\n")
            self.assertEqual(R.local_head_readonly(repo), sha)
            loose.unlink()
            (gitdir / "packed-refs").write_text("# pack-refs\n" + sha + " refs/heads/main\n")
            self.assertEqual(R.local_head_readonly(repo), sha)
            (gitdir / "HEAD").write_text(sha + "\n")
            self.assertEqual(R.local_head_readonly(repo), sha)
            (gitdir / "HEAD").write_text("ref: refs/../secrets\n")
            self.assertIsNone(R.local_head_readonly(repo))

    def test_legacy_branch_pr_cache_is_not_reported_as_main_evidence_or_carried_forward(self):
        legacy = {"source": "gh", "observed_at": R.now_iso(), "head_sha": self.SHA, "branch": "feature/x",
                  "pr": {"number": 10, "state": "OPEN"}, "checks": [{"name": "c", "state": "SUCCESS"}],
                  "runs": [{"name": "CI", "status": "completed", "conclusion": "success", "head_sha": self.SHA}]}
        (self.home / "ci.json").write_text(json.dumps(legacy))
        ci = R.snapshot(self.cfg)["ci"]
        self.assertEqual((ci["state"], ci["runs"], ci["head_sha"], ci["error"]), ("unavailable", [], None, "legacy-scope"))
        self.assertNotIn("pr", ci)
        r = self.runner(ci_every=60)
        r.ci_run = self.fake_gh(fail="missing")
        r.refresh_ci()
        saved = json.loads((self.home / "ci.json").read_text())
        self.assertEqual((saved.get("runs"), saved.get("head_sha"), saved["error"]), (None, None, "gh-missing"))
        self.assertNotIn("pr", saved)

    def test_malformed_ci_cache_lists_do_not_crash_reader_or_runner(self):
        (self.home / "ci.json").write_text(json.dumps({"source": "gh", "runs": {"bad": 1}}))
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

    def test_dashboard_ci_ui_uses_safe_text_and_separate_freshness(self):
        js = dashboard.JS
        self.assertIn("function ciVerdict", js)
        self.assertIn("cached runs are not current evidence", js)
        self.assertNotIn("innerHTML", js)
        self.assertIn("CI freshness is distinct from recorded module acceptance", dashboard.HTML)
        self.assertNotIn("ci.pr", js)
        self.assertNotIn("ci.checks", js)


class PrerequisiteGate(Base):
    """MOD-001 depends only on MOD-000 in the catalog; its receipt is the evidence under test."""

    def head(self):
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def review(self, name="rev.json", result=None, model="claude-opus-5-5", kind="gatekeeper", bind=None, **over):
        result = f"fine {name}\nOUTCOME: APPROVED" if result is None else result
        body = {"type": "result", "subtype": "success", "is_error": False, "result": result,
                "modelUsage": {model: {"inputTokens": 10, "outputTokens": 20}}} | over
        data = json.dumps(body).encode()
        (self.home / "reviews").mkdir(parents=True, exist_ok=True)
        (self.home / "reviews" / name).write_bytes(data)
        return {"kind": kind, "path": f"reviews/{name}", "sha256": hashlib.sha256(data).hexdigest(),
                "activation_sha": bind or self.head()}

    def both(self):
        return [self.review("gk.json"), self.review("act.json", kind="activation-review")]

    def ci(self, sha=None, **over):
        return {"run_id": "123", "name": "Veyro Foundation CI", "event": "push", "status": "completed",
                "head_sha": sha or self.head(), "conclusion": "success"} | over

    def receipt(self, module="MOD-000", **over):
        sha = self.head()
        body = {"schema": 1, "module": module, "operator": "op", "recorded_at": R.now_iso(), "activation_sha": sha,
                "ci": self.ci(sha)} | over
        if "reviews" not in over:  # build defaults lazily so caller-made review files are never overwritten
            body["reviews"] = self.both()
        (self.home / "acceptances").mkdir(parents=True, exist_ok=True)
        (self.home / "acceptances" / f"{module}.json").write_text(json.dumps(body))

    def refused(self, role="implement", module="MOD-001", **kw):
        with self.assertRaises(ValueError) as cm:
            self.add(self.runner(), role=role, module=module, **kw)
        return str(cm.exception)

    def test_missing_prerequisite_refused_at_enqueue(self):
        self.assertIn("PREREQ_NOT_ACCEPTED MOD-000", self.refused())
        self.assertIn("PREREQ_NOT_ACCEPTED", self.refused("gatekeeper"))

    def test_valid_exact_evidence_allows(self):
        self.receipt()
        r = self.runner()
        t = self.add(r, module="MOD-001")
        self.assertIs(r.next_ready(), t)
        self.assertIsNone(t.get("gate_reason"))

    def test_wrong_evidence_fails_closed(self):
        good, act = self.review(), self.review("act.json", kind="activation-review")
        bad_cases = {
            "only-gatekeeper": {"reviews": [good]},
            "only-activation": {"reviews": [act]},
            "same-file-both-kinds": {"reviews": [good, good | {"kind": "activation-review"}]},
            "unbound-review": {"reviews": [good, act | {"activation_sha": "1" * 40}]},
            "unknown-mode": {"mode": "other"},
            "module": {"module": "MOD-002"},
            "sha": {"activation_sha": "0" * 40, "ci": self.ci("0" * 40)},
            "ci-sha": {"ci": self.ci("1" * 40)},
            "ci-conclusion": {"ci": self.ci(conclusion="failure")},
            "ci-pending": {"ci": self.ci(status="in_progress", conclusion=None)},
            "ci-status": {"ci": self.ci(status="queued")},
            "ci-pr-event": {"ci": self.ci(event="pull_request")},
            "ci-wrong-workflow": {"ci": self.ci(name="Other Workflow")},
            "ci-run-id": {"ci": self.ci(run_id="12a")},
            "ci-run-id-int": {"ci": self.ci(run_id=123)},
            "review-hash": {"reviews": [good | {"sha256": "0" * 64}, act]},
            "review-not-approved": {"reviews": [self.review("b.json", result="x\nOUTCOME: CHANGES_REQUESTED"), act]},
            "review-not-opus": {"reviews": [self.review("c.json", model="claude-sonnet-5-5"), act]},
            "review-escape": {"reviews": [good | {"path": "../outside.json"}, act]},
            "no-reviews": {"reviews": []},
        }
        for name, over in bad_cases.items():
            self.receipt(**over)
            self.assertIn("PREREQ_NOT_ACCEPTED", self.refused(), name)
        self.receipt()
        (self.home / "acceptances" / "MOD-000.json").write_text("{not json")
        self.assertIn("PREREQ_NOT_ACCEPTED", self.refused())

    def test_unknown_module_fails_closed(self):
        self.assertIn("GATE_UNVERIFIABLE", self.refused(module="MOD-999"))

    def test_independent_readonly_roles_bypass(self):
        r = self.runner()
        for i, role in enumerate(("architecture", "security", "performance", "code-review")):
            self.add(r, role=role, module="MOD-001", id=f"ro{i}")
        self.assertEqual(len(r.state["tasks"]), 4)
        self.assertIsNotNone(r.next_ready())

    def test_recheck_at_dispatch(self):
        self.receipt()
        r = self.runner()
        t = self.add(r, module="MOD-001")
        self.assertIs(r.next_ready(), t)
        (self.home / "acceptances" / "MOD-000.json").unlink()
        r.dispatch(t)
        self.assertEqual((t["status"], t["attempts"]), ("QUEUED", 0))
        self.assertIn("PREREQ_NOT_ACCEPTED", t["gate_reason"])
        self.assertFalse((self.repo / "out" / "a.txt").exists())

    def test_gated_head_of_line_does_not_starve_or_complete(self):
        self.receipt()
        r = self.runner()
        old = self.add(r, module="MOD-001", id="old")
        (self.home / "acceptances" / "MOD-000.json").unlink()
        new = self.add(r, module="MOD-000", id="new", allowed_paths=["out/"], expected_changes=["out/b.txt"],
                       prompt="WRITE=out/b.txt\nCONTENT=hi")
        self.assertIs(r.next_ready(), new)
        self.assertEqual(old["status"], "QUEUED")
        r.dispatch(r.next_ready())
        self.assertEqual(new["status"], "DONE")
        self.assertEqual((old["status"], old["attempts"]), ("QUEUED", 0))
        self.assertIsNone(r.next_ready())

    def test_no_second_writer_when_gate_passes(self):
        self.receipt()
        r = self.runner()
        t = self.add(r, module="MOD-001")
        other = R.FileLock(R.writer_lock_path(self.home, self.repo))
        self.assertTrue(other.acquire({"pid": os.getpid()}))
        try:
            r.dispatch(t)
        finally:
            other.release()
        self.assertEqual((t["status"], t["attempts"]), ("QUEUED", 0))
        self.assertFalse((self.repo / "out" / "a.txt").exists())
        r.dispatch(t)
        self.assertEqual(t["status"], "DONE")

    def test_markdown_verdict_shape_and_contradictions(self):
        md = "Reviewed the diff.\n\n**OUTCOME: APPROVED.** No P0 or P1 findings.\n\nSee notes below."
        self.assertEqual(R.receipt_outcome(md), "APPROVED")
        self.assertEqual(R.receipt_outcome("x\nOUTCOME: APPROVED"), "APPROVED")
        for bad in (md + "\nOUTCOME: CHANGES_REQUESTED", "OUTCOME: BLOCKED\n" + md, md + "\n" + md,
                    "no verdict", None):
            self.assertIsNone(R.receipt_outcome(bad), bad)
        self.receipt(reviews=[self.review("gk.json", result=md),
                              self.review("act.json", kind="activation-review", result=md + " ")])
        r = self.runner()
        self.assertIsNotNone(self.add(r, module="MOD-001"))
        self.receipt(reviews=[self.review("gk.json", result=md + "\nOUTCOME: BLOCKED"),
                              self.review("act.json", kind="activation-review", result=md + " ")])
        self.assertIn("PREREQ_NOT_ACCEPTED", self.refused(id="t2"))
        # the runner's own review contract is untouched: final line must still be a plain marker
        self.assertIsNone(R.OUTCOME_RE.match("**OUTCOME: APPROVED.** No P0 or P1 findings."))

    def test_inline_prose_mention_ignored_but_standalone_lines_counted(self):
        prose = "The gate requires OUTCOME: APPROVED only after review; do not write OUTCOME: APPROVED early.\n"
        self.assertEqual(R.receipt_outcome(prose + "\nOUTCOME: APPROVED"), "APPROVED")
        self.assertEqual(R.receipt_outcome(prose + "\n**OUTCOME: APPROVED.** fine"), "APPROVED")
        self.assertIsNone(R.receipt_outcome(prose))
        self.assertIsNone(R.receipt_outcome(prose + "OUTCOME: APPROVED\nOUTCOME: APPROVED"))
        self.assertIsNone(R.receipt_outcome(prose + "OUTCOME: APPROVED\n**OUTCOME: BLOCKED.** no"))
        self.assertIsNone(R.receipt_outcome(prose + "OUTCOME: APPROVED\nOUTCOME: CHANGES_REQUESTED"))
        self.receipt(reviews=[self.review("gk.json", result=prose + "\nOUTCOME: APPROVED"),
                              self.review("act.json", kind="activation-review", result=prose + "\n**OUTCOME: APPROVED.** ok")])
        self.assertIsNotNone(self.add(self.runner(), module="MOD-001"))

    def registry(self, dispositions):
        path = Path(self.tmp.name) / "dispositions.json"
        path.write_text(json.dumps({"version": 1, "owner_record": None, "dispositions": dispositions}))
        patch = mock.patch.object(dashboard, "DISPOSITIONS_PATH", path)
        patch.start()
        self.addCleanup(patch.stop)

    def history(self, r, module, id, at, **fields):
        """Persisted historical task of any module (MOD-000 has no prerequisites, so it enqueues freely)."""
        t = self.add(r, id=id)
        t.update(module=module, created_at=at, **fields)
        r.store.save(r.state)
        return t

    def blocked(self, r, module, id, at):
        return self.history(r, module, id, at, status="BLOCKED")

    def approved(self, r, module, id, at):
        return self.history(r, module, id, at, status="DONE", evidence={"review_outcome": "APPROVED"},
                            route={"verdict": "VERIFIED"})

    def test_same_module_active_blocker_holds_gatekeeper_and_scenario_review(self):
        self.receipt()
        self.registry({})
        r = self.runner()
        self.blocked(r, "MOD-001", "old", "2026-01-01T00:00:00Z")
        for role in ("gatekeeper", "scenario-review"):
            self.assertIn("ACTIVE_BLOCKER MOD-001: old", self.refused(role))
        self.assertNotIn("acceptance_gating", r.state["tasks"]["old"])

    def test_other_module_and_other_roles_not_held(self):
        self.receipt()
        self.registry({})
        r = self.runner()
        self.blocked(r, "MOD-000", "other", "2026-01-01T00:00:00Z")
        self.assertEqual(self.add(r, role="gatekeeper", module="MOD-001", id="gk")["status"], "QUEUED")
        self.assertEqual(self.add(r, module="MOD-001", id="impl")["status"], "QUEUED")

    def test_resolved_historical_blocker_does_not_hold(self):
        self.receipt()
        self.registry({"old": {"module": "MOD-001", "classification": dashboard.RESOLVED, "evidence_task_id": "ok"}})
        r = self.runner()
        self.blocked(r, "MOD-001", "old", "2026-01-01T00:00:00Z")
        self.approved(r, "MOD-001", "ok", "2026-01-02T00:00:00Z")
        self.assertEqual(self.add(r, role="gatekeeper", module="MOD-001", id="gk")["status"], "QUEUED")

    def test_unverifiable_disposition_stays_active(self):
        self.receipt()
        r = self.runner()
        self.blocked(r, "MOD-001", "old", "2026-01-01T00:00:00Z")
        ok = self.approved(r, "MOD-001", "ok", "2026-01-02T00:00:00Z")
        entry = {"module": "MOD-001", "classification": dashboard.RESOLVED, "evidence_task_id": "ok"}
        for name, reg in {"empty": {}, "wrong-module": {"old": entry | {"module": "MOD-002"}},
                          "missing-evidence": {"old": entry | {"evidence_task_id": "nope"}},
                          "doc-missing": {"old": entry | {"docs": [{"path": "none.md", "contains": "x"}]}}}.items():
            self.registry(reg)
            self.assertIn("ACTIVE_BLOCKER", self.refused("gatekeeper"), name)
        ok["route"] = {"verdict": "UNVERIFIED"}
        r.store.save(r.state)
        self.registry({"old": entry})
        self.assertIn("ACTIVE_BLOCKER", self.refused("gatekeeper"))
        ok["route"] = {"verdict": "VERIFIED"}
        r.store.save(r.state)
        (Path(self.tmp.name) / "dispositions.json").write_text("{bad")  # unreadable registry fails closed
        self.assertIn("ACTIVE_BLOCKER", self.refused("gatekeeper"))
        self.assertEqual(r.state["tasks"]["old"]["status"], "BLOCKED")  # statuses are never cleared

    def test_current_mod003_review_rejection_holds_until_exact_disposition(self):
        self.registry({})  # MOD-003 prerequisites are not under test: the receipt check is bypassed below
        r = self.runner()
        self.blocked(r, "MOD-003", "mod003-s1-full-opus-review-20261016", "2026-01-01T00:00:00Z")
        t = {"id": "gk3", "module": "MOD-003", "role": "gatekeeper", "status": "QUEUED"}
        with mock.patch.object(R, "catalog_dependencies", return_value=[]):
            self.assertIn("ACTIVE_BLOCKER MOD-003", R.gate_reason(self.cfg, t, r.state["tasks"]))
            self.registry({"mod003-s1-full-opus-review-20261016": {
                "module": "MOD-003", "classification": dashboard.RESOLVED, "evidence_task_id": "rem"}})
            self.approved(r, "MOD-003", "rem", "2026-01-02T00:00:00Z")
            self.assertIsNone(R.gate_reason(self.cfg, t, r.state["tasks"]))

    def test_dispatch_recheck_and_no_head_of_line_starvation(self):
        self.receipt()
        self.registry({})
        r = self.runner()
        gk = self.add(r, role="gatekeeper", module="MOD-001", id="gk")
        later = self.add(r, module="MOD-000", id="later", allowed_paths=["out/"], expected_changes=["out/b.txt"],
                         prompt="WRITE=out/b.txt\nCONTENT=hi")
        self.assertIs(r.next_ready(), gk)
        self.blocked(r, "MOD-001", "old", "2026-01-01T00:00:00Z")
        self.assertIs(r.next_ready(), later)  # gated gatekeeper is skipped, not blocking eligible work
        r.dispatch(gk)  # re-checked under the writer lock before dispatch
        self.assertEqual((gk["status"], gk["attempts"]), ("QUEUED", 0))
        self.assertIn("ACTIVE_BLOCKER", gk["gate_reason"])
        self.assertEqual(r.state["tasks"]["old"]["status"], "BLOCKED")


class LegacyMod000Receipt(Base):
    """MOD-000-only receipt for the pre-CI Lean Foundation acceptance; the fixed evidence is patched to a temp repo."""

    def head(self):
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def setUp(self):
        super().setUp()
        rec = self.repo / R.MOD000_RECORD
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text("# MOD-000\nStatus: ACCEPTED\n" + R.MOD000_LEGACY_MR + "\n")
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "module record")
        self.hdr = self.head()
        for name, val in (("MOD000_HEADER_SHA", self.hdr),):
            p = mock.patch.object(R, name, val)
            p.start()
            self.addCleanup(p.stop)
        self.write_evidence()

    def write_evidence(self, state_over=None, result="done\nOUTCOME: APPROVED", model="claude-opus-5-5"):
        body = {"subtype": "success", "is_error": False, "result": result,
                "modelUsage": {model: {"inputTokens": 10, "outputTokens": 20}}}
        data = json.dumps(body).encode()
        (self.home / "runs").mkdir(parents=True, exist_ok=True)
        (self.home / R.MOD000_LEGACY_REVIEW).write_bytes(data)
        task = {"id": R.MOD000_LEGACY_TASK, "module": "MOD-000", "role": "gatekeeper", "status": "DONE",
                "evidence": {"route_verdict": "VERIFIED", "review_outcome": "APPROVED"}} | (state_over or {})
        (self.home / "state.json").write_text(json.dumps({"schema": 1, "tasks": {R.MOD000_LEGACY_TASK: task}}))
        return hashlib.sha256(data).hexdigest()

    def legacy(self, sha256=None, module="MOD-000", **over):
        body = {"schema": 1, "module": module, "mode": R.LEGACY_MODE, "operator": "op", "recorded_at": R.now_iso(),
                "activation_sha": self.hdr, "review_sha256": sha256 or self.write_evidence()} | over
        (self.home / "acceptances").mkdir(parents=True, exist_ok=True)
        (self.home / "acceptances" / f"{module}.json").write_text(json.dumps(body))

    def check(self):
        return R.gate_reason(self.runner().cfg, {"role": "implement", "module": "MOD-001", "id": "x"}, {})

    def test_positive_without_ci(self):
        self.legacy()
        self.assertIsNone(self.check())

    def test_missing_or_wrong_evidence_rejected(self):
        self.legacy()
        (self.home / "state.json").write_text(json.dumps({"schema": 1, "tasks": {}}))
        self.assertIn("PREREQ_NOT_ACCEPTED", self.check())
        for over in ({"status": "BLOCKED"}, {"evidence": {"route_verdict": "MISMATCH", "review_outcome": "APPROVED"}},
                     {"evidence": {"route_verdict": "VERIFIED", "review_outcome": "CHANGES_REQUESTED"}}):
            self.legacy(self.write_evidence(over))
            self.assertIn("PREREQ_NOT_ACCEPTED", self.check(), over)
        for kw in ({"result": "x\nOUTCOME: CHANGES_REQUESTED"}, {"model": "claude-sonnet-5-5"}):
            self.legacy(self.write_evidence(**kw))
            self.assertIn("PREREQ_NOT_ACCEPTED", self.check(), kw)
        self.legacy(self.write_evidence())
        self.assertIsNone(self.check())
        self.legacy("0" * 64)
        self.assertIn("PREREQ_NOT_ACCEPTED", self.check())
        self.legacy(activation_sha="1" * 40)
        self.assertIn("PREREQ_NOT_ACCEPTED", self.check())
        self.legacy()
        (self.home / R.MOD000_LEGACY_REVIEW).unlink()
        self.assertIn("PREREQ_NOT_ACCEPTED", self.check())

    def test_live_header_must_still_show_accepted(self):
        self.legacy()
        (self.repo / R.MOD000_RECORD).write_text("# MOD-000\nStatus: PENDING ACCEPTED\n" + R.MOD000_LEGACY_MR + "\n")
        self.assertIn("PREREQ_NOT_ACCEPTED", self.check())
        (self.repo / R.MOD000_RECORD).write_text("# MOD-000\nStatus: ACCEPTED\n")
        self.assertIn("PREREQ_NOT_ACCEPTED", self.check())

    def test_mode_rejected_for_other_modules(self):
        cfg = self.runner().cfg
        self.legacy(module="MOD-001", activation_sha=self.hdr)
        with self.assertRaises(R.GateError):
            R.verify_receipt(cfg, "MOD-001")

    def test_legacy_prose_mention_with_final_verdict_accepted(self):
        prose = "Gate says OUTCOME: APPROVED is only for clean reviews.\n\nOUTCOME: APPROVED"
        self.legacy(self.write_evidence(result=prose))
        self.assertIsNone(self.check())
        self.legacy(self.write_evidence(result=prose + "\nOUTCOME: CHANGES_REQUESTED"))
        self.assertIn("PREREQ_NOT_ACCEPTED", self.check())


class WorkflowShape(unittest.TestCase):
    """Direct-main policy: the real workflow passes, and each forbidden mutation of it is detected."""

    @classmethod
    def setUpClass(cls):
        cls.text = WC.WORKFLOW.read_text()

    def test_committed_workflow_is_push_to_main_only_with_gate_disabled(self):
        self.assertEqual(WC.check(self.text), [])
        self.assertIn("name: foundation (MOD-000 focused checks)", self.text)  # check name kept for continuity

    def mutated(self, old, new):
        self.assertIn(old, self.text)  # a stale mutation target must fail loudly, not pass vacuously
        return WC.check(self.text.replace(old, new, 1))

    def test_removed_and_added_triggers_are_rejected(self):
        trigger = 'on:\n  push:\n    branches:\n      - "main"\n'
        for extra in ("  pull_request:\n", "  merge_group:\n", "  pull_request_target:\n", "  workflow_dispatch:\n"):
            self.assertTrue(self.mutated(trigger, trigger + extra), extra)
        self.assertTrue(self.mutated('      - "main"\n', '      - "main"\n      - "feature/**"\n'))
        self.assertTrue(self.mutated('      - "main"\n', '      - "release"\n'))
        self.assertTrue(self.mutated(trigger, "on:\n  pull_request:\n"))

    def test_write_permission_gate_secret_and_deploy_are_rejected(self):
        self.assertTrue(self.mutated("contents: read", "contents: write"))
        self.assertTrue(self.mutated("contents: read\n", "contents: read\n  checks: write\n"))
        self.assertTrue(self.mutated("      - name: Compile / syntax check\n",
                                     "      - name: Compile / syntax check\n        env:\n          VEYRO_GATE_MODE: publish\n"))
        self.assertTrue(self.mutated("      - name: Compile / syntax check\n",
                                     "      - name: x\n        run: echo ${{ secrets.TOKEN }}\n"
                                     "      - name: Compile / syntax check\n"))
        self.assertTrue(self.mutated("    timeout-minutes: 15\n", "    timeout-minutes: 15\n    environment: production\n"))

    def test_renamed_job_is_rejected_and_comments_cannot_hide_or_trigger_findings(self):
        self.assertTrue(self.mutated("name: foundation (MOD-000 focused checks)", "name: foundation"))
        self.assertEqual(WC.check(self.text + "\n# pull_request merge_group feature/** deploy\n"), [])

    def test_top_level_concurrency_is_rejected_but_comment_mentions_are_not(self):
        self.assertNotRegex(self.text, r"(?m)^concurrency\s*:")
        block = "concurrency:\n  group: g\n  cancel-in-progress: false\n\n"
        inline = "concurrency: g\n\n"
        for extra in (block, inline):
            self.assertTrue(self.mutated("jobs:\n", extra + "jobs:\n"), extra)
        self.assertEqual(WC.check(self.text.replace("jobs:\n", "# concurrency: not used here\njobs:\n", 1)), [])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            good, bad = Path(d, "good.yml"), Path(d, "bad.yml")
            good.write_text(self.text)
            bad.write_text(self.text.replace('      - "main"\n', '      - "main"\n  pull_request:\n', 1))
            with mock.patch("sys.stderr"), mock.patch("builtins.print"):
                self.assertEqual(WC.main(["x", str(good)]), 0)
                self.assertEqual(WC.main(["x", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
