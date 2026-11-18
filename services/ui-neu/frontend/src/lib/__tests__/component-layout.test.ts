import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';

const COMPONENTS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'components');

const DOMAIN_FOLDERS = [
	'dashboard',
	'drives',
	'episodes',
	'files',
	'handbrake',
	'help',
	'jobs',
	'logs',
	'match',
	'music',
	'notifications',
	'sessions',
	'settings',
	'setup',
	'transcode'
];
const SPECIAL_FOLDERS = ['shared', 'layout', '__tests__', '__fixtures__'];
const ALLOWED_FOLDERS = [...DOMAIN_FOLDERS, ...SPECIAL_FOLDERS];

const entries = readdirSync(COMPONENTS_DIR, { withFileTypes: true });

describe('components layout', () => {
	it('keeps no .svelte file directly in components/', () => {
		const strays = entries.filter((e) => e.isFile() && e.name.endsWith('.svelte')).map((e) => e.name);
		expect(strays).toEqual([]);
	});

	it('only has domain, shared, layout, __tests__ and __fixtures__ folders directly under components/', () => {
		const unknown = entries.filter((e) => e.isDirectory() && !ALLOWED_FOLDERS.includes(e.name)).map((e) => e.name);
		expect(unknown).toEqual([]);
	});
});
