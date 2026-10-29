"""Boundary tests for the owner control wrapper. Everything runs against a disposable home/repo/legacy fixture in a temp dir."""
import ast
import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import control as C
import runner as R

TMP_ROOT = os.environ.get("VEYRO_TEST_TMP", "/tmp")
SPEC = {"id": "CTL-1", "module": "MOD-002", "role": "implement", "prompt": "do the thing", "allowed_paths": ["src/"]}


class Fixture(unittest.TestCase):
    """Constants point into a temp dir. By default the host-only predicates (worker uid, root-owned install) are patched out,
    exactly as test_runner.Env does; GuardTests turns them back on."""

    patch_host = True

    def setUp(self):
        self.addCleanup(os.umask, os.umask(0o022))  # fixture dirs and the proof must not be group/other-writable whatever the caller's umask
        self.tmp = tempfile.TemporaryDirectory(dir=TMP_ROOT)
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.repo, self.home, self.legacy = base / "repo", base / "home", base / "legacy" / "state.json"
        self.proof = self.legacy.parent / "cutover.json"
        self.legacy.parent.mkdir()
        self.home.mkdir()
        self.repo.mkdir()
        catalog = self.repo / "tools/mission_runner/module_catalog.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_bytes(R.CATALOG_PATH.read_bytes())
        for a in (("init", "-q", "-b", "main"), ("add", "-A"),
                  ("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")):
            subprocess.run(["git", "-C", str(self.repo), *a], check=True, capture_output=True)
        self.write_legacy({})
        self.write_proof(self.pin)
        self.patch_all(mock.patch.dict(os.environ, {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/")}, clear=True),
                       mock.patch.multiple(C, HOME=self.home, REPO=self.repo, LEGACY_STATE=self.legacy,
                                           LEGACY_EVIDENCE=base / "evidence", CUTOVER_PROOF=self.proof, ROOT_UID=os.getuid(),
                                           OWNER_HOME=base, CLAUDE_BIN=base / "claude"))
        if self.patch_host:
            self.patch_all(mock.patch.object(C, "worker_problem", lambda: None), mock.patch.object(C, "load_runner", lambda: R),
                           mock.patch.object(R, "runner_install_problem", lambda *a, **k: None),
                           mock.patch.object(R, "worker_boundary_problem", lambda *a, **k: None),
                           mock.patch.object(R, "host_problem", lambda *a, **k: None))

    def patch_all(self, *patches):
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def write_legacy(self, tasks):
        raw = json.dumps({"schema": 1, "tasks": tasks}).encode()
        self.legacy.write_bytes(raw)
        self.pin = hashlib.sha256(raw).hexdigest()

    def write_proof(self, pin, raw=None):
        self.proof.write_text(raw if raw is not None else json.dumps({"schema": 1, "legacy_sha256": pin}))
        self.proof.chmod(0o644)

    def run_ctl(self, *argv, stdin=b""):
        out, err, stream = io.StringIO(), io.StringIO(), io.BytesIO(stdin)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = C.main(list(argv), stdin=stream)
        return code, out.getvalue(), err.getvalue()

    def enqueue(self, spec=SPEC, **kw):
        return self.run_ctl("enqueue", stdin=json.dumps(spec).encode(), **kw)

    def tasks(self):
        return R.Store(self.home, create=False).load()["tasks"]


class VerbTests(Fixture):
    def test_allowed_verbs_parse(self):
        for argv, want in ((["status"], ("status", None)), (["pause"], ("pause", None)), (["resume"], ("resume", None)),
                           (["stop"], ("stop", None)), (["cancel", "T-1"], ("cancel", "T-1")), (["enqueue"], ("enqueue", None))):
            self.assertEqual(C.parse_argv(argv), want)

    def test_denied_unknown_and_extra_args_refused_without_touching_state(self):
        bad = (["run"], ["dashboard"], ["dashboard", "--port", "1"], ["acknowledge-escaped"], ["bogus"], [], ["--help"], ["-h"],
               ["STATUS"], ["status", "x"], ["pause", "--home", "/tmp/x"], ["stop", "x"], ["enqueue", "--id", "a"],
               ["enqueue", "-"], ["cancel"], ["cancel", "a", "b"])
        for argv in bad:
            with self.subTest(argv=argv):
                code, out, err = self.run_ctl(*argv)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith("refused:"))
        self.assertFalse((self.home / "v2").exists(), "a refused request must not create state")

    def test_pause_resume_stop_set_control(self):
        for verb, control in (("pause", "PAUSE"), ("stop", "STOP"), ("resume", "RUN")):
            code, out, _ = self.run_ctl(verb)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), {"command": verb, "control": control})
            self.assertEqual(R.Store(self.home, create=False).load()["control"], control)

    def test_cancel_pending_and_refusals(self):
        self.assertEqual(self.enqueue()[0], 0)
        code, out, _ = self.run_ctl("cancel", "CTL-1")
        self.assertEqual((code, json.loads(out)), (0, {"task_id": "CTL-1", "result": "cancelled"}))
        self.assertEqual(self.tasks()["CTL-1"]["status"], "CANCELLED")
        for tid in ("CTL-1", "nope", "a b", "x;rm -rf /", "$(id)", "a" * 65, "id\n"):
            with self.subTest(tid=tid):
                code, out, err = self.run_ctl("cancel", tid)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("cancel refused", err)

    def test_status_is_bounded_and_redacts_prompts_and_event_detail(self):
        secret = "PROMPT-SECRET-0xC0FFEE"
        self.assertEqual(self.enqueue({**SPEC, "prompt": secret})[0], 0)
        store = R.Store(self.home)
        store.event("leak-test", task_id="CTL-1", detail="EVENT-SECRET-DETAIL")
        with store.txn() as st:
            for i in range(300):
                st["tasks"][f"B-{i}"] = {"id": f"B-{i}", "seq": 10 + i, "status": "PENDING", "next_attempt_at": 0,
                                         "last_error": "e" * 5000, "title": "t" * 5000}
        code, out, _ = self.run_ctl("status")
        self.assertEqual(code, 0)
        view = json.loads(out)
        self.assertLessEqual(len(out), C.OUT_MAX)
        self.assertEqual(view["task_count"], 301)
        self.assertLessEqual(len(view["tasks"]), C.TASKS_MAX)
        self.assertTrue(all(len(t["last_error"]) < 600 for t in view["tasks"] if t["last_error"]))
        self.assertNotIn(secret, out)
        self.assertNotIn("EVENT-SECRET-DETAIL", out)
        self.assertIn("leak-test", [e["kind"] for e in view["events"]])
        self.assertNotIn("legacy_tasks", view)

    def test_status_stays_bounded_with_long_untrusted_event_fields(self):
        self.assertEqual(self.enqueue()[0], 0)
        store = R.Store(self.home)
        for i in range(40):
            store.event("k" * 30_000, task_id="t" * 30_000)  # tail window is 256 KiB, so keep lines small enough to survive it
        code, out, _ = self.run_ctl("status")
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out), C.OUT_MAX)
        events = json.loads(out)["events"]
        self.assertTrue(events)
        self.assertTrue(all(len(v) < 600 for e in events for v in e.values() if isinstance(v, str)))


    def test_status_returns_a_fixed_error_when_non_task_fields_alone_exceed_the_bound(self):
        self.assertEqual(self.enqueue()[0], 0)
        wide = {f"k{i}": {f"j{j}": "x" * 600 for j in range(100)} for i in range(100)}  # clips to ~100x100x500 chars
        with R.Store(self.home).txn() as st:
            st["usage"] = wide
        code, out, _ = self.run_ctl("status")
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out), C.OUT_MAX)
        self.assertEqual(json.loads(out), {"error": "status too large to display", "task_count": 1})


