import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  collectUrls,
  classifyStatus,
  checkUrl,
  findBroken,
  renderIssueBody,
  renderDryRun,
  syncIssue,
  main,
  USER_AGENT,
} from './check-field-docs-links.mjs';

const res = (status, json) => ({ status, ok: status >= 200 && status < 300, json: async () => json });
const noSleep = () => {
  const waits = [];
  const fn = async (ms) => void waits.push(ms);
  fn.waits = waits;
  return fn;
};

test('collectUrls de-duplicates external urls and groups field ids', () => {
  const map = collectUrls({
    fields: {
      b: { type: 'external', url: 'https://x.test/a' },
      a: { type: 'external', url: 'https://x.test/a' },
      c: { type: 'external', url: 'https://x.test/c' },
      d: { type: 'internal', page: 'p' },
      e: { none: 'reason' },
    },
  });
  assert.deepEqual([...map], [
    ['https://x.test/a', ['a', 'b']],
    ['https://x.test/c', ['c']],
  ]);
  assert.equal(collectUrls({}).size, 0);
});

test('classifyStatus', () => {
  assert.equal(classifyStatus(200), 'ok');
  assert.equal(classifyStatus(301), 'ok');
  assert.equal(classifyStatus(429), 'ok');
  assert.equal(classifyStatus(404), 'fail');
  assert.equal(classifyStatus(503), 'retry');
});

