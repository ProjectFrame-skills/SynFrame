import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, symlinkSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { findPython } from '../cli/python.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const metadata = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
const name = metadata.name.replace('-cli', '');
const variable = `${name.toUpperCase()}_PYTHON`;
const missing = { error: { code: 'ENOENT' }, status: null };
const ok = (stdout = '[3,13,2]\n') => ({ status: 0, stdout, stderr: '' });
const fixture = (responses = {}, extra = {}) => ({
  env: {}, platform: 'darwin', exists: () => false, list: () => [],
  spawn: (command, args, options) => {
    assert.equal(options.shell, undefined);
    assert.equal(options.timeout, 5000);
    return responses[command] ?? missing;
  }, ...extra,
});

test('PATH selection is lazy; explicit executable remains authoritative and supports spaces', () => {
  const calls = [];
  const io = fixture({}, { spawn: (command) => { calls.push(command); return ok(); } });
  assert.deepEqual(findPython(variable, io), { command: 'python3', prefix: [] });
  assert.deepEqual(calls, ['python3']);
  const explicit = '/custom Python/bin/python';
  assert.deepEqual(findPython(variable, fixture({ [explicit]: ok() }, { env: { [variable]: explicit } })),
    { command: explicit, prefix: [] });
  assert.throws(() => findPython(variable, fixture({ python3: ok() }, { env: { [variable]: explicit } })),
    error => error.message.includes('executable not found') && error.message.includes('fix or unset'));
});

test('Homebrew fallback handles Apple Silicon, Intel, Linux, custom prefixes and keg-only versions', () => {
  for (const [platform, prefix] of [['darwin', '/opt/homebrew'], ['darwin', '/usr/local'], ['linux', '/home/linuxbrew/.linuxbrew']]) {
    const command = join(prefix, 'bin/python3');
    assert.equal(findPython(variable, fixture({ python3: ok('[3,9,6]'), [command]: ok() }, { platform })).command, command);
    const brew = join(prefix, 'bin/brew');
    const custom = '/custom Homebrew';
    const keg = join(custom, 'opt/python@3.13/libexec/bin/python3');
    assert.equal(findPython(variable, fixture({ [brew]: ok(`${custom}\n`), [keg]: ok() }, {
      platform, exists: path => path === brew,
      list: path => path === join(custom, 'opt') ? ['python@3.9', 'other', 'python@3.13'] : [],
    })).command, keg);
  }
  const keg = '/custom Brew/opt/python@3.12/bin/python3.12';
  assert.equal(findPython(variable, fixture({ brew: ok('/custom Brew\n'), [keg]: ok() }, {
    list: path => path === '/custom Brew/opt' ? ['python@3.12'] : [],
  })).command, keg);
  assert.equal(findPython(variable, fixture({ brew: ok('/active Brew\n'),
    '/active Brew/bin/python3': ok(), '/opt/homebrew/bin/python3': ok(),
  })).command, '/active Brew/bin/python3');
});

test('Windows launcher and Python 3.11 boundary remain supported', () => {
  assert.deepEqual(findPython(variable, fixture({ py: ok('[3,11,0]') }, { platform: 'win32' })),
    { command: 'py', prefix: ['-3'] });
  assert.throws(() => findPython(variable, fixture({ python3: ok('[3,10,14]') }, { platform: 'win32' })), /too old/);
});

test('diagnostics distinguish absence, version, permissions, startup failure, timeout and invalid response', () => {
  const env = { [variable]: '/chosen/python' };
  for (const [result, expected] of [
    [missing, /executable not found \(ENOENT\)/],
    [ok('[3,9,6]'), /Python 3\.9\.6 is too old/],
    [{ error: { code: 'EACCES' } }, /permission denied \(EACCES\)/],
    [{ status: 7, stderr: 'missing shared library' }, /exit 7.*missing shared library/],
    [{ status: null, signal: 'SIGTERM' }, /signal SIGTERM/],
    [{ error: { code: 'ETIMEDOUT' } }, /timed out.*ETIMEDOUT/],
    [{ error: { code: 'ENOEXEC' } }, /could not execute \(ENOEXEC\)/],
    [ok('not JSON'), /invalid version response/],
    [ok('["3",13,2]'), /invalid version response/],
  ]) assert.throws(() => findPython(variable, fixture({ '/chosen/python': result }, { env })), expected);
  assert.throws(() => findPython(variable, fixture({}, { env, exists: () => true })), /could not execute \(ENOENT\)/);
  assert.throws(() => findPython(variable, fixture()), /python3: executable not found.*\n- python: executable not found/);
  assert.throws(() => findPython(variable, fixture({ brew: { status: 1 } })), /Homebrew lookup.*exit 1/);
  assert.throws(() => findPython(variable, fixture({ brew: ok('relative/prefix') })), /invalid prefix response/);
});

