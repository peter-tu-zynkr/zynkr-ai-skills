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
  scratch,
  skill,
  writeFile,
} from './fixtures.mjs';
import { Refusal, SHELF_URL, unexpectedWords } from './common.mjs';
import { DEFAULT_ATLAS_MODE, atlasMode, idWords } from './enforce.mjs';
import { textHash } from './listing.mjs';
import { MAX_STAGE_FOLDERS, main, publish, readStage, stageIndexEnforce } from './publish.mjs';

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
  test('unset means enforce since the switch; anything but off, report or enforce refuses', () => {
    assert.equal(DEFAULT_ATLAS_MODE, 'enforce');
    assert.deepEqual(atlasMode(undefined), { mode: 'enforce', explicit: false });
    assert.deepEqual(atlasMode(''), { mode: 'enforce', explicit: false });
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
    assert.match(d.out[0], /^atlas: off \(SHELF_ATLAS=off, set on purpose\)/);
  });

  test('unset runs enforce, says it is the default, and asks Atlas', async () => {
    const { shelf, remote } = makeShelf();
    const stage = buildStage([F('alpha', '1.01')]);
    const net = network({ atlas: atlasList(listed(stage, 'alpha')) });
    const d = deps(net, { SHELF_ATLAS: '' });
    const result = await publish(opts(stage, shelf), d);
    assert.equal(result.outcome, 'published');
    assert.equal(net.atlasCalls().length, 1);
    assert.match(d.out[0], /^atlas: enforce \(SHELF_ATLAS is not set: the default\)/);
    assert.match(filesOn(remote), /alpha\/SKILL\.md/);
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

  test('a folder Atlas does not list leaves, even past half the shelf: Atlas asks, so no shrink guard here, and the site keeps its valve', async () => {
    const { shelf, remote } = makeShelf();
    const four = ['a1', 'a2', 'a3', 'a4'].map((s, i) => F(s, `2.0${i + 1}`));
    placeOnShelf(shelf, buildStage(four), ['a1', 'a2', 'a3', 'a4'], WB.a);
    const stage = buildStage([...four, F('acme-portal', '3.40')], { sha: WB.b });
    const net = network({ atlas: atlasList(listed(stage, 'a1')) });
    const d = enforce(net);
    await publish(opts(stage, shelf), d);
    assert.deepEqual(filesOn(remote).split('\n').filter((p) => p.startsWith('skills/')), [`${stage.dir('a1')}/SKILL.md`]);
    assert.deepEqual(Object.keys(rowsBy(net)), ['a1']);
    assert.equal(bodyOf(net).allow_shrink, undefined, "the site keeps its valve: choice 3 was dropped (16 Oct)");
    assert.match(lastMessage(remote), /^Removed: a2, a3, a4$/m);
    assert.match(lastMessage(remote), /^Waiting for Atlas: 3\.40$/m);
    assert.doesNotMatch(everything(d, remote), /acme-portal/);
  });

  test('a run dispatched with allow_shrink lets the site prune what Atlas asked to remove', async () => {
    const { shelf } = makeShelf();
    const four = ['a1', 'a2', 'a3', 'a4'].map((s, i) => F(s, `2.0${i + 1}`));
    placeOnShelf(shelf, buildStage(four), ['a1', 'a2', 'a3', 'a4'], WB.a);
    const stage = buildStage(four, { sha: WB.b });
    const net = network({ atlas: atlasList(listed(stage, 'a1')) });
    await publish(opts(stage, shelf, { allowShrink: true }), enforce(net));
    assert.equal(bodyOf(net).allow_shrink, true);
    assert.deepEqual(Object.keys(rowsBy(net)), ['a1']);
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

  test('first_seen is carried by id from the row zynkr.ai holds, through a rename; a new row gets the run\'s date; the order key is the run\'s own start', async () => {
    const { shelf } = makeShelf();
    placeOnShelf(shelf, buildStage([F('alpha', '1.01')]), ['alpha'], WB.a);
    // The stage claims a commit time far older than anything the site has applied: it is never used.
    const stage = buildStage([F('alpha', '1.01'), F('beta', '1.02'), F('gamma', '1.03')], { sha: WB.b, committedAt: '2020-01-01T00:00:00Z' });
    const net = network({
      atlas: atlasList(listed(stage, 'alpha', 'beta', 'gamma')),
      details: {
        '1.01': { id: '1.01', slug: 'alpha', first_seen: '2026-08-17' },
        // gamma's skill, listed on zynkr.ai under the name it had before a rename: same sheetId.
        '1.03': { id: '1.03', slug: 'gamma-before-rename', first_seen: '2026-05-05' },
        '9.99': { id: '9.99', slug: 'retired-elsewhere', first_seen: '2026-01-01' },
      },
    });
    await publish(opts(stage, shelf), enforce(net));
    const body = bodyOf(net);
    assert.equal(body.workbench_committed_at, RUN_STARTED);
    assert.equal(body.workbench_sha, WB.b);
    assert.equal(rowsBy(net).alpha.first_seen, '2026-08-17');
    assert.equal(rowsBy(net).gamma.first_seen, '2026-05-05', 'a renamed skill keeps its date');
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
    // The door names no reason (every refusal is the same 401); the run says what it seeded.
    for (const [seed, words] of [
      ['unreachable', /the door could not be reached \(a seeded dispatch: a door address that never resolves\)/],
      ['wrong_audience', /Atlas refused this job's token \(a seeded dispatch: a token asked for another audience\)/],
    ]) {
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

// Review round 1 (qa3): nothing the stage holds may stop the removals Atlas asks for, and a stage the
// shrink guard set aside is not recorded as taken.
describe('rule 5, whatever the stage holds', () => {
  const threeOnShelf = () => {
    const shelves = makeShelf();
    const earlier = buildStage([F('alpha', '1.01'), F('beta', '1.02'), F('gamma', '1.03')]);
    placeOnShelf(shelves.shelf, earlier, ['alpha', 'beta', 'gamma'], WB.a);
    // Atlas withdrew gamma: it lists alpha and beta at the trees the shelf holds.
    const atlas = atlasList([[earlier.dir('alpha'), earlier.tree('alpha')], [earlier.dir('beta'), earlier.tree('beta')]]);
    return { ...shelves, earlier, atlas };
  };

  // A file the runner cannot read throws EACCES, not a refusal. Root reads it anyway, so this cannot
  // be shown as root.
  const asRoot = typeof process.getuid === 'function' && process.getuid() === 0;
  test('a staged file the runner cannot read sets the stage aside: Atlas is still asked and its removals made', { skip: asRoot && 'root reads a mode-000 file' }, async () => {
    const { shelf, remote, atlas } = threeOnShelf();
    const stage = buildStage([F('alpha', '1.01', { files: { 'references/extra.md': 'x\n' } }), F('beta', '1.02'), F('gamma', '1.03')], { sha: WB.b });
    const unreadable = path.join(stage.stageRoot, stage.dir('alpha'), 'references/extra.md');
    fs.chmodSync(unreadable, 0o000);
    try {
      const net = network({ atlas });
      const d = enforce(net, { GITHUB_ACTIONS: 'true' });
      assert.equal(await main(argv(stage, shelf), d), 1);
      assert.equal(net.atlasCalls().length, 1, 'Atlas was asked');
      assert.doesNotMatch(filesOn(remote), /gamma/, 'the withdrawal reached the shelf');
      assert.equal(net.posts().length, 1, 'and zynkr.ai');
      assert.deepEqual(Object.keys(rowsBy(net)).sort(), ['alpha', 'beta']);
      const text = everything(d, remote);
      assert.match(text, /the stage was refused: the stage could not be read \(unexpected failure: Error EACCES/);
      assert.doesNotMatch(text, /extra\.md|shelf-tests-/, 'the error says what kind, never which path');
    } finally {
      fs.chmodSync(unreadable, 0o644);
    }
  });

  test(`a stage of more than ${MAX_STAGE_FOLDERS} folders is refused unread, at once`, { timeout: 15_000 }, () => {
    // 40,000 folders took 75 s in the old pairwise checks; refused by count now, before any is read.
    const root = scratch('huge-stage');
    const stageRoot = path.join(root, 'stage');
    fs.mkdirSync(path.join(stageRoot, 'skills'), { recursive: true });
    const sha = 'a'.repeat(40);
    const skills = [];
    const files = [];
    for (let i = 0; i < 40_000; i++) {
      skills.push({ dir: `skills/c/s${i}`, manifest: `skills/c/s${i}/SKILL.md`, slug: `s${i}`, name: `s${i}`, installable: true });
      files.push({ path: `skills/c/s${i}/SKILL.md`, mode: '100644', sha });
    }
    fs.writeFileSync(path.join(stageRoot, 'manifest.json'), JSON.stringify({ format: 'stage-v1', workbench_sha: sha, workbench_committed_at: '2026-10-15T00:00:00Z', files, skills }));
    fs.writeFileSync(path.join(stageRoot, 'payload.json'), '[]');
    assert.throws(() => readStage(stageRoot), (err) => {
      assert.ok(err instanceof Refusal);
      assert.match(err.message, /manifest\.json lists 40000 skill folders, more than the 5000 a stage may hold/);
      return true;
    });
  });

  test('at the bound the folder checks stay linear, and still catch a nested or repeated folder', { timeout: 15_000 }, () => {
    const make = (extra) => {
      const root = scratch('bound-stage');
      const stageRoot = path.join(root, 'stage');
      fs.mkdirSync(path.join(stageRoot, 'skills'), { recursive: true });
      const sha = 'a'.repeat(40);
      const skills = [];
      const files = [];
      for (let i = 0; i < MAX_STAGE_FOLDERS - 1; i++) {
        skills.push({ dir: `skills/c/s${i}`, manifest: `skills/c/s${i}/SKILL.md`, slug: `s${i}`, name: `s${i}`, installable: true });
        files.push({ path: `skills/c/s${i}/SKILL.md`, mode: '100644', sha });
      }
      skills.push(extra);
      files.push({ path: extra.manifest, mode: '100644', sha });
      fs.writeFileSync(path.join(stageRoot, 'manifest.json'), JSON.stringify({ format: 'stage-v1', workbench_sha: sha, workbench_committed_at: '2026-10-15T00:00:00Z', files, skills }));
      fs.writeFileSync(path.join(stageRoot, 'payload.json'), '[]');
      return stageRoot;
    };
    const refusedWith = (stageRoot, pattern) =>
      assert.throws(() => readStage(stageRoot), (err) => err instanceof Refusal && pattern.test(err.message));
    const t0 = Date.now();
    refusedWith(make({ dir: 'skills/c/s7/inner', manifest: 'skills/c/s7/inner/SKILL.md', slug: 'x', name: 'x', installable: true }), /nests one inside another/);
    refusedWith(make({ dir: 'skills/c', manifest: 'skills/c/SKILL.md', slug: 'y', name: 'y', installable: true }), /nests one inside another/);
    // A clean manifest of 5,000 folders passes the shape checks; the tree check then finds no files.
    refusedWith(make({ dir: 'skills/d/last', manifest: 'skills/d/last/SKILL.md', slug: 'z', name: 'z', installable: true }), /5000 listed files missing/);
    assert.ok(Date.now() - t0 < 10_000, 'three checks of 5,000 folders, in well under the pairwise time');
  });

  test('a stage the shrink guard sets aside is not recorded as taken', async () => {
    const { shelf, remote } = makeShelf();
    const earlier = buildStage([F('alpha', '1.01'), F('beta', '1.02'), F('gamma', '1.03'), F('delta', '1.04')]);
    placeOnShelf(shelf, earlier, ['alpha', 'beta', 'gamma', 'delta'], WB.a);
    // The stage drops three of four folders; Atlas withdrew delta and lists the other three.
    const stage = buildStage([F('alpha', '1.01')], { sha: WB.b });
    const net = network({ atlas: atlasList(['alpha', 'beta', 'gamma'].map((s) => [earlier.dir(s), earlier.tree(s)])) });
    const d = enforce(net);
    assert.equal(await main(argv(stage, shelf), d), 1);
    const message = lastMessage(remote);
    assert.match(message, /^export: 3 skills, only the removals Atlas asked for$/m);
    assert.match(message, /^Removed: delta$/m);
    assert.doesNotMatch(message, /Workbench-Commit|2222222/, 'the set-aside stage is not recorded');
    assert.equal(bodyOf(net).workbench_sha, WB.a, 'the post names the last stage taken from');
  });
});

// Review round 2: what git's attributes do to bytes on the way in or out may not stop a run either,
// and an unexpected error's message never reaches the log, however its frames are searched.
describe("rule 5, whatever git's attributes do", () => {
  const withGamma = (alphaSpec = {}) => {
    const shelves = makeShelf();
    const earlier = buildStage([F('alpha', '1.01', alphaSpec), F('beta', '1.02'), F('gamma', '1.03')]);
    placeOnShelf(shelves.shelf, earlier, ['alpha', 'beta', 'gamma'], WB.a);
    return { ...shelves, earlier };
  };

  test('a listed folder whose bytes git would change on the way in is kept as the shelf has it, and the run goes on', async () => {
    const { shelf, remote, earlier } = withGamma();
    const before = git(remote, ['rev-parse', `main:${earlier.dir('alpha')}`]).trim();
    // alpha's approved tree holds a CRLF file under `* text`: `git add` would store it as LF.
    const stage = buildStage(
      [
        F('alpha', '1.01', { files: { '.gitattributes': '* text\n', 'references/win.md': 'line one\r\nline two\r\n' } }),
        F('beta', '1.02'),
        F('gamma', '1.03'),
        F('newcomer', '1.04', { files: { '.gitattributes': '* text\n', 'notes.md': 'a\r\nb\r\n' } }),
      ],
      { sha: WB.b },
    );
    // Atlas lists alpha and the newcomer at their staged trees, beta at the shelf's, and withdrew gamma.
    const net = network({ atlas: atlasList([...listed(stage, 'alpha', 'newcomer'), [earlier.dir('beta'), earlier.tree('beta')]]) });
    const d = enforce(net);
    assert.equal(await main(argv(stage, shelf), d), 0, d.err.join('\n'));
    const files = filesOn(remote);
    assert.doesNotMatch(files, /gamma/, 'the withdrawal Atlas asked for was made');
    assert.equal(git(remote, ['rev-parse', `main:${earlier.dir('alpha')}`]).trim(), before, 'alpha is exactly the copy the shelf had');
    assert.doesNotMatch(files, /newcomer/, 'the newcomer waits');
    assert.ok(d.out.some((l) => /why kept or waiting: git would change its bytes 2/.test(l)), d.out.join('\n'));
    assert.match(lastMessage(remote), /^Kept as the shelf has it: 1\.01$/m);
    assert.match(lastMessage(remote), /^Waiting for Atlas: 1\.04$/m);
    assert.deepEqual(Object.keys(rowsBy(net)).sort(), ['alpha', 'beta']);
  });

  test('a kept folder whose checkout git rewrote (eol=crlf) is held as the shelf holds it: its blobs, not its working tree', async () => {
    const attrs = { files: { '.gitattributes': '*.md text eol=crlf\n' } };
    const { shelf, remote, earlier } = withGamma(attrs);
    // A fresh checkout, as the job gets one: alpha's .md files are CRLF in the working tree now.
    fs.rmSync(path.join(shelf, earlier.dir('alpha')), { recursive: true, force: true });
    git(shelf, ['checkout', '--', 'skills']);
    assert.ok(fs.readFileSync(path.join(shelf, earlier.dir('alpha'), 'SKILL.md'), 'utf8').includes('\r\n'));
    const before = git(remote, ['rev-parse', `main:${earlier.dir('alpha')}`]).trim();
    const stage = buildStage([F('alpha', '1.01', attrs), F('beta', '1.02'), F('gamma', '1.03')], { sha: WB.b });
    // Atlas keeps alpha 「as is」, lists beta at the shelf's tree, and withdrew gamma.
    const net = network({ atlas: atlasList([[earlier.dir('beta'), earlier.tree('beta')]], [earlier.dir('alpha')]) });
    const d = enforce(net);
    assert.equal(await main(argv(stage, shelf), d), 0, d.err.join('\n'));
    assert.doesNotMatch(filesOn(remote), /gamma/);
    assert.equal(git(remote, ['rev-parse', `main:${earlier.dir('alpha')}`]).trim(), before);
    assert.deepEqual(Object.keys(rowsBy(net)).sort(), ['alpha', 'beta']);
  });

  test('the same folder, published at its approved tree, goes through: its blobs are LF and stay so', async () => {
    const { shelf, remote } = makeShelf();
    const stage = buildStage([F('alpha', '1.01', { files: { '.gitattributes': '*.md text eol=crlf\n', 'references/notes.md': 'one\ntwo\n' } })]);
    const net = network({ atlas: atlasList(listed(stage, 'alpha')) });
    assert.equal(await main(argv(stage, shelf), enforce(net)), 0);
    assert.equal(git(remote, ['rev-parse', `main:${stage.dir('alpha')}`]).trim(), stage.tree('alpha'), 'byte for byte the tree Atlas approved');
  });

  test('a move whose new place git would change keeps the old place, which the first mirror had taken away', async () => {
    const { shelf, remote, earlier } = withGamma();
    const before = git(remote, ['rev-parse', `main:${earlier.dir('alpha')}`]).trim();
    const stage = buildStage(
      [F('alpha', '1.01', { cat: '3-operations', files: { '.gitattributes': '* text\n', 'references/win.md': 'one\r\ntwo\r\n' } }), F('beta', '1.02'), F('gamma', '1.03')],
      { sha: WB.b },
    );
    // Atlas approves the new place, still lists the old one at the shelf's tree, and withdrew gamma.
    const net = network({
      atlas: atlasList([[earlier.dir('alpha'), earlier.tree('alpha')], ...listed(stage, 'alpha'), [earlier.dir('beta'), earlier.tree('beta')]]),
    });
    const d = enforce(net);
    assert.equal(await main(argv(stage, shelf), d), 0, d.err.join('\n'));
    const files = filesOn(remote);
    assert.doesNotMatch(files, /gamma|3-operations/);
    assert.equal(git(remote, ['rev-parse', `main:${earlier.dir('alpha')}`]).trim(), before, 'the old place stays, as the shelf had it');
    assert.match(lastMessage(remote), /^Waiting for Atlas: 1\.01$/m);
    assert.equal(rowsBy(net).alpha.source_path, `${earlier.dir('alpha')}/SKILL.md`, "alpha's row is built from the old place's files");
  });

  test("a kept folder's rows are built from the blobs the shelf holds, not from what a checkout wrote (ident)", async () => {
    const attrs = { files: { '.gitattributes': '* ident\n' }, description: 'Pinned at $Id$ on purpose' };
    const { shelf, remote, earlier } = withGamma(attrs);
    fs.rmSync(path.join(shelf, earlier.dir('alpha')), { recursive: true, force: true });
    git(shelf, ['checkout', '--', 'skills']);
    assert.match(fs.readFileSync(path.join(shelf, earlier.dir('alpha'), 'SKILL.md'), 'utf8'), /\$Id: [0-9a-f]{40} \$/, 'the checkout expanded it');
    const stage = buildStage([F('alpha', '1.01', attrs), F('beta', '1.02'), F('gamma', '1.03')], { sha: WB.b });
    const net = network({ atlas: atlasList([[earlier.dir('beta'), earlier.tree('beta')]], [earlier.dir('alpha')]) });
    const d = enforce(net);
    assert.equal(await main(argv(stage, shelf), d), 0, d.err.join('\n'));
    assert.doesNotMatch(filesOn(remote), /gamma/);
    const row = JSON.stringify(rowsBy(net).alpha);
    assert.match(row, /Pinned at \$Id\$ on purpose/);
    assert.doesNotMatch(row, /\$Id: /);
  });

  test('a kept folder named like a pathspec glob puts only itself back to HEAD', () => {
    const repo = scratch('literal');
    git(repo, ['init', '-q']);
    writeFile(repo, 'skills/c/a*/SKILL.md', 'kept\n');
    writeFile(repo, 'skills/c/aXb/SKILL.md', 'old\n');
    git(repo, ['add', '-A']);
    git(repo, ['-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-q', '-m', 'one']);
    const kept = git(repo, ['rev-parse', 'HEAD:skills/c/a*/SKILL.md']).trim();
    writeFile(repo, 'skills/c/aXb/SKILL.md', 'new\n');
    const published = git(repo, ['hash-object', '--', 'skills/c/aXb/SKILL.md']).trim();
    const desired = new Map([
      ['skills/c/a*/SKILL.md', { sha: kept, mode: '100644', from: 'shelf' }],
      ['skills/c/aXb/SKILL.md', { sha: published, mode: '100644', from: 'stage' }],
    ]);
    assert.deepEqual(stageIndexEnforce(repo, desired, ['skills/c/a*']), []);
  });
});

describe('an unexpected error in the public log (D-73)', () => {
  test("is named by a frame of this repo's code, never by anything in its message", () => {
    const err = new Error("EACCES: permission denied, open '/tmp/stage/skills/1-x/acme-portal/tools/acme-portal-sync.mjs:7'");
    err.code = 'EACCES';
    // This test file is no module of the publisher's (its name has a dot), so no frame qualifies here;
    // the end-to-end test below sees the real one, tools/publish.mjs.
    assert.equal(unexpectedWords(err), 'unexpected failure: Error EACCES');
    // A message over several lines, one of them dressed as a frame.
    const forged = new Error('first line\n    at tools/acme-portal.mjs:7\nlast line');
    assert.doesNotMatch(unexpectedWords(forged), /acme-portal/);
    assert.equal(unexpectedWords({ name: 'Error', message: 'x tools/acme-portal.mjs:1', stack: 'Error: x tools/acme-portal.mjs:1' }), 'unexpected failure: Error');
  });

  test('end to end: a staged file named like a code line, unreadable, never names its folder', { skip: typeof process.getuid === 'function' && process.getuid() === 0 && 'root reads a mode-000 file' }, async () => {
    const { shelf, remote } = makeShelf();
    const earlier = buildStage([F('alpha', '1.01'), F('beta', '1.02')]);
    placeOnShelf(shelf, earlier, ['alpha', 'beta'], WB.a);
    const stage = buildStage([F('alpha', '1.01'), F('beta', '1.02'), F('acme-portal', '1.09', { files: { 'tools/acme-portal-sync.mjs:7': 'x\n' } })], { sha: WB.b });
    const bad = path.join(stage.stageRoot, stage.dir('acme-portal'), 'tools/acme-portal-sync.mjs:7');
    fs.chmodSync(bad, 0o000);
    try {
      const net = network({ atlas: atlasList([[earlier.dir('alpha'), earlier.tree('alpha')], [earlier.dir('beta'), earlier.tree('beta')]]) });
      const d = enforce(net, { GITHUB_ACTIONS: 'true' });
      assert.equal(await main(argv(stage, shelf), d), 1);
      const text = everything(d, remote);
      assert.match(text, /the stage could not be read \(unexpected failure: Error EACCES at tools\/publish\.mjs:\d+\)/);
      assert.doesNotMatch(text, /acme-portal/);
    } finally {
      fs.chmodSync(bad, 0o644);
    }
  });
});
