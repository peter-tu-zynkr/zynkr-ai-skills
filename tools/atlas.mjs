/**
 * atlas.mjs — ask Zynkr Atlas which skill folders may leave the team, now (ATL-113 Part D, §15.4).
 *
 * No secret: the job asks GitHub Actions for an OIDC token with the audience `zynkr-atlas-shelf`
 * (the publish job holds `id-token: write`) and posts it to Atlas's door, which checks that GitHub
 * signed it for this repository's export workflow, on main, in its `export` environment. The token
 * is asked for right before the call: the door takes one no older than ten minutes.
 *
 * The answer is `{ format: "atlas-shelf-v1", folders: [{ path, tree }], as_is: [{ path }] }`: the
 * folders that may leave at the git tree each may leave at, and the two folders kept as the shelf
 * has them. It is checked here to exactly that shape (the door's own check, again) and kept in
 * memory. This repo's logs are public: nothing in this module prints, and a caller prints no part
 * of the answer and no count of it — only what the run decided.
 */

export const ATLAS_SHELF_URL = 'https://atlas.zynkr.ai/api/shelf';
export const ATLAS_AUDIENCE = 'zynkr-atlas-shelf';

const SHA40 = /^[0-9a-f]{40}$/;
const PATH_SHAPE = /^skills(\/[A-Za-z0-9._-]+)+$/;
const DOT_SEGMENT = /(^|\/)\.\.?(\/|$)/;
const MAX_ANSWER = 2 * 1024 * 1024;

/** The door's refusal codes; only these are ever printed. */
export const REFUSAL_CODES = new Set([
  'no_token', 'bad_token', 'expired', 'wrong_issuer', 'wrong_audience', 'wrong_repository',
  'wrong_ref', 'wrong_event', 'wrong_workflow', 'wrong_environment', 'wrong_subject',
]);

/** The claims the door pins, by name: printed in `report` so the pins can be checked against a real token. */
export const PINNED_CLAIMS = [
  'aud', 'sub', 'repository', 'repository_id', 'repository_owner_id', 'ref', 'event_name',
  'environment', 'workflow_ref', 'job_workflow_ref',
];

const safePath = (p) => typeof p === 'string' && PATH_SHAPE.test(p) && !DOT_SEGMENT.test(p);
const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

/** The answer, refused unless it has exactly the shape the door promises: { folders: Map(path → tree), asIs: Set }. */
export function readList(data) {
  if (!isObject(data) || data.format !== 'atlas-shelf-v1' || !Array.isArray(data.folders) || !Array.isArray(data.as_is)) return null;
  const folders = new Map();
  const asIs = new Set();
  for (const f of data.folders) {
    if (!isObject(f) || !safePath(f.path) || typeof f.tree !== 'string' || !SHA40.test(f.tree) || folders.has(f.path)) return null;
    folders.set(f.path, f.tree);
  }
  for (const a of data.as_is) {
    if (!isObject(a) || !safePath(a.path) || folders.has(a.path) || asIs.has(a.path)) return null;
    asIs.add(a.path);
  }
  return { folders, asIs };
}

/** The pinned claims of a token, decoded (not verified: Atlas verifies). Printable values only. */
export function pinnedClaims(token) {
  try {
    const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
    return Object.fromEntries(
      PINNED_CLAIMS.map((name) => {
        const v = payload[name];
        const text = typeof v === 'string' || typeof v === 'number' ? String(v) : null;
        return [name, text !== null && /^[\w@:./-]{1,200}$/.test(text) ? text : '(not printable)'];
      }),
    );
  } catch {
    return null;
  }
}

/**
 * Ask Atlas. Resolves to { ok: true, list, claims } or { ok: false, why, reason?, status?, claims? }:
 *   no_token     GitHub gave no OIDC token (the job lacks id-token: write, or this is not Actions)
 *   unreachable  the door could not be reached or did not answer in time
 *   refused      401 — `reason` is the door's code when it is one of REFUSAL_CODES
 *   try_later    503 — Atlas could not read its keys or its database
 *   unreadable   any other answer, or a body that is not exactly the list (`status` its HTTP status)
 */
export async function askAtlas({ env, fetchImpl = globalThis.fetch, url = ATLAS_SHELF_URL, audience = ATLAS_AUDIENCE, timeoutMs = 20_000 }) {
  const requestUrl = env.ACTIONS_ID_TOKEN_REQUEST_URL;
  const requestToken = env.ACTIONS_ID_TOKEN_REQUEST_TOKEN;
  if (!requestUrl || !requestToken) return { ok: false, why: 'no_token' };

  let token = null;
  try {
    const res = await fetchImpl(`${requestUrl}&audience=${encodeURIComponent(audience)}`, {
      headers: { Authorization: `bearer ${requestToken}`, Accept: 'application/json' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (res.ok) {
      const body = await res.json();
      if (typeof body?.value === 'string' && /^[A-Za-z0-9._-]+$/.test(body.value)) token = body.value;
    }
  } catch {
    token = null;
  }
  if (!token) return { ok: false, why: 'no_token' };
  const claims = pinnedClaims(token);

  let res;
  try {
    res = await fetchImpl(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json', 'User-Agent': 'zynkr-ai-skills-export' },
      redirect: 'manual',
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    return { ok: false, why: 'unreachable', claims };
  }
  let text = '';
  try {
    text = await res.text();
  } catch {
    return { ok: false, why: 'unreachable', claims };
  }
  if (res.status === 401) {
    let reason;
    try {
      const code = JSON.parse(text)?.reason;
      if (REFUSAL_CODES.has(code)) reason = code;
    } catch {
      // no readable reason; the status says enough
    }
    return { ok: false, why: 'refused', reason, claims };
  }
  if (res.status === 503) return { ok: false, why: 'try_later', claims };
  if (res.status !== 200 || text.length > MAX_ANSWER) return { ok: false, why: 'unreadable', status: res.status, claims };
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    return { ok: false, why: 'unreadable', status: res.status, claims };
  }
  const list = readList(data);
  return list ? { ok: true, list, claims } : { ok: false, why: 'unreadable', status: res.status, claims };
}

/** One phrase for a failed ask, safe for the public log. */
export function atlasWords(answer) {
  switch (answer.why) {
    case 'no_token':
      return 'GitHub gave this job no OIDC token (does the publish job hold id-token: write?)';
    case 'unreachable':
      return 'the door could not be reached';
    case 'refused':
      return `the door refused this job's token${answer.reason ? ` (${answer.reason})` : ''}`;
    case 'try_later':
      return 'Atlas answered try_later (its keys or its database could not be read)';
    default:
      return `the door's answer could not be read${answer.status ? ` (HTTP ${answer.status})` : ''}`;
  }
}
