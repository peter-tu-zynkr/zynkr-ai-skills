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
 *      The body's order key (`workbench_committed_at`) is this run's own start, read from GitHub's
 *      API — never the stage's claimed commit time, which a rewritten stage job could set to
 *      anything (ATL-113 Part D).
 *   k. SHELF_ATLAS (ATL-113 Part D, rulings D-138…D-142), a repository variable:
 *        off      — (a)–(j) as above. Unset means off until the switch (enforce.mjs
 *                   DEFAULT_ATLAS_MODE); after it, unset means enforce and off is set on purpose.
 *        report   — first rehearses: asks Atlas, plans what enforce would publish, keep, hold and
 *                   remove, builds every row from the staged files and prints how many differ from
 *                   today's (the parity check); then (a)–(j) exactly as off. Red if Atlas could not
 *                   be asked.
 *        enforce  — only what Atlas lists leaves the team, byte for byte (enforce.mjs rules 1–7);
 *                   every row zynkr.ai gets is built from the files the shelf holds (listing.mjs);
 *                   promote is retired. Atlas unreachable, or no usable stage: one side is enough to
 *                   remove, nothing new is published, the rows are posted, and the run is red.
 *
 * Any refusal exits 1 before anything is pushed or posted (a failed post after a push exits 1
 * too; the next run posts again). This repo's logs are public, so until the marks are checked (c)
 * a refusal gives counts, never a path: a stage that went wrong may carry a team skill, and its
 * name must not reach this log. After (c) a refusal names a file the shelf already publishes by its
 * path, and one new to the shelf by its sheetId or not at all (wordsFor; stageIndex counts them): it
 * comes before the hold (e), and a new file may belong to a client build marked public by mistake.
 * Under enforce a folder is named by its slug only when it is published or removed, and by its
 * sheetId when it is kept or waits; Atlas's answer is never printed, nor any count of it.
 * Rebuild the stage in the workbench to see which files (`npx tsx scripts/export-shelf.ts --out <dir>`).
 *
 *   node tools/publish.mjs --stage <dir holding stage/> --shelf <this checkout>
 *        --event schedule|workflow_dispatch --run <run.json> [--prune report|true]
 *        [--promote <sheetIds or slugs, comma-separated>|all] [--allow-shrink] [--allow-rewind]
 *        [--seed-fail] [--seed-atlas unreachable|wrong_audience] [--dry-run]
 *
 * Env: WORKBENCH_READ_TOKEN (the compare call), SKILLS_SYNC_HMAC_SECRET, SITE_SYNC_URL
 * (default https://zynkr.ai/api/skills/sync), GITHUB_STEP_SUMMARY (optional), SHELF_ATLAS,
 * GITHUB_RUN_ID and GITHUB_TOKEN (this run's start time), ACTIONS_ID_TOKEN_REQUEST_URL and
 * ACTIONS_ID_TOKEN_REQUEST_TOKEN (the OIDC token Atlas checks; GitHub sets them).
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
  SHELF_REPO,
  SHELF_URL,
  SITE_DETAILS_URL,
  SITE_SYNC_URL,
  WORKBENCH,
  annotation,
  githubHeaders,
  httpHint,
  plural,
  refuse,
  unexpectedWords,
} from './common.mjs';
import { ATLAS_AUDIENCE, ATLAS_SHELF_URL, askAtlas, atlasWords } from './atlas.mjs';
import { atlasMode, checkedId, idWords, planEnforce, planWords, slugWords } from './enforce.mjs';
import {
  ListingError,
  deriveFolder,
  finishRows,
  folderView,
  isoDay,
  parity,
  readFrozen,
  readSiteFirstSeen,
  shelfFields,
  sortRows,
  textHash,
} from './listing.mjs';
import { MANIFEST_NAMES, NAME_RE, OVERRIDE_RE, nameOf, parseFrontmatter, renamedFromOf, sheetIdOf } from './manifest.mjs';
import { planPromotion } from './promotion.mjs';
import { treeId } from './tree.mjs';

export { NAME_RE, OVERRIDE_RE, parseFrontmatter, planPromotion, renamedFromOf, sheetIdOf };

const SHA_RE = /^[0-9a-f]{40}$/;
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const MODES = new Set(['100644', '100755']);
const KINDS = new Set(['skill', 'orchestrator', 'subagent']);
const STAGE_ENTRIES = ['manifest.json', 'payload.json', 'skills'];
const BOT = { name: 'github-actions[bot]', email: '41898282+github-actions[bot]@users.noreply.github.com' };
const FROZEN_FILE = 'listing/frozen-text.json';
/** A seeded dispatch's door: `.invalid` never resolves (RFC 2606), so the ask fails as unreachable. */
const SEED_UNREACHABLE = 'https://atlas.invalid/api/shelf';
const SEEDS = new Set(['unreachable', 'wrong_audience']);
/** A committer's clock may run a little ahead of GitHub's; a stage's claimed commit time may not run further. */
const CLOCK_SKEW_MS = 5 * 60 * 1000;
/** More skill folders than any stage holds (94 on 2026-10-15): a stage past this is refused unread. */
export const MAX_STAGE_FOLDERS = 5000;
const USAGE =
  'usage: publish.mjs --stage <dir holding stage/> --shelf <checkout> --event schedule|workflow_dispatch ' +
  '--run <run.json> [--prune report|true] [--promote a,b|all] [--allow-shrink] [--allow-rewind] [--seed-fail] ' +
  '[--seed-atlas unreachable|wrong_audience] [--dry-run]';

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

/**
 * The folder in `dirs` (a Set of folders that never nest) that holds `p`: the one proper prefix of it
 * that ends at a "/", or null. Linear in the path's depth, so a lookup per file never costs a scan of
 * every folder.
 */
function folderOf(p, dirs) {
  for (let i = p.indexOf('/'); i !== -1; i = p.indexOf('/', i + 1)) {
    const prefix = p.slice(0, i);
    if (dirs.has(prefix)) return prefix;
  }
  return null;
}

/** Map(folder → its files [{ path relative to the folder, mode, sha }]) for folders that never nest. */
function groupByFolder(files, dirs) {
  const out = new Map([...dirs].map((d) => [d, []]));
  for (const f of files) {
    const d = folderOf(f.path, dirs);
    if (d) out.get(d).push({ path: f.path.slice(d.length + 1), mode: f.mode, sha: f.sha });
  }
  return out;
}

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
  if (manifest.skills.length > MAX_STAGE_FOLDERS) {
    refuse(`manifest.json lists ${manifest.skills.length} skill folders, more than the ${MAX_STAGE_FOLDERS} a stage may hold`);
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
  // A repeated folder, or one inside another: a Set and each folder's own prefixes, never every pair.
  const dirs = new Set();
  for (const s of manifest.skills) {
    if (dirs.has(s.dir)) refuse('manifest.skills repeats a folder or nests one inside another');
    dirs.add(s.dir);
  }
  for (const d of dirs) if (folderOf(d, dirs)) refuse('manifest.skills repeats a folder or nests one inside another');
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

  const dirs = new Set(manifest.skills.map((s) => s.dir));
  const loose = [...listed.keys()].filter((p) => !folderOf(p, dirs)).length;
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

/**
 * (b, under SHELF_ATLAS): a stage may not claim a workbench commit time later than the run that built
 * it was created (run.json's created_at, which fetch-stage.mjs took from GitHub's API). Five minutes
 * are allowed for a committer's clock running ahead.
 */
export function checkCommitTime(run, manifest) {
  const created = Date.parse(run?.created_at);
  if (Number.isNaN(created)) refuse("run.json has no created_at, so the stage's commit time cannot be checked");
  if (Date.parse(manifest.workbench_committed_at) > created + CLOCK_SKEW_MS) {
    refuse('the stage claims a workbench commit time later than the run that built it');
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

/** (c): returns Map(dir → { entry, fm }) once every owning manifest is marked public. */
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
  const fields = shelfFields({ sourcePath: rec.source_path, kind: rec.kind, installable: entry.installable, fm });
  if (!fields) {
    refuse(`${wordsFor(shelfHas, entry.manifest, sheetIdOf(fm))}: install_command must be an "npx skills add https://github.com/<owner>/<repo> --skill <name>" line`);
  }
  return fields;
}

/** (d): [{ dir, row }] — each row with its owning folder and its derived fields. A refusal names a row
 *  the shelf doesn't publish yet by its id, never its path or slug (wordsFor). */
export function derivePayload(payload, manifest, owners, shelfHas = () => false) {
  if (!Array.isArray(payload)) refuse('payload.json is not an array');
  const files = new Set(manifest.files.map((f) => f.path));
  const dirs = new Set(owners.keys());
  const slugs = new Set();
  const rows = payload.map((rec, i) => {
    if (!isObject(rec) || typeof rec.source_path !== 'string' || !files.has(rec.source_path)) {
      refuse(`payload[${i}].source_path is not a file in the stage`);
    }
    // The stage's folders never nest (checkManifestShape), so a file sits in one folder or none.
    const owner = folderOf(rec.source_path, dirs);
    const hits = owner ? [owner] : [];
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

/** The refusal for a rewind not dispatched with allow_rewind (g). */
function refuseRewind(order, last, next) {
  if (order === 'diverged') {
    refuse(
      `the stage's workbench commit ${next.slice(0, 7)} is not a descendant of the last export ` +
        `${last.slice(0, 7)} (a rewritten workbench main?). Dispatch with allow_rewind if that is intended.`,
    );
  }
  refuse(
    `the last export ${last.slice(0, 7)} shares no history with the stage's workbench commit ` +
      `${next.slice(0, 7)}, or no longer exists in the workbench (a rewritten main?). ` +
      'Dispatch with allow_rewind if that is intended.',
  );
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
  const keptDirs = new Set(kept.map((s) => s.dir));
  const desired = new Map(manifest.files.filter((f) => folderOf(f.path, keptDirs)).map((f) => [f.path, f]));
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
  // The kept folders that hold a path that differs, found per path (folders never nest), not per pair.
  const differing = new Set();
  for (const p of new Set([...desired.keys(), ...current.keys()])) {
    const d = differs(p) ? folderOf(p, keptDirs) : null;
    if (d) differing.add(d);
  }
  return {
    desired,
    added: kept.filter((s) => !onShelf.has(s.dir)),
    changed: kept.filter((s) => onShelf.has(s.dir) && differing.has(s.dir)),
    removed: shelfDirs.filter((d) => !keptDirs.has(d)),
    loose: [...current.keys()].filter((p) => !desired.has(p) && !folderOf(p, onShelf)).length,
  };
}

/**
 * Make <shelf>/skills hold exactly `desired`. A file whose entry says `from: 'shelf'` is the shelf's
 * own and stays where it is (SHELF_ATLAS keeps a folder as the shelf has it); every other one is
 * copied from the stage with its mode.
 */
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
    if (f.from === 'shelf') continue;
    const dst = path.join(shelfRoot, p);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(path.join(stageRoot, p), dst);
    fs.chmodSync(dst, f.mode === '100755' ? 0o755 : 0o644);
  }
  if (isDir(root) && fs.readdirSync(root).length === 0) fs.rmdirSync(root);
}

/** git's index under skills/: Map(path → { mode, sha }), the bytes git holds, after any attribute. */
function readIndex(shelfRoot) {
  const index = new Map();
  for (const line of git(shelfRoot, ['ls-files', '-s', '-z', '--', 'skills']).split('\0').filter(Boolean)) {
    const [meta, p] = line.split('\t');
    const [mode, sha] = meta.split(' ');
    index.set(p, { mode, sha });
  }
  return index;
}

/** The paths where the index and `desired` disagree: missing on one side, or another sha or mode. */
const indexMismatches = (index, desired) =>
  [...new Set([...index.keys(), ...desired.keys()])].filter((p) => {
    const a = index.get(p);
    const b = desired.get(p);
    return !a || !b || a.mode !== b.mode || a.sha !== b.sha;
  });

/**
 * Stage skills/ in git's index and prove the index equals the stage (a .gitattributes filter in a
 * skill folder could otherwise rewrite bytes on the way in). Returns whether anything changed.
 */
export function stageIndex(shelfRoot, desired) {
  git(shelfRoot, ['rm', '-r', '-q', '--cached', '--ignore-unmatch', '--', 'skills']);
  // -f: a skill's own .gitignore must not keep one of its tracked files off the shelf.
  if (isDir(path.join(shelfRoot, 'skills'))) git(shelfRoot, ['add', '-f', '--', 'skills']);
  const off = indexMismatches(readIndex(shelfRoot), desired);
  if (off.length) {
    // Only a path the shelf already published is named: one new to it may belong to a client build
    // marked public by mistake (wordsFor; workbench SKB-054, review round 5).
    let published = new Set();
    try {
      published = new Set(git(shelfRoot, ['ls-tree', '-r', '-z', '--name-only', 'HEAD', '--', 'skills']).split('\0').filter(Boolean));
    } catch {
      // a shelf with no commit yet published nothing
    }
    const named = off.filter((p) => published.has(p)).slice(0, 5);
    const unnamed = off.filter((p) => !published.has(p)).length;
    refuse(
      `after the mirror, git's index differs from the stage at ${plural(off.length, 'path')}` +
        `${named.length ? ` (${named.join(', ')})` : ''}${unnamed ? `, ${unnamed} of them new to the shelf and unnamed here` : ''}` +
        ': a .gitattributes or line-ending rule in a skill folder?',
    );
  }
  return git(shelfRoot, ['diff', '--cached', '--name-only', '--', 'skills']).trim() !== '';
}

/**
 * Under SHELF_ATLAS=enforce: stage skills/ as stageIndex does, then put the folders the shelf keeps
 * back to HEAD's own entries (`git reset HEAD -- <folder>`), so a kept folder is exactly the blobs
 * the shelf already holds, whatever its attributes made of the working tree on checkout. Returns the
 * paths where the index differs from `desired` and refuses nothing: the caller sets the published
 * folders they sit in aside (git would change their bytes) and plans again.
 */
export function stageIndexEnforce(shelfRoot, desired, keptDirs) {
  git(shelfRoot, ['rm', '-r', '-q', '--cached', '--ignore-unmatch', '--', 'skills']);
  if (isDir(path.join(shelfRoot, 'skills'))) git(shelfRoot, ['add', '-f', '--', 'skills']);
  if (keptDirs.length) git(shelfRoot, ['reset', '-q', 'HEAD', '--', ...keptDirs]);
  return indexMismatches(readIndex(shelfRoot), desired);
}

/** The mirror's adds and removes with renames taken out: a rename is reported once, as a rename. */
export function netOfRenames(plan, renamed = []) {
  const to = new Set(renamed.map((r) => r.skill.dir));
  const from = new Set(renamed.map((r) => r.from));
  return { added: plan.added.filter((s) => !to.has(s.dir)), removed: plan.removed.filter((d) => !from.has(d)) };
}

/** How held skills are named in public: by sheetId, never by slug (e). A held skill may be a client
 *  build marked public by mistake, and its slug would name the client. One without a checkable sheetId
 *  is counted; promote it by slug from the workbench's own export log, which is private. */
export function heldWords(held) {
  const ids = held.map((s) => checkedId(s.sheetId)).filter(Boolean);
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

/** The shelf-v1 body, keys in the contract's order; allow_shrink only when it is set. `committedAt` is
 *  the order key: this run's own start (runStartedAt), never a time the stage claims. */
export function buildBody({ workbenchSha, committedAt, prune, allowShrink, rows }) {
  const body = { format: 'shelf-v1', repo_url: SHELF_URL, prune };
  if (allowShrink) body.allow_shrink = true;
  body.workbench_sha = workbenchSha;
  body.workbench_committed_at = committedAt;
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

/**
 * (j): this run's own start time, from GitHub's API (the shelf's run, read with the job's token):
 * the order key of every post. The site refuses a body older than the newest it applied, so a run
 * that started later always wins, whatever the stage claims.
 */
export async function runStartedAt({ env, fetchImpl }) {
  const id = String(env.GITHUB_RUN_ID ?? '');
  if (!/^\d+$/.test(id)) refuse("this run's start time cannot be read outside GitHub Actions (GITHUB_RUN_ID is not set)");
  const headers = env.GITHUB_TOKEN
    ? githubHeaders(env.GITHUB_TOKEN)
    : { Accept: 'application/vnd.github+json', 'User-Agent': 'zynkr-ai-skills-export' };
  let res;
  try {
    res = await fetchImpl(`https://api.github.com/repos/${SHELF_REPO}/actions/runs/${id}`, { headers });
  } catch (err) {
    refuse(`reading this run's start time failed: ${err.message}`);
  }
  if (!res.ok) refuse(`reading this run's start time answered ${res.status}`);
  let run;
  try {
    run = await res.json();
  } catch {
    refuse("GitHub's answer for this run is not JSON");
  }
  const at = run?.run_started_at;
  if (typeof at !== 'string' || !ISO_RE.test(at) || Number.isNaN(Date.parse(at))) refuse('GitHub gave no start time for this run');
  return at;
}

// ── k. SHELF_ATLAS: the shelf, the stage and Atlas, read for the rule ────────

/** listing/frozen-text.json from this checkout (D-142), or none. A malformed file refuses the run. */
export function loadFrozen(shelfRoot) {
  const file = path.join(shelfRoot, FROZEN_FILE);
  if (!isFile(file)) return null;
  try {
    return readFrozen(readJson(file, FROZEN_FILE));
  } catch (err) {
    if (err instanceof ListingError) refuse(err.message);
    throw err;
  }
}

/**
 * The shelf as it is before the run: its folders (shelfSkills, which never nest) with their files,
 * tree ids and a view for the listing build; every file it holds; and how many sit in no folder.
 * A file's sha and mode are git's, from the index the checkout made (the committed blob), never a
 * hash of the working tree: a folder's .gitattributes (`eol=crlf`, say) can make a checkout write
 * other bytes than the shelf holds. Its text is read from the working tree, which differs from the
 * blob only in line ends, and the listing build reads line ends alike.
 */
export function readShelfState(shelfRoot) {
  const files = [...readIndex(shelfRoot)].map(([p, f]) => ({ path: p, sha: f.sha, mode: f.mode }));
  const indexed = shelfSkills(shelfRoot);
  const dirs = new Set(indexed.map((h) => h.dir));
  const byFolder = groupByFolder(files, dirs);
  // A folder with no file in the index is nothing the shelf holds (the mirror clears it).
  const found = indexed.filter((h) => byFolder.get(h.dir).length > 0);
  const folders = found.map((h) => {
    const entries = byFolder.get(h.dir);
    return {
      ...h,
      files: entries,
      tree: treeId(entries),
      view: folderView(h.dir, entries.map((e) => e.path), (rel) => fs.readFileSync(path.join(shelfRoot, h.dir, rel), 'utf8')),
    };
  });
  const held = new Set(found.map((h) => h.dir));
  return { folders, files, loose: files.filter((f) => !folderOf(f.path, held)).length };
}

/** A staged folder for the rule: its files, its recomputed tree, its manifest's own line, a view. */
function stageFolder(stageRoot, entry, entries) {
  const fm = parseFrontmatter(fs.readFileSync(path.join(stageRoot, entry.manifest), 'utf8'));
  return {
    dir: entry.dir,
    files: entries,
    tree: treeId(entries),
    name: nameOf(fm),
    sheetId: sheetIdOf(fm),
    renamedFrom: renamedFromOf(fm),
    view: folderView(entry.dir, entries.map((e) => e.path), (rel) => fs.readFileSync(path.join(stageRoot, entry.dir, rel), 'utf8')),
  };
}

/**
 * The stage, read for the rule. { usable: true, manifest, payload, order, last, folders, stageRoot }
 * or { usable: false, why: 'none' | 'refused' | 'stale', words }. Whatever goes wrong while it is read
 * — a refusal, an unreadable file, anything — sets the stage aside and never stops the run: the
 * removals Atlas asks for still go (rule 5). An unexpected error is described by its kind and code
 * only, never its message, which could name a staged path new to the shelf.
 */
export async function loadStageForAtlas(opts, { env, fetchImpl }) {
  const stageRoot = path.join(opts.stage, 'stage');
  if (opts.run === undefined || !isDir(stageRoot)) return { usable: false, why: 'none', words: 'no stage was fetched' };
  try {
    const { manifest, payload } = readStage(stageRoot);
    checkRunSha(opts.run, manifest);
    checkCommitTime(opts.run, manifest);
    const last = lastWorkbenchCommit(opts.shelf);
    const order = await ordering({ last, next: manifest.workbench_sha, token: env.WORKBENCH_READ_TOKEN, fetchImpl });
    if (REWINDS.has(order) && !opts.allowRewind) refuseRewind(order, last, manifest.workbench_sha);
    if (order === 'behind') {
      return { usable: false, why: 'stale', words: `the stage (${manifest.workbench_sha.slice(0, 7)}) is older than the last export (${last.slice(0, 7)})`, manifest, last };
    }
    const byFolder = groupByFolder(manifest.files, new Set(manifest.skills.map((s) => s.dir)));
    const folders = manifest.skills.map((entry) => stageFolder(stageRoot, entry, byFolder.get(entry.dir)));
    return { usable: true, manifest, payload, order, last, folders, stageRoot };
  } catch (err) {
    if (err instanceof Refusal) return { usable: false, why: 'refused', words: err.message };
    return { usable: false, why: 'refused', words: `the stage could not be read (${unexpectedWords(err)})` };
  }
}

/** Ask Atlas, or a seeded dispatch's wrong door or wrong audience (AC-18, AC-19 red proofs). The
 *  answer carries the seed, so the run's own words can say a failure was seeded. */
async function askAtlasFor(opts, { env, fetchImpl }) {
  const url = opts.seedAtlas === 'unreachable' ? SEED_UNREACHABLE : env.ATLAS_SHELF_URL || ATLAS_SHELF_URL;
  if (new URL(url).protocol !== 'https:') refuse('ATLAS_SHELF_URL must be an https URL');
  const audience = opts.seedAtlas === 'wrong_audience' ? `${ATLAS_AUDIENCE}-seed` : ATLAS_AUDIENCE;
  return { ...(await askAtlas({ env, fetchImpl, url, audience })), seed: opts.seedAtlas || '' };
}

const stageLine = (stage) =>
  stage.usable
    ? `stage: workbench ${stage.manifest.workbench_sha.slice(0, 7)}, ${plural(stage.folders.length, 'skill')} (${ORDER_WORDS[stage.order]})`
    : stage.why === 'none'
      ? 'stage: none — no stage was fetched (see the step before)'
      : stage.why === 'stale'
        ? `stage: set aside — ${stage.words}`
        : `stage: refused — ${stage.words}`;

const atlasLine = (atlas) => (atlas.ok ? 'atlas: asked; it answered' : `atlas: could not be asked — ${atlasWords(atlas, atlas.seed)}`);

/** The plan in words, for the log and the summary (enforce.mjs planWords). */
function planLines(plan, words, prefix) {
  const lines = [`${prefix}${words.counts}`];
  if (words.added.length) lines.push(`  new on the shelf: ${words.added.join(', ')}`);
  if (words.changed.length) lines.push(`  changed: ${words.changed.join(', ')}`);
  if (words.moved.length) lines.push(`  moved or renamed: ${words.moved.join(', ')}`);
  if (words.removed.length) lines.push(`  removed: ${words.removed.join(', ')}`);
  if (words.kept.length) lines.push(`  kept as the shelf has it (sheetId): ${words.kept.join(', ')}`);
  if (words.waiting.length) lines.push(`  waiting for Atlas (sheetId): ${words.waiting.join(', ')}`);
  if (words.reasons.length) lines.push(`  why kept or waiting: ${words.reasons.join(' · ')}`);
  if (plan.stageRefused) lines.push(`  the stage was set aside: ${plan.stageRefused}`);
  return lines;
}

/** Build a folder's rows, or null: `why` is the ListingError's phrase, or a fixed one for anything else. */
function rowsOf(view, opts) {
  try {
    return { built: deriveFolder(view, opts), why: null };
  } catch (err) {
    return { built: null, why: err instanceof ListingError ? err.message : 'an unexpected failure' };
  }
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
 * Steps a–k. Resolves to { outcome: 'dry-run' | 'behind' | 'published', … }; a failed check
 * rejects with a Refusal before anything is pushed or posted.
 */
export async function publish(opts, deps = {}) {
  const env = deps.env ?? process.env;
  const log = deps.log ?? console.log;
  const mode = atlasMode(env.SHELF_ATLAS);
  if (opts.seedAtlas && !SEEDS.has(opts.seedAtlas)) refuse('--seed-atlas must be unreachable or wrong_audience');
  if (mode.mode === 'enforce') return enforceRun(opts, deps, mode);
  if (mode.mode === 'off') {
    log(`atlas: off${mode.explicit ? ' (SHELF_ATLAS=off, set on purpose)' : ' (SHELF_ATLAS is not set)'} — the shelf publishes the stage as it did before Part D`);
    if (opts.seedAtlas) log('note: seed_atlas does nothing while SHELF_ATLAS is off');
    return publishAsToday(opts, deps);
  }
  // report: rehearse enforce first (it changes nothing), then publish as today.
  if (opts.seedFail) {
    const stageRoot = path.join(opts.stage, 'stage');
    if (isDir(stageRoot)) seedFail(stageRoot);
  }
  log('atlas: report — rehearsing what SHELF_ATLAS=enforce would do, then publishing as before');
  const rehearsal = await rehearse(opts, deps);
  for (const line of rehearsal.lines) log(line);
  summarize(env, ['### SHELF_ATLAS=report: the rehearsal', '', ...rehearsal.lines.map((l) => `- ${l.trim()}`), '']);
  const result = await publishAsToday({ ...opts, seedFail: false }, deps);
  if (rehearsal.failed) {
    refuse(`SHELF_ATLAS=report: ${rehearsal.failed}. The stage was published as before; under enforce this run would publish nothing new.`);
  }
  return { ...result, rehearsal };
}

/** (a)–(j): the publish as it was before Part D (SHELF_ATLAS off, and report's second half). */
async function publishAsToday(opts, { fetchImpl = globalThis.fetch, env = process.env, log = console.log, now = () => new Date() } = {}) {
  const prune = pruneValue(opts.event, opts.prune);
  const siteUrl = env.SITE_SYNC_URL || SITE_SYNC_URL;
  const secret = env.SKILLS_SYNC_HMAC_SECRET;
  if (!opts.dryRun && !secret) refuse('the secret SKILLS_SYNC_HMAC_SECRET is not set (the export environment holds it)');
  if (!opts.dryRun && new URL(siteUrl).protocol !== 'https:') refuse('SITE_SYNC_URL must be an https URL');
  if (opts.stageMissing) refuse('no stage was fetched (the download step failed; see it above), so nothing changed');

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
  if (REWINDS.has(order) && !opts.allowRewind) refuseRewind(order, last, manifest.workbench_sha);

  const heldDirs = new Set(promotion.held.map((s) => s.dir));
  const posted = rows.filter((r) => !heldDirs.has(r.dir)).map((r) => r.row);
  const bodyFor = (committedAt) =>
    buildBody({ workbenchSha: manifest.workbench_sha, committedAt, prune, allowShrink: opts.allowShrink, rows: posted });
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
    const body = bodyFor(now().toISOString());
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

  const body = bodyFor(await runStartedAt({ env, fetchImpl })); // j
  const answer = await postToSite({ url: siteUrl, body, secret, sourceSha: manifest.workbench_sha, fetchImpl });
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

/**
 * report's first half: everything enforce would read and decide, changing nothing. Never throws a
 * Refusal: `failed` says why the rehearsal could not finish, and makes the run red after it has
 * published as before.
 */
export async function rehearse(opts, { fetchImpl = globalThis.fetch, env = process.env, now = () => new Date() } = {}) {
  const lines = [];
  try {
    const today = isoDay(now());
    const frozen = loadFrozen(opts.shelf);
    // Atlas first, as enforce asks it: whatever the stage turns out to be, its answer is in hand.
    const atlas = await askAtlasFor(opts, { env, fetchImpl });
    const shelf = readShelfState(opts.shelf);
    const stage = await loadStageForAtlas(opts, { env, fetchImpl });
    lines.push(stageLine(stage));
    lines.push(atlasLine(atlas));
    if (atlas.claims) {
      lines.push(`atlas: this job's token, as the door reads it: ${Object.entries(atlas.claims).map(([k, v]) => `${k}=${v}`).join(' · ')}`);
    }
    const plan = planEnforce({ stage, shelf: shelf.folders, atlas, allowShrink: opts.allowShrink, frozen, today });
    lines.push(...planLines(plan, planWords(plan), 'report: enforce would '));
    if (plan.unbuildable.length) {
      lines.push(`report: ${plural(plan.unbuildable.length, 'folder')} the shelf would keep build no rows from their files: enforce would post nothing`);
    }

    if (stage.usable) {
      // The parity check: rows built from the staged files beside the rows this run posts as before.
      const built = [];
      const unbuilt = [];
      let frozenUsed = 0;
      const fileText = new Map();
      for (const s of stage.folders) {
        const r = rowsOf(s.view, { frozen, today });
        if (!r.built) {
          unbuilt.push(s.sheetId);
          continue;
        }
        built.push(...r.built.rows);
        frozenUsed += r.built.frozenUsed;
        for (const [p, t] of r.built.fileText) fileText.set(p, t);
      }
      let todays = null;
      try {
        const shelfHas = (p) => isFile(path.join(opts.shelf, p));
        const owners = checkMarks(stage.stageRoot, stage.manifest, shelfHas);
        todays = derivePayload(stage.payload, stage.manifest, owners, shelfHas).map((r) => r.row);
      } catch (err) {
        if (!(err instanceof Refusal)) throw err;
        lines.push('parity: the stage fails the checks it is published under today, so there is nothing to compare');
      }
      if (todays) {
        const p = parity(built, todays);
        const fields = [...p.fields].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).map(([f, n]) => `${f} ${n}`);
        lines.push(
          `parity: ${p.built} rows built from the staged files · ${p.matched} beside today's · ${p.differ.length} differ` +
            `${fields.length ? ` (${fields.join(' · ')})` : ''} · ${p.missing} only today's · ${p.extra} only built`,
        );
        if (p.differ.length) lines.push(`parity: rows that differ (sheetId): ${idWords(p.differ.map((d) => d.id)).join(', ')}`);
      }
      if (unbuilt.length) lines.push(`parity: ${plural(unbuilt.length, 'staged folder')} build no rows (sheetId): ${idWords(unbuilt).join(', ')}`);
      if (frozen) {
        let moved = 0;
        let unused = 0;
        for (const [slug, f] of frozen) {
          const row = built.find((r) => r.slug === slug && r.id === f.id);
          if (!row) {
            unused++;
            continue;
          }
          const own = fileText.get(row.source_path);
          if ([...f.fields].some(([field, v]) => textHash(own?.[field]) !== v.whileFilesSay)) moved++;
        }
        lines.push(
          `frozen text: ${frozen.size} entries · applied to ${frozenUsed} rows · ${moved} whose own files now say something else` +
            ` · ${unused} with no row`,
        );
      }
    }
    return { lines, failed: atlas.ok ? null : `Atlas could not be asked (${atlasWords(atlas, atlas.seed)})` };
  } catch (err) {
    const why = err instanceof Refusal || err instanceof ListingError ? err.message : unexpectedWords(err);
    lines.push(`report: the rehearsal stopped — ${why}`);
    return { lines, failed: `the rehearsal stopped (${why})` };
  }
}

/**
 * Under enforce, the commit message: what was published and removed by slug, what waits by sheetId.
 * `applied` is the stage this run took from, or null — none fetched, refused, older than the shelf,
 * or set aside by the shrink guard — and only a stage taken from is recorded in the trailer.
 */
export function enforceCommitMessage({ plan, words, applied, heldBack, loose, count, rewoundFrom }) {
  const lines = [];
  const claimants = new Set(plan.remove.filter((r) => r.claimant).map((r) => r.claimant.dir));
  const added = slugWords(plan.publish.filter((p) => !p.onShelf && !claimants.has(p.dir)).map((p) => p.built.rows[0]?.slug));
  if (added.length) lines.push(`Added: ${added.join(', ')}`);
  if (words.moved.length) lines.push(`Moved or renamed: ${words.moved.join(', ')}`);
  if (words.changed.length) lines.push(`Changed: ${words.changed.join(', ')}`);
  const removed = slugWords(plan.remove.filter((r) => !r.claimant).map((r) => path.posix.basename(r.dir)));
  if (removed.length) lines.push(`Removed: ${removed.join(', ')}`);
  if (loose) lines.push(`Removed ${plural(loose, 'file')} outside every skill folder`);
  if (heldBack.length) lines.push(`Kept as the shelf has it: ${idWords(heldBack).join(', ')}`);
  if (words.waiting.length) lines.push(`Waiting for Atlas: ${words.waiting.join(', ')}`);
  if (rewoundFrom) lines.push(`Rewound from ${rewoundFrom.slice(0, 7)}, dispatched with allow_rewind`);
  const subject = applied
    ? `export: ${plural(count, 'skill')} from ${applied.manifest.workbench_sha.slice(0, 7)}`
    : `export: ${plural(count, 'skill')}, only the removals Atlas asked for`;
  return [
    subject,
    '',
    ...(lines.length ? [...lines, ''] : []),
    ...(applied ? [`Workbench-Commit: ${applied.manifest.workbench_sha}`, ''] : []),
  ].join('\n');
}

/** k: SHELF_ATLAS=enforce. */
async function enforceRun(opts, deps, mode) {
  const { fetchImpl = globalThis.fetch, env = process.env, log = console.log, now = () => new Date() } = deps;
  const prune = pruneValue(opts.event, opts.prune);
  const siteUrl = env.SITE_SYNC_URL || SITE_SYNC_URL;
  const detailsUrl = env.SITE_DETAILS_URL || SITE_DETAILS_URL;
  const secret = env.SKILLS_SYNC_HMAC_SECRET;
  if (!opts.dryRun && !secret) refuse('the secret SKILLS_SYNC_HMAC_SECRET is not set (the export environment holds it)');
  if (!opts.dryRun && (new URL(siteUrl).protocol !== 'https:' || new URL(detailsUrl).protocol !== 'https:')) {
    refuse('SITE_SYNC_URL and SITE_DETAILS_URL must be https URLs');
  }
  log(`atlas: enforce${mode.explicit ? '' : ' (SHELF_ATLAS is not set: the default)'} — only what Atlas lists leaves the team`);
  if (opts.promote) log('note: promote is retired under SHELF_ATLAS=enforce — Atlas is the only way onto the shelf; ignored');

  const stageRoot = path.join(opts.stage, 'stage');
  if (opts.seedFail && isDir(stageRoot)) seedFail(stageRoot); // a: the stage is then refused (rule 5)
  const today = isoDay(now());
  const frozen = loadFrozen(opts.shelf);
  // Atlas is asked first, so its answer is in hand whatever the stage turns out to be; the stage read
  // never throws (loadStageForAtlas sets anything it cannot read aside, rule 5).
  const atlas = await askAtlasFor(opts, { env, fetchImpl });
  const shelf = readShelfState(opts.shelf);
  const stage = await loadStageForAtlas(opts, { env, fetchImpl });
  // Staged folders whose bytes git changed on the way into the index; filled below, and planned again.
  const setAside = new Set();
  const planFor = () => planEnforce({ stage, shelf: shelf.folders, atlas, allowShrink: opts.allowShrink, frozen, today, setAside });
  let plan = planFor();
  // How many rows the shelf listed before, and how many of them the removals Atlas asks for take —
  // read now, while every folder is still on disk (setting a folder aside never changes those).
  const rowCount = (h) => rowsOf(h.view, { frozen, today }).built?.rows.length ?? 0;
  const rowsBefore = shelf.folders.reduce((n, h) => n + rowCount(h), 0);
  const rowsByAtlas = plan.remove.filter((r) => r.by === 'atlas').reduce((n, r) => n + rowCount(r.shelf), 0);
  const tell = (p) => {
    const lines = [stageLine(stage), atlasLine(atlas), ...planLines(p, planWords(p), 'rule: ')];
    for (const line of lines) log(line);
    return ['### Export to the shelf (SHELF_ATLAS=enforce)', '', `- Prune: \`${prune}\``, ...lines.map((l) => `- ${l.trim()}`)];
  };

  if (opts.dryRun) {
    const summary = tell(plan);
    const words = planWords(plan);
    log(JSON.stringify({ dry_run: true, atlas: 'enforce', prune, counts: words.counts, ...words }, null, 2));
    summarize(env, [...summary, '- Dry run: nothing changed, nothing posted', '']);
    return { outcome: 'dry-run', plan, stage, atlas };
  }

  // i: the shelf after the run — published folders from the stage, kept ones as the shelf has them.
  // A published folder whose bytes git would change (a .gitattributes rule) is set aside — kept as the
  // shelf has it, or waiting — and the run plans and mirrors again: rule 5, nothing in the stage stops
  // the removals Atlas asks for. Each round sets at least one folder aside, so this ends.
  const shelfFiles = new Map(shelf.folders.map((h) => [h.dir, h.files]));
  let applied;
  let desired;
  for (;;) {
    // The stage this run takes from: not one the shrink guard set aside.
    applied = stage.usable && !plan.stageRefused ? stage : null;
    const stageFiles = applied ? new Map(applied.folders.map((s) => [s.dir, s.files])) : new Map();
    desired = new Map();
    for (const [dir, f] of plan.final) {
      const files = f.from === 'stage' ? stageFiles.get(dir) : shelfFiles.get(dir);
      for (const e of files) desired.set(`${dir}/${e.path}`, { sha: e.sha, mode: e.mode, from: f.from });
    }
    mirror(opts.shelf, applied ? applied.stageRoot : stageRoot, desired);
    const kept = [...plan.final].filter(([, f]) => f.from === 'shelf').map(([dir]) => dir);
    const off = stageIndexEnforce(opts.shelf, desired, kept);
    if (!off.length) break;
    const published = new Set(plan.publish.map((p) => p.dir));
    const culprits = [...new Set(off.map((p) => folderOf(p, published)).filter(Boolean))];
    if (!culprits.length) {
      refuse(`after the mirror, git's index differs from the copies the shelf keeps at ${plural(off.length, 'path')}, so nothing is committed`);
    }
    for (const dir of culprits) setAside.add(dir);
    // Those the shelf already held go back to its own copy before the next mirror.
    const held = culprits.filter((dir) => shelfFiles.has(dir));
    if (held.length) git(opts.shelf, ['checkout', '-q', 'HEAD', '--', ...held]);
    plan = planFor();
  }
  const words = planWords(plan);
  const summary = tell(plan);
  const changed = git(opts.shelf, ['diff', '--cached', '--name-only', '--', 'skills']).trim() !== '';
  const rewound = Boolean(applied) && REWINDS.has(applied.order);
  const stagedTree = applied ? new Map(applied.folders.map((s) => [s.dir, s.tree])) : new Map();
  const heldBack = plan.keep
    .filter((k) => stagedTree.has(k.dir) && stagedTree.get(k.dir) !== k.shelf.tree)
    .flatMap((k) => (k.shelf.ids.size ? [...k.shelf.ids] : ['']));
  let commit = null;
  if (changed || rewound) {
    const message = enforceCommitMessage({ plan, words, applied, heldBack, loose: shelf.loose, count: plan.final.size, rewoundFrom: rewound ? applied.last : null });
    commit = commitAndPush(opts.shelf, message, { allowEmpty: !changed });
    log(`shelf: pushed ${commit.slice(0, 7)}`);
  } else log('shelf: no change to commit');
  summary.push(`- Shelf: ${commit ? `pushed \`${commit.slice(0, 7)}\`` : 'no change to commit'}`);

  // j: every row is built from the files the shelf now holds; nothing from the stage's payload.
  if (plan.unbuildable.length) {
    summarize(env, [...summary, '']);
    refuse(
      `${plural(plan.unbuildable.length, 'folder')} the shelf keeps ${plan.unbuildable.length === 1 ? 'builds' : 'build'} no rows from ` +
        `${plan.unbuildable.length === 1 ? 'its' : 'their'} files (sheetId: ${idWords(plan.unbuildable.flatMap((d) => [...(shelf.folders.find((h) => h.dir === d)?.ids ?? [])])).join(', ') || 'none'}), ` +
        'so nothing is posted: a partial body would prune live listings',
    );
  }
  const rows = sortRows([...plan.final.values()].flatMap((f) => f.built.rows));
  const ids = new Set();
  const slugs = new Set();
  for (const r of rows) {
    if (ids.has(r.id) || slugs.has(r.slug)) refuse('two rows the shelf holds share an id or a slug, so nothing is posted');
    ids.add(r.id);
    slugs.add(r.slug);
  }
  let firstSeen;
  try {
    firstSeen = await readSiteFirstSeen({ url: detailsUrl, fetchImpl, bust: env.GITHUB_RUN_ID });
  } catch (err) {
    if (err instanceof ListingError) refuse(`${err.message}: first_seen cannot be carried, so nothing is posted`);
    throw err;
  }
  finishRows(rows, { firstSeen, today });
  const carried = rows.filter((r) => firstSeen.has(r.id)).length;
  const frozenUsed = [...plan.final.values()].reduce((n, f) => n + (f.built.frozenUsed ?? 0), 0);
  log(`listing: ${plural(rows.length, 'row')} built from the shelf's files · first_seen carried for ${carried} · frozen text on ${frozenUsed}`);

  // Atlas asks for removals with no shrink guard (rule 5), and that holds for the site's valve too:
  // when the removals Atlas asked for are what takes the post under half, the body says allow_shrink.
  const atlasShrink = rowsBefore > 0 && rows.length < rowsBefore / 2 && rows.length + rowsByAtlas >= rowsBefore / 2;
  if (atlasShrink) log('note: the removals Atlas asked for take the listings under half, so the post carries allow_shrink');

  const workbenchSha = applied ? applied.manifest.workbench_sha : lastWorkbenchCommit(opts.shelf);
  if (!workbenchSha) refuse('no workbench commit to name in the post (no stage taken from, and no Workbench-Commit trailer on the shelf)');
  const startedAt = await runStartedAt({ env, fetchImpl });
  const body = buildBody({ workbenchSha, committedAt: startedAt, prune, allowShrink: opts.allowShrink || atlasShrink, rows });
  const answer = await postToSite({ url: siteUrl, body, secret, sourceSha: workbenchSha, fetchImpl });
  const described = describeAnswer(answer.status, answer.text);
  log(`site: ${described}`);
  summarize(env, [...summary, `- Listing: ${plural(rows.length, 'row')} built from the shelf's files`, `- Site: ${described}`, '']);

  // Rule 5: the removals were made and the rows posted; a missing side still makes the run red.
  const missing = [];
  if (!atlas.ok) missing.push(`Atlas could not be asked (${atlasWords(atlas, atlas.seed)})`);
  if (plan.stageRefused) missing.push(plan.stageRefused);
  else if (!stage.usable && stage.why !== 'stale') missing.push(stage.why === 'none' ? 'no stage was fetched' : `the stage was refused: ${stage.words}`);
  if (missing.length) {
    refuse(`${missing.join('; ')}. Only the removals one side asked for were made, nothing new was published, and the rows were posted.`);
  }
  return { outcome: 'published', plan, stage, atlas, body, commit, answer };
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
          'seed-atlas': { type: 'string' },
          'dry-run': { type: 'boolean' },
        },
      }));
    } catch (err) {
      refuse(`${err.message}\n${USAGE}`);
    }
    if (!values.stage || !values.shelf || !values.event) refuse(USAGE);
    // fetch-stage.mjs writes run.json only beside a stage it fetched and checked: no file means no stage.
    const runFile = values.run ? path.resolve(values.run) : null;
    const stageMissing = runFile !== null && !isFile(runFile);
    await publish(
      {
        stage: path.resolve(values.stage),
        shelf: path.resolve(values.shelf),
        event: values.event,
        run: runFile && !stageMissing ? readJson(runFile, 'run.json') : undefined,
        stageMissing,
        prune: values.prune,
        promote: values.promote ?? '',
        allowShrink: Boolean(values['allow-shrink']),
        allowRewind: Boolean(values['allow-rewind']),
        seedFail: Boolean(values['seed-fail']),
        seedAtlas: values['seed-atlas'] ?? '',
        dryRun: Boolean(values['dry-run']),
      },
      { ...deps, env },
    );
    return 0;
  } catch (err) {
    const message = err instanceof Refusal ? err.message : unexpectedWords(err);
    error(env.GITHUB_ACTIONS === 'true' ? `::error::${annotation(message)}` : `refused: ${message}`);
    summarize(env, ['### Export refused', '', message, '']);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main();
}
