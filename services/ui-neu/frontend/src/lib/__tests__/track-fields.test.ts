import { describe, it, expect } from 'vitest';
import { handSetTrackCount, isSeriesTrackList, trackKindLabel, trackSizeLabel } from '../jobs/track-fields';
import { createTrack } from '../components/__fixtures__/job';

describe('trackKindLabel', () => {
	it.each([
		['video_title', 'Video'],
		['audio_track', 'Audio'],
		['data_dump', 'Data'],
		['disc_backup', 'Disc backup']
	])('maps %s -> %s', (kind, label) => {
		expect(trackKindLabel(kind)).toBe(label);
	});

	it.each([null, undefined, ''])('returns a dash for %j', (kind) => {
		expect(trackKindLabel(kind)).toBe('-');
	});

	it('passes through an unknown kind unchanged', () => {
		expect(trackKindLabel('weird_kind')).toBe('weird_kind');
	});
});

describe('trackSizeLabel', () => {
	it('formats actual size_bytes when present', () => {
		const t = createTrack({ size_bytes: 1048576, expected_size_bytes: 2097152 });
		expect(trackSizeLabel(t)).toBe('1 MB');
	});

	it('prefixes expected size with ~ when actual is null', () => {
		const t = createTrack({ size_bytes: null, expected_size_bytes: 2097152 });
		expect(trackSizeLabel(t)).toBe('~2 MB');
	});

	it('returns a dash when neither is present', () => {
		const t = createTrack({ size_bytes: null, expected_size_bytes: null });
		expect(trackSizeLabel(t)).toBe('-');
	});
});

describe('isSeriesTrackList', () => {
	it('is false for no tracks', () => {
		expect(isSeriesTrackList([], 'tv')).toBe(false);
	});

	it('is true when a track has the episode role', () => {
		expect(isSeriesTrackList([createTrack({ role: 'episode' })], 'movie')).toBe(true);
	});

	it('is true when a track has an episode number', () => {
		expect(isSeriesTrackList([createTrack({ role: 'main', episode_number: 3 })], 'movie')).toBe(true);
	});

	it('is true for a track with no role on a TV job', () => {
		expect(isSeriesTrackList([createTrack({ role: null })], 'tv')).toBe(true);
	});

	it('is false for a track with no role on a movie job', () => {
		expect(isSeriesTrackList([createTrack({ role: null })], 'movie')).toBe(false);
	});

	it('is false when every track has a non-episode role', () => {
		expect(isSeriesTrackList([createTrack({ role: 'main' }), createTrack({ role: 'extra' })], 'tv')).toBe(false);
	});
});

describe('handSetTrackCount', () => {
	it('is 0 for no tracks', () => {
		expect(handSetTrackCount([])).toBe(0);
	});

	it('counts a track whose episode number was set by hand', () => {
		const t = createTrack({ identity_provenance: { episode_number: 'manual' } });
		expect(handSetTrackCount([t])).toBe(1);
	});

	it('counts a track whose role was set by hand', () => {
		const t = createTrack({ identity_provenance: { role: 'manual' } });
		expect(handSetTrackCount([t])).toBe(1);
	});

	it('counts a track once when both fields were set by hand', () => {
		const t = createTrack({ identity_provenance: { episode_number: 'manual', role: 'manual' } });
		expect(handSetTrackCount([t])).toBe(1);
	});

	it('ignores tracks with non-manual or missing provenance', () => {
		const t = createTrack({ identity_provenance: { episode_number: 'auto', role: 'auto' } });
		expect(handSetTrackCount([t, createTrack()])).toBe(0);
	});
});
