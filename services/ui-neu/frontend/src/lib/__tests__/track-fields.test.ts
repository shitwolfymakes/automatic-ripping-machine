import { describe, it, expect } from 'vitest';
import { trackKindLabel, trackSizeLabel } from '../utils/track-fields';
import { createTrack } from '../components/__fixtures__/job';

describe('trackKindLabel', () => {
	it.each([
		['video_title', 'Video'],
		['audio_track', 'Audio'],
		['data_dump', 'Data']
	])('maps %s -> %s', (kind, label) => {
		expect(trackKindLabel(kind)).toBe(label);
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

	it('returns em-dash when neither is present', () => {
		const t = createTrack({ size_bytes: null, expected_size_bytes: null });
		expect(trackSizeLabel(t)).toBe('—');
	});
});