class EnqueueTests(Fixture):
    def test_valid_enqueue_goes_through_runner_with_owner_source(self):
        self.assertFalse(R.HANDOFF_ENABLED)
        code, out, err = self.enqueue({**SPEC, "title": "T", "verify_cmd": ["python3", "-V"], "max_attempts": 2})
        self.assertEqual((code, json.loads(out), err), (0, {"queued": "CTL-1"}, ""))
        t = self.tasks()["CTL-1"]
        self.assertEqual((t["status"], t["source"], t["attempts"], t["max_attempts"]), ("PENDING", "owner", 0, 2))
        self.assertEqual((t["allowed_paths"], t["verify_cmd"], t["title"]), (["src/"], ["python3", "-V"], "T"))

    def test_runner_validation_still_applies(self):
        for patch in ({"id": "bad id"}, {"id": "id\n"}, {"module": "MOD-999"}, {"role": "root"}, {"allowed_paths": ["/etc"]},
                      {"allowed_paths": ["../x"]}, {"prompt": " "}, {"max_attempts": True}):
            with self.subTest(patch=patch):
                code, out, err = self.enqueue({**SPEC, **patch})
                self.assertEqual((code, out), (2, ""))
                self.assertIn("enqueue refused", err)
        self.assertEqual(self.tasks(), {})

    def test_duplicate_id_and_legacy_id_refused(self):
        self.assertEqual(self.enqueue()[0], 0)
        self.assertEqual(self.enqueue()[0], 2)
        self.write_legacy({"OLD-1": {"id": "OLD-1", "status": "COMPLETED"}})
        self.write_proof(self.pin)
        code, _, err = self.enqueue({**SPEC, "id": "OLD-1"})
        self.assertEqual(code, 2)
        self.assertIn("preserved v1 history", err)

    def test_malformed_oversize_and_non_object_json_refused(self):
        cases = {"empty": b"", "garbage": b"{not json", "truncated": b'{"id": "CTL-1"', "array": b"[]", "scalar": b"1", "null": b"null",
                 "duplicate key": b'{"id": "CTL-1", "id": "CTL-2", "module": "MOD-002", "role": "review", "prompt": "p"}',
                 "nan": b'{"id": "CTL-1", "max_attempts": NaN}', "bad utf8": b'{"id": "\xff\xfe"}',
                 "deep nesting": b"[" * 100_000 + b"]" * 100_000,
                 "oversize": b'{"prompt": "' + b"a" * C.SPEC_MAX + b'"}'}
        for name, raw in cases.items():
            with self.subTest(name):
                code, out, err = self.run_ctl("enqueue", stdin=raw)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("enqueue refused", err)
                self.assertLess(len(err), 600)
        self.assertEqual(self.tasks(), {})

    def test_stdin_read_is_capped(self):
        class Endless:
            read_total = 0

            def read(self, n):
                self.read_total += n
                return b"x" * n

        s = Endless()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(C.main(["enqueue"], stdin=s), 2)
        self.assertEqual(s.read_total, C.SPEC_MAX + 1)

    def test_exact_field_allowlist(self):
        for extra in ("source", "status", "prompt_file", "cwd", "env", "home", "repo", "attempts", "child", "claude_bin", "seq"):
            with self.subTest(extra=extra):
                code, _, err = self.enqueue({**SPEC, extra: "openclaw" if extra == "source" else "/etc/passwd"})
                self.assertEqual(code, 2)
                self.assertIn("fields not accepted", err)
        self.assertEqual(self.tasks(), {})

    def test_error_text_is_bounded(self):
        code, _, err = self.enqueue({**SPEC, "allowed_paths": ["x" * 200_000 + "\n"]})
        self.assertEqual(code, 2)
        self.assertLess(len(err), 600)

    def test_shell_metacharacters_are_stored_verbatim_and_never_executed(self):
        marker = Path(self.tmp.name) / "pwned"
        payload = f"$(touch {marker}); `touch {marker}`; touch {marker} #\n'\"\\"
        self.assertEqual(self.enqueue({**SPEC, "title": payload, "prompt": payload})[0], 0)
        t = self.tasks()["CTL-1"]
        self.assertEqual((t["title"], t["prompt"]), (payload, payload))
        self.assertFalse(marker.exists())

    def test_fails_closed_without_a_valid_cutover_proof_or_matching_legacy_copy(self):
        proof = self.proof
        for name, setup in (
                ("missing", lambda: proof.unlink()),
                ("not json", lambda: self.write_proof(None, "{nope")),
                ("not object", lambda: self.write_proof(None, "[]")),
                ("wrong schema", lambda: self.write_proof(None, json.dumps({"schema": 2, "legacy_sha256": self.pin}))),
                ("short pin", lambda: self.write_proof(None, json.dumps({"schema": 1, "legacy_sha256": "abc"}))),
                ("upper pin", lambda: self.write_proof(None, json.dumps({"schema": 1, "legacy_sha256": self.pin.upper()}))),
                ("oversize", lambda: self.write_proof(None, " " * (R.CUTOVER_MAX + 1))),
                ("symlink", lambda: (proof.unlink(), proof.symlink_to(self.legacy))),
                ("copy mismatch", lambda: self.write_proof("0" * 64)),
                ("copy changed", lambda: self.legacy.write_bytes(self.legacy.read_bytes() + b" "))):
            with self.subTest(name):
                self.write_proof(self.pin)
                if self.legacy.read_bytes().endswith(b" "):
                    self.write_legacy({})
                setup()
                code, out, err = self.enqueue()
                self.assertEqual((code, out), (2, ""))
                self.assertIn("refused", err)
                self.assertEqual(self.tasks(), {})

    def test_other_verbs_do_not_need_the_cutover_proof(self):
        self.proof.unlink()
        self.assertEqual(self.run_ctl("pause")[0], 0)
        code, out, _ = self.run_ctl("status")
        self.assertEqual(code, 0)
        self.assertIn("legacy history unverified", json.loads(out)["legacy_error"])


