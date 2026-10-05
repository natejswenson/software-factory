"""Offline task fingerprints in a disposable Git directory, never the real store."""

import json
import os
import re
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

from . import engine, history, rules
from .errors import FactoryError
from .git import git
from .store import fingerprint

OBJECT = re.compile(r'(?:[a-f0-9]{40}|[a-f0-9]{64})')
SAFE_CORE = {'core.autocrlf', 'core.eol', 'core.filemode', 'core.ignorecase', 'core.symlinks',
             'core.safecrlf', 'core.checkroundtripencoding', 'core.precomposeunicode',
             'core.protecthfs', 'core.protectntfs', 'core.bigfilethreshold'}


def read_git(root, argv, *, isolated=None):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('GIT_TRACE') or (isolated is not None and (key.startswith('GIT_CONFIG_') or key == 'GIT_CONFIG')) or key in (
            'GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
            'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_NAMESPACE',
        ):
            env.pop(key, None)
    env.update(GIT_OPTIONAL_LOCKS='0', GIT_NO_LAZY_FETCH='1')
    options = ['--no-lazy-fetch', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
               '-c', 'core.untrackedCache=false', '-c', 'core.splitIndex=false']
    if isolated is not None:
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null',
                   GIT_DIR=str(isolated), GIT_WORK_TREE=str(root), GIT_INDEX_FILE=str(isolated / 'index'))
    return git(root, [*options, *argv], env=env).strip()


def repository(repo):
    root = Path(repo).resolve()
    root = Path(read_git(root, ['rev-parse', '--show-toplevel'])).resolve()
    common = (root / read_git(root, ['rev-parse', '--git-common-dir'])).resolve()
    return root, common


def worktree_token(run):
    root, common = Path(run['worktree']), Path(run['common'])
    info = root.lstat()
    shared = common.lstat()
    if not stat.S_ISDIR(info.st_mode) or not stat.S_ISDIR(shared.st_mode):
        raise FactoryError('Worktree/common directory is unavailable or unsafe.', 'inspection')
    actual, actual_common = repository(root)
    branch = read_git(root, ['branch', '--show-current'])
    head = read_git(root, ['rev-parse', '--verify', 'HEAD^{commit}'])
    if actual != root or actual_common != common or branch != run['branch'] or not OBJECT.fullmatch(head):
        raise FactoryError('Worktree ownership or HEAD is unavailable.', 'inspection')
    return (info.st_dev, info.st_ino, shared.st_dev, shared.st_ino, head)


def _file(path):
    if not path.exists() and not path.is_symlink():
        return None
    with history._directory(path.parent) as fd:
        return history._read(fd, path.name, optional=True)


def inputs(run):
    root = Path(run['worktree'])
    raw = read_git(root, ['config', '--null', '--list'])
    values = {}
    for entry in raw.split('\0'):
        if entry:
            key, _, value = entry.partition('\n')
            values[key.lower()] = value
    if any(key.startswith('filter.') for key in values):
        raise FactoryError('Configured filter drivers cannot be executed by guide.', 'inspection')
    if values.get('core.sparsecheckout', '').lower() in ('true', 'yes', 'on', '1'):
        raise FactoryError('Sparse worktree fingerprinting is unavailable.', 'inspection')
    local = root / read_git(root, ['rev-parse', '--git-path', 'info/attributes'])
    default = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'git/attributes'
    global_path = Path(values.get('core.attributesfile', str(default))).expanduser()
    if not global_path.is_absolute():
        global_path = root / global_path
    local_exclude = root / read_git(root, ['rev-parse', '--git-path', 'info/exclude'])
    default_exclude = default.with_name('ignore')
    global_exclude = Path(values.get('core.excludesfile', str(default_exclude))).expanduser()
    if not global_exclude.is_absolute():
        global_exclude = root / global_exclude
    return raw, values, _file(local), _file(global_path), _file(local_exclude), _file(global_exclude)


def _rules(root):
    directory = root / '.rules'
    if not directory.exists() and not directory.is_symlink():
        return rules._bundle([])
    with history._directory(directory) as fd:
        with os.scandir(fd) as entries:
            names = sorted(entry.name for entry in entries if entry.name.endswith('.md'))
        if len(names) > rules.MAX_FILES:
            raise FactoryError('Too many rule files.', 'inspection')
        return rules._bundle([(f'.rules/{name}', history._read(fd, name, limit=rules.MAX_FILE)) for name in names])


def _temporary_parent(run):
    sources = [Path(run[key]).resolve() for key in ('worktree', 'repo', 'common')]
    sources.append(Path(run['common']).parent.resolve())
    for name in ('/tmp', '/var/tmp'):
        parent = Path(name).resolve()
        if parent.is_dir() and not any(parent.is_relative_to(source) for source in sources):
            return parent
    raise FactoryError('No temporary directory outside source is available.', 'inspection')


