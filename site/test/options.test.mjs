import { test } from 'node:test';
import assert from 'node:assert/strict';
import { join, resolve } from 'node:path';
import { parseOptions } from '../src/options.mjs';

const siteDir = resolve('/tmp/arm-site-fixture');

test('defaults to target all, quiet, and build dirs under the site dir', () => {
	const o = parseOptions([], siteDir);
	assert.equal(o.target, 'all');
	assert.equal(o.verbose, false);
	assert.equal(o.out, resolve(siteDir, 'build'));
	assert.equal(o.appOut, join(o.out, 'app'));
});

test('accepts --target site and --target app', () => {
	assert.equal(parseOptions(['--target', 'site'], siteDir).target, 'site');
	assert.equal(parseOptions(['--target', 'app'], siteDir).target, 'app');
});

test('resolves a relative --out against the cwd and puts appOut under it', () => {
	const o = parseOptions(['--out', 'rel/dir'], siteDir);
	assert.equal(o.out, resolve(process.cwd(), 'rel/dir'));
	assert.equal(o.appOut, join(o.out, 'app'));
});

test('--app-out overrides appOut and is resolved', () => {
	const o = parseOptions(['--app-out', 'elsewhere'], siteDir);
	assert.equal(o.appOut, resolve(process.cwd(), 'elsewhere'));
});

test('--verbose turns verbose on', () => {
	assert.equal(parseOptions(['--verbose'], siteDir).verbose, true);
});

test('rejects an unknown --target', () => {
	assert.throws(() => parseOptions(['--target', 'bogus'], siteDir), {
		name: 'Error',
		message: '--target must be all, site or app (got bogus)'
	});
});

test('rejects an unknown option', () => {
	assert.throws(() => parseOptions(['--nope'], siteDir), { code: 'ERR_PARSE_ARGS_UNKNOWN_OPTION' });
});
