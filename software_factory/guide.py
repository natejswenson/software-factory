"""Choose a saved run explicitly and inspect one next command without mutations."""

import hashlib
import os
import re
import shlex
from pathlib import Path
from uuid import UUID

from . import diagnostics, engine, history, inspection, progress, summary
from .errors import FactoryError
from .store import runs_root

LIMITATIONS = [
    'Recorded delivery is local history; merged, released and remote CI states are unknown.',
    'Same-task groups are possible relations, never supersession or completion decisions.',
    'Recommendations are data: execute separately through existing task gates.',
    'Fingerprinting is offline in a disposable Git directory; filters and unsupported inspection remain unknown.',
]
ERRORS = (FactoryError, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError)


def _selection(value):
    if value is None:
        return None
    value = value.lower()
    try:
        if str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    if re.fullmatch(r'[a-f0-9]{8,32}', value):
        return value
    raise FactoryError('--select requires an exact UUID or a hexadecimal prefix of 8–32 characters.')


def _error(report, code, message, run=None):
    report['errors'].append({'code': code, 'message': str(message), 'run': str(run) if run else None})
    report['partial'] = True


def _availability():
    return {'status': 'unknown', 'worktreeAvailable': None, 'owner': None, 'head': None, 'message': None}


def _current(run, owner):
    if owner:
        return {'status': 'locked', 'worktreeAvailable': None, 'owner': owner, 'head': None,
                'message': 'An operation owns this run; source was not inspected.'}, None
    try:
        token = inspection.worktree_token(run)
        return {'status': 'available', 'worktreeAvailable': True, 'owner': None, 'head': token[-1],
                'message': 'Worktree ownership observed; this is not proof freshness.'}, token
    except ERRORS as error:
        result = _availability()
        result.update(status='unavailable', worktreeAvailable=False if not Path(run['worktree']).exists() else None,
                      message=str(error))
        return result, None


def _recommended(run, step, observed_progress=None):
    if run['phase'] == 'done' or step and step['action'] == 'done':
        return None
    path = run['dir']
    action = step['action'] if step else 'unknown'
    argv = ['factory']
    artifact = None
    direction = False
    reasons = {
        'plan': 'Write the plan at the expected artifact path, then submit it.',
        'plan-review': 'Obtain native plan review from this context, then submit its artifact.',
        'implement': 'Implement the reviewed plan or repair findings, then run verification.',
        'review': 'Obtain native code review from this context, then submit its artifact.',
        'verify': 'Run the frozen executable checks.', 'deliver': 'Deliver through the reviewed requested endpoint.',
        'resume': 'Reconcile the recorded interrupted operation through the engine.',
        'wait': 'Observe the owning operation; do not recover a live lock.',
        'blocked': 'Inspect findings; extending the repair budget requires explicit user direction.',
        'unknown': 'Inspect saved history; resolve unavailable inputs before any task mutation.',
    }
    if action == 'plan':
        artifact = str(Path(path) / 'plan.md')
        argv += ['plan', '--run', path, '--file', artifact]
    elif action in ('plan-review', 'review'):
        stage = 'plan' if action == 'plan-review' else 'code'
        artifact = str(Path(path) / ('plan-review.json' if stage == 'plan' else 'code-review.json'))
        argv += ['review-context', '--run', path, '--stage', stage, '--json']
    elif action in ('implement', 'verify', 'deliver', 'resume'):
        argv += ['verify' if action == 'implement' else action, '--run', path, '--json']
    elif action == 'wait':
        argv += ['progress' if run['checkAttempt'] else 'status', '--run', path, '--json']
        direction = bool(observed_progress and observed_progress['status'] in ('unknown', 'interrupted'))
    else:
        argv += ['explain' if action == 'blocked' else 'history', '--run', path, '--json']
        direction = True
    reason = reasons.get(action, reasons['unknown'])
    if step and step.get('reason'):
        reason = step['reason'] + ' ' + reason
    return {'argv': argv, 'reason': reason, 'requiresDirection': direction, 'artifact': artifact}


