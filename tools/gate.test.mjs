/**
 * The tick's gate (ATL-113 D6, D-145): what a run the repo's owner did not start may do. The App's
 * name here is made up; the gate keys on the owner, never on it.
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from './fixtures.mjs';
import { Refusal } from './common.mjs';
import { gate, main, rerunRule } from './gate.mjs';

const OWNER = 'peter-tu-zynkr';
const APP = 'shelf-tick[bot]';
/** The tick's own dispatch, as the gate job sees it. */
const TICK = {
  OWNER,
  TRIGGERED_BY: APP,
  ATTEMPT: '1',
  EVENT: 'workflow_dispatch',
  REF: 'refs/heads/main',
  SHELF_LIVE: 'true',
  PROMOTE: '',
  ALLOW_SHRINK: 'false',
  ALLOW_REWIND: 'false',
  SEED_FAIL: 'false',
  SEED_ATLAS: 'none',
};
const refused = (fn, pattern) =>
  assert.throws(fn, (err) => {
    assert.ok(err instanceof Refusal, `expected a Refusal, got ${err?.stack ?? err}`);
    assert.match(err.message, pattern);
    return true;
  });
const run = (argv, env) => {
  const out = [];
  const err = [];
  const code = main(argv, { env, log: (l) => out.push(l), error: (l) => err.push(l) });
  return { code, out: out.join('\n'), err: err.join('\n') };
};

describe('the gate (D-145)', () => {
  test("the tick's first, plain dispatch on main goes while SHELF_LIVE is 'true'", () => {
    assert.deepEqual(gate(TICK), { go: true, why: `a plain dispatch by ${APP}` });
    assert.equal(gate({ ...TICK, PRUNE: 'report' }).go, true, 'prune may be either of its values');
  });

  test('with SHELF_LIVE off, a run someone else started stops quietly', () => {
    for (const live of ['', 'false', 'TRUE']) {
      assert.deepEqual(gate({ ...TICK, SHELF_LIVE: live }), { go: false, why: `SHELF_LIVE is not 'true', so a run ${APP} started does nothing` });
    }
  });

  test('every input but prune is refused, each by name', () => {
    refused(() => gate({ ...TICK, PROMOTE: 'all' }), /dispatched with promote: a run the owner did not start takes prune alone/);
    refused(() => gate({ ...TICK, ALLOW_SHRINK: 'true' }), /with allow_shrink:/);
    refused(() => gate({ ...TICK, ALLOW_REWIND: 'true' }), /with allow_rewind:/);
    refused(() => gate({ ...TICK, SEED_FAIL: 'true' }), /with seed_fail:/);
    refused(() => gate({ ...TICK, SEED_ATLAS: 'unreachable' }), /with seed_atlas:/);
    refused(() => gate({ ...TICK, PROMOTE: '3.24', ALLOW_SHRINK: 'true', SEED_ATLAS: 'wrong_audience' }), /with promote, allow_shrink, seed_atlas:/);
    refused(() => gate({ ...TICK, PROMOTE: 'all', SHELF_LIVE: 'false' }), /with promote/);
  });

  test('a dispatch on any ref but main is refused', () => {
    refused(() => gate({ ...TICK, REF: 'refs/heads/atl-113-part-d-shelf' }), /dispatched on refs\/heads\/atl-113-part-d-shelf: a run the owner did not start runs on main only/);
    refused(() => gate({ ...TICK, REF: 'refs/tags/v1' }), /on main only/);
    refused(() => gate({ ...TICK, REF: '' }), /dispatched on no ref/);
  });

  test('a re-run the owner did not trigger is refused, whatever the run was', () => {
    refused(() => gate({ ...TICK, ATTEMPT: '2' }), /attempt 2 was started by shelf-tick\[bot\]: only peter-tu-zynkr may re-run a run/);
    refused(() => gate({ ...TICK, EVENT: 'schedule', ATTEMPT: '2' }), /only peter-tu-zynkr may re-run/);
    refused(() => gate({ ...TICK, TRIGGERED_BY: 'a-collaborator', ATTEMPT: '5', PROMOTE: 'all' }), /attempt 5 was started by a-collaborator/);
    refused(() => rerunRule({ ...TICK, ATTEMPT: '2' }), /only peter-tu-zynkr may re-run/);
  });

  test("the owner's runs pass as before: any input, any attempt", () => {
    assert.deepEqual(gate({ ...TICK, TRIGGERED_BY: OWNER, PROMOTE: 'all', ALLOW_SHRINK: 'true', SHELF_LIVE: '' }), { go: true, why: `started by ${OWNER}` });
    assert.equal(gate({ ...TICK, TRIGGERED_BY: OWNER, ATTEMPT: '3', REF: 'refs/heads/other' }).go, true);
    assert.equal(rerunRule({ ...TICK, TRIGGERED_BY: OWNER, ATTEMPT: '2' }).attempt, '2');
  });

  test("GitHub's schedule passes on its first attempt; any other event someone else starts is refused", () => {
    assert.deepEqual(gate({ ...TICK, EVENT: 'schedule', PROMOTE: '', SHELF_LIVE: 'true' }), { go: true, why: "GitHub's schedule" });
    refused(() => gate({ ...TICK, EVENT: 'push' }), /a push run started by shelf-tick\[bot\]/);
    refused(() => gate({ ...TICK, EVENT: '' }), /a run of no known event/);
  });

  test('nothing passes when the owner, the starter or the attempt is unknown', () => {
    refused(() => gate({ ...TICK, OWNER: '' }), /owner is not known/);
    refused(() => gate({ ...TICK, TRIGGERED_BY: '' }), /who started this run is not known/);
    refused(() => gate({ ...TICK, ATTEMPT: '' }), /the run attempt is not a number \(empty\)/);
    refused(() => gate({ ...TICK, ATTEMPT: '1; rm -rf' }), /not a number \(unreadable\)/);
    refused(() => gate({ ...TICK, ATTEMPT: '0' }), /not a number/);
  });
});

