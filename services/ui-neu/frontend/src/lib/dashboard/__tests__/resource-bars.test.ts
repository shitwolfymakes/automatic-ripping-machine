import { describe, expect, it } from 'vitest';
import type { StorageRoot } from '$lib/types/api.gen';
import { filesHref, storageBars } from '../resource-bars';

const root = (name: string, placement?: StorageRoot['placement']): StorageRoot => ({
	name,
	path: `/${name}`,
	total_gb: 100,
	used_gb: 40,
	free_gb: 60,
	percent: 40,
	placement
});

describe('storageBars', () => {
	it('keeps every root that has a disk of its own', () => {
		const roots = [root('MEDIA_ROOT'), root('RAW_ROOT'), root('STAGING_ROOT', 'separate_device')];
		expect(storageBars(roots)).toEqual(roots);
	});

	it.each(['inside_raw', 'same_device'] as const)('drops a staging area that is %s', (placement) => {
		const names = storageBars([root('RAW_ROOT'), root('STAGING_ROOT', placement)]).map((r) => r.name);
		expect(names).toEqual(['RAW_ROOT']);
	});

	it('keeps a root with no placement', () => {
		expect(storageBars([root('STAGING_ROOT', null)])).toHaveLength(1);
	});
});

describe('filesHref', () => {
	it('links a known root to its files-browser root', () => {
		expect(filesHref('RAW_ROOT')).toBe('/files?root=RAW');
	});

	it('falls back to /files for staging, which has no files-browser root', () => {
		expect(filesHref('STAGING_ROOT')).toBe('/files');
	});
});
