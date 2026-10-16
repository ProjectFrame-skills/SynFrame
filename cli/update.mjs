import { spawnSync } from 'node:child_process';
import { isAbsolute, join } from 'node:path';

// Only fixed npm arguments use the Windows command shell; user paths go to Node directly.
export function updateSkill(packageName, commandName, installerArgs, run = spawnSync) {
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const npmOptions = { windowsHide: true, shell: process.platform === 'win32' };
  const globalRoot = run(npm, ['root', '--global'], { ...npmOptions, encoding: 'utf8' });
  if (globalRoot.error || globalRoot.status !== 0 || !isAbsolute(globalRoot.stdout?.trim() ?? '')) {
    console.error(`Could not locate global npm packages: ${globalRoot.error?.message || globalRoot.stderr?.trim() || 'npm root --global failed'}`);
    return 1;
  }
  console.log(`Updating ${packageName} and its skill to the latest published version...`);
  const update = run(npm, ['install', '--global', `${packageName}@latest`], { ...npmOptions, stdio: 'inherit' });
  if (update.error || update.status !== 0) {
    console.error(`npm update failed${update.error ? `: ${update.error.message}` : ''}. Skill installation was not started. Fix the npm error and retry ${commandName} update.`);
    return update.status || 1;
  }
  const latestCli = join(globalRoot.stdout.trim(), packageName, 'cli', `${commandName}.mjs`);
  const install = run(process.execPath, [latestCli, 'install', ...installerArgs], { windowsHide: true, stdio: 'inherit' });
  if (install.error || install.status !== 0) {
    console.error(`The npm CLI was updated, but skill installation failed${install.error ? `: ${install.error.message}` : ''}. Fix the installer error, then run ${commandName} install with the same path options.`);
    return install.status || 1;
  }
  console.log(`Update complete. Use $${commandName} in a new conversation.`);
  return 0;
}
