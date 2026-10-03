#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { init, start, describe, resume, taskRules, submitPlan, submitPlanReview, verify, submitReview, deliver, extend, recover, recoverAllocation } from '../lib/factory.mjs';
import { readRun, listRuns } from '../lib/store.mjs';
import { repository, FactoryError } from '../lib/git.mjs';
import { summarize, formatSummary } from '../lib/summary.mjs';

const help = `Software Factory — take one task to verified delivery in your current agent session.

  factory init --repo PATH --check '["npm","test"]'
  factory start --repo PATH --task "Fix the bug" --criterion "Observable outcome"
                --worktree-root PATH [--base main] [--endpoint local|draft-pr]
  factory start --repo PATH --issue 42 --criterion "Outcome" --worktree-root PATH
  factory list --repo PATH
  factory status|next|resume --run PATH
  factory summary --run PATH [--json]
  factory rules --run PATH [--json]
  factory plan|plan-review|review --run PATH --file PATH
  factory verify|deliver --run PATH
  factory recover --run PATH | --repo PATH
  factory extend --run PATH --attempts 1 --reason "User directed another attempt"

  Use --json for machine-readable output. Repeat --criterion and --check.
  --task-file PATH accepts task text without shell quoting. No model calls or daemon.
  Plan/review schemas and the host workflow: skills/software-factory/SKILL.md
`;
let json = false;
try {
  const { values, positionals } = parseArgs({ allowPositionals: true, options: {
    repo: { type: 'string' }, run: { type: 'string' }, task: { type: 'string' },
    'task-file': { type: 'string' }, issue: { type: 'string' },
    criterion: { type: 'string', multiple: true }, base: { type: 'string' },
    'worktree-root': { type: 'string' }, endpoint: { type: 'string' },
    file: { type: 'string' }, check: { type: 'string', multiple: true },
    attempts: { type: 'string' }, reason: { type: 'string' },
    json: { type: 'boolean' }, help: { type: 'boolean', short: 'h' },
  } });
  json = Boolean(values.json);
  const action = positionals[0];
  if (values.help || !action || action === 'help') { console.log(help); process.exit(0); }
  if (positionals.length !== 1) throw new FactoryError('Use exactly one command.');
  const required = key => { if (!values[key]) throw new FactoryError(`Missing --${key}.`); return values[key]; };
  const run = () => resolve(required('run'));
  let result;
  switch (action) {
    case 'init': result = init(required('repo'), (values.check || []).map((c, i) => ({ name: `check${i + 1}`, argv: JSON.parse(c), timeoutMs: 120000 }))); break;
    case 'start': {
      if ([values.task, values['task-file'], values.issue].filter(Boolean).length !== 1) throw new FactoryError('Choose exactly one of --task, --task-file or --issue.');
      result = await start({ repo: required('repo'),
        task: values['task-file'] ? readFileSync(values['task-file'], 'utf8') : values.task,
        issue: values.issue, criteria: values.criterion, base: values.base,
        endpoint: values.endpoint, worktreeRoot: required('worktree-root') }); break;
    }
    case 'list': result = listRuns(repository(required('repo')).common).map(r => ({ id: r.id, task: r.task.split('\n')[0], phase: r.phase, endpoint: r.endpoint, run: r.dir })); break;
    case 'status': case 'next': result = describe(readRun(run())); break;
    case 'summary': result = summarize(readRun(run())); break;
    case 'rules': result = taskRules(readRun(run())); break;
    case 'resume': result = await resume(run()); break;
    case 'plan': result = await submitPlan(run(), required('file')); break;
    case 'plan-review': result = await submitPlanReview(run(), required('file')); break;
    case 'verify': result = await verify(run()); break;
    case 'review': result = await submitReview(run(), required('file')); break;
    case 'deliver': result = await deliver(run()); break;
    case 'recover': result = values.run ? recover(run()) : recoverAllocation(required('repo')); break;
    case 'extend': result = await extend(run(), Number(required('attempts')), required('reason')); break;
    default: throw new FactoryError(`Unknown command: ${action}. Use --help.`);
  }
  if (json) console.log(JSON.stringify(result, null, action === 'summary' ? undefined : 2));
  else if (action === 'summary') console.log(formatSummary(result));
  else if (action === 'rules') console.log(result.enabled
    ? result.files.map(f => `# ${f.path}\n\n${f.content}`).join('\n\n') || 'No repository rules.'
    : 'Legacy run: repository rules were not enabled at start.');
  else if (Array.isArray(result)) {
    console.log('TASK\tSTATE\tENDPOINT\tRUN');
    for (const r of result) console.log(`${r.task}\t${r.phase}\t${r.endpoint}\t${r.run}`);
  } else if (result.id) {
    console.log(`${result.task.split('\n')[0]}\n\nState: ${result.phase}    Next: ${result.next.action}    Endpoint: ${result.endpoint}`);
    console.log(`Worktree: ${result.worktree}\nRun: ${result.run}`);
    if (result.next.reason) console.log(result.next.reason);
    if (result.verification) for (const c of result.verification.results) console.log(`Check ${c.name}: ${c.passed ? 'passed' : 'failed'}${c.timedOut ? ' (timeout)' : ''}    Log: ${c.log}`);
    if (result.delivery) console.log(`Commit: ${result.delivery.commit}${result.delivery.pr ? `\nDraft PR: ${result.delivery.pr}` : ''}`);
  } else console.log(JSON.stringify(result, null, 2));
  if (result?.phase === 'blocked' || result?.verification?.passed === false && action === 'verify') process.exitCode = 2;
} catch (e) {
  const output = { error: e.message, code: e.code || 'invalid' };
  if (json) console.error(JSON.stringify(output)); else console.error(`factory: ${e.message}`);
  process.exitCode = e.code === 'infrastructure' ? 3 : 2;
}
