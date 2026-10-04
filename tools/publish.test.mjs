import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { SECRET, SITE, TOKEN, WB, buildStage, deps, git, head, makeShelf, network, placeOnShelf, skill, writeFile } from './fixtures.mjs';
import { Refusal, SHELF_URL } from './common.mjs';
import {
  checkShrink,
  commitMessage,
  heldWords,
  main,
  parseFrontmatter,
  planPromotion,
  publish,
  pruneValue,
  renamedFromOf,
  sheetIdOf,
} from './publish.mjs';

const opts = (stage, shelf, more = {}) => ({
  stage: stage.root,
  shelf,
  event: 'workflow_dispatch',
  run: stage.run,
  prune: 'report',
  promote: 'all',
  allowShrink: false,
  allowRewind: false,
  seedFail: false,
  dryRun: false,
  ...more,
});

const argv = (stage, shelf, ...more) =>
  ['--stage', stage.root, '--shelf', shelf, '--event', 'workflow_dispatch', '--run', stage.runFile, ...more];

/** The three skills most tests use: a plain one, one with an executable script, one with a sub-agent. */
const trio = () => [
  skill('alpha'),
  skill('beta', { files: { 'scripts/run.sh': { content: '#!/bin/sh\necho hi\n', exec: true }, 'references/notes.md': 'notes\n' } }),
  skill('gamma', { cat: '3-operations', agents: ['helper'] }),
];

const bodyOf = (net) => JSON.parse(net.posts()[0].init.body);

async function refused(promise, pattern) {
  await assert.rejects(promise, (err) => {
    assert.ok(err instanceof Refusal, `expected a Refusal, got ${err}`);
    assert.match(err.message, pattern);
    return true;
  });
}

describe('frontmatter', () => {
  test('reads top-level scalars, quotes and comments; skips indented lines; notes repeats', () => {
    const fm = parseFrontmatter(
      [
        '---',
        'name: "quoted-name"',
        "visibility: 'public'",
        'install_command: npx skills add https://github.com/a/b --skill c # upstream',
        'description: >-',
        '  name: not-a-key',
        'status: Done',
        'status: WIP',
        '---',
        'name: after-the-block',
      ].join('\n'),
    );
    assert.equal(fm.keys.get('name'), 'quoted-name');
    assert.equal(fm.keys.get('visibility'), 'public');
    assert.equal(fm.keys.get('install_command'), 'npx skills add https://github.com/a/b --skill c');
    assert.equal(fm.keys.get('description'), null);
    assert.deepEqual([...fm.dupes], ['status']);
    assert.equal(parseFrontmatter('# no frontmatter\n'), null);
    assert.equal(parseFrontmatter('---\nname: x\n'), null, 'an unterminated block is no frontmatter');
    assert.equal(parseFrontmatter('---\nvisibility:public\n---\n').keys.has('visibility'), false);
  });
});

describe('a clean stage', () => {
  test('a dry run prints the plan and changes nothing', async () => {
    const stage = buildStage(trio());
    const { shelf } = makeShelf();
    const before = head(shelf);
    const net = network();
    const d = deps(net);
    const result = await publish(opts(stage, shelf, { dryRun: true }), d);

    assert.equal(result.outcome, 'dry-run');
    assert.equal(net.calls.length, 0, 'first export: no compare, and a dry run posts nothing');
    assert.equal(head(shelf), before);
    assert.equal(fs.existsSync(path.join(shelf, 'skills')), false);
    const plan = JSON.parse(d.out.find((l) => l.startsWith('{')));
    assert.equal(plan.dry_run, true);
    assert.deepEqual(plan.added, ['alpha', 'beta', 'gamma']);
    assert.deepEqual(plan.held, []);
    assert.equal(plan.body.format, 'shelf-v1');
    assert.equal(plan.body.skills.length, 4);
    assert.ok(!d.out.join('\n').includes(SECRET));
  });

  test('publishes: one bot commit with the trailer, modes kept, then a signed post', async () => {
    const stage = buildStage([
      ...trio(),
      skill('delta', { files: { '.gitignore': '*.log\n', 'kept.log': 'tracked in the workbench\n' } }),
    ]);
    const { shelf, remote } = makeShelf();
    const net = network();
    const d = deps(net);
    const result = await publish(opts(stage, shelf), d);

    assert.equal(result.outcome, 'published');
    assert.equal(head(remote, 'main'), result.commit, 'pushed');
    const [subject, , ...rest] = git(remote, ['log', '-1', '--format=%B', 'main']).trim().split('\n');
    assert.equal(subject, 'export: 4 skills from 1111111');
    assert.equal(rest.at(-1), `Workbench-Commit: ${WB.a}`);
    assert.match(rest.join('\n'), /^Added: alpha, beta, gamma, delta$/m);
    assert.equal(git(remote, ['log', '-1', '--format=%an <%ae>', 'main']).trim(), 'github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>');

    const tree = git(remote, ['ls-tree', '-r', 'main']);
    assert.match(tree, /^100755 blob \w+\tskills\/1-brand-marketing\/beta\/scripts\/run\.sh$/m);
    assert.match(tree, /\tskills\/1-brand-marketing\/delta\/kept\.log$/m, "a skill's own .gitignore does not drop a tracked file");
    assert.match(tree, /\tskills\/1-brand-marketing\/delta\/\.gitignore$/m);

    assert.equal(net.posts().length, 1);
    const post = net.posts()[0];
    assert.equal(post.url, SITE);
    assert.equal(post.init.headers['X-Zynkr-Signature'], crypto.createHmac('sha256', SECRET).update(post.init.body).digest('hex'));
    assert.equal(post.init.headers['X-Zynkr-Source-Sha'], WB.a);
    assert.equal(post.init.headers['Content-Type'], 'application/json');
    const body = bodyOf(net);
    assert.deepEqual(Object.keys(body), ['format', 'repo_url', 'prune', 'workbench_sha', 'workbench_committed_at', 'skills']);
    assert.equal(body.repo_url, SHELF_URL);
    assert.equal(body.prune, 'report');
    assert.equal(body.workbench_committed_at, '2026-09-28T10:00:00Z');
    assert.equal(body.skills.length, 5);
    assert.match(d.summary(), /### Export to the shelf/);
  });

  test('a second run of the same stage commits nothing and still posts', async () => {
    const stage = buildStage(trio());
    const { shelf } = makeShelf();
    await publish(opts(stage, shelf), deps(network()));
    const after = head(shelf);
    const net = network();
    const result = await publish(opts(stage, shelf), deps(net));
    assert.equal(result.order, 'identical');
    assert.equal(result.commit, null);
    assert.equal(head(shelf), after);
    assert.equal(net.calls.length, 1, 'no compare call for an identical commit');
    assert.equal(net.posts().length, 1);
  });

  test('a folder the stage dropped leaves the shelf', async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(shelf, buildStage(trio()), ['alpha', 'beta', 'gamma'], WB.a);
    const stage = buildStage([skill('alpha'), skill('beta', trio()[1])], { sha: WB.b });
    await publish(opts(stage, shelf), deps(network()));
    assert.equal(fs.existsSync(path.join(shelf, 'skills/3-operations')), false);
    assert.match(git(remote, ['log', '-1', '--format=%B', 'main']), /^Removed: gamma$/m);
  });
});

