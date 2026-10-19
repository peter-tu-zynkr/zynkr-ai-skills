/**
 * enforce.mjs — SHELF_ATLAS: what may leave the team is what Zynkr Atlas lists (ATL-113 Part D,
 * spec §15.4, rulings D-138…D-142). The plan here is pure: publish.mjs reads the shelf, the stage and
 * Atlas, and then does what the plan says.
 *
 * For each folder the stage holds:
 *   1. Publish: Atlas lists it, and the git tree recomputed from the staged files equals the listed
 *      tree. Rules 6 and 7 must hold too.
 *   2. Keep: Atlas lists it with another tree, or 「as is」, or rule 6 or 7 fails: the shelf keeps the
 *      copy it has; a folder not on the shelf yet waits.
 *   3. Out: Atlas does not list it: removed if the shelf has it (Atlas asks: no shrink guard), waits
 *      if not.
 * For each folder the shelf holds that the stage no longer does:
 *   4. Left the workbench: removed — unless the shelf's own test (promotion.mjs) sees a staged folder
 *      as its category move or rename, the claimant is not published this run, and Atlas still lists
 *      the old path at the tree the shelf holds (or as 「as is」).
 *   5. One side is enough to remove. Atlas cannot be asked: rule 4's removals, nothing new. No usable
 *      stage: the shelf folders Atlas no longer lists go. The shrink guard (under half needs
 *      allow_shrink) counts only removals the stage asks for; when it trips, the stage is refused and
 *      only the removals Atlas asks for are made.
 *   6. A folder publishes only when its own manifest reads exactly `visibility: public` line by line
 *      and as YAML, no agents/*.md is marked anything else, it holds no SKILL.md or CLAUDE.md but its
 *      own manifest, and its manifest carries no install_command — and its rows build from its files.
 *   7. No two rows may share a sheetId, a slug or a name: a folder whose rows would collide with
 *      another's keeps the shelf's copy or waits.
 *
 * Words for the public log: a folder published or removed is named by its slug (checked); a folder
 * kept or waiting by its sheetId (checked, `^\d+\.\d+$`), never by name; reasons as counts only.
 */

import path from 'node:path';
import { plural, refuse } from './common.mjs';
import { Unreadable, markReadings, readFrontmatter, readFrontmatterKey } from './frontmatter.mjs';
import { ListingError, deriveFolder } from './listing.mjs';
import { NAME_RE } from './manifest.mjs';
import { claimsOf } from './promotion.mjs';

// ── the switch ───────────────────────────────────────────────────────────────

export const ATLAS_MODES = ['off', 'report', 'enforce'];

/**
 * What an unset SHELF_ATLAS means: `enforce`, since the switch on 2026-10-19 (spec §15.4 「Switching it
 * on」). `off`, the shelf as it published before Part D, must be set on purpose; each run logs which.
 */
export const DEFAULT_ATLAS_MODE = 'enforce';

/** { mode, explicit } from the SHELF_ATLAS variable; anything else refuses the run. */
export function atlasMode(value) {
  const v = typeof value === 'string' ? value.trim() : '';
  if (v === '') return { mode: DEFAULT_ATLAS_MODE, explicit: false };
  if (!ATLAS_MODES.includes(v)) refuse('the repository variable SHELF_ATLAS must be off, report or enforce');
  return { mode: v, explicit: true };
}

// ── words for the public log ─────────────────────────────────────────────────

const SHEET_ID_RE = /^\d+\.\d+$/;

/** A sheetId fit for the public log, or null. */
export const checkedId = (id) => (typeof id === 'string' && SHEET_ID_RE.test(id) ? id : null);

/** A slug or folder name fit for the public log, or null. */
export const checkedSlug = (s) => (typeof s === 'string' && s.length <= 64 && NAME_RE.test(s) ? s : null);

const countWords = (n, what) => (n ? [`${plural(n, what)} with no ${what === 'skill' ? 'sheetId' : 'checkable name'}`] : []);

