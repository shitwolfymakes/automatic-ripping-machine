import { describe, it, expect } from 'vitest';
import { extractMusicTracks } from '../utils/music-tracks';

describe('extractMusicTracks', () => {
	it('returns [] when metadata has no tracks', () => {
		expect(extractMusicTracks({})).toEqual([]);
		expect(extractMusicTracks({ tracks: 'nope' })).toEqual([]);
		expect(extractMusicTracks(null)).toEqual([]);
		expect(extractMusicTracks(undefined)).toEqual([]);
	});

	it('maps title + duration_ms, numbering from 1', () => {
		const out = extractMusicTracks({
			tracks: [
				{ title: 'Intro', duration_ms: 65000 },
				{ title: 'Outro', duration_ms: null }
			]
		});
		expect(out).toEqual([
			{ number: 1, title: 'Intro', durationLabel: '1:05' },
			{ number: 2, title: 'Outro', durationLabel: '-' }
		]);
	});

	it('falls back to a placeholder title when missing', () => {
		const out = extractMusicTracks({ tracks: [{ duration_ms: 1000 }] });
		expect(out).toEqual([{ number: 1, title: 'Track 1', durationLabel: '0:01' }]);
	});

	it('renders sub-second durations as a dash, not 0:00', () => {
		const out = extractMusicTracks({ tracks: [{ title: 'Blip', duration_ms: 0.4 }] });
		expect(out[0].durationLabel).toBe('-');
	});
});
