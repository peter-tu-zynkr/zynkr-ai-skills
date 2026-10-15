/**
 * listing.mjs — every zynkr.ai row, built by the shelf from the files it holds (ATL-113 Part D, D-142).
 *
 * Until Part D the shelf passed the stage's payload.json through to zynkr.ai, so whoever could change
 * the workbench's stage job could change any public listing. Now the shelf builds each row itself,
 * from the bytes of the folder it holds, with the workbench's own derivation vendored here:
 *
 *   1. the workbench's ingest record: one for a SKILL.md and each of its agents/*.md, or, for a
 *      project whose orchestrator carries a `## Pipeline Stages` table (tried first, as ingest
 *      does), one for its manifest and each stage's agent; the manifest must pass the workbench's
 *      frontmatter schema (zod, ported in `skillFrontmatter`); every id is the file's own `sheetId`
 *      (the shelf cannot replay the workbench's id allocation, so a file without one is refused);
 *      input / process / output are resolved and clipped twice, exactly as ingest's two passes do
 *      (the record, then the registry built from it);
 *   2. the workbench's marketplace build: slug, summary, tags, the trimmed fields and the duplicate
 *      checks;
 *   3. the shelf's own fields, as before: repo_url, github_url and install_command.
 *
 * Three things never come from the folder, and never from the stage either:
 *   - input / process / output for the entries whose text came from a workbench index file no skill
 *     folder holds (D-142, Q11 a) are frozen at what zynkr.ai served at the switch, in
 *     listing/frozen-text.json. Each frozen field applies while the shelf's own files still say what
 *     they said when it was frozen (`while_files_say`, a sha256 of the text the files give, or null for
 *     none): once an approved merge moves the text into the skill's own file, the file wins;
 *   - first_seen is carried from the row zynkr.ai already holds (a new row gets the run's date);
 *   - github_stars and github_forks are left out, and the site keeps the counts it stored.
 *
 * Nothing here logs. A failure is a ListingError carrying a fixed phrase, never a file's text.
 */

import crypto from 'node:crypto';
import path from 'node:path';
import { SHELF_URL } from './common.mjs';
import { Unreadable, readFrontmatter } from './frontmatter.mjs';
import { NAME_RE, OVERRIDE_RE, parseFrontmatter } from './manifest.mjs';

/** The folder's rows cannot be built; `message` is a fixed phrase, safe for the public log. */
export class ListingError extends Error {}

const cannot = (why) => {
  throw new ListingError(why);
};

export const IPO_FIELDS = ['input', 'process', 'output'];
const SHEET_ID_RE = /^\d+\.\d+$/;
const SITE_SLUG_RE = /^[a-z0-9-]{1,128}$/;

const byBytes = (a, b) => Buffer.compare(Buffer.from(a, 'utf8'), Buffer.from(b, 'utf8'));
const isPlainObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v) && !(v instanceof Date);

// ── a folder, as the derivation sees it ──────────────────────────────────────

/**
 * A read-only view of one skill folder: `dir` is its path from the repo root (`skills/<cat>/<name>`),
 * `rels` its files relative to it, `readText(rel)` a file's text. Listing is sorted by bytes, as the
 * workbench's readdir (libuv sorts with strcmp).
 */
export function folderView(dir, rels, readText) {
  const files = new Set(rels);
  const dirs = new Set(['']);
  for (const r of rels) {
    const parts = r.split('/');
    for (let i = 1; i < parts.length; i++) dirs.add(parts.slice(0, i).join('/'));
  }
  const children = new Map();
  const add = (parent, name, isDir) => {
    if (!children.has(parent)) children.set(parent, new Map());
    children.get(parent).set(name, isDir);
  };
  for (const r of files) add(path.posix.dirname(r) === '.' ? '' : path.posix.dirname(r), path.posix.basename(r), false);
  for (const d of dirs) if (d) add(path.posix.dirname(d) === '.' ? '' : path.posix.dirname(d), path.posix.basename(d), true);
  const listing = new Map(
    [...children].map(([parent, names]) => [
      parent,
      [...names].map(([name, isDir]) => ({ name, isDir })).sort((a, b) => byBytes(a.name, b.name)),
    ]),
  );
  const cache = new Map();
  return {
    dir,
    rels: [...files].sort(byBytes),
    isFile: (rel) => files.has(rel),
    exists: (rel) => files.has(rel) || (rel !== '' && dirs.has(rel)),
    list: (rel) => listing.get(rel) ?? [],
    read: (rel) => {
      if (!files.has(rel)) cannot('a file the folder does not hold');
      if (!cache.has(rel)) cache.set(rel, readText(rel));
      return cache.get(rel);
    },
  };
}

