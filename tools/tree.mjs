/**
 * tree.mjs — a folder's git tree id, from its files' paths, modes and blob shas (ATL-113 Part D).
 *
 * Atlas records each approved version of a public skill as the git tree id of its folder, and that
 * id is the same in the workbench, the stage and the shelf (94/94, 2026-10-11). So "is this the
 * folder Atlas approved, byte for byte?" is one comparison: the tree id recomputed here from what
 * the stage holds (or what the shelf holds) against the tree Atlas lists. git's own rule: entries
 * sorted by name, with a folder compared as its name plus "/"; a file is `<mode> <name>\0<sha>`,
 * a folder `40000 <name>\0<sha>`; the id is the sha1 of `tree <length>\0` and those bytes.
 */

import crypto from 'node:crypto';

const MODES = new Set(['100644', '100755']);
const SHA_RE = /^[0-9a-f]{40}$/;

function hashTree(children) {
  const items = [...children].map(([name, node]) => ({
    name,
    node,
    key: Buffer.from(node.kind === 'dir' ? `${name}/` : name, 'utf8'),
  }));
  items.sort((a, b) => Buffer.compare(a.key, b.key));
  const parts = [];
  for (const { name, node } of items) {
    const mode = node.kind === 'dir' ? '40000' : node.mode;
    const sha = node.kind === 'dir' ? hashTree(node.children) : node.sha;
    parts.push(Buffer.from(`${mode} ${name}\0`, 'utf8'), Buffer.from(sha, 'hex'));
  }
  const body = Buffer.concat(parts);
  return crypto.createHash('sha1').update(`tree ${body.length}\0`).update(body).digest('hex');
}

/**
 * git's tree id for a folder holding `entries`: [{ path, mode, sha }], each path relative to the
 * folder ("SKILL.md", "agents/helper.md"). Throws on a path that is no plain relative file path.
 */
export function treeId(entries) {
  if (!entries.length) throw new Error('a tree needs at least one file');
  const root = new Map();
  for (const e of entries) {
    if (!MODES.has(e.mode) || !SHA_RE.test(String(e.sha))) throw new Error('a tree entry needs mode 100644|100755 and a 40-hex sha');
    const parts = String(e.path).split('/');
    if (parts.some((p) => p === '' || p === '.' || p === '..')) throw new Error('a tree entry needs a plain relative path');
    let node = root;
    for (const part of parts.slice(0, -1)) {
      let child = node.get(part);
      if (!child) {
        child = { kind: 'dir', children: new Map() };
        node.set(part, child);
      } else if (child.kind !== 'dir') {
        throw new Error('a path is both a file and a folder');
      }
      node = child.children;
    }
    const name = parts.at(-1);
    if (node.has(name)) throw new Error('a path appears twice');
    node.set(name, { kind: 'file', mode: e.mode, sha: e.sha });
  }
  return hashTree(root);
}
