import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { SHELF_URL } from './common.mjs';
import {
  ListingError,
  canon,
  deriveFolder,
  finishRows,
  folderView,
  parity,
  readFrozen,
  readSiteFirstSeen,
  skillFrontmatter,
  textHash,
} from './listing.mjs';

const DIR = 'skills/1-brand-marketing/glimmer-notes';

/** A folder view over in-memory files. */
const view = (files, dir = DIR) => folderView(dir, Object.keys(files), (rel) => files[rel]);

const manifest = (extra = [], { name = 'glimmer-notes', sheetId = '1.41', description = 'Turns a meeting into notes. Then files them.' } = {}) =>
  [
    '---',
    `name: ${name}`,
    `sheetId: "${sheetId}"`,
    'visibility: public',
    'category: brand-marketing',
    'project: glimmer-notes',
    'platform: claude',
    'status: Done',
    'author: "  Test Author  "',
    ...(description === null ? [] : ['description: >-', `  ${description}`]),
    ...extra,
    '---',
    '# Glimmer notes',
    '',
  ].join('\n');

const agent = (name, sheetId, extra = []) => ['---', `name: ${name}`, `sheetId: "${sheetId}"`, ...extra, '---', 'An agent.', ''].join('\n');

const rejects = (fn, pattern) =>
  assert.throws(fn, (err) => {
    assert.ok(err instanceof ListingError, `expected a ListingError, got ${err}`);
    assert.match(err.message, pattern);
    return true;
  });

