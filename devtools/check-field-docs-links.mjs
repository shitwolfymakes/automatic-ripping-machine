#!/usr/bin/env node
// Weekly check that every external docs link in the field docs registry
// still resolves. Reads packages/arm_common/arm_common/field_docs.json,
// requests each distinct external URL, and reports broken ones as a single
// GitHub issue labelled `docs-links` (opened or updated while links are
// broken, commented on and closed once a run is clean).
//
// Usage: node devtools/check-field-docs-links.mjs [--dry-run]
//   --dry-run  print the report and touch no issues (no token needed)
// Issue I/O uses the GitHub REST API with GITHUB_TOKEN and GITHUB_REPOSITORY.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const USER_AGENT = 'link-checker/1.0 (+docs link validation)';
export const TIMEOUT_MS = 15000;
export const RETRIES = 2;
export const BACKOFF_MS = 1000;
export const LABEL = 'docs-links';
export const ISSUE_TITLE = 'Broken field docs links';
const API = 'https://api.github.com';
const REGISTRY = fileURLToPath(
  new URL('../packages/arm_common/arm_common/field_docs.json', import.meta.url),
);

/** Map each distinct external URL to the sorted field ids that use it. */
export function collectUrls(registry) {
  const byUrl = new Map();
  for (const [id, entry] of Object.entries(registry.fields ?? {})) {
    if (entry?.type !== 'external') continue;
    if (!byUrl.has(entry.url)) byUrl.set(entry.url, []);
    byUrl.get(entry.url).push(id);
  }
  for (const ids of byUrl.values()) ids.sort();
  return byUrl;
}

/** ok | retry | fail for an HTTP status. 429 is rate limiting, not a broken link. */
export function classifyStatus(status) {
  if (status < 400 || status === 429) return 'ok';
  if (status >= 500) return 'retry';
  return 'fail';
}

