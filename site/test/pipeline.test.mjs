import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildDocs, repoLinkLines, userDocs } from '../src/pipeline.mjs';
import { fixtureTree, MANIFEST } from './helpers.mjs';

test('buildDocs: a clean fixture yields no errors, pages in manifest order, one render per page', async () => {
	const { pages, rendered, errors } = await buildDocs(fixtureTree(), MANIFEST);
	assert.deepEqual(errors, []);
	assert.deepEqual(pages.map((p) => p.id), [
		'guide/home',
		'guide/getting-started',
		'guide/configuring-arm',
		'dev/architecture',
		'dev/01-architecture',
		'dev/contributing'
	]);
	assert.equal(rendered.length, pages.length);
	rendered.forEach((r, i) => assert.equal(r.page, pages[i]));
});

test('buildDocs: the returned nav is the resolved nav', async () => {
	const { nav } = await buildDocs(fixtureTree(), MANIFEST);
	const items = nav.flatMap((s) => s.groups.flatMap((g) => g.items));
	assert.deepEqual(items[0].resolved, { kind: 'page', id: 'guide/home', fragment: '' });
	const link = items.find((i) => i.label === 'Open an issue');
	assert.equal(link.resolved.kind, 'external');
});

test('buildDocs: errors come from collect, then render, then fragment check, then nav', async () => {
	const root = fixtureTree({
		'docs/user/Orphan.md': '# Orphan\n',
		'docs/user/Home.md': '# ARM Wiki\n\nSee [gone](Nowhere-Page) and [anchor](Configuring-ARM#nope).\n'
	});
	const manifest = structuredClone(MANIFEST);
	manifest.sections[1].groups[0].files[1].link = 'missing/target.md';
	const { errors } = await buildDocs(root, manifest);
	assert.deepEqual(errors, [
		'manifest: docs/user/Orphan.md is not placed in any section',
		'docs/user/Home.md:3: link target not found: docs/user/Nowhere-Page',
		'docs/user/Home.md:3: missing anchor #nope in guide/configuring-arm',
		'manifest.json (Using ARM): link target not found: missing/target.md'
	]);
});

const entry = (srcPath, links) => ({
	page: { srcPath },
	links: links.map(([line, raw, kind]) => ({ line, raw, resolved: { kind } }))
});

test('repoLinkLines: lists only repo links, not page or external ones', () => {
	const rendered = [entry('a.md', [[1, 'x.md', 'page'], [2, 'src/y.py', 'repo'], [3, 'https://e.com', 'external']])];
	assert.deepEqual(repoLinkLines(rendered), ['a.md:2: src/y.py']);
});

test('repoLinkLines: follows page order, then link order within a page, as <srcPath>:<line>: <raw>', () => {
	const rendered = [
		entry('b.md', [[9, '../one', 'repo'], [4, '../two', 'repo']]),
		entry('a.md', [[7, '../three', 'repo']])
	];
	assert.deepEqual(repoLinkLines(rendered), ['b.md:9: ../one', 'b.md:4: ../two', 'a.md:7: ../three']);
});

test('repoLinkLines: pages without links, or no pages at all, give an empty list', () => {
	assert.deepEqual(repoLinkLines([entry('a.md', []), entry('b.md', [])]), []);
	assert.deepEqual(repoLinkLines([]), []);
});

const docEntry = (id, audience) => ({ page: { id, audience } });
const section = (id, audience) => ({ id, audience });

test('userDocs: keeps only user pages and sections, in their original order', () => {
	const rendered = [docEntry('a', 'user'), docEntry('b', 'dev'), docEntry('c', 'user')];
	const nav = [section('s1', 'user'), section('s2', 'dev'), section('s3', 'user')];
	const result = userDocs(rendered, nav);
	assert.deepEqual(result.rendered.map((r) => r.page.id), ['a', 'c']);
	assert.deepEqual(result.nav.map((s) => s.id), ['s1', 's3']);
});

test('userDocs: dev and any other audience are dropped', () => {
	const result = userDocs(
		[docEntry('a', 'dev'), docEntry('b', 'admin'), docEntry('c', undefined)],
		[section('s1', 'dev'), section('s2', 'admin'), section('s3', undefined)]
	);
	assert.deepEqual(result, { rendered: [], nav: [] });
});

test('userDocs: the kept objects are the same references, not copies', () => {
	const page = docEntry('a', 'user');
	const sect = section('s1', 'user');
	const result = userDocs([page], [sect]);
	assert.equal(result.rendered[0], page);
	assert.equal(result.nav[0], sect);
});

test('userDocs: the inputs are not mutated', () => {
	const rendered = [docEntry('a', 'user'), docEntry('b', 'dev')];
	const nav = [section('s1', 'dev'), section('s2', 'user')];
	const renderedBefore = structuredClone(rendered);
	const navBefore = structuredClone(nav);
	userDocs(rendered, nav);
	assert.deepEqual(rendered, renderedBefore);
	assert.deepEqual(nav, navBefore);
});

test('userDocs: empty inputs give empty arrays', () => {
	assert.deepEqual(userDocs([], []), { rendered: [], nav: [] });
});
