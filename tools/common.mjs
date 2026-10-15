/**
 * common.mjs — what fetch-stage.mjs and publish.mjs share (SKB-038).
 *
 * Both talk to the private workbench with WORKBENCH_READ_TOKEN, a fine-grained PAT that reads
 * peter-tu-zynkr/zynkr-skill-builder (Contents and Actions, read-only). This repo's logs are
 * public: a message may name the secret, never its value.
 */

export const SHELF_REPO = 'peter-tu-zynkr/zynkr-ai-skills';
export const SHELF_URL = `https://github.com/${SHELF_REPO}`;
export const WORKBENCH = 'peter-tu-zynkr/zynkr-skill-builder';
export const SITE_SYNC_URL = 'https://zynkr.ai/api/skills/sync';
/** zynkr.ai's own public answer: its live rows, keyed by id (first_seen is carried from it, ATL-113 D-142). */
export const SITE_DETAILS_URL = 'https://zynkr.ai/api/skills/details';

/** A check that failed on purpose. The CLI prints its message and exits 1. */
export class Refusal extends Error {}

export const refuse = (message) => {
  throw new Refusal(message);
};

export const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export const githubHeaders = (token) => ({
  Accept: 'application/vnd.github+json',
  Authorization: `Bearer ${token}`,
  'User-Agent': 'zynkr-ai-skills-export',
  'X-GitHub-Api-Version': '2022-11-28',
});

/** Why the workbench API answered `status`, in words that point at the secret to fix. */
export function httpHint(status) {
  switch (status) {
    case 401:
      return 'the secret WORKBENCH_READ_TOKEN was refused (missing, expired or revoked)';
    case 403:
      return `the secret WORKBENCH_READ_TOKEN lacks read access to ${WORKBENCH} (Contents and Actions), or the API rate limit was hit`;
    case 404:
      return `not found: the secret WORKBENCH_READ_TOKEN cannot see ${WORKBENCH}, or what was asked for does not exist there`;
    default:
      return 'an unexpected answer';
  }
}

/** Workflow-command escaping, so a multi-line message stays one ::error:: annotation. */
export const annotation = (message) =>
  message.replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');

/**
 * An unexpected error, as this public log may show it: its kind, its code and the line of this
 * repo's code it came from — never its message, which can quote the path of a staged file that is
 * new to the shelf (and may be a client build marked public by mistake).
 */
export function unexpectedWords(err) {
  const name = typeof err?.name === 'string' && /^[A-Za-z]{1,40}$/.test(err.name) ? err.name : 'Error';
  const code = typeof err?.code === 'string' && /^[A-Z0-9_]{1,40}$/.test(err.code) ? ` ${err.code}` : '';
  const frame = /tools\/[a-z-]+\.mjs:\d+/.exec(String(err?.stack ?? ''));
  return `unexpected failure: ${name}${code}${frame ? ` at ${frame[0]}` : ''}`;
}