describe('derived fields', () => {
  test('repo_url, github_url and install_command come from the tree, not the stage', async () => {
    const stage = buildStage([
      skill('alpha'),
      skill('writer', { manifestFile: 'CLAUDE.md', kind: 'orchestrator', installable: false, agents: ['draft'], agentsDir: '.claude/agents' }),
      skill('slide-pptx', { extra: 'install_command: npx skills add https://github.com/anthropics/skills --skill slide-pptx' }),
      skill('gamma', { kind: 'orchestrator', agents: ['helper'] }),
    ]);
    const { shelf } = makeShelf();
    const { body } = await publish(opts(stage, shelf, { dryRun: true }), deps(network()));
    const rows = Object.fromEntries(JSON.parse(body).skills.map((r) => [r.slug, r]));

    for (const r of Object.values(rows)) assert.equal(r.repo_url, SHELF_URL);
    assert.equal(rows.alpha.install_command, `npx skills add ${SHELF_URL} --skill alpha`);
    assert.equal(rows.alpha.github_url, `${SHELF_URL}/blob/main/skills/1-brand-marketing/alpha/SKILL.md`);
    assert.equal(rows.writer.github_url, `${SHELF_URL}/tree/main/skills/1-brand-marketing/writer`);
    assert.equal(rows.writer.install_command, null, 'installable: false carries no line');
    assert.equal(rows['writer-draft'].install_command, null);
    assert.equal(rows['writer-draft'].github_url, `${SHELF_URL}/blob/main/skills/1-brand-marketing/writer/.claude/agents/draft.md`);
    assert.equal(rows['slide-pptx'].install_command, 'npx skills add https://github.com/anthropics/skills --skill slide-pptx');
    assert.equal(rows.gamma.install_command, `npx skills add ${SHELF_URL} --skill gamma`);
    assert.equal(rows['gamma-helper'].install_command, null, 'a sub-agent carries no line');
  });

  test('an install_command override that is not an npx skills add line refuses', async () => {
    for (const line of ['curl -sL zynkr.ai/s/1.01.md -o x.md', 'npx skills add https://evil.test/a/b --skill x']) {
      const stage = buildStage([skill('alpha', { extra: `install_command: ${line}` })]);
      // A folder the shelf already publishes is named by its path...
      const { shelf: known } = makeShelf();
      placeOnShelf(known, buildStage([skill('alpha')]), ['alpha'], WB.a);
      await refused(publish(opts(stage, known, { dryRun: true }), deps(network())), /alpha\/SKILL\.md: install_command must be/);
      // ...and one new to it by its sheetId only.
      const { shelf: empty } = makeShelf();
      await refused(publish(opts(stage, empty, { dryRun: true }), deps(network())), /a file new to the shelf \(sheetId id-alpha\): install_command must be/);
    }
  });

  test('names must be CLI-safe and unique', async () => {
    const { shelf } = makeShelf();
    const bad = buildStage([skill('alpha', { name: 'Alpha_Skill' })]);
    await refused(publish(opts(bad, shelf, { dryRun: true }), deps(network())), /name must match/);
    const twice = buildStage([skill('alpha', { name: 'same' }), skill('beta', { name: 'same' })]);
    await refused(publish(opts(twice, shelf, { dryRun: true }), deps(network())), /one name is used by both a file new to the shelf \(sheetId id-alpha\) and a file new to the shelf \(sheetId id-beta\)/);
  });

  // Review round 4 (workbench SKB-054): a refusal came before the hold and named the folder, so a client
  // build marked public by mistake was named in this public log. A folder new to the shelf is named by
  // its sheetId now, whatever the refusal.
  test('a refusal never names a folder new to the shelf', async () => {
    const cases = [
      ['name written as a block', { name: '>-' }],
      ['name on the next line', { name: '' }],
      ['install_command with -y', { extra: `install_command: npx skills add ${SHELF_URL} --skill globex-portal -y` }],
    ];
    for (const [label, spec] of cases) {
      const { shelf } = makeShelf();
      const stage = buildStage([skill('globex-portal', { sheetId: '3.41', ...spec })]);
      const d = deps(network());
      const err = await publish(opts(stage, shelf, { dryRun: true }), d).then(() => null, (e) => e);
      assert.ok(err instanceof Refusal, `${label}: refused`);
      assert.match(err.message, /sheetId 3\.41/, label);
      assert.doesNotMatch(`${err.message}\n${d.out.join('\n')}\n${d.err.join('\n')}\n${d.summary()}`, /globex/, label);
    }
  });
});