class GuardTests(Fixture):
    patch_host = False

    def test_main_refuses_as_the_wrong_user_before_touching_state(self):
        self.write_proof(self.pin)
        for argv in (["status"], ["pause"], ["cancel", "x"], ["enqueue"]):
            with self.subTest(argv=argv):
                code, out, err = self.run_ctl(*argv, stdin=json.dumps(SPEC).encode())
                self.assertEqual((code, out), (C.EXIT_BOUNDARY, ""))
                self.assertTrue(err.startswith("refused:"))
        self.assertFalse((self.home / "v2").exists())

    def test_worker_problem(self):
        pw = mock.Mock(pw_uid=501)
        ok = dict(getuid=lambda: 501, geteuid=lambda: 501)
        cases = (("root", dict(getuid=lambda: 0, geteuid=lambda: 0)), ("euid root", dict(getuid=lambda: 501, geteuid=lambda: 0)),
                 ("split", dict(getuid=lambda: 501, geteuid=lambda: 502)), ("wrong user", dict(getuid=lambda: 502, geteuid=lambda: 502)))
        with mock.patch.object(C.pwd, "getpwnam", lambda n: pw if n == "veyroworker" else self.fail(n)):
            self.assertIsNone(self.problem(ok))
            for name, fns in cases:
                with self.subTest(name):
                    self.assertTrue(self.problem(fns))
        with mock.patch.object(C.pwd, "getpwnam", side_effect=KeyError("x")):
            self.assertIn("does not exist", self.problem(ok))

    @staticmethod
    def problem(fns):
        with mock.patch.multiple(C.os, **fns):
            return C.worker_problem()

    def test_env_problem_rejects_injection_vectors(self):
        for var in ("PYTHONPATH", "PYTHONSTARTUP", "pythonhome", "VEYRO_LEGACY_STATE", "VEYRO_CLAUDE_BIN", "VEYRO_RUNNER_HOME",
                    "DYLD_INSERT_LIBRARIES", "LD_PRELOAD", "GIT_DIR", "CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY"):
            with self.subTest(var=var):
                self.assertIn("not accepted", C.env_problem({"PATH": "/usr/bin", var: "x"}))
        self.assertIsNone(C.env_problem({"HOME": "/Users/veyroworker", "USER": "veyroworker", "LOGNAME": "veyroworker", "PATH": "/usr/bin"}))

    def test_env_injection_refused_before_state_is_touched(self):
        with mock.patch.object(C, "worker_problem", lambda: None), mock.patch.dict(os.environ, {"VEYRO_LEGACY_STATE": "/tmp/x"}):
            code, out, err = self.run_ctl("pause")
        self.assertEqual((code, out), (C.EXIT_BOUNDARY, ""))
        self.assertIn("environment", err)
        self.assertFalse((self.home / "v2").exists())

    def test_load_runner_requires_the_fixed_install_dir(self):
        with self.assertRaises(C.Refused):  # this file lives in tools/mission_runner, not the fixed install directory
            C.load_runner()
        with mock.patch.object(C, "INSTALL_DIR", Path(C.__file__).resolve().parent), \
                mock.patch.object(C, "install_tree_problem", lambda: None):  # the source dir has tests/; tree check is tested below
            self.assertIs(C.load_runner(), R)
        with mock.patch.object(C, "INSTALL_DIR", Path(C.__file__).resolve().parent / "nested"), self.assertRaises(C.Refused):
            C.load_runner()

    def test_load_runner_checks_the_tree_before_putting_it_on_sys_path_or_importing(self):
        here = Path(C.__file__).resolve().parent
        before = list(C.sys.path)
        with mock.patch.object(C, "INSTALL_DIR", here), mock.patch.object(C, "install_tree_problem", lambda: "RUNNER_INSTALL: planted"), \
                mock.patch.dict(C.sys.modules), self.assertRaises(C.Refused):
            C.sys.modules.pop("runner", None)
            C.load_runner()
            self.fail("unreachable")
        self.assertEqual(C.sys.path, before)

    def make_install(self, *, mode=0o644):
        d = Path(self.tmp.name) / "install"
        d.mkdir()
        for n in ("runner.py", "acceptance_receipt.py", "control.py", "module_catalog.json"):
            (d / n).write_text("x = 1\n")
            (d / n).chmod(mode)
        return d

    def test_install_tree_problem_refuses_planted_subdirs_and_unsafe_modules(self):
        self.assertIsNone(C.install_tree_problem(self.make_install()))
        d = Path(self.tmp.name) / "install"
        (d / "__pycache__").mkdir()
        self.assertIn("__pycache__", C.install_tree_problem(d))  # a planted .pyc dir would be read despite -B
        (d / "__pycache__").rmdir()
        self.assertIsNone(C.install_tree_problem(d))
        (d / "runner.py").chmod(0o664)
        self.assertIn("runner.py", C.install_tree_problem(d))
        (d / "runner.py").chmod(0o644)
        (d / "acceptance_receipt.py").chmod(0o606)
        self.assertIn("acceptance_receipt.py", C.install_tree_problem(d))
        (d / "acceptance_receipt.py").chmod(0o644)
        with mock.patch.object(C, "ROOT_UID", os.getuid() + 1):
            self.assertIn("root-owned", C.install_tree_problem(d))
        (d / "runner.py").unlink()
        (d / "runner.py").symlink_to(d / "control.py")  # a symlink is not a regular file under lstat
        self.assertIn("runner.py", C.install_tree_problem(d))
        (d / "runner.py").unlink()
        self.assertIn("cannot inspect", C.install_tree_problem(d))  # missing
        self.assertIn("cannot inspect", C.install_tree_problem(d / "nope"))

    def test_install_tree_checks_the_directory_its_ancestors_and_every_entry(self):
        d = self.make_install()
        self.assertIsNone(C.install_tree_problem(d))
        (d / "subprocess.py").write_text("planted = 1\n")  # a stdlib-shadowing module is just another entry: it must be root-owned too
        (d / "subprocess.py").chmod(0o666)
        self.assertIn("subprocess.py", C.install_tree_problem(d))
        (d / "subprocess.py").chmod(0o644)
        self.assertIsNone(C.install_tree_problem(d))
        (d / "link.py").symlink_to(d / "runner.py")
        self.assertIn("link.py", C.install_tree_problem(d))
        (d / "link.py").unlink()
        d.chmod(0o775)  # the directory itself group-writable: anyone in the group can plant a file
        self.assertIn("'install'", C.install_tree_problem(d))
        d.chmod(0o757)
        self.assertIn("'install'", C.install_tree_problem(d))
        d.chmod(0o755)
        self.assertIsNone(C.install_tree_problem(d))
        parent = d.parent
        parent.chmod(0o775)  # an ancestor: a rename-swap of the whole install
        try:
            self.assertIn(parent.name, C.install_tree_problem(d))
        finally:
            parent.chmod(0o700)
        nested = d / "sub"
        nested.mkdir()
        self.assertIn("'sub'", C.install_tree_problem(d))
        with mock.patch.object(C, "ROOT_UID", os.getuid() + 1):  # production-style ownership: nothing here is root's
            self.assertIn("root-owned", C.install_tree_problem(d))

    def test_the_install_directory_is_appended_after_the_standard_library(self):
        here = Path(C.__file__).resolve().parent
        with mock.patch.object(C, "INSTALL_DIR", here), mock.patch.object(C, "install_tree_problem", lambda: None), \
                mock.patch.object(C.sys, "path", [p for p in C.sys.path if p != str(here)]):
            before = list(C.sys.path)
            C.load_runner()
            self.assertEqual(C.sys.path, before + [str(here)])
            self.assertNotEqual(C.sys.path[0], str(here))

    def test_enqueue_refuses_an_unsafe_parent_chain_for_proof_legacy_state_or_evidence(self):
        for name, path in (("proof", self.proof), ("legacy state", self.legacy), ("evidence", C.LEGACY_EVIDENCE)):
            with self.subTest(name), mock.patch.object(C, "worker_problem", lambda: None), mock.patch.object(C, "load_runner", lambda: R), \
                    mock.patch.object(R, "runner_install_problem", return_value=None), \
                    mock.patch.object(R, "worker_boundary_problem", return_value=None), \
                    mock.patch.object(R, "host_problem", return_value=None) as host:
                parent = path.parent
                parent.chmod(0o775)
                try:
                    code, out, err = self.enqueue()
                finally:
                    parent.chmod(0o755)
                self.assertEqual((code, out), (C.EXIT_BOUNDARY, ""), name)
                self.assertIn("parent chain is unsafe", err)
                host.assert_not_called()
        self.assertEqual(self.tasks(), {})

    def test_enqueue_refuses_a_proof_parent_that_is_not_root_owned(self):
        with mock.patch.object(C, "worker_problem", lambda: None), mock.patch.object(C, "load_runner", lambda: R), \
                mock.patch.object(R, "runner_install_problem", return_value=None), \
                mock.patch.object(R, "worker_boundary_problem", return_value=None), \
                mock.patch.object(R, "host_problem", return_value=None), mock.patch.object(C, "ROOT_UID", os.getuid() + 1):
            code, out, err = self.enqueue()
        self.assertEqual((code, out), (C.EXIT_BOUNDARY, ""))
        self.assertIn("parent chain is unsafe", err)

    def test_runner_install_problem_refusal_is_enforced(self):
        self.write_proof(self.pin)
        with mock.patch.object(C, "worker_problem", lambda: None), mock.patch.object(C, "load_runner", lambda: R), \
                mock.patch.object(R, "runner_install_problem", return_value="RUNNER_INSTALL: not root-owned") as p:
            code, out, err = self.run_ctl("pause")
        self.assertEqual((code, out), (C.EXIT_BOUNDARY, ""))
        self.assertIn("RUNNER_INSTALL", err)
        self.assertEqual(p.call_args.args[1], C.INSTALL_DIR)
        self.assertFalse((self.home / "v2").exists())

    def test_worker_home_boundary_refusal_is_enforced(self):
        with mock.patch.object(C, "worker_problem", lambda: None), mock.patch.object(C, "load_runner", lambda: R), \
                mock.patch.object(R, "runner_install_problem", return_value=None), \
                mock.patch.object(R, "worker_boundary_problem", return_value="WORKER_BOUNDARY: owner home traversable"):
            code, out, err = self.run_ctl("pause")
        self.assertEqual((code, out), (C.EXIT_BOUNDARY, ""))
        self.assertIn("WORKER_BOUNDARY", err)
        self.assertFalse((self.home / "v2").exists())

    def test_enqueue_requires_full_host_cutover_predicate(self):
        with mock.patch.object(C, "worker_problem", lambda: None), mock.patch.object(C, "load_runner", lambda: R), \
                mock.patch.object(R, "runner_install_problem", return_value=None), \
                mock.patch.object(R, "worker_boundary_problem", return_value=None), \
                mock.patch.object(R, "host_problem", return_value="CUTOVER_PROOF: v1 still running"):
            code, out, err = self.enqueue()
        self.assertEqual((code, out), (C.EXIT_BOUNDARY, ""))
        self.assertIn("CUTOVER_PROOF", err)
        self.assertFalse((self.home / "v2").exists())

    def test_real_install_check_refuses_this_unprotected_checkout(self):
        cfg = C.build_config(R, strict=False)
        why = R.runner_install_problem(cfg, Path(C.__file__).resolve().parent)
        self.assertIn("RUNNER_INSTALL", why)  # user-owned, not root

    def test_config_is_built_from_constants_not_environment(self):
        hostile = {"VEYRO_RUNNER_HOME": "/tmp/evil", "VEYRO_LEGACY_STATE": "/tmp/evil", "VEYRO_LEGACY_SHA256": "1" * 64,
                   "VEYRO_CLAUDE_BIN": "/tmp/evil", "VEYRO_CLAUDE_SHA256": "2" * 64, "VEYRO_CLAUDE_VERSION": "0",
                   "VEYRO_OWNER_HOME": "/tmp/evil", "VEYRO_LEGACY_EVIDENCE": "/tmp/evil", "VEYRO_MODEL_SONNET": "evil-opus",
                   "VEYRO_MODEL_OPUS": "evil-sonnet"}
        with mock.patch.dict(os.environ, hostile):
            cfg = C.build_config(R, strict=True)
        self.assertEqual((cfg.home, cfg.repo, cfg.legacy_state, cfg.legacy_sha256), (self.home, self.repo, self.legacy, self.pin))
        self.assertEqual((cfg.claude_bin, cfg.claude_sha256, cfg.claude_version),
                         (str(C.CLAUDE_BIN), C.CLAUDE_SHA256, C.CLAUDE_VERSION))
        self.assertEqual((cfg.owner_home, cfg.legacy_evidence, cfg.cutover_proof),
                         (C.OWNER_HOME, C.LEGACY_EVIDENCE, self.proof))
        self.assertEqual(cfg.models, {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"})

    def test_production_constants_are_the_pinned_ones(self):
        import importlib
        fresh = importlib.reload(C)  # undo this fixture's constant patches for the check
        try:
            self.assertEqual(fresh.CLAUDE_SHA256, "75e3016e9d2570767b08e43a7467d4817a4f149232c169ca295f2c95fef21433")
            self.assertEqual((fresh.CLAUDE_VERSION, str(fresh.REPO), str(fresh.HOME), str(fresh.OWNER_HOME)),
                             ("2.1.286", "/Users/Shared/veyroworker/veyro", "/Users/Shared/veyroworker/mission-runner",
                              "/Users/ahmadmabrouk"))
            self.assertEqual(str(fresh.INSTALL_DIR), "/Library/Application Support/Veyro/release-v2-ctl1/runner")
            self.assertEqual(str(fresh.CLAUDE_BIN), "/Library/Application Support/Veyro/release-v2-ctl1/bin/claude")
            self.assertEqual(str(fresh.CUTOVER_PROOF), "/Library/Application Support/Veyro/legacy-2026-10-29/cutover.json")
            self.assertEqual(fresh.ROOT_UID, 0)
            self.assertNotIn(str(fresh.HOME), str(fresh.CUTOVER_PROOF))
        finally:
            for k, v in dict(HOME=self.home, REPO=self.repo, LEGACY_STATE=self.legacy, CUTOVER_PROOF=self.proof,
                                ROOT_UID=os.getuid()).items():
                setattr(C, k, v)


class CutoverProofOwnershipTests(Fixture):
    def test_proof_must_be_root_owned_regular_and_not_group_or_other_writable(self):
        self.assertEqual(C.read_pin(R.CUTOVER_MAX), self.pin)
        for mode in (0o664, 0o646, 0o666, 0o620):
            with self.subTest(mode=oct(mode)):
                self.proof.chmod(mode)
                with self.assertRaisesRegex(ValueError, "root-owned and unwritable"):
                    C.read_pin(R.CUTOVER_MAX)
        self.proof.chmod(0o644)
        with mock.patch.object(C, "ROOT_UID", os.getuid() + 1), self.assertRaisesRegex(ValueError, "root-owned and unwritable"):
            C.read_pin(R.CUTOVER_MAX)  # a worker-owned (non-root) proof is a forgeable single-writer claim
        code, out, err = self.run_ctl("pause")  # other verbs still work without a trustworthy proof
        self.assertEqual(code, 0)
        self.proof.chmod(0o666)
        code, out, err = self.enqueue()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("cutover proof", err)
        self.assertEqual(self.tasks(), {})

    def test_proof_symlink_or_directory_is_refused(self):
        self.proof.unlink()
        self.proof.symlink_to(self.legacy)
        with self.assertRaises(ValueError):
            C.read_pin(R.CUTOVER_MAX)
        self.proof.unlink()
        self.proof.mkdir()
        with self.assertRaises(ValueError):
            C.read_pin(R.CUTOVER_MAX)

    def test_proof_parent_chain_is_checked_by_read_pin_too(self):
        self.proof.parent.chmod(0o775)
        try:
            with self.assertRaisesRegex(ValueError, "unsafe parent chain"):
                C.read_pin(R.CUTOVER_MAX)
            code, out, _ = self.run_ctl("status")  # status must not display a legacy copy pinned by an untrusted proof
            self.assertEqual(code, 0)
            self.assertIn("legacy history unverified", json.loads(out)["legacy_error"])
        finally:
            self.proof.parent.chmod(0o755)
        self.assertEqual(C.read_pin(R.CUTOVER_MAX), self.pin)

    def test_proof_lives_outside_the_worker_home(self):
        self.assertNotIn(self.home, self.proof.parents)


class StaticBoundaryTests(unittest.TestCase):
    def test_control_has_no_subprocess_shell_or_network_surface(self):
        tree = ast.parse(Path(C.__file__).read_text())
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse(imported & {"subprocess", "socket", "urllib", "http", "ssl", "shlex", "ctypes", "importlib"}, imported)
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertFalse(names & {"system", "popen", "execv", "execve", "spawn", "eval", "exec", "__import__", "HANDOFF_ENABLED"}, names)

    def test_launcher_is_fixed_and_passes_arguments_only_as_quoted_args(self):
        path = Path(C.__file__).parent / "veyro-ctl"
        text = path.read_text()
        self.assertTrue(os.access(path, os.X_OK))
        self.assertEqual(subprocess.run(["sh", "-n", str(path)]).returncode, 0)
        self.assertIn("exec /usr/bin/env -i", text)
        self.assertIn("/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3.9 -I -S -B", text)
        self.assertIn('"/Library/Application Support/Veyro/release-v2-ctl1/runner/control.py" "$@"', text)
        for env in ("HOME=/Users/veyroworker", "USER=veyroworker", "LOGNAME=veyroworker"):
            self.assertIn(env, text)
        body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        self.assertEqual(body.count("$"), 1)  # only the single "$@"
        self.assertNotRegex(body, r"\b(eval|source|sudo|sh -c|bash)\b|`")


if __name__ == "__main__":
    unittest.main()
