import tempfile
from datetime import datetime
import unittest
import subprocess
from pathlib import Path
from unittest import mock
import dashboard


class DashboardProjectionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = dashboard.CATALOG
        self.records = {"MOD-000": {"accepted": True}, "MOD-001": {"accepted": True}}
        self.tasks = [
            {"id": "old-review", "module": "MOD-001", "role": "code-review", "title": "Old review",
             "status": "BLOCKED", "blocked_reason": "REVIEW_CHANGES_REQUESTED", "route": None, "evidence": None},
            {"id": "current", "module": "MOD-002", "role": "implement", "title": "Validator",
             "status": "RUNNING", "started_at": "2026-10-16T10:08:33+00:00", "route": None, "evidence": None},
        ]

    def test_recorded_decisions_survive_stale_ci_but_current_head_guard_closes(self):
        snapshot = {"tasks": self.tasks, "events": [], "ci": {"state": "stale", "error": "github-api-timeout"}}
        old = dashboard.module_records
        dashboard.module_records = lambda repo: self.records
        try:
            state = dashboard.build_state(snapshot, Path('/unneeded'))
        finally:
            dashboard.module_records = old
        self.assertEqual(state['recorded_accepted_count'], 2)
        self.assertEqual(state['accepted_count'], 0)
        self.assertFalse(state['module_records']['MOD-001']['accepted'])
        self.assertTrue(state['module_records']['MOD-001']['recorded_accepted'])
        self.assertEqual(state['total_modules'], 75)
        self.assertEqual(state['ci']['state'], 'stale')
        self.assertEqual(state['current_module'], 'MOD-002')

    @staticmethod
    def _epoch(text):
        return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()

    def _blocked(self, finished='2026-10-16T10:00:00Z', **extra):
        return dict(self.tasks[0], module='MOD-002', finished_at=finished,
                    updated_at=finished, created_at='2026-10-16T09:00:00Z', **extra)

    def _record(self, written, accepted=True):
        return {"MOD-002": {"accepted": accepted, "recorded_accepted": accepted,
                            "updated_at": self._epoch(written) if isinstance(written, str) else written}}

    def test_accepted_module_blocked_task_is_historical(self):
        records = {"MOD-001": dict(self.records["MOD-001"], updated_at=self._epoch('2026-10-16T12:00:00Z'))}
        old = dict(self.tasks[0], updated_at='2026-10-16T10:00:00Z')
        tasks = dashboard.task_projection([old, self.tasks[1]], records)
        self.assertEqual(tasks[0]['lifecycle'], 'historical')
        self.assertEqual(tasks[0]['history_reason'], 'Module subsequently accepted')
        self.assertEqual(tasks[1]['lifecycle'], 'running')
        self.assertEqual(dashboard.module_projection(self.catalog, records, tasks)[0], 'MOD-002')

    def test_blocked_task_after_conditional_record_remains_active(self):
        blocked = self._blocked(finished='2026-10-16T12:00:00Z')
        projected = dashboard.task_projection([blocked], self._record('2026-10-16T11:00:00Z'))
        self.assertEqual(projected[0]['lifecycle'], 'active-blocker')

    def test_record_written_after_block_makes_it_historical(self):
        blocked = self._blocked()
        projected = dashboard.task_projection([blocked], self._record('2026-10-16T11:00:00Z'))
        self.assertEqual(projected[0]['lifecycle'], 'historical')
        self.assertEqual(projected[0]['history_reason'], 'Module subsequently accepted')

    def test_missing_or_malformed_dates_fail_closed(self):
        record = self._record('2026-10-16T11:00:00Z')
        for blocked in (self._blocked(finished='not-a-date'), self._blocked(finished='2026-10-16T10:00:00'),
                        dict(self._blocked(), updated_at=None, finished_at=None)):
            self.assertEqual(dashboard.task_projection([blocked], record)[0]['lifecycle'], 'active-blocker')
        for written in (None, 'bad'):
            rec = {"MOD-002": {"recorded_accepted": True, "updated_at": written}}
            self.assertEqual(dashboard.task_projection([self._blocked()], rec)[0]['lifecycle'], 'active-blocker')

    def test_later_work_supersedes_block_despite_earlier_record(self):
        blocked = self._blocked(finished='2026-10-16T12:00:00Z')
        later = dict(self.tasks[1], module='MOD-002', status='QUEUED', created_at='2026-10-16T13:00:00Z')
        projected = dashboard.task_projection([blocked, later], self._record('2026-10-16T11:00:00Z'))
        self.assertEqual(projected[0]['lifecycle'], 'historical')
        self.assertIn('formal resolution not recorded', projected[0]['history_reason'])

    def _conditional_projection(self, current_head):
        records = {"MOD-000": {"accepted": False, "recorded_accepted": True},
                   "MOD-001": {"accepted": False, "recorded_accepted": True},
                   "MOD-002": {"accepted": current_head, "recorded_accepted": True}}
        tasks = [dict(self.tasks[1], id="t1", status="DONE", created_at="2026-10-16T10:00:00Z"),
                 dict(self.tasks[1], id="t2", status="QUEUED", created_at="2026-10-16T11:00:00Z")]
        projected = dashboard.task_projection(tasks[::-1], records)
        return dashboard.module_projection(self.catalog, records, projected)

    def test_unverified_conditional_module_is_current_with_latest_task(self):
        active, modules = self._conditional_projection(False)
        self.assertEqual(active, 'MOD-002')
        self.assertEqual(modules['MOD-002'], 'current')
        self.assertEqual(modules['MOD-000'], 'accepted')
        self.assertEqual(modules['MOD-001'], 'accepted')

    def test_current_head_verified_module_with_no_other_task_has_no_current_module(self):
        active, modules = self._conditional_projection(True)
        self.assertIsNone(active)
        self.assertEqual(modules['MOD-002'], 'accepted')
        self.assertEqual(modules['MOD-000'], 'accepted')

    def test_unaccepted_module_blocked_task_remains_actionable(self):
        item = dict(self.tasks[0], module='MOD-003')
        self.assertEqual(dashboard.task_projection([item], self.records)[0]['lifecycle'], 'active-blocker')

    def test_later_work_removes_old_blocker_from_current_count_without_claiming_resolution(self):
        old = dict(self.tasks[0], module='MOD-003')
        later = dict(self.tasks[1], module='MOD-003', status='DONE')
        projected = dashboard.task_projection([old, later], self.records)
        self.assertEqual(projected[0]['lifecycle'], 'historical')
        self.assertIn('formal resolution not recorded', projected[0]['history_reason'])
        self.assertFalse(any(t['lifecycle'] == 'active-blocker' for t in projected))

    def test_blocker_lifecycle_uses_timestamps_not_sorted_task_ids(self):
        old = dict(self.tasks[0], id='z-review', module='MOD-003', created_at='2026-10-16T10:00:00Z')
        later = dict(self.tasks[1], id='a-correction', module='MOD-003', status='DONE',
                     created_at='2026-10-16T11:00:00Z')
        projected = dashboard.task_projection([later, old], self.records)
        self.assertEqual([t['id'] for t in projected], ['z-review', 'a-correction'])
        self.assertEqual(projected[0]['lifecycle'], 'historical')

    def test_review_request_is_not_automatically_an_owner_action(self):
        old = dict(self.tasks[0], module='MOD-003')
        old['blocked_reason'] = 'REVIEW_CHANGES_REQUESTED'
        snapshot = {'tasks': [old], 'events': [], 'ci': None}
        original = dashboard.module_records
        dashboard.module_records = lambda repo: self.records
        try:
            state = dashboard.build_state(snapshot, Path('/unneeded'))
        finally:
            dashboard.module_records = original
        self.assertEqual(len(state['active_blockers']), 1)
        self.assertEqual(state['owner_action_blockers'], [])

    def test_baseline_health_blocker_is_counted_and_actionable(self):
        snapshot = {'tasks': [], 'events': [], 'ci': None,
                    'health': {'status': 'BLOCKED', 'code': 'BASELINE_MISMATCH', 'detail': 'Pinned SHA changed'},
                    'runner_alive': True, 'control': 'RUN'}
        original = dashboard.module_records
        dashboard.module_records = lambda repo: {}
        try:
            state = dashboard.build_state(snapshot, Path('/unneeded'))
        finally:
            dashboard.module_records = original
        self.assertEqual(state['runner_execution'], 'blocked')
        self.assertEqual(len(state['active_blockers']), 1)
        self.assertEqual(state['owner_action_blockers'][0]['blocked_reason'], 'BASELINE_MISMATCH')

    def test_current_head_guard_requires_fresh_exact_success_and_clean_worktree(self):
        ci = {'state': 'fresh', 'scope': 'main-push', 'branch': 'main', 'head_matches_local': True,
              'head_sha': 'abc', 'runs': [{'event': 'push', 'ref': 'main', 'head_sha': 'abc',
                                         'name': 'Veyro Foundation CI', 'status': 'completed',
                                         'conclusion': 'success'}]}
        records = {'MOD-001': {'accepted': True, 'recorded_accepted': True}}
        self.assertTrue(dashboard.gate_module_records(records, ci, True)['MOD-001']['accepted'])
        self.assertFalse(dashboard.gate_module_records(records, ci, False)['MOD-001']['accepted'])
        run = ci['runs'][0]
        for mutation in ({'state': 'stale'}, {'error': 'timeout'}, {'head_matches_local': False},
                         {'head_sha': 'wrong'}, {'runs': []}, {'branch': 'feature/x'}, {'scope': None},
                         {'runs': [run | {'event': 'pull_request'}]},
                         {'runs': [run | {'ref': 'feature/x'}]},
                         {'runs': [run | {'name': 'Deploy Docs'}]},
                         {'runs': [run | {'name': 'veyro foundation ci'}]},
                         {'runs': [run, run | {'name': 'Other', 'status': 'queued', 'conclusion': None}]}):
            with self.subTest(mutation=mutation):
                self.assertFalse(dashboard.gate_module_records(records, ci | mutation, True)['MOD-001']['accepted'])
        for status, conclusion in (('in_progress', None), ('completed', 'failure')):
            with self.subTest(status=status):
                altered = ci | {'runs': [ci['runs'][0] | {'status': status, 'conclusion': conclusion}]}
                self.assertFalse(dashboard.gate_module_records(records, altered, True)['MOD-001']['accepted'])
        nonaccepted = {'MOD-002': {'accepted': False, 'recorded_accepted': False}}
        self.assertFalse(dashboard.gate_module_records(nonaccepted, ci, True)['MOD-002']['accepted'])

    def test_worktree_clean_fails_closed_on_git_failure_timeout_and_missing_git(self):
        self.assertFalse(dashboard.worktree_clean(Path('/nonexistent')))
        for error in (subprocess.TimeoutExpired('git', 2), FileNotFoundError('git')):
            with self.subTest(error=type(error).__name__), mock.patch.object(dashboard.subprocess, 'run', side_effect=error):
                self.assertFalse(dashboard.worktree_clean(Path('/unneeded')))

    def test_build_state_positive_and_dirty_worktree_current_head_paths(self):
        ci = {'state': 'fresh', 'scope': 'main-push', 'branch': 'main', 'head_matches_local': True,
              'head_sha': 'abc', 'runs': [{'event': 'push', 'ref': 'main', 'head_sha': 'abc',
                                         'name': 'Veyro Foundation CI', 'status': 'completed',
                                         'conclusion': 'success'}]}
        records = {'MOD-001': {'accepted': True, 'recorded_accepted': True}}
        snapshot = {'tasks': [], 'events': [], 'ci': ci}
        with mock.patch.object(dashboard, 'module_records', return_value=records), \
             mock.patch.object(dashboard, 'worktree_clean', return_value=True):
            accepted = dashboard.build_state(snapshot, Path('/unneeded'))
        self.assertEqual(accepted['accepted_count'], 1)
        self.assertEqual(accepted['recorded_accepted_count'], 1)
        self.assertTrue(accepted['module_records']['MOD-001']['accepted'])
        with mock.patch.object(dashboard, 'module_records', return_value=records), \
             mock.patch.object(dashboard, 'worktree_clean', return_value=False):
            dirty = dashboard.build_state(snapshot, Path('/unneeded'))
        self.assertEqual(dirty['accepted_count'], 0)
        self.assertEqual(dirty['recorded_accepted_count'], 1)
        self.assertFalse(dirty['module_records']['MOD-001']['accepted'])

    def test_active_model_requires_dispatch_and_live_child(self):
        tasks = dashboard.task_projection(self.tasks, self.records)
        state = {"runner_alive": True, "writer_lock": {"state": "held", "child_alive": True},
                 "events": [{"kind": "dispatch", "task_id": "current", "model_alias": "sonnet"}]}
        agents = dashboard.agent_projection(state, tasks)
        self.assertEqual([a['status'] for a in agents], ['unknown', 'working', 'idle'])
        self.assertIn('Actual model UNKNOWN', agents[1]['identity'])
        self.assertIsNone(tasks[1]['model'])
        state['writer_lock']['child_alive'] = False
        self.assertEqual(dashboard.agent_projection(state, tasks)[1]['status'], 'idle')

    def test_orchestrator_identity_comes_only_from_receipt(self):
        tasks = dashboard.task_projection(self.tasks, self.records)
        state = {"runner_alive": True, "writer_lock": {"state": "free"}, "events": []}
        self.assertEqual(dashboard.agent_projection(state, tasks)[0]['identity'],
                         'UNKNOWN · no orchestrator receipt')
        state['orchestrator'] = {"identity": "OpenClaw-hosted Codex session", "model": "openai/gpt-6-sol",
                                 "state": "waiting", "decision": "Review queued", "decision_at": "2026-10-16T10:43:00Z",
                                 "worker_task_id": "current", "age_s": 5, "evidence": "recorded"}
        agent = dashboard.agent_projection(state, tasks)[0]
        self.assertEqual(agent['status'], 'waiting')
        self.assertIn('openai/gpt-6-sol', agent['identity'])
        state['orchestrator']['worker_task_id'] = 'old-review'
        self.assertEqual(dashboard.agent_projection(state, tasks)[0]['status'], 'unknown')

    def test_orchestrator_receipt_fails_closed_without_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(dashboard.runner.orchestrator_receipt(tmp)['model'], 'UNKNOWN')
            path = Path(tmp) / 'orchestrator.json'
            path.write_text('{bad')
            self.assertEqual(dashboard.runner.orchestrator_receipt(tmp)['evidence'], 'missing')
            path.write_text('{"schema":1,"identity":"OpenClaw-hosted Codex session",'
                            '"model":"openai/gpt-6-sol","decision_at":"2026-10-16T10:43:00+00:00"}')
            self.assertEqual(dashboard.runner.orchestrator_receipt(tmp)['model'], 'openai/gpt-6-sol')

    def test_runner_execution_distinguishes_activity_queue_and_control(self):
        records = {"MOD-001": dict(self.records["MOD-001"], updated_at=self._epoch('2026-10-16T12:00:00Z'))}
        old = dict(self.tasks[0], updated_at='2026-10-16T10:00:00Z')
        tasks = dashboard.task_projection([old, self.tasks[1]], records)
        state = {"runner_alive": True, "control": "RUN", "health": {"status": "OK"},
                 "writer_lock": {"state": "free", "child_alive": False}}
        self.assertEqual(dashboard.runner_execution(state, tasks), 'stale')
        state['writer_lock'] = {"state": "held", "child_alive": True}
        self.assertEqual(dashboard.runner_execution(state, tasks), 'running')
        tasks[1]['status'] = 'QUEUED'
        self.assertEqual(dashboard.runner_execution(state, tasks), 'waiting')
        tasks[1]['status'] = 'DONE'
        self.assertEqual(dashboard.runner_execution(state, tasks), 'idle')
        state['control'] = 'PAUSE'
        self.assertEqual(dashboard.runner_execution(state, tasks), 'paused')
        state['control'] = 'STOP'
        self.assertEqual(dashboard.runner_execution(state, tasks), 'stopped')

    def test_delayed_heartbeat_is_stale_not_dead_when_pid_is_alive(self):
        tasks = dashboard.task_projection(self.tasks, self.records)
        state = {"runner_alive": False, "runner": {"pid": 123}, "control": "RUN", "health": {"status": "OK"},
                 "writer_lock": {"state": "held", "child_alive": True},
                 "events": [{"kind": "dispatch", "task_id": "current", "model_alias": "sonnet"}]}
        original = dashboard.runner.pid_alive
        dashboard.runner.pid_alive = lambda pid: pid == 123
        try:
            self.assertEqual(dashboard.runner_execution(state, tasks), 'stale')
            self.assertEqual(dashboard.agent_projection(state, tasks)[1]['status'], 'working')
        finally:
            dashboard.runner.pid_alive = original

    def test_recorded_certificate_condition_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'knowledge' / '03-Modules'
            for mid, header in [('MOD-000', '**Status: ACCEPTED — LEAN FOUNDATION.** gatekeeper approved'),
                                ('MOD-001', '**Status: ACCEPTED — FOUNDATION ONLY.**')]:
                folder = root / mid
                folder.mkdir(parents=True)
                (folder / f'{mid}.md').write_text(f'# {mid}\n\n{header}\n')
            (root / 'MOD-001' / 'APPROVAL.md').write_text(
                '# Approval\n\n**Status: APPROVED — FOUNDATION ONLY, ACTIVATION PENDING OWN CI.**\n')
            records = dashboard.module_records(Path(tmp))
            self.assertTrue(records['MOD-000']['accepted'])
            self.assertTrue(records['MOD-001']['accepted'])
            self.assertIn('pending', records['MOD-001']['discrepancy'])


if __name__ == '__main__':
    unittest.main()