describe('the stage is checked before anything happens', () => {
  const noLeak = (d, word) => assert.ok(![...d.out, ...d.err, d.summary()].join('\n').includes(word), `"${word}" reached the log`);

  test('a file not in the manifest refuses, and the log does not name it', async () => {
    const stage = buildStage(trio());
    writeFile(stage.stageRoot, 'skills/9-legal/team-only-plan/SKILL.md', '---\nname: team-only-plan\nvisibility: team\n---\n');
    const { shelf } = makeShelf();
    const net = network();
    const d = deps(net);
    assert.equal(await main(argv(stage, shelf, '--promote', 'all'), d), 1);
    assert.match(d.err.join('\n'), /1 file not in manifest\.files/);
    noLeak(d, 'team-only-plan');
    assert.equal(net.calls.length, 0);
  });

  test('a wrong sha refuses', async () => {
    const stage = buildStage(trio());
    fs.appendFileSync(path.join(stage.stageRoot, 'skills/1-brand-marketing/beta/references/notes.md'), 'changed\n');
    const { shelf } = makeShelf();
    await refused(publish(opts(stage, shelf), deps(network())), /1 file whose bytes differ from its listed sha/);
  });

  test('a lost executable bit refuses', async () => {
    const stage = buildStage(trio());
    fs.chmodSync(path.join(stage.stageRoot, 'skills/1-brand-marketing/beta/scripts/run.sh'), 0o644);
    const { shelf } = makeShelf();
    await refused(publish(opts(stage, shelf), deps(network())), /executable bit differs/);
  });

  test('a file listed but missing, an empty folder and a link each refuse', async () => {
    const { shelf } = makeShelf();
    const missing = buildStage(trio());
    fs.rmSync(path.join(missing.stageRoot, 'skills/1-brand-marketing/alpha/SKILL.md'));
    await refused(publish(opts(missing, shelf), deps(network())), /1 listed file missing/);

    const empty = buildStage(trio());
    fs.mkdirSync(path.join(empty.stageRoot, 'skills/9-legal/nothing-here'), { recursive: true });
    await refused(publish(opts(empty, shelf), deps(network())), /2 folders holding no listed file/);

    const linked = buildStage(trio());
    fs.symlinkSync('/etc/hosts', path.join(linked.stageRoot, 'skills/1-brand-marketing/alpha/hosts'));
    await refused(publish(opts(linked, shelf), deps(network())), /neither a file nor a folder/);
  });

  test('anything in stage/ besides manifest.json, payload.json and skills/ refuses', async () => {
    const stage = buildStage(trio());
    fs.writeFileSync(path.join(stage.stageRoot, 'notes.txt'), 'x');
    const { shelf } = makeShelf();
    await refused(publish(opts(stage, shelf), deps(network())), /stage\/ holds 1 entry besides/);
  });

  test('a manifest of another format, or a path escaping skills/, refuses', async () => {
    const { shelf } = makeShelf();
    const format = buildStage(trio());
    format.manifest.format = 'stage-v2';
    format.save();
    await refused(publish(opts(format, shelf), deps(network())), /not format stage-v1/);

    const escape = buildStage(trio());
    escape.manifest.files[0].path = 'skills/../README.md';
    escape.save();
    await refused(publish(opts(escape, shelf), deps(network())), /manifest\.files\[0\] is not/);
  });

  test('a team mark, or no mark, refuses without naming the skill', async () => {
    const { shelf } = makeShelf();
    for (const visibility of ['team', undefined, 'Public']) {
      const stage = buildStage([skill('alpha'), skill('quiet-internal-tool', { visibility })]);
      const d = deps(network());
      assert.equal(await main(argv(stage, shelf, '--promote', 'all'), d), 1);
      assert.match(d.err.join('\n'), /1 skill manifest in the stage lacks visibility: public/);
      noLeak(d, 'quiet-internal-tool');
    }
  });

  test('a nested SKILL.md that says team refuses', async () => {
    const stage = buildStage([
      skill('writer', {
        manifestFile: 'CLAUDE.md',
        kind: 'orchestrator',
        installable: false,
        files: { '.claude/skills/write-article/SKILL.md': '---\nname: write-article\nvisibility: team\n---\n' },
      }),
    ]);
    const { shelf } = makeShelf();
    await refused(publish(opts(stage, shelf), deps(network())), /declares a visibility other than public/);
  });

  test('a payload row outside the stage, or not marked public, refuses', async () => {
    const { shelf } = makeShelf();
    const outside = buildStage(trio());
    outside.payload.push({ slug: 'ghost', kind: 'skill', source_path: 'skills/9-legal/ghost/SKILL.md', visibility: 'public' });
    outside.save();
    await refused(publish(opts(outside, shelf), deps(network())), /payload\[4\]\.source_path is not a file in the stage/);

    const unmarked = buildStage(trio());
    delete unmarked.payload[0].visibility;
    unmarked.save();
    // alpha is new to this shelf, so the refusal names its row by id, never its path (wordsFor).
    await refused(publish(opts(unmarked, shelf), deps(network())), /the payload row for a file new to the shelf \(sheetId 1\.1\) is not marked visibility: public/);
    const { shelf: known } = makeShelf();
    placeOnShelf(known, buildStage(trio()), trio().map((s) => s.slug), WB.a);
    await refused(publish(opts(unmarked, known), deps(network())), /alpha\/SKILL\.md is not marked visibility: public/);
  });

  test("a stage whose workbench_sha is not its run's commit refuses before anything is pushed or posted", async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(shelf, buildStage([skill('alpha')]), ['alpha'], WB.a);
    const before = head(remote, 'main');
    // The run fetch-stage checked built WB.b; the stage inside claims the newer WB.c.
    const stage = buildStage([skill('alpha'), skill('beta')], { sha: WB.c });
    stage.run.head_sha = WB.b;
    fs.writeFileSync(stage.runFile, JSON.stringify(stage.run));
    const net = network({ compare: 'ahead' });
    const d = deps(net);
    assert.equal(await main(argv(stage, shelf, '--promote', 'all'), d), 1);
    assert.match(d.err.join('\n'), /the stage claims workbench commit 3333333, but the run it came from built 2222222/);
    assert.equal(head(remote, 'main'), before);
    assert.equal(net.calls.length, 0, 'no compare, no post');
  });

  test('without --run only a dry run proceeds', async () => {
    const stage = buildStage(trio());
    const { shelf } = makeShelf();
    await refused(publish(opts(stage, shelf, { run: undefined }), deps(network())), /--run must name the run\.json/);
    const dry = await publish(opts(stage, shelf, { run: undefined, dryRun: true }), deps(network()));
    assert.equal(dry.outcome, 'dry-run');

    const d = deps(network());
    assert.equal(await main(['--stage', stage.root, '--shelf', shelf, '--event', 'workflow_dispatch', '--run', path.join(stage.root, 'nope.json')], d), 1);
    assert.match(d.err.join('\n'), /--run names no file/);
  });

  test('seed_fail plants an unlisted file and refuses (AC-18)', async () => {
    const stage = buildStage(trio());
    const { shelf, remote } = makeShelf();
    const before = head(remote, 'main');
    const net = network();
    const d = deps(net);
    assert.equal(await main(argv(stage, shelf, '--promote', 'all', '--seed-fail'), d), 1);
    assert.match(d.err.join('\n'), /1 file not in manifest\.files/);
    assert.match(d.summary(), /### Export refused/);
    assert.equal(head(remote, 'main'), before);
    assert.equal(net.calls.length, 0);
  });

  test('under Actions a refusal is one ::error:: annotation', async () => {
    const stage = buildStage(trio());
    stage.manifest.format = 'nope';
    stage.save();
    const { shelf } = makeShelf();
    const d = deps(network(), { GITHUB_ACTIONS: 'true' });
    assert.equal(await main(argv(stage, shelf), d), 1);
    assert.equal(d.err.length, 1);
    assert.match(d.err[0], /^::error::manifest\.json is not format stage-v1$/);
  });
});