// ── the workbench's frontmatter schema (zod), ported ─────────────────────────

const TAXONOMY = new Set([
  'strategy', 'brand-marketing', 'sales-consultant', 'operations', 'training',
  'product', 'engineer', 'people-talent', 'finance-admin', 'legal',
]);
const PLATFORMS = new Set(['gpt', 'claude', 'gemini', 'multi']);
const STATUSES = new Set(['Done', 'WIP', 'Not started', 'Pause', 'Out dated']);
const VISIBILITIES = new Set(['public', 'team', 'client']);
const EXECUTED_BY = new Set(['external-user', 'internal-user']);
const EXECUTION_MODES = new Set(['llm', 'deterministic', 'hitl']);
const AUDITS = new Set(['pass', 'fail', 'pending']);
const AUDIT_KEYS = ['gen_agent_trust_hub', 'socket', 'snyk'];

const isString = (v) => typeof v === 'string';
const optString = (v) => v === undefined || isString(v);
const optStrings = (v) => v === undefined || (Array.isArray(v) && v.every(isString));
const isUrl = (v) => {
  try {
    new URL(v);
    return true;
  } catch {
    return false;
  }
};

/** The manifest as zod parses it (known keys; synergy defaulted), or null when it fails the schema. */
export function skillFrontmatter(d) {
  if (!isPlainObject(d)) return null;
  const ok =
    isString(d.name) && d.name.length >= 1 &&
    isString(d.category) && TAXONOMY.has(d.category) &&
    isString(d.project) && d.project.length >= 1 &&
    PLATFORMS.has(d.platform) &&
    STATUSES.has(d.status) &&
    (d.visibility === undefined || VISIBILITIES.has(d.visibility)) &&
    isString(d.author) && d.author.length >= 1 &&
    optString(d.description) && optString(d.input) && optString(d.process) && optString(d.output) &&
    optStrings(d.synergy) && optStrings(d.handoff) && optStrings(d.steps) && optStrings(d.flow) &&
    (d.executed_by === undefined || EXECUTED_BY.has(d.executed_by)) &&
    (d.execution_mode === undefined || EXECUTION_MODES.has(d.execution_mode)) &&
    (d.sheetId === undefined || (isString(d.sheetId) && SHEET_ID_RE.test(d.sheetId))) &&
    optString(d.upstream_repo) &&
    (d.original_source_url === undefined || (isString(d.original_source_url) && isUrl(d.original_source_url))) &&
    (d.original_author === undefined || (isString(d.original_author) && d.original_author.length >= 1)) &&
    (d.install_command === undefined || (isString(d.install_command) && d.install_command.length >= 1)) &&
    (d.security_audits === undefined ||
      (isPlainObject(d.security_audits) &&
        AUDIT_KEYS.every((k) => d.security_audits[k] === undefined || AUDITS.has(d.security_audits[k]))));
  if (!ok) return null;
  // Attribution: if any of the trio is set, all three must be (SKILL_SPEC.md §6).
  const hasAny = !!(d.upstream_repo || d.original_source_url || d.original_author);
  const hasAll = !!(d.upstream_repo && d.original_source_url && d.original_author);
  if (hasAny && !hasAll) return null;
  const audits = d.security_audits === undefined
    ? undefined
    : Object.fromEntries(AUDIT_KEYS.filter((k) => d.security_audits[k] !== undefined).map((k) => [k, d.security_audits[k]]));
  return {
    name: d.name,
    category: d.category,
    project: d.project,
    platform: d.platform,
    status: d.status,
    visibility: d.visibility,
    author: d.author,
    description: d.description,
    input: d.input,
    process: d.process,
    output: d.output,
    sheetId: d.sheetId,
    upstream_repo: d.upstream_repo,
    original_source_url: d.original_source_url,
    original_author: d.original_author,
    install_command: d.install_command,
    security_audits: audits,
  };
}

