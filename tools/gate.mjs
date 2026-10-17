#!/usr/bin/env node
/**
 * gate.mjs — ATL-113 D6 (D-145): what a run the owner did not start may do.
 *
 * The hourly tick in zynkr.ai's Vercel project starts this workflow through a GitHub App of the
 * owner's own, which holds Actions read and write on this repo alone. Actions write is the only
 * permission that can dispatch, and it can also re-run any run of the last 30 days, with that run's
 * original inputs and at its original commit. On a re-run github.actor stays the first run's; only
 * github.triggering_actor changes. So for a run whose triggering actor is not the repo's owner:
 *   - a re-run (run_attempt above 1) is refused;
 *   - a dispatch must be on main with prune the only input set (no promote, allow_shrink,
 *     allow_rewind, seed_fail or seed_atlas), and it runs only while SHELF_LIVE is 'true': otherwise
 *     it stops quietly, so SHELF_LIVE stays the off switch.
 * The owner's own runs, re-runs included, and the first attempt of GitHub's schedule pass as before.
 *
 * The gate job runs it before the export environment and hands `go` to the publish job. The publish
 * job asks the re-run rule again (--rerun) before any step that reads a secret, because re-running
 * that job alone reuses the gate job's answer from the first attempt. A run made before this file
 * existed is beyond its reach: D-145's M3 deletes those, by the owner's own line.
 *
 * It reads only the workflow's context, passed through env; nothing it prints is secret:
 *   OWNER TRIGGERED_BY ATTEMPT EVENT REF SHELF_LIVE PROMOTE ALLOW_SHRINK ALLOW_REWIND SEED_FAIL SEED_ATLAS
 *   node tools/gate.mjs            # the gate job: writes go=true|false to GITHUB_OUTPUT
 *   node tools/gate.mjs --rerun    # the publish job's first check: the re-run rule alone
 */

import fs from 'node:fs';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import { Refusal, annotation, refuse, unexpectedWords } from './common.mjs';

/** The re-run rule: a run past its first attempt passes only if the owner triggered it. */
export function rerunRule(env) {
  const owner = String(env.OWNER ?? '');
  const by = String(env.TRIGGERED_BY ?? '');
  const attempt = String(env.ATTEMPT ?? '');
  if (!owner) refuse("the repository's owner is not known, so no run passes the gate");
  if (!by) refuse('who started this run is not known, so it does not pass the gate');
  if (!/^[1-9][0-9]{0,5}$/.test(attempt)) refuse(`the run attempt is not a number (${attempt ? 'unreadable' : 'empty'})`);
  if (by !== owner && attempt !== '1') refuse(`attempt ${attempt} was started by ${by}: only ${owner} may re-run a run (D-145)`);
  return { owner, by, attempt };
}

/** The gate job's answer: { go, why }, or a Refusal for a run that may not go further. */
export function gate(env) {
  const { owner, by } = rerunRule(env);
  if (by === owner) return { go: true, why: `started by ${owner}` };
  const event = String(env.EVENT ?? '');
  if (event === 'schedule') return { go: true, why: "GitHub's schedule" };
  if (event !== 'workflow_dispatch') refuse(`a ${event ? `${event} run` : 'run of no known event'} started by ${by}`);
  if (env.REF !== 'refs/heads/main') refuse(`${by} dispatched on ${env.REF || 'no ref'}: a run the owner did not start runs on main only (D-145)`);
  const set = [];
  if (env.PROMOTE) set.push('promote');
  if (env.ALLOW_SHRINK === 'true') set.push('allow_shrink');
  if (env.ALLOW_REWIND === 'true') set.push('allow_rewind');
  if (env.SEED_FAIL === 'true') set.push('seed_fail');
  if (env.SEED_ATLAS && env.SEED_ATLAS !== 'none') set.push('seed_atlas');
  if (set.length) refuse(`${by} dispatched with ${set.join(', ')}: a run the owner did not start takes prune alone (D-145)`);
  if (env.SHELF_LIVE !== 'true') return { go: false, why: `SHELF_LIVE is not 'true', so a run ${by} started does nothing` };
  return { go: true, why: `a plain dispatch by ${by}` };
}

export function main(argv = process.argv.slice(2), deps = {}) {
  const env = deps.env ?? process.env;
  const log = deps.log ?? console.log;
  const error = deps.error ?? console.error;
  try {
    let values;
    try {
      ({ values } = parseArgs({ args: argv, options: { rerun: { type: 'boolean' } } }));
    } catch (err) {
      refuse(`${err.message}\nusage: gate.mjs [--rerun]`);
    }
    if (values.rerun) {
      const { by, attempt } = rerunRule(env);
      log(`gate: attempt ${attempt}, started by ${by}: passes the re-run rule`);
      return 0;
    }
    const { go, why } = gate(env);
    log(`gate: ${go ? 'go' : 'stop'} · ${why}`);
    if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT, `go=${go}\n`);
    return 0;
  } catch (err) {
    const message = err instanceof Refusal ? err.message : unexpectedWords(err);
    error(env.GITHUB_ACTIONS === 'true' ? `::error::${annotation(message)}` : `refused: ${message}`);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = main();
}
