// The tags a music session can write into each encoded track, with the
// labels the session builder shows. The values are the backend's
// MusicTagField: a Record over that type fails to compile when the
// backend adds one without a label here.
import type { MusicTagField } from '$lib/types/api.gen';

const LABELS: Record<MusicTagField, string> = {
	artist: 'Artist',
	album_artist: 'Album artist',
	album: 'Album',
	title: 'Track title',
	track_number: 'Track number',
	track_total: 'Track total',
	disc_number: 'Disc number',
	year: 'Year',
	musicbrainz_release_id: 'MusicBrainz release ID',
	cover: 'Cover art'
};

/** Every tag, in the backend's order, with its label. */
export const MUSIC_TAG_OPTIONS: readonly { value: MusicTagField; label: string }[] = (
	Object.keys(LABELS) as MusicTagField[]
).map((value) => ({ value, label: LABELS[value] }));

/** Every tag switched on: what a new music session writes. */
export const ALL_MUSIC_TAGS: readonly MusicTagField[] = MUSIC_TAG_OPTIONS.map((o) => o.value);
