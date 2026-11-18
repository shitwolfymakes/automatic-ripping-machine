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
  runCli,
  isEntry,
  sleepReal,
  USER_AGENT,
  ISSUE_TITLE,
  BOT_LOGIN,
} from './check-field-docs-links.mjs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

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

test('checkUrl: keeps the HEAD status when GET then throws', async () => {
  const fetchFn = async (_u, { method }) => {
    if (method === 'HEAD') return res(405);
    throw new Error('reset');
  };
  const out = await checkUrl('https://x.test', { fetchFn, sleep: noSleep() });
  assert.equal(out.reason, 'HTTP 405 on HEAD, GET failed: reset');
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

/**
 * Fake GitHub API. Records every call as {method, route, body}; `issues` seeds
 * the open-issue list, `label` the label lookup, `labelPost` the POST /labels status.
 */
function fakeGithub({ label = true, issues = [], labelPost = 201 } = {}) {
  const calls = [];
  const fetchFn = async (url, init) => {
    const route = url.replace('https://api.github.com/repos/o/r', '');
    calls.push({ method: init.method, route, body: init.body ? JSON.parse(init.body) : undefined });
    assert.equal(init.headers.authorization, 'Bearer tok');
    if (route.startsWith('/labels/')) return label ? res(200, {}) : res(404);
    if (route === '/labels') return res(labelPost, {});
    if (init.method === 'GET') return res(200, issues);
    if (route === '/issues') return res(201, { number: 9 });
    return res(init.method === 'PATCH' ? 200 : 201, {});
  };
  return { calls, fetchFn };
}
const opts = (fetchFn) => ({ fetchFn, repo: 'o/r', token: 'tok' });
// An issue this workflow opened: its title, by the Actions bot.
const own = (number, extra = {}) => ({ number, title: ISSUE_TITLE, user: { login: BOT_LOGIN }, ...extra });
const LIST = '/issues?labels=docs-links&state=open&per_page=100';

test('syncIssue opens an issue, creating the missing label', async () => {
  const { calls, fetchFn } = fakeGithub({ label: false });
  assert.equal(await syncIssue(BROKEN, opts(fetchFn)), 'opened #9');
  assert.deepEqual(calls, [
    { method: 'GET', route: '/labels/docs-links', body: undefined },
    {
      method: 'POST',
      route: '/labels',
      body: { name: 'docs-links', color: 'd93f0b', description: 'Broken field docs links' },
    },
    { method: 'GET', route: LIST, body: undefined },
    {
      method: 'POST',
      route: '/issues',
      body: { title: 'Broken field docs links', body: renderIssueBody(BROKEN), labels: ['docs-links'] },
    },
  ]);
});

test('syncIssue treats a 422 from the label POST as already created', async () => {
  const { fetchFn } = fakeGithub({ label: false, labelPost: 422 });
  assert.equal(await syncIssue(BROKEN, opts(fetchFn)), 'opened #9');
});

test('syncIssue fails on other label POST errors', async () => {
  const { fetchFn } = fakeGithub({ label: false, labelPost: 403 });
  await assert.rejects(syncIssue(BROKEN, opts(fetchFn)), /POST \/labels failed: HTTP 403/);
});

test('syncIssue updates the first real open issue and skips pull requests', async () => {
  const { calls, fetchFn } = fakeGithub({
    issues: [own(3, { pull_request: {} }), own(4), own(5)],
  });
  assert.equal(await syncIssue(BROKEN, opts(fetchFn)), 'updated #4');
  assert.deepEqual(calls.slice(1), [
    { method: 'GET', route: LIST, body: undefined },
    { method: 'PATCH', route: '/issues/4', body: { body: renderIssueBody(BROKEN) } },
  ]);
});

test('syncIssue comments on and closes every open issue on a clean run', async () => {
  const { calls, fetchFn } = fakeGithub({
    issues: [own(4), own(3, { pull_request: {} }), own(6)],
  });
  assert.equal(await syncIssue([], opts(fetchFn)), 'closed #4, #6');
  const comment = { body: 'All field docs links resolve again; closing.' };
  assert.deepEqual(calls.slice(2), [
    { method: 'POST', route: '/issues/4/comments', body: comment },
    { method: 'PATCH', route: '/issues/4', body: { state: 'closed' } },
    { method: 'POST', route: '/issues/6/comments', body: comment },
    { method: 'PATCH', route: '/issues/6', body: { state: 'closed' } },
  ]);
});

// A person's report with the label, or another bot issue with the label, is not this workflow's.
const FOREIGN = [
  { number: 7, title: ISSUE_TITLE, user: { login: 'someone' } },
  { number: 8, title: 'The help link on Ripping is broken', user: { login: BOT_LOGIN } },
];

test('syncIssue leaves labelled issues it did not open alone on a clean run', async () => {
  const { calls, fetchFn } = fakeGithub({ issues: FOREIGN });
  assert.equal(await syncIssue([], opts(fetchFn)), 'clean, nothing to close');
  assert.equal(calls.length, 2);
});

test('syncIssue opens its own issue instead of overwriting one it did not open', async () => {
  const { calls, fetchFn } = fakeGithub({ issues: FOREIGN });
  assert.equal(await syncIssue(BROKEN, opts(fetchFn)), 'opened #9');
  assert.equal(calls.filter((c) => c.method === 'PATCH').length, 0);
});

test('syncIssue does nothing on a clean run with no open issue', async () => {
  const { calls, fetchFn } = fakeGithub();
  assert.equal(await syncIssue([], opts(fetchFn)), 'clean, nothing to close');
  assert.equal(calls.length, 2);
});

test('syncIssue surfaces API failures, including a 404 outside the label lookup', async () => {
  await assert.rejects(syncIssue(BROKEN, opts(async () => res(500))), /HTTP 500/);
  const fetchFn = async (url) => (url.includes('/labels/') ? res(200, {}) : res(404));
  await assert.rejects(syncIssue(BROKEN, opts(fetchFn)), /GET .*issues.* failed: HTTP 404/);
});

test('syncIssue handles a 204 response', async () => {
  const fetchFn = async (url, init) =>
    url.includes('/labels/') ? res(200, {}) : init.method === 'GET' ? res(200, [own(1)]) : res(204);
  assert.equal(await syncIssue([], opts(fetchFn)), 'closed #1');
});

test('response bodies are cancelled when not read', async () => {
  let cancelled = 0;
  const withBody = (status) => ({ ...res(status), body: { cancel: async () => void cancelled++ } });
  await checkUrl('https://x.test', { fetchFn: async () => withBody(200), sleep: noSleep() });
  assert.equal(cancelled, 1);
  await assert.rejects(syncIssue(BROKEN, opts(async () => withBody(500))));
  assert.equal(cancelled, 2);
  const labelMissing = async (url) =>
    url.includes('/labels/') ? withBody(404) : url.endsWith('/labels') ? withBody(422) : { ...res(200, []) };
  await syncIssue([], opts(labelMissing));
  assert.equal(cancelled, 4);
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

test('main without --dry-run fails fast when the token or repository is unset', async () => {
  let calls = 0;
  const fetchFn = async () => {
    calls += 1;
    return res(200);
  };
  await assert.rejects(
    main({ argv: [], env: { GITHUB_REPOSITORY: 'o/r' }, fetchFn, sleep: noSleep(), log() {} }),
    /GITHUB_TOKEN must be set/,
  );
  await assert.rejects(
    main({ argv: [], env: {}, fetchFn, sleep: noSleep(), log() {} }),
    /GITHUB_TOKEN and GITHUB_REPOSITORY must be set/,
  );
  assert.equal(calls, 0, 'no link is probed before the environment is checked');
});

test('sleepReal waits for the given time', async () => {
  const start = Date.now();
  await sleepReal(20);
  assert.ok(Date.now() - start >= 15);
});

test('runCli exits with what main returns', async () => {
  const codes = [];
  await runCli({
    argv: ['--dry-run'],
    env: {},
    fetchFn: async () => res(200),
    sleep: noSleep(),
    log() {},
    exit: (code) => codes.push(code),
  });
  assert.deepEqual(codes, [0]);
});

test('isEntry is true only for the script run directly', () => {
  const self = new URL('./check-field-docs-links.mjs', import.meta.url).href;
  assert.equal(isEntry(fileURLToPath(self), self), true);
  assert.equal(isEntry('/elsewhere/other.mjs', self), false);
  assert.equal(isEntry(undefined, self), false);
});

test('run directly without a token, the script fails before any request', () => {
  const env = { ...process.env };
  delete env.GITHUB_TOKEN;
  delete env.GITHUB_REPOSITORY;
  const script = fileURLToPath(new URL('./check-field-docs-links.mjs', import.meta.url));
  const run = spawnSync(process.execPath, [script], { env, encoding: 'utf8' });
  assert.notEqual(run.status, 0);
  assert.match(run.stderr, /GITHUB_TOKEN and GITHUB_REPOSITORY must be set/);
});
