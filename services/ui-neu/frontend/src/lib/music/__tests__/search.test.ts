import { describe, it, expect } from 'vitest';
import { buildSearchOpts, countActiveFilters, type MusicSearchFilters } from '../search';

const none: MusicSearchFilters = {
	artist: '',
	type: '',
	format: '',
	country: '',
	status: '',
	matchCount: false
};
const f = (over: Partial<MusicSearchFilters>): MusicSearchFilters => ({ ...none, ...over });

describe('buildSearchOpts', () => {
	it('gives no keys when no filter is set', () => {
		expect(buildSearchOpts(none, 0)).toEqual({});
		expect(buildSearchOpts(none, 12)).toEqual({});
	});

	it('maps each filter to its key alone', () => {
		expect(buildSearchOpts(f({ artist: 'Bjork' }), 0)).toEqual({ artist: 'Bjork' });
		expect(buildSearchOpts(f({ type: 'album' }), 0)).toEqual({ release_type: 'album' });
		expect(buildSearchOpts(f({ format: 'CD' }), 0)).toEqual({ format: 'CD' });
		expect(buildSearchOpts(f({ country: 'GB' }), 0)).toEqual({ country: 'GB' });
		expect(buildSearchOpts(f({ status: 'official' }), 0)).toEqual({ status: 'official' });
	});

	it('trims the artist and the country', () => {
		expect(buildSearchOpts(f({ artist: '  Bjork ', country: ' GB  ' }), 0)).toEqual({
			artist: 'Bjork',
			country: 'GB'
		});
	});

	it('leaves out a whitespace artist and country', () => {
		expect(buildSearchOpts(f({ artist: '   ', country: ' \t' }), 0)).toEqual({});
	});

	it('adds track_count only with the box on and disc tracks', () => {
		expect(buildSearchOpts(f({ matchCount: true }), 9)).toEqual({ track_count: 9 });
		expect(buildSearchOpts(f({ matchCount: true }), 0)).toEqual({});
		expect(buildSearchOpts(f({ matchCount: false }), 9)).toEqual({});
	});

	it('keeps the key order with every filter set', () => {
		const opts = buildSearchOpts(
			{ artist: 'A', type: 'album', format: 'CD', country: 'GB', status: 'official', matchCount: true },
			9
		);
		expect(Object.keys(opts)).toEqual(['artist', 'track_count', 'release_type', 'format', 'country', 'status']);
	});
});

describe('countActiveFilters', () => {
	it('is 0 with nothing set', () => {
		expect(countActiveFilters(none, 0)).toBe(0);
	});

	it('counts each filter alone as 1', () => {
		expect(countActiveFilters(f({ type: 'album' }), 0)).toBe(1);
		expect(countActiveFilters(f({ format: 'CD' }), 0)).toBe(1);
		expect(countActiveFilters(f({ country: 'GB' }), 0)).toBe(1);
		expect(countActiveFilters(f({ status: 'official' }), 0)).toBe(1);
		expect(countActiveFilters(f({ matchCount: true }), 9)).toBe(1);
	});

	it('does not count a whitespace country', () => {
		expect(countActiveFilters(f({ country: '   ' }), 0)).toBe(0);
	});

	it('counts the box only when the disc has tracks', () => {
		expect(countActiveFilters(f({ matchCount: true }), 0)).toBe(0);
	});

	it('never counts the artist', () => {
		expect(countActiveFilters(f({ artist: 'Bjork' }), 9)).toBe(0);
	});

	it('gives 5 with all five filters set', () => {
		expect(
			countActiveFilters(
				{ artist: 'A', type: 'album', format: 'CD', country: 'GB', status: 'official', matchCount: true },
				9
			)
		).toBe(5);
	});
});
