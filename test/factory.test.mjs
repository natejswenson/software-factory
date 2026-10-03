import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, chmodSync, symlinkSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir, hostname } from 'node:os';
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import { start, describe, resume, submitPlan, submitPlanReview, verify, submitReview, deliver, extend, recover } from '../lib/factory.mjs';
import { git, snapshot } from '../lib/git.mjs';
import { readRun, readJSON, atomicJSON, locked, listRuns } from '../lib/store.mjs';
import { executeCheck, validateConfig } from '../lib/checks.mjs';

const cli = resolve('bin/factory.mjs');
function fixture(t, options = {}) {
  const root = mkdtempSync(join(tmpdir(), 'factory test '));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const repo = join(root, 'source repo'); mkdirSync(repo);
  git(repo, ['init', '-b', 'main']); git(repo, ['config', 'user.name', 'Factory Test']);
  git(repo, ['config', 'user.email', 'factory@example.invalid']);
  writeFileSync(join(repo, '.factory.json'), JSON.stringify({ version: 1, endpoint: options.endpoint || 'local',
    checks: [{ name: 'behavior', argv: [process.execPath, 'check.mjs'], timeoutMs: 2000 }] }, null, 2) + '\n');
  writeFileSync(join(repo, 'value.txt'), 'old\n');
  writeFileSync(join(repo, 'check.mjs'), `import {readFileSync} from 'node:fs'; if (readFileSync('value.txt','utf8').trim() !== 'new') process.exit(1);\n`);
  writeFileSync(join(repo, '.gitignore'), 'ignored*\n');
  git(repo, ['add', '--', '.factory.json', 'value.txt', 'check.mjs', '.gitignore']);
  git(repo, ['commit', '-m', 'fixture baseline']);
  const opts = { repo, worktreeRoot: join(root, 'worktrees'), task: 'Change old to new', criteria: ['value.txt contains new'], base: 'main' };
  return { root, repo, opts };
}
function jsonFile(dir, name, data) { const path = join(dir, name); writeFileSync(path, JSON.stringify(data)); return path; }
async function planned(f) {
  const run = await start(f.opts);
  const plan = join(run.run, 'plan.md'); writeFileSync(plan, '# Plan\nChange value.txt to new. Run the behavior check.\n');
  await submitPlan(run.run, plan);
  const state = describe(readRun(run.run));
  await submitPlanReview(run.run, jsonFile(run.run, 'test-plan-review.json', { reviewer: 'synthetic test fixture', verdict: 'pass', findings: [], context: state.next.context }));
  return describe(readRun(run.run));
}
async function checked(f) {
  const run = await planned(f); writeFileSync(join(run.worktree, 'value.txt'), 'new\n');
  return verify(run.run);
}
function codeReview(run, overrides = {}) {
  return { reviewer: 'synthetic test fixture', verdict: 'pass', findings: [], evidence: run.next.evidence,
    criteria: [{ id: 'AC1', passed: true, evidence: 'behavior check passed' }], ...overrides };
}
async function reviewed(f) {
  const run = await checked(f);
  return submitReview(run.run, jsonFile(run.run, 'test-review.json', codeReview(run)));
}

