import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cssEntry, pageHtml, relativeFontUrls, searchIndexScript } from '../src/write-site.mjs';

const ALL = ['root', 'title', 'repo', 'nav', 'toc', 'content', 'editUrl', 'version', 'commit'];
const TEMPLATE = ALL.map((k) => `{{${k}}}`).join('|');
const MANIFEST_ = { repo: 'o/r' };
const META = { version: '1.0', commit: 'abc' };

const page = (id, extra = {}) => ({
	page: { id, title: 'T', srcPath: `docs/${id}.md` },
	html: '<p>body</p>',
	toc: [],
	links: [],
	assets: [],
	...extra
});
const navOf = (groups) => [{ id: 's', label: 'Sec', groups }];
const pageItem = (label, id) => ({ label, resolved: { kind: 'page', id, fragment: '' } });
const build = (r, nav = [], template = TEMPLATE, manifest = MANIFEST_, meta = META) =>
	pageHtml(template, r, { nav, manifest, meta });

test('fills every placeholder', () => {
	const r = page('guide/home', { toc: [{ depth: 2, id: 'a', text: 'A' }, { depth: 2, id: 'b', text: 'B' }] });
	const nav = navOf([{ label: 'G', items: [pageItem('Home', 'guide/home')] }]);
	assert.equal(
		build(r, nav),
		[
			'',
			'T',
			'o/r',
			'<div class="docs-nav-section"><p class="eyebrow docs-nav-heading">Sec</p><p class="docs-nav-group">G</p>' +
				'<a class="nav-item" href="index.html" data-active="true" aria-current="page">Home</a></div>',
			'<nav class="docs-toc" aria-label="On this page"><p class="eyebrow">On this page</p>' +
				'<a class="docs-toc-link" data-depth="2" href="#a">A</a>' +
				'<a class="docs-toc-link" data-depth="2" href="#b">B</a></nav>',
			'<p>body</p>',
			'https://github.com/o/r/edit/main/docs/guide/home.md',
			'1.0',
			'abc'
		].join('|')
	);
});

test('title, repo, version and commit are HTML-escaped', () => {
	const r = page('x', { page: { id: 'x', title: '<&>', srcPath: 'x.md' } });
	const meta = { version: '<v>', commit: '"c"' };
	const out = build(r, [], '{{title}}|{{repo}}|{{version}}|{{commit}}', { repo: 'a&b' }, meta);
	assert.equal(out, '&lt;&amp;&gt;|a&amp;b|&lt;v&gt;|&quot;c&quot;');
});

test('root prefix follows the page id depth', () => {
	assert.equal(build(page('guide/home'), [], '{{root}}'), '');
	assert.equal(build(page('guide/intro'), [], '{{root}}'), '../');
	assert.equal(build(page('a/b/c'), [], '{{root}}'), '../../');
});

test('only the active page gets the active attributes', () => {
	const nav = navOf([{ label: 'G', items: [pageItem('One', 'one'), pageItem('Two', 'two')] }]);
	const out = build(page('two'), nav, '{{nav}}');
	assert.match(out, /href="one.html">One</);
	assert.match(out, /href="two.html" data-active="true" aria-current="page">Two</);
	assert.equal(out.split('data-active').length, 2);
});

test('external nav items open in a new tab', () => {
	const ext = { label: 'Ext', resolved: { kind: 'external', url: 'https://e.com/' } };
	const out = build(page('one'), navOf([{ label: 'G', items: [ext, pageItem('One', 'one')] }]), '{{nav}}');
	assert.match(out, /href="https:\/\/e.com\/" target="_blank" rel="noopener">Ext</);
	assert.equal(out.split('noopener').length, 2);
});

test('a group label renders a heading, an unlabelled group does not', () => {
	const nav = navOf([{ label: 'G', items: [pageItem('One', 'one')] }, { items: [pageItem('Two', 'two')] }]);
	const out = build(page('one'), nav, '{{nav}}');
	assert.equal(out.split('<p class="docs-nav-group">').length, 2);
	assert.match(out, /<p class="docs-nav-group">G<\/p>/);
});

test('the toc renders only with two or more entries', () => {
	const one = [{ depth: 2, id: 'a', text: 'A' }];
	assert.equal(build(page('x', { toc: one }), [], '{{toc}}'), '');
	assert.match(build(page('x', { toc: [...one, { depth: 3, id: 'b', text: 'B' }] }), [], '{{toc}}'), /docs-toc-link/);
});

test('an unknown placeholder throws', () => {
	assert.throws(() => build(page('x'), [], '{{nope}}'), { message: 'template: unknown placeholder {{nope}}' });
});