def capture(run, plan):
    root = Path(run['worktree'])
    token = worktree_token(run)
    if not OBJECT.fullmatch(run['base']):
        raise FactoryError('Frozen base is not an object ID.', 'inspection')
    read_git(root, ['merge-base', '--is-ancestor', run['base'], token[-1]])
    ctx = {'base': run['base'], 'criteria': fingerprint(run['criteria']), 'config': run['configHash'],
           'plan': fingerprint(plan) if plan is not None else None}
    if run.get('rules'):
        current_rules = _rules(root)
        rules.configuration(current_rules, run['config'])
        ctx['rules'] = current_rules['hash']
    # Mirror next_action's lazy capture: context-only actions need no staged tree.
    if not engine.plan_current(run, ctx) or run['phase'] == 'implement':
        return {'context': ctx, 'evidence': None, 'ownedDelivery': False,
                'changedPaths': {'baseline': None, 'available': False, 'paths': []}, 'token': token, 'inputs': None}
    raw, values, local_attributes, global_attributes, local_exclude, global_exclude = inputs(run)
    object_format = read_git(root, ['rev-parse', '--show-object-format'])
    if object_format not in ('sha1', 'sha256'):
        raise FactoryError('Unsupported object format.', 'inspection')
    with TemporaryDirectory(prefix='factory-guide-', dir=_temporary_parent(run)) as temporary:
        isolated = Path(temporary) / 'git'
        for name in ('objects/info', 'objects/pack', 'refs', 'info'):
            (isolated / name).mkdir(parents=True, exist_ok=True)
        objects = str(Path(run['common']) / 'objects')
        if '\n' in objects:
            raise FactoryError('Object alternate path is unsupported.', 'inspection')
        (isolated / 'objects/info/alternates').write_text(objects + '\n')
        (isolated / 'HEAD').write_text(token[-1] + '\n')
        config = '[core]\n repositoryformatversion = ' + ('1' if object_format == 'sha256' else '0') + '\n bare = false\n'
        for key in sorted(SAFE_CORE & values.keys()):
            config += f' {key.split(".", 1)[1]} = {json.dumps(values[key], ensure_ascii=False)}\n'
        attributes = isolated / 'global-attributes'
        attributes.write_bytes(global_attributes or b'')
        config += f' attributesFile = {json.dumps(str(attributes))}\n'
        excludes = isolated / 'global-ignore'
        excludes.write_bytes(global_exclude or b'')
        config += f' excludesFile = {json.dumps(str(excludes))}\n'
        if object_format == 'sha256':
            config += '[extensions]\n objectFormat = sha256\n'
        (isolated / 'config').write_text(config)
        (isolated / 'info/attributes').write_bytes(local_attributes or b'')
        (isolated / 'info/exclude').write_bytes(local_exclude or b'')
        read = lambda argv: read_git(root, argv, isolated=isolated)
        if read(['ls-files', '--unmerged']):
            raise FactoryError('Index conflicts make current proof unavailable.', 'inspection')
        # Inspect the real index too; the isolated index has not been created yet.
        if read_git(root, ['ls-files', '--unmerged']) or any(
            line.startswith('160000 ') for line in read_git(root, ['ls-files', '--stage']).splitlines()
        ):
            raise FactoryError('Conflicts/submodules make current proof unavailable.', 'inspection')
        read(['read-tree', token[-1]])
        read(['add', '-A', '--', '.'])
        tree = read(['write-tree'])
        paths = sorted(p for p in read(['diff', '--no-ext-diff', '--no-textconv', '--no-renames',
                                       '--name-only', '-z', run['base'], tree, '--']).split('\0') if p)
        current = {**ctx, 'head': token[-1], 'tree': tree, 'paths': paths}
        owned = False
        intent = run.get('commitIntent')
        verification = run.get('verification')
        if intent and verification and token[-1] != intent['parent'] and tree == intent['tree']:
            owned = read(['rev-parse', 'HEAD^']) == intent['parent'] and all(
                current.get(key) == verification['evidence'].get(key) for key in engine.EVIDENCE_KEYS if key != 'head')
        changed = {'baseline': None, 'available': False, 'paths': []}
        for name in ('verification', 'codeReview'):
            record = run.get(name)
            saved = record.get('evidence') if isinstance(record, dict) else None
            if isinstance(saved, dict) and isinstance(saved.get('tree'), str):
                if not OBJECT.fullmatch(saved['tree']):
                    raise FactoryError('Saved tree is malformed.', 'inspection')
                changed = {'baseline': name, 'available': True, 'paths': sorted(p for p in read(
                    ['diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--name-only', '-z',
                     saved['tree'], tree, '--']).split('\0') if p)}
                break
    return {'context': ctx, 'evidence': current, 'ownedDelivery': owned, 'changedPaths': changed,
            'token': token, 'inputs': fingerprint([raw, fingerprint(local_attributes or b''),
                                                 fingerprint(global_attributes or b''),
                                                 fingerprint(local_exclude or b''), fingerprint(global_exclude or b'')])}
