import { spawn } from 'node:child_process';
import { closeSync, openSync, writeSync } from 'node:fs';
import { join } from 'node:path';
import { FactoryError } from './git.mjs';

export function validateConfig(config) {
  if (config?.version !== 1) throw new FactoryError('Expected .factory.json version 1.');
  if (!['local', 'draft-pr'].includes(config.endpoint)) throw new FactoryError('Endpoint must be local or draft-pr.');
  if (!Array.isArray(config.checks) || !config.checks.length) throw new FactoryError('Configure at least one executable check.');
  const names = new Set();
  for (const c of config.checks) {
    if (!c || typeof c.name !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(c.name) || names.has(c.name)) throw new FactoryError('Checks need distinct simple names.');
    names.add(c.name);
    if (!Array.isArray(c.argv) || !c.argv.length || c.argv.some(x => typeof x !== 'string' || x.includes('\0')) || !c.argv[0].trim()) throw new FactoryError('Each check needs a nonempty argv array.');
    if (!Number.isInteger(c.timeoutMs) || c.timeoutMs < 100 || c.timeoutMs > 600000) throw new FactoryError('Check timeoutMs must be 100–600000.');
  }
  return config;
}
export function executeCheck(check, cwd, dir, attempt) {
  if (!['darwin', 'linux'].includes(process.platform)) throw new FactoryError('Verification requires macOS/Linux process groups.');
  return new Promise(resolve => {
    const log = join(dir, `check-${attempt}-${check.name}.log`);
    const fd = openSync(log, 'wx', 0o600);
    let bytes = 0, truncated = false, timedOut = false, error, killer;
    const started = Date.now();
    const child = spawn(check.argv[0], check.argv.slice(1), {
      cwd, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, CI: 'true' },
    });
    const append = chunk => {
      const size = Math.min(chunk.length, Math.max(0, 1024 * 1024 - bytes));
      if (size) writeSync(fd, chunk.subarray(0, size));
      bytes += size;
      if (size < chunk.length) truncated = true;
    };
    child.stdout.on('data', append); child.stderr.on('data', append);
    child.on('error', e => { error = e.message; });
    const killGroup = signal => { if (child.pid) { try { process.kill(-child.pid, signal); } catch (e) { if (e.code !== 'ESRCH') error = e.message; } } };
    const timer = setTimeout(() => {
      timedOut = true; killGroup('SIGTERM');
      killer = setTimeout(() => killGroup('SIGKILL'), 300);
    }, check.timeoutMs);
    const interrupted = () => { error = 'Verification interrupted'; killGroup('SIGKILL'); };
    process.on('SIGINT', interrupted); process.on('SIGTERM', interrupted);
    child.on('close', async (code, signal) => {
      clearTimeout(timer);
      // Even when the parent exits early, ensure timed-out descendants are killed.
      if (timedOut) { await new Promise(r => setTimeout(r, 350)); killGroup('SIGKILL'); }
      // Checks may not leave background writers behind after a successful parent exit.
      killGroup('SIGKILL');
      process.off('SIGINT', interrupted); process.off('SIGTERM', interrupted);
      clearTimeout(killer); closeSync(fd);
      resolve({ name: check.name, argv: check.argv, exitCode: code, signal, timedOut,
        error, truncated, durationMs: Date.now() - started, log,
        passed: code === 0 && !timedOut && !error });
    });
  });
}
