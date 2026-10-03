import { describe } from './factory.mjs';

// Keep next-action decisions in the engine. This projection never saves a run
// or submits evidence; status/next remain available for the full payload.
export function summarize(run) {
  const status = describe(run);
  const next = Object.fromEntries(['action', 'reason', 'endpoint', 'owner', 'failures', 'limit', 'receipt']
    .filter(key => Object.hasOwn(status.next, key)).map(key => [key, status.next[key]]));
  const verification = run.verification;
  return {
    id: run.id, task: run.task, phase: run.phase, endpoint: run.endpoint,
    criteria: run.criteria,
    checks: run.config.checks.map(check => ({ ...check,
      result: verification?.results.find(result => result.name === check.name) ?? null })),
    verification: verification ? { passed: verification.passed, unchanged: verification.unchanged, at: verification.at } : null,
    findings: { plan: run.planReview?.findings ?? [], code: run.codeReview?.findings ?? [] },
    next, delivery: run.delivery ?? null,
  };
}

export function formatSummary(summary) {
  const lines = [`Task: ${summary.task}`, `State: ${summary.phase}    Endpoint: ${summary.endpoint}`, '', 'Criteria:'];
  for (const criterion of summary.criteria) lines.push(`  ${criterion.id}: ${criterion.text}`);
  lines.push('', 'Checks: last verification');
  for (const check of summary.checks) {
    const result = check.result;
    if (!result) { lines.push(`  ${check.name}: not run`); continue; }
    lines.push(`  ${check.name}: ${result.passed ? 'passed' : 'failed'}${result.timedOut ? ' (timeout)' : ''}`);
    if (!result.passed) lines.push(`    Exit: ${result.exitCode}    Signal: ${result.signal ?? 'none'}${result.error ? `    Error: ${result.error}` : ''}`);
    if (result.truncated) lines.push('    Log truncated');
    lines.push(`    Log: ${result.log}`);
  }
  if (summary.verification) {
    lines.push(`  Overall: ${summary.verification.passed ? 'passed' : 'failed'}${summary.verification.unchanged ? '' : ' (files changed during checks)'}`);
  }
  lines.push('', 'Findings:');
  let count = 0;
  for (const kind of ['plan', 'code']) for (const finding of summary.findings[kind]) {
    count++; lines.push(`  ${kind} ${finding.severity} ${finding.location}: ${finding.issue}`);
  }
  if (!count) lines.push('  none');
  lines.push('', `Next: ${summary.next.action}${summary.next.reason ? ` — ${summary.next.reason}` : ''}`);
  if (summary.next.owner) lines.push(`  Owner: ${summary.next.owner.pid} on ${summary.next.owner.host}`);
  if (summary.next.limit !== undefined) lines.push(`  Repair attempts: ${summary.next.failures}/${summary.next.limit}`);
  const delivery = summary.delivery;
  if (!delivery) lines.push('Delivery: pending');
  else {
    lines.push(`Delivery: ${delivery.endpoint}${summary.phase === 'done' ? ' (completed)' : ' (pending)'}`, `  Commit: ${delivery.commit}`);
    if (delivery.endpoint === 'draft-pr') lines.push(`  PR: ${delivery.pr ?? 'pending'}`);
  }
  return lines.join('\n');
}
