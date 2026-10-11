import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, existsSync, readdirSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fixtureTree, MANIFEST } from './helpers.mjs';

const siteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const FIXTURE_MANIFEST = join(siteDir, 'test/fixture-manifest.json');
function writeManifest(manifest) {
	const file = join(mkdtempSync(join(tmpdir(), 'arm-docs-manifest-')), 'manifest.json');
	writeFileSync(file, JSON.stringify(manifest));
	return file;
}
const run = (args, env = {}) => spawnSync(process.execPath, ['src/build.mjs', ...args], { cwd: siteDir, encoding: 'utf8', env: { ...process.env, ...env } });

test('app build against the real ARM tree: user docs only, every nav page exists', () => {
	const out = mkdtempSync(join(tmpdir(), 'arm-docs-out-'));
	const res = run(['--target', 'app', '--out', out], { ARM_COMMIT: 'abc123' });
	assert.equal(res.status, 0, res.stdout + res.stderr);
	const app = join(out, 'app');
	const nav = JSON.parse(readFileSync(join(app, 'nav.json'), 'utf8'));
	for (const item of nav.flatMap((s) => s.groups.flatMap((g) => g.items))) {
		if (item.pageId) assert.ok(existsSync(join(app, 'pages', `${item.pageId}.json`)), item.pageId);
	}
	const home = JSON.parse(readFileSync(join(app, 'pages/guide/home.json'), 'utf8'));
	assert.equal(home.id, 'guide/home');
	assert.equal(home.source, 'docs/user/Home.md');
	assert.doesNotMatch(home.html, /@@doc(link|asset)/);
	const meta = JSON.parse(readFileSync(join(app, 'meta.json'), 'utf8'));
	assert.equal(meta.commit, 'abc123');
	const search = JSON.parse(readFileSync(join(app, 'search.json'), 'utf8'));
	assert.deepEqual(search.options.fields, ['title', 'headings', 'text']);
	assert.ok(readdirSync(join(app, 'pages/guide')).length > 10);
	assert.equal(existsSync(join(app, 'pages/dev')), false, 'developer docs must not ship in the app');
	assert.deepEqual(nav.map((s) => s.label), ['Get started', 'Using ARM', 'Troubleshooting', 'Project']);
	assert.doesNotMatch(JSON.stringify(search.index), /"dev\//, 'developer docs must not be in the app search index');
});

test('broken links fail the build with every error reported', () => {
	const manifest = structuredClone(MANIFEST);
	manifest.sections[1].groups[0].files.push('docs/user/Bad.md');
	const armRoot = fixtureTree({ 'docs/user/Bad.md': '# Bad\n\n[a](Nope)\n\n[b](Getting-Started#nowhere)\n' });
	const res = run(['--target', 'app', '--out', mkdtempSync(join(tmpdir(), 'arm-docs-out-'))], { ARM_ROOT: armRoot, DOCS_MANIFEST: writeManifest(manifest) });
	assert.equal(res.status, 1);
	assert.match(res.stderr, /docs\/user\/Bad\.md:3: link target not found: docs\/user\/Nope/);
	assert.match(res.stderr, /docs\/user\/Bad\.md:5: missing anchor #nowhere in guide\/getting-started/);
});

test('a nav link with an unsupported scheme fails the build', () => {
	const manifest = structuredClone(MANIFEST);
	manifest.sections[1].groups[0].files.push({ label: 'x', link: 'javascript:alert(1)' });
	const res = run(['--target', 'app', '--out', mkdtempSync(join(tmpdir(), 'arm-docs-out-'))], { ARM_ROOT: fixtureTree(), DOCS_MANIFEST: writeManifest(manifest) });
	assert.equal(res.status, 1);
	assert.match(res.stderr, /manifest\.json \(Using ARM\): unsupported link scheme: javascript:alert\(1\)/);
});

test('app bundle links developer docs to the public site; the site keeps them local', () => {
	const armRoot = fixtureTree({ 'docs/user/Getting-Started.md': '# Getting Started\n\n## Install\n\nSee [the architecture](../developers/architecture/README.md).\n' });
	// The site writer compiles ui-neu's real styles and copies its fonts and favicon.
	for (const dir of ['services/ui-neu/frontend/src/lib/styles', 'services/ui-neu/frontend/static']) {
		mkdirSync(dirname(join(armRoot, dir)), { recursive: true });
		symlinkSync(join(siteDir, '..', dir), join(armRoot, dir));
	}
	const out = mkdtempSync(join(tmpdir(), 'arm-docs-out-'));
	const res = run(['--out', out], { ARM_ROOT: armRoot, DOCS_MANIFEST: FIXTURE_MANIFEST });
	assert.equal(res.status, 0, res.stdout + res.stderr);
	const page = JSON.parse(readFileSync(join(out, 'app/pages/guide/getting-started.json'), 'utf8'));
	assert.match(page.html, /<a href="https:\/\/example\.test\/arm-v3\/dev\/architecture\.html" target="_blank" rel="noopener">the architecture<\/a>/);
	const nav = JSON.parse(readFileSync(join(out, 'app/nav.json'), 'utf8'));
	assert.deepEqual(nav.map((s) => s.id), ['start', 'using']);
	const sitePage = readFileSync(join(out, 'site/guide/getting-started.html'), 'utf8');
	assert.match(sitePage, /<a href="\.\.\/dev\/architecture\.html">the architecture<\/a>/);
	assert.match(sitePage, /Developers/);
});

test('a missing ARM root is a clear error', () => {
	const res = run(['--target', 'app'], { ARM_ROOT: '/nonexistent/arm' });
	assert.equal(res.status, 1);
	assert.match(res.stderr, /ARM root not found at \/nonexistent\/arm \(set ARM_ROOT\)/);
});

test('site build against the real ARM tree: relative URLs only, css compiled from ui-neu tokens', () => {
	const out = mkdtempSync(join(tmpdir(), 'arm-docs-out-'));
	const res = run(['--target', 'site', '--out', out]);
	assert.equal(res.status, 0, res.stdout + res.stderr);
	const site = join(out, 'site');
	const htmlFiles = ['index.html', ...readdirSync(join(site, 'guide')).map((f) => `guide/${f}`), ...readdirSync(join(site, 'dev')).map((f) => `dev/${f}`)];
	assert.ok(htmlFiles.length > 20);
	for (const f of htmlFiles) {
		const html = readFileSync(join(site, f), 'utf8');
		assert.match(html, /<title>[^<]+<\/title>/, f);
		assert.doesNotMatch(html, /(href|src)="\//, `${f} has a root-absolute URL`);
		assert.doesNotMatch(html, /@@doc(link|asset)|\{\{\w+\}\}/, f);
	}
	const index = readFileSync(join(site, 'index.html'), 'utf8');
	assert.match(index, /href="site\.css"/);
	assert.match(index, /class="nav-item" href="index\.html" data-active="true"/);
	assert.ok(existsSync(join(site, 'dev/architecture.html')), 'the site carries developer docs');
	const page = readFileSync(join(site, 'guide/getting-started.html'), 'utf8');
	assert.match(page, /href="\.\.\/site\.css"/);
	const css = readFileSync(join(site, 'site.css'), 'utf8');
	assert.match(css, /--color-page/);
	assert.match(css, /\.docs-prose/);
	assert.doesNotMatch(css, /url\(["']?\//, 'root-absolute url() in css');
	assert.ok(existsSync(join(site, 'fonts/rajdhani-700-latin.woff2')));
	assert.match(readFileSync(join(site, 'js/search-index.js'), 'utf8'), /^window\.ARM_DOCS_SEARCH = \{/);
	assert.match(readFileSync(join(site, 'js/minisearch.js'), 'utf8'), /MiniSearch/);
});
