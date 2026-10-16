import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { ATLAS, OIDC, OIDC_REQUEST_TOKEN, atlasList, network, oidcToken } from './fixtures.mjs';
import { ATLAS_AUDIENCE, askAtlas, atlasWords, pinnedClaims, readList } from './atlas.mjs';

const env = { ACTIONS_ID_TOKEN_REQUEST_URL: OIDC, ACTIONS_ID_TOKEN_REQUEST_TOKEN: OIDC_REQUEST_TOKEN };
const TREE = 'a'.repeat(40);

describe("the shape of Atlas's answer", () => {
  test('folders with a tree and 「as is」 paths, one entry per path', () => {
    const list = readList(atlasList([['skills/1-x/alpha', TREE]], ['skills/1-x/kept']));
    assert.equal(list.folders.get('skills/1-x/alpha'), TREE);
    assert.ok(list.asIs.has('skills/1-x/kept'));
  });

  test('anything else is refused whole', () => {
    const bad = [
      null,
      { ...atlasList(), format: 'atlas-shelf-v2' },
      atlasList([['skills/1-x/alpha', 'not-a-tree']]),
      atlasList([['skills/../etc', TREE]]),
      atlasList([['other/1-x/alpha', TREE]]),
      atlasList([['skills/1-x/alpha', TREE], ['skills/1-x/alpha', TREE]]),
      atlasList([['skills/1-x/alpha', TREE]], ['skills/1-x/alpha']),
      { format: 'atlas-shelf-v1', folders: [{ path: 'skills/1-x/a', tree: TREE }] },
    ];
    for (const data of bad) assert.equal(readList(data), null);
  });
});

describe('asking the door', () => {
  test('asks GitHub for a token with the shelf audience, then posts it as a bearer token', async () => {
    const net = network({ atlas: atlasList([['skills/1-x/alpha', TREE]]) });
    const answer = await askAtlas({ env, fetchImpl: net.fetchImpl, url: ATLAS });
    assert.equal(answer.ok, true);
    assert.equal(answer.list.folders.size, 1);
    const [tokenCall, doorCall] = net.calls;
    assert.equal(tokenCall.url, `${OIDC}&audience=${ATLAS_AUDIENCE}`);
    assert.equal(tokenCall.init.headers.Authorization, `bearer ${OIDC_REQUEST_TOKEN}`);
    assert.equal(doorCall.url, ATLAS);
    assert.equal(doorCall.init.method, 'POST');
    assert.equal(doorCall.init.headers.Authorization, `Bearer ${oidcToken(ATLAS_AUDIENCE)}`);
    assert.equal(doorCall.init.redirect, 'manual', 'never follows a redirect with the token');
    assert.equal(answer.claims.environment, 'export');
    assert.equal(answer.claims.sub, 'repo:peter-tu-zynkr@262132933/zynkr-ai-skills@1401051249:environment:export');
  });

  test('every way it can fail is a word, never the answer', async () => {
    const cases = [
      [{}, network(), 'no_token'],
      [env, network({ atlas: 'down' }), 'unreachable'],
      // The door's own answers: 401 {"error":"refused"} and 503 {"error":"try_later"}, no reason.
      [env, network({ atlas: { status: 401, body: { error: 'refused' } } }), 'refused'],
      [env, network({ atlas: { status: 503, body: { error: 'try_later' } } }), 'try_later'],
      [env, network({ atlas: { status: 500, body: { error: 'boom' } } }), 'unreadable'],
      [env, network({ atlas: { format: 'atlas-shelf-v1', folders: 'all of them', as_is: [] } }), 'unreadable'],
    ];
    for (const [e, net, why] of cases) {
      const answer = await askAtlas({ env: e, fetchImpl: net.fetchImpl, url: ATLAS });
      assert.equal(answer.ok, false);
      assert.equal(answer.why, why);
      assert.ok(!('list' in answer));
    }
    // Whatever a refusal's body says, the run says it in its own words, and repeats none of it.
    const refused = await askAtlas({ env, fetchImpl: network({ atlas: { status: 401, body: { error: 'refused', reason: 'quiet-internal-tool' } } }).fetchImpl, url: ATLAS });
    assert.equal(atlasWords(refused), "Atlas refused this job's token");
    assert.equal(atlasWords(refused, 'wrong_audience'), "Atlas refused this job's token (a seeded dispatch: a token asked for another audience)");
    assert.ok(!JSON.stringify(refused).includes('quiet-internal-tool'));
  });

  test('a token for another audience is refused by the door (the seeded proof)', async () => {
    const net = network({ atlas: atlasList() });
    const answer = await askAtlas({ env, fetchImpl: net.fetchImpl, url: ATLAS, audience: `${ATLAS_AUDIENCE}-seed` });
    assert.equal(answer.why, 'refused');
    assert.equal(answer.ok, false);
  });

  test('the claims it prints are only the pinned ones, and only printable values', () => {
    const claims = pinnedClaims(oidcToken('zynkr-atlas-shelf'));
    assert.deepEqual(Object.keys(claims).sort(), ['aud', 'environment', 'event_name', 'job_workflow_ref', 'ref', 'repository', 'repository_id', 'repository_owner_id', 'sub', 'workflow_ref']);
    assert.equal(pinnedClaims('not-a-jwt'), null);
  });
});
