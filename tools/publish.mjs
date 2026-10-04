#!/usr/bin/env node
/**
 * publish.mjs — SKB-038: put the workbench's public stage on this shelf, then tell zynkr.ai.
 *
 * The private workbench (peter-tu-zynkr/zynkr-skill-builder) builds the public tree and hands it
 * over as stage.tgz; fetch-stage.mjs downloads and unpacks it. This file trusts none of it:
 *
 *   a. --seed-fail plants an unlisted SKILL.md first, so (b) refuses: the red proof (AC-18).
 *   b. stage/ holds manifest.json, payload.json and skills/ only, and the files under skills/ are
 *      exactly manifest.files: same paths, same git blob shas, same modes (AC-9). Its
 *      workbench_sha is the commit of the run it came from (--run: fetch-stage's run.json).
 *   c. Every owning manifest says `visibility: public`, no other SKILL.md / CLAUDE.md says
 *      anything else, and names are CLI-safe and unique.
 *   d. Every payload row sits in exactly one public folder. repo_url, github_url and
 *      install_command are derived here and overwrite whatever the stage carried.
 *   e. A folder the shelf does not hold yet waits for --promote (AC-12), unless it is a skill the
 *      shelf already publishes under another folder: moved between categories, or renamed (its
 *      manifest says `renamed_from: <old name>` and keeps the old folder's sheetId). A held skill is
 *      named by its sheetId in every output (log, summary, commit message, dry-run), never by its
 *      slug: it may be a client build marked public by mistake, and a client build's slug names the
 *      client (workbench SKB-054). --promote takes sheetIds or slugs.
 *   f. A stage under half the shelf waits for --allow-shrink.
 *   g. The stage must be newer than the shelf's last `Workbench-Commit:` trailer (AC-10).
 *   h. prune: a scheduled run prunes, a dispatch reports unless told `true` (AC-11).
 *   i. skills/ is mirrored, committed as github-actions[bot] and pushed (never forced).
 *   j. The signed shelf-v1 body is posted on every run, whether the shelf changed or not. The
 *      site's answer is logged as its status and counts: its would_prune / pruned lists name
 *      live rows the shelf does not carry, team skills among them, so they never reach this log.
 *
 * Any refusal exits 1 before anything is pushed or posted (a failed post after a push exits 1
 * too; the next run posts again). This repo's logs are public, so until the marks are checked (c)
 * a refusal gives counts, never a path: a stage that went wrong may carry a team skill, and its
 * name must not reach this log. After (c) a refusal names a file the shelf already publishes by its
 * path, and one new to the shelf by its sheetId only: it comes before the hold (e), and a new file may
 * belong to a client build marked public by mistake (wordsFor). Rebuild the stage in the workbench to
 * see which files (`npx tsx scripts/export-shelf.ts --out <dir>`).
 *
 *   node tools/publish.mjs --stage <dir holding stage/> --shelf <this checkout>
 *        --event schedule|workflow_dispatch --run <run.json> [--prune report|true]
 *        [--promote <sheetIds or slugs, comma-separated>|all] [--allow-shrink] [--allow-rewind]
 *        [--seed-fail] [--dry-run]
 *
 * Env: WORKBENCH_READ_TOKEN (the compare call), SKILLS_SYNC_HMAC_SECRET, SITE_SYNC_URL
 * (default https://zynkr.ai/api/skills/sync), GITHUB_STEP_SUMMARY (optional).
 */

import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import {
  Refusal,
  SHELF_URL,
  SITE_SYNC_URL,
  WORKBENCH,
  annotation,
  githubHeaders,
  httpHint,
  plural,
  refuse,
} from './common.mjs';

export const NAME_RE = /^[a-z0-9][a-z0-9-]*$/;
export const OVERRIDE_RE =
  /^npx skills add https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+ --skill [a-z0-9][a-z0-9-]*$/;
const SHA_RE = /^[0-9a-f]{40}$/;
const MODES = new Set(['100644', '100755']);
const KINDS = new Set(['skill', 'orchestrator', 'subagent']);
const MANIFEST_NAMES = new Set(['SKILL.md', 'CLAUDE.md']);
const STAGE_ENTRIES = ['manifest.json', 'payload.json', 'skills'];
const BOT = { name: 'github-actions[bot]', email: '41898282+github-actions[bot]@users.noreply.github.com' };
const USAGE =
  'usage: publish.mjs --stage <dir holding stage/> --shelf <checkout> --event schedule|workflow_dispatch ' +
  '--run <run.json> [--prune report|true] [--promote a,b|all] [--allow-shrink] [--allow-rewind] [--seed-fail] [--dry-run]';

// ── small helpers ────────────────────────────────────────────────────────────

/** git's blob id: sha1 of `blob <length>\0` followed by the bytes. */
export const blobSha = (bytes) =>
  crypto.createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');

/** git's reading of a mode: executable by its owner or not. */
const modeOf = (stat) => (stat.mode & 0o100 ? '100755' : '100644');

const isObject = (v) => typeof v === 'object' && v !== null && !Array.isArray(v);
const lstat = (p) => fs.lstatSync(p, { throwIfNoEntry: false });
const isDir = (p) => lstat(p)?.isDirectory() === true;
const isFile = (p) => lstat(p)?.isFile() === true;
const within = (file, dir) => file.startsWith(`${dir}/`);

/** A relative path under skills/ with no empty, `.` or `..` segment. */
const isSkillsPath = (p) =>
  typeof p === 'string' &&
  p.startsWith('skills/') &&
  !/[\\\0]/.test(p) &&
  p.split('/').every((s) => s !== '' && s !== '.' && s !== '..');

/** Everything under `root`, as posix paths relative to `base`, without following links. */
function walk(root, base) {
  const out = { files: [], dirs: [], other: [] };
  const visit = (abs) => {
    for (const name of fs.readdirSync(abs)) {
      const child = path.join(abs, name);
      const rel = path.relative(base, child).split(path.sep).join('/');
      const st = fs.lstatSync(child);
      if (st.isDirectory()) {
        out.dirs.push(rel);
        visit(child);
      } else if (st.isFile()) out.files.push(rel);
      else out.other.push(rel);
    }
  };
  if (isDir(root)) visit(root);
  return out;
}

