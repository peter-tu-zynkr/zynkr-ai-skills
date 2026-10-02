#!/usr/bin/env node
/**
 * fetch-stage.mjs — SKB-038: download the newest public stage the workbench built.
 *
 * The private workbench's export-stage.yml builds the public tree and keeps it as a 3-day
 * artifact named `stage` holding one file, stage.tgz. This finds the newest successful run of
 * that workflow on main, downloads the artifact with GH_TOKEN (the secret WORKBENCH_READ_TOKEN:
 * Actions read on the workbench), and unpacks stage.tgz into --out, giving <out>/stage/.
 *
 * The run must be what it says before anything is downloaded: on the workbench's own main, started
 * by push, schedule or dispatch, at a commit main holds. It then writes <out>/run.json
 * ({ id, head_sha, event, head_branch, created_at }), and publish.mjs --run refuses a stage whose
 * workbench_sha is not that run's commit.
 *
 * The artifact API answers with a redirect to a signed blob URL; the token goes to api.github.com
 * only, never to the blob host. Nothing about the stage's contents is printed (this repo's logs
 * are public): only the run id, its head sha and when it ran. publish.mjs checks the rest.
 *
 *   GH_TOKEN=… node tools/fetch-stage.mjs --out "$RUNNER_TEMP/in"
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import { Refusal, WORKBENCH, annotation, githubHeaders, httpHint, plural, refuse } from './common.mjs';

const API = `https://api.github.com/repos/${WORKBENCH}`;
const WORKFLOW = 'export-stage.yml';
const ARTIFACT = 'stage';
const EVENTS = new Set(['push', 'schedule', 'workflow_dispatch']);
const SHA_RE = /^[0-9a-f]{40}$/;

async function getJson(fetchImpl, url, token, what) {
  let res;
  try {
    res = await fetchImpl(url, { headers: githubHeaders(token) });
  } catch (err) {
    refuse(`${what} failed: ${err.message}`);
  }
  if (!res.ok) refuse(`${what} answered ${res.status}: ${httpHint(res.status)}`);
  return res.json();
}

/** The zip's bytes: ask the API (with the token), then follow its redirect without the token. */
async function downloadZip(fetchImpl, artifactId, token) {
  const what = `downloading artifact ${artifactId}`;
  let res;
  try {
    res = await fetchImpl(`${API}/actions/artifacts/${artifactId}/zip`, {
      headers: githubHeaders(token),
      redirect: 'manual',
    });
    if (res.status >= 300 && res.status < 400) {
      const location = res.headers.get('location');
      if (!location || new URL(location).protocol !== 'https:') refuse(`${what}: the API redirected nowhere usable`);
      // A fresh request with no headers: the signed URL needs no credential and must not see one.
      res = await fetchImpl(location, { redirect: 'follow' });
    }
  } catch (err) {
    if (err instanceof Refusal) throw err;
    refuse(`${what} failed: ${err.message}`);
  }
  if (!res.ok) refuse(`${what} answered ${res.status}: ${httpHint(res.status)}`);
  return Buffer.from(await res.arrayBuffer());
}

/**
 * Unpack the artifact zip's stage.tgz into `out`. Every tar entry must be a plain file or folder
 * under stage/, so extraction cannot write outside `out` or plant a link.
 */
export function extractStage(zipPath, out) {
  const dir = path.dirname(zipPath);
  try {
    execFileSync('unzip', ['-q', '-o', zipPath, 'stage.tgz', '-d', dir], { stdio: ['ignore', 'ignore', 'pipe'] });
  } catch {
    refuse('the stage artifact holds no stage.tgz');
  }
  const tgz = path.join(dir, 'stage.tgz');
  const list = (args) =>
    execFileSync('tar', args, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }).split('\n').filter(Boolean);
  const names = list(['-tzf', tgz]);
  const outside = names.filter(
    (n) => n.startsWith('/') || (n !== 'stage/' && !n.startsWith('stage/')) || n.split('/').includes('..'),
  );
  if (outside.length) refuse(`stage.tgz holds ${plural(outside.length, 'entry', 'entries')} outside stage/; nothing extracted`);
  const special = list(['-tvzf', tgz]).filter((line) => !'-d'.includes(line[0])).length;
  if (special) refuse(`stage.tgz holds ${plural(special, 'link or special entry', 'links or special entries')}; nothing extracted`);

  fs.mkdirSync(out, { recursive: true });
  if (fs.existsSync(path.join(out, 'stage'))) refuse(`${out} already holds a stage/; give an empty --out`);
  execFileSync('tar', ['-xzf', tgz, '-C', out]);
}

