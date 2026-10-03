import { randomUUID, createHash } from 'node:crypto';
import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { hostname } from 'node:os';
import { join } from 'node:path';
import { FactoryError } from './git.mjs';

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])]));
  return value;
}
export const hash = value => createHash('sha256').update(typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(stable(value))).digest('hex');
export const readJSON = path => JSON.parse(readFileSync(path, 'utf8'));
export function atomicJSON(path, data) {
  const temp = `${path}.${randomUUID()}.tmp`;
  const fd = openSync(temp, 'wx', 0o600);
  try { writeFileSync(fd, `${JSON.stringify(data, null, 2)}\n`); fsyncSync(fd); } finally { closeSync(fd); }
  renameSync(temp, path);
}
export const runsRoot = common => join(common, 'factory', 'runs');
export function readRun(dir) {
  const run = readJSON(join(dir, 'state.json'));
  if (run.version !== 1 || run.dir !== dir) throw new FactoryError('Invalid run directory.');
  return run;
}
export function save(run, action, details = {}) {
  run.updatedAt = new Date().toISOString();
  run.history.push({ at: run.updatedAt, action, ...details });
  atomicJSON(join(run.dir, 'state.json'), run);
}
export function listRuns(common) {
  const root = runsRoot(common);
  if (!existsSync(root)) return [];
  return readdirSync(root).filter(x => /^[a-f0-9-]{36}$/.test(x)).map(x => readRun(join(root, x)));
}
export async function locked(dir, fn) {
  const lock = join(dir, 'lock');
  try { mkdirSync(lock, { mode: 0o700 }); } catch (e) {
    if (e.code === 'EEXIST') throw new FactoryError('An operation owns this run. Use status; recover only after its process exits.', 'locked');
    throw e;
  }
  const owner = { pid: process.pid, host: hostname(), at: new Date().toISOString() };
  atomicJSON(join(lock, 'owner.json'), owner);
  try { return await fn(); } finally { rmSync(lock, { recursive: true, force: true }); }
}
export function recoverLock(dir) {
  const lock = join(dir, 'lock');
  if (!existsSync(lock)) return { recovered: false };
  if (!existsSync(join(lock, 'owner.json'))) throw new FactoryError('Lock has no owner receipt. Inspect it manually; automatic takeover refused.');
  const owner = readJSON(join(lock, 'owner.json'));
  if (owner.host !== hostname()) throw new FactoryError('Lock belongs to another host.');
  try { process.kill(owner.pid, 0); throw new FactoryError('Lock owner is still alive.'); }
  catch (e) { if (e.code !== 'ESRCH') throw e; }
  rmSync(lock, { recursive: true });
  return { recovered: true, owner };
}