function readJson(file, label) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    // The parser's message quotes the text around the error, and that text is unchecked.
    return refuse(`${label} is not valid JSON`);
  }
}

function git(cwd, args, options = {}) {
  return execFileSync('git', args, {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    maxBuffer: 256 * 1024 * 1024,
    ...options,
  });
}

// ── frontmatter ──────────────────────────────────────────────────────────────

/** One top-level YAML scalar: quotes removed, a trailing comment dropped; block and empty → null. */
function scalar(raw) {
  const v = raw.trim();
  if (v.startsWith('"')) {
    let end = 1;
    while (end < v.length && v[end] !== '"') end += v[end] === '\\' ? 2 : 1;
    try {
      return JSON.parse(v.slice(0, end + 1));
    } catch {
      return v.slice(1, end);
    }
  }
  if (v.startsWith("'")) {
    const m = /^'((?:[^']|'')*)'/.exec(v);
    return m ? m[1].replace(/''/g, "'") : v.slice(1);
  }
  const plain = v.replace(/\s+#.*$/, '').trim();
  return plain === '' || plain.startsWith('|') || plain.startsWith('>') ? null : plain;
}

/**
 * The top-level scalar keys of a `---` frontmatter block: { keys: Map, dupes: Set }, or null when
 * the file has none. Indented lines (folded descriptions, lists) are skipped; only name,
 * visibility, install_command, sheetId and renamed_from are read, and a repeated one is reported
 * in `dupes`.
 */
export function parseFrontmatter(text) {
  const lines = text.replace(/^﻿/, '').split(/\r?\n/);
  if (lines[0] !== '---') return null;
  const keys = new Map();
  const dupes = new Set();
  for (const line of lines.slice(1)) {
    if (line === '---' || line === '...') return { keys, dupes };
    const m = /^([A-Za-z_][\w.-]*)\s*:(?:\s+(.*))?$/.exec(line);
    if (!m) continue;
    if (keys.has(m[1])) dupes.add(m[1]);
    keys.set(m[1], scalar(m[2] ?? ''));
  }
  return null;
}

// ── a. the red proof ─────────────────────────────────────────────────────────

export function seedFail(stageRoot) {
  const dir = path.join(stageRoot, 'skills', '_seed_fail');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, 'SKILL.md'),
    '---\nname: seed-fail\nvisibility: public\n---\n' +
      'Planted by a seed_fail dispatch. No manifest lists it, so the publisher must refuse this stage (SKB-038 AC-18).\n',
  );
}

// ── b. structure ─────────────────────────────────────────────────────────────

function checkManifestShape(manifest) {
  if (!isObject(manifest) || manifest.format !== 'stage-v1') refuse('manifest.json is not format stage-v1');
  if (!SHA_RE.test(String(manifest.workbench_sha))) refuse('manifest.workbench_sha is not a 40-hex commit');
  const at = manifest.workbench_committed_at;
  if (typeof at !== 'string' || Number.isNaN(Date.parse(at))) {
    refuse('manifest.workbench_committed_at is not an ISO-8601 time');
  }
  if (!Array.isArray(manifest.files) || !Array.isArray(manifest.skills)) {
    refuse('manifest.json lacks its files or skills list');
  }

  const paths = new Set();
  manifest.files.forEach((f, i) => {
    if (!isObject(f) || !isSkillsPath(f.path) || !MODES.has(f.mode) || !SHA_RE.test(String(f.sha))) {
      refuse(`manifest.files[${i}] is not {path under skills/, mode 100644|100755, 40-hex sha}`);
    }
    if (paths.has(f.path)) refuse(`manifest.files[${i}] repeats a path`);
    paths.add(f.path);
  });

  manifest.skills.forEach((s, i) => {
    const ok =
      isObject(s) &&
      isSkillsPath(s.dir) &&
      typeof s.manifest === 'string' &&
      path.posix.dirname(s.manifest) === s.dir &&
      MANIFEST_NAMES.has(path.posix.basename(s.manifest)) &&
      paths.has(s.manifest) &&
      typeof s.slug === 'string' &&
      s.slug !== '' &&
      typeof s.name === 'string' &&
      typeof s.installable === 'boolean';
    if (!ok) {
      refuse(
        `manifest.skills[${i}] is not {dir, manifest: <dir>/SKILL.md or CLAUDE.md listed in files, slug, name, installable}`,
      );
    }
  });
  const dirs = manifest.skills.map((s) => s.dir);
  if (dirs.some((d, i) => dirs.some((e, j) => i !== j && (d === e || within(d, e))))) {
    refuse('manifest.skills repeats a folder or nests one inside another');
  }
  const slugs = new Set(manifest.skills.map((s) => s.slug));
  if (slugs.size !== manifest.skills.length) refuse('manifest.skills repeats a slug');
}

function checkTree(stageRoot, manifest) {
  const tree = walk(path.join(stageRoot, 'skills'), stageRoot);
  const listed = new Map(manifest.files.map((f) => [f.path, f]));
  const present = new Set(tree.files);
  const problems = [];
  const count = (n, one, many) => {
    if (n) problems.push(plural(n, one, many));
  };

  count(tree.other.length, 'entry that is neither a file nor a folder', 'entries that are neither a file nor a folder');
  count(tree.files.filter((p) => !listed.has(p)).length, 'file not in manifest.files', 'files not in manifest.files');
  count([...listed.keys()].filter((p) => !present.has(p)).length, 'listed file missing', 'listed files missing');

  const needed = new Set();
  for (const p of listed.keys()) {
    for (let d = path.posix.dirname(p); d !== 'skills' && d !== '.'; d = path.posix.dirname(d)) needed.add(d);
  }
  count(tree.dirs.filter((d) => !needed.has(d)).length, 'folder holding no listed file', 'folders holding no listed file');

  let badSha = 0;
  let badMode = 0;
  for (const [p, f] of listed) {
    if (!present.has(p)) continue;
    const abs = path.join(stageRoot, p);
    if (blobSha(fs.readFileSync(abs)) !== f.sha) badSha++;
    if (modeOf(fs.lstatSync(abs)) !== f.mode) badMode++;
  }
  count(badSha, 'file whose bytes differ from its listed sha', 'files whose bytes differ from their listed sha');
  count(badMode, 'file whose executable bit differs from its listed mode', 'files whose executable bit differs from their listed mode');

  const dirs = manifest.skills.map((s) => s.dir);
  const loose = [...listed.keys()].filter((p) => !dirs.some((d) => within(p, d))).length;
  count(loose, 'listed file outside every skill folder', 'listed files outside every skill folder');

  if (problems.length) {
    refuse(
      `the stage does not match manifest.json: ${problems.join('; ')}. ` +
        'This public log names no path; rebuild the stage in the workbench to see which.',
    );
  }
}

