/**
 * fixtures.mjs — tiny stages, shelves and stubbed network for the node:test files beside it.
 *
 * Everything lives under one temp folder removed on exit. git runs with an empty global config,
 * so a developer's hooks, signing or default branch never leak into a test.
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { blobSha } from './publish.mjs';

const ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'shelf-tests-'));
process.on('exit', () => fs.rmSync(ROOT, { recursive: true, force: true }));

const gitConfig = path.join(ROOT, 'gitconfig');
fs.writeFileSync(gitConfig, '');
process.env.GIT_CONFIG_GLOBAL = gitConfig;
process.env.GIT_CONFIG_NOSYSTEM = '1';
process.env.GIT_TERMINAL_PROMPT = '0';

export const SITE = 'https://site.test/api/skills/sync';
export const SECRET = 'test-only-hmac-secret';
export const TOKEN = 'test-only-read-token';
/** Three workbench commits, oldest first. */
export const WB = { a: '1'.repeat(40), b: '2'.repeat(40), c: '3'.repeat(40) };

let counter = 0;
export function scratch(name) {
  const dir = path.join(ROOT, `${name}-${++counter}`);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

export function git(cwd, args) {
  return execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
}

export function writeFile(root, rel, content, exec = false) {
  const abs = path.join(root, rel);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, content);
  fs.chmodSync(abs, exec ? 0o755 : 0o644);
}

function filesUnder(root, base = root) {
  const out = [];
  for (const e of fs.readdirSync(root, { withFileTypes: true })) {
    const abs = path.join(root, e.name);
    if (e.isDirectory()) out.push(...filesUnder(abs, base));
    else out.push(path.relative(base, abs).split(path.sep).join('/'));
  }
  return out.sort();
}

/**
 * A skill for buildStage. `visibility: undefined` leaves the key out; `extra` is more frontmatter;
 * `files` maps a path inside the folder to its text, or to { content, exec }; `dirName` names its
 * folder when that is not the slug; `sheetId` pins its id, which by default follows the slug, so the
 * same skill keeps its id from one stage to the next and a rename can keep the old one.
 */
export const skill = (slug, spec = {}) => ({ slug, cat: '1-brand-marketing', visibility: 'public', ...spec });

/** Write stage/ as export-shelf.ts would: skills/**, payload.json and a manifest.json that matches. */
export function buildStage(skills, { sha = WB.a, committedAt = '2026-09-28T10:00:00Z' } = {}) {
  const root = scratch('stage');
  const stageRoot = path.join(root, 'stage');
  const payload = [];
  const entries = skills.map((s, i) => {
    const dir = `skills/${s.cat}/${s.dirName ?? s.slug}`;
    const manifestFile = s.manifestFile ?? 'SKILL.md';
    const name = s.name ?? s.slug;
    const kind = s.kind ?? 'skill';
    const frontmatter = [
      '---',
      `name: ${name}`,
      `sheetId: "${s.sheetId ?? `id-${s.slug}`}"`,
      ...(s.visibility === undefined ? [] : [`visibility: ${s.visibility}`]),
      ...(s.extra ? [s.extra] : []),
      'description: >-',
      '  A test skill that does one thing.',
      '  name: an-indented-line-is-not-a-key',
      '---',
    ];
    writeFile(stageRoot, `${dir}/${manifestFile}`, `${frontmatter.join('\n')}\n# ${s.slug}\n\nBody.\n`);
    for (const [rel, v] of Object.entries(s.files ?? {})) {
      const { content, exec } = typeof v === 'string' ? { content: v, exec: false } : v;
      writeFile(stageRoot, `${dir}/${rel}`, content, exec);
    }
    const stale = {
      repo_url: 'https://github.com/peter-tu-zynkr/zynkr-skill-builder',
      github_url: 'https://example.test/stale',
      install_command: `curl -sL zynkr.ai/s/${s.slug}.md -o ~/.claude/skills/${s.slug}.md`,
    };
    payload.push({ id: `1.${i + 1}`, slug: s.slug, name, kind, ...stale, source_path: `${dir}/${manifestFile}`, visibility: 'public' });
    for (const agent of s.agents ?? []) {
      const agentPath = `${dir}/${s.agentsDir ?? 'agents'}/${agent}.md`;
      writeFile(stageRoot, agentPath, `---\nname: ${agent}\n---\nAn agent.\n`);
      payload.push({ id: `1.${i + 1}.${agent}`, slug: `${s.slug}-${agent}`, name: agent, kind: 'subagent', ...stale, source_path: agentPath, visibility: 'public' });
    }
    return { dir, manifest: `${dir}/${manifestFile}`, id: `1.${i + 1}`, slug: s.slug, name, kind, installable: s.installable ?? true };
  });
  fs.mkdirSync(path.join(stageRoot, 'skills'), { recursive: true });

  const files = filesUnder(path.join(stageRoot, 'skills'), stageRoot).map((p) => {
    const abs = path.join(stageRoot, p);
    return { path: p, mode: fs.statSync(abs).mode & 0o100 ? '100755' : '100644', sha: blobSha(fs.readFileSync(abs)) };
  });
  const manifest = {
    format: 'stage-v1',
    workbench_sha: sha,
    workbench_committed_at: committedAt,
    built_at: '2026-09-28T10:05:00Z',
    counts: { rows: payload.length, manifests: entries.length, subagents: payload.length - entries.length, files: files.length },
    skills: entries,
    files,
  };
  // The run fetch-stage.mjs would have written beside stage/: the export run that built `sha`.
  const run = { id: 42, head_sha: sha, event: 'push', head_branch: 'main', created_at: '2026-09-28T10:06:00Z' };
  const runFile = path.join(root, 'run.json');
  fs.writeFileSync(runFile, JSON.stringify(run, null, 2));
  const stage = { root, stageRoot, manifest, payload, run, runFile };
  stage.save = () => {
    fs.writeFileSync(path.join(stageRoot, 'manifest.json'), JSON.stringify(stage.manifest, null, 2));
    fs.writeFileSync(path.join(stageRoot, 'payload.json'), JSON.stringify(stage.payload, null, 2));
  };
  stage.save();
  return stage;
}

