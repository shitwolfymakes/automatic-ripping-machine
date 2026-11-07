import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildDocs } from '../src/pipeline.mjs';
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