/**
 * (b): the stage's workbench_sha must be the commit of the run fetch-stage.mjs took it from
 * (--run, its run.json) — a run fetch-stage checked is on the workbench's main. Otherwise a stage
 * could claim any commit and jump the order check (g) with nothing on main behind it. A dry run
 * may leave --run out.
 */
export function checkRunSha(run, manifest, dryRun = false) {
  if (run === undefined && dryRun) return;
  if (!isObject(run) || !SHA_RE.test(String(run.head_sha))) {
    refuse('--run must name the run.json fetch-stage.mjs wrote beside stage/ ({ id, head_sha, … })');
  }
  if (run.head_sha !== manifest.workbench_sha) {
    refuse(
      `the stage claims workbench commit ${manifest.workbench_sha.slice(0, 7)}, but the run it came from ` +
        `built ${run.head_sha.slice(0, 7)}`,
    );
  }
}

/** (b): the stage's shape, and its tree against manifest.files. Returns the parsed JSON. */
export function readStage(stageRoot) {
  if (!isDir(stageRoot)) refuse('there is no stage/ folder under --stage');
  const extra = fs.readdirSync(stageRoot).filter((n) => !STAGE_ENTRIES.includes(n));
  if (extra.length) {
    refuse(`stage/ holds ${plural(extra.length, 'entry', 'entries')} besides manifest.json, payload.json and skills/`);
  }
  for (const f of ['manifest.json', 'payload.json']) {
    if (!isFile(path.join(stageRoot, f))) refuse(`stage/${f} is missing or not a file`);
  }
  if (!isDir(path.join(stageRoot, 'skills'))) refuse('stage/skills/ is missing or not a folder');

  const manifest = readJson(path.join(stageRoot, 'manifest.json'), 'manifest.json');
  const payload = readJson(path.join(stageRoot, 'payload.json'), 'payload.json');
  checkManifestShape(manifest);
  checkTree(stageRoot, manifest);
  return { manifest, payload };
}

// ── c. marks ─────────────────────────────────────────────────────────────────

const says = (fm, key, value) => !fm.dupes.has(key) && fm.keys.get(key) === value;

/** (c): returns Map(dir → { entry, fm }) once every owning manifest is marked public. */
/**
 * How a refusal names a stage file: by its path when the shelf already publishes that file, else by its
 * sheetId. A refusal comes before the hold (e), and a file new to the shelf may belong to a client build
 * marked public by mistake, whose path and slug name the client (workbench SKB-054, review round 4).
 * `shelfHas(path)` says whether the shelf holds a file; without it nothing is named by path.
 */
export function wordsFor(shelfHas, file, id) {
  if (shelfHas(file)) return file;
  return id ? `a file new to the shelf (sheetId ${id})` : 'a file new to the shelf, with no sheetId';
}

export function checkMarks(stageRoot, manifest, shelfHas = () => false) {
  const frontmatter = (p) => parseFrontmatter(fs.readFileSync(path.join(stageRoot, p), 'utf8'));
  const owners = new Map();
  let unmarked = 0;
  for (const entry of manifest.skills) {
    const fm = frontmatter(entry.manifest);
    if (fm && says(fm, 'visibility', 'public')) owners.set(entry.dir, { entry, fm });
    else unmarked++;
  }
  const owning = new Set(manifest.skills.map((s) => s.manifest));
  let stray = 0;
  for (const f of manifest.files) {
    if (owning.has(f.path) || !MANIFEST_NAMES.has(path.posix.basename(f.path))) continue;
    const fm = frontmatter(f.path);
    if (fm?.keys.has('visibility') && !says(fm, 'visibility', 'public')) stray++;
  }
  if (unmarked) {
    refuse(
      `${plural(unmarked, 'skill manifest')} in the stage lack${unmarked === 1 ? 's' : ''} visibility: public. ` +
        'This public log names none; rebuild the stage in the workbench to see which.',
    );
  }
  if (stray) {
    refuse(
      `${plural(stray, 'SKILL.md or CLAUDE.md', 'SKILL.md or CLAUDE.md files')} inside a public folder declare${stray === 1 ? 's' : ''} ` +
        'a visibility other than public. This public log names none; rebuild the stage in the workbench to see which.',
    );
  }

  // Every folder is marked public from here on. A message names one the shelf already publishes by its
  // path, and one new to the shelf by its sheetId only, never its path or name (wordsFor).
  const names = new Map();
  for (const { entry, fm } of owners.values()) {
    const known = shelfHas(entry.manifest);
    const words = wordsFor(shelfHas, entry.manifest, sheetIdOf(fm));
    const name = fm.keys.get('name');
    if (fm.dupes.has('name') || typeof name !== 'string' || !NAME_RE.test(name)) {
      refuse(`${words}: its name must match ${NAME_RE} (the CLI installs by name)`);
    }
    if (name !== entry.name) {
      refuse(known ? `${entry.manifest}: manifest.json calls it "${entry.name}", its frontmatter "${name}"` : `${words}: manifest.json and its frontmatter name it differently`);
    }
    if (names.has(name)) {
      const other = names.get(name);
      refuse(known && other.known ? `the name "${name}" is used by both ${other.words} and ${words}` : `one name is used by both ${other.words} and ${words}`);
    }
    names.set(name, { words, known });
  }
  return owners;
}

// ── d. payload ───────────────────────────────────────────────────────────────

