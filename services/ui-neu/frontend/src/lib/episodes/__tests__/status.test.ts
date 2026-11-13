import { describe, it, expect } from 'vitest';
import { episodeStatus } from '$lib/episodes/status';

describe('episodeStatus', () => {
	const tv = (over: Record<string, unknown> = {}, claims?: Record<string, { status: string }>) =>
		({
			id: 'job_1',
			status: 'awaiting_review',
			media_type: 'tv',
			has_series: true,
			metadata_json: claims ? { identity_claims: { sources: claims } } : {},
			...over
		}) as any;
	const ep = (n: number | null, over: Record<string, unknown> = {}) =>
		({ kind: 'video_title', excluded: false, episode_number: n, role: n == null ? null : 'episode', ...over }) as any;

	it('no series known waits for the show', () => {
		expect(episodeStatus(tv({ has_series: false }))).toEqual({
			state: 'waiting',
			source: null,
			total: null,
			unmatched: null
		});
	});
	it('an ok episode claim with every title placed is matched, naming its source', () => {
		const c = { episodes_tvmaze: { status: 'ok' }, episodes_tmdb: { status: 'miss' } };
		expect(episodeStatus(tv({}, c), [ep(1), ep(2), ep(null, { role: 'extra' })])).toEqual({
			state: 'matched',
			source: 'TVmaze',
			total: 3,
			unmatched: 0
		});
		expect(episodeStatus(tv({}, { episodes_tvdb: { status: 'ok' } }))?.source).toBe('TVDB');
		expect(episodeStatus(tv({}, { episodes_tmdb: { status: 'ok' } }))?.source).toBe('TMDb');
	});
	it('every title placed from a held result is a guess, not matched', () => {
		const c = { episodes_tmdb: { status: 'ok' } };
		expect(episodeStatus(tv({ episodes_unsure: true }, c), [ep(1), ep(2)])).toEqual({
			state: 'guess',
			source: 'TMDb',
			total: 2,
			unmatched: 0
		});
		// A guess with unplaced titles is attention first.
		expect(episodeStatus(tv({ episodes_unsure: true }, c), [ep(1), ep(null)])?.state).toBe('attention');
	});
	it('an ok claim with unplaced titles needs attention, counting only selected video titles', () => {
		const tracks = [ep(1), ep(null), ep(null, { excluded: true }), ep(null, { kind: 'audio_track' })];
		expect(episodeStatus(tv({}, { episodes_tmdb: { status: 'ok' } }), tracks)).toEqual({
			state: 'attention',
			source: 'TMDb',
			total: 2,
			unmatched: 1
		});
	});
	it('a pinned source wins over an earlier ok source', () => {
		const c = { episodes_tmdb: { status: 'ok' }, episodes_tvmaze: { status: 'ok' } };
		const j = tv({ metadata_json: { identity_claims: { sources: c, pin: { episode: 'episodes_tvmaze' } } } });
		expect(episodeStatus(j)?.source).toBe('TVmaze');
	});
	it('an ok non-suggestion beats an earlier ok suggestion', () => {
		const c = { episodes_tmdb: { status: 'ok', suggestion: true }, episodes_tvdb: { status: 'ok' } };
		expect(episodeStatus(tv({}, c as any))?.source).toBe('TVDB');
	});
	it('claims present but none ok needs attention', () => {
		const c = { episodes_tmdb: { status: 'miss' }, episodes_tvmaze: { status: 'error' } };
		expect(episodeStatus(tv({}, c), [ep(null), ep(null)])).toEqual({
			state: 'attention',
			source: null,
			total: 2,
			unmatched: 2
		});
		expect(episodeStatus(tv({}, c))?.state).toBe('attention');
	});
	it('claims present but none ok, with every title placed by hand, is matched', () => {
		const c = { episodes_tmdb: { status: 'miss' } };
		expect(episodeStatus(tv({}, c), [ep(1), ep(null, { role: 'extra' })])).toEqual({
			state: 'matched',
			source: null,
			total: 2,
			unmatched: 0
		});
	});
	it('no episode claims yet, or a re-match running, is matching', () => {
		expect(episodeStatus(tv())?.state).toBe('matching');
		expect(episodeStatus(tv({}, { tmdb: { status: 'ok' } }))?.state).toBe('matching');
		const running = episodeStatus(tv({}, { episodes_tmdb: { status: 'ok' } }), [ep(1), ep(null)], true);
		expect(running).toEqual({ state: 'matching', source: 'TMDb', total: 2, unmatched: 1 });
	});
	it('absent for movies and post-rip jobs', () => {
		expect(episodeStatus(tv({ media_type: 'movie' }))).toBeNull();
		expect(episodeStatus(tv({ status: 'ripped' }))).toBeNull();
		expect(episodeStatus(tv({ status: 'ripped_partial' }))).toBeNull();
	});

	it('episodeStatus of a re-match with no episode source has no source name', () => {
		const tvJob = { status: 'awaiting_review', media_type: 'tv', has_series: true, metadata_json: {} } as any;
		expect(episodeStatus(tvJob, null, true)).toEqual({ state: 'matching', source: null, total: null, unmatched: null });
	});
	it('episodeStatus of a re-match names an unknown source by its id', () => {
		const tvJob = {
			status: 'awaiting_review',
			media_type: 'tv',
			has_series: true,
			metadata_json: { identity_claims: { sources: { episodes_other: { status: 'error' } } } }
		} as any;
		expect(episodeStatus(tvJob, null, true)?.source).toBe('episodes_other');
	});
});
