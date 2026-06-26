import { describe, it, expect } from 'vitest';
import { readJobMetadata, videoTypeLabel } from './job-fields';

describe('readJobMetadata', () => {
	it('returns empty object fields for an empty blob', () => {
		expect(readJobMetadata({})).toEqual({});
	});

	it('returns empty for null/undefined without throwing', () => {
		expect(readJobMetadata(null)).toEqual({});
		expect(readJobMetadata(undefined)).toEqual({});
	});

	it('reads well-formed known scalars', () => {
		const md = {
			imdb_id: 'tt1234567',
			tmdb_id: '603',
			tvdb_id: '81189',
			video_type: 'series',
			season: '2',
			artist: 'The Beatles',
			album: 'Abbey Road',
			multi_title: true,
			source_type: 'iso'
		};
		expect(readJobMetadata(md)).toEqual({
			imdb_id: 'tt1234567',
			tmdb_id: '603',
			tvdb_id: '81189',
			video_type: 'series',
			season: '2',
			artist: 'The Beatles',
			album: 'Abbey Road',
			multi_title: true,
			source_type: 'iso'
		});
	});

	it('coerces numeric ids/season to strings', () => {
		expect(readJobMetadata({ tmdb_id: 603, season: 2 })).toEqual({
			tmdb_id: '603',
			season: '2'
		});
	});

	it('ignores malformed (non-scalar) known keys', () => {
		expect(readJobMetadata({ imdb_id: { nested: 1 }, video_type: ['a'] })).toEqual({});
	});

	it('derives titleCount from scan_result.titles length', () => {
		expect(
			readJobMetadata({ scan_result: { titles: [{ index: 0 }, { index: 1 }] } })
		).toEqual({ titleCount: 2 });
	});

	it('omits titleCount when scan_result has no titles array', () => {
		expect(readJobMetadata({ scan_result: { raw: {} } })).toEqual({});
	});
});

describe('videoTypeLabel', () => {
	it('maps known types', () => {
		expect(videoTypeLabel('movie')).toBe('Movie');
		expect(videoTypeLabel('series')).toBe('Series');
		expect(videoTypeLabel('music')).toBe('Music');
		expect(videoTypeLabel('data')).toBe('Data');
	});
	it('passes through unknown and falls back for empty', () => {
		expect(videoTypeLabel('anime')).toBe('anime');
		expect(videoTypeLabel(null)).toBe('Unknown');
	});
});