/** The public fields of one row, from the tree: never from what the stage carried. */
export function deriveFields(rec, { entry, fm }, shelfHas = () => false) {
  const src = rec.source_path;
  const github_url =
    path.posix.basename(src) === 'CLAUDE.md'
      ? `${SHELF_URL}/tree/main/${path.posix.dirname(src)}`
      : `${SHELF_URL}/blob/main/${src}`;
  let install_command = null;
  if (rec.kind !== 'subagent' && entry.installable) {
    if (fm.keys.has('install_command')) {
      const override = fm.keys.get('install_command');
      if (fm.dupes.has('install_command') || typeof override !== 'string' || !OVERRIDE_RE.test(override)) {
        refuse(`${wordsFor(shelfHas, entry.manifest, sheetIdOf(fm))}: install_command must be an "npx skills add https://github.com/<owner>/<repo> --skill <name>" line`);
      }
      install_command = override;
    } else {
      install_command = `npx skills add ${SHELF_URL} --skill ${fm.keys.get('name')}`;
    }
  }
  return { repo_url: SHELF_URL, github_url, install_command };
}

/** (d): [{ dir, row }] — each row with its owning folder and its derived fields. A refusal names a row
 *  the shelf doesn't publish yet by its id, never its path or slug (wordsFor). */
export function derivePayload(payload, manifest, owners, shelfHas = () => false) {
  if (!Array.isArray(payload)) refuse('payload.json is not an array');
  const files = new Set(manifest.files.map((f) => f.path));
  const dirs = [...owners.keys()];
  const slugs = new Set();
  const rows = payload.map((rec, i) => {
    if (!isObject(rec) || typeof rec.source_path !== 'string' || !files.has(rec.source_path)) {
      refuse(`payload[${i}].source_path is not a file in the stage`);
    }
    const hits = dirs.filter((d) => within(rec.source_path, d));
    if (hits.length !== 1) refuse(`payload[${i}].source_path sits in ${hits.length} skill folders, not one`);
    const known = shelfHas(rec.source_path);
    const where = wordsFor(shelfHas, rec.source_path, typeof rec.id === 'string' ? rec.id : null);
    if (rec.visibility !== 'public') refuse(`the payload row for ${where} is not marked visibility: public`);
    if (typeof rec.slug !== 'string' || rec.slug === '') refuse(`the payload row for ${where} has no slug`);
    if (slugs.has(rec.slug)) refuse(known ? `the payload slug "${rec.slug}" appears twice` : `the payload row for ${where} repeats another row's slug`);
    slugs.add(rec.slug);
    if (!KINDS.has(rec.kind)) refuse(`the payload row for ${where} has kind "${rec.kind}", not skill, orchestrator or subagent`);
    return { dir: hits[0], row: { ...rec, ...deriveFields(rec, owners.get(hits[0]), shelfHas) } };
  });
  for (const { entry, fm } of owners.values()) {
    if (!rows.some((r) => r.row.source_path === entry.manifest)) refuse(`${wordsFor(shelfHas, entry.manifest, sheetIdOf(fm))} has no payload row`);
  }
  return rows;
}

// ── e, f. promotion and shrink ───────────────────────────────────────────────

/** One frontmatter key as a non-empty string; missing, empty or repeated → null. */
const keyOf = (fm, key) => {
  const v = fm && !fm.dupes.has(key) ? fm.keys.get(key) : null;
  return typeof v === 'string' && v !== '' ? v : null;
};

/** A manifest's sheetId: the skill's pinned id, which a rename keeps. */
export const sheetIdOf = (fm) => keyOf(fm, 'sheetId');

/** A manifest's `renamed_from`: the name the skill had before a rename, written by whoever renamed it. */
export const renamedFromOf = (fm) => keyOf(fm, 'renamed_from');

/**
 * The skill folders on the shelf now: the topmost folders under skills/ holding a SKILL.md or
 * CLAUDE.md, each with the frontmatter names and sheetIds its manifests carry:
 * [{ dir, names: Set, ids: Set }].
 */
export function shelfSkills(shelfRoot) {
  const found = [];
  const visit = (abs, rel) => {
    const entries = fs.readdirSync(abs, { withFileTypes: true });
    const manifests = entries.filter((e) => e.isFile() && MANIFEST_NAMES.has(e.name));
    if (rel !== 'skills' && manifests.length) {
      const names = new Set();
      const ids = new Set();
      for (const e of manifests) {
        const fm = parseFrontmatter(fs.readFileSync(path.join(abs, e.name), 'utf8'));
        const name = fm && !fm.dupes.has('name') ? fm.keys.get('name') : null;
        if (typeof name === 'string' && name) names.add(name);
        const id = sheetIdOf(fm);
        if (id) ids.add(id);
      }
      found.push({ dir: rel, names, ids });
      return;
    }
    for (const e of entries) if (e.isDirectory()) visit(path.join(abs, e.name), `${rel}/${e.name}`);
  };
  const root = path.join(shelfRoot, 'skills');
  if (isDir(root)) visit(root, 'skills');
  return found.sort((a, b) => (a.dir < b.dir ? -1 : a.dir > b.dir ? 1 : 0));
}

/**
 * (e): a stage folder the shelf does not hold is held unless `promote` is `all` or names its slug.
 * The shelf holds a folder under the same path. A skill moved between categories stays published
 * when the shelf holds a folder of the same folder name that the stage no longer has, whose
 * manifest carries the same frontmatter name. A new skill that only reuses a public folder name is
 * held like any other: folder names are not unique across categories, names are.
 *
 * A renamed skill stays published too, when two things agree: its manifest says which public
 * skill it was (`renamed_from: <old name>`), and that skill's shelf folder carries the same pinned
 * sheetId. A sheetId alone is not enough: the workbench can hand a retired skill's id to a new one,
 * so a retirement and a new skill in one run would pass as a rename. The old folder must also have
 * left the stage and be no other folder's category move; the id must be carried by no other stage
 * folder; and one old folder renames into one new folder only. Anything less certain — no mark, a
 * mark the id does not back, an id or an old folder two folders claim — is held for the owner as
 * before (D-76). `renamed` lists { skill, from } with `from` the shelf folder it replaces.
 *
 * `skills` are manifest.skills entries; publish() adds `sheetId` and `renamedFrom` from each one's
 * manifest.
 */
