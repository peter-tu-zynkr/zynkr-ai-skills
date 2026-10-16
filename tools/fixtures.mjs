/**
 * fixtures.mjs — tiny stages, shelves and stubbed network for the node:test files beside it.
 *
 * Everything lives under one temp folder removed on exit. git runs with an empty global config,
 * so a developer's hooks, signing or default branch never leak into a test. Every skill name here is
 * made up.
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { blobSha } from './publish.mjs';
import { ListingError, deriveFolder, finishRows, folderView } from './listing.mjs';
import { treeId } from './tree.mjs';

const ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'shelf-tests-'));
process.on('exit', () => fs.rmSync(ROOT, { recursive: true, force: true }));

const gitConfig = path.join(ROOT, 'gitconfig');
fs.writeFileSync(gitConfig, '');
process.env.GIT_CONFIG_GLOBAL = gitConfig;
process.env.GIT_CONFIG_NOSYSTEM = '1';
process.env.GIT_TERMINAL_PROMPT = '0';

export const SITE = 'https://site.test/api/skills/sync';
export const DETAILS = 'https://site.test/api/skills/details';
export const ATLAS = 'https://atlas.example.test/api/shelf';
export const OIDC = 'https://oidc.example.test/token?api-version=2.0';
export const SECRET = 'test-only-hmac-secret';
export const TOKEN = 'test-only-read-token';
export const OIDC_REQUEST_TOKEN = 'test-only-oidc-request-token';
export const RUN_ID = '7001';
export const RUNS = `https://api.github.com/repos/peter-tu-zynkr/zynkr-ai-skills/actions/runs/${RUN_ID}`;
/** This shelf run's start, as GitHub's API gives it: the order key of every post. */
export const RUN_STARTED = '2026-10-15T08:00:00Z';
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
 *
 * `full: true` writes the frontmatter the workbench's schema needs (category from the folder,
 * project, platform, status, author), a numeric sheetId for the skill and each agent, and builds the
 * stage's payload rows with the shelf's own derivation — the stage the workbench would hand over.
 * `ipo` adds input/process/output; `agents` may hold names or { name, sheetId, extra }.
 */
export const skill = (slug, spec = {}) => ({ slug, cat: '1-brand-marketing', visibility: 'public', ...spec });

let numbered = 0;
/** A fresh numeric sheetId for a full skill. */
const nextId = () => `9.${String(++numbered).padStart(2, '0')}`;

function frontmatterOf(s, name, sheetId) {
  const lines = [
    '---',
    `name: ${name}`,
    `sheetId: "${sheetId}"`,
    ...(s.visibility === undefined ? [] : [`visibility: ${s.visibility}`]),
  ];
  if (s.full) {
    lines.push(
      `category: ${s.category ?? s.cat.replace(/^\d+-/, '')}`,
      `project: ${s.project ?? s.slug}`,
      'platform: claude',
      'status: Done',
      'author: Test Author',
    );
    for (const field of ['input', 'process', 'output']) if (s.ipo?.[field]) lines.push(`${field}: "${s.ipo[field]}"`);
  }
  if (s.extra) lines.push(s.extra);
  if (s.description) lines.push('description: >-', `  ${s.description}`, '---');
  else lines.push('description: >-', '  A test skill that does one thing.', '  name: an-indented-line-is-not-a-key', '---');
  return lines.join('\n');
}

