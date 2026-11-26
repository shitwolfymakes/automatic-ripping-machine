// Check 6 of the field docs links: every internal registry entry names a help
// page the site builds for the in-app help and a heading that exists on it.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import GithubSlugger from 'github-slugger';
import { loadManifest } from '../src/collect.mjs';
import { buildDocs, userDocs } from '../src/pipeline.mjs';
import { fixtureTree, MANIFEST } from './helpers.mjs';

const siteDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const armRoot = join(siteDir, '..');
const REGISTRY = join(armRoot, 'packages/arm_common/arm_common/field_docs.json');

// The in-app help ships the user pages only, so those are the page ids a link can target.
async function helpHeadings(root, manifest) {
	const { rendered, errors } = await buildDocs(root, manifest);
	assert.deepEqual(errors, []);
	return new Map(userDocs(rendered, []).rendered.map((r) => [r.page.id, r.headingIds]));
}

// A repeated heading gets a numeric suffix on the site, which a link cannot name.
function isRepeated(anchor, ids) {
	return ids.has(`${anchor}-1`);
}

function problemFor(page, section, headings) {
	const ids = headings.get(page);
	if (!ids) return `page "${page}" is not a help page`;
	if (section === undefined) return null;
	const anchor = new GithubSlugger().slug(section);
	if (!ids.has(anchor)) return `heading "${section}" (#${anchor}) is not on page "${page}"`;
	if (isRepeated(anchor, ids)) return `heading "${section}" (#${anchor}) occurs more than once on page "${page}"`;
	return null;
}

function internalLinkErrors(registry, headings) {
	return Object.entries(registry.fields)
		.filter(([, entry]) => entry.type === 'internal')
		.map(([id, entry]) => [id, problemFor(entry.page, entry.section, headings)])
		.filter(([, problem]) => problem !== null)
		.map(([id, problem]) => `${id}: ${problem}`);
}

const entry = (page, section) => ({ type: 'internal', page, ...(section === undefined ? {} : { section }) });

async function fixtureHeadings() {
	const root = fixtureTree({
		'docs/user/Configuring-ARM.md': '# Configuring ARM\n\n## Options\n\n## Repeat\n\n## Repeat\n\n## Rip / transcode behaviour\n'
	});
	return helpHeadings(root, MANIFEST);
}

test('a link to a real page and heading passes, with or without a section', async () => {
	const headings = await fixtureHeadings();
	const registry = { fields: {
		a: entry('guide/configuring-arm', 'Options'),
		b: entry('guide/configuring-arm', 'Rip / transcode behaviour'),
		c: entry('guide/getting-started'),
		d: { type: 'external', url: 'https://example.com/' },
		e: { none: 'no link' }
	} };
	assert.deepEqual(internalLinkErrors(registry, headings), []);
});

test('a missing page names the registry id and the page', async () => {
	const errors = internalLinkErrors({ fields: { 'x.y': entry('guide/nope') } }, await fixtureHeadings());
	assert.deepEqual(errors, ['x.y: page "guide/nope" is not a help page']);
});

test('a developer page is not a help page', async () => {
	const errors = internalLinkErrors({ fields: { 'x.y': entry('dev/contributing') } }, await fixtureHeadings());
	assert.deepEqual(errors, ['x.y: page "dev/contributing" is not a help page']);
});

test('a missing heading names the registry id, the page and the heading', async () => {
	const errors = internalLinkErrors({ fields: { 'x.y': entry('guide/configuring-arm', 'Nothing here') } }, await fixtureHeadings());
	assert.deepEqual(errors, ['x.y: heading "Nothing here" (#nothing-here) is not on page "guide/configuring-arm"']);
});

test('a heading that occurs more than once on its page fails', async () => {
	const errors = internalLinkErrors({ fields: { 'x.y': entry('guide/configuring-arm', 'Repeat') } }, await fixtureHeadings());
	assert.deepEqual(errors, ['x.y: heading "Repeat" (#repeat) occurs more than once on page "guide/configuring-arm"']);
});

test('every internal entry in the real registry points at a real help page and heading', async () => {
	const registry = JSON.parse(readFileSync(REGISTRY, 'utf8'));
	const headings = await helpHeadings(armRoot, loadManifest(siteDir));
	assert.deepEqual(internalLinkErrors(registry, headings), []);
});