describe('promotion (AC-12)', () => {
  test('a folder new to the shelf is held until promoted, with its sub-agents', async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(shelf, buildStage([skill('alpha')]), ['alpha'], WB.a);
    const stage = buildStage([skill('alpha'), skill('gamma', { sheetId: '1.07', agents: ['helper'] })], { sha: WB.b });

    const net = network();
    const d = deps(net);
    const held = await publish(opts(stage, shelf, { promote: '' }), d);
    assert.deepEqual(held.promotion.held.map((s) => s.slug), ['gamma']);
    assert.equal(held.commit, null, 'alpha is unchanged and gamma is held: nothing to commit');
    assert.equal(fs.existsSync(path.join(shelf, 'skills/1-brand-marketing/gamma')), false);
    assert.deepEqual(bodyOf(net).skills.map((r) => r.slug), ['alpha']);
    // A held skill is named by its sheetId: it may be a client build marked public by mistake, whose
    // slug names the client (workbench SKB-054). Nothing public says "gamma" until it is promoted.
    assert.match(d.summary(), /Held until promoted.*`1\.07`/);
    assert.ok(d.out.includes('held until promoted: 1.07'));
    assert.doesNotMatch(d.summary(), /gamma/);
    assert.doesNotMatch(JSON.stringify(d.out), /gamma/);

    const net2 = network();
    const promoted = await publish(opts(stage, shelf, { promote: 'other, 1.07' }), deps(net2));
    assert.deepEqual(promoted.promotion.held, []);
    assert.deepEqual(bodyOf(net2).skills.map((r) => r.slug), ['alpha', 'gamma', 'gamma-helper']);
    assert.match(git(remote, ['log', '-1', '--format=%B', 'main']), /^Added: gamma$/m);
  });

  const onShelf = (dir, name, id = null) => ({ dir, names: new Set([name]), ids: new Set(id ? [id] : []) });

  test('all promotes every folder; a folder moved between categories stays published', () => {
    const stageSkills = [
      { dir: 'skills/1-x/alpha', slug: 'alpha', name: 'alpha' },
      { dir: 'skills/3-y/moved', slug: 'moved', name: 'moved' },
      { dir: 'skills/1-x/fresh', slug: 'fresh', name: 'fresh' },
    ];
    const shelf = [onShelf('skills/1-x/alpha', 'alpha'), onShelf('skills/2-z/moved', 'moved')];
    const none = planPromotion(stageSkills, shelf, '');
    assert.deepEqual(none.held.map((s) => s.slug), ['fresh']);
    assert.deepEqual(none.kept.map((s) => s.slug), ['alpha', 'moved']);
    const all = planPromotion(stageSkills, shelf, 'all');
    assert.deepEqual(all.held, []);
    assert.deepEqual(all.promoted.map((s) => s.slug), ['fresh']);
    assert.equal(planPromotion(stageSkills, shelf, 'fresh,typo').unmatched, 1);
    // promote also takes a sheetId: the outputs name a held skill by its id, never its slug.
    const numbered = stageSkills.map((s) => (s.slug === 'fresh' ? { ...s, sheetId: '1.09' } : s));
    assert.deepEqual(planPromotion(numbered, shelf, '1.09').promoted.map((s) => s.slug), ['fresh']);
    assert.equal(planPromotion(numbered, shelf, '9.99').unmatched, 1);
  });

  test('held skills are named by sheetId in the commit message, never by slug', () => {
    const held = [{ slug: 'acme-portal', sheetId: '3.40' }, { slug: 'acme-tools' }];
    assert.deepEqual(heldWords(held), ['3.40', '1 skill with no sheetId']);
    const msg = commitMessage({
      manifest: { workbench_sha: 'a'.repeat(40) },
      kept: [],
      plan: { added: [], changed: [], removed: [], loose: 0 },
      held,
    });
    assert.match(msg, /^Held until promoted: 3\.40, 1 skill with no sheetId$/m);
    assert.doesNotMatch(msg, /acme/);
  });

  test('a new skill that only reuses a public folder name is held', () => {
    const shelf = [onShelf('skills/1-x/alpha', 'alpha')];
    // The original stays on the shelf; a new skill in another category takes its folder name.
    const beside = [
      { dir: 'skills/1-x/alpha', slug: 'alpha', name: 'alpha' },
      { dir: 'skills/3-y/alpha', slug: 'brand-new-skill', name: 'brand-new-skill' },
    ];
    assert.deepEqual(planPromotion(beside, shelf, '').held.map((s) => s.slug), ['brand-new-skill']);
    // The original leaves; a new skill under its folder name in another category is still new.
    const replaced = [{ dir: 'skills/3-y/alpha', slug: 'brand-new-skill', name: 'brand-new-skill' }];
    assert.deepEqual(planPromotion(replaced, shelf, '').held.map((s) => s.slug), ['brand-new-skill']);
    // The same skill moved: same folder name, gone from its old path, same name.
    const moved = [{ dir: 'skills/3-y/alpha', slug: 'alpha', name: 'alpha' }];
    assert.deepEqual(planPromotion(moved, shelf, '').held, []);
  });

  test('a category move end to end: the moved skill is kept, a new folder-name twin is held', async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(shelf, buildStage([skill('alpha', { cat: '1-brand-marketing' })]), ['alpha'], WB.a);
    const stage = buildStage(
      [skill('alpha', { cat: '3-operations' }), skill('brand-new-skill', { cat: '5-product', dirName: 'alpha' })],
      { sha: WB.b },
    );
    const net = network();
    const result = await publish(opts(stage, shelf, { promote: '' }), deps(net));
    assert.deepEqual(result.promotion.held.map((s) => s.slug), ['brand-new-skill']);
    assert.deepEqual(bodyOf(net).skills.map((r) => r.slug), ['alpha']);
    const tree = git(remote, ['ls-tree', '-r', '--name-only', 'main']);
    assert.match(tree, /^skills\/3-operations\/alpha\/SKILL\.md$/m);
    assert.doesNotMatch(tree, /^skills\/(1-brand-marketing|5-product)\//m);
  });
});

