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

describe('readJobMetadata — pending_session_id', () => {
	it('reads a string pending_session_id', () => {
		expect(readJobMetadata({ pending_session_id: 'sess_01ABC' }).pending_session_id).toBe('sess_01ABC');
	});
	it('omits pending_session_id when absent', () => {
		expect(readJobMetadata({}).pending_session_id).toBeUndefined();
	});
	it('ignores a non-string pending_session_id', () => {
		expect(readJobMetadata({ pending_session_id: { x: 1 } }).pending_session_id).toBeUndefined();
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


describe('readJobMetadata typed sections (step 2 §3.4)', () => {
	it('prefers identity/provider_raw/music over legacy top-level keys', () => {
		const out = readJobMetadata({
			identity: { provider: 'tmdb', external_ids: { imdb: 'tt0371746', tmdb: '1726' } },
			provider_raw: { arm_server: { video_type: 'movie', multi_title: true, source_type: 'dvd' } },
			music: { artist: 'The Beatles', album: 'Abbey Road' },
			imdb_id: 'tt-stale',
			video_type: 'series',
			artist: 'Stale Artist'
		});
		expect(out.imdb_id).toBe('tt0371746');
		expect(out.tmdb_id).toBe('1726');
		expect(out.video_type).toBe('movie');
		expect(out.multi_title).toBe(true);
		expect(out.source_type).toBe('dvd');
		expect(out.artist).toBe('The Beatles');
		expect(out.album).toBe('Abbey Road');
	});

	it('still reads pre-migration rows via the legacy keys', () => {
		const out = readJobMetadata({ imdb_id: 'tt123', video_type: 'series', artist: 'A' });
		expect(out.imdb_id).toBe('tt123');
		expect(out.video_type).toBe('series');
		expect(out.artist).toBe('A');
	});

	it('prefers the job columns for season and pending session', () => {
		const out = readJobMetadata(
			{ season: '09', pending_session_id: 'ses_old' },
			{ season: 3, pending_session_id: 'ses_col' } as never
		);
		expect(out.season).toBe('03');
		expect(out.pending_session_id).toBe('ses_col');
	});
});
