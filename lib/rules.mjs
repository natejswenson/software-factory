import { lstatSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { FactoryError, git } from './git.mjs';
import { hash } from './store.mjs';
import { validateConfig } from './checks.mjs';

const maxFile = 128 * 1024, maxTotal = 1024 * 1024, maxFiles = 128;
const decoder = new TextDecoder('utf-8', { fatal: true });
const selected = path => /^\.rules\/[^/]+\.md$/.test(path);
function stat(path) {
  try { return lstatSync(path); } catch (e) { if (e.code === 'ENOENT') return null; throw e; }
}
function regular(path) {
  const info = stat(path);
  if (info && !info.isFile()) throw new FactoryError(`${path}: expected a regular file, not a symlink or directory.`);
  if (info?.size > maxFile) throw new FactoryError(`${path}: exceeds 128 KiB.`);
  return info;
}
function decode(bytes, path) {
  if (bytes.length > maxFile) throw new FactoryError(`${path}: exceeds 128 KiB.`);
  try { return decoder.decode(bytes); } catch { throw new FactoryError(`${path}: expected valid UTF-8.`); }
}
function bundle(entries) {
  if (entries.length > maxFiles || entries.reduce((n, f) => n + f.bytes.length, 0) > maxTotal) {
    throw new FactoryError('Rules exceed 128 files or 1 MiB total.');
  }
  const files = entries.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
    .map(({ path, bytes }) => ({ path, content: decode(bytes, path), hash: hash(bytes) }));
  return { files, hash: hash(files) };
}
export function readRules(root) {
  const dir = join(root, '.rules'), info = stat(dir);
  if (!info) return bundle([]);
  if (!info.isDirectory()) throw new FactoryError('.rules must be a directory, not a symlink.');
  const names = readdirSync(dir).filter(name => name.endsWith('.md')).sort();
  if (names.length > maxFiles) throw new FactoryError('Rules exceed 128 files.');
  const entries = []; let total = 0;
  for (const name of names) {
    const path = `.rules/${name}`, full = join(root, path);
    total += regular(full).size;
    if (total > maxTotal) throw new FactoryError('Rules exceed 1 MiB total.');
    entries.push({ path, bytes: readFileSync(full) });
  }
  return bundle(entries);
}

// Native JSON validation first; then walk its tokens to reject duplicate keys
// (including escaped-equivalent names) rather than silently choosing a value.
function json(raw, path) {
  let value;
  try { value = JSON.parse(raw); } catch (e) { throw new FactoryError(`${path}: invalid factory configuration JSON: ${e.message}`); }
  const tokens = raw.match(/"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}\[\]:,]/g);
  let i = 0;
  function walk(depth = 0) {
    if (depth > 64) throw new FactoryError(`${path}: configuration nesting exceeds 64 levels.`);
    const token = tokens[i++];
    if (token === '{') {
      const keys = new Set();
      while (tokens[i] !== '}') {
        const key = JSON.parse(tokens[i++]);
        if (keys.has(key)) throw new FactoryError(`${path}: duplicate JSON key ${key}.`);
        keys.add(key); i++; walk(depth + 1);
        if (tokens[i] !== ',') break;
        i++;
      }
      i++;
    } else if (token === '[') {
      while (tokens[i] !== ']') { walk(depth + 1); if (tokens[i] !== ',') break; i++; }
      i++;
    }
  }
  walk(); return value;
}
export function settings(rules) {
  const result = {}, owners = new Map();
  for (const file of rules.files) {
    let fence = null, lines = [];
    for (const line of file.content.split(/\r?\n/)) {
      if (fence) {
        const close = line.match(/^ {0,3}(`{3,}|~{3,})\s*$/);
        if (close && close[1][0] === fence.char && close[1].length >= fence.length) {
          if (fence.config) {
            const block = json(lines.join('\n'), file.path);
            if (!block || typeof block !== 'object' || Array.isArray(block)) throw new FactoryError(`${file.path}: factory-config must be a JSON object.`);
            for (const key of Object.keys(block)) {
              if (!['version', 'endpoint', 'checks'].includes(key)) throw new FactoryError(`${file.path}: unknown factory setting ${key}.`);
              if (owners.has(key)) throw new FactoryError(`${file.path}: duplicate factory setting ${key}, already set in ${owners.get(key)}.`);
              owners.set(key, file.path); result[key] = block[key];
            }
          }
          fence = null; lines = [];
        } else if (fence.config) lines.push(line);
      } else {
        const open = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
        if (open && !(open[1][0] === '`' && open[2].includes('`'))) {
          fence = { char: open[1][0], length: open[1].length, config: open[2].trim() === 'factory-config' };
        }
      }
    }
    if (fence?.config) throw new FactoryError(`${file.path}: unterminated factory-config fence.`);
  }
  return result;
}
export function configuration(rules, legacy = null) {
  return validateConfig({ version: 1, endpoint: 'draft-pr', ...(legacy ?? {}), ...settings(rules) });
}
export function readProject(root) {
  const path = join(root, '.factory.json');
  const legacyRaw = regular(path) ? decode(readFileSync(path), '.factory.json') : null;
  const legacy = legacyRaw === null ? null : json(legacyRaw, '.factory.json');
  if (legacyRaw !== null && (!legacy || typeof legacy !== 'object' || Array.isArray(legacy))) throw new FactoryError('.factory.json must be a JSON object.');
  if (legacy !== null) validateConfig(legacy);
  const rules = readRules(root);
  return { rules, legacy, legacyRaw, config: configuration(rules, legacy) };
}
export function assertCommitted(root, base, project) {
  const parse = tree => tree.split('\0').filter(Boolean).map(line => {
    const tab = line.indexOf('\t'), header = line.slice(0, tab), path = line.slice(tab + 1);
    const [mode, , oid] = header.split(' ');
    return { mode, oid, path };
  });
  const roots = parse(git(root, ['ls-tree', '-z', base, '--', '.rules', '.factory.json']));
  const entries = [];
  for (const entry of roots) {
    if (entry.path === '.rules') {
      if (entry.mode !== '040000') throw new FactoryError('.rules on the selected base must be a directory, not a symlink.');
      entries.push(...parse(git(root, ['ls-tree', '-z', entry.oid])).map(f => ({ ...f, path: `.rules/${f.path}` })).filter(f => selected(f.path)));
    } else entries.push(entry);
  }
  if (entries.filter(f => selected(f.path)).length > maxFiles) throw new FactoryError('Committed rules exceed 128 files.');
  const rules = []; let legacyRaw = null, total = 0;
  for (const entry of entries) {
    if (!['100644', '100755'].includes(entry.mode)) throw new FactoryError(`${entry.path}: committed configuration must be a regular file.`);
    const size = Number(git(root, ['cat-file', '-s', entry.oid]).trim());
    if (size > maxFile) throw new FactoryError(`${entry.path}: exceeds 128 KiB.`);
    if (selected(entry.path)) total += size;
    if (total > maxTotal) throw new FactoryError('Committed rules exceed 1 MiB total.');
    const bytes = git(root, ['cat-file', 'blob', entry.oid], { encoding: 'buffer' });
    if (entry.path === '.factory.json') legacyRaw = decode(bytes, entry.path);
    else rules.push({ path: entry.path, bytes });
  }
  if (legacyRaw !== project.legacyRaw || bundle(rules).hash !== project.rules.hash) {
    throw new FactoryError('Configuration and .rules/*.md must be committed on the selected base. Review and commit them first.');
  }
}