export function planPromotion(skills, shelf, promote = '') {
  const paths = new Set(shelf.map((h) => h.dir));
  const stageDirs = new Set(skills.map((s) => s.dir));
  const movedFrom = (s) =>
    shelf.some(
      (h) =>
        !stageDirs.has(h.dir) &&
        path.posix.basename(h.dir) === path.posix.basename(s.dir) &&
        h.names.has(s.name),
    );
  const movedTo = (h) =>
    skills.some((t) => path.posix.basename(t.dir) === path.posix.basename(h.dir) && h.names.has(t.name));
  const renameOf = (s) => {
    if (!s.renamedFrom || !s.sheetId) return null;
    if (skills.filter((t) => t.sheetId === s.sheetId).length !== 1) return null;
    const holders = shelf.filter((h) => h.names.has(s.renamedFrom) && h.ids.has(s.sheetId));
    if (holders.length !== 1) return null;
    const [h] = holders;
    // Gone from the stage, and not already explained as a category move of another stage folder.
    return !stageDirs.has(h.dir) && !movedTo(h) ? h.dir : null;
  };
  const isNew = (s) => !paths.has(s.dir) && !movedFrom(s);
  const claims = skills.filter(isNew).map(renameOf).filter(Boolean);
  const renamedFrom = (s) => {
    const from = renameOf(s);
    return from && claims.filter((c) => c === from).length === 1 ? from : null;
  };
  const all = promote.trim() === 'all';
  const named = new Set(all ? [] : promote.split(',').map((s) => s.trim()).filter(Boolean));
  const kept = [];
  const held = [];
  const promoted = [];
  const renamed = [];
  for (const s of skills) {
    if (!isNew(s)) {
      kept.push(s);
      continue;
    }
    const from = renamedFrom(s);
    if (from) {
      kept.push(s);
      renamed.push({ skill: s, from });
    } else if (all || named.has(s.slug) || (s.sheetId && named.has(s.sheetId))) {
      kept.push(s);
      promoted.push(s);
    } else held.push(s);
  }
  const unmatched = [...named].filter((n) => !skills.some((s) => s.slug === n || s.sheetId === n)).length;
  return { kept, held, promoted, renamed, unmatched };
}

/** (f): a stage that would leave fewer than half the shelf's folders needs --allow-shrink. */
export function checkShrink(keptCount, shelfCount, allowShrink) {
  if (shelfCount > 0 && keptCount < shelfCount / 2 && !allowShrink) {
    refuse(
      `the stage would leave ${plural(keptCount, 'skill')} on a shelf that holds ${shelfCount}: under half. ` +
        'Dispatch with allow_shrink if that is intended.',
    );
  }
}

// ── g, h. order and prune ────────────────────────────────────────────────────

/** The workbench sha in the newest `Workbench-Commit:` trailer on the shelf, or null. */
export function lastWorkbenchCommit(shelfRoot) {
  try {
    git(shelfRoot, ['rev-parse', '--verify', '-q', 'HEAD']);
  } catch {
    return null; // no commit yet
  }
  const body = git(shelfRoot, ['log', '-n', '1', '-E', '--grep=^Workbench-Commit: [0-9a-f]{40}$', '--format=%B']);
  const hits = [...body.matchAll(/^Workbench-Commit: ([0-9a-f]{40})\s*$/gm)];
  return hits.length ? hits[hits.length - 1][1] : null;
}

/**
 * (g): first | identical | ahead | behind | diverged | unrelated — the stage's commit against the
 * last export's. A 404 is not the token's fault here (fetch-stage just read the workbench with it):
 * GitHub answers 404 "No common ancestor" for two commits that share no history (a filter-repo
 * purge), which is `diverged`; any other 404 means the last export's commit is gone from the
 * workbench, `unrelated`. Both are rewinds, accepted only when dispatched with allow_rewind.
 */
export async function ordering({ last, next, token, fetchImpl }) {
  if (!last) return 'first';
  if (last === next) return 'identical';
  if (!token) refuse('the secret WORKBENCH_READ_TOKEN is not set; it is needed to compare the stage with the last export');
  const url = `https://api.github.com/repos/${WORKBENCH}/compare/${last}...${next}?per_page=1`;
  let res;
  try {
    res = await fetchImpl(url, { headers: githubHeaders(token) });
  } catch (err) {
    refuse(`comparing the last export with the stage failed: ${err.message}`);
  }
  if (res.status === 404) {
    const text = await res.text().catch(() => '');
    return /No common ancestor/i.test(text) ? 'diverged' : 'unrelated';
  }
  if (!res.ok) refuse(`comparing the last export with the stage answered ${res.status}: ${httpHint(res.status)}`);
  const { status } = await res.json();
  if (!['ahead', 'behind', 'diverged', 'identical'].includes(status)) {
    refuse(`comparing the last export with the stage answered an unknown status "${status}"`);
  }
  return status;
}

/** (h): a scheduled run prunes; a dispatch reports unless told `true`. */
export function pruneValue(event, prune) {
  if (event === 'schedule') return true;
  if (event !== 'workflow_dispatch') refuse('--event must be schedule or workflow_dispatch');
  const value = prune || 'report';
  if (value === 'true') return true;
  if (value === 'report') return 'report';
  return refuse('--prune must be true or report');
}

// ── i. mirror ────────────────────────────────────────────────────────────────

/** What the mirror will do: the wanted files, and which folders it adds, changes and removes. */
export function planMirror(shelfRoot, manifest, kept, shelfDirs) {
  const keptDirs = kept.map((s) => s.dir);
  const desired = new Map(
    manifest.files.filter((f) => keptDirs.some((d) => within(f.path, d))).map((f) => [f.path, f]),
  );
  const tree = walk(path.join(shelfRoot, 'skills'), shelfRoot);
  const current = new Map(tree.other.map((p) => [p, null]));
  for (const p of tree.files) {
    const abs = path.join(shelfRoot, p);
    current.set(p, { sha: blobSha(fs.readFileSync(abs)), mode: modeOf(fs.lstatSync(abs)) });
  }
  const differs = (p) => {
    const want = desired.get(p);
    const have = current.get(p);
    return !want || !have || want.sha !== have.sha || want.mode !== have.mode;
  };
  const onShelf = new Set(shelfDirs);
  const everyPath = [...new Set([...desired.keys(), ...current.keys()])];
  return {
    desired,
    added: kept.filter((s) => !onShelf.has(s.dir)),
    changed: kept.filter((s) => onShelf.has(s.dir) && everyPath.some((p) => within(p, s.dir) && differs(p))),
    removed: shelfDirs.filter((d) => !keptDirs.includes(d)),
    loose: [...current.keys()].filter((p) => !desired.has(p) && !shelfDirs.some((d) => within(p, d))).length,
  };
}