def _clear(selected):
    selected.update(next=None, diagnostics=None, progress=None, summary=None)
    selected['currentAvailability'] = _availability()
    selected['currentAvailability']['message'] = 'Current observation changed or is unavailable.'


def _selected(path, root_fd, common, report):
    selected = None
    with history._directory(path, parent_fd=root_fd) as fd:
        raw = history._read(fd, 'state.json')
        run = history._run(raw, path, common=str(common))
        selected = {'id': run['id'], 'run': str(path), 'phase': run['phase'],
                    'recordedOutcome': run.get('delivery'), 'currentAvailability': _availability(),
                    'next': None, 'findings': {'plan': (run.get('planReview') or {}).get('findings', []),
                                              'code': (run.get('codeReview') or {}).get('findings', [])},
                    'diagnostics': None, 'progress': None, 'recommended': None, 'summary': None}
        owner = None
        try:
            owner = history._owner(fd)
            available, token = _current(run, owner)
            selected['currentAvailability'] = available
            verifying = (isinstance(run.get('operation'), dict) and run['operation'].get('kind') == 'verify'
                         and run['phase'] != 'done')
            terminal = run['phase'] in ('done', 'blocked', 'preparing') or run.get('renameIntent')
            if run['phase'] == 'done':
                step = engine.next_action(run)
            elif owner or verifying:
                step = {'action': 'wait', 'owner': owner, 'reason': 'Inspect verification ownership.' if verifying and not owner else 'An operation owns the run.'}
            elif terminal:
                step = engine.next_action(run)
            else:
                step = None
            first = sidecar = None
            active_progress = False
            if verifying:
                active_progress = True
                sidecar = history._read(fd, progress.SIDECAR, optional=True)
                if sidecar is not None:
                    history._json(sidecar)
                selected['progress'] = progress.project(run, (raw, sidecar, owner, list(progress.LIMITATIONS)))
                if selected['progress']['status'] in ('unknown', 'interrupted'):
                    _error(report, 'progress-unavailable', 'Live progress is unknown or interrupted.', path)
            if available['status'] == 'unavailable':
                _error(report, 'worktree-unavailable', available['message'], path)
            elif not owner and not terminal and not verifying:
                plan = history._read(fd, 'plan.md', optional=True)
                first = inspection.capture(run, plan)
                step = engine.next_action(run, captured_plan=plan, observation=first)
                gates = diagnostics.proof_gates(run, first['context'], first['evidence'])
                if any(gate['status'] != 'current' for gate in gates.values()):
                    selected['diagnostics'] = {'gates': gates, 'changedPaths': first['changedPaths']}
                second = inspection.capture(run, plan)
                if first != second or plan != history._read(fd, 'plan.md', optional=True):
                    raise FactoryError('Source, context or ownership changed during inspection.', 'snapshot-changed')
            selected['next'] = step
            selected['summary'] = summary.summarize(run, captured_next=step or {'action': 'unknown'})
            if token is not None and inspection.worktree_token(run) != token:
                raise FactoryError('Worktree changed during inspection.', 'snapshot-changed')
            if active_progress and sidecar != history._read(fd, progress.SIDECAR, optional=True):
                raise FactoryError('Progress changed during inspection.', 'snapshot-changed')
            if history._owner(fd) != owner:
                raise FactoryError('Owner changed during inspection.', 'snapshot-changed')
            history._unchanged(path, fd, raw)
        except ERRORS as error:
            _clear(selected)
            _error(report, error.code if isinstance(error, FactoryError) else 'inspection', error, path)
            # Terminal historical receipt stays terminal; no mutation can be recommended.
            if run['phase'] == 'done':
                selected['next'] = {'action': 'done', 'reason': 'Recorded terminal delivery; current inspection unavailable.'}
        selected['recommended'] = _recommended(run, selected['next'], selected['progress'])
    return selected