function commit(cwd, message) {
  git(cwd, ['add', '-A', '-f']);
  git(cwd, ['-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-q', '--allow-empty', '-m', message]);
}

/** A bare remote plus a clone of it holding one bootstrap commit, as `gh repo create` leaves the shelf. */
export function makeShelf() {
  const base = scratch('shelf');
  const remote = path.join(base, 'remote.git');
  const shelf = path.join(base, 'shelf');
  git(base, ['init', '-q', '--bare', remote]);
  git(remote, ['symbolic-ref', 'HEAD', 'refs/heads/main']);
  git(base, ['clone', '-q', remote, shelf]);
  git(shelf, ['symbolic-ref', 'HEAD', 'refs/heads/main']);
  writeFile(shelf, 'README.md', '# shelf\n');
  commit(shelf, 'bootstrap');
  git(shelf, ['push', '-q', '-u', 'origin', 'main']);
  return { base, remote, shelf };
}

/** Put some of a stage's folders on the shelf as an earlier export of `sha` would have. */
export function placeOnShelf(shelf, stage, slugs, sha) {
  for (const entry of stage.manifest.skills.filter((s) => slugs.includes(s.slug))) {
    for (const f of stage.manifest.files.filter((x) => x.path.startsWith(`${entry.dir}/`))) {
      const dst = path.join(shelf, f.path);
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(path.join(stage.stageRoot, f.path), dst);
      fs.chmodSync(dst, f.mode === '100755' ? 0o755 : 0o644);
    }
  }
  commit(shelf, `export: earlier\n\nWorkbench-Commit: ${sha}`);
  git(shelf, ['push', '-q']);
}

export const head = (repo, ref = 'HEAD') => git(repo, ['rev-parse', ref]).trim();

/**
 * A fetch stand-in: the compare API and the site sync; it records every call. `compare` is the
 * status the compare answers with 200, or { status, body } for any other answer.
 */
export function network({ compare = 'ahead', status = 200, answer = { upserted: 1, unchanged: 0, would_prune: [] } } = {}) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (String(url).includes('/compare/')) {
      return typeof compare === 'string'
        ? new Response(JSON.stringify({ status: compare }), { status: 200 })
        : new Response(JSON.stringify(compare.body), { status: compare.status });
    }
    if (String(url) === SITE) return new Response(JSON.stringify(answer), { status });
    throw new Error(`unexpected fetch ${url}`);
  };
  return { fetchImpl, calls, posts: () => calls.filter((c) => c.init.method === 'POST') };
}

/** deps for publish()/main(): the stub network, a test env, and captured output. */
export function deps(net, extraEnv = {}) {
  const out = [];
  const err = [];
  const summary = path.join(scratch('summary'), 'summary.md');
  return {
    fetchImpl: net.fetchImpl,
    env: {
      SKILLS_SYNC_HMAC_SECRET: SECRET,
      WORKBENCH_READ_TOKEN: TOKEN,
      SITE_SYNC_URL: SITE,
      GITHUB_STEP_SUMMARY: summary,
      ...extraEnv,
    },
    log: (line) => out.push(line),
    error: (line) => err.push(line),
    out,
    err,
    summary: () => (fs.existsSync(summary) ? fs.readFileSync(summary, 'utf8') : ''),
  };
}

// ── zip, for fetch-stage ─────────────────────────────────────────────────────

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
const crc32 = (buf) => {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};

/** A zip with stored (uncompressed) entries — what the artifact API hands back, minus deflate. */
export function storedZip(entries) {
  const parts = [];
  const central = [];
  let offset = 0;
  for (const { name, data } of entries) {
    const n = Buffer.from(name);
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x21, 12); // 1980-01-01
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(n.length, 26);
    const dirEntry = Buffer.alloc(46);
    dirEntry.writeUInt32LE(0x02014b50, 0);
    dirEntry.writeUInt16LE(20, 4);
    dirEntry.writeUInt16LE(20, 6);
    dirEntry.writeUInt16LE(0x21, 14);
    dirEntry.writeUInt32LE(crc, 16);
    dirEntry.writeUInt32LE(data.length, 20);
    dirEntry.writeUInt32LE(data.length, 24);
    dirEntry.writeUInt16LE(n.length, 28);
    dirEntry.writeUInt32LE(offset, 42);
    parts.push(local, n, data);
    central.push(dirEntry, n);
    offset += 30 + n.length + data.length;
  }
  const cd = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(cd.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...parts, cd, end]);
}

/** tar -czf of `names` inside `dir`, without macOS's ._ companion files. */
export function tarball(dir, names) {
  const out = path.join(scratch('tgz'), 'stage.tgz');
  execFileSync('tar', ['-czf', out, '-C', dir, ...names], { env: { ...process.env, COPYFILE_DISABLE: '1' } });
  return fs.readFileSync(out);
}