// ── the workbench's ingest, ported ───────────────────────────────────────────

const MAX_LENGTH = { input: 180, process: 260, output: 180 };

function normalizeWhitespace(value) {
  if (!value) return undefined;
  const compact = value.replace(/\s+/g, ' ').trim();
  return compact || undefined;
}

function normalizeFieldValue(value, maxLength) {
  if (!value) return undefined;
  const compact = value.replace(/\s+/g, ' ').trim();
  if (!compact) return undefined;
  if (compact.length <= maxLength) return compact;
  const clipped = compact.slice(0, maxLength);
  const safeBoundary = clipped.lastIndexOf(' ');
  const truncated = safeBoundary > Math.floor(maxLength * 0.7) ? clipped.slice(0, safeBoundary) : clipped;
  return `${truncated.trim()}...`;
}

/** One pass of ingest's resolveIpoFields for one field, without the CSV: the first candidate that
 *  normalizes to something. */
function resolveField(field, candidates) {
  for (const value of candidates) {
    const normalized = normalizeFieldValue(normalizeWhitespace(value) ?? '', MAX_LENGTH[field]);
    if (normalized) return normalized;
  }
  return undefined;
}

/** Both passes: the record's own (ingest), then the registry's over the record's value. */
const fileText = (field, candidates) => resolveField(field, [resolveField(field, candidates)]);

function normalizeAttributionUrl(value) {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (/^[\w.-]+\/[\w.-]+$/.test(trimmed)) return `https://github.com/${trimmed}`;
  return trimmed;
}

const optionalString = (data, key) => (isPlainObject(data) && typeof data[key] === 'string' ? data[key] : undefined);

