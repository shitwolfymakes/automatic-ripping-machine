// The tags a music session can write into each encoded track, and the
// cover sizes it can embed, with the labels the session builder shows. The
// values are the backend's MusicTagField and MusicCoverSize: a Record over
// either type fails to compile when the backend adds one without a label here.
import type { MusicCoverSize, MusicTagField } from '$lib/types/api.gen';

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

const COVER_SIZE_LABELS: Record<MusicCoverSize, string> = {
	'250': '250 px',
	'500': '500 px',
	'1200': '1200 px',
	source: 'Original upload'
};

/** Every cover size, smallest first, with its label. */
export const COVER_SIZE_OPTIONS: readonly { value: MusicCoverSize; label: string }[] = (
	Object.keys(COVER_SIZE_LABELS) as MusicCoverSize[]
).map((value) => ({ value, label: COVER_SIZE_LABELS[value] }));

/** What a new music session embeds: the size ARM used before it was a choice. */
export const DEFAULT_COVER_SIZE: MusicCoverSize = '500';
