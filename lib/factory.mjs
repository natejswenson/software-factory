import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { hostname } from 'node:os';
import { command, git, FactoryError, repository, assertSupported, assertWorktree, snapshot } from './git.mjs';
import { atomicJSON, hash, readJSON, readRun, runsRoot, listRuns, locked, save, recoverLock } from './store.mjs';
import { validateConfig, executeCheck } from './checks.mjs';

const text = (value, name) => {
  if (typeof value !== 'string' || !value.trim()) throw new FactoryError(`${name} must be nonempty.`);
  return value.trim();
};
const configFile = '.factory.json';
export function init(repo, checks) {
  const { root } = repository(repo);
  const path = join(root, configFile);
  if (existsSync(path)) throw new FactoryError('.factory.json already exists; inspect it before editing.');
  const config = validateConfig({ version: 1, endpoint: 'draft-pr', checks });
  writeFileSync(path, `${JSON.stringify(config, null, 2)}\n`, { flag: 'wx' });
  return { config: path, next: 'Review and commit .factory.json, then start a task.' };
}
export async function start(options) {
  const repo = repository(options.repo);
  assertSupported(repo.root);
  const source = options.issue ? { kind: 'issue', id: text(options.issue, 'Issue') } : { kind: 'text' };
  const endpoint = options.endpoint;
  const criteria = options.criteria?.map((c, i) => ({ id: `AC${i + 1}`, text: text(c, 'Criterion') }));
  if (!criteria?.length) throw new FactoryError('Supply at least one --criterion.');
  const baseRef = options.base || (git(repo.root, ['branch', '--list', 'main']).trim() ? 'main' : 'HEAD');
  const base = git(repo.root, ['rev-parse', '--verify', `${baseRef}^{commit}`]).trim();
  const configRaw = readFileSync(join(repo.root, configFile), 'utf8');
  const config = validateConfig(JSON.parse(configRaw));
  const selectedEndpoint = endpoint || config.endpoint;
  if (!['local', 'draft-pr'].includes(selectedEndpoint)) throw new FactoryError('Unknown endpoint.');
  if (git(repo.root, ['show', `${base}:${configFile}`]) !== configRaw) {
    throw new FactoryError('Check configuration must be committed on the selected base. Review and commit it first.');
  }
  if (!options.issue) source.text = text(options.task, 'Task');
  const identity = hash({ common: repo.common, source, criteria, endpoint: selectedEndpoint, baseRef, base });
  mkdirSync(runsRoot(repo.common), { recursive: true, mode: 0o700 });
  // Serialize identity allocation as well as worktree creation.
  return locked(runsRoot(repo.common), async () => {
    const matches = listRuns(repo.common).filter(r => r.identity === identity && r.phase !== 'done');
    if (matches.length > 1) throw new FactoryError('Multiple matching runs; select an explicit --run.');
    if (matches.length) {
      const run = matches[0];
      return locked(run.dir, () => { prepare(run); return describe(run); });
    }
    let task = source.text;
    if (options.issue) {
      const issue = JSON.parse(command(['gh', 'issue', 'view', options.issue, '--json', 'number,title,body,url'], repo.root));
      if (!Number.isInteger(issue.number) || typeof issue.title !== 'string' || typeof issue.body !== 'string' || !/^https:\/\//.test(issue.url)) throw new FactoryError('Invalid GitHub issue response.');
      source.snapshot = issue;
      task = `${issue.title}\n\n${issue.body}`;
    }
    const id = randomUUID(), dir = join(runsRoot(repo.common), id);
    const root = resolve(text(options.worktreeRoot, 'Worktree root'));
    mkdirSync(root, { recursive: true });
    const worktree = join(realpathSync(root), `factory-${id.slice(0, 8)}`);
    if (existsSync(worktree)) throw new FactoryError('Worktree path already exists.');
    mkdirSync(dir, { mode: 0o700 });
    const run = { version: 1, id, dir, common: repo.common, repo: repo.root,
      identity, task, source, criteria, config, configHash: hash(configRaw),
      endpoint: selectedEndpoint, baseRef, base, worktree, branch: `factory/${id.slice(0, 8)}`,
      phase: 'preparing', failures: 0, failureLimit: 3, history: [], checkAttempt: 0,
      createdAt: new Date().toISOString() };
    save(run, 'start-intent');
    return locked(dir, () => { prepare(run); return describe(run); });
  });
}
function prepare(run) {
  if (run.phase !== 'preparing') { assertWorktree(run); return; }
  if (existsSync(run.worktree)) {
    assertWorktree(run);
    if (git(run.worktree, ['rev-parse', 'HEAD']).trim() !== run.base) throw new FactoryError('Interrupted start has unexpected worktree HEAD.', 'ownership');
  } else {
    // If Git created the branch before interruption, re-use only its exact base.
    const branchExists = git(run.repo, ['branch', '--list', run.branch]).trim();
    if (branchExists) {
      if (git(run.repo, ['rev-parse', run.branch]).trim() !== run.base) throw new FactoryError('Interrupted start branch changed.', 'ownership');
      git(run.repo, ['worktree', 'add', run.worktree, run.branch]);
    } else git(run.repo, ['worktree', 'add', '-b', run.branch, run.worktree, run.base]);
  }
  writeFileSync(join(run.dir, 'task.md'), `# Task\n\n${run.task}\n\n## Acceptance criteria\n\n${run.criteria.map(c => `- ${c.id}: ${c.text}`).join('\n')}\n`);
  run.phase = 'plan'; save(run, 'worktree-created');
}
function context(run) {
  assertWorktree(run);
  const planPath = join(run.dir, 'plan.md');
  const planHash = existsSync(planPath) ? hash(readFileSync(planPath)) : null;
  return { base: run.base, criteria: hash(run.criteria), config: run.configHash, plan: planHash };
}
function evidence(run) { return { ...context(run), ...snapshot(run.worktree, run.base) }; }
function equal(a, b) { return hash(a) === hash(b); }
function sameEvidence(a, b) {
  return a && b && ['base', 'criteria', 'config', 'plan', 'head', 'tree'].every(k => a[k] === b[k]);
}
function ownDeliveryCommit(run, current) {
  const intent = run.commitIntent;
  return Boolean(intent && current.head !== intent.parent && current.tree === intent.tree &&
    git(run.worktree, ['rev-parse', 'HEAD^']).trim() === intent.parent &&
    run.verification && ['base', 'criteria', 'config', 'plan', 'tree'].every(k => current[k] === run.verification.evidence[k]));
}
function planCurrent(run, ctx) { return run.planReview?.verdict === 'pass' && equal(run.planReview.context, ctx); }
function fail(run, action) {
  run.failures++;
  if (run.failures >= run.failureLimit) run.phase = 'blocked';
  save(run, action, { failures: run.failures });
}
function active(run) {
  if (run.phase === 'done') throw new FactoryError('This run has completed. Start a new task for further work.');
  if (run.phase === 'blocked') throw new FactoryError('Repair limit reached. Report the findings; extend only with user direction.', 'blocked');
}
function checkPlan(run) {
  if (!planCurrent(run, context(run))) throw new FactoryError('Current plan needs a passing plan review.', 'gate');
}
function checkVerified(run) {
  checkPlan(run);
  const current = evidence(run);
  if (!run.verification?.passed || !sameEvidence(run.verification.evidence, current)) throw new FactoryError('Current files need successful verification.', 'gate');
  return current;
}
export function next(run) {
  if (run.phase === 'preparing') return { action: 'resume', reason: 'Reconcile interrupted worktree creation.' };
  if (run.phase === 'done') return { action: 'done', delivery: run.delivery, receipt: join(run.dir, 'delivery.json') };
  if (run.phase === 'blocked') return { action: 'blocked', reason: 'Repair limit reached.', failures: run.failures, limit: run.failureLimit };
  const ctx = context(run);
  if (!ctx.plan) return { action: 'plan', output: join(run.dir, 'plan.md') };
  if (run.planReview?.verdict === 'fail' && equal(run.planReview.context, ctx)) return { action: 'plan', reason: 'Address the rejected plan review.', findings: run.planReview.findings };
  if (!planCurrent(run, ctx)) return { action: 'plan-review', plan: join(run.dir, 'plan.md'), context: ctx };
  if (run.phase === 'implement') return { action: 'implement', reason: run.verification?.passed === false ? 'Fix failed checks, then verify.' : 'Implement the reviewed plan, then verify.' };
  const current = evidence(run);
  if (run.codeReview?.verdict === 'pass' && ownDeliveryCommit(run, current) &&
      sameEvidence(run.codeReview.evidence, run.verification.evidence)) return { action: 'deliver', endpoint: run.endpoint, reason: 'Reconcile interrupted delivery.', evidence: current };
  if (!run.verification?.passed || !sameEvidence(run.verification.evidence, current)) return { action: 'verify', reason: 'Evidence is missing or files changed.' };
  if (!run.codeReview || !sameEvidence(run.codeReview.evidence, current) || run.codeReview.verdict !== 'pass') return { action: 'review', evidence: current };
  return { action: 'deliver', endpoint: run.endpoint, evidence: current };
}
export function describe(run) {
  const ownerPath = join(run.dir, 'lock', 'owner.json');
  const owner = existsSync(ownerPath) ? readJSON(ownerPath) : null;
  const busy = owner && owner.pid !== process.pid;
  return { id: run.id, run: run.dir, task: run.task, worktree: run.worktree,
    branch: run.branch, base: run.baseRef, endpoint: run.endpoint, phase: run.phase,
    failures: run.failures, criteria: run.criteria, checks: run.config.checks,
    next: busy ? { action: 'wait', owner } : next(run),
    plan: join(run.dir, 'plan.md'), taskFile: join(run.dir, 'task.md'),
    verification: run.verification, review: run.codeReview, delivery: run.delivery };
}
export async function mutate(dir, fn) {
  return locked(dir, async () => { const run = readRun(dir); return fn(run); });
}
export async function resume(dir) {
  return mutate(dir, run => { prepare(run); return describe(run); });
}
export async function submitPlan(dir, file) {
  return mutate(dir, run => {
    active(run); assertWorktree(run);
    const content = text(readFileSync(file, 'utf8'), 'Plan');
    if (resolve(file) !== join(dir, 'plan.md')) writeFileSync(join(dir, 'plan.md'), `${content}\n`);
    run.phase = 'plan-review'; run.planReview = null; run.verification = null; run.codeReview = null;
    run.commitIntent = null; run.delivery = null;
    save(run, 'plan-submitted'); return describe(run);
  });
}
function validateReview(input) {
  text(input.reviewer, 'Reviewer');
  if (!['pass', 'fail'].includes(input.verdict) || !Array.isArray(input.findings)) throw new FactoryError('Review needs verdict pass/fail and findings array.');
  for (const f of input.findings) {
    if (!['blocking', 'major', 'minor'].includes(f.severity)) throw new FactoryError('Finding severity must be blocking, major or minor.');
    text(f.location, 'Finding location'); text(f.issue, 'Finding issue');
  }
  if (input.verdict === 'pass' && input.findings.some(f => f.severity !== 'minor')) throw new FactoryError('Passing review contains unresolved blocking/major findings.');
  return input;
}
export async function submitPlanReview(dir, file) {
  return mutate(dir, run => {
    active(run);
    const input = validateReview(readJSON(file)), ctx = context(run);
    if (!ctx.plan || !equal(input.context, ctx)) throw new FactoryError('Plan review context is stale or missing.', 'gate');
    run.planReview = { ...input, at: new Date().toISOString() };
    run.verification = null; run.codeReview = null;
    atomicJSON(join(dir, `plan-review-${run.history.length}.json`), run.planReview);
    run.phase = input.verdict === 'pass' ? 'implement' : 'plan';
    if (input.verdict === 'fail') fail(run, 'plan-review-failed'); else save(run, 'plan-reviewed');
    return describe(run);
  });
}
export async function verify(dir) {
  return mutate(dir, async run => {
    active(run); checkPlan(run);
    const before = evidence(run);
    // A new verification supersedes any interrupted delivery of an older tree.
    run.commitIntent = null; run.delivery = null;
    run.checkAttempt++; run.operation = { kind: 'verify', evidence: before, attempt: run.checkAttempt };
    run.verification = null; run.codeReview = null; save(run, 'verify-intent');
    const results = [];
    for (const check of run.config.checks) {
      const result = await executeCheck(check, run.worktree, dir, run.checkAttempt);
      results.push(result);
      if (!result.passed) break;
    }
    const after = evidence(run);
    const unchanged = sameEvidence(before, after);
    run.verification = { evidence: after, unchanged, results,
      passed: unchanged && results.length === run.config.checks.length && results.every(r => r.passed),
      at: new Date().toISOString() };
    atomicJSON(join(dir, `verification-${run.checkAttempt}.json`), run.verification);
    run.operation = null; run.phase = run.verification.passed ? 'review' : 'implement';
    if (!run.verification.passed) fail(run, 'verify-failed'); else save(run, 'verified');
    return describe(run);
  });
}
export async function submitReview(dir, file) {
  return mutate(dir, run => {
    active(run);
    const current = checkVerified(run), input = validateReview(readJSON(file));
    if (!sameEvidence(input.evidence, current)) throw new FactoryError('Code review evidence is stale or missing.', 'gate');
    if (!Array.isArray(input.criteria) || input.criteria.length !== run.criteria.length ||
        run.criteria.some(c => input.criteria.filter(r => r.id === c.id).length !== 1)) throw new FactoryError('Review must cover every acceptance criterion exactly once.');
    for (const c of input.criteria) { if (typeof c.passed !== 'boolean') throw new FactoryError('Criterion passed must be boolean.'); text(c.evidence, 'Criterion evidence'); }
    if (input.verdict === 'pass' && input.criteria.some(c => !c.passed)) throw new FactoryError('Passing review has an unmet criterion.');
    run.codeReview = { ...input, at: new Date().toISOString() };
    atomicJSON(join(dir, `code-review-${run.history.length}.json`), run.codeReview);
    run.phase = input.verdict === 'pass' ? 'deliver' : 'implement';
    if (input.verdict === 'fail') fail(run, 'code-review-failed'); else save(run, 'code-reviewed');
    return describe(run);
  });
}
export async function extend(dir, count, reason) {
  return mutate(dir, run => {
    if (run.phase !== 'blocked' || !Number.isInteger(count) || count < 1 || count > 10) throw new FactoryError('Extend a blocked run by 1–10 attempts.');
    text(reason, 'User-directed extension reason'); run.failureLimit += count;
    run.phase = run.planReview?.verdict === 'pass' ? 'implement' : 'plan';
    save(run, 'user-extension', { count, reason }); return describe(run);
  });
}
export function recover(dir) {
  const allocation = recoverLock(runsRoot(readRun(dir).common));
  const operation = recoverLock(dir);
  return { allocation, operation };
}
export function recoverAllocation(repo) { return recoverLock(runsRoot(repository(repo).common)); }

function remoteRepo(run) {
  const info = JSON.parse(command(['gh', 'repo', 'view', '--json', 'nameWithOwner,url'], run.worktree));
  if (!/^[\w.-]+\/[\w.-]+$/.test(info.nameWithOwner) || !/^https:\/\//.test(info.url)) throw new FactoryError('Invalid GitHub repository response.');
  return info;
}
function findPR(run, target) {
  const prs = JSON.parse(command(['gh', 'pr', 'list', '--repo', target.nameWithOwner, '--head', run.branch, '--state', 'all', '--json', 'number,url,isDraft,headRefOid,baseRefName,headRefName,state'], run.worktree));
  if (!Array.isArray(prs) || prs.length > 1) throw new FactoryError('Ambiguous PR response; inspect GitHub before retrying.');
  return prs[0] || null;
}
export async function deliver(dir) {
  return mutate(dir, run => {
    if (run.phase === 'done') return describe(run);
    active(run); checkPlan(run);
    const current = evidence(run);
    const intent = run.commitIntent;
    const recoveringCommit = ownDeliveryCommit(run, current);
    if (!run.verification?.passed || !run.codeReview || run.codeReview.verdict !== 'pass' ||
        !(sameEvidence(run.verification.evidence, current) || recoveringCommit) ||
        !sameEvidence(run.codeReview.evidence, run.verification.evidence) ||
        !['base', 'criteria', 'config', 'plan', 'tree'].every(k => current[k] === run.verification.evidence[k])) {
      throw new FactoryError('Delivery requires current verification and passing code review.', 'gate');
    }
    if (!current.paths.length) throw new FactoryError('Task has no changes against its base.');
    if (!intent) {
      run.commitIntent = { parent: current.head, tree: current.tree, paths: current.paths };
      save(run, 'commit-intent');
    }
    if (!recoveringCommit && !run.delivery?.commit) {
      // Index content must also equal reviewed content; no unrelated staged changes.
      const stagePaths = git(run.worktree, ['diff', '--no-renames', '--name-only', '-z', 'HEAD', current.tree]).split('\0').filter(Boolean);
      if (stagePaths.length) git(run.worktree, ['add', '--', ...stagePaths]);
      if (git(run.worktree, ['write-tree']).trim() !== current.tree) throw new FactoryError('Index differs from reviewed tree.', 'drift');
      if (git(run.worktree, ['rev-parse', 'HEAD^{tree}']).trim() !== current.tree) {
        git(run.worktree, ['commit', '-m', `factory: ${run.task.split('\n')[0].slice(0, 100)}`]);
      }
    }
    const final = snapshot(run.worktree, run.base);
    if (final.tree !== current.tree || git(run.worktree, ['rev-parse', 'HEAD^{tree}']).trim() !== final.tree || git(run.worktree, ['status', '--porcelain']).trim()) throw new FactoryError('Final commit/worktree differs from reviewed files.', 'drift');
    run.delivery = { endpoint: run.endpoint, commit: final.head, tree: final.tree, branch: run.branch, at: new Date().toISOString() };
    save(run, 'commit-observed');
    if (run.endpoint === 'draft-pr') {
      const target = remoteRepo(run);
      // A named base is required for GitHub; a SHA/HEAD is valid only for local delivery.
      if (run.baseRef === 'HEAD' || /^[a-f0-9]{40}$/.test(run.baseRef)) throw new FactoryError('Draft PR needs a named --base branch.', 'delivery');
      const baseBranch = run.baseRef.replace(/^origin\//, '');
      const origin = git(run.worktree, ['remote', 'get-url', 'origin']).trim();
      if (!origin.includes(target.nameWithOwner)) throw new FactoryError('origin does not match the selected GitHub repository.', 'delivery');
      run.operation = { kind: 'push', commit: final.head, repository: target.nameWithOwner };
      save(run, 'push-intent');
      git(run.worktree, ['push', '--set-upstream', 'origin', run.branch]);
      const remote = git(run.worktree, ['ls-remote', 'origin', `refs/heads/${run.branch}`]).trim().split(/\s/)[0];
      if (remote !== final.head) throw new FactoryError('Remote head does not match the verified commit.', 'delivery');
      save(run, 'push-observed');
      let pr = findPR(run, target);
      if (!pr) {
        const body = join(dir, 'pr-body.md');
        writeFileSync(body, `## Task\n\n${run.task}\n\n## Acceptance criteria\n\n${run.criteria.map(c => `- ${c.text}`).join('\n')}\n\n## Verification\n\n${run.verification.results.map(c => `- ${c.name}: passed`).join('\n')}\n\nReviewed commit: ${final.head}\n`);
        run.operation = { kind: 'pr-create', commit: final.head, repository: target.nameWithOwner };
        save(run, 'pr-intent');
        command(['gh', 'pr', 'create', '--repo', target.nameWithOwner, '--draft', '--head', run.branch, '--base', baseBranch, '--title', run.task.split('\n')[0].slice(0, 150), '--body-file', body], run.worktree);
        pr = findPR(run, target);
      }
      if (!pr || pr.state !== 'OPEN' || !pr.isDraft || pr.headRefOid !== final.head ||
          pr.headRefName !== run.branch || pr.baseRefName !== baseBranch ||
          !Number.isInteger(pr.number) || !pr.url?.startsWith(`${target.url}/pull/`)) throw new FactoryError('PR is not an open draft for the verified head/base.', 'delivery');
      run.delivery.pr = pr.url; run.delivery.number = pr.number;
    }
    // Changes during remote operations must never acquire a completion receipt.
    if (!sameEvidence({ ...current, head: final.head }, evidence(run)) || git(run.worktree, ['status', '--porcelain']).trim()) throw new FactoryError('Files changed during delivery.', 'drift');
    run.phase = 'done'; run.operation = null;
    atomicJSON(join(dir, 'delivery.json'), run.delivery); save(run, 'completed');
    return describe(run);
  });
}
