import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { TOKEN, buildStage, scratch, skill, storedZip, tarball } from './fixtures.mjs';
import { Refusal } from './common.mjs';
import { fetchStage, main } from './fetch-stage.mjs';

const API = 'https://api.github.com/repos/peter-tu-zynkr/zynkr-skill-builder';
const BLOB = 'https://blob.example.test/artifact.zip?sig=abc';
const RUN = {
  id: 42,
  head_sha: '1'.repeat(40),
  head_branch: 'main',
  event: 'push',
  head_repository: { full_name: 'peter-tu-zynkr/zynkr-skill-builder' },
  created_at: '2026-09-28T10:06:00Z',
  name: 'export stage',
};
const COMPARE = `${API}/compare/${RUN.head_sha}...heads/main?per_page=1`;

const json = (value, status = 200) => new Response(JSON.stringify(value), { status });

/** The artifact API as GitHub answers it; `over` replaces one answer by path suffix. */
function github(zip, over = {}) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const u = String(url);
    for (const [suffix, respond] of Object.entries(over)) if (u.includes(suffix)) return respond();
    if (u.startsWith(`${API}/actions/workflows/export-stage.yml/runs?`)) return json({ total_count: 1, workflow_runs: [RUN] });
    if (u === COMPARE) return json({ status: 'ahead' });
    if (u.startsWith(`${API}/actions/runs/42/artifacts`)) return json({ artifacts: [{ id: 7, name: 'stage', expired: false }] });
    if (u === `${API}/actions/artifacts/7/zip`) return new Response(null, { status: 302, headers: { location: BLOB } });
    if (u === BLOB) return new Response(zip, { status: 200 });
    throw new Error(`unexpected fetch ${u}`);
  };
  return { fetchImpl, calls };
}

const stageZip = () => {
  const stage = buildStage([skill('alpha', { files: { 'scripts/run.sh': { content: '#!/bin/sh\n', exec: true } } })]);
  return { stage, zip: storedZip([{ name: 'stage.tgz', data: tarball(stage.root, ['stage']) }]) };
};

async function refused(promise, pattern) {
  await assert.rejects(promise, (err) => {
    assert.ok(err instanceof Refusal, `expected a Refusal, got ${err}`);
    assert.match(err.message, pattern);
    return true;
  });
}