def inspect(repo, *, select=None):
    selection = _selection(select)  # Reject traversal/short prefixes before any filesystem/Git access.
    root, common = inspection.repository(repo)
    directory = runs_root(str(common))
    report = {'version': 1, 'repo': str(root), 'runs': [], 'possibleRelations': [], 'selected': None,
              'candidates': [], 'omitted': {'total': 0, 'unfinished': 0, 'recent': 0},
              'errors': [], 'partial': False, 'limitations': list(LIMITATIONS)}
    if not directory.exists() and not directory.is_symlink():
        if selection:
            _error(report, 'selection-absent', 'No matching saved run.', directory)
        return report
    try:
        with (history._directory(common) as common_fd,
              history._directory(directory.parent, parent_fd=common_fd) as factory_fd,
              history._directory(directory, parent_fd=factory_fd) as fd):
            with os.scandir(fd) as entries:
                names = sorted(entry.name for entry in entries if history.RUN_NAME.fullmatch(entry.name))
            matches = [] if selection is None else [name for name in names if (
                name == selection if '-' in selection else name.replace('-', '').startswith(selection))]
            if selection and len(matches) != 1:
                report['candidates'] = matches
                _error(report, 'selection-ambiguous' if matches else 'selection-absent',
                       'Select one exact run; matches are candidates only.', directory)
            records = []
            for name in names:
                path = directory / name
                try:
                    with history._directory(path, parent_fd=fd) as run_fd:
                        raw = history._read(run_fd, 'state.json')
                        run = history._run(raw, path, common=str(common))
                        date = history._date(run.get('updatedAt')) or history._date(run.get('createdAt'))
                        if date is None:
                            _error(report, 'timestamp', 'Saved timestamp unavailable; sorting last.', path)
                        relation = hashlib.sha256(' '.join(run['task'].split()).encode()).hexdigest()
                        row = {'id': name, 'run': str(path), 'taskTitle': run['task'].splitlines()[0][:300],
                               'phase': run['phase'], 'endpoint': run['endpoint'],
                               'recordedOutcome': {key: run['delivery'][key] for key in ('endpoint', 'commit', 'pr', 'at')
                                                   if key in run.get('delivery', {})} if run.get('delivery') else None,
                               'currentAvailability': _availability()}
                        history._unchanged(path, run_fd, raw)
                        records.append((row, date, relation, hashlib.sha256(raw).hexdigest()))
                except ERRORS as error:
                    _error(report, 'record-unavailable', error, path)
            records.sort(key=lambda item: (item[0]['phase'] == 'done', item[1] is None,
                                           -item[1].timestamp() if item[1] else 0, item[0]['id']))
            unfinished = [item for item in records if item[0]['phase'] != 'done']
            recent = [item for item in records if item[0]['phase'] == 'done'][:20]
            visible = (unfinished + recent)[:100]
            report['omitted'] = {'total': len(records) - len(visible),
                                 'unfinished': len(unfinished) - sum(item[0]['phase'] != 'done' for item in visible),
                                 'recent': sum(item[0]['phase'] == 'done' for item in records) - sum(
                                     item[0]['phase'] == 'done' for item in visible)}
            relations = {}
            for row, _, relation, saved_hash in visible:
                path = Path(row['run'])
                try:
                    with history._directory(path, parent_fd=fd) as run_fd:
                        raw = history._read(run_fd, 'state.json')
                        run = history._run(raw, path, common=str(common))
                        if hashlib.sha256(raw).hexdigest() != saved_hash:
                            raise FactoryError('Recorded row changed before inspection.', 'snapshot-changed')
                        owner = history._owner(run_fd)
                        current, token = _current(run, owner)
                        if token and token != inspection.worktree_token(run):
                            raise FactoryError('Worktree changed.', 'snapshot-changed')
                        history._unchanged(path, run_fd, raw)
                        if owner != history._owner(run_fd):
                            raise FactoryError('Owner changed.', 'snapshot-changed')
                        row['currentAvailability'] = current
                        if current['status'] == 'unavailable':
                            _error(report, 'worktree-unavailable', current['message'], path)
                except ERRORS as error:
                    _error(report, 'inspection-unavailable', error, path)
                report['runs'].append(row)
                relations.setdefault(relation, []).append(row['id'])
            report['possibleRelations'] = [{'taskHash': key, 'candidates': ids, 'kind': 'possible-same-task'}
                                           for key, ids in sorted(relations.items()) if len(ids) > 1]
            if selection and len(matches) == 1:
                try:
                    report['selected'] = _selected(directory / matches[0], fd, common, report)
                except ERRORS as error:
                    _error(report, 'selected-unavailable', error, directory / matches[0])
    except ERRORS as error:
        raise FactoryError(f'Cannot enumerate saved runs: {error}', 'infrastructure') from error
    return report


