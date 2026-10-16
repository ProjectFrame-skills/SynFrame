import { existsSync, readdirSync } from 'node:fs';
import { isAbsolute, join } from 'node:path';
import { spawnSync } from 'node:child_process';

// Shared installer lookup; never changes PATH, installs Python, or invokes a shell.
export function findPython(variable, {
  env = process.env, platform = process.platform, spawn = spawnSync,
  exists = existsSync, list = readdirSync,
} = {}) {
  const options = { env, encoding: 'utf8', windowsHide: true, timeout: 5000,
    killSignal: 'SIGKILL', maxBuffer: 64 * 1024 };
  const failures = [];
  const checked = new Set();
  const brewNotes = [];
  function* candidates() {
    if (env[variable]) { yield [env[variable]]; return; }
    yield ['python3']; yield ['python'];
    if (platform === 'win32') { yield ['py', '-3']; return; }
    if (!['darwin', 'linux'].includes(platform)) return;

    const defaults = platform === 'darwin'
      ? ['/opt/homebrew', '/usr/local'] : ['/home/linuxbrew/.linuxbrew'];
    const prefixes = new Set();
    const brews = ['brew', ...defaults.map(p => join(p, 'bin', 'brew')).filter(exists)];
    for (const brew of new Set(brews)) {
      const result = spawn(brew, ['--prefix'], options);
      const prefix = result.stdout?.trim();
      if (!result.error && result.status === 0 && prefix && isAbsolute(prefix) && !prefix.includes('\n')) {
        prefixes.add(prefix);
      } else if (result.error?.code !== 'ENOENT') {
        brewNotes.push(`Homebrew lookup (${brew}) failed: ${result.error?.code
          ?? (result.status === 0 ? 'invalid prefix response' : `exit ${result.status}`)}.`);
      }
    }
    for (const prefix of defaults) prefixes.add(prefix);
    for (const prefix of prefixes) {
      yield [join(prefix, 'bin', 'python3')];
      yield [join(prefix, 'opt', 'python', 'libexec', 'bin', 'python3')];
      let formulae;
      try { formulae = list(join(prefix, 'opt')).filter(name => /^python@\d+\.\d+$/.test(name)); }
      catch (error) {
        if (error.code !== 'ENOENT') brewNotes.push(`Cannot inspect ${join(prefix, 'opt')}: ${error.code}.`);
        continue;
      }
      formulae.sort((a, b) => b.localeCompare(a, 'en', { numeric: true }));
      for (const formula of formulae) {
        const bin = join(prefix, 'opt', formula);
        yield [join(bin, 'libexec', 'bin', 'python3')];
        yield [join(bin, 'bin', `python${formula.slice(7)}`)];
      }
    }
  }
  for (const candidate of candidates()) {
    const label = candidate.join(' ');
    if (checked.has(label)) continue;
    checked.add(label);
    const [command, ...prefix] = candidate;
    const result = spawn(command, [...prefix, '-c',
      'import json, sys; print(json.dumps(list(sys.version_info[:3])))'], options);
    let reason;
    if (result.error) {
      const code = result.error.code;
      reason = code === 'ENOENT' && !exists(command) ? 'executable not found (ENOENT)'
        : code === 'EACCES' ? 'permission denied (EACCES)'
        : code === 'ETIMEDOUT' ? 'Python check timed out after 5 seconds (ETIMEDOUT)'
        : `could not execute (${code ?? result.error.message})`;
    } else if (result.status !== 0) {
      const detail = (result.stderr ?? '').trim().slice(0, 300);
      reason = `Python check failed (${result.signal ? `signal ${result.signal}` : `exit ${result.status}`})${detail ? `: ${detail}` : ''}`;
    } else {
      let version;
      try { version = JSON.parse(result.stdout); } catch { /* Not a valid Python probe response. */ }
      if (!Array.isArray(version) || version.length !== 3 || !version.every(n => Number.isInteger(n) && n >= 0)) {
        reason = 'Python check returned an invalid version response';
      } else if (version[0] > 3 || (version[0] === 3 && version[1] >= 11)) {
        return { command, prefix };
      } else {
        reason = `Python ${version.join('.')} is too old; Python 3.11+ is required`;
      }
    }
    // Omit nonexistent optional Homebrew paths; retain failed existing executables.
    if (env[variable] || !isAbsolute(command) || exists(command)) failures.push(`${label}: ${reason}`);
  }
  const message = [
    'No usable Python 3.11+ was found.', ...failures.map(s => `- ${s}`), ...brewNotes,
    env[variable] ? `${variable} is set; fix or unset it to enable automatic discovery.`
      : 'Checked PATH and, on macOS/Linux, Homebrew prefixes and installed versioned Python formulae.',
    `Install Python 3.11+ or set ${variable} to the full path of an existing Python executable.`,
  ].join('\n');
  throw new Error(message);
}
