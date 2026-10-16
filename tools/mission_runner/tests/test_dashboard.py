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

    def test_accepted_module_blocked_task_stays_active(self):
        records = {"MOD-001": dict(self.records["MOD-001"], updated_at=self._epoch('2026-10-16T12:00:00Z'))}
        old = dict(self.tasks[0], updated_at='2026-10-16T10:00:00Z')
        tasks = dashboard.task_projection([old, self.tasks[1]], records)
        self.assertEqual(tasks[0]['lifecycle'], 'active-blocker')
        self.assertIsNone(tasks[0]['disposition'])
        self.assertEqual(tasks[1]['lifecycle'], 'running')
        self.assertEqual(dashboard.module_projection(self.catalog, records, tasks)[0], 'MOD-002')

    def test_blocked_task_after_conditional_record_remains_active(self):
        blocked = self._blocked(finished='2026-10-16T12:00:00Z')
        projected = dashboard.task_projection([blocked], self._record('2026-10-16T11:00:00Z'))
        self.assertEqual(projected[0]['lifecycle'], 'active-blocker')

    def test_newer_module_acceptance_alone_never_closes_blocker(self):
        blocked = self._blocked()
        projected = dashboard.task_projection([blocked], self._record('2026-10-16T11:00:00Z'))
        self.assertEqual(projected[0]['lifecycle'], 'active-blocker')

    def test_missing_or_malformed_dates_fail_closed(self):
        record = self._record('2026-10-16T11:00:00Z')
        for blocked in (self._blocked(finished='not-a-date'), self._blocked(finished='2026-10-16T10:00:00'),
                        dict(self._blocked(), updated_at=None, finished_at=None)):
            self.assertEqual(dashboard.task_projection([blocked], record)[0]['lifecycle'], 'active-blocker')
        for written in (None, 'bad'):
            rec = {"MOD-002": {"recorded_accepted": True, "updated_at": written}}
            self.assertEqual(dashboard.task_projection([self._blocked()], rec)[0]['lifecycle'], 'active-blocker')

    def test_later_queued_work_does_not_close_block(self):
        blocked = self._blocked(finished='2026-10-16T12:00:00Z')
        later = dict(self.tasks[1], module='MOD-002', status='QUEUED', created_at='2026-10-16T13:00:00Z')
        projected = dashboard.task_projection([blocked, later], self._record('2026-10-16T11:00:00Z'))
        self.assertEqual(projected[0]['lifecycle'], 'active-blocker')

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

    def test_later_unrelated_same_module_done_never_closes_block(self):
        old = dict(self.tasks[0], module='MOD-003')
        later = dict(self.tasks[1], module='MOD-003', status='DONE')
        projected = dashboard.task_projection([old, later], self.records)
        self.assertEqual(projected[0]['lifecycle'], 'active-blocker')

    @staticmethod
    def _registry(blocked, evidence, module='MOD-003'):
        return {"owner_record": None, "dispositions": {blocked: {
            "module": module, "classification": dashboard.RESOLVED, "evidence_task_id": evidence}}}

    def _approved(self, tid, module='MOD-003', created='2026-10-16T11:00:00Z', status='DONE', outcome='APPROVED',
                  verdict='VERIFIED'):
        return dict(self.tasks[1], id=tid, module=module, status=status, created_at=created,
                    evidence={'review_outcome': outcome}, route={'verdict': verdict})

    def test_blocker_lifecycle_uses_timestamps_not_sorted_task_ids(self):
        old = dict(self.tasks[0], id='z-review', module='MOD-003', created_at='2026-10-16T10:00:00Z')
        later = self._approved('a-correction')
        projected = dashboard.task_projection([later, old], self.records, self._registry('z-review', 'a-correction'))
        self.assertEqual([t['id'] for t in projected], ['z-review', 'a-correction'])
        self.assertEqual(projected[0]['lifecycle'], 'historical')
        self.assertEqual(projected[0]['disposition'], dashboard.RESOLVED)
        self.assertEqual(projected[0]['disposition_evidence_id'], 'a-correction')
        # Evidence recorded before the block is not "later" evidence.
        early = self._approved('a-correction', created='2026-10-16T09:00:00Z')
        projected = dashboard.task_projection([early, old], self.records, self._registry('z-review', 'a-correction'))
        self.assertEqual(projected[1]['lifecycle'], 'active-blocker')

    def test_missing_failed_or_unapproved_evidence_stays_active(self):
        old = dict(self.tasks[0], id='old', module='MOD-003', created_at='2026-10-16T10:00:00Z')
        registry = self._registry('old', 'ev')
        cases = {'absent': [], 'blocked': [self._approved('ev', status='BLOCKED')],
                 'running': [self._approved('ev', status='RUNNING')],
                 'changes': [self._approved('ev', outcome='CHANGES_REQUESTED')],
                 'no-outcome': [self._approved('ev', outcome=None)],
                 'wrong-module': [self._approved('ev', module='MOD-002')],
                 'unverified-route': [self._approved('ev', verdict='UNVERIFIED')],
                 'no-route': [dict(self._approved('ev'), route=None)]}
        for name, extra in cases.items():
            with self.subTest(name):
                got = dashboard.task_projection([old] + extra, self.records, registry)[0]
                self.assertEqual(got['lifecycle'], 'active-blocker')
        # Every also_task_ids entry is held to the same standard.
        registry['dispositions']['old']['also_task_ids'] = ['ev2']
        both = [old, self._approved('ev'), self._approved('ev2')]
        self.assertEqual(dashboard.task_projection(both, self.records, registry)[0]['lifecycle'], 'historical')
        for bad in (self._approved('ev2', module='MOD-002'), self._approved('ev2', verdict='UNVERIFIED')):
            got = dashboard.task_projection([old, self._approved('ev'), bad], self.records, registry)[0]
            self.assertEqual(got['lifecycle'], 'active-blocker')
        del registry['dispositions']['old']['also_task_ids']
        # Evidence must be a task id, not just any approved same-module work.
        other = self._approved('other')
        self.assertEqual(dashboard.task_projection([old, other], self.records, registry)[0]['lifecycle'], 'active-blocker')
        wrong_entry = {"owner_record": None, "dispositions": {"old": {"module": "MOD-002", "classification": dashboard.RESOLVED,
                                                                        "evidence_task_id": "ev"}}}
        got = dashboard.task_projection([old, self._approved('ev')], self.records, wrong_entry)[0]
        self.assertEqual(got['lifecycle'], 'active-blocker')

    def test_superseded_requires_approved_owner_record_and_docs_are_required(self):
        old = dict(self.tasks[0], id='gate', module='MOD-001', created_at='2026-10-16T10:00:00Z')
        owner = {"id": "OWNER-X", "path": "owner.md", "contains": "APPROVED by the owner"}
        registry = {"owner_record": owner, "dispositions": {"gate": {"module": "MOD-001",
                                                                     "classification": dashboard.SUPERSEDED,
                                                                     "clauses": ["a custom App"]}}}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(dashboard.task_projection([old], self.records, registry, tmp)[0]['lifecycle'], 'active-blocker')
            (Path(tmp) / 'owner.md').write_text('Status: DRAFT')
            self.assertEqual(dashboard.task_projection([old], self.records, registry, tmp)[0]['lifecycle'], 'active-blocker')
            (Path(tmp) / 'owner.md').write_text('Status: APPROVED by the owner')
            self.assertEqual(dashboard.task_projection([old], self.records, registry, tmp)[0]['lifecycle'], 'active-blocker')
            (Path(tmp) / 'owner.md').write_text('Status: APPROVED by the owner. Not used: a custom App')
            got =dashboard.task_projection([old], self.records, registry, tmp)[0]
            self.assertEqual((got['lifecycle'], got['disposition'], got['disposition_evidence_id']),
                             ('historical', dashboard.SUPERSEDED, 'OWNER-X'))
            self.assertEqual(dashboard.task_projection([old], self.records, registry, None)[0]['lifecycle'], 'active-blocker')
            # A resolved entry with a required doc marker stays active until the doc has it.
            doc = {"module": "MOD-001", "classification": dashboard.RESOLVED, "evidence_task_id": "ev",
                   "docs": [{"path": "rec.md", "contains": "final external review"}]}
            reg = {"owner_record": None, "dispositions": {"gate": doc}}
            tasks = [dict(old, module='MOD-001'), self._approved('ev', module='MOD-001')]
            self.assertEqual(dashboard.task_projection(tasks, self.records, reg, tmp)[0]['lifecycle'], 'active-blocker')
            (Path(tmp) / 'rec.md').write_text('names final external review')
            self.assertEqual(dashboard.task_projection(tasks, self.records, reg, tmp)[0]['lifecycle'], 'historical')

    def test_superseded_requires_exact_clause_in_owner_record(self):
        old = dict(self.tasks[0], id='gate', module='MOD-001', created_at='2026-10-16T10:00:00Z')
        owner = {"id": "OWNER-X", "path": "owner.md", "contains": "APPROVED by the owner"}
        entry = {"module": "MOD-001", "classification": dashboard.SUPERSEDED, "clauses": ["a custom App"]}
        registry = {"owner_record": owner, "dispositions": {"gate": entry}}
        def lifecycle(reg=registry):
            return dashboard.task_projection([old], self.records, reg, tmp)[0]['lifecycle']
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'owner.md').write_text('Status: APPROVED by the owner\n- Not used: a custom App, a hosted gate.')
            self.assertEqual(lifecycle(), 'historical')
            (Path(tmp) / 'owner.md').write_text('Status: APPROVED by the owner\n- Not used: pull requests.')
            self.assertEqual(lifecycle(), 'active-blocker')
            (Path(tmp) / 'owner.md').write_text('Status: APPROVED by the owner\n- Not used: a custom App.')
            for clauses in (None, [], [""], "a custom App"):
                with self.subTest(clauses=clauses):
                    bad = {"owner_record": owner, "dispositions": {"gate": dict(entry, clauses=clauses)}}
                    self.assertEqual(lifecycle(bad), 'active-blocker')

    def test_registry_clauses_are_present_in_real_owner_record(self):
        repo = Path(__file__).resolve().parents[3]
        registry = dashboard.load_dispositions()
        owner_text = (repo / registry['owner_record']['path']).read_text()
        for tid, entry in registry['dispositions'].items():
            if entry['classification'] == dashboard.SUPERSEDED:
                self.assertTrue(entry['clauses'], tid)
                for clause in entry['clauses']:
                    self.assertIn(clause, owner_text, tid)

    def test_evidence_paths_must_be_relative_regular_files_inside_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'
            repo.mkdir()
            (repo / 'ok.md').write_text('marker')
            outside = Path(tmp) / 'outside.md'
            outside.write_text('marker')
            (repo / 'link.md').symlink_to(outside)
            (repo / 'sub').mkdir()
            check = lambda rel: dashboard._doc_contains(repo, rel, 'marker', {})
            self.assertTrue(check('ok.md'))
            self.assertFalse(check(str(outside)))
            self.assertFalse(check(str(repo / 'ok.md')))
            self.assertFalse(check('../outside.md'))
            self.assertFalse(check('sub/../../outside.md'))
            self.assertFalse(check('link.md'))
            self.assertFalse(check('sub'))
            self.assertFalse(check('missing.md'))

    def test_malformed_registry_keeps_everything_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'r.json'
            for text in ('{bad', '{"version": 2, "dispositions": {}}', '[]'):
                bad.write_text(text)
                self.assertEqual(dashboard.load_dispositions(bad)['dispositions'], {})
            self.assertEqual(dashboard.load_dispositions(Path(tmp) / 'missing.json')['dispositions'], {})

    OWNER_BLOCKER = 'mission-control-owner-decision-blocker-opus-review-20261016'
    MOD000_REVIEW = 'blocker-integrity-full-code-opus-review-20261016'
    NEW_ATTEMPT = 'blocker-new-attempt-dispositions-sonnet-20261016'
    POST_AUDIT = {
        OWNER_BLOCKER: ('MOD-003', 'mission-control-owner-decision-blocker-full-opus-r2-20261016'),
        'mod003-owner-appendix-b-record-opus-review-20261016': ('MOD-003', 'mod003-owner-appendix-b-record-opus-r2-20261016'),
        'blocker-projection-hardening-sonnet-20261016': ('MOD-000', MOD000_REVIEW),
        'runner-prerequisite-gate-sonnet-20261016': ('MOD-000', MOD000_REVIEW),
        'runner-prerequisite-gate-evidence-sonnet-20261016': ('MOD-000', MOD000_REVIEW),
        'runner-prerequisite-gate-correction-sonnet-20261016': ('MOD-000', MOD000_REVIEW),
        NEW_ATTEMPT: ('MOD-000', MOD000_REVIEW),
    }
    POST_AUDIT_IDS = frozenset(POST_AUDIT)

    def _audited_state(self, with_evidence=True):
        # The ORIGINAL 25-BLOCKED audit only; later-added entries are tested separately.
        reg = {k: v for k, v in dashboard.load_dispositions()['dispositions'].items() if k not in self.POST_AUDIT_IDS}
        tasks, n = [], 0
        def stamp():
            nonlocal n
            n += 1
            return '2026-10-16T%02d:%02d:00Z' % divmod(n, 60)
        for tid, entry in reg.items():
            tasks.append(dict(self.tasks[0], id=tid, module=entry['module'], created_at=stamp()))
        owner = dict(self.tasks[0], id='mission-control-owner-decision-blocker-opus-review-20261016', module='MOD-002',
                     created_at=stamp(), evidence={'review_outcome': 'CHANGES_REQUESTED'})
        tasks.append(owner)
        if with_evidence:
            modules = {}
            for entry in reg.values():
                linked = [entry.get('evidence_task_id')] + list(entry.get('also_task_ids', []))
                for ev_id in filter(None, linked):
                    self.assertEqual(modules.setdefault(ev_id, entry['module']), entry['module'],
                                     'evidence task %s is shared across modules' % ev_id)
            for tid in sorted(modules):
                tasks.append(self._approved(tid, module=modules[tid], created=stamp()))
            tasks.append(self._approved('mission-control-owner-decision-blocker-sonnet-20261016', module='MOD-002',
                                        created=stamp()))
        return tasks

    def _real_repo_projection(self, tasks):
        repo = Path(__file__).resolve().parents[3]
        return dashboard.task_projection(tasks, {}, None, repo)

    def test_audited_registry_has_25_blocked_19_resolved_5_superseded_1_active(self):
        reg = dashboard.load_dispositions()['dispositions']
        self.assertTrue(self.POST_AUDIT_IDS <= set(reg))
        self.assertEqual(len(set(reg) - self.POST_AUDIT_IDS), 24)
        projected = self._real_repo_projection(self._audited_state())
        blocked = [t for t in projected if t['status'] == 'BLOCKED']
        self.assertEqual(len(blocked), 25)
        self.assertEqual(sum(t['disposition'] == dashboard.RESOLVED for t in blocked), 19)
        self.assertEqual(sum(t['disposition'] == dashboard.SUPERSEDED for t in blocked), 5)
        active = [t['id'] for t in blocked if t['lifecycle'] == 'active-blocker']
        self.assertEqual(active, ['mission-control-owner-decision-blocker-opus-review-20261016'])
        self.assertTrue(all(t['disposition_evidence_id'] for t in blocked if t['disposition']))

    def test_audited_registry_without_evidence_tasks_is_all_active_except_superseded(self):
        projected = self._real_repo_projection(self._audited_state(with_evidence=False))
        blocked = [t for t in projected if t['status'] == 'BLOCKED']
        self.assertEqual(sum(t['lifecycle'] == 'active-blocker' for t in blocked), 20)
        self.assertEqual(sum(t['disposition'] == dashboard.SUPERSEDED for t in blocked), 5)

    def test_current_owner_decision_opus_rejection_stays_active_after_sonnet_done(self):
        tid = self.OWNER_BLOCKER
        old = dict(self.tasks[0], id=tid, module='MOD-002', created_at='2026-10-16T10:00:00Z',
                   evidence={'review_outcome': 'CHANGES_REQUESTED'})
        fix = self._approved('mission-control-owner-decision-blocker-sonnet-20261016', module='MOD-002')
        projected = self._real_repo_projection([old, fix])
        self.assertEqual(projected[0]['lifecycle'], 'active-blocker')
        self.assertEqual(projected[1]['status'], 'DONE')

    def _post_audit_projection(self, evidence_ids=(), **overrides):
        tasks = []
        for i, (tid, (module, _)) in enumerate(sorted(self.POST_AUDIT.items())):
            tasks.append(dict(self.tasks[0], id=tid, module=module, created_at='2026-10-16T10:%02d:00Z' % i))
        for i, (ev, module) in enumerate(sorted(evidence_ids)):
            tasks.append(self._approved(ev, module=module, created='2026-10-16T12:%02d:00Z' % i, **overrides))
        by_id = {t['id']: t for t in self._real_repo_projection(tasks)}
        return {tid: by_id[tid] for tid in self.POST_AUDIT}

    def test_post_audit_entries_are_registered_with_exact_evidence_tasks(self):
        reg = dashboard.load_dispositions()['dispositions']
        for tid, (module, evidence) in self.POST_AUDIT.items():
            self.assertEqual(reg[tid]['module'], module)
            self.assertEqual(reg[tid]['classification'], dashboard.RESOLVED)
            self.assertEqual(reg[tid]['evidence_task_id'], evidence)
            self.assertNotIn('also_task_ids', reg[tid])

    def test_post_audit_blockers_stay_active_without_their_evidence_task(self):
        for tid, row in self._post_audit_projection().items():
            self.assertEqual(row['lifecycle'], 'active-blocker', tid)
            self.assertIsNone(row['disposition'], tid)
        # Same-module approved work that is not the named evidence task is not enough.
        other = [('unrelated-opus-review-20261016', 'MOD-000'), ('unrelated-opus-review-b-20261016', 'MOD-003')]
        for tid, row in self._post_audit_projection(other).items():
            self.assertEqual(row['lifecycle'], 'active-blocker', tid)

    def test_post_audit_blockers_stay_active_for_unapproved_or_wrong_module_evidence(self):
        needed = [(ev, module) for module, ev in self.POST_AUDIT.values()]
        for kwargs in ({'outcome': 'CHANGES_REQUESTED'}, {'verdict': 'REJECTED'}, {'status': 'BLOCKED'}):
            for tid, row in self._post_audit_projection(needed, **kwargs).items():
                self.assertEqual(row['lifecycle'], 'active-blocker', (tid, kwargs))
        wrong = [(ev, 'MOD-002') for _, ev in self.POST_AUDIT.values()]
        for tid, row in self._post_audit_projection(wrong).items():
            self.assertEqual(row['lifecycle'], 'active-blocker', tid)

    def test_mod000_blockers_become_historical_only_with_the_shared_code_review(self):
        mod000 = [t for t, (m, _) in self.POST_AUDIT.items() if m == 'MOD-000']
        self.assertEqual(len(mod000), 5)
        rows = self._post_audit_projection([(self.MOD000_REVIEW, 'MOD-000')])
        for tid in mod000:
            self.assertEqual(rows[tid]['lifecycle'], 'historical', tid)
            self.assertEqual(rows[tid]['disposition'], dashboard.RESOLVED)
            self.assertEqual(rows[tid]['disposition_evidence_id'], self.MOD000_REVIEW)
        for tid in set(self.POST_AUDIT) - set(mod000):
            self.assertEqual(rows[tid]['lifecycle'], 'active-blocker', tid)

    def test_new_attempt_blocker_requires_exact_later_same_module_opus_review(self):
        entry = dashboard.load_dispositions()['dispositions'][self.NEW_ATTEMPT]
        self.assertEqual(entry, {'module': 'MOD-000', 'classification': dashboard.RESOLVED,
                                 'evidence_task_id': self.MOD000_REVIEW})
        row = lambda ev: self._post_audit_projection(ev)[self.NEW_ATTEMPT]
        self.assertEqual(row([])['lifecycle'], 'active-blocker')
        self.assertEqual(row([('other-opus-review-20261016', 'MOD-000')])['lifecycle'], 'active-blocker')
        self.assertEqual(row([(self.MOD000_REVIEW, 'MOD-003')])['lifecycle'], 'active-blocker')
        positive = row([(self.MOD000_REVIEW, 'MOD-000')])
        self.assertEqual(positive['lifecycle'], 'historical')
        self.assertEqual(positive['disposition'], dashboard.RESOLVED)
        self.assertEqual(positive['disposition_evidence_id'], self.MOD000_REVIEW)

    def test_owner_decision_blocker_becomes_historical_with_its_r2_review(self):
        ev = self.POST_AUDIT[self.OWNER_BLOCKER][1]
        rows = self._post_audit_projection([(ev, 'MOD-003')])
        self.assertEqual(rows[self.OWNER_BLOCKER]['lifecycle'], 'historical')
        self.assertEqual(rows[self.OWNER_BLOCKER]['disposition_evidence_id'], ev)

    def test_owner_record_blocker_requires_bound_status_clause_only(self):
        tid = 'mod003-owner-appendix-b-record-opus-review-20261016'
        entry = dashboard.load_dispositions()['dispositions'][tid]
        needles = [d['contains'] for d in entry['docs']]
        self.assertEqual(needles, ['**Status: APPROVED by the owner on 2026-10-16; operative for MOD-003 S1 only after the publication conditions below.**'])
        ev = self.POST_AUDIT[tid][1]
        old = dict(self.tasks[0], id=tid, module='MOD-003', created_at='2026-10-16T10:00:00Z')
        done = self._approved(ev, module='MOD-003', created='2026-10-16T12:00:00Z')
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            doc = repo / entry['docs'][0]['path']
            doc.parent.mkdir(parents=True)
            project = lambda: dashboard.task_projection([old, done], {}, {'owner_record': None, 'dispositions': {tid: entry}}, repo)[0]
            doc.write_text(needles[0])
            self.assertEqual(project()['lifecycle'], 'historical')
            doc.write_text('**Status: DRAFT**')
            self.assertEqual(project()['lifecycle'], 'active-blocker')  # status clause missing

    def test_owner_record_review_is_historical_only_with_r2_and_real_approved_record(self):
        tid = 'mod003-owner-appendix-b-record-opus-review-20261016'
        ev = self.POST_AUDIT[tid][1]
        row = self._post_audit_projection([(ev, 'MOD-003')])[tid]
        self.assertEqual(row['lifecycle'], 'historical')
        self.assertEqual(row['disposition'], dashboard.RESOLVED)
        self.assertEqual(row['disposition_evidence_id'], ev)
        self.assertEqual(self._post_audit_projection([])[tid]['lifecycle'], 'active-blocker')
        self.assertEqual(self._post_audit_projection([(ev, 'MOD-002')])[tid]['lifecycle'], 'active-blocker')
        for kwargs in ({'outcome': 'CHANGES_REQUESTED'}, {'verdict': 'REJECTED'}, {'status': 'BLOCKED'}):
            rows = self._post_audit_projection([(ev, 'MOD-003')], **kwargs)
            self.assertEqual(rows[tid]['lifecycle'], 'active-blocker', kwargs)

    def test_build_state_separates_historical_from_active(self):
        with mock.patch.object(dashboard, 'module_records', return_value={}), \
             mock.patch.object(dashboard, 'worktree_clean', return_value=False):
            state = dashboard.build_state({'tasks': self._audited_state(), 'events': [], 'ci': None},
                                          Path(__file__).resolve().parents[3])
        self.assertEqual(state['resolved_historical_count'], 19)
        self.assertEqual(state['superseded_count'], 5)
        self.assertEqual(state['historical_blocked_count'], 24)
        self.assertEqual(len(state['historical_blockers']), 24)
        self.assertEqual([b['id'] for b in state['active_blockers']],
                         ['mission-control-owner-decision-blocker-opus-review-20261016'])

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

    def _owner_state(self, receipt, tasks=()):
        snapshot = {'tasks': list(tasks), 'events': [], 'ci': None, 'runner_alive': True, 'control': 'RUN',
                    'health': {'status': 'OK'}}
        if receipt is not None:
            snapshot['orchestrator'] = receipt
        with mock.patch.object(dashboard, 'module_records', lambda repo: {}):
            return dashboard.build_state(snapshot, Path('/unneeded'))

    GOOD_RECEIPT = {'evidence': 'recorded', 'state': 'blocked', 'decision': 'Ask owner about EIP Appendix B',
                    'next_legal_action': 'OWNER_ACTION_REQUIRED: Decide EIP Appendix B IN/OUT',
                    'age_s': 5, 'decision_at': '2026-10-16T10:00:00Z',
                    'identity': 'Orchestrator-Claude', 'model': 'claude-opus-5-5'}

    def test_marked_orchestrator_receipt_is_owner_action_blocker_without_task_or_runner_change(self):
        state = self._owner_state(self.GOOD_RECEIPT)
        for key in ('active_blockers', 'owner_action_blockers'):
            self.assertEqual(len(state[key]), 1)
            entry = state[key][0]
            self.assertEqual(entry['id'], 'orchestrator-owner-decision')
            self.assertEqual(entry['role'], 'orchestrator')
            self.assertEqual(entry['title'], 'Owner decision required')
            self.assertEqual(entry['status'], 'BLOCKED')
            self.assertEqual(entry['lifecycle'], 'active-blocker')
            self.assertEqual(entry['blocked_reason'], 'OWNER_DECISION_REQUIRED')
            self.assertEqual(entry['last_error'], 'Decide EIP Appendix B IN/OUT')
            self.assertEqual(entry['module'], state['current_module'])
            self.assertIs(entry['stale'], False)
            self.assertEqual(entry['age_s'], 5)
            self.assertEqual(entry['decision_at'], '2026-10-16T10:00:00Z')
        self.assertEqual(state['tasks'], [])
        self.assertEqual(state['actionable_tasks'], [])
        self.assertEqual(state['runner_execution'], 'idle')
        orchestrator, sonnet, opus = state['agents']
        self.assertEqual(orchestrator['status'], 'blocked')
        self.assertEqual(orchestrator['identity'], 'Orchestrator-Claude · claude-opus-5-5')
        for agent in (sonnet, opus):
            self.assertNotEqual(agent['status'], 'working')
            self.assertEqual(agent['identity'], 'No verified invocation recorded')

    def test_old_or_unaged_receipt_stays_visible_but_is_labelled_stale(self):
        for age in (901, 10**6, None, 'five', True, float('nan'), float('inf'), -1):
            with self.subTest(age=age):
                state = self._owner_state(self.GOOD_RECEIPT | {'age_s': age})
                self.assertEqual(len(state['owner_action_blockers']), 1)
                entry = state['owner_action_blockers'][0]
                self.assertTrue(entry['stale'])
                self.assertEqual(entry['title'], 'Owner decision required (stale receipt)')
                self.assertEqual(state['agents'][0]['status'], 'unknown')
        missing = {k: v for k, v in self.GOOD_RECEIPT.items() if k != 'age_s'}
        entry = self._owner_state(missing)['owner_action_blockers'][0]
        self.assertTrue(entry['stale'])
        self.assertIsNone(entry['age_s'])
        boundary = self._owner_state(self.GOOD_RECEIPT | {'age_s': 900})['owner_action_blockers'][0]
        self.assertFalse(boundary['stale'])

    def test_malformed_identity_and_model_normalize_to_unknown(self):
        for bad in (None, 5, ['x'], {'a': 1}, '  '):
            with self.subTest(bad=bad):
                state = self._owner_state(self.GOOD_RECEIPT | {'identity': bad, 'model': bad})
                self.assertEqual(state['agents'][0]['identity'], 'UNKNOWN · UNKNOWN')

    def test_owner_decision_blocker_fails_closed_and_bounds_text(self):
        good = self.GOOD_RECEIPT
        bad = [None, {}, 'blocked', good | {'evidence': 'unrecorded'}, good | {'evidence': None},
               good | {'state': 'waiting'}, good | {'decision': ''}, good | {'decision': '  '},
               good | {'decision': None}, good | {'decision': 5},
               good | {'next_legal_action': None}, good | {'next_legal_action': ['OWNER_ACTION_REQUIRED: x']},
               good | {'next_legal_action': 'Owner action required: decide'},
               good | {'next_legal_action': 'please OWNER_ACTION_REQUIRED: decide'},
               good | {'next_legal_action': 'OWNER_ACTION_REQUIRED:decide'},
               good | {'next_legal_action': ' OWNER_ACTION_REQUIRED: decide'},
               good | {'next_legal_action': 'OWNER_ACTION_REQUIRED: '},
               good | {'next_legal_action': 'OWNER_ACTION_REQUIRED:    '}]
        for receipt in bad:
            with self.subTest(receipt=receipt):
                state = self._owner_state(receipt)
                self.assertEqual(state['active_blockers'], [])
                self.assertEqual(state['owner_action_blockers'], [])
                self.assertIsInstance(state['orchestrator'], dict)
                if not isinstance(receipt, dict):
                    self.assertEqual((state['orchestrator']['identity'], state['orchestrator']['model']),
                                     ('UNKNOWN', 'UNKNOWN'))
        long = self._owner_state(good | {'next_legal_action': 'OWNER_ACTION_REQUIRED: ' + 'x' * 5000})
        self.assertEqual(len(long['owner_action_blockers'][0]['last_error']), dashboard.OWNER_ACTION_MAX)

    def test_owner_decision_blocker_not_duplicated_and_historical_blockers_unchanged(self):
        old = dict(self.tasks[0], module='MOD-003', created_at='2026-10-16T09:00:00Z')
        later = self._approved('later-done')
        tasks = [old, later] + self.tasks[1:]
        with mock.patch.object(dashboard, 'load_dispositions',
                               return_value=self._registry('old-review', 'later-done')):
            return self._check_owner_dedup(tasks)

    def _check_owner_dedup(self, tasks):
        state = self._owner_state(self.GOOD_RECEIPT, tasks)
        ids = [b['id'] for b in state['active_blockers']]
        self.assertEqual(ids.count('orchestrator-owner-decision'), 1)
        self.assertEqual([b['id'] for b in state['owner_action_blockers']].count('orchestrator-owner-decision'), 1)
        self.assertNotIn('orchestrator-owner-decision', [t['id'] for t in state['tasks']])
        self.assertNotIn('orchestrator-owner-decision', [t['id'] for t in state['actionable_tasks']])
        plain = self._owner_state(None, tasks)
        by_id = {t['id']: t for t in state['tasks']}
        self.assertEqual(by_id['old-review']['lifecycle'], 'historical')
        self.assertGreaterEqual(state['historical_blocked_count'], 1)
        self.assertEqual(plain['historical_blocked_count'], state['historical_blocked_count'])
        self.assertEqual(plain['runner_execution'], state['runner_execution'])
        self.assertEqual([b['id'] for b in plain['active_blockers']],
                         [i for i in ids if i != 'orchestrator-owner-decision'])

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
        old = dict(self.tasks[0], module='MOD-003', created_at='2026-10-16T09:00:00Z')
        tasks = dashboard.task_projection([old, self._approved('ev', created='2026-10-16T09:30:00Z'), self.tasks[1]], self.records,
                                          self._registry('old-review', 'ev'))
        self.assertEqual([t['id'] for t in tasks], ['old-review', 'ev', 'current'])
        self.assertEqual(tasks[0]['lifecycle'], 'historical')
        state = {"runner_alive": True, "control": "RUN", "health": {"status": "OK"},
                 "writer_lock": {"state": "free", "child_alive": False}}
        self.assertEqual(dashboard.runner_execution(state, tasks), 'stale')
        state['writer_lock'] = {"state": "held", "child_alive": True}
        self.assertEqual(dashboard.runner_execution(state, tasks), 'running')
        tasks[2]['status'] = 'QUEUED'
        self.assertEqual(dashboard.runner_execution(state, tasks), 'waiting')
        tasks[2]['status'] = 'DONE'
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
