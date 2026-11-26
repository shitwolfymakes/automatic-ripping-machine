import { describe, it, expect } from 'vitest';
import { readJobMetadata } from '../metadata';

describe('readJobMetadata', () => {
	it('returns empty object fields for an empty blob', () => {
		expect(readJobMetadata({})).toEqual({});
	});

	it('returns empty for null/undefined without throwing', () => {
		expect(readJobMetadata(null)).toEqual({});
		expect(readJobMetadata(undefined)).toEqual({});
	});

	it('reads well-formed known scalars from typed sections', () => {
		const md = {
			identity: { provider: 'tmdb', external_ids: { imdb: 'tt1234567', tmdb: '603', tvdb: '81189' } },
			provider_raw: { arm_server: { video_type: 'series', multi_title: true, source_type: 'iso' } },
			music: { artist: 'The Beatles', album: 'Abbey Road' }
		};
		expect(readJobMetadata(md)).toEqual({
			imdb_id: 'tt1234567',
			tmdb_id: '603',
			tvdb_id: '81189',
			video_type: 'series',
			artist: 'The Beatles',
			album: 'Abbey Road',
			multi_title: true,
			source_type: 'iso'
		});
	});

	it('coerces a numeric tmdb id to a string', () => {
		expect(readJobMetadata({ identity: { provider: 'tmdb', external_ids: { tmdb: 603 } } })).toEqual({
			tmdb_id: '603'
		});
	});

	it('ignores malformed (non-scalar) known keys', () => {
		expect(
			readJobMetadata({
				identity: { provider: 'tmdb', external_ids: { imdb: { nested: 1 } } },
				provider_raw: { arm_server: { video_type: ['a'] } }
			})
		).toEqual({});
	});

	it('derives titleCount from scan_result.titles length', () => {
		expect(readJobMetadata({ scan_result: { titles: [{ index: 0 }, { index: 1 }] } })).toEqual({ titleCount: 2 });
	});

	it('omits titleCount when scan_result has no titles array', () => {
		expect(readJobMetadata({ scan_result: { raw: {} } })).toEqual({});
	});
});

describe('readJobMetadata — pending_session_id', () => {
	it('reads pending_session_id from the job column', () => {
		expect(readJobMetadata({}, { season: null, pending_session_id: 'sess_01ABC' } as never).pending_session_id).toBe(
			'sess_01ABC'
		);
	});
	it('omits pending_session_id when absent', () => {
		expect(readJobMetadata({}).pending_session_id).toBeUndefined();
	});
});

describe('readJobMetadata typed sections', () => {
	it('reads external ids / video_type / multi_title / source_type / music from the typed sections', () => {
		const out = readJobMetadata({
			identity: { provider: 'tmdb', external_ids: { imdb: 'tt0371746', tmdb: '1726' } },
			provider_raw: { arm_server: { video_type: 'movie', multi_title: true, source_type: 'dvd' } },
			music: { artist: 'The Beatles', album: 'Abbey Road' }
		});
		expect(out.imdb_id).toBe('tt0371746');
		expect(out.tmdb_id).toBe('1726');
		expect(out.video_type).toBe('movie');
		expect(out.multi_title).toBe(true);
		expect(out.source_type).toBe('dvd');
		expect(out.artist).toBe('The Beatles');
		expect(out.album).toBe('Abbey Road');
	});

	it('reads season and pending_session_id only from the job columns', () => {
		const out = readJobMetadata({}, { season: 3, pending_session_id: 'ses_col' } as never);
		expect(out.season).toBe('03');
		expect(out.pending_session_id).toBe('ses_col');
	});
});

describe('readJobMetadata — video_type falls back to job.media_type', () => {
	it('maps media_type "tv" to "series" when arm_server has no video_type', () => {
		const out = readJobMetadata({}, { media_type: 'tv' } as never);
		expect(out.video_type).toBe('series');
	});

	it('uses media_type as-is for movie/music/data', () => {
		expect(readJobMetadata({}, { media_type: 'movie' } as never).video_type).toBe('movie');
		expect(readJobMetadata({}, { media_type: 'music' } as never).video_type).toBe('music');
		expect(readJobMetadata({}, { media_type: 'data' } as never).video_type).toBe('data');
	});

	it('prefers the job.media_type column over a stale provider_raw.arm_server.video_type', () => {
		const out = readJobMetadata({ provider_raw: { arm_server: { video_type: 'movie' } } }, {
			media_type: 'tv'
		} as never);
		expect(out.video_type).toBe('series');
	});

	it('reads video_type, multi_title and source_type from provider_raw.legacy on pre-section rows', () => {
		const out = readJobMetadata(
			{ provider_raw: { legacy: { video_type: 'series', multi_title: true, source_type: 'dvd' } } },
			{ media_type: null } as never
		);
		expect(out.video_type).toBe('series');
		expect(out.multi_title).toBe(true);
		expect(out.source_type).toBe('dvd');
	});

	it('prefers provider_raw.arm_server over provider_raw.legacy', () => {
		const out = readJobMetadata({
			provider_raw: { arm_server: { source_type: 'iso' }, legacy: { source_type: 'dvd' } }
		});
		expect(out.source_type).toBe('iso');
	});

	it('omits video_type when neither source has a value', () => {
		expect(readJobMetadata({}, { media_type: null } as never).video_type).toBeUndefined();
		expect(readJobMetadata({}).video_type).toBeUndefined();
	});
});