const sleepReal = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function requestOnce(fetchFn, url, method) {
  const res = await fetchFn(url, {
    method,
    redirect: 'follow',
    headers: { 'user-agent': USER_AGENT },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  await res.body?.cancel();
  return res.status;
}

/** HEAD first; GET when HEAD is refused or errors (some hosts reject HEAD). */
async function probe(fetchFn, url) {
  let headStatus;
  try {
    headStatus = await requestOnce(fetchFn, url, 'HEAD');
    if (classifyStatus(headStatus) === 'ok') return { verdict: 'ok', status: headStatus };
  } catch {
    // fall through to GET
  }
  try {
    const status = await requestOnce(fetchFn, url, 'GET');
    return { verdict: classifyStatus(status), status };
  } catch (err) {
    return { verdict: 'retry', status: headStatus, error: err?.message ?? String(err) };
  }
}

function describeFailure({ status, error }) {
  if (status && error) return `HTTP ${status} on HEAD, GET failed: ${error}`;
  return status ? `HTTP ${status}` : error;
}

/** Check one URL with up to RETRIES retries (exponential backoff) on 5xx/network errors. */
export async function checkUrl(url, { fetchFn = fetch, sleep = sleepReal } = {}) {
  let result;
  for (let attempt = 0; attempt <= RETRIES; attempt++) {
    result = await probe(fetchFn, url);
    if (result.verdict !== 'retry') break;
    if (attempt < RETRIES) await sleep(BACKOFF_MS * 2 ** attempt);
  }
  if (result.verdict === 'ok') return { url, ok: true };
  return { url, ok: false, reason: describeFailure(result) };
}

/** Check every URL in the map; returns the failures with their field ids. */
export async function findBroken(urlMap, deps) {
  const broken = [];
  for (const [url, fields] of urlMap) {
    const result = await checkUrl(url, deps);
    if (!result.ok) broken.push({ url, fields, reason: result.reason });
  }
  return broken;
}

/** Markdown issue body, one section per broken URL. */
export function renderIssueBody(broken) {
  const lines = [
    `${broken.length} external docs link(s) in \`field_docs.json\` did not resolve.`,
    '',
  ];
  for (const { url, fields, reason } of broken) {
    lines.push(`- ${url} (${reason})`);
    for (const id of fields) lines.push(`  - \`${id}\``);
  }
  lines.push('', 'Update or replace the entry in `packages/arm_common/arm_common/field_docs.json`.');
  return lines.join('\n');
}

export function renderDryRun(total, broken) {
  const head = `${total - broken.length}/${total} URLs ok, ${broken.length} broken`;
  return broken.length ? `${head}\n\n${renderIssueBody(broken)}` : head;
}

function ghClient(fetchFn, repo, token) {
  // `tolerate` lists statuses that mean "not an error" and yield null.
  return async (method, route, body, tolerate = []) => {
    const res = await fetchFn(`${API}/repos/${repo}${route}`, {
      method,
      headers: {
        authorization: `Bearer ${token}`,
        accept: 'application/vnd.github+json',
        'content-type': 'application/json',
        'user-agent': USER_AGENT,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (tolerate.includes(res.status)) {
      await res.body?.cancel();
      return null;
    }
    if (!res.ok) {
      await res.body?.cancel();
      throw new Error(`GitHub API ${method} ${route} failed: HTTP ${res.status}`);
    }
    if (res.status === 204) return null;
    return res.json();
  };
}

async function ensureLabel(call) {
  if ((await call('GET', `/labels/${LABEL}`, undefined, [404])) !== null) return;
  // 422 means a concurrent run created it first.
  await call(
    'POST',
    '/labels',
    { name: LABEL, color: 'd93f0b', description: 'Broken field docs links' },
    [422],
  );
}

async function closeIssue(call, number) {
  await call('POST', `/issues/${number}/comments`, {
    body: 'All field docs links resolve again; closing.',
  });
  await call('PATCH', `/issues/${number}`, { state: 'closed' });
}

/** Open or update the one open `docs-links` issue, or comment and close every one when clean. */
export async function syncIssue(broken, { fetchFn = fetch, repo, token }) {
  const call = ghClient(fetchFn, repo, token);
  await ensureLabel(call);
  const listed = await call('GET', `/issues?labels=${LABEL}&state=open&per_page=100`);
  const issues = listed.filter((item) => !item.pull_request);
  if (broken.length === 0) {
    for (const { number } of issues) await closeIssue(call, number);
    return issues.length
      ? `closed ${issues.map((i) => `#${i.number}`).join(', ')}`
      : 'clean, nothing to close';
  }
  const body = renderIssueBody(broken);
  if (issues.length) {
    await call('PATCH', `/issues/${issues[0].number}`, { body });
    return `updated #${issues[0].number}`;
  }
  const created = await call('POST', '/issues', { title: ISSUE_TITLE, body, labels: [LABEL] });
  return `opened #${created.number}`;
}

export async function main({ argv, env, fetchFn = fetch, sleep = sleepReal, log = console.log }) {
  const registry = JSON.parse(readFileSync(REGISTRY, 'utf8'));
  const urls = collectUrls(registry);
  const dryRun = argv.includes('--dry-run');
  // Checked before any probe, so a misconfigured run fails at once.
  const missing = dryRun ? [] : ['GITHUB_TOKEN', 'GITHUB_REPOSITORY'].filter((name) => !env[name]);
  if (missing.length) throw new Error(`${missing.join(' and ')} must be set (or use --dry-run)`);
  const broken = await findBroken(urls, { fetchFn, sleep });
  if (dryRun) {
    log(renderDryRun(urls.size, broken));
    return 0;
  }
  log(await syncIssue(broken, { fetchFn, repo: env.GITHUB_REPOSITORY, token: env.GITHUB_TOKEN }));
  log(renderDryRun(urls.size, broken));
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(await main({ argv: process.argv.slice(2), env: process.env }));
}
