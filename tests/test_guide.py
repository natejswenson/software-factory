"""Real task selection, coherent observations and preservation of Git/run bytes."""

import json
import os
import shlex
import socket
import stat
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from software_factory import diagnostics, engine, guide, inspection, progress
from software_factory.delivery import deliver
from software_factory.errors import FactoryError
from software_factory.git import git
from software_factory.store import atomic_json, locked, read_run
from tests.support import FactoryCase


class GuideTests(FactoryCase):
    def setUp(self):
        config_home = tempfile.TemporaryDirectory(prefix='factory-guide-test-config-')
        self.addCleanup(config_home.cleanup)
        environment = patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
                                               'XDG_CONFIG_HOME': config_home.name})
        environment.start()
        self.addCleanup(environment.stop)

    def snapshot(self, root):
        result = {}
        for path in root.rglob('*'):
            name = str(path.relative_to(root))
            if path.is_symlink():
                result[name] = ('link', os.readlink(path))
            elif path.is_file():
                result[name] = (stat.S_IMODE(path.stat().st_mode), path.read_bytes())
            elif path.is_dir():
                result[name] = ('directory',)
        return result

    def observe(self, fixture, selection=None):
        before = self.snapshot(fixture.root)
        with patch.object(engine, 'evidence', side_effect=AssertionError('No real-store snapshot')), patch.object(
            engine, 'describe', side_effect=AssertionError('No uncaptured describe')
        ), patch.object(engine, 'resume', side_effect=AssertionError('No automatic resume')):
            result = guide.inspect(fixture.repo, select=selection)
        self.assertEqual(self.snapshot(fixture.root), before)
        return result

    def select(self, fixture, run):
        return self.observe(fixture, run['id'][:8])['selected']

    def test_real_lifecycle_matches_authoritative_next_and_literal_recommendations(self):
        f = self.fixture()
        run = engine.start(f.options)
        for phase in ('plan', 'plan-review', 'implement', 'review', 'deliver', 'done'):
            state = read_run(run['run'])
            expected = engine.next_action(state)
            selected = self.select(f, run)
            self.assertEqual(selected['next'], expected, phase)
            self.assertEqual(selected['summary']['phase'], phase)
            command = selected['recommended']
            if phase == 'done':
                self.assertIsNone(command)
                self.assertEqual(selected['recordedOutcome'], state['delivery'])
                break
            self.assertIn(run['run'], command['argv'])
            self.assertEqual(shlex.split(shlex.join(command['argv'])), command['argv'])
            self.assertFalse(command['requiresDirection'])
            if phase in ('plan-review', 'review'):
                self.assertEqual(command['argv'][1], 'review-context')
                self.assertTrue(command['artifact'].endswith('review.json'))
            if phase == 'plan':
                plan = Path(run['run']) / 'plan.md'
                plan.write_text('# Plan\nChange value to new.\n')
                engine.submit_plan(run['run'], plan)
            elif phase == 'plan-review':
                self.approve_plan(run)
            elif phase == 'implement':
                (Path(run['worktree']) / 'value.txt').write_text('new\n')
                engine.verify(run['run'])
            elif phase == 'review':
                self.review(engine.describe(read_run(run['run'])))
            elif phase == 'deliver':
                deliver(run['run'])

    def test_interrupted_creation_rename_and_owned_commit_recovery_remain_recommendations(self):
        f = self.fixture()
        run = self.reviewed(f)
        state = read_run(run['run'])
        saved = state['verification']['evidence']
        state['commitIntent'] = {'parent': saved['head'], 'tree': saved['tree'], 'paths': saved['paths']}
        atomic_json(Path(run['run']) / 'state.json', state)
        git(run['worktree'], ['add', '--', *saved['paths']])
        git(run['worktree'], ['commit', '-m', 'synthetic owned delivery commit'])
        selected = self.select(f, run)
        self.assertEqual(selected['next']['action'], 'deliver')
        self.assertIn('Reconcile', selected['next']['reason'])
        self.assertEqual(selected['recommended']['argv'][1], 'deliver')
        for kind in ('preparing', 'rename'):
            current = {**state}
            if kind == 'preparing':
                current['phase'] = 'preparing'
            else:
                current['renameIntent'] = {'from': run['branch'], 'to': 'feature/renamed'}
            atomic_json(Path(run['run']) / 'state.json', current)
            selected = self.select(f, run)
            self.assertEqual(selected['next']['action'], 'resume')
            self.assertEqual(selected['recommended']['argv'][1], 'resume')

    def test_context_only_actions_skip_tree_and_unrelated_filter_configuration(self):
        f = self.fixture()
        run = engine.start(f.options)
        git(f.repo, ['config', 'filter.installed.required', 'true'])
        with patch.object(inspection, 'inputs', side_effect=AssertionError('Context requires no source staging')):
            selected = self.select(f, run)
        self.assertEqual(selected['next']['action'], 'plan')
        plan = Path(run['run']) / 'plan.md'
        plan.write_text('Synthetic plan')
        engine.submit_plan(run['run'], plan)
        self.approve_plan(run)
        with patch.object(inspection, 'inputs', side_effect=AssertionError('Context requires no source staging')):
            selected = self.select(f, run)
        self.assertEqual(selected['next']['action'], 'implement')
        self.assertEqual(selected['diagnostics']['gates']['verification']['status'], 'missing')

    def test_dirty_source_modes_symlinks_and_eol_fingerprint_match_without_real_object_writes(self):
        f = self.fixture()
        run = self.checked(f)
        root = Path(run['worktree'])
        (root / 'new data;$(false).txt').write_bytes(b'new untracked\r\n')
        (root / 'value.txt').write_text('changed\n')
        (root / 'ignored-data').write_text('ignored')
        (root / 'link').symlink_to('value.txt')
        (root / 'check.py').chmod(0o755)
        git(root, ['config', 'core.autocrlf', 'true'])
        (root / '.gitattributes').write_text('*.txt text\n')
        state = read_run(run['run'])
        expected = engine.evidence(state)
        plan = (Path(run['run']) / 'plan.md').read_bytes()
        before = self.snapshot(f.root)
        captured = inspection.capture(state, plan)
        self.assertEqual(captured['evidence'], expected)
        self.assertEqual(before, self.snapshot(f.root))
        selected = self.select(f, run)
        self.assertEqual(selected['next']['action'], 'verify')
        self.assertEqual(selected['diagnostics']['gates']['verification']['status'], 'stale')
        self.assertIn('new data;$(false).txt', selected['diagnostics']['changedPaths']['paths'])
        self.assertNotIn('ignored-data', selected['diagnostics']['changedPaths']['paths'])

    def test_local_explicit_and_default_global_ignores_preserve_engine_evidence_and_precedence(self):
        for kind in ('local', 'explicit-global', 'default-global'):
            with self.subTest(kind=kind):
                f = self.fixture()
                run = self.checked(f)
                root = Path(run['worktree'])
                if kind == 'local':
                    ignore = Path(git(root, ['rev-parse', '--git-path', 'info/exclude']).strip())
                elif kind == 'explicit-global':
                    ignore = f.root / 'global ignore;data'
                    git(root, ['config', 'core.excludesFile', str(ignore)])
                else:
                    config_root = f.root / 'xdg config'
                    (config_root / 'git').mkdir(parents=True)
                    ignore = config_root / 'git/ignore'
                    patcher = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(config_root)})
                    patcher.start()
                    self.addCleanup(patcher.stop)
                ignore.write_text('local-only.cache\n*.retained\n')
                (root / 'local-only.cache').write_text('must remain untracked and ignored')
                (root / '.gitignore').write_text((root / '.gitignore').read_text() + '!visible.retained\n')
                (root / 'visible.retained').write_text('higher-precedence project rule wins')
                state = read_run(run['run'])
                expected = engine.evidence(state)
                plan = (Path(run['run']) / 'plan.md').read_bytes()
                before = self.snapshot(f.root)
                captured = inspection.capture(state, plan)
                self.assertEqual(captured['evidence'], expected)
                self.assertNotIn('local-only.cache', captured['evidence']['paths'])
                self.assertIn('visible.retained', captured['evidence']['paths'])
                self.assertEqual(before, self.snapshot(f.root))
                # With only an ignored file added, current verification remains current.
                (root / '.gitignore').write_text((root / '.gitignore').read_text().replace('!visible.retained\n', ''))
                (root / 'visible.retained').unlink()
                selected = self.select(f, run)
                self.assertEqual(selected['next']['action'], 'review')
                self.assertEqual(selected['diagnostics']['gates']['verification']['status'], 'current')

    def test_local_and_global_ignore_drift_discards_current_advice(self):
        for kind in ('local', 'global'):
            f = self.fixture()
            run = self.checked(f)
            root = Path(run['worktree'])
            if kind == 'local':
                ignore = Path(git(root, ['rev-parse', '--git-path', 'info/exclude']).strip())
            else:
                ignore = f.root / 'global ignore'
                git(root, ['config', 'core.excludesFile', str(ignore)])
            ignore.write_text('ignored-one\n')
            original = inspection.capture
            count = 0

            def moving(state, plan):
                nonlocal count
                result = original(state, plan)
                count += 1
                if count == 1:
                    ignore.write_text('ignored-two\n')
                return result

            with patch.object(inspection, 'capture', side_effect=moving):
                report = guide.inspect(f.repo, select=run['id'])
            self.assertTrue(report['partial'])
            self.assertIsNone(report['selected']['next'])
            self.assertIsNone(report['selected']['diagnostics'])
            self.assertTrue(report['selected']['recommended']['requiresDirection'])

    def test_snapshot_scratch_stays_outside_source_when_tempdir_points_at_worktree(self):
        f = self.fixture()
        run = self.checked(f)
        with patch.object(tempfile, 'tempdir', run['worktree']):
            report = self.observe(f, run['id'])
        self.assertFalse(report['partial'])
        self.assertEqual(report['selected']['next']['action'], 'review')
        self.assertEqual(report['selected']['diagnostics']['gates']['verification']['status'], 'current')

    def test_failure_and_rejected_plan_findings_and_blocked_budget_stay_explicit(self):
        f = self.fixture()
        run = self.planned(f)
        failed = engine.verify(run['run'])
        selected = self.select(f, run)
        self.assertEqual(selected['next']['action'], 'implement')
        self.assertIn('Fix failed', selected['recommended']['reason'])
        self.assertEqual(selected['diagnostics']['gates']['verification']['status'], 'failed')
        state = read_run(run['run'])
        state['phase'] = 'blocked'
        state['failures'] = state['failureLimit']
        atomic_json(Path(run['run']) / 'state.json', state)
        report = self.observe(f, run['id'])
        self.assertEqual(guide.exit_code(report), 2)
        command = report['selected']['recommended']
        self.assertEqual(command['argv'][1], 'explain')
        self.assertTrue(command['requiresDirection'])
        self.assertNotIn('extend', command['argv'])
        self.assertFalse(failed['verification']['passed'])
        other = self.fixture()
        pending = engine.start(other.options)
        plan = Path(pending['run']) / 'plan.md'
        plan.write_text('Plan rejected in synthetic fixture')
        status = engine.submit_plan(pending['run'], plan)
        finding = {'severity': 'major', 'location': 'plan.md', 'issue': 'Missing behavior check'}
        engine.submit_plan_review(pending['run'], self.json_file(pending['run'], 'reject.json', {
            'context': status['next']['context'], 'reviewer': 'synthetic test', 'verdict': 'fail', 'findings': [finding]}))
        selected = self.select(other, pending)
        self.assertEqual(selected['next']['action'], 'plan')
        self.assertEqual(selected['findings']['plan'], [finding])

    def test_inventory_preserves_corrupt_neighbors_and_possible_relations(self):
        f = self.fixture()
        first = engine.start(f.options)
        f.options = replace(f.options, task='Second synthetic candidate')
        second = engine.start(f.options)
        state = read_run(second['run'])
        state['task'] = '  Change old   to new\n'
        atomic_json(Path(second['run']) / 'state.json', state)
        f.options = replace(f.options, task='Third synthetic candidate')
        third = engine.start(f.options)
        state = read_run(third['run'])
        state['task'] = 'CHANGE OLD TO NEW'
        atomic_json(Path(third['run']) / 'state.json', state)
        broken = Path(first['run']).parent / 'eeeeeeee-0000-4000-8000-000000000001'
        broken.mkdir()
        (broken / 'state.json').write_text('malformed')
        report = self.observe(f)
        self.assertEqual(len(report['runs']), 3)
        self.assertTrue(report['partial'])
        self.assertEqual(guide.exit_code(report), 2)
        self.assertEqual(len(report['possibleRelations']), 1)
        self.assertEqual(set(report['possibleRelations'][0]['candidates']), {first['id'], second['id']})
        self.assertNotIn('Change old', report['possibleRelations'][0]['taskHash'])
        self.assertEqual(report['possibleRelations'][0]['kind'], 'possible-same-task')
        self.assertIsNone(report['selected'])

    def test_prefix_collision_including_corrupt_hidden_candidates_and_invalid_before_fs(self):
        f = self.fixture()
        run = engine.start(f.options)
        self.assertEqual(self.select(f, run)['id'], run['id'])
        parent = Path(run['run']).parent
        neighbor = parent / (run['id'][:8] + '-0000-4000-8000-000000000099')
        neighbor.mkdir()
        (neighbor / 'state.json').write_text('corrupt candidate')
        report = self.observe(f, run['id'][:8])
        self.assertIsNone(report['selected'])
        self.assertEqual(set(report['candidates']), {run['id'], neighbor.name})
        self.assertEqual(guide.exit_code(report), 2)
        exact = self.observe(f, run['id'])
        self.assertEqual(exact['selected']['id'], run['id'])
        missing = self.observe(f, '00000000')
        self.assertIsNone(missing['selected'])
        self.assertEqual(missing['candidates'], [])
        for value in ('a', '1234567', '../unsafe', '/other/repo', 'not-a-uuid'):
            with patch.object(inspection, 'repository', side_effect=AssertionError('No filesystem access')):
                with self.assertRaises(Exception) as caught:
                    guide.inspect(f.repo, select=value)
                self.assertNotIsInstance(caught.exception, AssertionError)

    def test_bounded_ordering_and_older_selection_beyond_display_page(self):
        f = self.fixture()
        run = engine.start(f.options)
        original = read_run(run['run'])
        parent = Path(run['run']).parent
        saved = []
        for index in range(125):
            name = f'{index:08x}-0000-4000-8000-000000000001'
            path = parent / name
            path.mkdir()
            state = {**original, 'id': name, 'dir': str(path), 'phase': 'plan' if index < 105 else 'done',
                     'updatedAt': f'2026-10-05T12:00:{index % 60:02d}.000Z',
                     'delivery': {'endpoint': 'local', 'commit': original['base']} if index >= 105 else None}
            atomic_json(path / 'state.json', state)
            saved.append(name)
        report = self.observe(f)
        self.assertEqual(len(report['runs']), 100)
        self.assertTrue(all(row['phase'] != 'done' for row in report['runs']))
        self.assertEqual(report['omitted'], {'total': 26, 'unfinished': 6, 'recent': 20})
        report = self.observe(f, saved[-1])
        self.assertEqual(report['selected']['id'], saved[-1])
        self.assertEqual(report['selected']['next']['action'], 'done')
        self.assertIsNone(report['selected']['recommended'])
        self.assertEqual(guide.exit_code(report), 0)

    def test_terminal_missing_worktree_and_foreign_repository_keep_saved_delivery(self):
        f = self.fixture()
        status = deliver(self.reviewed(f)['run'])
        Path(status['worktree']).rename(f.root / 'saved worktree')
        report = self.observe(f, status['id'])
        selected = report['selected']
        self.assertEqual(selected['recordedOutcome'], status['delivery'])
        self.assertEqual(selected['next']['action'], 'done')
        self.assertIsNone(selected['recommended'])
        self.assertFalse(selected['currentAvailability']['worktreeAvailable'])
        self.assertEqual(guide.exit_code(report), 2)
        other = self.fixture()
        self.assertIsNone(self.observe(other, status['id'])['selected'])

    def test_all_owners_and_malformed_lock_are_observed_without_snapshot_or_takeover(self):
        f = self.fixture()
        run = engine.start(f.options)
        with locked(run['run']):
            for host in (socket.gethostname(), 'foreign-host'):
                atomic_json(Path(run['run']) / 'lock/owner.json', {'pid': os.getpid(), 'host': host, 'at': 'synthetic'})
                with patch.object(inspection, 'capture', side_effect=AssertionError('No source snapshot while owned')):
                    report = self.observe(f, run['id'])
                selected = report['selected']
                self.assertEqual(selected['next']['action'], 'wait')
                self.assertEqual(selected['currentAvailability']['status'], 'locked')
                self.assertEqual(guide.exit_code(report), 0)
                self.assertEqual(selected['recommended']['argv'][1], 'status')
            (Path(run['run']) / 'lock/owner.json').write_text('{}')
            report = self.observe(f, run['id'])
            self.assertTrue(report['partial'])
            self.assertIsNone(report['selected']['next'])
            self.assertTrue(report['selected']['recommended']['requiresDirection'])

    def test_active_verification_uses_pinned_progress_and_detects_sidecar_drift(self):
        f = self.fixture()
        run = engine.start(f.options)
        state = read_run(run['run'])
        state['checkAttempt'] = 1
        state['operation'] = {'kind': 'verify', 'attempt': 1}
        atomic_json(Path(run['run']) / 'state.json', state)
        with locked(run['run']):
            writer = progress.Observation(state)
            writer.begin('behavior')
            with patch.object(progress, '_snapshot', side_effect=AssertionError('Only pinned sidecar reads')):
                report = self.observe(f, run['id'])
            self.assertEqual(report['selected']['progress']['status'], 'running')
            self.assertEqual(report['selected']['recommended']['argv'][1], 'progress')
            self.assertEqual(guide.exit_code(report), 0)
            original = progress.project

            def moving(*args):
                value = original(*args)
                writer.finish('interrupted')
                return value

            with patch.object(progress, 'project', side_effect=moving):
                report = guide.inspect(f.repo, select=run['id'])
            self.assertTrue(report['partial'])
            self.assertIsNone(report['selected']['progress'])
            self.assertIsNone(report['selected']['next'])

    def test_missing_verification_owner_requires_inspection_without_source_capture(self):
        f = self.fixture()
        run = engine.start(f.options)
        state = read_run(run['run'])
        state['checkAttempt'] = 1
        state['operation'] = {'kind': 'verify', 'attempt': 1}
        atomic_json(Path(run['run']) / 'state.json', state)
        with patch.object(inspection, 'capture', side_effect=AssertionError('Unknown verification ownership')):
            report = self.observe(f, run['id'])
        self.assertTrue(report['partial'])
        selected = report['selected']
        self.assertEqual(selected['next']['action'], 'wait')
        self.assertEqual(selected['progress']['status'], 'unknown')
        self.assertTrue(selected['recommended']['requiresDirection'])
        self.assertEqual(selected['recommended']['argv'][1], 'progress')

    def test_filter_refusal_and_driver_inserted_after_precheck_never_execute(self):
        for key in ('clean', 'process', 'required'):
            f = self.fixture()
            run = self.checked(f)
            marker = f.root / 'filter-executed'
            command = f'python3 -c "from pathlib import Path; Path({str(marker)!r}).touch()"'
            git(f.repo, ['config', f'filter.unsafe.{key}', 'true' if key == 'required' else command])
            report = self.observe(f, run['id'])
            self.assertEqual(guide.exit_code(report), 2)
            self.assertFalse(marker.exists())
            self.assertIsNone(report['selected']['next'])
        f = self.fixture()
        run = self.checked(f)
        root = Path(run['worktree'])
        (root / '.gitattributes').write_text('*.txt filter=racing\n')
        marker = f.root / 'racing-filter-executed'
        original = inspection.inputs
        count = 0

        def racing(state):
            nonlocal count
            result = original(state)
            count += 1
            if count == 1:
                git(root, ['config', 'filter.racing.clean', f'python3 -c "from pathlib import Path; Path({str(marker)!r}).touch()"'])
            return result

        with patch.object(inspection, 'inputs', side_effect=racing):
            report = guide.inspect(f.repo, select=run['id'])
        self.assertTrue(report['partial'])
        self.assertFalse(marker.exists())
        self.assertIsNone(report['selected']['next'])

    def test_state_owner_head_and_plan_drift_clear_selected_action_and_freshness(self):
        for field in ('state', 'owner', 'head', 'plan'):
            f = self.fixture()
            run = self.checked(f)
            original = inspection.capture
            count = 0

            def moving(state, plan):
                nonlocal count
                value = original(state, plan)
                count += 1
                if count == 1:
                    if field == 'state':
                        state = read_run(run['run'])
                        state['updatedAt'] = 'changed during inspection'
                        atomic_json(Path(run['run']) / 'state.json', state)
                    elif field == 'owner':
                        lock = Path(run['run']) / 'lock'
                        lock.mkdir()
                        atomic_json(lock / 'owner.json', {'pid': os.getpid(), 'host': 'another-host', 'at': 'synthetic'})
                    elif field == 'head':
                        git(run['worktree'], ['commit', '--allow-empty', '-m', 'moving HEAD'])
                    else:
                        (Path(run['run']) / 'plan.md').write_text('changed plan')
                return value

            with patch.object(inspection, 'capture', side_effect=moving):
                report = guide.inspect(f.repo, select=run['id'])
            selected = report['selected']
            self.assertTrue(report['partial'], field)
            self.assertIsNone(selected['next'], field)
            self.assertIsNone(selected['diagnostics'], field)
            self.assertTrue(selected['recommended']['requiresDirection'])

    def test_promised_missing_head_stays_offline_and_unsupported_git_fails_closed(self):
        f = self.fixture()
        run = engine.start(f.options)
        remote = f.root / 'local remote.git'
        git(f.root, ['clone', '--bare', '--no-local', str(f.repo), str(remote)])
        for key, value in (('core.repositoryformatversion', '1'), ('extensions.partialClone', 'origin'),
                           ('remote.origin.url', str(remote)), ('remote.origin.promisor', 'true')):
            git(f.repo, ['config', key, value])
        base = read_run(run['run'])['base']
        (f.repo / '.git/objects' / base[:2] / base[2:]).unlink()
        report = self.observe(f, run['id'])
        self.assertTrue(report['partial'])
        self.assertIsNone(report['selected']['next'])
        self.assertTrue(report['selected']['recommended']['requiresDirection'])
        calls = []

        def old_git(root, argv, **kwargs):
            calls.append(argv)
            self.assertEqual(argv[0], '--no-lazy-fetch')
            self.assertEqual(kwargs['env']['GIT_NO_LAZY_FETCH'], '1')
            self.assertEqual(kwargs['env']['GIT_OPTIONAL_LOCKS'], '0')
            raise FactoryError('unsupported --no-lazy-fetch', 'infrastructure')

        with patch.object(inspection, 'git', side_effect=old_git):
            with self.assertRaises(FactoryError):
                guide.inspect(f.repo)
        self.assertEqual(len(calls), 1)

    def test_unsafe_run_directory_and_state_are_not_followed(self):
        f = self.fixture()
        run = engine.start(f.options)
        neighbor = Path(run['run']).parent / 'ffffffff-0000-4000-8000-000000000001'
        neighbor.symlink_to(run['run'])
        report = self.observe(f, 'ffffffff')
        self.assertTrue(report['partial'])
        self.assertIsNone(report['selected'])
        state = Path(run['run']) / 'state.json'
        original = state.read_bytes()
        state.unlink()
        state.symlink_to(f.repo / 'value.txt')
        report = self.observe(f, run['id'])
        self.assertIsNone(report['selected'])
        self.assertTrue(report['partial'])
        state.unlink()
        state.write_bytes(original)

    def test_cli_human_json_exit_quote_and_help_names(self):
        f = self.fixture()
        run = engine.start(f.options)
        report = self.observe(f, run['id'])
        before = self.snapshot(f.root)
        output = self.cli('guide', '--repo', f.repo, '--select', run['id'], '--json')
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(json.loads(output.stdout), report)
        human = self.cli('guide', '--repo', f.repo, '--select', run['id'])
        self.assertEqual(human.returncode, 0, human.stderr)
        self.assertIn(shlex.join(report['selected']['recommended']['argv']), human.stdout)
        self.assertIn('delivery is historical', human.stdout)
        self.assertEqual(before, self.snapshot(f.root))
        for argv in (('guide',), ('guide', '--repo', f.repo, '--select', '../unsafe')):
            output = self.cli(*argv, '--json')
            self.assertEqual(output.returncode, 2)
            self.assertNotIn('Traceback', output.stderr)
        help_text = self.cli('--help').stdout
        for name in ('guide', 'review-context', 'plan-review', 'pr-description'):
            self.assertIn(name, help_text)