def exit_code(report):
    return 2 if report['partial'] or report['selected'] and report['selected']['phase'] == 'blocked' else 0


def _human(value):
    return ''.join(f'\\x{ord(char):02x}' if ord(char) < 32 or ord(char) == 127 else char for char in str(value))


def format_report(report):
    lines = ['Saved runs (unfinished first; delivery is historical):']
    for row in report['runs']:
        outcome = row['recordedOutcome']
        label = f"recorded {outcome.get('endpoint', 'unknown')}" if outcome else 'undelivered'
        lines.append(_human(f"{row['id']}  {row['phase']}  {row['taskTitle']} — {label}; "
                            f"current {row['currentAvailability']['status']}"))
    if report['omitted']['total']:
        lines.append(f"Omitted: {report['omitted']['total']} (explicit selection still searches all names)")
    for relation in report['possibleRelations']:
        lines.append('Possible same-task attempts: ' + ', '.join(relation['candidates']))
    selected = report['selected']
    if selected:
        outcome = selected['recordedOutcome']
        recorded = 'none (undelivered)' if outcome is None else str(outcome.get('endpoint', 'unknown'))
        step = selected['next']
        next_label = step['action'] if step else 'unavailable'
        if step and step.get('reason'):
            next_label += ' — ' + step['reason']
        lines.extend(['', f"Selected: {selected['id']}", 'Recorded delivery: ' + _human(recorded),
                      'Current: ' + selected['currentAvailability']['status'], 'Next: ' + _human(next_label)])
        if outcome:
            lines.append('Recorded commit: ' + _human(outcome.get('commit', 'unknown')))
            if outcome.get('pr'):
                lines.append('Recorded PR: ' + _human(outcome['pr']))
        for stage, findings in selected['findings'].items():
            for finding in findings:
                lines.append(_human(f"Finding {stage}: {finding['severity']} {finding['location']}: {finding['issue']}"))
        if selected['diagnostics']:
            for name, gate in selected['diagnostics']['gates'].items():
                lines.append(f"Proof {name}: {gate['status']}")
                lines.extend('  ' + _human(reason) for reason in gate['reasons'])
        if selected['progress']:
            lines.append('Progress: ' + selected['progress']['status'])
        recommended = selected['recommended']
        if recommended:
            lines.extend(['Recommended: ' + _human(shlex.join(recommended['argv'])),
                          'Reason: ' + _human(recommended['reason']),
                          f"Requires direction: {recommended['requiresDirection']}"])
        else:
            lines.append('Recommended: none (recorded terminal delivery)')
    if report['candidates']:
        lines.append('Selection candidates: ' + ', '.join(report['candidates']))
    lines.extend(_human(f"Unavailable {item['code']}: {item['message']}") for item in report['errors'])
    if report['partial']:
        lines.append('Partial observation; unknown inputs do not establish readiness.')
    lines.extend('Limit: ' + item for item in report['limitations'])
    return '\n'.join(lines)