describe('a rename keeps its place: renamed_from, backed by the same sheetId', () => {
  const onShelf = (dir, name, ...ids) => ({ dir, names: new Set([name]), ids: new Set(ids) });
  const gone = onShelf('skills/2-z/consult-governance', 'consult-governance', '2.45');
  const renamed = {
    dir: 'skills/2-z/project-governance',
    slug: 'project-governance',
    name: 'project-governance',
    sheetId: '2.45',
    renamedFrom: 'consult-governance',
  };
  const held = (skills, shelf) => planPromotion(skills, shelf, '').held.map((s) => s.slug);

  test('the mark and the id agree on one folder that left the stage: kept without a promote', () => {
    const plan = planPromotion([renamed], [gone], '');
    assert.deepEqual(plan.held, []);
    assert.deepEqual(plan.promoted, []);
    assert.deepEqual(plan.renamed, [{ skill: renamed, from: gone.dir }]);
    // Named in promote as well: still a rename, not a promotion, and not an unmatched name.
    const named = planPromotion([renamed], [gone], 'project-governance');
    assert.deepEqual([named.promoted, named.renamed.length, named.unmatched], [[], 1, 0]);
  });

  test('anything less certain is held for the owner (D-76)', () => {
    // A retired skill's id handed to a new skill: the same sheetId, but no mark.
    assert.deepEqual(held([{ ...renamed, renamedFrom: null }], [gone]), ['project-governance']);
    // A mark the id does not back, or a mark naming no shelf skill.
    assert.deepEqual(held([{ ...renamed, sheetId: '2.46' }], [gone]), ['project-governance']);
    assert.deepEqual(held([{ ...renamed, sheetId: null }], [gone]), ['project-governance']);
    assert.deepEqual(held([{ ...renamed, renamedFrom: 'never-public' }], [gone]), ['project-governance']);
    // The old folder is still in the stage: nothing was renamed.
    const stillThere = { dir: gone.dir, slug: 'consult-governance', name: 'consult-governance', sheetId: '9.99' };
    assert.deepEqual(held([stillThere, renamed], [gone]), ['project-governance']);
    // The old folder's path is still in the stage, now holding another skill: it did not leave.
    const reused = { dir: gone.dir, slug: 'other-name', name: 'other-name', sheetId: '9.99' };
    assert.deepEqual(held([reused, renamed], [gone]), ['project-governance']);
    // The old folder moved to another category (and lost the id): the move claims it.
    const moved = { ...stillThere, dir: 'skills/3-y/consult-governance' };
    assert.deepEqual(held([moved, renamed], [gone]), ['project-governance']);
    // Two stage folders carry the id: neither is known to be the skill.
    const twin = { ...renamed, dir: 'skills/3-y/twin', slug: 'twin', name: 'twin', renamedFrom: null };
    assert.deepEqual(held([renamed, twin], [gone]), ['project-governance', 'twin']);
    // Two shelf folders carry the name and the id: which one it replaces is unknown.
    assert.deepEqual(held([renamed], [gone, onShelf('skills/3-y/consult-governance', 'consult-governance', '2.45')]), [
      'project-governance',
    ]);
    // One old folder carrying two ids (a stray second manifest) claimed by two new folders: both held.
    const both = onShelf('skills/2-z/consult-governance', 'consult-governance', '2.45', '2.46');
    const second = { ...renamed, dir: 'skills/2-z/brand-new', slug: 'brand-new', name: 'brand-new', sheetId: '2.46' };
    assert.deepEqual(held([renamed, second], [both]), ['project-governance', 'brand-new']);
  });

  test('a repeated sheetId or renamed_from key counts as none', () => {
    assert.equal(sheetIdOf(parseFrontmatter('---\nname: a\nsheetId: "2.45"\nsheetId: "2.46"\n---\n')), null);
    assert.equal(sheetIdOf(parseFrontmatter('---\nname: a\nsheetId: "2.45"\n---\n')), '2.45');
    assert.equal(sheetIdOf(parseFrontmatter('---\nname: a\n---\n')), null);
    assert.equal(renamedFromOf(parseFrontmatter('---\nname: a\nrenamed_from: b\nrenamed_from: c\n---\n')), null);
    assert.equal(renamedFromOf(parseFrontmatter('---\nname: a\nrenamed_from: b  # was b\n---\n')), 'b');
  });

  test('end to end: published without a promote, one Renamed line, the old folder gone', async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(
      shelf,
      buildStage([skill('alpha'), skill('consult-governance', { sheetId: '2.45' })]),
      ['alpha', 'consult-governance'],
      WB.a,
    );
    const stage = buildStage(
      [skill('alpha'), skill('project-governance', { sheetId: '2.45', extra: 'renamed_from: consult-governance', agents: ['helper'] })],
      { sha: WB.b },
    );
    const net = network();
    const d = deps(net);
    const result = await publish(opts(stage, shelf, { promote: '' }), d);
    assert.deepEqual(result.promotion.held, []);
    assert.deepEqual(bodyOf(net).skills.map((r) => r.slug), ['alpha', 'project-governance', 'project-governance-helper']);
    const tree = git(remote, ['ls-tree', '-r', '--name-only', 'main']);
    assert.match(tree, /^skills\/1-brand-marketing\/project-governance\/SKILL\.md$/m);
    assert.doesNotMatch(tree, /consult-governance/);
    const message = git(remote, ['log', '-1', '--format=%B', 'main']);
    assert.match(message, /^Renamed: consult-governance → project-governance$/m);
    assert.doesNotMatch(message, /^(Added|Removed):/m);
    assert.ok(d.out.includes('kept under a new name (renamed_from, same sheetId): consult-governance → project-governance'));
    assert.ok(d.out.some((l) => /^shelf: added 0 · renamed 1 · changed 0 · removed 0; pushed /.test(l)));
    assert.match(d.summary(), /after this run: 2 \(added 0 · renamed 1 · changed 0 · removed 0\)/);
  });

  test('end to end: a retired skill and a new one with its id in one run — the new one is held', async () => {
    const { shelf, remote } = makeShelf();
    placeOnShelf(shelf, buildStage([skill('alpha'), skill('retired-skill', { sheetId: '2.47' })]), ['alpha', 'retired-skill'], WB.a);
    const stage = buildStage([skill('alpha'), skill('brand-new', { cat: '5-product', sheetId: '2.47' })], { sha: WB.b });
    const net = network();
    const result = await publish(opts(stage, shelf, { promote: '', prune: 'true' }), deps(net));
    assert.deepEqual(result.promotion.held.map((s) => s.slug), ['brand-new']);
    assert.deepEqual(result.promotion.renamed, []);
    assert.deepEqual(bodyOf(net).skills.map((r) => r.slug), ['alpha']);
    assert.doesNotMatch(git(remote, ['ls-tree', '-r', '--name-only', 'main']), /brand-new|retired-skill/);
  });
});

