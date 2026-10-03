import { readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
for (const folder of ['bin', 'lib', 'scripts', 'test']) {
  for (const file of readdirSync(folder).filter(f => f.endsWith('.mjs'))) {
    execFileSync(process.execPath, ['--check', `${folder}/${file}`], { stdio: 'inherit' });
  }
}
console.log('All JavaScript source parses.');