test('actual CLI reports Python failures separately and never installs after a failed explicit check', { skip: process.platform === 'win32' }, () => {
  const folder = mkdtempSync(join(tmpdir(), `${name} Python errors `));
  try {
    const denied = join(folder, 'permission denied');
    const old = join(folder, 'old Python');
    const broken = join(folder, 'broken Python');
    writeFileSync(denied, '#!/bin/sh\nexit 0\n', { mode: 0o644 });
    writeFileSync(old, "#!/bin/sh\nprintf '[3,10,9]\\n'\n", { mode: 0o755 });
    writeFileSync(broken, "#!/bin/sh\nprintf 'cannot load Python library\\n' >&2\nexit 7\n", { mode: 0o755 });
    const codexHome = join(folder, 'must not install');
    for (const [command, reason] of [[join(folder, 'missing'), /executable not found/],
      [denied, /permission denied/], [old, /Python 3\.10\.9 is too old/], [broken, /exit 7.*cannot load Python library/]]) {
      const result = spawnSync(process.execPath, [join(root, `cli/${name}.mjs`), 'install'], {
        encoding: 'utf8', env: { ...process.env, [variable]: command, CODEX_HOME: codexHome },
      });
      assert.equal(result.status, 1); assert.match(result.stderr, reason);
      assert.ok(!existsSync(codexHome));
    }
  } finally { rmSync(folder, { recursive: true, force: true }); }
});

test('actual CLI installs through a custom Homebrew prefix when PATH Python is too old', { skip: process.platform === 'win32' }, () => {
  const folder = mkdtempSync(join(tmpdir(), `${name} brew test `));
  try {
    const python = spawnSync('python3', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' });
    assert.equal(python.status, 0, python.stderr);
    const pathBin = join(folder, 'path bin');
    const prefix = join(folder, 'custom Homebrew');
    const kegBin = join(prefix, 'opt/python@3.13/libexec/bin');
    mkdirSync(pathBin, { recursive: true }); mkdirSync(kegBin, { recursive: true });
    const quote = s => `'${s.replaceAll("'", "'\\''")}'`;
    writeFileSync(join(pathBin, 'python3'), "#!/bin/sh\nprintf '[3,9,6]\\n'\n", { mode: 0o755 });
    writeFileSync(join(pathBin, 'brew'), `#!/bin/sh\nprintf '%s\\n' ${quote(prefix)}\n`, { mode: 0o755 });
    symlinkSync(python.stdout.trim(), join(kegBin, 'python3'));
    const env = { ...process.env, PATH: pathBin, CODEX_HOME: join(folder, 'codex home') };
    delete env[variable];
    const result = spawnSync(process.execPath, [join(root, `cli/${name}.mjs`), 'install'], { env, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const installed = join(env.CODEX_HOME, 'skills', name);
    assert.ok(existsSync(join(installed, 'SKILL.md')));
    assert.deepEqual(readFileSync(join(installed, 'SKILL.md')), readFileSync(join(root, 'skills', name, 'SKILL.md')));
    if (name === 'specframe') {
      const hooks = JSON.parse(readFileSync(join(env.CODEX_HOME, 'hooks.json'), 'utf8'));
      assert.ok(hooks.hooks.SessionStart[0].hooks[0].command.includes(join(installed, 'scripts/state.py')));
    }
  } finally { rmSync(folder, { recursive: true, force: true }); }
});
