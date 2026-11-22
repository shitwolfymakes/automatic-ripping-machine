import { describe, it, expect } from 'vitest';
import { ALL_MUSIC_TAGS, MUSIC_TAG_OPTIONS } from '../music-tags';

describe('MUSIC_TAG_OPTIONS', () => {
	it("lists every tag once, in the backend's order, then the cover", () => {
		expect(ALL_MUSIC_TAGS).toEqual([
			'artist',
			'album_artist',
			'album',
			'title',
			'track_number',
			'track_total',
			'disc_number',
			'year',
			'musicbrainz_release_id',
			'cover'
		]);
	});

	it('labels each tag', () => {
		expect(MUSIC_TAG_OPTIONS.find((o) => o.value === 'musicbrainz_release_id')?.label).toBe('MusicBrainz release ID');
		expect(MUSIC_TAG_OPTIONS.every((o) => o.label.length > 0)).toBe(true);
	});
});
