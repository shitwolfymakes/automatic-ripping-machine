import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fixtureTree } from './helpers.mjs';

const siteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const run = (args, env = {}) => spawnSync(process.execPath, ['src/build.mjs', ...args], { cwd: siteDir, encoding: 'utf8', env: { ...process.env, ...env } });

test('app build against the real ARM tree: no errors, every nav page exists', () => {
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
	assert.equal(home.source, 'arm_wiki/Home.md');
	assert.doesNotMatch(home.html, /@@doc(link|asset)/);
	const meta = JSON.parse(readFileSync(join(app, 'meta.json'), 'utf8'));
	assert.equal(meta.commit, 'abc123');
	const search = JSON.parse(readFileSync(join(app, 'search.json'), 'utf8'));
	assert.deepEqual(search.options.fields, ['title', 'headings', 'text']);
	assert.ok(readdirSync(join(app, 'pages/dev')).length > 5);
});

test('broken links fail the build with every error reported', () => {
	const armRoot = fixtureTree({ 'arm_wiki/Bad.md': '# Bad\n\n[a](Nope)\n\n[b](Getting-Started#nowhere)\n' });
	const res = run(['--target', 'app', '--out', mkdtempSync(join(tmpdir(), 'arm-docs-out-'))], { ARM_ROOT: armRoot, DOCS_MANIFEST: join(siteDir, 'test/fixture-manifest.json') });
	assert.equal(res.status, 1);
	assert.match(res.stderr, /arm_wiki\/Bad\.md:3: link target not found: arm_wiki\/Nope/);
	assert.match(res.stderr, /arm_wiki\/Bad\.md:5: missing anchor #nowhere in guide\/getting-started/);
});

test('a nav link with an unsupported scheme fails the build', () => {
	const armRoot = fixtureTree({
		'arm_wiki/_Sidebar.md': [
			'**[Home](https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki)**',
			'',
			'**Getting Started**',
			'  - [x](javascript:alert(1))',
			''
		].join('\n')
	});
	const res = run(['--target', 'app', '--out', mkdtempSync(join(tmpdir(), 'arm-docs-out-'))], { ARM_ROOT: armRoot, DOCS_MANIFEST: join(siteDir, 'test/fixture-manifest.json') });
	assert.equal(res.status, 1);
	assert.match(res.stderr, /arm_wiki\/_Sidebar\.md:4: unsupported link scheme: javascript:alert\(1/);
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
