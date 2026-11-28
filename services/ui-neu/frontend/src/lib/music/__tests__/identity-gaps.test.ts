import { describe, it, expect } from 'vitest';
import { cdIdentityMissing } from '../identity-gaps';

describe('cdIdentityMissing', () => {
	it.each([
		[{ album: true, artist: false }, 'the album'],
		[{ album: false, artist: true }, 'the artist'],
		[{ album: true, artist: true }, 'the album and the artist']
	])('lists what is missing (%j)', (gaps, text) => {
		expect(cdIdentityMissing(gaps)).toBe(text);
	});
});