const STYLES = '/arm/services/ui-neu/frontend/src/lib/styles';

test('cssEntry imports tailwind, the base sheets, every block, then the site sheet', () => {
	const up = '../../services/ui-neu/frontend/src/lib/styles';
	const blocks = ['panel', 'button', 'alert', 'badge', 'code-block', 'table', 'nav', 'field', 'text', 'docs-prose'];
	assert.deepEqual(cssEntry(STYLES, '/arm/site', '/arm/site/.cache').split('\n'), [
		'@import "tailwindcss" source(none);',
		...['tokens', 'base', 'layout', 'utilities'].map((n) => `@import "${up}/${n}.css";`),
		...blocks.map((b) => `@import "${up}/components/${b}.css";`),
		'@import "../src/styles/site.css";'
	]);
});

test('cssEntry paths are relative to cacheDir', () => {
	const lines = cssEntry(STYLES, '/arm/site', '/arm/site/.cache/deep').split('\n');
	assert.equal(lines[1], '@import "../../../services/ui-neu/frontend/src/lib/styles/tokens.css";');
	assert.equal(lines.at(-1), '@import "../../src/styles/site.css";');
});

test('cssEntry has no trailing newline', () => {
	assert.equal(cssEntry(STYLES, '/arm/site', '/arm/site/.cache').endsWith('\n'), false);
});

test('relativeFontUrls rewrites unquoted and quoted font urls, keeping the quote', () => {
	assert.equal(relativeFontUrls('src:url(/fonts/a.woff2)'), 'src:url(fonts/a.woff2)');
	assert.equal(relativeFontUrls("src:url('/fonts/a.woff2')"), "src:url('fonts/a.woff2')");
	assert.equal(relativeFontUrls('src:url("/fonts/a.woff2")'), 'src:url("fonts/a.woff2")');
});

test('relativeFontUrls rewrites every occurrence in a minified sheet', () => {
	const css =
		'@font-face{src:url(/fonts/a.woff2)}@font-face{src:url("/fonts/b.woff2")}@font-face{src:url(/fonts/c.woff2)}';
	assert.equal(
		relativeFontUrls(css),
		'@font-face{src:url(fonts/a.woff2)}@font-face{src:url("fonts/b.woff2")}@font-face{src:url(fonts/c.woff2)}'
	);
});

test('relativeFontUrls leaves other urls as they are', () => {
	for (const css of ['a{background:url(/img/x.png)}', 'a{src:url(fonts/x.woff2)}', 'a{src:url(/fontsx/a.woff2)}']) {
		assert.equal(relativeFontUrls(css), css);
	}
});

test('relativeFontUrls leaves a sheet without urls unchanged', () => {
	assert.equal(relativeFontUrls('a{color:red}'), 'a{color:red}');
});

const PREFIX = 'window.ARM_DOCS_SEARCH = ';
const entry = (id, title) => ({ page: { id, title } });
const parseScript = (script) => JSON.parse(script.slice(PREFIX.length, -2));

test('searchIndexScript assigns the index and page paths to window.ARM_DOCS_SEARCH', () => {
	const script = searchIndexScript({ docs: [1] }, [entry('guide/home', 'Home'), entry('guide/setup', 'Setup')]);
	assert.equal(
		script,
		`${PREFIX}{"docs":[1],"pages":{"guide/home":{"title":"Home","path":"index.html"},` +
			'"guide/setup":{"title":"Setup","path":"guide/setup.html"}}};\n'
	);
	assert.ok(script.startsWith(PREFIX));
	assert.ok(script.endsWith(';\n'));
});

test('searchIndexScript JSON parses back to the search object plus pages in input order', () => {
	const search = { docs: ['a'], n: 2 };
	const parsed = parseScript(searchIndexScript(search, [entry('b/z', 'Z'), entry('a/y', 'Y')]));
	assert.deepEqual(parsed, {
		...search,
		pages: { 'b/z': { title: 'Z', path: 'b/z.html' }, 'a/y': { title: 'Y', path: 'a/y.html' } }
	});
	assert.deepEqual(Object.keys(parsed.pages), ['b/z', 'a/y']);
});

test('searchIndexScript replaces a pages key already in the search object', () => {
	const parsed = parseScript(searchIndexScript({ pages: { old: 1 } }, [entry('a/y', 'Y')]));
	assert.deepEqual(parsed.pages, { 'a/y': { title: 'Y', path: 'a/y.html' } });
});

test('searchIndexScript gives empty pages for no rendered pages', () => {
	assert.deepEqual(parseScript(searchIndexScript({ docs: [] }, [])), { docs: [], pages: {} });
});
