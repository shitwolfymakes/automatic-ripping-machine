import { describe, it, expect } from 'vitest';
import { visibleTracksFor, discTotalSeconds, releaseTotalMs, pairTracks, releasePatchBody } from '$lib/music/release';
import { matchIndicator } from '$lib/jobs/track-match';

const rt = (title: string, length_ms?: number | null, disc_number?: number | null) =>
	({ title, length_ms, disc_number }) as any;
const dt = (id: string, expected_duration_seconds?: number | null) => ({ id, expected_duration_seconds }) as any;

describe('visibleTracksFor', () => {
	it('gives no tracks for no release', () => {
		expect(visibleTracksFor(null, 1)).toEqual([]);
	});

	it('gives no tracks when the release has no tracks key, with or without a scope', () => {
		expect(visibleTracksFor({ disc_count: 2 } as any, 1)).toEqual([]);
		expect(visibleTracksFor({ disc_count: 1 } as any, 1)).toEqual([]);
	});

	it('keeps only the held disc of a multi-disc release', () => {
		const tracks = [rt('a', 1, 1), rt('b', 1, 2)];
		expect(visibleTracksFor({ disc_count: 2, tracks } as any, 2)).toEqual([tracks[1]]);
	});

	it('keeps every track without a disc number', () => {
		const tracks = [rt('a', 1, 1), rt('b', 1, 2)];
		expect(visibleTracksFor({ disc_count: 2, tracks } as any, null)).toEqual(tracks);
		expect(visibleTracksFor({ disc_count: 2, tracks } as any, undefined)).toEqual(tracks);
	});

	it('keeps every track when disc_count is 1 or null', () => {
		const tracks = [rt('a', 1, 1), rt('b', 1, 2)];
		expect(visibleTracksFor({ disc_count: 1, tracks } as any, 1)).toEqual(tracks);
		expect(visibleTracksFor({ disc_count: null, tracks } as any, 1)).toEqual(tracks);
	});
});

describe('discTotalSeconds', () => {
	it('is null with no disc tracks', () => {
		expect(discTotalSeconds([])).toBeNull();
	});

	it('is null when no track has a duration', () => {
		expect(discTotalSeconds([dt('a', null), dt('b')])).toBeNull();
	});

	it('sums the durations, a missing one counting 0', () => {
		expect(discTotalSeconds([dt('a', 10), dt('b'), dt('c', 5)])).toBe(15);
	});
});

describe('releaseTotalMs', () => {
	it('is 0 for no tracks', () => {
		expect(releaseTotalMs([])).toBe(0);
	});

	it('sums the lengths, a missing one counting 0', () => {
		expect(releaseTotalMs([rt('a', 1000), rt('b'), rt('c', 500)])).toBe(1500);
	});
});

describe('pairTracks', () => {
	it('stops at the shorter disc list', () => {
		const pairs = pairTracks([dt('d1', 10)], [rt('a', 10000), rt('b', 5000)]);
		expect(pairs).toHaveLength(1);
		expect(pairs[0].mb.title).toBe('a');
	});

	it('stops at the shorter release list', () => {
		const pairs = pairTracks([dt('d1', 10), dt('d2', 10)], [rt('a', 10000)]);
		expect(pairs).toHaveLength(1);
		expect(pairs[0].disc.id).toBe('d1');
	});

	it('takes each match from the lengths', () => {
		const disc = [dt('d1', 10), dt('d2', 10), dt('d3', 10), dt('d4')];
		const mb = [rt('a', 10000), rt('b', 15000), rt('c', 60000), rt('d', 10000)];
		const pairs = pairTracks(disc, mb);
		expect(pairs.map((p) => p.match)).toEqual(
			mb.map((m, i) => matchIndicator(m.length_ms, disc[i].expected_duration_seconds))
		);
		expect(pairs.map((p) => p.match)).toEqual(['match', 'close', 'mismatch', 'unknown']);
	});
});

describe('releasePatchBody', () => {
	const pair = { disc: dt('d1'), mb: rt('Song'), match: 'unknown' } as any;

	it('is null with neither a cover nor a pair', () => {
		expect(releasePatchBody(null, [])).toBeNull();
	});

	it('saves the cover alone', () => {
		expect(releasePatchBody('http://c', [])).toEqual({ poster_url_manual: 'http://c' });
	});

	it('saves the titles alone', () => {
		expect(releasePatchBody(null, [pair])).toEqual({ tracks: [{ track_id: 'd1', title: 'Song' }] });
	});

	it('saves the cover then the titles', () => {
		const body = releasePatchBody('http://c', [pair]);
		expect(Object.keys(body!)).toEqual(['poster_url_manual', 'tracks']);
	});
});
