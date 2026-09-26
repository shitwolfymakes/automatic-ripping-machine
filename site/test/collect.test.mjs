import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseSidebar, slugFor, collectPages } from '../src/collect.mjs';
import { fixtureTree, MANIFEST } from './helpers.mjs';

test('parseSidebar: bold lines are groups, list items are links, a bold link is its own item', () => {
	const groups = parseSidebar('**[Home](https://x/wiki)**\n\n**Getting Started**\n  - [Getting Started](Getting-Started)\n  - [Config](Configuring-ARM)\n');
	assert.deepEqual(groups, [
		{ label: null, items: [{ label: 'Home', target: 'https://x/wiki', line: 1 }] },
		{ label: 'Getting Started', items: [
			{ label: 'Getting Started', target: 'Getting-Started', line: 4 },
			{ label: 'Config', target: 'Configuring-ARM', line: 5 }
		] }
	]);
});

test('slugFor: lowercased stem; README takes its directory name', () => {
	assert.equal(slugFor('arm_wiki/Getting-Started.md'), 'getting-started');
	assert.equal(slugFor('docs/arch/01-architecture.md'), '01-architecture');
	assert.equal(slugFor('docs/arch/README.md'), 'arch');
	assert.equal(slugFor('CONTRIBUTING.md'), 'contributing');
});

test('collectPages: wiki pages (minus _files), manifest pages in pattern order, titles', () => {
	const root = fixtureTree();
	const { pages, nav, errors } = collectPages(root, MANIFEST);
	assert.deepEqual(errors, []);
	assert.deepEqual(pages.map((p) => p.id), [
		'guide/configuring-arm', 'guide/getting-started', 'guide/home',
		'dev/arch', 'dev/01-architecture', 'dev/contributing'
	]);
	const home = pages.find((p) => p.id === 'guide/home');
	assert.equal(home.title, 'ARM Wiki');
	assert.equal(home.srcPath, 'arm_wiki/Home.md');
	assert.equal(nav[0].id, 'guide');
	assert.equal(nav[0].groups[1].label, 'Getting Started');
	assert.deepEqual(nav[0].groups[1].items[0], { label: 'Getting Started', target: 'Getting-Started', line: 4, from: 'arm_wiki/_Sidebar.md' });
	assert.deepEqual(nav[1].groups[0], { label: 'Architecture', items: [
		{ label: 'Architecture', pageId: 'dev/arch' },
		{ label: 'Service topology', pageId: 'dev/01-architecture' }
	] });
});

test('collectPages: title falls back to the de-slugged stem and ignores # lines in code fences', () => {
	const root = fixtureTree({ 'arm_wiki/FAQ.md': '```bash\n# not a title\n```\n\nNo heading here.\n' });
	const faq = collectPages(root, MANIFEST).pages.find((p) => p.id === 'guide/faq');
	assert.equal(faq.title, 'FAQ');
});

test('collectPages: a pattern matching nothing is an error', () => {
	const root = fixtureTree();
	const manifest = structuredClone(MANIFEST);
	manifest.sections[1].groups.push({ label: 'Ops', files: ['docs/ops/*.md'] });
	assert.deepEqual(collectPages(root, manifest).errors, ['manifest: docs/ops/*.md matched no files']);
});

test('collectPages: two sources with the same id is an error', () => {
	const root = fixtureTree({ 'docs/other/01-architecture.md': '# Dup\n' });
	const manifest = structuredClone(MANIFEST);
	manifest.sections[1].groups.push({ label: 'Other', files: ['docs/other/*.md'] });
	assert.deepEqual(collectPages(root, manifest).errors, [
		'duplicate page id dev/01-architecture: docs/arch/01-architecture.md and docs/other/01-architecture.md'
	]);
});

test('collectPages: an id with characters outside the app id rule is an error, not added as a page', () => {
	const root = fixtureTree({ 'arm_wiki/Foo.Bar.md': '# Foo Bar\n' });
	const { pages, errors } = collectPages(root, MANIFEST);
	assert.deepEqual(errors, ['invalid page id guide/foo.bar from arm_wiki/Foo.Bar.md (slugs may use a-z, 0-9, _ and -)']);
	assert.ok(!pages.some((p) => p.srcPath === 'arm_wiki/Foo.Bar.md'));
});

test('collectPages: a missing sidebar is an error, not a crash', () => {
	const root = fixtureTree();
	const manifest = structuredClone(MANIFEST);
	manifest.sections[0].sidebar = 'arm_wiki/_Nope.md';
	assert.deepEqual(collectPages(root, manifest).errors, ['manifest: sidebar arm_wiki/_Nope.md not found']);
});
