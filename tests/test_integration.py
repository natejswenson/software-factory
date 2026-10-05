"""Real Git integration observations remain offline, bounded and read-only."""

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

from software_factory import cli, engine, integration
from software_factory.delivery import deliver
from software_factory.errors import FactoryError
from software_factory.git import git as git_command
from software_factory.store import atomic_json, locked, read_run
from tests.support import FactoryCase


def git(cwd, argv):
    return git_command(cwd, argv).strip()


class IntegrationTests(FactoryCase):
    def snapshot(self, root):
        result = {}
        for path in root.rglob('*'):
            name = str(path.relative_to(root))
            if path.is_symlink():
                result[name] = ('symlink', os.readlink(path))
            elif path.is_file():
                result[name] = ('file', stat.S_IMODE(path.stat().st_mode), path.read_bytes())
            elif path.is_dir():
                result[name] = ('directory',)
        return result

    def observe(self, fixture, run, target='main'):
        before = self.snapshot(fixture.root)
        original = integration._git
        commands = []

        def read_only(cwd, argv):
            commands.append(argv)
            action = argv[2:] if argv[:1] == ['--git-dir'] else argv
            self.assertIn(action[0], ('rev-parse', 'rev-list'))
            return original(cwd, argv)

        with patch.object(integration, '_git', side_effect=read_only), patch.object(
            engine, 'evidence', side_effect=AssertionError('observer cannot fingerprint/write objects')
        ):
            report = integration.inspect(run['run'], target)
        self.assertEqual(before, self.snapshot(fixture.root))
        return report, commands

    def done(self, fixture):
        run = self.reviewed(fixture)
        return deliver(run['run'])

    def test_help_retains_literal_command_names_across_terminal_widths(self):
        for width in (50, 80, 120):
            parser = cli.parser()
            parser.formatter_class = lambda prog: cli.HelpFormatter(prog, width=width)
            output = parser.format_help()
            command = next(action for action in parser._actions if action.dest == 'command')
            for name in command.help.split(', '):
                self.assertIn(name, output)
            self.assertIn('--target TARGET', output)

    def test_recorded_head_current_head_and_real_target_ancestry_are_separate(self):
        f = self.fixture()
        run = self.done(f)
        head = run['delivery']['commit']
        baseline = git(f.repo, ['rev-parse', 'main'])
        report, _ = self.observe(f, run)
        self.assertEqual(report['recordedDelivery'], run['delivery'])
        self.assertEqual(report['target']['commit'], baseline)
        self.assertEqual(report['head'], {'commit': head, 'source': 'recorded-delivery'})
        self.assertEqual(report['ancestry'], {'targetIsAncestor': True, 'ahead': 1, 'behind': 0})
        self.assertEqual(git(f.repo, ['merge-base', baseline, head]), baseline)
        self.assertTrue(report['current']['headMatchesReceipt'])
        self.assertEqual(integration.exit_code(report), 0)
        git(f.repo, ['update-ref', 'refs/remotes/origin/main', baseline])
        for target in ('refs/heads/main', 'origin/main', 'refs/remotes/origin/main'):
            named, _ = self.observe(f, run, target)
            self.assertEqual(named['target']['commit'], baseline)
            self.assertEqual(named['ancestry'], report['ancestry'])
            self.assertTrue(named['target']['resolvedRef'].startswith('refs/'))
        git(f.repo, ['update-ref', 'refs/heads/main', head])
        equal, _ = self.observe(f, run)
        self.assertEqual(equal['ancestry'], {'targetIsAncestor': True, 'ahead': 0, 'behind': 0})
        git(f.repo, ['update-ref', 'refs/heads/main', baseline])
        (f.repo / 'main-only').write_text('target advance')
        git(f.repo, ['add', 'main-only'])
        git(f.repo, ['commit', '-m', 'target advance'])
        advanced, _ = self.observe(f, run)
        self.assertEqual(advanced['ancestry'], {'targetIsAncestor': False, 'ahead': 1, 'behind': 1})
        self.assertEqual(integration.exit_code(advanced), 0)
        self.assertIn('separately authorized', ' '.join(advanced['nextSteps']))
        git(run['worktree'], ['reset', '--hard', baseline])
        (Path(run['worktree']) / 'uncommitted').write_text('does not change committed ancestry')
        current, _ = self.observe(f, run)
        self.assertEqual(current['head']['commit'], head)
        self.assertEqual(current['ancestry'], advanced['ancestry'])
        self.assertFalse(current['current']['headMatchesReceipt'])
        self.assertEqual(current['current']['head'], baseline)

    def test_undelivered_blocked_legacy_and_disconnected_histories(self):
        f = self.fixture()
        run = engine.start(f.options)
        report, _ = self.observe(f, run)
        self.assertIsNone(report['recordedDelivery'])
        self.assertEqual(report['head']['source'], 'worktree')
        self.assertIsNone(report['current']['headMatchesReceipt'])
        state = read_run(run['run'])
        state.pop('rules', None)
        state['phase'] = 'blocked'
        atomic_json(Path(run['run']) / 'state.json', state)
        blocked, _ = self.observe(f, run)
        self.assertEqual(integration.exit_code(blocked), 0)
        git(f.repo, ['checkout', '--orphan', 'independent'])
        git(f.repo, ['commit', '-m', 'independent root'])
        disconnected, _ = self.observe(f, run, 'independent')
        self.assertFalse(disconnected['ancestry']['targetIsAncestor'])
        self.assertEqual(disconnected['ancestry']['ahead'], 1)
        self.assertEqual(disconnected['ancestry']['behind'], 1)

    def test_real_source_identical_pending_merge_and_cli_exits(self):
        f = self.fixture()
        run = engine.start(f.options)
        git(f.repo, ['commit', '--allow-empty', '-m', 'target ancestry advance'])
        git(run['worktree'], ['commit', '--allow-empty', '-m', 'task ancestry advance'])
        original_tree = git(run['worktree'], ['rev-parse', 'HEAD^{tree}'])
        git(run['worktree'], ['merge', '--no-commit', '--no-ff', 'main'])
        self.assertEqual(git(run['worktree'], ['status', '--porcelain']), '')
        self.assertEqual(git(run['worktree'], ['write-tree']), original_tree)
        report, _ = self.observe(f, run)
        self.assertEqual(report['current']['pendingOperations'], ['merge'])
        self.assertEqual(integration.exit_code(report), 2)
        self.assertEqual(report['errors'], [])
        before = self.snapshot(f.root)
        for human in (False, True):
            output = self.cli('integration', '--run', run['run'], '--target', 'main', *([] if human else ['--json']))
            self.assertEqual(output.returncode, 2, output.stderr)
            self.assertNotIn('Traceback', output.stderr)
            if human:
                self.assertIn('Pending operations: merge', output.stdout)
                self.assertIn('Local target: main at', output.stdout)
            else:
                self.assertEqual(json.loads(output.stdout), report)
        self.assertEqual(before, self.snapshot(f.root))

    def test_real_cherry_pick_and_rebase_conflict_markers(self):
        for action in ('cherry-pick', 'rebase'):
            with self.subTest(action=action):
                f = self.fixture()
                run = engine.start(f.options)
                (f.repo / 'value.txt').write_text('main change\n')
                git(f.repo, ['add', 'value.txt'])
                git(f.repo, ['commit', '-m', 'target conflict'])
                (Path(run['worktree']) / 'value.txt').write_text('task change\n')
                git(run['worktree'], ['add', 'value.txt'])
                git(run['worktree'], ['commit', '-m', 'task conflict'])
                with self.assertRaises(FactoryError):
                    git(run['worktree'], [action, 'main'])
                report, _ = self.observe(f, run)
                self.assertEqual(report['current']['pendingOperations'], [action])
                self.assertEqual(integration.exit_code(report), 2)
                self.assertEqual(report['errors'], [])

    def test_missing_worktree_refs_objects_and_wrong_repository_keep_unknowns(self):
        f = self.fixture()
        run = self.done(f)
        absent, _ = self.observe(f, run, 'absent-target')
        self.assertIsNone(absent['target']['commit'])
        self.assertIsNone(absent['ancestry']['targetIsAncestor'])
        self.assertEqual(integration.exit_code(absent), 3)
        state = read_run(run['run'])
        state['delivery']['commit'] = '0' * 40
        atomic_json(Path(run['run']) / 'state.json', state)
        missing, _ = self.observe(f, run)
        self.assertIsNone(missing['head']['commit'])
        self.assertEqual(integration.exit_code(missing), 3)
        state['delivery'] = run['delivery']
        atomic_json(Path(run['run']) / 'state.json', state)
        Path(run['worktree']).rename(f.root / 'saved worktree')
        unavailable, _ = self.observe(f, run)
        self.assertFalse(unavailable['current']['worktreeAvailable'])
        self.assertIsNone(unavailable['current']['pendingOperations'])
        self.assertEqual(unavailable['head']['commit'], run['delivery']['commit'])
        self.assertTrue(unavailable['ancestry']['targetIsAncestor'])
        self.assertEqual(integration.exit_code(unavailable), 3)
        other = self.fixture()
        state['worktree'] = str(other.repo)
        atomic_json(Path(run['run']) / 'state.json', state)
        wrong, _ = self.observe(f, run)
        self.assertIsNone(wrong['current']['worktreeAvailable'])
        self.assertEqual(integration.exit_code(wrong), 3)

    def test_every_owner_or_malformed_lock_prevents_git_without_takeover(self):
        f = self.fixture()
        run = self.done(f)
        with locked(run['run']):
            owner = Path(run['run']) / 'lock/owner.json'
            for foreign in (False, True):
                if foreign:
                    atomic_json(owner, {'pid': os.getpid(), 'host': 'another-host', 'at': 'synthetic'})
                before = self.snapshot(f.root)
                with patch.object(integration, '_git', side_effect=AssertionError('no Git while owned')):
                    report = integration.inspect(run['run'], 'main')
                self.assertEqual(integration.exit_code(report), 3)
                self.assertEqual(report['recordedDelivery'], run['delivery'])
                self.assertIsNone(report['ancestry']['targetIsAncestor'])
                self.assertIsNotNone(report['current']['owner'])
                self.assertEqual(before, self.snapshot(f.root))
            owner.write_text('{}')
            with patch.object(integration, '_git', side_effect=AssertionError('malformed owner blocks Git')):
                report = integration.inspect(run['run'], 'main')
            self.assertEqual(integration.exit_code(report), 3)
            self.assertIsNone(report['current']['pendingOperations'])

    def test_moving_target_state_and_owner_clear_current_observations(self):
        for field in ('target', 'state', 'owner'):
            with self.subTest(field=field):
                f = self.fixture()
                run = self.done(f)
                original = integration._target
                count = 0

                def moving(common, name):
                    nonlocal count
                    value = original(common, name)
                    count += 1
                    if count == 1:
                        if field == 'target':
                            git(f.repo, ['update-ref', 'refs/heads/main', run['delivery']['commit']])
                        elif field == 'state':
                            state = read_run(run['run'])
                            state['updatedAt'] = 'changed during read'
                            atomic_json(Path(run['run']) / 'state.json', state)
                        else:
                            lock = Path(run['run']) / 'lock'
                            lock.mkdir()
                            atomic_json(lock / 'owner.json', {'pid': os.getpid(), 'host': 'new-owner', 'at': 'synthetic'})
                    return value

                with patch.object(integration, '_target', side_effect=moving):
                    report = integration.inspect(run['run'], 'main')
                self.assertEqual(integration.exit_code(report), 3)
                self.assertIsNone(report['target']['commit'])
                self.assertIsNone(report['current']['pendingOperations'])
                self.assertIsNone(report['ancestry']['targetIsAncestor'])
                self.assertIn('snapshot-changed', [e['code'] for e in report['errors']])
                self.assertEqual(report['recordedDelivery'], run['delivery'])

    def test_moving_head_and_operation_markers_clear_observations(self):
        for field in ('head', 'marker'):
            with self.subTest(field=field):
                f = self.fixture()
                run = self.done(f)
                original = integration._current
                count = 0

                def moving(root, common):
                    nonlocal count
                    value = original(root, common)
                    count += 1
                    if count == 1:
                        if field == 'head':
                            git(root, ['update-ref', 'HEAD', git(f.repo, ['rev-parse', 'main'])])
                        else:
                            marker = Path(git(root, ['rev-parse', '--git-path', 'MERGE_HEAD']))
                            marker.write_text(run['delivery']['commit'] + '\n')
                    return value

                with patch.object(integration, '_current', side_effect=moving):
                    report = integration.inspect(run['run'], 'main')
                self.assertEqual(integration.exit_code(report), 3)
                self.assertIsNone(report['current']['head'])
                self.assertIsNone(report['current']['pendingOperations'])
                self.assertIsNone(report['ancestry']['targetIsAncestor'])
                self.assertIn('snapshot-changed', [e['code'] for e in report['errors']])
                self.assertEqual(report['recordedDelivery'], run['delivery'])

    def test_real_shallow_history_keeps_ancestry_unknown(self):
        f = self.fixture()
        run = self.done(f)
        clone = f.root / 'shallow clone'
        git(f.root, ['clone', '--depth', '1', '--no-single-branch', f.repo.as_uri(), str(clone)])
        self.assertEqual(git(clone, ['rev-parse', '--is-shallow-repository']), 'true')
        state = read_run(run['run'])
        state['common'] = str(clone / '.git')
        state['worktree'] = str(clone)
        atomic_json(Path(run['run']) / 'state.json', state)
        report, _ = self.observe(f, run)
        self.assertEqual(report['head']['commit'], run['delivery']['commit'])
        self.assertIsNone(report['ancestry']['targetIsAncestor'])
        self.assertIsNone(report['ancestry']['ahead'])
        self.assertIsNone(report['ancestry']['behind'])
        self.assertEqual(integration.exit_code(report), 3)
        self.assertIn('ancestry-unavailable', [e['code'] for e in report['errors']])

    def test_promised_missing_commit_never_fetches_or_populates_object_store(self):
        f = self.fixture()
        run = engine.start(f.options)
        commit = git(f.repo, ['rev-parse', 'HEAD'])

        def promisor(name):
            directory = f.root / name
            git(f.root, ['init', '--bare', str(directory)])
            for key, value in (('core.repositoryformatversion', '1'), ('extensions.partialClone', 'origin'),
                               ('remote.origin.url', str(f.repo)), ('remote.origin.promisor', 'true'),
                               ('remote.origin.partialclonefilter', 'blob:none'), ('maintenance.auto', 'false'), ('gc.auto', '0')):
                git(directory, ['config', key, value])
            (directory / 'refs/heads/main').write_text(commit + '\n')
            return directory

        control = promisor('control promisor')
        # Prove this fixture actually fetches without the protection (local transport only).
        self.assertEqual(git(control, ['rev-parse', 'main^{commit}']), commit)
        self.assertTrue(any((control / 'objects/pack').iterdir()))
        directory = promisor('protected promisor')
        state = read_run(run['run'])
        state['common'] = str(directory)
        state['delivery'] = {'endpoint': 'local', 'commit': commit}
        atomic_json(Path(run['run']) / 'state.json', state)
        trace = f.root.parent / (f.root.name + '-git-trace')
        trace.write_text('')
        self.addCleanup(trace.unlink, missing_ok=True)
        with patch.dict(os.environ, {'GIT_TRACE': str(trace)}):
            report, _ = self.observe(f, run)
        self.assertEqual(integration.exit_code(report), 3)
        self.assertIsNone(report['target']['commit'])
        self.assertIsNone(report['head']['commit'])
        self.assertNotRegex(trace.read_text(), r'run_command:.*(?:git fetch|git-upload-pack|index-pack|maintenance run)')
        self.assertEqual(list((directory / 'objects/pack').iterdir()), [])

    def test_invalid_inputs_symlinks_unsafe_markers_and_unsupported_git_fail_closed(self):
        f = self.fixture()
        run = engine.start(f.options)
        for target in ('HEAD', '@', '0' * 40, 'A' * 40, '--help', 'main~1', 'main..other', 'main^{commit}', 'main\nother', 'refs/tags/release'):
            output = self.cli('integration', '--run', run['run'], '--target', target, '--json')
            self.assertEqual(output.returncode, 2, output.stderr)
            self.assertNotIn('Traceback', output.stderr)
            self.assertIn('error', json.loads(output.stderr))
        git(f.repo, ['tag', 'release'])
        output = self.cli('integration', '--run', run['run'], '--target', 'release', '--json')
        self.assertEqual(output.returncode, 2, output.stderr)
        link = f.root / 'run-link'
        link.symlink_to(run['run'])
        output = self.cli('integration', '--run', link, '--target', 'main', '--json')
        self.assertEqual(output.returncode, 2)
        state = Path(run['run']) / 'state.json'
        raw = state.read_bytes()
        state.write_text('{"nested":' + '[' * 1100 + '0' + ']' * 1100 + '}')
        output = self.cli('integration', '--run', run['run'], '--target', 'main', '--json')
        self.assertEqual(output.returncode, 2)
        self.assertNotIn('Traceback', output.stderr)
        state.write_bytes(raw)
        marker = Path(git(run['worktree'], ['rev-parse', '--git-path', 'MERGE_HEAD']))
        marker.symlink_to(f.repo / 'value.txt')
        unsafe, _ = self.observe(f, run)
        self.assertEqual(integration.exit_code(unsafe), 3)
        self.assertIsNone(unsafe['current']['pendingOperations'])
        marker.unlink()
        calls = []

        def old_git(cwd, args, **kwargs):
            calls.append(args)
            self.assertEqual(args[0], '--no-lazy-fetch')
            self.assertEqual(kwargs['env']['GIT_NO_LAZY_FETCH'], '1')
            self.assertEqual(kwargs['env']['GIT_OPTIONAL_LOCKS'], '0')
            raise FactoryError('unknown option --no-lazy-fetch', 'infrastructure')

        with patch.object(integration, 'git', side_effect=old_git):
            report, _ = self.observe(f, run)
        self.assertEqual(integration.exit_code(report), 3)
        self.assertEqual(len(calls), 1)
