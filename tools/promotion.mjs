/**
 * promotion.mjs — the shelf's test for a skill it already publishes under another folder (SKB-038):
 * moved between categories, or renamed. Moved here unchanged from publish.mjs, which re-exports it;
 * `claimsOf` names the old folder each such skill claims, for SHELF_ATLAS rule 4 (ATL-113 Part D).
 */

import path from 'node:path';

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

/**
 * Rule 4's exception (ATL-113 §15.4): Map(old shelf folder → the stage folder that claims it), by the
 * same two tests planPromotion makes — a category move (same folder name, same frontmatter name, the
 * old folder gone from the stage) and a rename (`renamed_from` backed by the same sheetId).
 */
export function claimsOf(skills, shelf) {
  const stageDirs = new Set(skills.map((s) => s.dir));
  const paths = new Set(shelf.map((h) => h.dir));
  const claims = new Map();
  for (const s of skills) {
    if (paths.has(s.dir)) continue;
    for (const h of shelf) {
      if (
        !stageDirs.has(h.dir) &&
        path.posix.basename(h.dir) === path.posix.basename(s.dir) &&
        h.names.has(s.name) &&
        !claims.has(h.dir)
      ) {
        claims.set(h.dir, s);
      }
    }
  }
  for (const { skill, from } of planPromotion(skills, shelf, '').renamed) if (!claims.has(from)) claims.set(from, skill);
  return claims;
}