/**
 * The run must be an export-stage.yml run of the workbench's own main, at a commit main holds.
 * GitHub lists a run started from a tag named `main` under branch main as well, and a tag push
 * reports its event as `push`, so the commit check is the one that counts: compare
 * <head_sha>...heads/main must answer identical or ahead (heads/ so a tag cannot stand in for the
 * branch). The branch, repository and event checks cost nothing on top. No message repeats a
 * branch or repository name: they would come from the private workbench.
 */
export async function checkRun(fetchImpl, run, token) {
  if (!SHA_RE.test(String(run.head_sha))) refuse(`run ${run.id} has no 40-hex head_sha`);
  if (run.head_branch !== 'main') refuse(`run ${run.id} did not run on the workbench's main`);
  if (String(run.head_repository?.full_name).toLowerCase() !== WORKBENCH.toLowerCase()) {
    refuse(`run ${run.id} ran code from another repository than ${WORKBENCH}`);
  }
  if (!EVENTS.has(run.event)) refuse(`run ${run.id} was not started by push, schedule or workflow_dispatch`);
  const compare = await getJson(
    fetchImpl,
    `${API}/compare/${run.head_sha}...heads/main?per_page=1`,
    token,
    `checking run ${run.id}'s commit against main`,
  );
  if (!['identical', 'ahead'].includes(compare.status)) {
    refuse(`run ${run.id}'s commit ${run.head_sha.slice(0, 7)} is not on the workbench's main; nothing downloaded`);
  }
}

/** Find, check, download and unpack the newest stage; write <out>/run.json. Resolves to that record. */
export async function fetchStage({ out, token, fetchImpl = globalThis.fetch, log = console.log }) {
  if (!token) refuse('GH_TOKEN is empty: set the secret WORKBENCH_READ_TOKEN in the export environment');

  const runs = await getJson(
    fetchImpl,
    `${API}/actions/workflows/${WORKFLOW}/runs?branch=main&status=success&per_page=1`,
    token,
    `listing ${WORKFLOW} runs`,
  );
  const run = runs.workflow_runs?.[0];
  if (!run) refuse(`${WORKFLOW} has no successful run on the workbench's main yet`);
  await checkRun(fetchImpl, run, token);

  const listing = await getJson(
    fetchImpl,
    `${API}/actions/runs/${run.id}/artifacts?name=${ARTIFACT}&per_page=100`,
    token,
    `listing run ${run.id}'s artifacts`,
  );
  const artifact = listing.artifacts?.find((a) => a.name === ARTIFACT);
  if (!artifact) refuse(`run ${run.id} has no artifact named ${ARTIFACT}`);
  if (artifact.expired) refuse(`run ${run.id}'s ${ARTIFACT} artifact has expired: re-run ${WORKFLOW} in the workbench`);

  const bytes = await downloadZip(fetchImpl, artifact.id, token);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'shelf-stage-'));
  const zipPath = path.join(tmp, `${ARTIFACT}.zip`);
  fs.writeFileSync(zipPath, bytes);
  extractStage(zipPath, out);
  fs.rmSync(tmp, { recursive: true, force: true });

  // Beside stage/, never in it: publish.mjs refuses anything in stage/ it did not expect.
  const record = { id: run.id, head_sha: run.head_sha, event: run.event, head_branch: run.head_branch, created_at: run.created_at };
  fs.writeFileSync(path.join(out, 'run.json'), `${JSON.stringify(record, null, 2)}\n`);
  log(`stage from run ${run.id} · head_sha ${run.head_sha} · created_at ${run.created_at}`);
  return record;
}

export async function main(argv = process.argv.slice(2), deps = {}) {
  const env = deps.env ?? process.env;
  const error = deps.error ?? console.error;
  try {
    let values;
    try {
      ({ values } = parseArgs({ args: argv, options: { out: { type: 'string' } } }));
    } catch (err) {
      refuse(`${err.message}\nusage: fetch-stage.mjs --out <dir>`);
    }
    if (!values.out) refuse('usage: fetch-stage.mjs --out <dir>');
    await fetchStage({ out: path.resolve(values.out), token: env.GH_TOKEN, ...deps });
    return 0;
  } catch (err) {
    const message = err instanceof Refusal ? err.message : `unexpected failure: ${err.message}`;
    error(env.GITHUB_ACTIONS === 'true' ? `::error::${annotation(message)}` : `refused: ${message}`);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main();
}