describe('shrink', () => {
  test('a stage under half the shelf refuses unless allow_shrink, which the body carries', async () => {
    const { shelf } = makeShelf();
    placeOnShelf(shelf, buildStage([skill('a1'), skill('a2'), skill('a3'), skill('a4'), skill('a5')]), ['a1', 'a2', 'a3', 'a4', 'a5'], WB.a);
    const stage = buildStage([skill('a1'), skill('a2')], { sha: WB.b });
    await refused(publish(opts(stage, shelf), deps(network())), /leave 2 skills on a shelf that holds 5: under half/);

    const net = network();
    await publish(opts(stage, shelf, { allowShrink: true }), deps(net));
    assert.equal(bodyOf(net).allow_shrink, true);
    assert.deepEqual(fs.readdirSync(path.join(shelf, 'skills/1-brand-marketing')).sort(), ['a1', 'a2']);
  });

  test('half exactly passes; an empty shelf never refuses', () => {
    assert.doesNotThrow(() => checkShrink(2, 4, false));
    assert.throws(() => checkShrink(1, 4, false), Refusal);
    assert.doesNotThrow(() => checkShrink(0, 0, false));
  });
});

describe('order (AC-10)', () => {
  const setup = () => {
    const shelves = makeShelf();
    placeOnShelf(shelves.shelf, buildStage([skill('alpha')]), ['alpha'], WB.b);
    return shelves;
  };

  test('ahead: the workbench is asked, with the token, and the run proceeds', async () => {
    const { shelf, remote } = setup();
    const stage = buildStage([skill('alpha'), skill('beta')], { sha: WB.c });
    const net = network({ compare: 'ahead' });
    const result = await publish(opts(stage, shelf), deps(net));
    const compare = net.calls[0];
    assert.equal(compare.url, `https://api.github.com/repos/peter-tu-zynkr/zynkr-skill-builder/compare/${WB.b}...${WB.c}?per_page=1`);
    assert.equal(compare.init.headers.Authorization, `Bearer ${TOKEN}`);
    assert.equal(result.order, 'ahead');
    assert.match(git(remote, ['log', '-1', '--format=%B', 'main']), new RegExp(`Workbench-Commit: ${WB.c}\\s*$`));
    assert.equal(net.posts().length, 1);
  });

  test('behind: exit 0, no commit, no post', async () => {
    const { shelf, remote } = setup();
    const before = head(remote, 'main');
    const stage = buildStage([skill('alpha'), skill('beta')], { sha: WB.a });
    const net = network({ compare: 'behind' });
    const d = deps(net);
    assert.equal(await main(argv(stage, shelf, '--promote', 'all'), d), 0);
    assert.equal(head(remote, 'main'), before);
    assert.equal(net.posts().length, 0);
    assert.equal(fs.existsSync(path.join(shelf, 'skills/1-brand-marketing/beta')), false);
  });

  test('diverged: refused unless allow_rewind, which records the new base even with no file changed', async () => {
    const { shelf, remote } = setup();
    const before = head(remote, 'main');
    const stage = buildStage([skill('alpha')], { sha: WB.c });
    await refused(publish(opts(stage, shelf), deps(network({ compare: 'diverged' }))), /not a descendant.*allow_rewind/);
    assert.equal(head(remote, 'main'), before);

    const net = network({ compare: 'diverged' });
    const result = await publish(opts(stage, shelf, { allowRewind: true }), deps(net));
    assert.equal(result.outcome, 'published');
    assert.equal(net.posts().length, 1);
    const message = git(remote, ['log', '-1', '--format=%B', 'main']);
    assert.match(message, /^Rewound from 2222222, dispatched with allow_rewind$/m);
    assert.match(message, new RegExp(`Workbench-Commit: ${WB.c}\\s*$`));

    const again = network({ compare: 'diverged' });
    assert.equal((await publish(opts(stage, shelf), deps(again))).order, 'identical', 'the next run is not red');
  });

  for (const [label, body, refusal] of [
    [
      'no common ancestor (a purged history)',
      { message: `No common ancestor between ${WB.b} and ${WB.c}.`, documentation_url: 'https://docs.github.com/rest' },
      /not a descendant of the last export 2222222.*allow_rewind/,
    ],
    [
      'an unknown last export',
      { message: 'Not Found', documentation_url: 'https://docs.github.com/rest', status: '404' },
      /the last export 2222222 shares no history with .* or no longer exists in the workbench.*allow_rewind/,
    ],
  ]) {
    test(`a compare 404, ${label}: refused unless allow_rewind, which records the rewind`, async () => {
      const { shelf, remote } = setup();
      const before = head(remote, 'main');
      const stage = buildStage([skill('alpha'), skill('beta')], { sha: WB.c });
      await assert.rejects(publish(opts(stage, shelf), deps(network({ compare: { status: 404, body } }))), (err) => {
        assert.ok(err instanceof Refusal, `expected a Refusal, got ${err}`);
        assert.match(err.message, refusal);
        assert.doesNotMatch(err.message, /WORKBENCH_READ_TOKEN/, 'a 404 here is not the token');
        return true;
      });
      assert.equal(head(remote, 'main'), before);

      const net = network({ compare: { status: 404, body } });
      const result = await publish(opts(stage, shelf, { allowRewind: true }), deps(net));
      assert.equal(result.outcome, 'published');
      assert.equal(net.posts().length, 1);
      const message = git(remote, ['log', '-1', '--format=%B', 'main']);
      assert.match(message, /^Rewound from 2222222, dispatched with allow_rewind$/m);
      assert.match(message, new RegExp(`Workbench-Commit: ${WB.c}\\s*$`));
    });
  }

  test('a compare the token cannot make names the secret, never its value', async () => {
    const { shelf } = setup();
    const stage = buildStage([skill('alpha')], { sha: WB.c });
    const fetchImpl = async () => new Response('{}', { status: 401 });
    const d = deps({ fetchImpl });
    assert.equal(await main(argv(stage, shelf), d), 1);
    assert.match(d.err.join('\n'), /401: the secret WORKBENCH_READ_TOKEN was refused/);
    assert.ok(!d.err.join('\n').includes(TOKEN));
  });
});

