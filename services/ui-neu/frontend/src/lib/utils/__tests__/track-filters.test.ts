import { describe, expect, it } from 'vitest';
import { parseDuration, parseIndexList, trackFiltersBody } from '../../jobs/track-filters';

describe('parseIndexList', () => {
	it('splits on commas', () => {
		expect(parseIndexList('1,2,3')).toEqual([1, 2, 3]);
	});

	it('splits on spaces', () => {
		expect(parseIndexList('1 2 3')).toEqual([1, 2, 3]);
	});

	it('splits on commas and spaces mixed', () => {
		expect(parseIndexList('1, 2 ,3  4')).toEqual([1, 2, 3, 4]);
	});

	it('drops zero, negatives, decimals and words', () => {
		expect(parseIndexList('0, -1, 2.5, abc, 7')).toEqual([7]);
	});

	it('gives an empty list for an empty string', () => {
		expect(parseIndexList('')).toEqual([]);
	});

	it('gives an empty list for only separators', () => {
		expect(parseIndexList(' , ,, ')).toEqual([]);
	});

	it('keeps order and duplicates as typed', () => {
		expect(parseIndexList('5, 1, 5, 3')).toEqual([5, 1, 5, 3]);
	});
});

describe('parseDuration', () => {
	it('parses a number of seconds', () => {
		expect(parseDuration('90')).toBe(90);
	});

	it('keeps a zero', () => {
		expect(parseDuration('0')).toBe(0);
	});

	it('gives null for a blank input', () => {
		expect(parseDuration('')).toBeNull();
	});

	it('gives NaN for non-numeric text', () => {
		expect(parseDuration('abc')).toBeNaN();
	});
});

describe('trackFiltersBody', () => {
	it.each(['main_feature', 'all_tracks', 'archive'] as const)(
		'gives null for the %s selection, even with filters set',
		(selection) => {
			expect(trackFiltersBody(selection, { min_duration_seconds: 60, title_indices: [1] })).toBeNull();
		}
	);

	it('drops null and undefined keys for the custom selection', () => {
		expect(
			trackFiltersBody('custom', {
				min_duration_seconds: null,
				max_duration_seconds: undefined,
				title_indices: [2]
			})
		).toEqual({ title_indices: [2] });
	});

	it('keeps a zero, an empty array and a non-empty array', () => {
		const filters = { min_duration_seconds: 0, title_indices: [], title_indices_exclude: [3, 4] };
		expect(trackFiltersBody('custom', filters)).toEqual(filters);
	});

	it('gives an empty object for empty filters', () => {
		expect(trackFiltersBody('custom', {})).toEqual({});
	});

	it('leaves the input object unchanged', () => {
		const filters = { min_duration_seconds: null, title_indices: [1] };
		trackFiltersBody('custom', filters);
		expect(filters).toEqual({ min_duration_seconds: null, title_indices: [1] });
	});
});