describe('fetch-stage', () => {
  test('downloads the newest stage and never sends the token to the blob host', async () => {
    const { stage, zip } = stageZip();
    const net = github(zip);
    const out = path.join(scratch('in'), 'in');
    const lines = [];
    const run = await fetchStage({ out, token: TOKEN, fetchImpl: net.fetchImpl, log: (l) => lines.push(l) });

    const record = { id: 42, head_sha: RUN.head_sha, event: 'push', head_branch: 'main', created_at: RUN.created_at };
    assert.deepEqual(run, record);
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(out, 'run.json'), 'utf8')), record, 'run.json beside stage/, for publish --run');
    assert.deepEqual(lines, [`stage from run 42 · head_sha ${RUN.head_sha} · created_at ${RUN.created_at}`]);
    assert.match(net.calls[0].url, /runs\?branch=main&status=success&per_page=1$/);
    assert.equal(net.calls[1].url, COMPARE, "the run's commit is checked against main before anything is downloaded");
    for (const c of net.calls.slice(0, 4)) assert.equal(c.init.headers.Authorization, `Bearer ${TOKEN}`);
    assert.equal(net.calls[3].init.redirect, 'manual');
    const blob = net.calls[4];
    assert.equal(blob.url, BLOB);
    assert.equal(blob.init.headers, undefined, 'no header, so no token, reaches the blob host');

    const got = fs.readFileSync(path.join(out, 'stage/manifest.json'), 'utf8');
    assert.equal(got, fs.readFileSync(path.join(stage.stageRoot, 'manifest.json'), 'utf8'));
    assert.equal(fs.statSync(path.join(out, 'stage/skills/1-brand-marketing/alpha/scripts/run.sh')).mode & 0o111, 0o111);
  });

  for (const [status, pattern] of [
    [401, /401: the secret WORKBENCH_READ_TOKEN was refused/],
    [403, /403: the secret WORKBENCH_READ_TOKEN lacks read access/],
    [404, /404: not found: the secret WORKBENCH_READ_TOKEN cannot see/],
  ]) {
    test(`a ${status} names the secret, never its value`, async () => {
      const net = github(Buffer.alloc(0), { '/runs?': () => json({ message: 'no' }, status) });
      const err = [];
      const code = await main(['--out', path.join(scratch('in'), 'in')], {
        env: { GH_TOKEN: TOKEN },
        fetchImpl: net.fetchImpl,
        error: (l) => err.push(l),
      });
      assert.equal(code, 1);
      assert.match(err.join('\n'), pattern);
      assert.ok(!err.join('\n').includes(TOKEN));
    });
  }

  test('an empty token refuses before any request', async () => {
    const net = github(Buffer.alloc(0));
    await refused(fetchStage({ out: scratch('in'), token: '', fetchImpl: net.fetchImpl }), /set the secret WORKBENCH_READ_TOKEN/);
    assert.equal(net.calls.length, 0);
  });

  test('no successful run, no stage artifact, or an expired one refuses', async () => {
    const out = () => path.join(scratch('in'), 'in');
    const none = github(Buffer.alloc(0), { '/runs?': () => json({ total_count: 0, workflow_runs: [] }) });
    await refused(fetchStage({ out: out(), token: TOKEN, fetchImpl: none.fetchImpl }), /no successful run/);

    const other = github(Buffer.alloc(0), { '/artifacts?': () => json({ artifacts: [{ id: 8, name: 'stage-old', expired: false }] }) });
    await refused(fetchStage({ out: out(), token: TOKEN, fetchImpl: other.fetchImpl }), /run 42 has no artifact named stage/);

    const expired = github(Buffer.alloc(0), { '/artifacts?': () => json({ artifacts: [{ id: 7, name: 'stage', expired: true }] }) });
    await refused(fetchStage({ out: out(), token: TOKEN, fetchImpl: expired.fetchImpl }), /has expired/);
  });

  test("a run whose commit is not on main refuses, and nothing is downloaded", async () => {
    for (const status of ['diverged', 'behind']) {
      const net = github(Buffer.alloc(0), { '/compare/': () => json({ status }) });
      const out = path.join(scratch('in'), 'in');
      await refused(fetchStage({ out, token: TOKEN, fetchImpl: net.fetchImpl }), /run 42's commit 1111111 is not on the workbench's main; nothing downloaded/);
      assert.equal(net.calls.some((c) => c.url.includes('/artifacts')), false);
      assert.equal(fs.existsSync(out), false);
    }
    const gone = github(Buffer.alloc(0), { '/compare/': () => json({ message: 'Not Found' }, 404) });
    await refused(fetchStage({ out: path.join(scratch('in'), 'in'), token: TOKEN, fetchImpl: gone.fetchImpl }), /checking run 42's commit against main answered 404/);
  });

  for (const [label, over, pattern] of [
    ['another branch', { head_branch: 'feature-quiet-thing' }, /run 42 did not run on the workbench's main$/],
    ['a fork', { head_repository: { full_name: 'someone/zynkr-skill-builder' } }, /run 42 ran code from another repository than/],
    ['a pull request', { event: 'pull_request' }, /run 42 was not started by push, schedule or workflow_dispatch/],
    ['no head sha', { head_sha: 'main' }, /run 42 has no 40-hex head_sha/],
  ]) {
    test(`a run from ${label} refuses before the compare, naming no branch or repository`, async () => {
      const net = github(Buffer.alloc(0), { '/runs?': () => json({ total_count: 1, workflow_runs: [{ ...RUN, ...over }] }) });
      const err = [];
      const code = await main(['--out', path.join(scratch('in'), 'in')], { env: { GH_TOKEN: TOKEN }, fetchImpl: net.fetchImpl, error: (l) => err.push(l) });
      assert.equal(code, 1);
      assert.match(err.join('\n'), pattern);
      assert.ok(!/feature-quiet-thing|someone\//.test(err.join('\n')));
      assert.equal(net.calls.length, 1, 'only the run listing');
    });
  }

  test('a zip without stage.tgz refuses', async () => {
    const net = github(storedZip([{ name: 'other.txt', data: Buffer.from('x') }]));
    await refused(fetchStage({ out: path.join(scratch('in'), 'in'), token: TOKEN, fetchImpl: net.fetchImpl }), /holds no stage\.tgz/);
  });

  test('a tarball reaching outside stage/, or holding a link, is not extracted', async () => {
    const { stage } = stageZip();
    fs.writeFileSync(path.join(stage.root, 'loose.txt'), 'x');
    const outside = github(storedZip([{ name: 'stage.tgz', data: tarball(stage.root, ['stage', 'loose.txt']) }]));
    const out1 = path.join(scratch('in'), 'in');
    await refused(fetchStage({ out: out1, token: TOKEN, fetchImpl: outside.fetchImpl }), /1 entry outside stage\/; nothing extracted/);
    assert.equal(fs.existsSync(out1), false);

    fs.symlinkSync('/etc', path.join(stage.stageRoot, 'skills/escape'));
    const linked = github(storedZip([{ name: 'stage.tgz', data: tarball(stage.root, ['stage']) }]));
    const out2 = path.join(scratch('in'), 'in');
    await refused(fetchStage({ out: out2, token: TOKEN, fetchImpl: linked.fetchImpl }), /1 link or special entry; nothing extracted/);
    assert.equal(fs.existsSync(out2), false);
  });
});