describe('prune (AC-11)', () => {
  test('schedule prunes; a dispatch reports unless told true; nothing else passes', async () => {
    assert.equal(pruneValue('schedule', undefined), true);
    assert.equal(pruneValue('schedule', 'report'), true);
    assert.equal(pruneValue('workflow_dispatch', undefined), 'report');
    assert.equal(pruneValue('workflow_dispatch', ''), 'report');
    assert.equal(pruneValue('workflow_dispatch', 'true'), true);
    assert.throws(() => pruneValue('workflow_dispatch', 'yes'), Refusal);
    assert.throws(() => pruneValue('push', 'true'), Refusal);

    const stage = buildStage(trio());
    const { shelf } = makeShelf();
    const net = network();
    await publish(opts(stage, shelf, { event: 'schedule', prune: undefined }), deps(net));
    assert.equal(bodyOf(net).prune, true);
  });
});

describe("the site's answer in this public log", () => {
  const everything = (d) => [...d.out, ...d.err, d.summary()].join('\n');

  test('a report run logs how many rows would go, never which', async () => {
    const stage = buildStage(trio());
    const { shelf } = makeShelf();
    const net = network({ answer: { upserted: 4, unchanged: 0, would_prune: ['quiet-internal-tool', 'old-team-skill'] } });
    const d = deps(net);
    assert.equal(await main(argv(stage, shelf, '--promote', 'all'), d), 0);
    assert.ok(d.out.includes('site: 200 · upserted 4 · unchanged 0 · would_prune 2'), d.out.join('\n'));
    assert.match(d.summary(), /- Site: 200 · upserted 4 · unchanged 0 · would_prune 2/);
    for (const slug of ['quiet-internal-tool', 'old-team-skill']) assert.ok(!everything(d).includes(slug), `${slug} reached the log`);
  });

  test('a prune run logs how many rows went, never which', async () => {
    const stage = buildStage(trio());
    const { shelf } = makeShelf();
    const net = network({ answer: { upserted: 0, unchanged: 4, pruned: ['quiet-internal-tool'] } });
    const d = deps(net);
    assert.equal(await main(argv(stage, shelf, '--promote', 'all', '--prune', 'true'), d), 0);
    assert.ok(d.out.includes('site: 200 · upserted 0 · unchanged 4 · pruned 1'), d.out.join('\n'));
    assert.ok(!everything(d).includes('quiet-internal-tool'));
  });

  test('a non-2xx answer exits 1 with its status, counts and error word, never its lists', async () => {
    const stage = buildStage(trio());
    const { shelf } = makeShelf();
    const net = network({ status: 409, answer: { upserted: 4, would_prune: ['old-skill'], error: 'valve' } });
    const d = deps(net);
    assert.equal(await main(argv(stage, shelf, '--promote', 'all', '--prune', 'true'), d), 1);
    assert.match(d.err.join('\n'), /answered 409 · upserted 4 · would_prune 1 · error "valve"$/);
    assert.ok(!everything(d).includes('old-skill'));

    const stale = deps(network({ status: 409, answer: { error: 'stale', newest_applied: '2026-09-29T00:00:00.000Z' } }));
    assert.equal(await main(argv(stage, shelf, '--promote', 'all'), stale), 1);
    assert.match(stale.err.join('\n'), /answered 409 · error "stale" · newest_applied 2026-09-29T00:00:00\.000Z$/);
  });

  test('a reply that is not JSON is described by its size', async () => {
    const stage = buildStage(trio());
    const { shelf } = makeShelf();
    const fetchImpl = async (url) => {
      if (String(url) === SITE) return new Response('<html>quiet-internal-tool</html>', { status: 502 });
      throw new Error(`unexpected fetch ${url}`);
    };
    const d = deps({ fetchImpl });
    assert.equal(await main(argv(stage, shelf, '--promote', 'all'), d), 1);
    assert.match(d.err.join('\n'), /answered 502 \(a reply that is not a JSON object, 32 bytes\)$/);
    assert.ok(!everything(d).includes('quiet-internal-tool'));
  });
});

