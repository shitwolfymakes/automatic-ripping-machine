import { test } from 'node:test';
import assert from 'node:assert/strict';
import { collectPages } from '../src/collect.mjs';
import { createResolver, hrefFor, isOffsite, assetHref, outPath, appRoute, rootPrefix, checkFragments, fillLinks } from '../src/links.mjs';
import { fixtureTree, MANIFEST } from './helpers.mjs';

const UP = 'https://github.com/automatic-ripping-machine/automatic-ripping-machine';

function setup(extra) {
	const armRoot = fixtureTree(extra);
	const { pages } = collectPages(armRoot, MANIFEST);
	return createResolver({ armRoot, pages, manifest: MANIFEST });
}

test('wiki bare targets resolve from wiki pages, with fragments', () => {
	const r = setup();
	assert.deepEqual(r.resolve('Getting-Started', 'docs/user/Home.md'), { kind: 'page', id: 'guide/getting-started', fragment: '' });
	assert.deepEqual(r.resolve('Configuring-ARM#options', 'docs/user/Getting-Started.md'), { kind: 'page', id: 'guide/configuring-arm', fragment: 'options' });
});

test('a bare target to a missing wiki page is an error', () => {
	assert.equal(setup().resolve('Nope', 'docs/user/Home.md').kind, 'error');
});

test('upstream wiki and blob URLs map into the site', () => {
	const r = setup();
	assert.deepEqual(r.resolve(`${UP}/wiki`, 'docs/user/_Sidebar.md'), { kind: 'page', id: 'guide/home', fragment: '' });
	assert.deepEqual(r.resolve(`${UP}/wiki/Getting-Started`, 'docs/developers/architecture/README.md'), { kind: 'page', id: 'guide/getting-started', fragment: '' });
	assert.deepEqual(r.resolve(`${UP}/blob/main/docs/developers/architecture/README.md`, 'docs/user/_Sidebar.md'), { kind: 'page', id: 'dev/architecture', fragment: '' });
	assert.deepEqual(r.resolve(`${UP}/blob/main/LICENSE`, 'docs/user/Home.md'), { kind: 'repo', path: 'LICENSE', fragment: '' });
});

test('other GitHub URLs on the same repo stay external', () => {
	assert.deepEqual(setup().resolve(`${UP}/issues/new/choose`, 'docs/user/_Sidebar.md'), { kind: 'external', url: `${UP}/issues/new/choose` });
});

test('relative repo paths, directories resolve to README, unpublished files go to GitHub', () => {
	const r = setup();
	assert.deepEqual(r.resolve('01-architecture.md', 'docs/developers/architecture/README.md'), { kind: 'page', id: 'dev/01-architecture', fragment: '' });
	assert.deepEqual(r.resolve('docs/developers/architecture/', 'CONTRIBUTING.md'), { kind: 'page', id: 'dev/architecture', fragment: '' });
	assert.deepEqual(r.resolve('LICENSE', 'CONTRIBUTING.md'), { kind: 'repo', path: 'LICENSE', fragment: '' });
});

test('missing files and repo escapes are errors', () => {
	const r = setup();
	assert.deepEqual(r.resolve('nope.md', 'docs/developers/architecture/README.md'), { kind: 'error', message: 'link target not found: docs/developers/architecture/nope.md' });
	assert.equal(r.resolve('../../x.md', 'docs/developers/architecture/README.md').kind, 'error');
});

test('URL-encoded targets decode; malformed encoding is an error, not a throw', () => {
	const r = setup({ 'docs/developers/architecture/My Page.md': '# Mine\n' });
	assert.deepEqual(r.resolve('My%20Page.md', 'docs/developers/architecture/README.md'), { kind: 'repo', path: 'docs/developers/architecture/My Page.md', fragment: '' });
	assert.deepEqual(r.resolve('bad%E0%A4%A.md', 'docs/developers/architecture/README.md'), { kind: 'error', message: 'malformed link: bad%E0%A4%A.md' });
});