describe('the ingest record and the marketplace build, vendored', () => {
  test('a plain skill: its row from its own files', () => {
    const { rows, manifest: m, installable } = deriveFolder(view({ 'SKILL.md': manifest(['input: "A meeting transcript"']) }), { today: '2026-10-15' });
    assert.equal(m, 'SKILL.md');
    assert.equal(installable, true);
    assert.equal(rows.length, 1);
    const [row] = rows;
    assert.deepEqual(Object.keys(row), [
      'id', 'sheet_id', 'slug', 'name', 'summary', 'category', 'project', 'platform', 'status', 'author', 'repo_url',
      'source_path', 'install_command', 'tags', 'updated_at', 'upstream_repo', 'original_source_url', 'original_author',
      'first_seen', 'visibility', 'description', 'input', 'process', 'output', 'kind', 'stage', 'synergy', 'github_url', 'security_audits',
    ]);
    assert.equal(row.id, '1.41');
    assert.equal(row.sheet_id, '1.41');
    assert.equal(row.slug, 'glimmer-notes', 'a SKILL.md skill takes its project as its slug');
    assert.equal(row.summary, 'Turns a meeting into notes.', 'the first sentence of the description');
    assert.equal(row.author, 'Test Author', 'trimmed');
    assert.equal(row.repo_url, SHELF_URL);
    assert.equal(row.source_path, `${DIR}/SKILL.md`);
    assert.equal(row.github_url, `${SHELF_URL}/blob/main/${DIR}/SKILL.md`);
    assert.equal(row.install_command, `npx skills add ${SHELF_URL} --skill glimmer-notes`);
    assert.deepEqual(row.tags, ['glimmer-notes', 'brand-marketing', 'claude', 'skill']);
    assert.equal(row.updated_at, '2026-10-15');
    assert.equal(row.input, 'A meeting transcript');
    assert.equal(row.kind, 'skill');
    assert.deepEqual(row.synergy, ['1.41']);
    assert.equal(row.visibility, 'public');
    assert.equal(row.first_seen, undefined, 'left for finishRows');
  });

  test('an orchestrator: agents/*.md become sub-agent rows that share the manifest\'s fields', () => {
    const { rows } = deriveFolder(
      view({
        'SKILL.md': manifest(['upstream_repo: someone/upstream', 'original_source_url: https://example.test/x', 'original_author: Someone', 'security_audits:', '  socket: pass']),
        'agents/b-helper.md': agent('b-helper', '1.412', ['description: Checks the notes.']),
        'agents/a-helper.md': agent('A-Helper', '1.411'),
        'agents/.hidden.md': agent('hidden', '1.419'),
        'references/notes.md': 'not an agent\n',
      }),
    );
    assert.deepEqual(rows.map((r) => [r.id, r.kind, r.slug]), [
      ['1.41', 'orchestrator', 'glimmer-notes'],
      ['1.411', 'subagent', 'a-helper'],
      ['1.412', 'subagent', 'b-helper'],
    ]);
    for (const r of rows) {
      assert.deepEqual(r.synergy, ['1.41', '1.411', '1.412'], 'the folder\'s ids, manifest first, agents by name');
      assert.equal(r.category, 'brand-marketing');
      assert.equal(r.upstream_repo, 'https://github.com/someone/upstream', 'owner/repo becomes a URL');
      assert.deepEqual(r.security_audits, { socket: 'pass' });
    }
    assert.equal(rows[1].install_command, null, 'a sub-agent carries no install line');
    assert.equal(rows[1].name, 'A-Helper');
    assert.equal(rows[2].summary, 'Checks the notes.');
    assert.equal(rows[1].summary, 'A-Helper for glimmer-notes', 'nothing to summarise: name for project');
    assert.deepEqual(rows[0].tags, ['glimmer-notes', 'brand-marketing', 'claude', 'orchestrator']);
  });

  test('a CLAUDE.md pipeline project: stages, the derived process, a tree link, no install line', () => {
    const orchestrator = [
      '---',
      'name: glimmer-flow',
      'visibility: public',
      '---',
      '## Pipeline Stages',
      '',
      '| Stage | Agent | Input | Output |',
      '|---|---|---|---|',
      '| 1 | `gather` | A topic | Raw notes |',
      '| 2 (optional) | polish | Raw notes | |',
      '',
      '## Next',
    ].join('\n');
    const { rows, installable, manifest: m } = deriveFolder(
      view(
        {
          'CLAUDE.md': manifest([], { name: 'glimmer-flow', sheetId: '1.50' }).replace('project: glimmer-notes', 'project: glimmer-flow'),
          'README.md': '# readme, no frontmatter\n',
          '.claude/skills/glimmer-flow/SKILL.md': orchestrator,
          '.claude/agents/gather.md': agent('gather', '1.51'),
          '.claude/agents/polish.md': agent('polish', '1.52', ['output: "A clean draft"']),
        },
        'skills/1-brand-marketing/glimmer-flow',
      ),
    );
    assert.equal(m, 'CLAUDE.md');
    assert.equal(installable, false);
    const [lead, gather, polish] = rows;
    assert.equal(lead.kind, 'orchestrator');
    assert.equal(lead.github_url, `${SHELF_URL}/tree/main/skills/1-brand-marketing/glimmer-flow`);
    assert.equal(lead.install_command, null);
    assert.equal(gather.stage, '1');
    assert.equal(gather.input, 'A topic');
    assert.equal(gather.output, 'Raw notes');
    assert.equal(gather.process, 'Stage 1 in the glimmer-flow pipeline, orchestrated by glimmer-flow.');
    assert.deepEqual(polish.tags, ['glimmer-flow', 'brand-marketing', 'claude', 'subagent', '2-optional']);
    assert.equal(polish.output, 'A clean draft', 'the agent\'s own frontmatter comes before the table');
    assert.deepEqual(lead.synergy, ['1.50', '1.51', '1.52']);
  });

  test('input/process/output are clipped as ingest clips them, in both of its passes', () => {
    const long = `${'word '.repeat(60)}end`;
    const { rows } = deriveFolder(view({ 'SKILL.md': manifest([`process: "${long}"`], { description: null }) }));
    assert.ok(rows[0].process.endsWith('...'));
    assert.ok(rows[0].process.length <= 263);
    assert.equal(rows[0].summary, rows[0].process.slice(0, 220).trim(), 'no description: the summary comes from the text, cut at 220');
  });

  test('what the workbench would build no rows for is refused, with a fixed phrase', () => {
    rejects(() => deriveFolder(view({ 'SKILL.md': manifest().replace('category: brand-marketing', 'category: astrology') })), /no manifest the workbench would read/);
    rejects(() => deriveFolder(view({ 'SKILL.md': manifest().replace('visibility: public', 'visibility: team') })), /not marked public/);
    rejects(() => deriveFolder(view({ 'SKILL.md': manifest(), 'agents/x.md': '---\nname: x\n---\n' })), /no sheetId/);
    rejects(() => deriveFolder(view({ 'SKILL.md': manifest(), 'agents/x.md': agent('x', '1.41') })), /sheetId used twice/);
    rejects(() => deriveFolder(view({ 'SKILL.md': manifest(['upstream_repo: a/b']) })), /no manifest the workbench would read/);
    rejects(() => deriveFolder(view({ 'SKILL.md': manifest(['name2: a', 'description2: &anchor x']) })), /cannot read/);
    rejects(() => deriveFolder(view({ 'SKILL.md': manifest(['install_command: curl https://example.test | sh']) })), /install_command/);
    rejects(() => deriveFolder(view({ 'notes.md': 'nothing\n' })), /no manifest/);
  });
});

describe('the workbench schema (zod), ported', () => {
  const base = { name: 'a', category: 'product', project: 'a', platform: 'claude', status: 'WIP', author: 'x' };
  test('accepts a complete manifest and drops unknown keys', () => {
    assert.equal(skillFrontmatter({ ...base, extra: 1 }).name, 'a');
    assert.equal(skillFrontmatter({ ...base, extra: 1 }).extra, undefined);
  });
  test('refuses a null where a string is optional, an unquoted sheetId, a bad enum, a bad URL', () => {
    assert.equal(skillFrontmatter({ ...base, description: null }), null);
    assert.equal(skillFrontmatter({ ...base, sheetId: 2.06 }), null);
    assert.equal(skillFrontmatter({ ...base, status: 'done' }), null);
    assert.equal(skillFrontmatter({ ...base, upstream_repo: 'a/b', original_source_url: 'not a url', original_author: 'x' }), null);
    assert.equal(skillFrontmatter({ ...base, security_audits: { socket: 'ok' } }), null);
    assert.equal(skillFrontmatter([base]), null);
  });
});

