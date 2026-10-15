/**
 * manifest.mjs — the shelf's own line-based reading of a manifest's frontmatter (SKB-038), shared by
 * publish.mjs and the listing builder. Moved here unchanged from publish.mjs, which re-exports it.
 */

export const NAME_RE = /^[a-z0-9][a-z0-9-]*$/;
export const OVERRIDE_RE =
  /^npx skills add https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+ --skill [a-z0-9][a-z0-9-]*$/;
export const MANIFEST_NAMES = new Set(['SKILL.md', 'CLAUDE.md']);

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

/** One frontmatter key as a non-empty string; missing, empty or repeated → null. */
const keyOf = (fm, key) => {
  const v = fm && !fm.dupes.has(key) ? fm.keys.get(key) : null;
  return typeof v === 'string' && v !== '' ? v : null;
};

/** A manifest's sheetId: the skill's pinned id, which a rename keeps. */
export const sheetIdOf = (fm) => keyOf(fm, 'sheetId');

/** A manifest's `renamed_from`: the name the skill had before a rename, written by whoever renamed it. */
export const renamedFromOf = (fm) => keyOf(fm, 'renamed_from');

/** A manifest's `name` as the shelf reads it (one plain line), or null. */
export const nameOf = (fm) => keyOf(fm, 'name');