test('real Git local lifecycle preserves dirty source and resumes idempotently', async t => {
  const f = fixture(t); writeFileSync(join(f.repo, 'value.txt'), 'user dirty change\n');
  const initial = await start(f.opts);
  assert.equal(initial.next.action, 'plan');
  assert.equal((await start(f.opts)).id, initial.id);
  assert.equal((await resume(initial.run)).id, initial.id);
  const run = await reviewed(f); const result = await deliver(run.run);
  assert.equal(result.phase, 'done'); assert.equal(result.delivery.endpoint, 'local');
  assert.equal(git(result.worktree, ['rev-parse', 'HEAD^{tree}']).trim(), result.delivery.tree);
  assert.equal(git(result.worktree, ['status', '--porcelain']).trim(), '');
  assert.equal(readFileSync(join(f.repo, 'value.txt'), 'utf8'), 'user dirty change\n');
  assert.equal((await deliver(run.run)).delivery.commit, result.delivery.commit);
  assert.equal(listRuns(readRun(run.run).common).length, 1);
});
test('missing criteria, checks and uncommitted config cannot start', async t => {
  const f = fixture(t);
  await assert.rejects(start({ ...f.opts, criteria: [] }), /criterion/);
  assert.throws(() => validateConfig({ version: 1, endpoint: 'local', checks: [] }), /at least one/);
  writeFileSync(join(f.repo, '.factory.json'), '{}');
  await assert.rejects(start(f.opts), /version 1/);
});
test('default endpoint is draft PR and base selects a stack layer', async t => {
  const f = fixture(t, { endpoint: 'draft-pr' });
  git(f.repo, ['branch', 'feature/lower']);
  const run = await start({ ...f.opts, base: 'feature/lower' });
  assert.equal(run.endpoint, 'draft-pr'); assert.equal(run.base, 'feature/lower');
  const main = await start(f.opts); assert.notEqual(main.id, run.id); assert.equal(main.base, 'main');
});
test('plan rejection, stale plan and key order are handled', async t => {
  const f = fixture(t); const run = await planned(f);
  writeFileSync(join(run.run, 'plan.md'), '# Revised plan\nDifferent scope\n');
  await assert.rejects(verify(run.run), /plan review/);
  const state = describe(readRun(run.run)); assert.equal(state.next.action, 'plan-review');
  const ctx = Object.fromEntries(Object.entries(state.next.context).reverse());
  const failed = await submitPlanReview(run.run, jsonFile(run.run, 'reject.json', { reviewer: 'fixture', context: ctx, verdict: 'fail', findings: [{ severity: 'major', location: 'plan', issue: 'Missing acceptance coverage' }] }));
  assert.equal(failed.next.action, 'plan'); assert.equal(failed.failures, 1);
});
test('failed executable check is recorded and repair can pass', async t => {
  const f = fixture(t); const run = await planned(f);
  const failed = await verify(run.run);
  assert.equal(failed.verification.passed, false); assert.equal(failed.failures, 1);
  assert.ok(existsSync(join(run.run, 'verification-1.json')));
  await assert.rejects(deliver(run.run), /current verification/);
  writeFileSync(join(run.worktree, 'value.txt'), 'new\n');
  const passed = await verify(run.run); assert.equal(passed.next.action, 'review');
  assert.ok(existsSync(join(run.run, 'verification-1.json')));
});
test('three failures stop; extension requires an explicit reason', async t => {
  const f = fixture(t); const run = await planned(f);
  await verify(run.run); await verify(run.run); const blocked = await verify(run.run);
  assert.equal(blocked.phase, 'blocked'); await assert.rejects(verify(run.run), /Repair limit/);
  await assert.rejects(extend(run.run, 1, ''), /reason/);
  assert.equal((await extend(run.run, 1, 'User directed one more attempt')).phase, 'implement');
});
test('tracked ignored files, modes, symlinks and untracked files invalidate evidence', async t => {
  const f = fixture(t); writeFileSync(join(f.repo, 'ignored-tracked'), 'one');
  git(f.repo, ['add', '-f', '--', 'ignored-tracked']); git(f.repo, ['commit', '-m', 'tracked ignore']);
  const run = await checked(f); const original = run.next.evidence.tree;
  writeFileSync(join(run.worktree, 'ignored-tracked'), 'two');
  assert.notEqual(snapshot(run.worktree, readRun(run.run).base).tree, original);
  assert.equal(describe(readRun(run.run)).next.action, 'verify');
  await assert.rejects(submitReview(run.run, jsonFile(run.run, 'stale.json', codeReview(run))), /verification/);
  writeFileSync(join(run.worktree, 'ignored-tracked'), 'one');
  chmodSync(join(run.worktree, 'check.mjs'), 0o755);
  assert.notEqual(snapshot(run.worktree, readRun(run.run).base).tree, original);
  chmodSync(join(run.worktree, 'check.mjs'), 0o644);
  symlinkSync('value.txt', join(run.worktree, 'link'));
  assert.notEqual(snapshot(run.worktree, readRun(run.run).base).tree, original);
  rmSync(join(run.worktree, 'link')); writeFileSync(join(run.worktree, ':untracked'), 'new');
  assert.notEqual(snapshot(run.worktree, readRun(run.run).base).tree, original);
});
test('check config edits do not weaken frozen checks; edits are reviewed as code', async t => {
  const f = fixture(t); const run = await planned(f);
  writeFileSync(join(run.worktree, '.factory.json'), JSON.stringify({ version: 1, endpoint: 'local', checks: [] }));
  const result = await verify(run.run);
  assert.equal(result.verification.passed, false); assert.equal(result.verification.results[0].name, 'behavior');
});
test('a check that edits the tree cannot certify itself', async t => {
  const f = fixture(t); const run = await planned(f);
  writeFileSync(join(run.worktree, 'check.mjs'), `import {writeFileSync} from 'node:fs'; writeFileSync('value.txt','new');`);
  const result = await verify(run.run);
  assert.equal(result.verification.results[0].passed, true);
  assert.equal(result.verification.passed, false); assert.equal(result.verification.unchanged, false);
});
test('review must cover criteria and cannot pass with major findings', async t => {
  const f = fixture(t); const run = await checked(f);
  await assert.rejects(submitReview(run.run, jsonFile(run.run, 'no-ac.json', codeReview(run, { criteria: [] }))), /every acceptance/);
  await assert.rejects(submitReview(run.run, jsonFile(run.run, 'major.json', codeReview(run, { findings: [{ severity: 'major', location: 'value.txt', issue: 'wrong behavior' }] }))), /unresolved/);
  const failed = await submitReview(run.run, jsonFile(run.run, 'finding.json', codeReview(run, { verdict: 'fail', criteria: [{ id: 'AC1', passed: false, evidence: 'Missing coverage' }] })));
  assert.equal(failed.next.action, 'implement'); assert.equal(failed.failures, 1);
});
test('edits after review and HEAD-only drift prevent delivery', async t => {
  const f = fixture(t); const run = await reviewed(f);
  writeFileSync(join(run.worktree, 'extra'), 'drift');
  await assert.rejects(deliver(run.run), /current verification/); rmSync(join(run.worktree, 'extra'));
  git(run.worktree, ['commit', '--allow-empty', '-m', 'unexpected commit']);
  await assert.rejects(deliver(run.run), /current verification/);
});
test('altered/missing worktree and conflicted index are rejected', async t => {
  const f = fixture(t); const run = await planned(f);
  git(run.worktree, ['checkout', '--detach']);
  await assert.rejects(resume(run.run), /ownership/);
  git(run.worktree, ['checkout', run.branch]);
  rmSync(run.worktree, { recursive: true }); await assert.rejects(resume(run.run), /missing/);
});
test('live locks refuse concurrent mutation; dead same-host locks recover', async t => {
  const f = fixture(t); const run = await start(f.opts);
  await locked(run.run, async () => { await assert.rejects(resume(run.run), /owns this run/); assert.throws(() => recover(run.run), /still alive/); });
  mkdirSync(join(run.run, 'lock')); atomicJSON(join(run.run, 'lock', 'owner.json'), { pid: 2147483647, host: hostname() });
  assert.equal(recover(run.run).operation.recovered, true); assert.equal((await resume(run.run)).phase, 'plan');
});
test('interrupted commit reconciles exact reviewed tree without duplicate commit', async t => {
  const f = fixture(t); const run = await reviewed(f); const state = readRun(run.run);
  const snap = snapshot(run.worktree, state.base);
  state.commitIntent = { parent: snap.head, tree: snap.tree, paths: snap.paths }; atomicJSON(join(run.run, 'state.json'), state);
  git(run.worktree, ['add', '--', ...snap.paths]); git(run.worktree, ['commit', '-m', 'interrupted delivery']);
  const head = git(run.worktree, ['rev-parse', 'HEAD']).trim();
  const result = await deliver(run.run); assert.equal(result.delivery.commit, head); assert.equal(result.phase, 'done');
});
test('interrupted worktree receipt can resume owned worktree', async t => {
  const f = fixture(t); const run = await start(f.opts); const state = readRun(run.run);
  state.phase = 'preparing'; atomicJSON(join(run.run, 'state.json'), state);
  assert.equal((await start(f.opts)).phase, 'plan');
});
test('timeout kills descendant writer and logs are bounded', async t => {
  const f = fixture(t); const script = join(f.root, 'parent.mjs'); const target = join(f.root, 'orphan.txt');
  writeFileSync(script, `import {spawn} from 'node:child_process'; spawn(process.execPath,['-e',${JSON.stringify(`setTimeout(()=>require('fs').writeFileSync(${JSON.stringify(target)},'orphan'),1000);`)}],{stdio:'ignore'}); setInterval(()=>{},100);`);
  const result = await executeCheck({ name: 'timeout', argv: [process.execPath, script], timeoutMs: 150 }, f.root, f.root, 1);
  assert.equal(result.passed, false); assert.equal(result.timedOut, true);
  await new Promise(r => setTimeout(r, 1100)); assert.equal(existsSync(target), false);
  const noisy = await executeCheck({ name: 'noisy', argv: [process.execPath, '-e', "process.stdout.write('x'.repeat(2*1024*1024))"], timeoutMs: 2000 }, f.root, f.root, 2);
  assert.equal(noisy.passed, true); assert.equal(noisy.truncated, true); assert.equal(readFileSync(noisy.log).length, 1024 * 1024);
});
test('argv arguments are literal and missing executable is a failed check', async t => {
  const f = fixture(t); const arg = 'spaces; `echo bad` $(echo bad)';
  const c = await executeCheck({ name: 'literal', argv: [process.execPath, '-e', 'console.log(process.argv[1])', arg], timeoutMs: 2000 }, f.root, f.root, 1);
  assert.equal(readFileSync(c.log, 'utf8').trim(), arg);
  const missing = await executeCheck({ name: 'missing', argv: ['/not/a/real/program'], timeoutMs: 1000 }, f.root, f.root, 2);
  assert.equal(missing.passed, false); assert.match(missing.error, /ENOENT/);
});
test('CLI JSON round trip and duplicate intake is idempotent across processes', async t => {
  const f = fixture(t); const args = ['start', '--repo', f.repo, '--task', f.opts.task, '--criterion', f.opts.criteria[0], '--worktree-root', f.opts.worktreeRoot, '--json'];
  const a = JSON.parse(execFileSync(process.execPath, [cli, ...args], { encoding: 'utf8' }));
  const b = JSON.parse(execFileSync(process.execPath, [cli, ...args], { encoding: 'utf8' }));
  assert.equal(a.id, b.id);
  const status = JSON.parse(execFileSync(process.execPath, [cli, 'next', '--run', a.run, '--json'], { encoding: 'utf8' })); assert.equal(status.next.action, 'plan');
  const child = spawn(process.execPath, [cli, 'start', '--repo', f.repo, '--task', 'No criteria', '--worktree-root', f.opts.worktreeRoot, '--json']);
  const code = await new Promise(r => child.on('close', r)); assert.equal(code, 2);
});

