#!/usr/bin/env node
/**
 * freeze-text.mjs — ATL-113 D-142 (Q11 a): freeze the listing text no skill folder holds.
 *
 * For some entries zynkr.ai's input / process / output came from a workbench index file no skill
 * folder holds, which no folder approval covers. Under SHELF_ATLAS=enforce the shelf builds
 * every row from the files it holds, so that text is frozen at what zynkr.ai serves at the switch:
 * this tool reads the site's own public answer (/api/skills/details) for the listed entries and
 * writes listing/frozen-text.json — outside skills/, so no folder's tree changes.
 *
 * Each frozen field records `while_files_say`: the sha256 of the text the shelf's own files give for
 * that field now (null for none). The shelf applies the frozen text only while its files still say
 * that; once an approved merge moves the text into the skill's own frontmatter, the file wins.
 *
 *   node tools/freeze-text.mjs --shelf <this checkout> [--ids 1.01,2.02,…] [--site <details URL>]
 *
 * --ids names the entries the first time (sheetIds: the workbench's own registry says which entries'
 * text came from its index file). Without it the entries already in the file are refreshed —
 * run that right before the switch, since `report` still publishes the stage's text until then.
 * Prints counts only.
 */

import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import { Refusal, SITE_DETAILS_URL, refuse } from './common.mjs';
import { IPO_FIELDS, ListingError, deriveFolder, readFrozen, textHash } from './listing.mjs';
import { readShelfState } from './publish.mjs';

const FILE = 'listing/frozen-text.json';
const SHEET_ID_RE = /^\d+\.\d+$/;

const byId = (a, b) => a.localeCompare(b, undefined, { numeric: true });

/** The site's live rows by id (its public /api/skills/details answer). */
async function siteRows(url, fetchImpl) {
  let res;
  try {
    res = await fetchImpl(url, { headers: { Accept: 'application/json', 'User-Agent': 'zynkr-ai-skills-freeze' } });
  } catch (err) {
    refuse(`reading ${url} failed: ${err.message}`);
  }
  if (!res.ok) refuse(`${url} answered ${res.status}`);
  const data = await res.json();
  if (!data || typeof data !== 'object' || Array.isArray(data)) refuse(`${url} did not answer an object`);
  return data;
}

/** The frozen-text document for `ids`, from the site's rows and the shelf's own files. */
export async function freeze({ shelf, ids, url = SITE_DETAILS_URL, fetchImpl = globalThis.fetch, now = () => new Date() }) {
  const rows = await siteRows(url, fetchImpl);
  const state = readShelfState(shelf);
  const built = new Map();
  for (const h of state.folders) {
    try {
      const r = deriveFolder(h.view);
      for (const row of r.rows) built.set(row.id, { row, text: r.fileText.get(row.source_path) });
    } catch (err) {
      if (!(err instanceof ListingError)) throw err;
    }
  }
  const entries = [];
  for (const { id, fields } of ids) {
    if (!SHEET_ID_RE.test(id)) refuse('an id that is no sheetId');
    const site = rows[id];
    const own = built.get(id);
    if (!site || typeof site.slug !== 'string') refuse(`zynkr.ai serves no live row with id ${id}`);
    if (!own) refuse(`the shelf builds no row with id ${id}`);
    if (own.row.slug !== site.slug) refuse(`the row with id ${id} has another slug on the shelf than on zynkr.ai`);
    const entry = { slug: site.slug, id };
    for (const field of fields) {
      const text = site[field];
      if (!(text === null || text === undefined || typeof text === 'string')) refuse(`zynkr.ai's ${field} for id ${id} is not text`);
      entry[field] = { text: text ?? null, while_files_say: textHash(own.text[field]) };
    }
    entries.push(entry);
  }
  entries.sort((a, b) => byId(a.id, b.id));
  return {
    format: 'shelf-frozen-text-v1',
    about:
      'ATL-113 D-142 (Q11 a): input/process/output zynkr.ai served for entries whose text came from a ' +
      "workbench index file no skill folder holds, frozen at the switch. A field applies while the shelf's own " +
      'files still give the text whose sha256 is while_files_say (null: none). Written by tools/freeze-text.mjs.',
    captured_at: now().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    source: url,
    entries,
  };
}

export async function main(argv = process.argv.slice(2), { fetchImpl = globalThis.fetch, log = console.log, error = console.error } = {}) {
  try {
    const { values } = parseArgs({ args: argv, options: { shelf: { type: 'string' }, ids: { type: 'string' }, site: { type: 'string' } } });
    if (!values.shelf) refuse('usage: freeze-text.mjs --shelf <checkout> [--ids 1.01,2.02,…] [--site <details URL>]');
    const shelf = path.resolve(values.shelf);
    const file = path.join(shelf, FILE);
    let ids;
    if (values.ids) {
      ids = values.ids.split(',').map((s) => s.trim()).filter(Boolean).map((id) => ({ id, fields: IPO_FIELDS }));
    } else {
      if (!fs.existsSync(file)) refuse(`${FILE} does not exist yet: name the entries with --ids`);
      const frozen = readFrozen(JSON.parse(fs.readFileSync(file, 'utf8')));
      ids = [...frozen.values()].map((f) => ({ id: f.id, fields: [...f.fields.keys()] }));
    }
    const doc = await freeze({ shelf, ids, url: values.site ?? SITE_DETAILS_URL, fetchImpl });
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, `${JSON.stringify(doc, null, 2)}\n`);
    const bound = doc.entries.reduce((n, e) => n + IPO_FIELDS.filter((f) => e[f]?.while_files_say).length, 0);
    log(`froze ${doc.entries.length} entries into ${FILE} (${bound} fields bound to text the files give, the rest to none)`);
    return 0;
  } catch (err) {
    error(`refused: ${err instanceof Refusal || err instanceof ListingError ? err.message : err.name}`);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main();
}