/** Write stage/ as export-shelf.ts would: skills/**, payload.json and a manifest.json that matches. */
export function buildStage(skills, { sha = WB.a, committedAt = '2026-09-28T10:00:00Z', runCreatedAt = '2026-09-28T10:06:00Z' } = {}) {
  const root = scratch('stage');
  const stageRoot = path.join(root, 'stage');
  const payload = [];
  const fullDirs = [];
  const entries = skills.map((s, i) => {
    const dir = `skills/${s.cat}/${s.dirName ?? s.slug}`;
    const manifestFile = s.manifestFile ?? 'SKILL.md';
    const name = s.name ?? s.slug;
    const kind = s.kind ?? 'skill';
    const sheetId = s.sheetId ?? (s.full ? nextId() : `id-${s.slug}`);
    writeFile(stageRoot, `${dir}/${manifestFile}`, `${frontmatterOf(s, name, sheetId)}\n# ${s.slug}\n\nBody.\n`);
    for (const [rel, v] of Object.entries(s.files ?? {})) {
      const { content, exec } = typeof v === 'string' ? { content: v, exec: false } : v;
      writeFile(stageRoot, `${dir}/${rel}`, content, exec);
    }
    const stale = {
      repo_url: 'https://github.com/peter-tu-zynkr/zynkr-skill-builder',
      github_url: 'https://example.test/stale',
      install_command: `curl -sL zynkr.ai/s/${s.slug}.md -o ~/.claude/skills/${s.slug}.md`,
    };
    if (!s.full) payload.push({ id: `1.${i + 1}`, slug: s.slug, name, kind, ...stale, source_path: `${dir}/${manifestFile}`, visibility: 'public' });
    (s.agents ?? []).forEach((a, n) => {
      const agent = typeof a === 'string' ? { name: a } : a;
      const agentPath = `${dir}/${s.agentsDir ?? 'agents'}/${agent.name}.md`;
      const agentId = agent.sheetId ?? (s.full ? `${sheetId}${n + 1}` : null);
      const head = ['---', `name: ${agent.name}`, ...(agentId && s.full ? [`sheetId: "${agentId}"`] : []), ...(agent.extra ? [agent.extra] : []), '---'];
      writeFile(stageRoot, agentPath, `${head.join('\n')}\nAn agent.\n`);
      if (!s.full) payload.push({ id: `1.${i + 1}.${agent.name}`, slug: `${s.slug}-${agent.name}`, name: agent.name, kind: 'subagent', ...stale, source_path: agentPath, visibility: 'public' });
    });
    if (s.full) fullDirs.push(dir);
    return { dir, manifest: `${dir}/${manifestFile}`, id: s.full ? sheetId : `1.${i + 1}`, slug: s.slug, name, kind, installable: s.installable ?? true };
  });
  fs.mkdirSync(path.join(stageRoot, 'skills'), { recursive: true });

  const files = filesUnder(path.join(stageRoot, 'skills'), stageRoot).map((p) => {
    const abs = path.join(stageRoot, p);
    return { path: p, mode: fs.statSync(abs).mode & 0o100 ? '100755' : '100644', sha: blobSha(fs.readFileSync(abs)) };
  });
  // A full stage's rows are the shelf's own derivation of its files: what the workbench would send.
  // A folder a test makes unreadable on purpose gets none.
  for (const dir of fullDirs) {
    const rels = files.filter((f) => f.path.startsWith(`${dir}/`)).map((f) => f.path.slice(dir.length + 1));
    const view = folderView(dir, rels, (rel) => fs.readFileSync(path.join(stageRoot, dir, rel), 'utf8'));
    try {
      const { rows } = deriveFolder(view, { today: '2026-09-28' });
      payload.push(...finishRows(rows, { firstSeen: new Map(), today: '2026-08-01' }));
    } catch (err) {
      if (!(err instanceof ListingError)) throw err;
    }
  }
  const manifest = {
    format: 'stage-v1',
    workbench_sha: sha,
    workbench_committed_at: committedAt,
    built_at: '2026-09-28T10:05:00Z',
    counts: { rows: payload.length, manifests: entries.length, subagents: payload.filter((r) => r.kind === 'subagent').length, files: files.length },
    skills: entries,
    files,
  };
  // The run fetch-stage.mjs would have written beside stage/: the export run that built `sha`.
  const run = { id: 42, head_sha: sha, event: 'push', head_branch: 'main', created_at: runCreatedAt };
  const runFile = path.join(root, 'run.json');
  fs.writeFileSync(runFile, JSON.stringify(run, null, 2));
  const stage = { root, stageRoot, manifest, payload, run, runFile };
  stage.save = () => {
    fs.writeFileSync(path.join(stageRoot, 'manifest.json'), JSON.stringify(stage.manifest, null, 2));
    fs.writeFileSync(path.join(stageRoot, 'payload.json'), JSON.stringify(stage.payload, null, 2));
  };
  stage.dir = (slug) => entries.find((e) => e.slug === slug).dir;
  stage.tree = (slug) => {
    const dir = stage.dir(slug);
    return treeId(stage.manifest.files.filter((f) => f.path.startsWith(`${dir}/`)).map((f) => ({ ...f, path: f.path.slice(dir.length + 1) })));
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

/** A token shaped like GitHub's OIDC JWT (unsigned: the shelf never verifies it, Atlas does). */
export function oidcToken(aud) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  return [
    b64({ alg: 'RS256', typ: 'JWT' }),
    b64({
      aud,
      sub: 'repo:peter-tu-zynkr@262132933/zynkr-ai-skills@1401051249:environment:export',
      repository: 'peter-tu-zynkr/zynkr-ai-skills',
      repository_id: '1401051249',
      repository_owner_id: '262132933',
      ref: 'refs/heads/main',
      event_name: 'schedule',
      environment: 'export',
      workflow_ref: 'peter-tu-zynkr/zynkr-ai-skills/.github/workflows/export.yml@refs/heads/main',
      job_workflow_ref: 'peter-tu-zynkr/zynkr-ai-skills/.github/workflows/export.yml@refs/heads/main',
    }),
    'c2ln',
  ].join('.');
}

/** Atlas's answer: folders as [dir, tree] pairs, and the 「as is」 dirs. */
export const atlasList = (folders = [], asIs = []) => ({
  format: 'atlas-shelf-v1',
  folders: folders.map(([p, tree]) => ({ path: p, tree })),
  as_is: asIs.map((p) => ({ path: p })),
});

/**
 * A fetch stand-in: the compare API, this run's record, the OIDC token, Atlas's door, the site's
 * details and the site sync; it records every call. `compare` is the status the compare answers with
 * 200, or { status, body } for any other answer. `atlas` is the door's 200 body, { status, body } for
 * another answer, or 'down' to fail the connection. `details` is the site's live rows by id.
 */
export function network({
  compare = 'ahead',
  status = 200,
  answer = { upserted: 1, unchanged: 0, would_prune: [] },
  atlas = atlasList(),
  details = {},
  detailsStatus = 200,
  runStarted = RUN_STARTED,
} = {}) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const u = String(url);
    if (u.includes('/compare/')) {
      return typeof compare === 'string'
        ? new Response(JSON.stringify({ status: compare }), { status: 200 })
        : new Response(JSON.stringify(compare.body), { status: compare.status });
    }
    if (u === SITE) return new Response(JSON.stringify(answer), { status });
    if (u === RUNS) return new Response(JSON.stringify({ id: Number(RUN_ID), run_started_at: runStarted }), { status: 200 });
    if (u.startsWith(`${OIDC}&audience=`)) {
      if (init.headers?.Authorization !== `bearer ${OIDC_REQUEST_TOKEN}`) return new Response('{}', { status: 401 });
      return new Response(JSON.stringify({ value: oidcToken(decodeURIComponent(u.split('&audience=')[1])) }), { status: 200 });
    }
    if (u === ATLAS) {
      if (atlas === 'down') throw new TypeError('fetch failed');
      // The door names no reason: every refusal is the same 401 (it logs the reason on its own side).
      const audience = JSON.parse(Buffer.from(String(init.headers?.Authorization).split('.')[1], 'base64url')).aud;
      if (audience !== 'zynkr-atlas-shelf') return new Response(JSON.stringify({ error: 'refused' }), { status: 401 });
      return atlas && typeof atlas.status === 'number'
        ? new Response(JSON.stringify(atlas.body), { status: atlas.status })
        : new Response(JSON.stringify(atlas), { status: 200 });
    }
    if (u.startsWith(DETAILS)) return new Response(JSON.stringify(details), { status: detailsStatus });
    if (u.startsWith('https://atlas.invalid/')) throw new TypeError('fetch failed');
    throw new Error(`unexpected fetch ${url}`);
  };
  return {
    fetchImpl,
    calls,
    posts: () => calls.filter((c) => c.init.method === 'POST' && c.url === SITE),
    atlasCalls: () => calls.filter((c) => c.url === ATLAS || c.url.startsWith('https://atlas.invalid/')),
  };
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
      SITE_DETAILS_URL: DETAILS,
      ATLAS_SHELF_URL: ATLAS,
      ACTIONS_ID_TOKEN_REQUEST_URL: OIDC,
      ACTIONS_ID_TOKEN_REQUEST_TOKEN: OIDC_REQUEST_TOKEN,
      GITHUB_RUN_ID: RUN_ID,
      GITHUB_TOKEN: 'test-only-job-token',
      GITHUB_STEP_SUMMARY: summary,
      ...extraEnv,
    },
    now: () => new Date('2026-10-15T08:00:30Z'),
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
