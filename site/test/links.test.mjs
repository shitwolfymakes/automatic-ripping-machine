import { test } from 'node:test';
import assert from 'node:assert/strict';
import { collectPages } from '../src/collect.mjs';
import { createResolver, hrefFor, assetHref, outPath, appRoute, rootPrefix, checkFragments, fillLinks } from '../src/links.mjs';
import { fixtureTree, MANIFEST } from './helpers.mjs';

const UP = 'https://github.com/automatic-ripping-machine/automatic-ripping-machine';

function setup(extra) {
	const armRoot = fixtureTree(extra);
	const { pages } = collectPages(armRoot, MANIFEST);
	return createResolver({ armRoot, pages, manifest: MANIFEST });
}

test('wiki bare targets resolve from wiki pages, with fragments', () => {
	const r = setup();
	assert.deepEqual(r.resolve('Getting-Started', 'arm_wiki/Home.md'), { kind: 'page', id: 'guide/getting-started', fragment: '' });
	assert.deepEqual(r.resolve('Configuring-ARM#options', 'arm_wiki/Getting-Started.md'), { kind: 'page', id: 'guide/configuring-arm', fragment: 'options' });
});

test('a bare target to a missing wiki page is an error', () => {
	assert.equal(setup().resolve('Nope', 'arm_wiki/Home.md').kind, 'error');
});

test('upstream wiki and blob URLs map into the site', () => {
	const r = setup();
	assert.deepEqual(r.resolve(`${UP}/wiki`, 'arm_wiki/_Sidebar.md'), { kind: 'page', id: 'guide/home', fragment: '' });
	assert.deepEqual(r.resolve(`${UP}/wiki/Getting-Started`, 'docs/arch/README.md'), { kind: 'page', id: 'guide/getting-started', fragment: '' });
	assert.deepEqual(r.resolve(`${UP}/blob/main/docs/arch/README.md`, 'arm_wiki/_Sidebar.md'), { kind: 'page', id: 'dev/arch', fragment: '' });
	assert.deepEqual(r.resolve(`${UP}/blob/main/LICENSE`, 'arm_wiki/Home.md'), { kind: 'repo', path: 'LICENSE', fragment: '' });
});

test('other GitHub URLs on the same repo stay external', () => {
	assert.deepEqual(setup().resolve(`${UP}/issues/new/choose`, 'arm_wiki/_Sidebar.md'), { kind: 'external', url: `${UP}/issues/new/choose` });
});

test('relative repo paths, directories resolve to README, unpublished files go to GitHub', () => {
	const r = setup();
	assert.deepEqual(r.resolve('01-architecture.md', 'docs/arch/README.md'), { kind: 'page', id: 'dev/01-architecture', fragment: '' });
	assert.deepEqual(r.resolve('docs/arch/', 'CONTRIBUTING.md'), { kind: 'page', id: 'dev/arch', fragment: '' });
	assert.deepEqual(r.resolve('LICENSE', 'CONTRIBUTING.md'), { kind: 'repo', path: 'LICENSE', fragment: '' });
});

test('missing files and repo escapes are errors', () => {
	const r = setup();
	assert.deepEqual(r.resolve('nope.md', 'docs/arch/README.md'), { kind: 'error', message: 'link target not found: docs/arch/nope.md' });
	assert.equal(r.resolve('../../x.md', 'docs/arch/README.md').kind, 'error');
});

test('URL-encoded targets decode; malformed encoding is an error, not a throw', () => {
	const r = setup({ 'docs/arch/My Page.md': '# Mine\n' });
	assert.deepEqual(r.resolve('My%20Page.md', 'docs/arch/README.md'), { kind: 'repo', path: 'docs/arch/My Page.md', fragment: '' });
	assert.deepEqual(r.resolve('bad%E0%A4%A.md', 'docs/arch/README.md'), { kind: 'error', message: 'malformed link: bad%E0%A4%A.md' });
});

