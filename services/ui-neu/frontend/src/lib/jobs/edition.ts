// Naming a version of the film: which tracks take an edition name, and the edit body the name saves as.
import type { TrackEditRequest, TrackView } from '$lib/types/api.gen';

const VERSION_CLASSES = new Set(['edition', 'angle', 'subset', 'variant', 'view']);

/** A title that is one version of a film the disc holds more than once: an alternate, an edition, or the pick the alternates point at. */
export function canNameVersion(track: TrackView, tracks: readonly TrackView[]): boolean {
	if (track.edition) return true;
	if (track.title_class && VERSION_CLASSES.has(track.title_class)) return true;
	return tracks.some(
		(t) => t.title_class_ref === track.source_ref && t.title_class && VERSION_CLASSES.has(t.title_class)
	);
}

/** The edit a typed name saves as: the trimmed name, or a revert when it is blank. */
export function editionEdit(raw: string): Omit<TrackEditRequest, 'track_id'> {
	const name = raw.trim();
	return name ? { edition: name } : { revert_fields: ['edition'] };
}