test('anchors and externals', () => {
	const r = setup();
	assert.deepEqual(r.resolve('#install', 'docs/user/Getting-Started.md'), { kind: 'anchor', fragment: 'install' });
	assert.deepEqual(r.resolve('https://www.makemkv.com/', 'docs/user/Home.md'), { kind: 'external', url: 'https://www.makemkv.com/' });
	assert.deepEqual(r.resolve('mailto:a@b.c', 'docs/user/Home.md'), { kind: 'external', url: 'mailto:a@b.c' });
});

test('assets resolve relative to the source; missing is an error', () => {
	const r = setup({ 'docs/developers/architecture/img/topo.png': 'png' });
	assert.deepEqual(r.resolveAsset('img/topo.png', 'docs/developers/architecture/README.md'), { kind: 'asset', path: 'docs/developers/architecture/img/topo.png' });
	assert.equal(r.resolveAsset('img/none.png', 'docs/developers/architecture/README.md').kind, 'error');
	assert.deepEqual(r.resolveAsset('https://x/y.png', 'docs/developers/architecture/README.md'), { kind: 'external', url: 'https://x/y.png' });
});

test('paths and hrefs per target', () => {
	assert.equal(outPath('guide/home'), 'index.html');
	assert.equal(outPath('dev/architecture'), 'dev/architecture.html');
	assert.equal(appRoute('guide/home'), '/help');
	assert.equal(appRoute('dev/architecture'), '/help/dev/architecture');
	assert.equal(rootPrefix('guide/home'), '');
	assert.equal(rootPrefix('dev/architecture'), '../');
	const page = { kind: 'page', id: 'dev/01-architecture', fragment: 'backend' };
	const site = { target: 'site', fromId: 'guide/getting-started', repo: 'o/r' };
	assert.equal(hrefFor(page, site), '../dev/01-architecture.html#backend');
	assert.equal(hrefFor(page, { ...site, fromId: 'guide/home' }), 'dev/01-architecture.html#backend');
	assert.equal(hrefFor({ kind: 'page', id: 'guide/home', fragment: '' }, site), '../index.html');
	assert.equal(hrefFor(page, { target: 'app', fromId: 'guide/home', repo: 'o/r' }), '/help/dev/01-architecture#backend');
	assert.equal(hrefFor({ kind: 'repo', path: 'LICENSE', fragment: '' }, site), 'https://github.com/o/r/blob/main/LICENSE');
	assert.equal(hrefFor({ kind: 'anchor', fragment: 'x' }, site), '#x');
	assert.equal(assetHref('docs/a.png', { target: 'site', fromId: 'dev/architecture' }), '../assets/docs/a.png');
	assert.equal(assetHref('docs/a.png', { target: 'app', fromId: 'dev/architecture' }), '/docs-data/assets/docs/a.png');
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

test('in the app, links to pages outside the app bundle go to the public site in a new tab', () => {
	const ctx = { target: 'app', fromId: 'guide/home', repo: 'o/r', siteUrl: 'https://example.test/arm-v3/', appIds: new Set(['guide/home', 'guide/faq']) };
	const dev = { kind: 'page', id: 'dev/architecture', fragment: 'topology' };
	assert.equal(hrefFor(dev, ctx), 'https://example.test/arm-v3/dev/architecture.html#topology');
	assert.equal(hrefFor({ kind: 'page', id: 'guide/faq', fragment: '' }, ctx), '/help/guide/faq');
	assert.equal(isOffsite(dev, ctx), true);
	assert.equal(isOffsite(dev, { ...ctx, target: 'site' }), false);
	const html = '<a href="@@doclink:0@@">arch</a> <a href="@@doclink:1@@">faq</a>';
	const out = fillLinks(html, { links: [{ resolved: dev }, { resolved: { kind: 'page', id: 'guide/faq', fragment: '' } }], assets: [] }, ctx);
	assert.equal(out, '<a href="https://example.test/arm-v3/dev/architecture.html#topology" target="_blank" rel="noopener">arch</a> <a href="/help/guide/faq">faq</a>');
});