test('anchors and externals', () => {
	const r = setup();
	assert.deepEqual(r.resolve('#install', 'arm_wiki/Getting-Started.md'), { kind: 'anchor', fragment: 'install' });
	assert.deepEqual(r.resolve('https://www.makemkv.com/', 'arm_wiki/Home.md'), { kind: 'external', url: 'https://www.makemkv.com/' });
	assert.deepEqual(r.resolve('mailto:a@b.c', 'arm_wiki/Home.md'), { kind: 'external', url: 'mailto:a@b.c' });
});

test('assets resolve relative to the source; missing is an error', () => {
	const r = setup({ 'docs/arch/img/topo.png': 'png' });
	assert.deepEqual(r.resolveAsset('img/topo.png', 'docs/arch/README.md'), { kind: 'asset', path: 'docs/arch/img/topo.png' });
	assert.equal(r.resolveAsset('img/none.png', 'docs/arch/README.md').kind, 'error');
	assert.deepEqual(r.resolveAsset('https://x/y.png', 'docs/arch/README.md'), { kind: 'external', url: 'https://x/y.png' });
});

test('paths and hrefs per target', () => {
	assert.equal(outPath('guide/home'), 'index.html');
	assert.equal(outPath('dev/arch'), 'dev/arch.html');
	assert.equal(appRoute('guide/home'), '/help');
	assert.equal(appRoute('dev/arch'), '/help/dev/arch');
	assert.equal(rootPrefix('guide/home'), '');
	assert.equal(rootPrefix('dev/arch'), '../');
	const page = { kind: 'page', id: 'dev/01-architecture', fragment: 'backend' };
	const site = { target: 'site', fromId: 'guide/getting-started', repo: 'o/r' };
	assert.equal(hrefFor(page, site), '../dev/01-architecture.html#backend');
	assert.equal(hrefFor(page, { ...site, fromId: 'guide/home' }), 'dev/01-architecture.html#backend');
	assert.equal(hrefFor({ kind: 'page', id: 'guide/home', fragment: '' }, site), '../index.html');
	assert.equal(hrefFor(page, { target: 'app', fromId: 'guide/home', repo: 'o/r' }), '/help/dev/01-architecture#backend');
	assert.equal(hrefFor({ kind: 'repo', path: 'LICENSE', fragment: '' }, site), 'https://github.com/o/r/blob/main/LICENSE');
	assert.equal(hrefFor({ kind: 'anchor', fragment: 'x' }, site), '#x');
	assert.equal(assetHref('docs/a.png', { target: 'site', fromId: 'dev/arch' }), '../assets/docs/a.png');
	assert.equal(assetHref('docs/a.png', { target: 'app', fromId: 'dev/arch' }), '/docs-data/assets/docs/a.png');
});

test('checkFragments reports missing anchors on pages and on the same page', () => {
	const rendered = [
		{ page: { id: 'a/x', srcPath: 'x.md' }, headingIds: new Set(['one']), links: [
			{ line: 3, resolved: { kind: 'anchor', fragment: 'two' } },
			{ line: 4, resolved: { kind: 'page', id: 'a/y', fragment: 'here' } },
			{ line: 5, resolved: { kind: 'repo', path: 'R', fragment: 'whatever' } }
		] },
		{ page: { id: 'a/y', srcPath: 'y.md' }, headingIds: new Set(['here']), links: [] }
	];
	assert.deepEqual(checkFragments(rendered), ['x.md:3: missing anchor #two in a/x']);
});

test('fillLinks substitutes placeholders and escapes attribute values', () => {
	const html = '<a href="@@doclink:0@@">a</a><img src="@@docasset:0@@">';
	const out = fillLinks(html, { links: [{ resolved: { kind: 'external', url: 'https://x/?a=1&b="2"' } }], assets: ['d/i.png'] }, { target: 'app', fromId: 'guide/home', repo: 'o/r' });
	assert.equal(out, '<a href="https://x/?a=1&amp;b=&quot;2&quot;">a</a><img src="/docs-data/assets/d/i.png">');
});
