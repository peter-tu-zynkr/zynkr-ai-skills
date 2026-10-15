/**
 * SHELF_ATLAS (ATL-113 Part D): rules 1–7, the listings, the frozen text, the order key and the public
 * log, end to end through publish.mjs against a local shelf, a stub Atlas and a stub zynkr.ai. Every
 * skill name here is made up; `quiet-internal-tool` and `acme-portal` stand for a team skill and a
 * client build that must never be named in this repo's public log.
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  RUN_STARTED,
  WB,
  atlasList,
  buildStage,
  deps,
  git,
  head,
  makeShelf,
  network,
  placeOnShelf,
  skill,
  writeFile,
} from './fixtures.mjs';
import { Refusal, SHELF_URL } from './common.mjs';
import { DEFAULT_ATLAS_MODE, atlasMode, idWords } from './enforce.mjs';
import { textHash } from './listing.mjs';
import { main, publish } from './publish.mjs';

const F = (slug, sheetId, spec = {}) => skill(slug, { full: true, sheetId, ...spec });
const opts = (stage, shelf, more = {}) => ({
  stage: stage.root,
  shelf,
  event: 'workflow_dispatch',
  run: stage.run,
  prune: 'true',
  promote: '',
  allowShrink: false,
  allowRewind: false,
  seedFail: false,
  seedAtlas: '',
  dryRun: false,
  ...more,
});
const enforce = (net, env = {}) => deps(net, { SHELF_ATLAS: 'enforce', ...env });
const bodyOf = (net) => JSON.parse(net.posts().at(-1).init.body);
const rowsBy = (net) => Object.fromEntries(bodyOf(net).skills.map((r) => [r.slug, r]));
const listed = (stage, ...slugs) => slugs.map((s) => [stage.dir(s), stage.tree(s)]);
const filesOn = (remote) => git(remote, ['ls-tree', '-r', '--name-only', 'main']);
const fileOn = (remote, p) => git(remote, ['show', `main:${p}`]);
const lastMessage = (remote) => git(remote, ['log', '-1', '--format=%B', 'main']);
const everything = (d, remote) => [...d.out, ...d.err, d.summary(), remote ? git(remote, ['log', '--format=%B', 'main']) : ''].join('\n');
const argv = (stage, shelf, ...more) => ['--stage', stage.root, '--shelf', shelf, '--event', 'schedule', '--run', stage.runFile, ...more];

async function red(promise, pattern) {
  await assert.rejects(promise, (err) => {
    assert.ok(err instanceof Refusal, `expected a Refusal, got ${err?.stack ?? err}`);
    assert.match(err.message, pattern);
    return true;
  });
}

describe('the switch', () => {
  test('unset means off until the switch; anything but off, report or enforce refuses', () => {
    assert.equal(DEFAULT_ATLAS_MODE, 'off');
    assert.deepEqual(atlasMode(undefined), { mode: 'off', explicit: false });
    assert.deepEqual(atlasMode(' enforce '), { mode: 'enforce', explicit: true });
    assert.deepEqual(atlasMode('off'), { mode: 'off', explicit: true });
    assert.throws(() => atlasMode('ENFORCE'), Refusal);
    assert.throws(() => atlasMode('on'), Refusal);
  });

  test('off asks Atlas nothing and reads nothing from the site', async () => {
    const stage = buildStage([F('alpha', '1.01')]);
    const { shelf } = makeShelf();
    const net = network();
    const d = deps(net);
    await publish(opts(stage, shelf, { promote: 'all' }), d);
    assert.equal(net.atlasCalls().length, 0);
    assert.equal(net.calls.filter((c) => c.url.includes('/details')).length, 0);
    assert.match(d.out[0], /^atlas: off \(SHELF_ATLAS is not set\)/);
  });

  test('a SHELF_ATLAS value outside the three refuses before anything happens', async () => {
    const stage = buildStage([F('alpha', '1.01')]);
    const { shelf } = makeShelf();
    const net = network();
    const d = deps(net, { SHELF_ATLAS: 'yes please' });
    assert.equal(await main(argv(stage, shelf), d), 1);
    assert.match(d.err.join('\n'), /SHELF_ATLAS must be off, report or enforce/);
    assert.equal(net.calls.length, 0);
  });
});

describe('rule 1: only an approved tree leaves, byte for byte (AC-12)', () => {
  test('a folder Atlas lists at the staged tree is published; one at another tree keeps the shelf copy', async () => {
    const { shelf, remote } = makeShelf();
    const earlier = buildStage([
      F('alpha', '1.01', { files: { 'references/notes.md': 'one\n' } }),
      F('beta', '1.02', { description: 'Beta, version one.', files: { 'references/notes.md': 'one\n' } }),
    ]);
    placeOnShelf(shelf, earlier, ['alpha', 'beta'], WB.a);
    const stage = buildStage(
      [
        F('alpha', '1.01', { files: { 'references/notes.md': 'two\n' } }),
        F('beta', '1.02', { description: 'Beta, version two.', files: { 'references/notes.md': 'two\n' } }),
        F('gamma', '1.03', { agents: ['helper'] }),
      ],
      { sha: WB.b },
    );
    // alpha's merge was approved (its new tree); beta's was not (Atlas still lists the earlier tree).
    const net = network({ atlas: atlasList([...listed(stage, 'alpha', 'gamma'), [earlier.dir('beta'), earlier.tree('beta')]]) });
    const d = enforce(net);
    const result = await publish(opts(stage, shelf), d);

    assert.equal(result.outcome, 'published');
    assert.equal(fileOn(remote, `${stage.dir('alpha')}/references/notes.md`), 'two\n');
    assert.equal(fileOn(remote, `${stage.dir('beta')}/references/notes.md`), 'one\n', "the shelf keeps beta's approved copy");
    assert.match(filesOn(remote), /gamma\/agents\/helper\.md/);
    const message = lastMessage(remote);
    assert.match(message, /^export: 3 skills from 2222222$/m);
    assert.match(message, /^Added: gamma$/m);
    assert.match(message, /^Changed: alpha$/m);
    assert.match(message, /^Kept as the shelf has it: 1\.02$/m);
    assert.match(message, new RegExp(`Workbench-Commit: ${WB.b}\\s*$`));
    assert.equal(rowsBy(net).beta.description, 'Beta, version one.', 'its row is built from the copy the shelf holds');
    assert.ok(d.out.some((l) => /^rule: publish 2 \(new 1 · changed 1\) · keep 1 · wait 0 · remove 0/.test(l)), d.out.join('\n'));
  });
});

describe('rules 2 and 3: kept, 「as is」, waiting, out', () => {
  test('「as is」 keeps the shelf copy and never publishes; one not on the shelf waits', async () => {
    const { shelf, remote } = makeShelf();
    const earlier = buildStage([F('card', '5.20', { description: 'A card, as the shelf has it.' })]);
    placeOnShelf(shelf, earlier, ['card'], WB.a);
    const stage = buildStage([F('card', '5.20', { description: 'A card, changed upstream.' }), F('other-card', '5.21')], { sha: WB.b });
    const net = network({ atlas: atlasList([], [stage.dir('card'), stage.dir('other-card')]) });
    const d = enforce(net);
    await publish(opts(stage, shelf), d);
    assert.match(fileOn(remote, `${stage.dir('card')}/SKILL.md`), /as the shelf has it/);
    assert.doesNotMatch(filesOn(remote), /other-card/);
    assert.deepEqual(Object.keys(rowsBy(net)), ['card']);
    assert.ok(d.out.some((l) => /waiting for Atlas \(sheetId\): 5\.21/.test(l)));
  });

  test('a folder Atlas does not list leaves, even past half the shelf: Atlas asks, so no shrink guard', async () => {
    const { shelf, remote } = makeShelf();
    const four = ['a1', 'a2', 'a3', 'a4'].map((s, i) => F(s, `2.0${i + 1}`));
    placeOnShelf(shelf, buildStage(four), ['a1', 'a2', 'a3', 'a4'], WB.a);
    const stage = buildStage([...four, F('acme-portal', '3.40')], { sha: WB.b });
    const net = network({ atlas: atlasList(listed(stage, 'a1')) });
    const d = enforce(net);
    await publish(opts(stage, shelf), d);
    assert.deepEqual(filesOn(remote).split('\n').filter((p) => p.startsWith('skills/')), [`${stage.dir('a1')}/SKILL.md`]);
    assert.deepEqual(Object.keys(rowsBy(net)), ['a1']);
    assert.equal(bodyOf(net).allow_shrink, true, "the site's valve does not hold back what Atlas asked to remove");
    assert.match(lastMessage(remote), /^Removed: a2, a3, a4$/m);
    assert.match(lastMessage(remote), /^Waiting for Atlas: 3\.40$/m);
    assert.doesNotMatch(everything(d, remote), /acme-portal/);
  });
});

describe('the listings are the shelf’s own (AC-13)', () => {
  test('a tampered payload changes nothing zynkr.ai gets, for a published, a kept and an 「as is」 folder', async () => {
    const { shelf } = makeShelf();
    const earlier = buildStage([F('kept-one', '4.02', { description: 'Kept, approved text.' }), F('as-is-one', '4.03', { description: 'As is, shelf text.' })]);
    placeOnShelf(shelf, earlier, ['kept-one', 'as-is-one'], WB.a);
    const stage = buildStage(
      [
        F('pub-one', '4.01', { description: 'Published, approved text.' }),
        F('kept-one', '4.02', { description: 'Kept, unapproved text.' }),
        F('as-is-one', '4.03', { description: 'As is, newer text.' }),
      ],
      { sha: WB.b },
    );
    for (const row of stage.payload) {
      row.description = 'Tampered text';
      row.upstream_repo = 'https://evil.example.test/redirect';
      row.input = 'Tampered input';
    }
    stage.payload.push({ ...stage.payload[0], id: '0.02', slug: 'injected-row', name: 'injected-row' });
    stage.save();
    const net = network({ atlas: atlasList([...listed(stage, 'pub-one'), [earlier.dir('kept-one'), earlier.tree('kept-one')]], [stage.dir('as-is-one')]) });
    await publish(opts(stage, shelf), enforce(net));
    const rows = rowsBy(net);
    assert.deepEqual(Object.keys(rows).sort(), ['as-is-one', 'kept-one', 'pub-one']);
    assert.equal(rows['pub-one'].description, 'Published, approved text.');
    assert.equal(rows['kept-one'].description, 'Kept, approved text.');
    assert.equal(rows['as-is-one'].description, 'As is, shelf text.');
    for (const r of Object.values(rows)) {
      assert.equal(r.upstream_repo, undefined);
      assert.equal(r.input, undefined);
      assert.equal(r.repo_url, SHELF_URL);
      assert.equal(r.github_stars, undefined, 'left out: the site keeps its stored counts');
    }
  });

  test('first_seen is carried from the row zynkr.ai holds; a new row gets the run\'s date; the order key is the run\'s own start', async () => {
    const { shelf } = makeShelf();
    placeOnShelf(shelf, buildStage([F('alpha', '1.01')]), ['alpha'], WB.a);
    // The stage claims a commit time far older than anything the site has applied: it is never used.
    const stage = buildStage([F('alpha', '1.01'), F('beta', '1.02')], { sha: WB.b, committedAt: '2020-01-01T00:00:00Z' });
    const net = network({
      atlas: atlasList(listed(stage, 'alpha', 'beta')),
      details: { '1.01': { slug: 'alpha', first_seen: '2026-08-17' }, '9.99': { slug: 'retired-elsewhere', first_seen: '2026-01-01' } },
    });
    await publish(opts(stage, shelf), enforce(net));
    const body = bodyOf(net);
    assert.equal(body.workbench_committed_at, RUN_STARTED);
    assert.equal(body.workbench_sha, WB.b);
    assert.equal(rowsBy(net).alpha.first_seen, '2026-08-17');
    assert.equal(rowsBy(net).beta.first_seen, '2026-10-15');
    assert.equal(rowsBy(net).beta.updated_at, '2026-10-15');
    const details = net.calls.find((c) => c.url.includes('/details'));
    assert.match(details.url, /shelf_run=7001/, 'past the edge cache');
  });

  test('frozen text (D-142) shows while the files still say what they said; it ends when they change', async () => {
    const { shelf } = makeShelf();
    const stage = buildStage([F('alpha', '1.01', { ipo: { input: 'What the file says' } })]);
    placeOnShelf(shelf, stage, ['alpha'], WB.a);
    const freeze = (fileText) => {
      writeFile(shelf, 'listing/frozen-text.json', JSON.stringify({
        format: 'shelf-frozen-text-v1',
        entries: [{ slug: 'alpha', id: '1.01', input: { text: 'What zynkr.ai showed', while_files_say: textHash(fileText) } }],
      }));
    };
    freeze('What the file says');
    let net = network({ atlas: atlasList(listed(stage, 'alpha')) });
    let d = enforce(net);
    await publish(opts(stage, shelf), d);
    assert.equal(rowsBy(net).alpha.input, 'What zynkr.ai showed');
    assert.ok(d.out.some((l) => /frozen text on 1$/.test(l)));

    freeze('What the file said before the move');
    net = network({ atlas: atlasList(listed(stage, 'alpha')) });
    await publish(opts(stage, shelf), enforce(net));
    assert.equal(rowsBy(net).alpha.input, 'What the file says');
  });

  test('when zynkr.ai’s own answer cannot be read, the shelf still changes and nothing is posted', async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(shelf, buildStage([F('alpha', '1.01'), F('beta', '1.02')]), ['alpha', 'beta'], WB.a);
    const stage = buildStage([F('alpha', '1.01'), F('beta', '1.02')], { sha: WB.b });
    const net = network({ atlas: atlasList(listed(stage, 'alpha')), detailsStatus: 502 });
    await red(publish(opts(stage, shelf), enforce(net)), /first_seen cannot be carried, so nothing is posted/);
    assert.doesNotMatch(filesOn(remote), /beta/, "the removal Atlas asked for still reached the shelf, the install source");
    assert.equal(net.posts().length, 0);
  });
});

describe('rule 4: a folder that left the workbench', () => {
  const twoOnShelf = () => {
    const shelves = makeShelf();
    const earlier = buildStage([F('alpha', '1.01'), F('beta', '1.02')]);
    placeOnShelf(shelves.shelf, earlier, ['alpha', 'beta'], WB.a);
    return { ...shelves, earlier };
  };

  test('leaves, even while Atlas still lists it (a team mark, or a deletion: D-76)', async () => {
    const { shelf, remote } = twoOnShelf();
    const stage = buildStage([F('alpha', '1.01')], { sha: WB.b });
    const net = network({ atlas: atlasList([...listed(stage, 'alpha'), ['skills/1-brand-marketing/beta', 'b'.repeat(40)]]) });
    await publish(opts(stage, shelf), enforce(net));
    assert.doesNotMatch(filesOn(remote), /beta/);
    assert.match(lastMessage(remote), /^Removed: beta$/m);
  });

  test('a category move keeps its old place while Atlas lists the old path at the shelf’s tree, and moves when Atlas approves the new one', async () => {
    const moved = () => buildStage([F('alpha', '1.01', { cat: '3-operations' }), F('beta', '1.02')], { sha: WB.b });

    let { shelf, remote, earlier } = twoOnShelf();
    let stage = moved();
    let net = network({ atlas: atlasList([[earlier.dir('alpha'), earlier.tree('alpha')], ...listed(stage, 'beta')]) });
    await publish(opts(stage, shelf), enforce(net));
    assert.match(filesOn(remote), /^skills\/1-brand-marketing\/alpha\/SKILL\.md$/m, 'kept at its old place');
    assert.doesNotMatch(filesOn(remote), /3-operations/);

    // Atlas no longer lists the old path (withdrawn): it goes; the new path waits for its approval.
    ({ shelf, remote, earlier } = twoOnShelf());
    stage = moved();
    net = network({ atlas: atlasList(listed(stage, 'beta')) });
    await publish(opts(stage, shelf), enforce(net));
    assert.doesNotMatch(filesOn(remote), /alpha/);

    // Atlas approves the new path: published there, and the old place goes.
    ({ shelf, remote, earlier } = twoOnShelf());
    stage = moved();
    net = network({ atlas: atlasList([[earlier.dir('alpha'), earlier.tree('alpha')], ...listed(stage, 'alpha', 'beta')]) });
    await publish(opts(stage, shelf), enforce(net));
    assert.match(filesOn(remote), /^skills\/3-operations\/alpha\/SKILL\.md$/m);
    assert.doesNotMatch(filesOn(remote), /1-brand-marketing\/alpha/);
    assert.match(lastMessage(remote), /^Moved or renamed: alpha → alpha$/m);
  });

  test('a decoy rename holds a folder only while Atlas still lists it; the decoy itself waits by sheetId', async () => {
    const { shelf, remote } = makeShelf();
    const earlier = buildStage([F('consult-plan', '2.45'), F('beta', '1.02')]);
    placeOnShelf(shelf, earlier, ['consult-plan', 'beta'], WB.a);
    const decoy = () => buildStage([F('quiet-internal-tool', '2.45', { extra: 'renamed_from: consult-plan' }), F('beta', '1.02')], { sha: WB.b });

    let net = network({ atlas: atlasList([[earlier.dir('consult-plan'), earlier.tree('consult-plan')], [earlier.dir('beta'), earlier.tree('beta')]]) });
    let d = enforce(net);
    await publish(opts(decoy(), shelf), d);
    assert.match(filesOn(remote), /consult-plan\/SKILL\.md/);
    assert.doesNotMatch(filesOn(remote), /quiet-internal-tool/);
    assert.doesNotMatch(everything(d, remote), /quiet-internal-tool/);

    net = network({ atlas: atlasList([[earlier.dir('beta'), earlier.tree('beta')]]) });
    d = enforce(net);
    await publish(opts(decoy(), shelf), d);
    assert.doesNotMatch(filesOn(remote), /consult-plan/, 'the owner withdrew it: the decoy holds nothing');
    assert.doesNotMatch(everything(d, remote), /quiet-internal-tool/);
  });

  test('an approved move of most of the shelf is no shrink: each old place is replaced, not lost', async () => {
    const { shelf, remote } = makeShelf();
    const names = ['m1', 'm2', 'm3', 'm4'];
    placeOnShelf(shelf, buildStage(names.map((s, i) => F(s, `3.0${i + 1}`))), names, WB.a);
    const stage = buildStage(names.map((s, i) => F(s, `3.0${i + 1}`, { cat: '3-operations' })), { sha: WB.b });
    const net = network({ atlas: atlasList(listed(stage, ...names)) });
    await publish(opts(stage, shelf), enforce(net));
    const files = filesOn(remote);
    for (const s of names) assert.match(files, new RegExp(`^skills/3-operations/${s}/SKILL\\.md$`, 'm'));
    assert.doesNotMatch(files, /1-brand-marketing/);
    assert.match(lastMessage(remote), /^Moved or renamed: m1 → m1, m2 → m2, m3 → m3, m4 → m4$/m);
  });
});

describe('rule 5: one side is enough to remove (AC-16, AC-19)', () => {
  const setup = () => {
    const shelves = makeShelf();
    const earlier = buildStage([F('alpha', '1.01', { description: 'Alpha one.' }), F('beta', '1.02')]);
    placeOnShelf(shelves.shelf, earlier, ['alpha', 'beta'], WB.a);
    // alpha changed, beta left the workbench, gamma is new.
    const stage = buildStage([F('alpha', '1.01', { description: 'Alpha two.' }), F('gamma', '1.03')], { sha: WB.b });
    return { ...shelves, earlier, stage };
  };

  test('Atlas unreachable: the folders that left the stage go, nothing new is published, the rows are posted, the run is red', async () => {
    const { shelf, remote, stage } = setup();
    const net = network({ atlas: 'down' });
    const d = enforce(net);
    await red(publish(opts(stage, shelf), d), /Atlas could not be asked \(the door could not be reached\)\. Only the removals one side asked for were made/);
    assert.doesNotMatch(filesOn(remote), /beta/);
    assert.match(fileOn(remote, `${stage.dir('alpha')}/SKILL.md`), /Alpha one\./);
    assert.doesNotMatch(filesOn(remote), /gamma/);
    assert.deepEqual(Object.keys(rowsBy(net)), ['alpha']);
    const message = lastMessage(remote);
    assert.match(message, /^Removed: beta$/m);
    assert.match(message, /^Kept as the shelf has it: 1\.01$/m);
    assert.match(message, /^Waiting for Atlas: 1\.03$/m);
    // The stage was read (its removals were made), so the order check moves on with it.
    assert.match(message, new RegExp(`Workbench-Commit: ${WB.b}\\s*$`));
  });

  test('seeded proofs: a wrong door and a wrong audience are each red, and still remove', async () => {
    for (const [seed, words] of [['unreachable', /could not be reached/], ['wrong_audience', /refused this job's token \(wrong_audience\)/]]) {
      const { shelf, remote, stage } = setup();
      const net = network({ atlas: atlasList(listed(stage, 'alpha', 'gamma')) });
      const d = enforce(net, { GITHUB_ACTIONS: 'true' });
      assert.equal(await main([...argv(stage, shelf), '--seed-atlas', seed], d), 1);
      assert.match(d.err.join('\n'), words);
      assert.doesNotMatch(filesOn(remote), /beta|gamma/);
      assert.equal(net.posts().length, 1);
    }
  });

  test('no stage: the folders Atlas no longer lists go, the rest stays, the rows are posted, the run is red', async () => {
    const { shelf, remote, stage } = setup();
    const net = network({ atlas: atlasList([['skills/1-brand-marketing/alpha', 'c'.repeat(40)]]) });
    const d = enforce(net);
    assert.equal(await main(['--stage', stage.root, '--shelf', shelf, '--event', 'schedule', '--run', path.join(stage.root, 'missing.json')], d), 1);
    assert.match(d.err.join('\n'), /no stage was fetched/);
    assert.doesNotMatch(filesOn(remote), /beta/);
    assert.match(filesOn(remote), /alpha/);
    assert.deepEqual(Object.keys(rowsBy(net)), ['alpha']);
    assert.match(lastMessage(remote), /^export: 1 skill, only the removals Atlas asked for$/m);
  });

  test('a refused stage (seed_fail) is set aside the same way', async () => {
    const { shelf, remote, stage } = setup();
    const net = network({ atlas: atlasList([['skills/1-brand-marketing/alpha', 'c'.repeat(40)]]) });
    const d = enforce(net);
    assert.equal(await main([...argv(stage, shelf), '--seed-fail'], d), 1);
    assert.match(d.err.join('\n'), /the stage was refused: the stage does not match manifest\.json/);
    assert.doesNotMatch(filesOn(remote), /beta/);
    assert.equal(net.posts().length, 1);
  });

  test('a stage claiming a commit time later than its run is refused, and set aside', async () => {
    const { shelf, remote, stage } = setup();
    stage.manifest.workbench_committed_at = '2030-01-01T00:00:00Z';
    stage.save();
    const net = network({ atlas: atlasList(listed(stage, 'alpha', 'gamma')) });
    await red(publish(opts(stage, shelf), enforce(net)), /later than the run that built it/);
    assert.doesNotMatch(filesOn(remote), /gamma/);
    assert.equal(bodyOf(net).workbench_committed_at, RUN_STARTED);
  });

  test('the shrink guard holds back the removals the stage asks for, never those Atlas asks for', async () => {
    const make = () => {
      const shelves = makeShelf();
      const four = ['a1', 'a2', 'a3', 'a4'].map((s, i) => F(s, `2.0${i + 1}`));
      const earlier = buildStage(four);
      placeOnShelf(shelves.shelf, earlier, ['a1', 'a2', 'a3', 'a4'], WB.a);
      return { ...shelves, earlier, stage: buildStage([F('a1', '2.01')], { sha: WB.b }) };
    };
    let { shelf, remote, earlier, stage } = make();
    // The stage drops three of four; Atlas still lists a1–a3 and no longer a4.
    const atlas = atlasList(['a1', 'a2', 'a3'].map((s) => [earlier.dir(s), earlier.tree(s)]));
    let net = network({ atlas });
    await red(publish(opts(stage, shelf), enforce(net)), /leaving under half; dispatch with allow_shrink/);
    const left = filesOn(remote);
    assert.match(left, /a2/);
    assert.match(left, /a3/);
    assert.doesNotMatch(left, /a4/, 'Atlas asked for that one');

    ({ shelf, remote, earlier, stage } = make());
    net = network({ atlas });
    await publish(opts(stage, shelf, { allowShrink: true }), enforce(net));
    assert.doesNotMatch(filesOn(remote), /a2|a3|a4/);
  });

  test('Atlas down and no stage: everything stays, the rows are posted, the run is red', async () => {
    const { shelf, remote, stage } = setup();
    const before = head(remote, 'main');
    const net = network({ atlas: 'down' });
    const d = enforce(net);
    assert.equal(await main(['--stage', stage.root, '--shelf', shelf, '--event', 'schedule', '--run', path.join(stage.root, 'missing.json')], d), 1);
    assert.equal(head(remote, 'main'), before);
    assert.deepEqual(Object.keys(rowsBy(net)).sort(), ['alpha', 'beta']);
  });
});

describe('rule 6: marks and manifests (AC-14)', () => {
  test('a folder with a second manifest, an override, a team sub-agent or a mark YAML reads otherwise waits; the run goes on', async () => {
    const { shelf, remote } = makeShelf();
    const stage = buildStage([
      F('good-one', '6.01'),
      F('nested-one', '6.02', { files: { 'examples/SKILL.md': '---\nname: new-skill\nvisibility: public\n---\n' } }),
      F('override-one', '6.03', { extra: 'install_command: npx skills add https://github.com/someone/else --skill override-one' }),
      F('agent-one', '6.04', { agents: [{ name: 'helper', extra: 'visibility: team' }] }),
      F('split-one', '6.05', { extra: '"visibility": team' }),
      F('claude-one', '6.06', { files: { 'CLAUDE.md': '# not a manifest, but named like one\n' } }),
    ]);
    const net = network({ atlas: atlasList(listed(stage, 'good-one', 'nested-one', 'override-one', 'agent-one', 'split-one', 'claude-one')) });
    const d = enforce(net);
    await publish(opts(stage, shelf), d);
    const files = filesOn(remote);
    assert.match(files, /good-one/);
    for (const s of ['nested-one', 'override-one', 'agent-one', 'split-one', 'claude-one']) assert.doesNotMatch(files, new RegExp(s));
    assert.deepEqual(Object.keys(rowsBy(net)), ['good-one']);
    const reasons = d.out.find((l) => l.includes('why kept or waiting'));
    assert.match(reasons, /a second manifest 2/);
    assert.match(reasons, /an install_command override 1/);
    assert.match(reasons, /a sub-agent marked other than public 1/);
    assert.match(reasons, /its listing does not build \(a frontmatter the shelf cannot read\) 1/);
    assert.match(lastMessage(remote), /^Waiting for Atlas: 6\.02, 6\.03, 6\.04, 6\.05, 6\.06$/m);
  });

  test('on the shelf already, a folder that fails rule 6 keeps its old copy', async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(shelf, buildStage([F('nested-one', '6.02')]), ['nested-one'], WB.a);
    const stage = buildStage([F('nested-one', '6.02', { files: { 'deep/SKILL.md': '---\nname: x\n---\n' } })], { sha: WB.b });
    await publish(opts(stage, shelf), enforce(network({ atlas: atlasList(listed(stage, 'nested-one')) })));
    assert.doesNotMatch(filesOn(remote), /deep\/SKILL\.md/);
    assert.match(filesOn(remote), /nested-one\/SKILL\.md/);
  });
});

describe('rule 7: no two rows share a sheetId, a slug or a name', () => {
  test('a newcomer that collides with a folder the shelf keeps waits; of two newcomers the first by path goes on', async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(shelf, buildStage([F('alpha', '1.01')]), ['alpha'], WB.a);
    const stage = buildStage(
      [F('alpha', '1.01'), F('same-id', '1.01'), F('same-slug', '1.05', { project: 'alpha' }), F('twin-a', '1.07'), F('twin-b', '1.07')],
      { sha: WB.b },
    );
    const net = network({ atlas: atlasList(listed(stage, 'alpha', 'same-id', 'same-slug', 'twin-a', 'twin-b')) });
    const d = enforce(net);
    await publish(opts(stage, shelf), d);
    const files = filesOn(remote);
    assert.match(files, /twin-a/);
    for (const s of ['same-id', 'same-slug', 'twin-b']) assert.doesNotMatch(files, new RegExp(s));
    const ids = bodyOf(net).skills.map((r) => r.id);
    assert.equal(new Set(ids).size, ids.length);
    assert.ok(d.out.some((l) => /its rows would collide with another folder's 3/.test(l)));
  });
});

describe('promote under enforce', () => {
  test('is retired: Atlas is the only way on', async () => {
    const { shelf, remote } = makeShelf();
    const stage = buildStage([F('alpha', '1.01')]);
    const d = enforce(network({ atlas: atlasList() }));
    await publish(opts(stage, shelf, { promote: 'all' }), d);
    assert.doesNotMatch(filesOn(remote), /alpha/);
    assert.ok(d.out.some((l) => /promote is retired under SHELF_ATLAS=enforce/.test(l)));
  });
});

describe('SHELF_ATLAS=report: rehearse, then publish as before', () => {
  test('publishes the stage as before, and prints the plan, the parity check and the token’s claims', async () => {
    const { shelf, remote } = makeShelf();
    const earlier = buildStage([F('beta', '1.02', { description: 'Beta one.' })]);
    placeOnShelf(shelf, earlier, ['beta'], WB.a);
    const stage = buildStage([F('alpha', '1.01'), F('beta', '1.02', { description: 'Beta two.' })], { sha: WB.b });
    stage.payload.find((r) => r.slug === 'alpha').description = 'Changed in the payload';
    stage.save();
    const net = network({ atlas: atlasList([...listed(stage, 'alpha'), [earlier.dir('beta'), earlier.tree('beta')]]) });
    const d = deps(net, { SHELF_ATLAS: 'report' });
    const result = await publish(opts(stage, shelf, { promote: 'all' }), d);
    assert.equal(result.outcome, 'published');
    // As before: the stage is mirrored whole and its payload posted (alpha promoted, beta changed).
    assert.match(fileOn(remote, `${stage.dir('beta')}/SKILL.md`), /Beta two\./);
    assert.equal(rowsBy(net).alpha.description, 'Changed in the payload');
    const out = d.out.join('\n');
    assert.match(out, /^report: enforce would publish 1 \(new 1 · changed 0\) · keep 1 · wait 0 · remove 0/m);
    assert.match(out, /^parity: 2 rows built from the staged files · 2 beside today's · 1 differ \(description 1\)/m);
    assert.match(out, /^parity: rows that differ \(sheetId\): 1\.01$/m);
    assert.match(out, /environment=export/);
    assert.match(d.summary(), /SHELF_ATLAS=report: the rehearsal/);
  });

  test('red when Atlas cannot be asked — after publishing as before', async () => {
    const stage = buildStage([F('alpha', '1.01')]);
    const { shelf, remote } = makeShelf();
    const net = network({ atlas: 'down' });
    await red(publish(opts(stage, shelf, { promote: 'all' }), deps(net, { SHELF_ATLAS: 'report' })), /SHELF_ATLAS=report: Atlas could not be asked/);
    assert.match(filesOn(remote), /alpha/);
    assert.equal(net.posts().length, 1);
  });
});

describe('the public log (AC-20, D-73)', () => {
  test('names what it publishes or removes by slug and what it holds by sheetId — never a held or team name, never Atlas’s answer', async () => {
    const { shelf, remote } = makeShelf();
    const earlier = buildStage([F('beta', '1.02'), F('gone-public', '1.04')]);
    placeOnShelf(shelf, earlier, ['beta', 'gone-public'], WB.a);
    const stage = buildStage(
      [
        F('alpha', '1.01'),
        F('beta', '1.02', { description: 'Beta two.' }),
        F('acme-portal', '3.40'),
        F('quiet-internal-tool', '3.41', { files: { 'examples/SKILL.md': '---\nname: quiet-internal-tool-nested\n---\n' } }),
        F('hidden-sheetless', 'x.yz'),
      ],
      { sha: WB.b },
    );
    const secretTree = 'e'.repeat(40);
    const net = network({
      atlas: atlasList([...listed(stage, 'alpha', 'quiet-internal-tool'), [earlier.dir('beta'), earlier.tree('beta')], ['skills/9-legal/unrelated-listed', secretTree]]),
    });
    const d = enforce(net, { GITHUB_ACTIONS: 'true' });
    const code = await main(argv(stage, shelf), d);
    assert.equal(code, 0, d.err.join('\n'));
    const text = everything(d, remote);
    for (const word of ['acme-portal', 'quiet-internal-tool', 'hidden-sheetless', 'unrelated-listed', secretTree]) {
      assert.ok(!text.includes(word), `"${word}" reached the public log`);
    }
    assert.match(text, /new on the shelf: alpha/);
    assert.match(text, /removed: gone-public/);
    assert.match(text, /waiting for Atlas \(sheetId\): 3\.40, 3\.41, 1 skill with no sheetId/);
    assert.match(text, /kept as the shelf has it \(sheetId\): 1\.02/);
  });

  test('idWords never prints what is no sheetId', () => {
    assert.deepEqual(idWords(['3.41', 'acme-portal', null, '3.41', '1.02']), ['1.02', '3.41', '2 skills with no sheetId']);
  });

  test('a dry run prints the plan in the same words, and changes nothing', async () => {
    const { shelf, remote } = makeShelf();
    const before = head(remote, 'main');
    const stage = buildStage([F('alpha', '1.01'), F('acme-portal', '3.40')]);
    const net = network({ atlas: atlasList(listed(stage, 'alpha')) });
    const d = enforce(net);
    const result = await publish(opts(stage, shelf, { dryRun: true }), d);
    assert.equal(result.outcome, 'dry-run');
    assert.equal(head(remote, 'main'), before);
    assert.equal(net.posts().length, 0);
    assert.ok(!everything(d).includes('acme-portal'));
    assert.ok(fs.existsSync(shelf));
  });
});
