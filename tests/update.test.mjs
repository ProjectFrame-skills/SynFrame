import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { updateSkill } from '../cli/update.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const metadata = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
const name = metadata.name.replace('-cli', '');
const cli = join(root, `cli/${name}.mjs`);

test('update stops at each failed stage and runs the newly installed CLI with literal user paths', () => {
  const globalRoot = join(tmpdir(), 'npm global with spaces');
  const installArgs = ['--destination', join(tmpdir(), 'literal & $(value) path')];
  for (const failAt of [-1, 0, 1, 2]) {
    const calls = [];
    const status = updateSkill(metadata.name, name, installArgs, (command, args, options) => {
      const index = calls.length;
      calls.push({ command, args, options });
      if (index === failAt) return index === 0 ? { error: new Error('npm missing') } : { status: 7 };
      return { status: 0, stdout: globalRoot+'\n' };
    });
    assert.equal(status, failAt < 0 ? 0 : failAt === 0 ? 1 : 7);
    assert.equal(calls.length, failAt < 0 ? 3 : failAt+1);
    assert.deepEqual(calls[0].args, ['root', '--global']);
    assert.equal(calls[0].options.shell, process.platform === 'win32');
    if (calls.length > 1) assert.deepEqual(calls[1].args, ['install', '--global', metadata.name+'@latest']);
    if (calls.length > 2) {
      assert.equal(calls[2].command, process.execPath);
      assert.deepEqual(calls[2].args, [join(globalRoot, metadata.name, 'cli', name+'.mjs'), 'install', ...installArgs]);
      assert.equal(calls[2].options.shell, undefined);
    }
  }
  let calls = 0;
  assert.equal(updateSkill(metadata.name, name, [], () => { calls++; return { status: 0, stdout: 'relative/path' }; }), 1);
  assert.equal(calls, 1);
});

test('actual update installs the new bundled skill, keeps project state and installation-specific settings', { skip: process.platform === 'win32' }, () => {
  const folder = mkdtempSync(join(tmpdir(), name+' update '));
  try {
    const npmBin = join(folder, 'bin'); mkdirSync(npmBin);
    const globalRoot = join(folder, 'global packages');
    const candidate = join(folder, 'candidate');
    mkdirSync(candidate);
    for (const entry of ['cli','skills','tools','package.json']) cpSync(join(root,entry),join(candidate,entry),{recursive:true});
    const newSkill = readFileSync(join(candidate,'skills',name,'SKILL.md'),'utf8')+'\n<!-- updated package fixture -->\n';
    writeFileSync(join(candidate,'skills',name,'SKILL.md'),newSkill);
    const npmLog = join(folder, 'npm-calls.jsonl');
    writeFileSync(join(npmBin, 'npm'), `#!${process.execPath}\n`+`
import { appendFileSync, cpSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
const args=process.argv.slice(2);
appendFileSync(process.env.UPDATE_LOG,JSON.stringify(args)+'\\n');
if (args.join(' ')==='root --global') console.log(process.env.UPDATE_GLOBAL_ROOT);
else if (args.join(' ')==='install --global '+process.env.UPDATE_PACKAGE+'@latest') {
  mkdirSync(process.env.UPDATE_GLOBAL_ROOT,{recursive:true});
  cpSync(process.env.UPDATE_CANDIDATE,join(process.env.UPDATE_GLOBAL_ROOT,process.env.UPDATE_PACKAGE),{recursive:true});
} else process.exit(8);
`, { mode: 0o755 });
    const codexHome=join(folder,'codex home');
    const env={...process.env,CODEX_HOME:codexHome,PATH:npmBin+delimiter+process.env.PATH,
      UPDATE_LOG:npmLog,UPDATE_GLOBAL_ROOT:globalRoot,UPDATE_PACKAGE:metadata.name,UPDATE_CANDIDATE:candidate};
    const run = args => spawnSync(process.execPath,[cli,...args],{encoding:'utf8',cwd:folder,env});
    assert.equal(run(['update','--bad']).status,2);
    assert.ok(!existsSync(npmLog));
    const pythonFailure=spawnSync(process.execPath,[cli,'update'],{encoding:'utf8',env:{...env,[name.toUpperCase()+'_PYTHON']:join(folder,'missing Python')}});
    assert.equal(pythonFailure.status,1); assert.ok(!existsSync(npmLog));
    for (const explicit of [false,true]) {
      const destination=explicit?join(folder,'custom & literal skills',name):join(codexHome,'skills',name);
      const flags=explicit?['--destination',destination]:[];
      const hooks=join(folder,'custom hooks.json');
      if (name==='specframe' && explicit) flags.push('--hooks',hooks);
      const first=run(['install',...flags]); assert.equal(first.status,0,first.stderr);
      writeFileSync(join(destination,'custom.txt'),'preserve previous installation');
      const statePath=join(folder,name+'-state.json'); writeFileSync(statePath,'{"userDecisions":"keep"}\n');
      const stateBefore=readFileSync(statePath);
      const hookPath=name==='specframe'?(explicit?hooks:join(codexHome,'hooks.json')):null;
      const hooksBefore=hookPath?readFileSync(hookPath):null;
      const result=run(['update',...flags]); assert.equal(result.status,0,result.stderr);
      assert.equal(readFileSync(join(destination,'SKILL.md'),'utf8'),newSkill);
      assert.deepEqual(readFileSync(statePath),stateBefore);
      if (hookPath) assert.deepEqual(readFileSync(hookPath),hooksBefore);
      if (name==='specframe') assert.equal(readFileSync(join(destination,'custom.txt'),'utf8'),'preserve previous installation');
      else {
        const receipt=JSON.parse(result.stdout.slice(result.stdout.indexOf('{'),result.stdout.lastIndexOf('}')+1));
        assert.equal(readFileSync(join(receipt.backup,'custom.txt'),'utf8'),'preserve previous installation');
      }
    }
    assert.deepEqual(readFileSync(npmLog,'utf8').trim().split('\n').map(JSON.parse),[
      ['root','--global'],['install','--global',metadata.name+'@latest'],
      ['root','--global'],['install','--global',metadata.name+'@latest'],
    ]);
  } finally { rmSync(folder,{recursive:true,force:true}); }
});