describe('gate.mjs, the command', () => {
  test('the gate job writes go to GITHUB_OUTPUT and says why', () => {
    const output = path.join(scratch('gate'), 'output');
    for (const [env, go] of [
      [TICK, 'true'],
      [{ ...TICK, SHELF_LIVE: 'false' }, 'false'],
    ]) {
      fs.writeFileSync(output, '');
      const r = run([], { ...env, GITHUB_OUTPUT: output });
      assert.equal(r.code, 0);
      assert.equal(fs.readFileSync(output, 'utf8'), `go=${go}\n`);
      assert.match(r.out, go === 'true' ? /^gate: go · a plain dispatch by shelf-tick\[bot\]$/ : /^gate: stop · SHELF_LIVE is not 'true'/);
    }
  });

  test('a refusal exits 1, as an ::error:: annotation in Actions, and writes no go', () => {
    const output = path.join(scratch('gate'), 'output');
    fs.writeFileSync(output, '');
    const r = run([], { ...TICK, PROMOTE: 'all', GITHUB_OUTPUT: output, GITHUB_ACTIONS: 'true' });
    assert.equal(r.code, 1);
    assert.match(r.err, /^::error::shelf-tick\[bot\] dispatched with promote: a run the owner did not start takes prune alone \(D-145\)$/);
    assert.equal(fs.readFileSync(output, 'utf8'), '');
    assert.match(run([], { ...TICK, ATTEMPT: '2' }).err, /^refused: attempt 2 was started by shelf-tick\[bot\]/);
  });

  test('--rerun asks the re-run rule alone, for the publish job', () => {
    const plainRerun = run(['--rerun'], { ...TICK, PROMOTE: 'all', SHELF_LIVE: 'false' });
    assert.equal(plainRerun.code, 0, 'inputs and SHELF_LIVE are the gate job’s to judge');
    assert.match(plainRerun.out, /^gate: attempt 1, started by shelf-tick\[bot\]: passes the re-run rule$/);
    assert.equal(run(['--rerun'], { ...TICK, ATTEMPT: '2' }).code, 1);
    assert.equal(run(['--rerun'], { ...TICK, TRIGGERED_BY: OWNER, ATTEMPT: '2' }).code, 0);
    assert.match(run(['--nope'], TICK).err, /usage: gate\.mjs \[--rerun\]/);
  });
});