/** Make <shelf>/skills hold exactly `desired`, copied from the stage with their modes. */
export function mirror(shelfRoot, stageRoot, desired) {
  const root = path.join(shelfRoot, 'skills');
  const tree = walk(root, shelfRoot);
  for (const p of tree.other) fs.rmSync(path.join(shelfRoot, p), { force: true });
  for (const p of tree.files) if (!desired.has(p)) fs.rmSync(path.join(shelfRoot, p), { force: true });
  // Reverse order visits every folder after everything inside it.
  for (const d of [...tree.dirs].sort().reverse()) {
    const abs = path.join(shelfRoot, d);
    if (fs.readdirSync(abs).length === 0) fs.rmdirSync(abs);
  }
  for (const [p, f] of desired) {
    const dst = path.join(shelfRoot, p);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(path.join(stageRoot, p), dst);
    fs.chmodSync(dst, f.mode === '100755' ? 0o755 : 0o644);
  }
  if (isDir(root) && fs.readdirSync(root).length === 0) fs.rmdirSync(root);
}

/**
 * Stage skills/ in git's index and prove the index equals the stage (a .gitattributes filter in a
 * skill folder could otherwise rewrite bytes on the way in). Returns whether anything changed.
 */
export function stageIndex(shelfRoot, desired) {
  git(shelfRoot, ['rm', '-r', '-q', '--cached', '--ignore-unmatch', '--', 'skills']);
  // -f: a skill's own .gitignore must not keep one of its tracked files off the shelf.
  if (isDir(path.join(shelfRoot, 'skills'))) git(shelfRoot, ['add', '-f', '--', 'skills']);
  const index = new Map();
  for (const line of git(shelfRoot, ['ls-files', '-s', '-z', '--', 'skills']).split('\0').filter(Boolean)) {
    const [meta, p] = line.split('\t');
    const [mode, sha] = meta.split(' ');
    index.set(p, { mode, sha });
  }
  const off = [...new Set([...index.keys(), ...desired.keys()])].filter((p) => {
    const a = index.get(p);
    const b = desired.get(p);
    return !a || !b || a.mode !== b.mode || a.sha !== b.sha;
  });
  if (off.length) {
    refuse(
      `after the mirror, git's index differs from the stage at ${plural(off.length, 'path')} ` +
        `(${off.slice(0, 5).join(', ')}): a .gitattributes or line-ending rule in a skill folder?`,
    );
  }
  return git(shelfRoot, ['diff', '--cached', '--name-only', '--', 'skills']).trim() !== '';
}

/** The mirror's adds and removes with renames taken out: a rename is reported once, as a rename. */
export function netOfRenames(plan, renamed = []) {
  const to = new Set(renamed.map((r) => r.skill.dir));
  const from = new Set(renamed.map((r) => r.from));
  return { added: plan.added.filter((s) => !to.has(s.dir)), removed: plan.removed.filter((d) => !from.has(d)) };
}

/** How held skills are named in public: by sheetId, never by slug (e). A held skill may be a client
 *  build marked public by mistake, and its slug would name the client. One without a sheetId is
 *  counted; promote it by slug from the workbench's own export log, which is private. */
export function heldWords(held) {
  const ids = held.map((s) => s.sheetId).filter(Boolean);
  const unnumbered = held.length - ids.length;
  return unnumbered ? [...ids, `${plural(unnumbered, 'skill')} with no sheetId`] : ids;
}

export function commitMessage({ manifest, kept, plan, held, renamed = [], rewoundFrom = null }) {
  const slugs = (entries) => entries.map((s) => s.slug).join(', ');
  const { added, removed } = netOfRenames(plan, renamed);
  const lines = [];
  if (added.length) lines.push(`Added: ${slugs(added)}`);
  if (renamed.length) lines.push(`Renamed: ${renamedWords(renamed).join(', ')}`);
  if (plan.changed.length) lines.push(`Changed: ${slugs(plan.changed)}`);
  if (removed.length) lines.push(`Removed: ${removed.map((d) => path.posix.basename(d)).join(', ')}`);
  if (plan.loose) lines.push(`Removed ${plural(plan.loose, 'file')} outside every skill folder`);
  if (held.length) lines.push(`Held until promoted: ${heldWords(held).join(', ')}`);
  if (rewoundFrom) lines.push(`Rewound from ${rewoundFrom.slice(0, 7)}, dispatched with allow_rewind`);
  return [
    `export: ${plural(kept.length, 'skill')} from ${manifest.workbench_sha.slice(0, 7)}`,
    '',
    ...(lines.length ? [...lines, ''] : []),
    `Workbench-Commit: ${manifest.workbench_sha}`,
    '',
  ].join('\n');
}

/** `old-folder → new-slug` for each rename. */
export const renamedWords = (renamed) => renamed.map((r) => `${path.posix.basename(r.from)} → ${r.skill.slug}`);

/** Commit as the Actions bot and push plainly. A rejected push is a refusal, so nothing is posted. */
export function commitAndPush(shelfRoot, message, { allowEmpty = false } = {}) {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'shelf-commit-')), 'message');
  fs.writeFileSync(file, message);
  const env = {
    ...process.env,
    GIT_AUTHOR_NAME: BOT.name,
    GIT_AUTHOR_EMAIL: BOT.email,
    GIT_COMMITTER_NAME: BOT.name,
    GIT_COMMITTER_EMAIL: BOT.email,
  };
  const args = ['-c', 'commit.gpgsign=false', 'commit', '-q', '--no-verify', ...(allowEmpty ? ['--allow-empty'] : []), '-F', file];
  git(shelfRoot, args, { env });
  const sha = git(shelfRoot, ['rev-parse', 'HEAD']).trim();
  try {
    git(shelfRoot, ['push', '-q']);
  } catch (err) {
    refuse(`git push was rejected, so nothing is posted: ${String(err.stderr || err.message).trim()}`);
  }
  return sha;
}

