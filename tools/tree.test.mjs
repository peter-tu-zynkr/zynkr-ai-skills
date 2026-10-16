import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { git, scratch, writeFile } from './fixtures.mjs';
import { blobSha } from './publish.mjs';
import { treeId } from './tree.mjs';

describe('a folder’s git tree id', () => {
  test('equals the id git itself gives the folder: nested folders, exec bits, and names git sorts as folders', () => {
    const repo = scratch('tree-repo');
    git(repo, ['init', '-q']);
    const files = {
      'SKILL.md': ['---\nname: alpha\n---\n', false],
      'a.b': ['dot\n', false],
      'a/inner.md': ['in a folder named a\n', false],
      'a-b': ['dash\n', false],
      a0: ['zero\n', false],
      'scripts/run.sh': ['#!/bin/sh\necho hi\n', true],
      'agents/helper.md': ['---\nname: helper\n---\n', false],
      '.gitignore': ['*.log\n', false],
      'references/deep/notes.md': ['notes\n', false],
    };
    const entries = [];
    for (const [rel, [content, exec]] of Object.entries(files)) {
      writeFile(repo, `skills/1-x/alpha/${rel}`, content, exec);
      entries.push({ path: rel, mode: exec ? '100755' : '100644', sha: blobSha(Buffer.from(content)) });
    }
    git(repo, ['add', '-f', '-A']);
    git(repo, ['-c', 'user.name=T', '-c', 'user.email=t@example.test', 'commit', '-q', '-m', 'x']);
    const expected = git(repo, ['rev-parse', 'HEAD:skills/1-x/alpha']).trim();
    assert.equal(treeId(entries), expected);
    assert.equal(treeId([...entries].reverse()), expected, 'the order given does not matter');
  });

  test('one byte or one mode changes the id', () => {
    const base = [{ path: 'SKILL.md', mode: '100644', sha: blobSha(Buffer.from('a\n')) }];
    const id = treeId(base);
    assert.notEqual(treeId([{ ...base[0], sha: blobSha(Buffer.from('b\n')) }]), id);
    assert.notEqual(treeId([{ ...base[0], mode: '100755' }]), id);
  });

  test('refuses what is no plain folder of files', () => {
    const sha = blobSha(Buffer.from('x'));
    assert.throws(() => treeId([]));
    assert.throws(() => treeId([{ path: '../x', mode: '100644', sha }]));
    assert.throws(() => treeId([{ path: 'x', mode: '120000', sha }]));
    assert.throws(() => treeId([{ path: 'a', mode: '100644', sha }, { path: 'a/b', mode: '100644', sha }]));
    assert.throws(() => treeId([{ path: 'a', mode: '100644', sha }, { path: 'a', mode: '100644', sha }]));
  });

  test('matches the stage builder: a real folder written to disk, read back by blob sha', () => {
    const dir = scratch('tree-disk');
    writeFile(dir, 'SKILL.md', '---\nname: beta\n---\n');
    writeFile(dir, 'tools/x.sh', 'echo\n', true);
    const entries = ['SKILL.md', 'tools/x.sh'].map((rel) => ({
      path: rel,
      mode: fs.statSync(path.join(dir, rel)).mode & 0o100 ? '100755' : '100644',
      sha: blobSha(fs.readFileSync(path.join(dir, rel))),
    }));
    git(dir, ['init', '-q']);
    git(dir, ['add', '-A']);
    assert.equal(treeId(entries), git(dir, ['write-tree']).trim());
  });
});