function parsePipelineStages(content) {
  const cleanCell = (value) => value.trim().replace(/^`(.+)`$/, '$1').replace(/\\`/g, '`');
  const tableLines = [];
  let inSection = false;
  for (const line of content.split(/\r?\n/)) {
    if (!inSection) {
      if (/^##\s+Pipeline Stages\b/i.test(line.trim())) inSection = true;
      continue;
    }
    if (/^##\s+/.test(line.trim())) break;
    if (line.trim().startsWith('|')) tableLines.push(line);
  }
  return tableLines
    .map((line) => line.trim())
    .filter((line) => line.startsWith('|'))
    .map((line) => line.split('|').slice(1, -1).map(cleanCell))
    .filter((cells) => cells.length >= 4)
    .filter((cells) => cells[0] !== 'Stage')
    .filter((cells) => !cells.every((cell) => /^-+$/.test(cell.replace(/:/g, ''))))
    .map(([stage, agent, input, output]) => ({ stage, agent, input: input || undefined, output: output || undefined }));
}

function readMd(view, rel) {
  const raw = view.read(rel);
  try {
    const { data, content } = readFrontmatter(raw);
    return { rel, raw, data, content };
  } catch (err) {
    if (err instanceof Unreadable) cannot('a frontmatter the shelf cannot read');
    throw err;
  }
}

/** A sub-agent file's frontmatter: {} for none; gray-matter's null document would crash ingest. */
function agentData(file) {
  if (file.data === null || file.data === undefined) cannot('a sub-agent whose frontmatter is empty YAML');
  return isPlainObject(file.data) ? file.data : {};
}

/** The .md files of an agents folder, as ingest lists them: no dot-files, by bytes. */
function agentFiles(view, dir) {
  if (view.isFile(dir)) cannot('an agents path that is a file');
  return view
    .list(dir)
    .filter((e) => e.name.endsWith('.md') && !e.name.startsWith('.'))
    .map((e) => {
      if (e.isDir) cannot('an agents entry that is a folder');
      return readMd(view, `${dir}/${e.name}`);
    });
}

/** ingest's findMdFiles: every .md under the folder, skipping dot-entries and node_modules, in readdir order. */
function findMdFiles(view, rel = '') {
  const out = [];
  for (const e of view.list(rel)) {
    if (e.name.startsWith('.') || e.name === 'node_modules') continue;
    const child = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDir) out.push(...findMdFiles(view, child));
    else if (e.name.endsWith('.md')) out.push(child);
  }
  return out;
}

/** ingest's findOrchestratorAndAgents: SKILL.md + agents/, else .claude/skills/<x>/SKILL.md + .claude/agents/. */
function findLayout(view) {
  if (view.exists('SKILL.md') && view.exists('agents')) return { orchestrator: 'SKILL.md', agentsDir: 'agents' };
  if (view.exists('.claude/agents') && view.exists('.claude/skills')) {
    for (const d of view.list('.claude/skills')) {
      if (!d.isDir) continue;
      const skillMd = `.claude/skills/${d.name}/SKILL.md`;
      if (view.exists(skillMd)) return { orchestrator: skillMd, agentsDir: '.claude/agents' };
    }
  }
  return null;
}

/** The authored id of each source file: the shelf allocates none (ingest's precedence 0 only). */
function idsOf(entries) {
  const ids = new Map();
  const seen = new Set();
  for (const [rel, sheetId] of entries) {
    if (sheetId === undefined || sheetId === null) cannot('a file with no sheetId');
    if (!SHEET_ID_RE.test(sheetId)) cannot('a sheetId the workbench refuses');
    if (seen.has(sheetId)) cannot('a sheetId used twice in one folder');
    seen.add(sheetId);
    ids.set(rel, sheetId);
  }
  return ids;
}

/** The manifest's fields every record of its folder shares. */
const shared = (manifest) => ({
  category: manifest.category,
  project: manifest.project,
  platform: manifest.platform,
  status: manifest.status,
  visibility: manifest.visibility ?? 'team',
  author: manifest.author,
  upstreamRepo: normalizeAttributionUrl(manifest.upstream_repo),
  originalSourceUrl: normalizeAttributionUrl(manifest.original_source_url),
  originalAuthor: manifest.original_author,
  securityAudits: manifest.security_audits,
});

/** ingestRepoAsPipeline: null when the folder is no pipeline project (ingest then tries the next way). */
function pipelineRecords(view) {
  const layout = findLayout(view);
  if (!layout) return null;
  const orchestrator = readMd(view, layout.orchestrator);
  const stages = parsePipelineStages(orchestrator.content);
  if (stages.length === 0) return null;
  const valid = findMdFiles(view).map((rel) => readMd(view, rel)).filter((f) => skillFrontmatter(f.data));
  const manifestFile = valid.find((f) => path.posix.basename(f.rel).toLowerCase() === 'claude.md') ?? valid[0];
  if (!manifestFile) return null;
  const manifest = skillFrontmatter(manifestFile.data);

  const agents = agentFiles(view, layout.agentsDir);
  const byStem = new Map(agents.map((f) => [path.posix.basename(f.rel, '.md'), f]));
  const byName = new Map(
    agents.map((f) => [typeof agentData(f).name === 'string' ? agentData(f).name : '', f]).filter(([name]) => Boolean(name)),
  );
  const agentFor = (stage) => byStem.get(stage.agent) ?? byName.get(stage.agent) ?? cannot('a pipeline stage whose agent file is missing');
  const sources = [manifestFile.rel, ...stages.map((s) => agentFor(s).rel)];
  const ids = idsOf([
    [manifestFile.rel, manifest.sheetId],
    ...stages.map((s) => [agentFor(s).rel, optionalString(agentData(agentFor(s)), 'sheetId')]),
  ]);
  const synergy = sources.map((rel) => ids.get(rel));
  const base = shared(manifest);
  const records = [
    {
      ...base,
      rel: manifestFile.rel,
      id: ids.get(manifestFile.rel),
      sheetId: manifest.sheetId,
      name: manifest.name,
      description: manifest.description,
      candidates: { input: [manifest.input], process: [manifest.process], output: [manifest.output] },
      kind: 'orchestrator',
      synergy,
    },
  ];
  for (const stage of stages) {
    const file = agentFor(stage);
    const data = agentData(file);
    records.push({
      ...base,
      rel: file.rel,
      id: ids.get(file.rel),
      sheetId: optionalString(data, 'sheetId'),
      name: (typeof data.name === 'string' && data.name) || `${manifest.name} - ${stage.agent}`,
      description: optionalString(data, 'description'),
      candidates: {
        input: [optionalString(data, 'input'), stage.input],
        process: [optionalString(data, 'process'), `Stage ${stage.stage} in the ${manifest.name} pipeline, orchestrated by ${manifest.name}.`],
        output: [optionalString(data, 'output'), stage.output],
      },
      kind: 'subagent',
      stage: stage.stage,
      synergy,
    });
  }
  return { manifest: manifestFile.rel, records };
}

/** ingestProjectSkills: a SKILL.md and its agents/*.md; null when there is no valid SKILL.md. */
function projectRecords(view) {
  if (!view.exists('SKILL.md')) return null;
  const skillFile = readMd(view, 'SKILL.md');
  const manifest = skillFrontmatter(skillFile.data);
  if (!manifest) return null;
  const agents = view.exists('agents') ? agentFiles(view, 'agents') : [];
  const ids = idsOf([
    [skillFile.rel, manifest.sheetId],
    ...agents.map((f) => [f.rel, optionalString(agentData(f), 'sheetId')]),
  ]);
  const synergy = [skillFile.rel, ...agents.map((f) => f.rel)].map((rel) => ids.get(rel));
  const base = shared(manifest);
  const records = [
    {
      ...base,
      rel: skillFile.rel,
      id: ids.get(skillFile.rel),
      sheetId: manifest.sheetId,
      name: manifest.name,
      description: manifest.description,
      candidates: { input: [manifest.input], process: [manifest.process], output: [manifest.output] },
      kind: agents.length > 0 ? 'orchestrator' : 'skill',
      synergy,
    },
  ];
  for (const file of agents) {
    const data = agentData(file);
    records.push({
      ...base,
      rel: file.rel,
      id: ids.get(file.rel),
      sheetId: optionalString(data, 'sheetId'),
      name: (typeof data.name === 'string' && data.name) || path.posix.basename(file.rel, '.md'),
      description: optionalString(data, 'description'),
      candidates: {
        input: [optionalString(data, 'input')],
        process: [optionalString(data, 'process')],
        output: [optionalString(data, 'output')],
      },
      kind: 'subagent',
      synergy,
    });
  }
  return { manifest: skillFile.rel, records };
}

// ── the workbench's marketplace build, ported ────────────────────────────────

function toSlug(value) {
  return value
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/[\s_]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

const ensureString = (value) => (typeof value === 'string' && value.trim() ? value.trim() : undefined);
const compactWhitespace = (value) => value?.replace(/\s+/g, ' ').trim() || undefined;

function firstSentence(value) {
  const compact = compactWhitespace(value) ?? value.trim();
  const match = compact.match(/^(.{1,220}?[.!?。！？])(\s|$)/);
  return (match?.[1] ?? compact.slice(0, 220)).trim();
}

function buildSummary(skill) {
  const description = compactWhitespace(skill.description);
  if (description) return firstSentence(description);
  const parts = [skill.input, skill.process, skill.output].map(compactWhitespace).filter(Boolean);
  if (parts.length > 0) return firstSentence(parts.join(' '));
  return `${skill.name} for ${skill.project}`;
}

function buildTags(skill) {
  const derived = [skill.project, skill.category, skill.platform, skill.kind, skill.stage]
    .map(compactWhitespace)
    .filter(Boolean)
    .map(toSlug);
  return Array.from(new Set(derived));
}

function buildSlug(skill, sourcePath) {
  const sourceStem = sourcePath.split('/').pop().replace(/\.md$/i, '');
  const normalized = sourceStem ? toSlug(sourceStem) : undefined;
  const generic = !normalized || ['skill', 'claude', 'readme', 'index'].includes(normalized);
  if (skill.kind === 'orchestrator') return toSlug(skill.project || skill.name);
  if (skill.kind === 'subagent') return toSlug(skill.name);
  if (!generic && sourceStem) return toSlug(sourceStem);
  return toSlug(skill.project || skill.name);
}

const REQUIRED = ['id', 'slug', 'name', 'summary', 'category', 'project', 'platform', 'status', 'author', 'repo_url', 'source_path', 'tags', 'updated_at'];

// ── the shelf's own fields (SKB-038) ─────────────────────────────────────────

/**
 * repo_url, github_url and install_command, from the shelf's layout and the owning manifest's
 * own line (`fm`: manifest.mjs parseFrontmatter): the shelf's rule since SKB-038. Returns null when
 * the manifest's install_command is not the shelf's one-line form.
 */
export function shelfFields({ sourcePath, kind, installable, fm }) {
  const github_url =
    path.posix.basename(sourcePath) === 'CLAUDE.md'
      ? `${SHELF_URL}/tree/main/${path.posix.dirname(sourcePath)}`
      : `${SHELF_URL}/blob/main/${sourcePath}`;
  let install_command = null;
  if (kind !== 'subagent' && installable) {
    if (fm.keys.has('install_command')) {
      const override = fm.keys.get('install_command');
      if (fm.dupes.has('install_command') || typeof override !== 'string' || !OVERRIDE_RE.test(override)) return null;
      install_command = override;
    } else {
      install_command = `npx skills add ${SHELF_URL} --skill ${fm.keys.get('name')}`;
    }
  }
  return { repo_url: SHELF_URL, github_url, install_command };
}

// ── frozen text (D-142) ──────────────────────────────────────────────────────

/** sha256 of the text the files give for a field, or null when they give none. */
export const textHash = (value) =>
  value === undefined || value === null ? null : `sha256:${crypto.createHash('sha256').update(value, 'utf8').digest('hex')}`;

const HASH_RE = /^sha256:[0-9a-f]{64}$/;

/**
 * listing/frozen-text.json → Map(slug → { id, fields: Map(field → { text, whileFilesSay }) }).
 * Throws ListingError on anything but the exact shape: it is this repo's own file.
 */
export function readFrozen(json) {
  const bad = () => cannot('listing/frozen-text.json is not format shelf-frozen-text-v1');
  if (!isPlainObject(json) || json.format !== 'shelf-frozen-text-v1' || !Array.isArray(json.entries)) bad();
  const frozen = new Map();
  for (const e of json.entries) {
    if (!isPlainObject(e) || typeof e.slug !== 'string' || !SITE_SLUG_RE.test(e.slug) || typeof e.id !== 'string' || !SHEET_ID_RE.test(e.id)) bad();
    if (frozen.has(e.slug)) bad();
    const fields = new Map();
    for (const field of IPO_FIELDS) {
      if (e[field] === undefined) continue;
      const f = e[field];
      if (!isPlainObject(f) || !(f.text === null || typeof f.text === 'string')) bad();
      if (!(f.while_files_say === null || (typeof f.while_files_say === 'string' && HASH_RE.test(f.while_files_say)))) bad();
      fields.set(field, { text: f.text, whileFilesSay: f.while_files_say });
    }
    if (fields.size === 0) bad();
    frozen.set(e.slug, { id: e.id, fields });
  }
  return frozen;
}

// ── the derivation ───────────────────────────────────────────────────────────

/** Today's date as ingest writes it (UTC). */
export const isoDay = (date) => date.toISOString().split('T')[0];

/**
 * The folder's rows, built from its files. Returns { rows, manifest, installable, frozenUsed,
 * fileText } — `fileText` maps each row's source_path to the input / process / output its own files
 * give (what frozen text is bound to). Throws ListingError when the workbench would build no rows
 * for it, when it is not marked public, or when any field the site needs is missing.
 * `today` (YYYY-MM-DD) is the row's updated_at; first_seen is left for `finishRows`.
 */
export function deriveFolder(view, { frozen = null, today = isoDay(new Date()) } = {}) {
  const ingested = pipelineRecords(view) ?? projectRecords(view);
  if (!ingested) cannot('no manifest the workbench would read');
  const owner = ingested.records[0];
  if (owner.visibility !== 'public') cannot('a manifest that is not marked public');
  const manifestPath = `${view.dir}/${ingested.manifest}`;
  const fm = parseFrontmatter(view.read(ingested.manifest));
  if (!fm) cannot('a manifest the shelf cannot read line by line');
  const ownerName = fm.dupes.has('name') ? null : fm.keys.get('name');
  if (typeof ownerName !== 'string' || !NAME_RE.test(ownerName)) cannot('a manifest name that is not CLI-safe');
  const depth = manifestPath.split('/').length - 2; // folders under skills/
  const installable = path.posix.basename(manifestPath) === 'SKILL.md' && depth <= 3;

  const seen = { ids: new Set(), slugs: new Set(), names: new Set() };
  const fileText_ = new Map();
  let frozenUsed = 0;
  const rows = ingested.records.map((rec) => {
    const sourcePath = `${view.dir}/${rec.rel}`;
    const slug = buildSlug(rec, sourcePath);
    const own = Object.fromEntries(IPO_FIELDS.map((f) => [f, fileText(f, rec.candidates[f])]));
    fileText_.set(sourcePath, own);
    const ipo = { ...own };
    const hold = frozen?.get(slug);
    if (hold && hold.id === rec.id) {
      let used = false;
      for (const [field, f] of hold.fields) {
        if (textHash(own[field]) === f.whileFilesSay) {
          ipo[field] = f.text === null ? undefined : f.text;
          used = true;
        }
      }
      if (used) frozenUsed++;
    }
    const skill = { ...rec, ...ipo };
    const name = rec.name.trim();
    if (seen.ids.has(rec.id)) cannot('an id used twice');
    if (seen.slugs.has(slug)) cannot('a slug used twice');
    if (seen.names.has(name.toLowerCase())) cannot('a name used twice');
    seen.ids.add(rec.id);
    seen.slugs.add(slug);
    seen.names.add(name.toLowerCase());
    const shelf = shelfFields({ sourcePath, kind: rec.kind, installable, fm });
    if (!shelf) cannot('an install_command that is not the shelf\'s one-line form');
    const row = {
      id: rec.id,
      sheet_id: ensureString(rec.sheetId),
      slug,
      name,
      summary: buildSummary(skill),
      category: rec.category.trim(),
      project: rec.project.trim(),
      platform: rec.platform,
      status: rec.status,
      author: rec.author.trim(),
      repo_url: shelf.repo_url,
      source_path: sourcePath,
      install_command: shelf.install_command,
      tags: buildTags(skill),
      updated_at: today,
      upstream_repo: ensureString(rec.upstreamRepo),
      original_source_url: ensureString(rec.originalSourceUrl),
      original_author: ensureString(rec.originalAuthor),
      first_seen: undefined,
      visibility: 'public',
      description: compactWhitespace(rec.description),
      input: compactWhitespace(skill.input),
      process: compactWhitespace(skill.process),
      output: compactWhitespace(skill.output),
      kind: rec.kind,
      stage: ensureString(rec.stage),
      synergy: Array.isArray(rec.synergy) ? rec.synergy : [],
      github_url: shelf.github_url,
      security_audits: rec.securityAudits,
    };
    for (const field of REQUIRED) {
      const v = row[field];
      if (Array.isArray(v) ? v.length === 0 : !v) cannot(`a row with no ${field}`);
    }
    if (!SITE_SLUG_RE.test(slug)) cannot('a slug the site refuses');
    return row;
  });
  return { rows, manifest: ingested.manifest, installable, frozenUsed, fileText: fileText_ };
}

/** first_seen from the row zynkr.ai holds for the slug, else the run's date. */
export function finishRows(rows, { firstSeen, today }) {
  for (const row of rows) row.first_seen = firstSeen.has(row.slug) ? firstSeen.get(row.slug) : today;
  return rows;
}

/** The workbench's order for rows: by sheet_id, numerically, then by id. */
export function sortRows(rows) {
  return rows.sort((a, b) => {
    const as = a.sheet_id;
    const bs = b.sheet_id;
    if (as && bs) return as.localeCompare(bs, undefined, { numeric: true }) || a.id.localeCompare(b.id, undefined, { numeric: true });
    if (as) return -1;
    if (bs) return 1;
    return a.id.localeCompare(b.id, undefined, { numeric: true });
  });
}

// ── zynkr.ai's own answer: first_seen ────────────────────────────────────────

/**
 * Map(slug → first_seen) from zynkr.ai's public /api/skills/details (its live rows). Throws
 * ListingError when the answer cannot be read: a row would otherwise get today's date.
 */
export async function readSiteFirstSeen({ url, fetchImpl, bust = null, timeoutMs = 30_000 }) {
  const target = new URL(url);
  if (bust) target.searchParams.set('shelf_run', String(bust));
  let res;
  try {
    res = await fetchImpl(target.href, {
      headers: { Accept: 'application/json', 'User-Agent': 'zynkr-ai-skills-export' },
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    cannot('zynkr.ai\'s skill list could not be read');
  }
  if (!res.ok) cannot(`zynkr.ai's skill list answered ${res.status}`);
  let data;
  try {
    data = JSON.parse(await res.text());
  } catch {
    cannot('zynkr.ai\'s skill list is not JSON');
  }
  if (!isPlainObject(data)) cannot('zynkr.ai\'s skill list is not an object');
  const firstSeen = new Map();
  for (const row of Object.values(data)) {
    if (!isPlainObject(row) || typeof row.slug !== 'string' || !SITE_SLUG_RE.test(row.slug) || firstSeen.has(row.slug)) {
      cannot('zynkr.ai\'s skill list holds a row the shelf cannot read');
    }
    const fs = row.first_seen;
    if (!(fs === null || fs === undefined || (typeof fs === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(fs)))) {
      cannot('zynkr.ai\'s skill list holds a first_seen the shelf cannot read');
    }
    firstSeen.set(row.slug, fs ?? null);
  }
  return firstSeen;
}

// ── the parity check (report) ────────────────────────────────────────────────

/** Fields the shelf carries or leaves out on purpose, never compared. */
export const PARITY_SKIPS = new Set(['first_seen', 'github_stars', 'github_forks', 'updated_at']);

/** A value's comparable form, as zynkr.ai compares rows (api/skills/sync.js canon): keys sorted, null ≡ absent. */
export function canon(v) {
  if (v == null) return 'null';
  if (Array.isArray(v)) return `[${v.map(canon).join(',')}]`;
  if (typeof v === 'object') return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canon(v[k])}`).join(',')}}`;
  return JSON.stringify(String(v));
}

/**
 * How the rows built from files compare with the rows today's publish posts, matched by source_path:
 * { built, matched, differ: [{ id, fields }], missing, extra, fields: Map(field → count) }.
 */
export function parity(built, today) {
  const byPath = new Map(today.map((r) => [r.source_path, r]));
  const builtPaths = new Set(built.map((r) => r.source_path));
  const differ = [];
  const fields = new Map();
  let matched = 0;
  for (const row of built) {
    const other = byPath.get(row.source_path);
    if (!other) continue;
    matched++;
    const keys = new Set([...Object.keys(row), ...Object.keys(other)]);
    const off = [...keys].filter((k) => !PARITY_SKIPS.has(k) && canon(row[k]) !== canon(other[k])).sort();
    if (off.length) {
      differ.push({ id: row.id, fields: off });
      for (const k of off) fields.set(k, (fields.get(k) ?? 0) + 1);
    }
  }
  return {
    built: built.length,
    matched,
    differ,
    missing: today.filter((r) => !builtPaths.has(r.source_path)).length,
    extra: built.filter((r) => !byPath.has(r.source_path)).length,
    fields,
  };
}
