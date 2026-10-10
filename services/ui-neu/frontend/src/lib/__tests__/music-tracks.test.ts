import { describe, it, expect } from 'vitest';
import { extractMusicTracks } from '../utils/music-tracks';

describe('extractMusicTracks', () => {
	it('returns [] when metadata has no music section or no tracks', () => {
		expect(extractMusicTracks({})).toEqual([]);
		expect(extractMusicTracks({ music: {} })).toEqual([]);
		expect(extractMusicTracks({ music: { tracks: 'nope' } })).toEqual([]);
		expect(extractMusicTracks({ music: 'nope' })).toEqual([]);
		expect(extractMusicTracks(null)).toEqual([]);
		expect(extractMusicTracks(undefined)).toEqual([]);
	});

	it('maps title + length_ms from metadata_json.music.tracks, numbering from 1', () => {
		const out = extractMusicTracks({
			music: {
				tracks: [
					{ title: 'Intro', length_ms: 65000 },
					{ title: 'Outro', length_ms: null }
				]
			}
		});
		expect(out).toEqual([
			{ number: 1, title: 'Intro', durationLabel: '1:05' },
			{ number: 2, title: 'Outro', durationLabel: '-' }
		]);
	});

	it('falls back to a placeholder title when missing', () => {
		const out = extractMusicTracks({ music: { tracks: [{ length_ms: 1000 }] } });
		expect(out).toEqual([{ number: 1, title: 'Track 1', durationLabel: '0:01' }]);
	});

	it('renders sub-second durations as a dash, not 0:00', () => {
		const out = extractMusicTracks({ music: { tracks: [{ title: 'Blip', length_ms: 0.4 }] } });
		expect(out[0].durationLabel).toBe('-');
	});
});
