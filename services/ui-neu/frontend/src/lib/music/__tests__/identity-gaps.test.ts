import { describe, it, expect } from 'vitest';
import { cdIdentityMissing } from '../identity-gaps';

describe('cdIdentityMissing', () => {
	it.each([
		[{ album: true, artist: false, untitled_tracks: [] }, 'the album'],
		[{ album: false, artist: true, untitled_tracks: [] }, 'the artist'],
		[{ album: false, artist: false, untitled_tracks: [4] }, 'the title of track 4'],
		[{ album: false, artist: false, untitled_tracks: [1, 3] }, 'titles for tracks 1 and 3'],
		[
			{ album: true, artist: true, untitled_tracks: [1, 2, 3] },
			'the album, the artist and titles for tracks 1, 2 and 3'
		]
	])('lists what is missing (%j)', (gaps, text) => {
		expect(cdIdentityMissing(gaps)).toBe(text);
	});
});
