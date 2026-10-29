"""Dashboard projection of v2 tasks plus the read-only v1 history adapter."""
import hashlib
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import dashboard
import runner as R


def task(tid, status, seq, module="MOD-002", role="implement", **kw):
    return {"id": tid, "module": module, "role": role, "title": tid, "status": status, "seq": seq, **kw}


def git_repo(path, commit=False):
    import subprocess
    run = lambda *a: subprocess.run(["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                    check=True, capture_output=True)
    if commit:
        run("add", "-A")
        run("commit", "-q", "--allow-empty", "-m", "c")
    else:
        run("init", "-q", "-b", "main")
        catalog = Path(path) / "tools/mission_runner/module_catalog.json"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_bytes(R.CATALOG_PATH.read_bytes())


class ProjectionTests(unittest.TestCase):
    def test_denied_agent_tool_request_is_visible(self):
        projected = dashboard.task_projection([task("w", "COMPLETED", 1, result={"permission_denied": True})])
        self.assertTrue(projected[0]["permission_denied"])

    def test_v2_statuses_are_shown_honestly(self):
        tasks = dashboard.task_projection([task("a", "COMPLETED", 1), task("b", "FAILED", 2, reason="VERIFY_FAILED"),
                                           task("c", "PENDING", 3, waiting="waiting for b (FAILED)"),
                                           task("d", "CANCELLED", 4)])
        self.assertEqual([t["lane"] for t in tasks], ["COMPLETED", "FAILED", "PENDING", "CANCELLED"])
        failed = tasks[1]
        self.assertEqual((failed["lifecycle"], failed["blocked_reason"]), ("active-blocker", "VERIFY_FAILED"))
        self.assertEqual(tasks[2]["waiting"], "waiting for b (FAILED)")

    def test_failed_task_is_never_resolved_by_unrelated_later_work_only_by_a_linked_remediation(self):
        tasks = dashboard.task_projection([task("a", "FAILED", 1), task("x", "COMPLETED", 2, module="MOD-003"),
                                           task("b", "COMPLETED", 3)])  # later same-module completion proves nothing
        self.assertEqual(tasks[0]["lifecycle"], "active-blocker")
        tasks = dashboard.task_projection([task("a", "FAILED", 1), task("c", "COMPLETED", 2, remediates="a")])
        self.assertEqual((tasks[0]["lifecycle"], tasks[0]["history_reason"]), ("historical", "Remediated by completed task c"))
        tasks = dashboard.task_projection([task("a", "FAILED", 1), task("c", "FAILED", 2, remediates="a")])
        self.assertEqual(tasks[0]["lifecycle"], "active-blocker")

    def test_owner_action_is_separate_from_routine_failures_and_surfaces_waiting_for_owner(self):
        snap = {"tasks": [task("a", "FAILED", 1, reason="VERIFY_FAILED"), task("b", "FAILED", 2, reason="HEAD_MOVED")],
                "events": []}
        state = dashboard.build_state(snap, Path("/nonexistent"))
        self.assertEqual([t["id"] for t in state["active_blockers"]], ["a", "b"])
        self.assertEqual([t["id"] for t in state["owner_action_blockers"]], ["b"])
        self.assertEqual({t["id"]: t["kind"] for t in state["active_blockers"]}, {"a": "routine", "b": "owner"})
        waiting = dashboard.build_state({"tasks": [], "runner_alive": True, "control": "RUN", "events": [],
                                         "handoff": {"status": "waiting_for_owner", "detail": "WAITING_FOR_OWNER: approve X"}},
                                        Path("/nonexistent"))
        self.assertEqual([t["id"] for t in waiting["owner_action_blockers"]], ["handoff"])
        self.assertIn("approve X", waiting["owner_action_blockers"][0]["last_error"])
        self.assertEqual(waiting["runner_execution"], "waiting_for_owner")
        unproven = dashboard.build_state({"tasks": [], "events": [], "handoff": {
            "status": "blocked", "detail": "PLANNER_POLICY_UNPROVEN: x"}}, Path("/nonexistent"))
        self.assertEqual([t["id"] for t in unproven["owner_action_blockers"]], ["handoff"])

    def test_unresolved_legacy_blockers_are_visible_context_but_not_runner_blockers(self):
        legacy = [{"id": "o1", "module": "MOD-004", "role": "implement", "title": "Old", "status": "BLOCKED",
                   "blocked_reason": "D16 rejected"},
                  {"id": "o2", "module": "MOD-004", "role": "implement", "title": "Done", "status": "DONE"}]
        state = dashboard.build_state({"tasks": [], "legacy_tasks": legacy, "events": []}, Path("/nonexistent"))
        self.assertEqual([t["id"] for t in state["legacy_unresolved"]], ["o1"])
        self.assertEqual((state["active_blockers"], state["owner_action_blockers"]), ([], []))

    def test_legacy_tasks_are_history_never_blockers_or_actionable(self):
        legacy = [{"id": "old", "module": "MOD-004", "role": "implement", "title": "Old", "status": "QUEUED"},
                  {"id": "old2", "module": "MOD-004", "role": "code-review", "title": "Old2", "status": "BLOCKED"}]
        state = dashboard.build_state({"tasks": [task("n", "PENDING", 1)], "legacy_tasks": legacy, "events": []},
                                      Path("/nonexistent"))
        self.assertEqual(state["legacy_count"], 2)
        self.assertEqual([t["id"] for t in state["actionable_tasks"]], ["n"])
        self.assertEqual(state["active_blockers"], [])
        old = [t for t in state["tasks"] if t["legacy"]]
        self.assertTrue(all(t["lane"] == "LEGACY" and t["lifecycle"] == "historical" for t in old))
        self.assertEqual(old[1]["status"], "BLOCKED")  # original status preserved, not rewritten

    def test_module_and_runner_projection(self):
        snap = {"tasks": [task("r", "RUNNING", 1, started_at="2026-10-29T10:00:00+00:00")], "runner_alive": True,
                "writer_lock": {"state": "held"}, "control": "RUN", "events": []}
        state = dashboard.build_state(snap, Path("/nonexistent"))
        self.assertEqual((state["current_module"], state["runner_execution"]), ("MOD-002", "running"))
        self.assertEqual([a["status"] for a in state["agents"]], ["working", "idle"])
        review = dashboard.build_state({**snap, "tasks": [task("r", "RUNNING", 1, role="review")]}, Path("/nonexistent"))
        self.assertEqual([a["status"] for a in review["agents"]], ["idle", "working"])
        self.assertEqual(dashboard.build_state({"tasks": [], "control": "PAUSE"}, Path("/x"))["runner_execution"], "paused")

    def test_recorded_certificate_condition_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            git_repo(tmp)
            root = Path(tmp) / "knowledge" / "03-Modules"
            for mid, header in [("MOD-000", "**Status: ACCEPTED — LEAN FOUNDATION.** gatekeeper approved"),
                                ("MOD-001", "**Status: ACCEPTED — FOUNDATION ONLY.**")]:
                (root / mid).mkdir(parents=True)
                (root / mid / f"{mid}.md").write_text(f"# {mid}\n\n{header}\n")
            (root / "MOD-001" / "APPROVAL.md").write_text("# Approval\n\n**Status: APPROVED — ACTIVATION PENDING OWN CI.**\n")
            git_repo(tmp, commit=True)
            records = dashboard.module_records(Path(tmp))
            self.assertTrue(records["MOD-000"]["accepted"])
            self.assertIn("pending", records["MOD-001"]["discrepancy"])

    def test_conditional_acceptance_is_neither_green_nor_counted(self):
        cond = "**Status: ACCEPTED — FOUNDATION ONLY, CONDITIONAL ON OWN EXACT-SHA PUSH CI.**"
        with tempfile.TemporaryDirectory() as tmp:
            git_repo(tmp)
            root = Path(tmp) / "knowledge" / "03-Modules"
            for mid, header in [("MOD-000", "**Status: ACCEPTED — LEAN FOUNDATION.** gatekeeper approved"), ("MOD-002", cond)]:
                (root / mid).mkdir(parents=True)
                (root / mid / f"{mid}.md").write_text(f"# {mid}\n\n{header}\n")
            git_repo(tmp, commit=True)
            records = dashboard.module_records(Path(tmp))
            self.assertTrue(records["MOD-000"]["accepted"])
            two = records["MOD-002"]
            self.assertEqual((two["accepted"], two["recorded_accepted"], two["conditional"], two["header_accepted"]),
                             (False, False, True, True))
            self.assertIn("conditionally", two["discrepancy"])
            catalog = [{"id": "MOD-000"}, {"id": "MOD-002"}]
            _, modules = dashboard.module_projection(catalog, records, [])
            self.assertEqual(modules, {"MOD-000": "accepted", "MOD-002": "conditional"})
            state = dashboard.build_state({"tasks": []}, Path(tmp))
            self.assertEqual((state["accepted_count"], state["recorded_accepted_count"], state["conditional_count"]), (1, 1, 1))

    def test_escaped_process_failures_are_owner_actions(self):
        snap = {"tasks": [task("a", "FAILED", 1, reason="ESCAPED_PROCESS")], "events": []}
        state = dashboard.build_state(snap, Path("/nonexistent"))
        self.assertEqual([t["id"] for t in state["owner_action_blockers"]], ["a"])

    def test_module_records_come_from_head_not_the_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            git_repo(tmp)
            rec = Path(tmp) / "knowledge/03-Modules/MOD-004/MOD-004.md"
            rec.parent.mkdir(parents=True)
            rec.write_text("# MOD-004\n\n**Status: IN PROGRESS.**\n")
            git_repo(tmp, commit=True)
            rec.write_text("# MOD-004\n\n**Status: ACCEPTED — forged by a failed write.**\n")  # uncommitted
            self.assertFalse(dashboard.module_records(Path(tmp))["MOD-004"]["accepted"])


class ApiTests(unittest.TestCase):
    def test_api_state_serves_v2_queue_and_legacy_history_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, repo = Path(tmp) / "home", Path(tmp) / "repo"
            home.mkdir()
            repo.mkdir()
            git_repo(repo)
            git_repo(repo, commit=True)
            legacy = json.dumps({"schema": 1, "tasks": {"old": {"id": "old", "module": "MOD-004", "role": "implement",
                                 "title": "Old", "status": "DONE"}}}).encode()
            legacy_path = Path(tmp) / "legacy-state.json"
            legacy_path.write_bytes(legacy)
            cfg = R.Config(home=home, repo=repo, module_order=False, legacy_state=str(legacy_path),
                           legacy_sha256=hashlib.sha256(legacy).hexdigest())
            R.enqueue(cfg, {"id": "n", "module": "MOD-002", "role": "implement", "prompt": "p", "allowed_paths": ["src/"]})
            with R.Store(home).txn() as st:
                R.Runner(cfg).handoff_update(st, status="blocked", detail="BLOCKED: needs owner", fingerprint="ab" * 32)
            srv = dashboard.make_server(cfg, 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            port = srv.server_address[1]

            def call(method, path):
                c = HTTPConnection("127.0.0.1", port)
                c.request(method, path)
                r = c.getresponse()
                return r.status, r.read()

            status, body = call("GET", "/api/state")
            data = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual({t["id"]: t["lane"] for t in data["tasks"]}, {"n": "PENDING", "old": "LEGACY"})
            self.assertEqual((data["handoff"]["status"], data["handoff"]["detail"]), ("blocked", "BLOCKED: needs owner"))
            self.assertEqual(data["handoff"]["fingerprint"], "ab" * 6)
            self.assertEqual(call("GET", "/app.js")[0], 200)
            self.assertEqual(call("POST", "/api/state")[0], 405)
            self.assertEqual(legacy_path.read_bytes(), legacy)
            self.assertFalse((home / "events.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
