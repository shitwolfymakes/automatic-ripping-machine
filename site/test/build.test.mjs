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

test('a missing ARM root is a clear error', () => {
	const res = run(['--target', 'app'], { ARM_ROOT: '/nonexistent/arm' });
	assert.equal(res.status, 1);
	assert.match(res.stderr, /ARM root not found at \/nonexistent\/arm \(set ARM_ROOT\)/);
});