test('checkUrl: HEAD success sends generic user agent and a timeout signal', async () => {
  const calls = [];
  const fetchFn = async (url, init) => (calls.push(init), res(200));
  assert.deepEqual(await checkUrl('https://x.test', { fetchFn, sleep: noSleep() }), {
    url: 'https://x.test',
    ok: true,
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'HEAD');
  assert.equal(calls[0].headers['user-agent'], USER_AGENT);
  assert.ok(calls[0].signal instanceof AbortSignal);
});

test('checkUrl: falls back to GET when HEAD is rejected', async () => {
  const fetchFn = async (_u, { method }) => res(method === 'HEAD' ? 405 : 200);
  assert.equal((await checkUrl('https://x.test', { fetchFn, sleep: noSleep() })).ok, true);
});

test('checkUrl: falls back to GET when HEAD throws', async () => {
  const fetchFn = async (_u, { method }) => {
    if (method === 'HEAD') throw new Error('reset');
    return res(200);
  };
  assert.equal((await checkUrl('https://x.test', { fetchFn, sleep: noSleep() })).ok, true);
});

test('checkUrl: 429 is not a failure', async () => {
  const fetchFn = async () => res(429);
  assert.equal((await checkUrl('https://x.test', { fetchFn, sleep: noSleep() })).ok, true);
});

test('checkUrl: 404 fails at once without retrying', async () => {
  let n = 0;
  const sleep = noSleep();
  const fetchFn = async () => (n++, res(404));
  const out = await checkUrl('https://x.test', { fetchFn, sleep });
  assert.deepEqual(out, { url: 'https://x.test', ok: false, reason: 'HTTP 404' });
  assert.equal(n, 2); // HEAD then GET
  assert.deepEqual(sleep.waits, []);
});

test('checkUrl: 5xx retries twice with backoff, then reports', async () => {
  const sleep = noSleep();
  let n = 0;
  const fetchFn = async () => (n++, res(503));
  const out = await checkUrl('https://x.test', { fetchFn, sleep });
  assert.equal(out.ok, false);
  assert.equal(out.reason, 'HTTP 503');
  assert.equal(n, 6); // 3 attempts x (HEAD + GET)
  assert.deepEqual(sleep.waits, [1000, 2000]);
});

test('checkUrl: recovers when a retry succeeds', async () => {
  const sleep = noSleep();
  let n = 0;
  const fetchFn = async () => res(++n <= 2 ? 500 : 200);
  assert.equal((await checkUrl('https://x.test', { fetchFn, sleep })).ok, true);
  assert.deepEqual(sleep.waits, [1000]);
});

test('checkUrl: persistent network errors report the error message', async () => {
  const fetchFn = async () => {
    throw new Error('getaddrinfo ENOTFOUND');
  };
  const sleep = noSleep();
  const out = await checkUrl('https://x.test', { fetchFn, sleep });
  assert.deepEqual(out, { url: 'https://x.test', ok: false, reason: 'getaddrinfo ENOTFOUND' });
  assert.deepEqual(sleep.waits, [1000, 2000]);
});

test('checkUrl: non-Error throw is stringified', async () => {
  const fetchFn = async () => {
    throw 'boom'; // eslint-disable-line no-throw-literal
  };
  const out = await checkUrl('https://x.test', { fetchFn, sleep: noSleep() });
  assert.equal(out.reason, 'boom');
});

test('findBroken keeps only failures with their fields', async () => {
  const urls = new Map([
    ['https://ok.test', ['a']],
    ['https://bad.test', ['b', 'c']],
  ]);
  const fetchFn = async (u) => res(u.includes('bad') ? 404 : 200);
  assert.deepEqual(await findBroken(urls, { fetchFn, sleep: noSleep() }), [
    { url: 'https://bad.test', fields: ['b', 'c'], reason: 'HTTP 404' },
  ]);
});

const BROKEN = [{ url: 'https://bad.test', fields: ['b', 'c'], reason: 'HTTP 404' }];

test('renderIssueBody groups field ids under each url', () => {
  const body = renderIssueBody(BROKEN);
  assert.match(body, /1 external docs link\(s\)/);
  assert.match(body, /- https:\/\/bad\.test \(HTTP 404\)\n {2}- `b`\n {2}- `c`/);
});

test('renderDryRun summarises clean and broken runs', () => {
  assert.equal(renderDryRun(3, []), '3/3 URLs ok, 0 broken');
  assert.match(renderDryRun(3, BROKEN), /^2\/3 URLs ok, 1 broken\n\n/);
});

/** Fake GitHub API recording calls; `state` seeds label/issue presence. */
function fakeGithub({ label = true, issue = null } = {}) {
  const calls = [];
  const fetchFn = async (url, init) => {
    const route = url.replace('https://api.github.com/repos/o/r', '');
    calls.push(`${init.method} ${route}`);
    calls.at(-1) && init.body && calls.push(JSON.parse(init.body));
    assert.equal(init.headers.authorization, 'Bearer tok');
    if (route.startsWith('/labels/')) return label ? res(200, {}) : res(404);
    if (init.method === 'GET') return res(200, issue ? [issue] : []);
    if (route === '/issues') return res(201, { number: 9 });
    return res(init.method === 'PATCH' ? 200 : 201, {});
  };
  return { calls, fetchFn };
}

test('syncIssue opens an issue and creates the missing label', async () => {
  const { calls, fetchFn } = fakeGithub({ label: false });
  assert.equal(await syncIssue(BROKEN, { fetchFn, repo: 'o/r', token: 'tok' }), 'opened #9');
  assert.ok(calls.includes('POST /labels'));
  assert.ok(calls.includes('POST /issues'));
});

test('syncIssue updates the existing open issue', async () => {
  const { calls, fetchFn } = fakeGithub({ issue: { number: 4 } });
  assert.equal(await syncIssue(BROKEN, { fetchFn, repo: 'o/r', token: 'tok' }), 'updated #4');
  assert.ok(calls.includes('PATCH /issues/4'));
  assert.ok(!calls.includes('POST /labels'));
});

test('syncIssue comments and closes the open issue on a clean run', async () => {
  const { calls, fetchFn } = fakeGithub({ issue: { number: 4 } });
  assert.equal(await syncIssue([], { fetchFn, repo: 'o/r', token: 'tok' }), 'closed #4');
  assert.ok(calls.includes('POST /issues/4/comments'));
  assert.ok(calls.includes('PATCH /issues/4'));
});

test('syncIssue does nothing on a clean run with no open issue', async () => {
  const { fetchFn } = fakeGithub();
  assert.equal(
    await syncIssue([], { fetchFn, repo: 'o/r', token: 'tok' }),
    'clean, nothing to close',
  );
});

test('syncIssue surfaces API failures', async () => {
  const fetchFn = async () => res(500);
  await assert.rejects(syncIssue(BROKEN, { fetchFn, repo: 'o/r', token: 'tok' }), /HTTP 500/);
});

test('syncIssue handles a 204 response', async () => {
  const fetchFn = async (url, init) =>
    url.includes('/labels/') ? res(200, {}) : init.method === 'GET' ? res(200, [{ number: 1 }]) : res(204);
  assert.equal(await syncIssue([], { fetchFn, repo: 'o/r', token: 'tok' }), 'closed #1');
});

test('main --dry-run checks the real registry and touches no issue API', async () => {
  const seen = [];
  const fetchFn = async (url) => (seen.push(url), res(200));
  const out = [];
  const code = await main({ argv: ['--dry-run'], env: {}, fetchFn, sleep: noSleep(), log: (s) => out.push(s) });
  assert.equal(code, 0);
  assert.ok(seen.every((u) => !u.includes('api.github.com')));
  assert.match(out[0], /^\d+\/\d+ URLs ok, 0 broken$/);
});

test('main without --dry-run syncs the issue then prints the summary', async () => {
  const { fetchFn } = fakeGithub();
  const wrapped = async (url, init) =>
    url.startsWith('https://api.github.com') ? fetchFn(url, init) : res(200);
  const out = [];
  await main({
    argv: [],
    env: { GITHUB_REPOSITORY: 'o/r', GITHUB_TOKEN: 'tok' },
    fetchFn: wrapped,
    sleep: noSleep(),
    log: (s) => out.push(s),
  });
  assert.equal(out[0], 'clean, nothing to close');
});
