import { describe, it, expect } from 'vitest';
import { readJobMetadata, videoTypeLabel, buildMetadataFields } from './job-fields';
import { createJob } from '$lib/components/__fixtures__/job';

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

const fieldByLabel = (fields: ReturnType<typeof buildMetadataFields>, label: string) =>
	fields.find((f) => f.label === label);

describe('buildMetadataFields — promoted fields', () => {
	it('promotes Disc # with total', () => {
		const fields = buildMetadataFields(createJob({ disc_number: 1, disc_total: 2 }));
		expect(fieldByLabel(fields, 'Disc #')?.value).toBe('1 of 2');
	});

	it('promotes Disc # without total', () => {
		const fields = buildMetadataFields(createJob({ disc_number: 1, disc_total: null }));
		expect(fieldByLabel(fields, 'Disc #')?.value).toBe('1');
	});

	it('shows Poster source Manual then Auto', () => {
		expect(
			fieldByLabel(buildMetadataFields(createJob({ poster_url_manual: 'm', poster_url: 'a' })), 'Poster')?.value
		).toBe('Manual');
		expect(
			fieldByLabel(buildMetadataFields(createJob({ poster_url_manual: null, poster_url: 'a' })), 'Poster')?.value
		).toBe('Auto');
		expect(
			fieldByLabel(buildMetadataFields(createJob({ poster_url_manual: null, poster_url: null })), 'Poster')
		).toBeUndefined();
	});

	it('promotes Type / IMDb (link) / TMDB (link) / TVDB (link) / Season from metadata_json', () => {
		const fields = buildMetadataFields(
			createJob({
				metadata_json: {
					video_type: 'series',
					imdb_id: 'tt1234567',
					tmdb_id: '603',
					tvdb_id: '81189',
					season: '2'
				}
			})
		);
		expect(fieldByLabel(fields, 'Type')?.value).toBe('Series');
		expect(fieldByLabel(fields, 'IMDb')?.link).toBe('https://www.imdb.com/title/tt1234567');
		expect(fieldByLabel(fields, 'TMDB')?.link).toBe('https://www.themoviedb.org/movie/603');
		expect(fieldByLabel(fields, 'TVDB')?.link).toBe('https://www.thetvdb.com/dereferrer/series/81189');
		expect(fieldByLabel(fields, 'Season')?.value).toBe('2');
	});

	it('promotes Artist / Album', () => {
		const fields = buildMetadataFields(
			createJob({ metadata_json: { artist: 'The Beatles', album: 'Abbey Road' } })
		);
		expect(fieldByLabel(fields, 'Artist')?.value).toBe('The Beatles');
		expect(fieldByLabel(fields, 'Album')?.value).toBe('Abbey Road');
	});

	it('adds Titles count only when rip_progress is absent', () => {
		const scanned = buildMetadataFields(
			createJob({ rip_progress: null, metadata_json: { scan_result: { titles: [{}, {}, {}] } } })
		);
		expect(fieldByLabel(scanned, 'Titles')?.value).toBe('3');

		const ripping = buildMetadataFields(
			createJob({
				rip_progress: { tracks_done: 1, tracks_total: 3, tracks_failed: 0, current_track_id: null, current_track_index: null },
				metadata_json: { scan_result: { titles: [{}, {}, {}] } }
			})
		);
		// Base "Tracks" cell is authoritative; "Titles" not added.
		expect(fieldByLabel(ripping, 'Titles')).toBeUndefined();
		expect(fieldByLabel(ripping, 'Tracks')?.value).toBe('1 / 3');
	});

	it('promotes nothing extra for a bare job (only base cells, padded)', () => {
		const fields = buildMetadataFields(createJob({ metadata_json: {} }));
		for (const label of ['Disc #', 'Poster', 'Type', 'IMDb', 'TMDB', 'TVDB', 'Season', 'Artist', 'Album', 'Titles']) {
			expect(fieldByLabel(fields, label)).toBeUndefined();
		}
		// Length is a multiple of 4 (pad preserved).
		expect(fields.length % 4).toBe(0);
	});
});