/** sheetIds as the public log may show them: checked, sorted, unique; the rest counted. */
export function idWords(ids) {
  const ok = [...new Set(ids.map(checkedId).filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  return [...ok, ...countWords(ids.filter((id) => !checkedId(id)).length, 'skill')];
}

/** Slugs as the public log may show them: checked; the rest counted. */
export function slugWords(slugs) {
  const ok = slugs.map(checkedSlug).filter(Boolean);
  return [...ok, ...countWords(slugs.length - ok.length, 'folder')];
}

// ── rule 6 ───────────────────────────────────────────────────────────────────

const AGENT_FILE = /(^|\/)agents\/[^/]+\.md$/;

/**
 * Rule 6 for a folder about to be published, on its staged bytes. `manifest` is the folder's own
 * manifest as the listing build found it. Returns null when the folder passes, else a short reason.
 */
export function markProblem(view, manifest) {
  const text = view.read(manifest);
  const own = markReadings(text);
  if (own.line !== 'public' || own.yaml !== 'public') return 'its manifest is not marked public both ways';
  for (const rel of view.rels) {
    const base = path.posix.basename(rel).toLowerCase();
    if ((base === 'skill.md' || base === 'claude.md') && rel !== manifest) return 'a second manifest';
  }
  for (const rel of view.rels) {
    if (!AGENT_FILE.test(rel)) continue;
    const r = markReadings(view.read(rel));
    if (r.yaml === null) return 'a sub-agent whose frontmatter cannot be read';
    if ((r.line !== undefined && r.line !== 'public') || (r.yaml !== undefined && r.yaml !== 'public')) {
      return 'a sub-agent marked other than public';
    }
  }
  if (readFrontmatterKey(text, 'install_command') !== null) return 'an install_command override';
  try {
    if (readFrontmatter(text).data?.install_command !== undefined) return 'an install_command override';
  } catch (err) {
    if (err instanceof Unreadable) return 'its manifest cannot be read';
    throw err;
  }
  return null;
}

// ── the plan ─────────────────────────────────────────────────────────────────

/**
 * Rows a folder's files build, or null when they build none: `why` is the ListingError's phrase, or a
 * fixed one for anything else (a staged file that cannot be read, say) — never stopping the run.
 */
function tryRows(view, opts) {
  try {
    return { built: deriveFolder(view, opts), why: null };
  } catch (err) {
    return { built: null, why: err instanceof ListingError ? err.message : 'an unexpected failure' };
  }
}

/** The (id | slug | name) keys of a folder's rows, for rule 7. */
const keysOf = (rows) => rows.flatMap((r) => [`id ${r.id}`, `slug ${r.slug}`, `name ${r.name.toLowerCase()}`]);

/**
 * The plan for one run.
 *   stage: { usable: true, folders: [{ dir, tree, name, sheetId, renamedFrom, view }] }
 *          or { usable: false, why } when there is none, it is refused, or it is older than the shelf
 *   shelf: [{ dir, tree, names: Set, ids: Set, view }]
 *   atlas: { ok: true, list: { folders: Map(path → tree), asIs: Set } } or { ok: false, … }
 *   setAside: staged folders whose bytes git changed on the way into the index (a .gitattributes
 *          rule): never published, kept as the shelf has them or waiting
 * Returns { publish, keep, wait, remove, final, stageRefused, unbuildable }:
 *   publish  [{ dir, folder, built, onShelf, sameTree }] — copy these from the stage
 *   keep     [{ dir, why, shelf }]   — the shelf's copy stays
 *   wait     [{ dir, why, folder }]  — not on the shelf, not published
 *   remove   [{ dir, by: 'atlas' | 'stage', shelf, claimant? }]
 *   final    Map(dir → { from: 'stage' | 'shelf', built }) — what the shelf holds after the run
 *   stageRefused  null, or why the stage was set aside (the shrink guard)
 *   unbuildable   [dir] — folders the shelf keeps whose rows its files do not build
 */
export function planEnforce({ stage, shelf, atlas, allowShrink = false, frozen = null, today, setAside = new Set() }) {
  const listOpts = { frozen, today };
  const shelfRows = new Map();
  const rowsOfShelf = (h) => {
    if (!shelfRows.has(h.dir)) shelfRows.set(h.dir, tryRows(h.view, listOpts));
    return shelfRows.get(h.dir);
  };
  const tree = (dir) => (atlas.ok ? atlas.list.folders.get(dir) : undefined);
  const asIs = (dir) => atlas.ok && atlas.list.asIs.has(dir);
  const plan = { publish: [], keep: [], wait: [], remove: [], final: new Map(), stageRefused: null, unbuildable: [] };
  const keep = (h, why) => plan.keep.push({ dir: h.dir, why, shelf: h });
  const finish = () => {
    for (const k of plan.keep) {
      const { built } = rowsOfShelf(k.shelf);
      plan.final.set(k.dir, { from: 'shelf', built });
      if (!built) plan.unbuildable.push(k.dir);
    }
    for (const p of plan.publish) plan.final.set(p.dir, { from: 'stage', built: p.built });
    return plan;
  };

  // Rule 5, no usable stage: keep what Atlas still lists, remove what it no longer does.
  if (!stage.usable) {
    for (const h of shelf) {
      if (!atlas.ok) keep(h, 'Atlas could not be asked');
      else if (tree(h.dir) !== undefined || asIs(h.dir)) keep(h, 'no usable stage');
      else plan.remove.push({ dir: h.dir, by: 'atlas', shelf: h });
    }
    return finish();
  }

  const shelfByDir = new Map(shelf.map((h) => [h.dir, h]));
  const stageDirs = new Set(stage.folders.map((s) => s.dir));
  const candidates = [];
  for (const s of stage.folders) {
    const h = shelfByDir.get(s.dir);
    const hold = (why) => (h ? keep(h, why) : plan.wait.push({ dir: s.dir, why, folder: s }));
    if (!atlas.ok) {
      hold('Atlas could not be asked');
      continue;
    }
    if (asIs(s.dir)) {
      hold('as is');
      continue;
    }
    const listed = tree(s.dir);
    if (listed === undefined) {
      if (h) plan.remove.push({ dir: s.dir, by: 'atlas', shelf: h });
      else plan.wait.push({ dir: s.dir, why: 'not listed', folder: s });
      continue;
    }
    if (listed !== s.tree) {
      hold('another tree');
      continue;
    }
    if (setAside.has(s.dir)) {
      hold('git would change its bytes');
      continue;
    }
    const { built, why } = tryRows(s.view, listOpts);
    if (!built) {
      hold(`its listing does not build (${why})`);
      continue;
    }
    let problem;
    try {
      problem = markProblem(s.view, built.manifest);
    } catch {
      problem = 'its marks cannot be read';
    }
    if (problem) {
      hold(problem);
      continue;
    }
    candidates.push({ s, h, built });
  }

  // Rule 4: shelf folders that left the stage, and who claims them.
  const claims = claimsOf(stage.folders, shelf);
  const claimed = new Map([...claims].map(([from, s]) => [s.dir, from]));
  const gone = shelf.filter((h) => !stageDirs.has(h.dir));
  const stillListed = (h) => atlas.ok && (tree(h.dir) === h.tree || asIs(h.dir));
  const provisionally = gone.filter((h) => claims.has(h.dir) && stillListed(h));

  // Rule 7: the rows on the shelf after the run must not share an id, a slug or a name. Start from
  // everything that stays if no candidate is published; take candidates claimants-first, by path.
  // Each key maps to the folders whose rows hold it, so a candidate costs its own keys, not the shelf's.
  const owners = new Map(); // key → Map(dir → how many of that folder's rows hold the key)
  const standing = new Map(); // dir → rows
  const unstand = (dir) => {
    for (const k of keysOf(standing.get(dir) ?? [])) {
      const holders = owners.get(k);
      const n = (holders?.get(dir) ?? 0) - 1;
      if (n > 0) holders.set(dir, n);
      else holders?.delete(dir);
    }
    standing.delete(dir);
  };
  const stand = (dir, rows) => {
    unstand(dir);
    standing.set(dir, rows);
    for (const k of keysOf(rows)) {
      if (!owners.has(k)) owners.set(k, new Map());
      owners.get(k).set(dir, (owners.get(k).get(dir) ?? 0) + 1);
    }
  };
  for (const k of plan.keep) stand(k.dir, rowsOfShelf(k.shelf).built?.rows ?? []);
  for (const c of candidates) if (c.h) stand(c.h.dir, rowsOfShelf(c.h).built?.rows ?? []);
  for (const h of provisionally) stand(h.dir, rowsOfShelf(h).built?.rows ?? []);
  const order = [...candidates].sort((a, b) => {
    const ca = claimed.has(a.s.dir) ? 0 : 1;
    const cb = claimed.has(b.s.dir) ? 0 : 1;
    return ca - cb || (a.s.dir < b.s.dir ? -1 : a.s.dir > b.s.dir ? 1 : 0);
  });
  const published = new Set();
  for (const c of order) {
    const replaced = claimed.get(c.s.dir);
    const collides = keysOf(c.built.rows).some((k) =>
      [...(owners.get(k)?.keys() ?? [])].some((dir) => dir !== c.s.dir && dir !== replaced),
    );
    if (collides) {
      if (c.h) keep(c.h, 'its rows would collide with another folder\'s');
      else plan.wait.push({ dir: c.s.dir, why: 'its rows would collide with another folder\'s', folder: c.s });
      continue;
    }
    stand(c.s.dir, c.built.rows);
    if (replaced) unstand(replaced);
    published.add(c.s.dir);
    plan.publish.push({ dir: c.s.dir, folder: c.s, built: c.built, onShelf: Boolean(c.h), sameTree: Boolean(c.h) && c.h.tree === c.s.tree });
  }

  for (const h of gone) {
    const claimant = claims.get(h.dir);
    if (claimant && !published.has(claimant.dir) && stillListed(h)) keep(h, 'moved or renamed; Atlas still lists its old place');
    else plan.remove.push({ dir: h.dir, by: 'stage', shelf: h, claimant: claimant && published.has(claimant.dir) ? claimant : undefined });
  }

  // The shrink guard, for the removals the stage asks for only. An old place whose move or rename was
  // published this run is replaced, not lost (planPromotion counts it as kept, too).
  const byStage = plan.remove.filter((r) => r.by === 'stage' && !r.claimant).length;
  if (shelf.length > 0 && shelf.length - byStage < shelf.length / 2 && !allowShrink) {
    const refused = planEnforce({ stage: { usable: false, why: 'shrink' }, shelf, atlas, allowShrink, frozen, today });
    refused.stageRefused =
      `the stage would take ${plural(byStage, 'folder')} off a shelf of ${shelf.length}, leaving under half; ` +
      'dispatch with allow_shrink if that is intended';
    return refused;
  }
  return finish();
}

/** Decision counts and names, as the public log may show them. */
export function planWords(plan) {
  const added = plan.publish.filter((p) => !p.onShelf);
  const changed = plan.publish.filter((p) => p.onShelf && !p.sameTree);
  const slugOf = (p) => p.built.rows[0]?.slug;
  const keptIds = plan.keep.flatMap((k) => (k.shelf.ids.size ? [...k.shelf.ids] : ['']));
  const waitIds = plan.wait.map((w) => w.folder.sheetId ?? '');
  const reasons = new Map();
  for (const x of [...plan.keep, ...plan.wait]) reasons.set(x.why, (reasons.get(x.why) ?? 0) + 1);
  return {
    counts:
      `publish ${plan.publish.length} (new ${added.length} · changed ${changed.length}) · keep ${plan.keep.length} · ` +
      `wait ${plan.wait.length} · remove ${plan.remove.length} (Atlas ${plan.remove.filter((r) => r.by === 'atlas').length} · ` +
      `left the workbench ${plan.remove.filter((r) => r.by === 'stage').length})`,
    added: slugWords(added.map(slugOf)),
    changed: slugWords(changed.map(slugOf)),
    removed: slugWords(plan.remove.map((r) => path.posix.basename(r.dir))),
    kept: idWords(keptIds),
    waiting: idWords(waitIds),
    reasons: [...reasons].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).map(([why, n]) => `${why} ${n}`),
    moved: plan.remove
      .filter((r) => r.claimant)
      .map((r) => `${checkedSlug(path.posix.basename(r.dir)) ?? 'a folder'} → ${checkedSlug(plan.publish.find((p) => p.dir === r.claimant.dir)?.built.rows[0]?.slug) ?? 'a folder'}`),
  };
}