function githubFixture(t, f) {
  const bin = join(f.root, 'mockbin'); mkdirSync(bin);
  const mock = join(bin, 'gh');
  const file = join(f.root, 'mock-pr.json');
  writeFileSync(mock, `#!${process.execPath}\nimport {readFileSync,writeFileSync,existsSync} from 'node:fs'; import {execFileSync} from 'node:child_process';
const args=process.argv.slice(2), file=process.env.MOCK_PR;
if(args[0]==='repo') console.log(JSON.stringify({nameWithOwner:'example/demo',url:'https://github.com/example/demo'}));
else if(args[0]==='issue') console.log(JSON.stringify({number:42,title:'Frozen issue',body:'Change old to new',url:'https://github.com/example/demo/issues/42'}));
else if(args[1]==='list') console.log(existsSync(file)?'['+readFileSync(file,'utf8')+']':'[]');
else if(args[1]==='create') { const get=k=>args[args.indexOf(k)+1]; writeFileSync(file,JSON.stringify({number:1,url:'https://github.com/example/demo/pull/1',isDraft:true,state:'OPEN',headRefName:get('--head'),baseRefName:get('--base'),headRefOid:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim()})); if(process.env.MOCK_FAIL==='1') process.exit(1); console.log('https://github.com/example/demo/pull/1'); } else process.exit(9);\n`);
  chmodSync(mock, 0o755);
  const oldPath = process.env.PATH, oldFile = process.env.MOCK_PR, oldFail = process.env.MOCK_FAIL;
  process.env.PATH = `${bin}:${oldPath}`; process.env.MOCK_PR = file;
  t.after(() => { process.env.PATH = oldPath; for (const [key, value] of [['MOCK_PR', oldFile], ['MOCK_FAIL', oldFail]]) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } });
  const parent = join(f.root, 'example'); mkdirSync(parent); const bare = join(parent, 'demo.git');
  git(f.root, ['init', '--bare', bare]); git(f.repo, ['remote', 'add', 'origin', bare]); git(f.repo, ['push', 'origin', 'main']);
  return file;
}
test('GitHub issue snapshot is frozen and repeated intake reuses identity', async t => {
  const f = fixture(t); githubFixture(t, f);
  const opts = { ...f.opts, task: undefined, issue: '42' };
  const run = await start(opts); assert.match(run.task, /Frozen issue/);
  assert.equal((await start(opts)).id, run.id);
  assert.equal(readRun(run.run).source.snapshot.number, 42);
});
test('draft delivery observes remote head and recovers uncertain PR creation', async t => {
  const f = fixture(t, { endpoint: 'draft-pr' }); const file = githubFixture(t, f);
  const run = await reviewed(f); process.env.MOCK_FAIL = '1';
  await assert.rejects(deliver(run.run), /gh pr/);
  assert.ok(existsSync(file)); assert.equal(readRun(run.run).operation.kind, 'pr-create');
  assert.equal(describe(readRun(run.run)).next.action, 'deliver');
  delete process.env.MOCK_FAIL;
  const created = readJSON(file); const result = await deliver(run.run);
  assert.equal(result.phase, 'done'); assert.equal(result.delivery.pr, created.url);
  assert.equal(result.delivery.commit, created.headRefOid);
  assert.equal(git(run.worktree, ['ls-remote', 'origin', `refs/heads/${run.branch}`]).trim().split(/\s/)[0], created.headRefOid);
});
test('closed, ready, wrong-head or wrong-base PR cannot complete', async t => {
  const f = fixture(t, { endpoint: 'draft-pr' }); const file = githubFixture(t, f);
  const run = await reviewed(f); process.env.MOCK_FAIL = '1'; await assert.rejects(deliver(run.run)); delete process.env.MOCK_FAIL;
  const original = readJSON(file);
  for (const change of [{ isDraft: false }, { state: 'CLOSED' }, { headRefOid: 'wrong' }, { baseRefName: 'wrong' }]) {
    atomicJSON(file, { ...original, ...change }); await assert.rejects(deliver(run.run), /not an open draft/);
    assert.notEqual(readRun(run.run).phase, 'done');
  }
  atomicJSON(file, original); assert.equal((await deliver(run.run)).phase, 'done');
});
test('missing remote does not downgrade the default endpoint', async t => {
  const f = fixture(t, { endpoint: 'draft-pr' }); const run = await reviewed(f);
  const original = process.env.PATH;
  // Reject remote delivery deterministically before an installed gh can attempt network.
  const mockdir = join(f.root, 'offline'); mkdirSync(mockdir); const mock = join(mockdir, 'gh');
  writeFileSync(mock, '#!/bin/sh\nexit 1\n'); chmodSync(mock, 0o755); process.env.PATH = `${mockdir}:${original}`;
  try { await assert.rejects(deliver(run.run), /gh repo/); } finally { process.env.PATH = original; }
  const state = readRun(run.run); assert.equal(state.endpoint, 'draft-pr'); assert.notEqual(state.phase, 'done'); assert.ok(state.delivery.commit);
});
test('repair after interrupted delivery supersedes its old commit intent', async t => {
  const f = fixture(t, { endpoint: 'draft-pr' }); const file = githubFixture(t, f);
  const run = await reviewed(f); process.env.MOCK_FAIL = '1'; await assert.rejects(deliver(run.run)); delete process.env.MOCK_FAIL;
  const old = readRun(run.run).delivery.commit;
  writeFileSync(join(run.worktree, 'new-file'), 'reviewed repair');
  const verified = await verify(run.run); assert.equal(readRun(run.run).commitIntent, null);
  await submitReview(run.run, jsonFile(run.run, 'repair-review.json', codeReview(verified)));
  // An existing PR for the previous head is updated by push, as real GitHub does.
  rmSync(file);
  const result = await deliver(run.run); assert.equal(result.phase, 'done'); assert.notEqual(result.delivery.commit, old);
});
test('renames and already-committed deletions deliver the exact reviewed tree', async t => {
  const f = fixture(t); writeFileSync(join(f.repo, 'original.txt'), 'rename content');
  writeFileSync(join(f.repo, 'delete.txt'), 'delete content');
  git(f.repo, ['add', '--', 'original.txt', 'delete.txt']); git(f.repo, ['commit', '-m', 'rename baseline']);
  const run = await planned(f); writeFileSync(join(run.worktree, 'value.txt'), 'new\n');
  rmSync(join(run.worktree, 'delete.txt')); git(run.worktree, ['add', '--', 'delete.txt']); git(run.worktree, ['commit', '-m', 'delete before verification']);
  const content = readFileSync(join(run.worktree, 'original.txt')); rmSync(join(run.worktree, 'original.txt')); writeFileSync(join(run.worktree, 'renamed.txt'), content);
  const checked = await verify(run.run);
  assert.ok(checked.next.evidence.paths.includes('original.txt')); assert.ok(checked.next.evidence.paths.includes('renamed.txt'));
  await submitReview(run.run, jsonFile(run.run, 'rename-review.json', codeReview(checked)));
  const result = await deliver(run.run); assert.equal(result.phase, 'done');
  assert.equal(git(run.worktree, ['rev-parse', 'HEAD^{tree}']).trim(), checked.next.evidence.tree);
});
test('recovering a killed start also clears its dead allocation lock', async t => {
  const f = fixture(t); const run = await start(f.opts);
  const allocation = join(readRun(run.run).common, 'factory', 'runs');
  mkdirSync(join(allocation, 'lock')); atomicJSON(join(allocation, 'lock', 'owner.json'), { pid: 2147483647, host: hostname() });
  assert.equal(recover(run.run).allocation.recovered, true);
  assert.notEqual((await start({ ...f.opts, task: 'Another task' })).id, run.id);
});

