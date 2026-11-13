import { describe, it, expect } from 'vitest';
import { matchesFilters, matchesTranscode, type ListFilters } from '../../../sessions/list-filters';

const builtin = { media_type: 'movie', is_builtin: true, name: 'Blu-ray Movie' };
const custom = { media_type: 'tv', is_builtin: false, name: 'My Show' };
const all: ListFilters = { type: 'all', source: 'all', search: '' };

describe('matchesFilters', () => {
	it('passes every item when nothing is filtered', () => {
		expect(matchesFilters(builtin, all)).toBe(true);
		expect(matchesFilters(custom, all)).toBe(true);
	});

	it('passes an item of the chosen type', () => {
		expect(matchesFilters(builtin, { ...all, type: 'movie' })).toBe(true);
	});

	it('rejects an item of another type', () => {
		expect(matchesFilters(builtin, { ...all, type: 'tv' })).toBe(false);
	});

	it('keeps only built-in items for the builtin source', () => {
		expect(matchesFilters(builtin, { ...all, source: 'builtin' })).toBe(true);
		expect(matchesFilters(custom, { ...all, source: 'builtin' })).toBe(false);
	});

	it('keeps only custom items for the custom source', () => {
		expect(matchesFilters(custom, { ...all, source: 'custom' })).toBe(true);
		expect(matchesFilters(builtin, { ...all, source: 'custom' })).toBe(false);
	});

	it('matches the name ignoring case and surrounding spaces', () => {
		expect(matchesFilters(builtin, { ...all, search: '  BLU-RAY ' })).toBe(true);
	});

	it('rejects a name that does not contain the search', () => {
		expect(matchesFilters(builtin, { ...all, search: 'dvd' })).toBe(false);
	});

	it('ignores a blank or spaces-only search', () => {
		expect(matchesFilters(builtin, { ...all, search: '' })).toBe(true);
		expect(matchesFilters(builtin, { ...all, search: '   ' })).toBe(true);
	});
});

describe('matchesTranscode', () => {
	const withPreset = { transcode_preset_id: 'abc' };
	const without = { transcode_preset_id: null };

	it('passes every session for the any filter', () => {
		expect(matchesTranscode(withPreset, 'any')).toBe(true);
		expect(matchesTranscode(without, 'any')).toBe(true);
	});

	it('keeps only sessions with a transcode preset for the has filter', () => {
		expect(matchesTranscode(withPreset, 'has')).toBe(true);
		expect(matchesTranscode(without, 'has')).toBe(false);
	});

	it('keeps only sessions without a transcode preset for the none filter', () => {
		expect(matchesTranscode(without, 'none')).toBe(true);
		expect(matchesTranscode(withPreset, 'none')).toBe(false);
	});
});