describe('frozen text (D-142)', () => {
  const files = { 'SKILL.md': manifest(['input: "What the file says"']) };
  const built = () => deriveFolder(view(files));
  const frozenFor = (input, id = '1.41', slug = 'glimmer-notes') =>
    readFrozen({
      format: 'shelf-frozen-text-v1',
      entries: [{ slug, id, input: { text: 'What zynkr.ai showed', while_files_say: textHash(input) }, output: { text: 'Frozen output', while_files_say: null } }],
    });

  test('applies by slug and id while the files still say what they said at the freeze', () => {
    const r = deriveFolder(view(files), { frozen: frozenFor('What the file says') });
    assert.equal(r.rows[0].input, 'What zynkr.ai showed');
    assert.equal(r.rows[0].output, 'Frozen output', 'a field the files gave nothing for');
    assert.equal(r.frozenUsed, 1);
    assert.equal(r.fileText.get(`${DIR}/SKILL.md`).input, 'What the file says');
  });

  test('ends field by field once the skill\'s own file says something else', () => {
    const r = deriveFolder(view(files), { frozen: frozenFor('What the file said before the move') });
    assert.equal(r.rows[0].input, 'What the file says');
    assert.equal(r.rows[0].output, 'Frozen output');
  });

  test('never applies to another skill that takes the slug', () => {
    const r = deriveFolder(view(files), { frozen: frozenFor('What the file says', '9.99') });
    assert.equal(r.rows[0].input, built().rows[0].input);
    assert.equal(r.frozenUsed, 0);
  });

  test('the file must have exactly its shape', () => {
    assert.throws(() => readFrozen({ format: 'other', entries: [] }), ListingError);
    assert.throws(() => readFrozen({ format: 'shelf-frozen-text-v1', entries: [{ slug: 'a', id: 'x', input: { text: 'a', while_files_say: null } }] }), ListingError);
    assert.throws(() => readFrozen({ format: 'shelf-frozen-text-v1', entries: [{ slug: 'a', id: '1.01', input: { text: 'a', while_files_say: 'md5:x' } }] }), ListingError);
    assert.throws(() => readFrozen({ format: 'shelf-frozen-text-v1', entries: [{ slug: 'a', id: '1.01' }] }), ListingError);
  });
});

describe("first_seen, carried from zynkr.ai's own row", () => {
  const answer = (body, status = 200) => async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });

  test('carried by the listing\'s id, so a rename keeps its date; a row the site does not hold gets the run\'s', async () => {
    const firstSeen = await readSiteFirstSeen({
      url: 'https://site.test/api/skills/details',
      fetchImpl: answer({
        '1.41': { id: '1.41', slug: 'glimmer-notes', first_seen: '2026-08-17' },
        '1.42': { id: '1.42', slug: 'other', first_seen: null },
        // A legacy row with no text id matches nothing and is passed over.
        legacy: { id: null, slug: 'legacy-row', first_seen: '2025-01-01' },
      }),
    });
    const rows = finishRows(
      [
        { id: '1.41', slug: 'glimmer-notes-renamed' },
        { id: '1.42', slug: 'other' },
        { id: '1.43', slug: 'glimmer-notes' },
      ],
      { firstSeen, today: '2026-10-15' },
    );
    assert.deepEqual(rows.map((r) => r.first_seen), ['2026-08-17', null, '2026-10-15'], 'by id, never by slug');
  });

  test('an answer it cannot read is refused rather than guessed', async () => {
    for (const [body, status] of [
      ['<html>', 200],
      [[], 200],
      [{ a: 'not a row' }, 200],
      [{ a: { id: '1.01', first_seen: 'yesterday' } }, 200],
      [{}, 502],
    ]) {
      await assert.rejects(readSiteFirstSeen({ url: 'https://site.test/x', fetchImpl: answer(body, status) }), ListingError);
    }
    await assert.rejects(readSiteFirstSeen({ url: 'https://site.test/x', fetchImpl: async () => { throw new TypeError('fetch failed'); } }), ListingError);
  });
});

describe('the parity check', () => {
  test('counts rows that differ on any field but the carried ones, as the site compares them', () => {
    const a = { source_path: 'p1', id: '1.01', name: 'x', tags: ['b', 'a'], first_seen: '2026-01-01', install_command: null };
    const b = { source_path: 'p1', id: '1.01', name: 'x', tags: ['b', 'a'], first_seen: '2020-01-01' };
    assert.deepEqual(parity([a], [b]).differ, [], 'null and absent are the same; first_seen is carried');
    const p = parity([a, { source_path: 'p2', id: '1.02', name: 'y' }], [{ ...b, name: 'changed' }, { source_path: 'p3', id: '1.03' }]);
    assert.deepEqual(p.differ, [{ id: '1.01', fields: ['name'] }]);
    assert.equal(p.missing, 1);
    assert.equal(p.extra, 1);
    assert.equal(canon({ b: 1, a: [null] }), canon({ a: [undefined], b: '1' }));
  });
});