// ── j. post ──────────────────────────────────────────────────────────────────

/** The shelf-v1 body, keys in the contract's order; allow_shrink only when dispatched with it. */
export function buildBody({ manifest, prune, allowShrink, rows }) {
  const body = { format: 'shelf-v1', repo_url: SHELF_URL, prune };
  if (allowShrink) body.allow_shrink = true;
  body.workbench_sha = manifest.workbench_sha;
  body.workbench_committed_at = manifest.workbench_committed_at;
  body.skills = rows;
  return JSON.stringify(body);
}

export const signature = (body, secret) => crypto.createHmac('sha256', secret).update(body, 'utf8').digest('hex');

/**
 * The site's answer, as this public log may show it: the status, the counts and the error word.
 * Never the reply itself: its would_prune and pruned name the live rows this body does not carry,
 * which are team or demoted skills, and no team skill's name reaches this log (SKB-038 decision 3).
 */
export function describeAnswer(status, text) {
  let reply = null;
  try {
    reply = JSON.parse(text);
  } catch {
    // not JSON: described by its size alone below
  }
  if (!isObject(reply)) return `${status} (a reply that is not a JSON object, ${plural(Buffer.byteLength(text), 'byte')})`;
  const parts = [String(status)];
  for (const key of ['upserted', 'unchanged']) if (Number.isInteger(reply[key])) parts.push(`${key} ${reply[key]}`);
  for (const key of ['would_prune', 'pruned']) if (Array.isArray(reply[key])) parts.push(`${key} ${reply[key].length}`);
  if (typeof reply.error === 'string') parts.push(`error "${reply.error.slice(0, 200)}"`);
  if (typeof reply.newest_applied === 'string') parts.push(`newest_applied ${reply.newest_applied.slice(0, 40)}`);
  return parts.join(' · ');
}

export async function postToSite({ url, body, secret, sourceSha, fetchImpl }) {
  let res;
  try {
    res = await fetchImpl(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Zynkr-Signature': signature(body, secret),
        'X-Zynkr-Source-Sha': sourceSha,
      },
      body,
    });
  } catch (err) {
    refuse(`the post to ${url} failed: ${err.message}`);
  }
  const text = await res.text();
  if (!res.ok) refuse(`${url} answered ${describeAnswer(res.status, text)}`);
  return { status: res.status, text };
}

// ── the run ──────────────────────────────────────────────────────────────────

function summarize(env, lines) {
  if (!env.GITHUB_STEP_SUMMARY) return;
  fs.appendFileSync(env.GITHUB_STEP_SUMMARY, `${lines.join('\n')}\n`);
}

const ORDER_WORDS = {
  first: 'the first export',
  identical: 'the same workbench commit as the last export',
  ahead: 'newer than the last export',
  behind: 'older than the last export',
  diverged: 'not a descendant of the last export',
  unrelated: 'not comparable with the last export, whose commit the workbench no longer holds',
};

/** The orders that rewind the shelf: taken only when dispatched with allow_rewind. */
const REWINDS = new Set(['diverged', 'unrelated']);

/**
 * Steps a–j. Resolves to { outcome: 'dry-run' | 'behind' | 'published', … }; a failed check
 * rejects with a Refusal before anything is pushed or posted.
 */
