import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const cli = join(root, 'cli/synframe.mjs');
const version = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).version;
const run = (args, env = process.env) => spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8', env });

test('help/version do not require Python; invalid arguments never install', () => {
  const env = { ...process.env, SYNFRAME_PYTHON: '/missing-python' };
  assert.equal(run(['--help'], env).status, 0);
  assert.equal(run(['--version'], env).stdout.trim(), version);
  assert.equal(run(['unknown'], env).status, 2);
  assert.equal(run(['install', '--destination'], env).status, 2);
  assert.equal(run(['install'], env).status, 1);
});

test('actual skill installation, backup and foreign directory protection', () => {
  const folder = mkdtempSync(join(tmpdir(), 'synframe-npm-'));
  try {
    const destination = join(folder, 'skills/synframe');
    const first = run(['install', '--destination', destination]);
    assert.equal(first.status, 0, first.stderr);
    const installed = JSON.parse(first.stdout);
    assert.ok(existsSync(join(destination, 'SKILL.md')));
    assert.ok(existsSync(join(destination, 'scripts/synframe_core/files.py')));
    const marker = join(destination, 'custom.txt'); writeFileSync(marker, 'preserve me');
    const second = run(['install', '--destination', destination]);
    assert.equal(second.status, 0, second.stderr);
    const updated = JSON.parse(second.stdout);
    assert.deepEqual(installed.sha256, updated.sha256);
    assert.equal(readFileSync(join(updated.backup, 'custom.txt'), 'utf8'), 'preserve me');
    writeFileSync(join(destination, 'SKILL.md'), 'another skill');
    assert.notEqual(run(['install', '--destination', destination]).status, 0);
    assert.equal(readFileSync(join(destination, 'SKILL.md'), 'utf8'), 'another skill');
  } finally { rmSync(folder, { recursive: true, force: true }); }
});
