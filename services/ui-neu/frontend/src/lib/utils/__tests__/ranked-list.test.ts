import { describe, it, expect } from 'vitest';
import type { ConfigFieldMeta } from '$lib/types/api.gen';
import { missingKey, rankedRows, rankedSelected, swapRank } from '$lib/utils/ranked-list';

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

describe('rankedSelected', () => {
	const known = ['a', 'b', 'c'];

	it('gives an empty list when the value is not an array', () => {
		expect(rankedSelected('a', known)).toEqual([]);
		expect(rankedSelected(undefined, known)).toEqual([]);
	});

	it('drops unknown entries and repeats', () => {
		expect(rankedSelected(['b', 'x', 'b', 'a'], known)).toEqual(['b', 'a']);
	});

	it('keeps the order of the value', () => {
		expect(rankedSelected(['c', 'a', 'b'], known)).toEqual(['c', 'a', 'b']);
	});
});

describe('rankedRows', () => {
	it('lists the entries switched on first, then the rest in known order', () => {
		expect(rankedRows(['c', 'a'], ['a', 'b', 'c', 'd'])).toEqual(['c', 'a', 'b', 'd']);
	});

	it('lists every known entry when none is on', () => {
		expect(rankedRows([], ['a', 'b'])).toEqual(['a', 'b']);
	});
});

describe('swapRank', () => {
	const list = ['a', 'b', 'c'];

	it('swaps an entry up from the middle', () => {
		expect(swapRank(list, 'b', 'up')).toEqual(['b', 'a', 'c']);
	});

	it('swaps an entry down from the middle', () => {
		expect(swapRank(list, 'b', 'down')).toEqual(['a', 'c', 'b']);
	});

	it('gives null moving the top entry up', () => {
		expect(swapRank(list, 'a', 'up')).toBeNull();
	});

	it('gives null moving the bottom entry down', () => {
		expect(swapRank(list, 'c', 'down')).toBeNull();
	});

	it('gives null for an entry that is not on', () => {
		expect(swapRank(list, 'x', 'up')).toBeNull();
		expect(swapRank(list, 'x', 'down')).toBeNull();
	});

	it('does not change the input list', () => {
		swapRank(list, 'b', 'up');
		expect(list).toEqual(['a', 'b', 'c']);
	});
});
