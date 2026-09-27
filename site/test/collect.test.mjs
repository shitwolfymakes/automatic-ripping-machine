import { test } from 'node:test';
import assert from 'node:assert/strict';
import { slugFor, collectPages } from '../src/collect.mjs';
import { fixtureTree, MANIFEST } from './helpers.mjs';

test('slugFor: lowercased stem; README takes its directory name', () => {
	assert.equal(slugFor('docs/user/Getting-Started.md'), 'getting-started');
	assert.equal(slugFor('docs/developers/architecture/01-architecture.md'), '01-architecture');
	assert.equal(slugFor('docs/developers/architecture/README.md'), 'architecture');
	assert.equal(slugFor('CONTRIBUTING.md'), 'contributing');
});

test('collectPages: pages in manifest order, id prefix from audience, titles', () => {
	const root = fixtureTree();
	const { pages, errors } = collectPages(root, MANIFEST);
	assert.deepEqual(errors, []);
	assert.deepEqual(pages.map((p) => [p.id, p.audience]), [
		['guide/home', 'user'],
		['guide/getting-started', 'user'],
		['guide/configuring-arm', 'user'],
		['dev/architecture', 'dev'],
		['dev/01-architecture', 'dev'],
		['dev/contributing', 'dev']
	]);
	const home = pages.find((p) => p.id === 'guide/home');
	assert.equal(home.title, 'ARM Wiki');
	assert.equal(home.srcPath, 'docs/user/Home.md');
});

test('collectPages: nav mirrors manifest sections, with label overrides and link items', () => {
	const { nav } = collectPages(fixtureTree(), MANIFEST);
	assert.deepEqual(nav.map((s) => [s.id, s.label, s.audience]), [
		['start', 'Get started', 'user'],
		['using', 'Using ARM', 'user'],
		['developers', 'Developers', 'dev']
	]);
	assert.deepEqual(nav[0].groups, [{ label: null, items: [
		{ label: 'Home', pageId: 'guide/home' },
		{ label: 'Getting Started', pageId: 'guide/getting-started' }
	] }]);
	assert.deepEqual(nav[1].groups[0].items[1], {
		label: 'Open an issue',
		target: 'https://github.com/automatic-ripping-machine/automatic-ripping-machine/issues/new/choose',
		from: 'manifest.json',
		where: 'manifest.json (Using ARM)'
	});
	assert.deepEqual(nav[2].groups[0], { label: 'Architecture', items: [
		{ label: 'Architecture', pageId: 'dev/architecture' },
		{ label: 'Service topology', pageId: 'dev/01-architecture' }
	] });
});

test('collectPages: a file item may override the slug', () => {
	const manifest = structuredClone(MANIFEST);
	manifest.sections[1].groups[0].files[0] = { file: 'docs/user/Configuring-ARM.md', slug: 'config' };
	const { pages, errors } = collectPages(fixtureTree(), manifest);
	assert.deepEqual(errors, []);
	assert.ok(pages.some((p) => p.id === 'guide/config' && p.srcPath === 'docs/user/Configuring-ARM.md'));
});

test('collectPages: title falls back to the de-slugged stem and ignores # lines in code fences', () => {
	const manifest = structuredClone(MANIFEST);
	manifest.sections[1].groups[0].files.push('docs/user/FAQ.md');
	const root = fixtureTree({ 'docs/user/FAQ.md': '```bash\n# not a title\n```\n\nNo heading here.\n' });
	const faq = collectPages(root, manifest).pages.find((p) => p.id === 'guide/faq');
	assert.equal(faq.title, 'FAQ');
});

test('collectPages: a user doc not placed in any section is an error', () => {
	const root = fixtureTree({ 'docs/user/Orphan.md': '# Orphan\n' });
	assert.deepEqual(collectPages(root, MANIFEST).errors, ['manifest: docs/user/Orphan.md is not placed in any section']);
});

test('collectPages: a pattern or file matching nothing is an error', () => {
	const manifest = structuredClone(MANIFEST);
	manifest.sections[2].groups.push({ label: 'Ops', files: ['docs/nonexistent/*.md', { file: 'docs/nope.md' }] });
	assert.deepEqual(collectPages(fixtureTree(), manifest).errors, [
		'manifest: docs/nonexistent/*.md matched no files',
		'manifest: docs/nope.md matched no files'
	]);
});

test('collectPages: an unknown audience is an error', () => {
	const manifest = structuredClone(MANIFEST);
	manifest.sections[2].audience = 'ops';
	assert.deepEqual(collectPages(fixtureTree(), manifest).errors, ['manifest: section developers has unknown audience ops (use user or dev)']);
});

test('collectPages: two sources with the same id is an error', () => {
	const manifest = structuredClone(MANIFEST);
	manifest.sections[2].groups.push({ label: 'Other', files: ['docs/other/*.md'] });
	const root = fixtureTree({ 'docs/other/01-architecture.md': '# Dup\n' });
	assert.deepEqual(collectPages(root, manifest).errors, [
		'duplicate page id dev/01-architecture: docs/developers/architecture/01-architecture.md and docs/other/01-architecture.md'
	]);
});

test('collectPages: an id with characters outside the app id rule is an error, not added as a page', () => {
	const manifest = structuredClone(MANIFEST);
	manifest.sections[1].groups[0].files.push('docs/user/Foo.Bar.md');
	const root = fixtureTree({ 'docs/user/Foo.Bar.md': '# Foo Bar\n' });
	const { pages, errors } = collectPages(root, manifest);
	assert.deepEqual(errors, ['invalid page id guide/foo.bar from docs/user/Foo.Bar.md (slugs may use a-z, 0-9, _ and -)']);
	assert.ok(!pages.some((p) => p.srcPath === 'docs/user/Foo.Bar.md'));
});
