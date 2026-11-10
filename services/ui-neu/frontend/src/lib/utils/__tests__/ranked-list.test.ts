import { describe, it, expect } from 'vitest';
import type { ConfigFieldMeta } from '$lib/types/api.gen';
import { missingKey } from '$lib/utils/ranked-list';

const field = (enum_requires?: Record<string, string>) =>
	({ key: 'sources', enum_requires }) as unknown as ConfigFieldMeta;

describe('missingKey', () => {
	it('returns null for a field with no enum_requires', () => {
		expect(missingKey(field(), {}, 'tmdb')).toBeNull();
	});

	it('returns null for an entry enum_requires does not list', () => {
		expect(missingKey(field({ omdb: 'omdb_key' }), {}, 'tmdb')).toBeNull();
	});

	it('returns the key when config does not have it', () => {
		expect(missingKey(field({ tmdb: 'tmdb_key' }), {}, 'tmdb')).toBe('tmdb_key');
	});

	it('returns the key when it is an empty string', () => {
		expect(missingKey(field({ tmdb: 'tmdb_key' }), { tmdb_key: '' }, 'tmdb')).toBe('tmdb_key');
	});

	it('returns the key when it is only whitespace', () => {
		expect(missingKey(field({ tmdb: 'tmdb_key' }), { tmdb_key: '   ' }, 'tmdb')).toBe('tmdb_key');
	});

	it('returns the key when it is not a string', () => {
		expect(missingKey(field({ tmdb: 'tmdb_key' }), { tmdb_key: 42 }, 'tmdb')).toBe('tmdb_key');
	});

	it('returns null when the key is set', () => {
		expect(missingKey(field({ tmdb: 'tmdb_key' }), { tmdb_key: 'abc' }, 'tmdb')).toBeNull();
	});
});