// Summary exercises the public CLI against real lifecycle fixtures. Any manual
// interruption state below belongs only to these temporary synthetic runs.
function summaryOutput(run, json = true) {
  const statePath = join(run.run, 'state.json');
  const before = readFileSync(statePath);
  const status = git(run.worktree, ['status', '--porcelain=v1']);
  const index = git(run.worktree, ['write-tree']);
  const output = spawnSync(process.execPath, [cli, 'summary', '--run', run.run, ...(json ? ['--json'] : [])], { encoding: 'utf8' });
  assert.equal(output.status, readRun(run.run).phase === 'blocked' ? 2 : 0, output.stderr);
  assert.deepEqual(readFileSync(statePath), before, 'summary must preserve saved state bytes');
  assert.equal(git(run.worktree, ['status', '--porcelain=v1']), status);
  assert.equal(git(run.worktree, ['write-tree']), index, 'summary must preserve the index');
  if (!json) return output.stdout;
  assert.equal(output.stdout.trim().split('\n').length, 1, 'JSON is one compact line');
  return JSON.parse(output.stdout);
}
test('summary before checks preserves exact multiline task/criteria and scans in human form', async t => {
  const f = fixture(t);
  const task = 'Fix “empty” output\n\nKeep values: false, 0, `literal` and unicode ✓';
  const run = await start({ ...f.opts, task, criteria: ['Value equals new', 'Keep second criterion\nwith detail'] });
  const output = summaryOutput(run);
  assert.deepEqual(Object.keys(output).sort(), ['id', 'task', 'phase', 'endpoint', 'criteria', 'checks', 'verification', 'findings', 'next', 'delivery'].sort());
  assert.equal(output.task, task); assert.deepEqual(output.criteria, run.criteria);
  assert.deepEqual(output.checks, run.checks.map(c => ({ ...c, result: null })));
  assert.equal(output.verification, null); assert.equal(output.delivery, null);
  assert.deepEqual(output.findings, { plan: [], code: [] });
  assert.deepEqual(output.next, { action: 'plan' });
  const human = summaryOutput(run, false);
  for (const label of ['Task:', 'Criteria:', 'Checks:', 'Findings:', 'Next:', 'Delivery:']) assert.ok(human.includes(label), label);
  assert.ok(human.includes(task)); assert.match(human, /AC2: Keep second criterion/);
  assert.match(human, /behavior: not run/); assert.match(human, /Delivery: pending/);
  assert.ok(!human.includes('"evidence"'));
});
test('summary reports failed check, skipped checks, exact diagnostics and subsequent repair', async t => {
  const f = fixture(t);
  const config = readJSON(join(f.repo, '.factory.json'));
  config.checks.push({ name: 'later', argv: [process.execPath, '-e', 'process.exit(0)'], timeoutMs: 2000 });
  atomicJSON(join(f.repo, '.factory.json'), config); git(f.repo, ['add', '.factory.json']); git(f.repo, ['commit', '-m', 'second check']);
  const run = await planned(f); const failed = await verify(run.run);
  const output = summaryOutput(failed);
  assert.deepEqual(output.checks[0].result, readRun(run.run).verification.results[0]);
  assert.equal(output.checks[0].result.exitCode, 1); assert.equal(output.checks[1].result, null);
  assert.deepEqual(output.verification, { passed: false, unchanged: true, at: failed.verification.at });
  assert.deepEqual(output.next, failed.next);
  const human = summaryOutput(failed, false);
  assert.match(human, /behavior: failed/); assert.match(human, /later: not run/); assert.ok(human.includes(failed.verification.results[0].log));
  writeFileSync(join(run.worktree, 'value.txt'), 'new\n');
  const passed = await verify(run.run); assert.equal(summaryOutput(passed).next.action, 'review');
  assert.ok(summaryOutput(passed).checks.every(c => c.result.passed));
  writeFileSync(join(run.worktree, 'extra'), 'drift');
  const stale = summaryOutput(passed);
  assert.equal(stale.verification.passed, true, 'retain exact last check result');
  assert.equal(stale.next.action, 'verify', 'next reflects drift');
});
test('summary surfaces latest rejected plan/code findings and clears superseded reviews', async t => {
  const f = fixture(t); let run = await planned(f);
  const planFinding = { severity: 'major', location: 'plan:7', issue: 'Missing edge case\nexact detail' };
  const context = readRun(run.run).planReview.context;
  run = await submitPlanReview(run.run, jsonFile(run.run, 'summary-rejected-plan.json', { reviewer: 'synthetic summary fixture', verdict: 'fail', context, findings: [planFinding] }));
  assert.deepEqual(summaryOutput(run).findings, { plan: [planFinding], code: [] });
  assert.equal(summaryOutput(run).next.action, 'plan');
  assert.ok(summaryOutput(run, false).includes(planFinding.issue));
  run = await submitPlanReview(run.run, jsonFile(run.run, 'summary-approved-plan.json', { reviewer: 'synthetic summary fixture', verdict: 'pass', context, findings: [] }));
  writeFileSync(join(run.worktree, 'value.txt'), 'new\n'); run = await verify(run.run);
  const finding = { severity: 'major', location: 'value.txt:1', issue: 'Missing review coverage' };
  run = await submitReview(run.run, jsonFile(run.run, 'summary-rejected-code.json', codeReview(run, { verdict: 'fail', findings: [finding] })));
  assert.deepEqual(summaryOutput(run).findings, { plan: [], code: [finding] });
  assert.equal(summaryOutput(run).next.action, 'implement');
  assert.match(summaryOutput(run, false), /code major value.txt:1/);
  run = await verify(run.run);
  const minor = { severity: 'minor', location: 'value.txt:1', issue: 'Optional polish' };
  run = await submitReview(run.run, jsonFile(run.run, 'summary-approved-code.json', codeReview(run, { findings: [minor] })));
  assert.deepEqual(summaryOutput(run).findings, { plan: [], code: [minor] });
});
test('summary retains timeout and executable error details', async t => {
  for (const timeout of [true, false]) {
    const f = fixture(t); const config = readJSON(join(f.repo, '.factory.json'));
    config.checks[0] = { name: timeout ? 'timeout' : 'missing', argv: timeout ? [process.execPath, '-e', 'setInterval(()=>{},100)'] : ['/not/a/real/program'], timeoutMs: 100 };
    atomicJSON(join(f.repo, '.factory.json'), config); git(f.repo, ['add', '.factory.json']); git(f.repo, ['commit', '-m', 'diagnostic check']);
    const run = await planned(f); const failed = await verify(run.run);
    const result = summaryOutput(failed).checks[0].result;
    assert.deepEqual(result, readRun(run.run).verification.results[0]);
    if (timeout) assert.equal(result.exitCode, null); else assert.notEqual(result.exitCode, 0);
    assert.equal(result.timedOut, timeout);
    const human = summaryOutput(failed, false);
    if (timeout) assert.match(human, /timeout/); else assert.ok(human.includes(result.error));
  }
});
test('summary supports wait, interrupted start, blocked and completed lifecycle without mutation', async t => {
  const f = fixture(t); let run = await start(f.opts);
  await locked(run.run, async () => {
    const output = summaryOutput(run); assert.equal(output.next.action, 'wait');
    assert.equal(output.next.owner.pid, process.pid); assert.equal(output.next.owner.host, hostname());
  });
  const synthetic = readRun(run.run); synthetic.phase = 'preparing'; atomicJSON(join(run.run, 'state.json'), synthetic);
  assert.equal(summaryOutput(run).next.action, 'resume');
  run = await resume(run.run);
  // Re-use this owned run through the normal helper's idempotent intake.
  run = await planned(f); await verify(run.run); await verify(run.run); run = await verify(run.run);
  assert.deepEqual(summaryOutput(run).next, { action: 'blocked', reason: 'Repair limit reached.', failures: 3, limit: 3 });
  await extend(run.run, 1, 'Synthetic test authorizes repair');
  writeFileSync(join(run.worktree, 'value.txt'), 'new\n'); run = await verify(run.run);
  run = await submitReview(run.run, jsonFile(run.run, 'summary-final-review.json', codeReview(run)));
  run = await deliver(run.run);
  const output = summaryOutput(run);
  assert.equal(output.phase, 'done'); assert.deepEqual(output.delivery, run.delivery);
  assert.equal(output.next.action, 'done'); assert.equal(output.next.receipt, join(run.run, 'delivery.json'));
  const human = summaryOutput(run, false); assert.ok(human.includes(run.delivery.commit)); assert.match(human, /Delivery: local/);
});
test('summary shows pending PR receipt during delivery recovery and exact completed draft receipt', async t => {
  const f = fixture(t, { endpoint: 'draft-pr' }); const file = githubFixture(t, f);
  let run = await reviewed(f); process.env.MOCK_FAIL = '1'; await assert.rejects(deliver(run.run)); delete process.env.MOCK_FAIL;
  const partial = summaryOutput(run), state = readRun(run.run);
  assert.deepEqual(partial.delivery, state.delivery); assert.ok(partial.delivery.commit); assert.equal(partial.delivery.pr, undefined);
  assert.equal(partial.next.action, 'deliver'); assert.equal(partial.next.reason, 'Reconcile interrupted delivery.');
  assert.match(summaryOutput(run, false), /PR: pending/);
  assert.ok(existsSync(file)); run = await deliver(run.run);
  const complete = summaryOutput(run); assert.deepEqual(complete.delivery, run.delivery);
  assert.ok(summaryOutput(run, false).includes(run.delivery.pr)); assert.equal(complete.next.action, 'done');
});