export async function publish(opts, { fetchImpl = globalThis.fetch, env = process.env, log = console.log } = {}) {
  const prune = pruneValue(opts.event, opts.prune);
  const siteUrl = env.SITE_SYNC_URL || SITE_SYNC_URL;
  const secret = env.SKILLS_SYNC_HMAC_SECRET;
  if (!opts.dryRun && !secret) refuse('the secret SKILLS_SYNC_HMAC_SECRET is not set (the export environment holds it)');
  if (!opts.dryRun && new URL(siteUrl).protocol !== 'https:') refuse('SITE_SYNC_URL must be an https URL');

  const stageRoot = path.join(opts.stage, 'stage');
  if (opts.seedFail) seedFail(stageRoot); // a
  const { manifest, payload } = readStage(stageRoot); // b
  checkRunSha(opts.run, manifest, opts.dryRun); // b
  const shelfHas = (p) => isFile(path.join(opts.shelf, p));
  const owners = checkMarks(stageRoot, manifest, shelfHas); // c
  const rows = derivePayload(payload, manifest, owners, shelfHas); // d
  const shelf = shelfSkills(opts.shelf);
  const shelfDirs = shelf.map((h) => h.dir);
  const staged = manifest.skills.map((s) => {
    const { fm } = owners.get(s.dir);
    return { ...s, sheetId: sheetIdOf(fm), renamedFrom: renamedFromOf(fm) };
  });
  const promotion = planPromotion(staged, shelf, opts.promote); // e
  checkShrink(promotion.kept.length, shelfDirs.length, opts.allowShrink); // f
  const last = lastWorkbenchCommit(opts.shelf);
  const order = await ordering({ last, next: manifest.workbench_sha, token: env.WORKBENCH_READ_TOKEN, fetchImpl }); // g
  if (order === 'diverged' && !opts.allowRewind) {
    refuse(
      `the stage's workbench commit ${manifest.workbench_sha.slice(0, 7)} is not a descendant of the last export ` +
        `${last.slice(0, 7)} (a rewritten workbench main?). Dispatch with allow_rewind if that is intended.`,
    );
  }
  if (order === 'unrelated' && !opts.allowRewind) {
    refuse(
      `the last export ${last.slice(0, 7)} shares no history with the stage's workbench commit ` +
        `${manifest.workbench_sha.slice(0, 7)}, or no longer exists in the workbench (a rewritten main?). ` +
        'Dispatch with allow_rewind if that is intended.',
    );
  }

  const heldDirs = new Set(promotion.held.map((s) => s.dir));
  const posted = rows.filter((r) => !heldDirs.has(r.dir)).map((r) => r.row);
  const body = buildBody({ manifest, prune, allowShrink: opts.allowShrink, rows: posted });
  const plan = planMirror(opts.shelf, manifest, promotion.kept, shelfDirs);
  const net = netOfRenames(plan, promotion.renamed);
  const counts =
    `added ${net.added.length}` +
    (promotion.renamed.length ? ` · renamed ${promotion.renamed.length}` : '') +
    ` · changed ${plan.changed.length} · removed ${net.removed.length}`;
  const slugsOf = (entries) => entries.map((s) => s.slug);

  const short = manifest.workbench_sha.slice(0, 7);
  log(`stage: workbench ${short} (committed ${manifest.workbench_committed_at}), ${plural(manifest.skills.length, 'skill')}, ${plural(rows.length, 'row')}`);
  log(`order: ${ORDER_WORDS[order]}${last && order !== 'identical' ? ` (${last.slice(0, 7)})` : ''}`);
  if (promotion.promoted.length) log(`promoted: ${slugsOf(promotion.promoted).join(', ')}`);
  if (promotion.renamed.length) log(`kept under a new name (renamed_from, same sheetId): ${renamedWords(promotion.renamed).join(', ')}`);
  if (promotion.held.length) log(`held until promoted: ${heldWords(promotion.held).join(', ')}`);
  if (promotion.unmatched) log(`note: promote names ${plural(promotion.unmatched, 'sheetId or slug', 'sheetIds or slugs')} that the stage does not hold`);

  const summary = [
    '### Export to the shelf',
    '',
    `- Workbench commit \`${short}\`, committed ${manifest.workbench_committed_at}: ${ORDER_WORDS[order]}`,
    `- Prune: \`${prune}\``,
    `- Skills on the shelf after this run: ${promotion.kept.length} (${counts})`,
  ];
  if (promotion.renamed.length) {
    summary.push(`- Kept under a new name (renamed_from, same sheetId): ${renamedWords(promotion.renamed).map((w) => `\`${w}\``).join(', ')}`);
  }
  if (promotion.held.length) {
    summary.push(
      `- **Held until promoted** (dispatch with \`promote\` and the sheetId): ${heldWords(promotion.held).map((s) => `\`${s}\``).join(', ')}`,
    );
  }

  if (opts.dryRun) {
    const planJson = {
      dry_run: true,
      workbench_sha: manifest.workbench_sha,
      order,
      prune,
      copy: promotion.kept.map((s) => s.dir),
      added: slugsOf(net.added),
      changed: slugsOf(plan.changed),
      removed: net.removed,
      held: heldWords(promotion.held),
      promoted: slugsOf(promotion.promoted),
      renamed: promotion.renamed.map((r) => ({ from: r.from, to: r.skill.dir })),
      body: JSON.parse(body),
    };
    log(JSON.stringify(planJson, null, 2));
    summarize(env, [...summary, '- Dry run: nothing changed, nothing posted', '']);
    return { outcome: 'dry-run', order, prune, plan, promotion, body };
  }

  if (order === 'behind') {
    log('nothing to do: the shelf already carries a newer workbench commit');
    summarize(env, [...summary, '- Nothing to do: the shelf already carries a newer workbench commit', '']);
    return { outcome: 'behind', order, prune, plan, promotion };
  }

  mirror(opts.shelf, stageRoot, plan.desired); // i
  let commit = null;
  const changed = stageIndex(opts.shelf, plan.desired);
  // An accepted rewind is recorded even when the tree is unchanged: without the new trailer every
  // later run would compare against the abandoned commit and go red as diverged again.
  const rewound = REWINDS.has(order);
  if (changed || rewound) {
    const message = commitMessage({
      manifest,
      kept: promotion.kept,
      plan,
      held: promotion.held,
      renamed: promotion.renamed,
      rewoundFrom: rewound ? last : null,
    });
    commit = commitAndPush(opts.shelf, message, { allowEmpty: !changed });
    log(`shelf: ${counts}; pushed ${commit.slice(0, 7)}`);
  } else log('shelf: no change to commit');

  const answer = await postToSite({ url: siteUrl, body, secret, sourceSha: manifest.workbench_sha, fetchImpl }); // j
  const described = describeAnswer(answer.status, answer.text);
  log(`site: ${described}`);
  summarize(env, [
    ...summary,
    `- Shelf: ${commit ? `pushed \`${commit.slice(0, 7)}\`` : 'no change to commit'}`,
    `- Site: ${described}`,
    '',
  ]);
  return { outcome: 'published', order, prune, plan, promotion, body, commit, answer };
}

export async function main(argv = process.argv.slice(2), deps = {}) {
  const env = deps.env ?? process.env;
  const error = deps.error ?? console.error;
  try {
    let values;
    try {
      ({ values } = parseArgs({
        args: argv,
        options: {
          stage: { type: 'string' },
          shelf: { type: 'string' },
          event: { type: 'string' },
          run: { type: 'string' },
          prune: { type: 'string' },
          promote: { type: 'string' },
          'allow-shrink': { type: 'boolean' },
          'allow-rewind': { type: 'boolean' },
          'seed-fail': { type: 'boolean' },
          'dry-run': { type: 'boolean' },
        },
      }));
    } catch (err) {
      refuse(`${err.message}\n${USAGE}`);
    }
    if (!values.stage || !values.shelf || !values.event) refuse(USAGE);
    if (values.run && !isFile(path.resolve(values.run))) refuse(`--run names no file: ${values.run}`);
    await publish(
      {
        stage: path.resolve(values.stage),
        shelf: path.resolve(values.shelf),
        event: values.event,
        run: values.run ? readJson(path.resolve(values.run), 'run.json') : undefined,
        prune: values.prune,
        promote: values.promote ?? '',
        allowShrink: Boolean(values['allow-shrink']),
        allowRewind: Boolean(values['allow-rewind']),
        seedFail: Boolean(values['seed-fail']),
        dryRun: Boolean(values['dry-run']),
      },
      { ...deps, env },
    );
    return 0;
  } catch (err) {
    const message = err instanceof Refusal ? err.message : `unexpected failure: ${err.message}`;
    error(env.GITHUB_ACTIONS === 'true' ? `::error::${annotation(message)}` : `refused: ${message}`);
    summarize(env, ['### Export refused', '', message, '']);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main();
}
