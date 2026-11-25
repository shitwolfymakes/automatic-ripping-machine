import { describe, it, expect } from 'vitest';
import {
	ALL_MUSIC_TAGS,
	COVER_MAX_SIZE_OPTIONS,
	COVER_SIZE_OPTIONS,
	DEFAULT_COVER_MAX_SIZE,
	DEFAULT_COVER_SIZE,
	MUSIC_TAG_OPTIONS
} from '../music-tags';

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

describe('COVER_SIZE_OPTIONS', () => {
	it('lists the sizes smallest first, then the original upload', () => {
		expect(COVER_SIZE_OPTIONS).toEqual([
			{ value: '250', label: '250 px' },
			{ value: '500', label: '500 px' },
			{ value: '1200', label: '1200 px' },
			{ value: 'source', label: 'Original upload' }
		]);
	});

	it('starts a new session at 500 px, the size used before it was a choice', () => {
		expect(DEFAULT_COVER_SIZE).toBe('500');
	});
});

describe('COVER_MAX_SIZE_OPTIONS', () => {
	it('lists the limits smallest first, then no limit', () => {
		expect(COVER_MAX_SIZE_OPTIONS).toEqual([
			{ value: '500kb', label: '500 KB' },
			{ value: '1mb', label: '1 MB' },
			{ value: '2mb', label: '2 MB' },
			{ value: '5mb', label: '5 MB' },
			{ value: '10mb', label: '10 MB' },
			{ value: 'unlimited', label: 'Unlimited' }
		]);
	});

	it('starts a new session at 2 MB, the limit every cover had before it was a choice', () => {
		expect(DEFAULT_COVER_MAX_SIZE).toBe('2mb');
	});
});
