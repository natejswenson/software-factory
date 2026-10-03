import { execFileSync } from 'node:child_process';
import { mkdtempSync, realpathSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';

export class FactoryError extends Error {
  constructor(message, code = 'invalid') { super(message); this.code = code; }
}
export function command(argv, cwd, options = {}) {
  try {
    return execFileSync(argv[0], argv.slice(1), {
      cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 30000, maxBuffer: 8 * 1024 * 1024, ...options,
    });
  } catch (e) {
    throw new FactoryError(`${argv[0]} ${argv[1] ?? ''}: ${String(e.stderr || e.message).trim()}`, 'infrastructure');
  }
}
export const git = (cwd, args, options) => command(['git', '--literal-pathspecs', ...args], cwd, options);
export function repository(path) {
  const root = realpathSync(git(resolve(path), ['rev-parse', '--show-toplevel']).trim());
  const common = realpathSync(resolve(root, git(root, ['rev-parse', '--git-common-dir']).trim()));
  return { root, common };
}
export function assertSupported(repo) {
  if (git(repo, ['ls-files', '--unmerged']).trim()) throw new FactoryError('Resolve index conflicts first.');
  if (git(repo, ['ls-files', '--stage']).split('\n').some(x => x.startsWith('160000 '))) {
    throw new FactoryError('Submodules are not supported in this version.');
  }
}
export function snapshot(repo, base) {
  assertSupported(repo);
  const dir = mkdtempSync(join(tmpdir(), 'factory-index-'));
  const env = { ...process.env, GIT_INDEX_FILE: join(dir, 'index') };
  try {
    const head = git(repo, ['rev-parse', 'HEAD']).trim();
    git(repo, ['read-tree', head], { env });
    git(repo, ['add', '-A', '--', '.'], { env });
    const tree = git(repo, ['write-tree'], { env }).trim();
    const paths = git(repo, ['diff', '--no-renames', '--name-only', '-z', base, tree]).split('\0').filter(Boolean);
    return { head, tree, paths };
  } finally { rmSync(dir, { recursive: true, force: true }); }
}
export function assertWorktree(run) {
  let info;
  try { info = repository(run.worktree); } catch { throw new FactoryError('Task worktree is missing. Restore it before resuming.', 'ownership'); }
  if (info.root !== run.worktree || info.common !== run.common ||
      git(run.worktree, ['branch', '--show-current']).trim() !== run.branch) {
    throw new FactoryError('Task worktree ownership changed; refusing to adopt it.', 'ownership');
  }
  if (git(run.worktree, ['merge-base', '--is-ancestor', run.base, 'HEAD']).trim()) {
    throw new FactoryError('Task HEAD no longer descends from its frozen base.', 'ownership');
  }
}