describe('failures after the checks', () => {

  test('a rejected push posts nothing', async () => {
    const { base, remote, shelf } = makeShelf();
    const other = path.join(base, 'other');
    git(base, ['clone', '-q', remote, other]);
    writeFile(other, 'README.md', '# moved on\n');
    git(other, ['-c', 'user.name=T', '-c', 'user.email=t@example.test', 'commit', '-q', '-am', 'elsewhere']);
    git(other, ['push', '-q']);

    const stage = buildStage(trio());
    const net = network();
    await refused(publish(opts(stage, shelf), deps(net)), /git push was rejected, so nothing is posted/);
    assert.equal(net.posts().length, 0);
  });

  test('a .gitattributes rule that would rewrite bytes on the way into git refuses before the commit', async () => {
    const stage = buildStage([skill('alpha', { files: { '.gitattributes': '*.txt text\n', 'crlf.txt': 'one\r\ntwo\r\n' } })]);
    const { shelf, remote } = makeShelf();
    const before = head(remote, 'main');
    const net = network();
    await refused(publish(opts(stage, shelf), deps(net)), /git's index differs from the stage at 1 path \(skills\/1-brand-marketing\/alpha\/crlf\.txt\)/);
    assert.equal(head(shelf), before, 'no commit');
    assert.equal(net.posts().length, 0);
  });

  test('without the sync secret nothing is pushed', async () => {
    const stage = buildStage(trio());
    const { shelf, remote } = makeShelf();
    const before = head(remote, 'main');
    await refused(publish(opts(stage, shelf), deps(network(), { SKILLS_SYNC_HMAC_SECRET: '' })), /SKILLS_SYNC_HMAC_SECRET is not set/);
    assert.equal(head(remote, 'main'), before);
  });
});
