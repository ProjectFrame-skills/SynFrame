#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = new URL('../', import.meta.url);
const metadata = JSON.parse(readFileSync(new URL('package.json', root), 'utf8'));
const args = process.argv.slice(2);
const help = `SynFrame ${metadata.version}

Usage:
  synframe install [--destination /absolute/path/to/skills/synframe]
  synframe --version
  synframe --help

Installs the bundled Codex skill. Existing installations are backed up.
Requires Python 3.11+. Set SYNFRAME_PYTHON to choose an explicit interpreter.
Default: CODEX_HOME/skills/synframe, or ~/.codex/skills/synframe
`;

function main() {
  if (args.length === 0 || (args.length === 1 && ['--help', '-h'].includes(args[0]))) {
    console.log(help); return 0;
  }
  if (args.length === 1 && ['--version', '-v'].includes(args[0])) {
    console.log(metadata.version); return 0;
  }
  if (args[0] !== 'install' || ![1, 3].includes(args.length)
      || (args.length === 3 && (args[1] !== '--destination' || !args[2] || args[2].startsWith('-')))) {
    console.error(`Invalid arguments.\n${help}`); return 2;
  }
  const candidates = process.env.SYNFRAME_PYTHON
    ? [[process.env.SYNFRAME_PYTHON]]
    : [['python3'], ['python'], ...(process.platform === 'win32' ? [['py', '-3']] : [])];
  for (const [command, ...prefix] of candidates) {
    const probe = spawnSync(command, [...prefix, '-c',
      'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'], { windowsHide: true, stdio: 'ignore' });
    if (probe.error || probe.status !== 0) continue;
    const result = spawnSync(command, [...prefix, fileURLToPath(new URL('tools/install.py', root)),
      ...args.slice(1)], { windowsHide: true, stdio: 'inherit' });
    if (result.error) { console.error(result.error.message); return 1; }
    return result.status ?? 1;
  }
  console.error('Python 3.11+ was not found. Install it or set SYNFRAME_PYTHON to its executable path.');
  return 1;
}

process.exitCode = main();
