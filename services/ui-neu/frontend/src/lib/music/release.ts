// The chosen release's tracks as the music search compares them with the disc:
// the tracks for the held disc, the two totals, the pairs for the title
// mapping, and the PATCH that saves the cover and the titles. Pure, so each
// rule is tested without the component.
import type { JobUpdateRequest, MetadataReleaseDetail, MetadataReleaseTrack, TrackView } from '$lib/types/api.gen';
import { matchIndicator, type MatchKind } from '$lib/jobs/track-match';

/** A disc track paired with the release track shown at the same position. */
export interface TrackPair {
	disc: TrackView;
	mb: MetadataReleaseTrack;
	match: MatchKind;
}

/**
 * The release's tracks. When the job knows its disc, scope a multi-disc
 * release's tracklist to it.
 */
export function visibleTracksFor(
	detail: MetadataReleaseDetail | null,
	discNumber: number | null | undefined
): MetadataReleaseTrack[] {
	return detail == null
		? []
		: detail.disc_count != null && detail.disc_count > 1 && discNumber != null
			? (detail.tracks ?? []).filter((t) => t.disc_number === discNumber)
			: (detail.tracks ?? []);
}

/** The disc tracks' summed expected duration (s), or null when none has one. */
export function discTotalSeconds(discTracks: TrackView[]): number | null {
	return discTracks.some((t) => t.expected_duration_seconds != null)
		? discTracks.reduce((sum, t) => sum + (t.expected_duration_seconds ?? 0), 0)
		: null;
}

/** The release tracks' summed length (ms); a missing length counts 0. */
export function releaseTotalMs(tracks: MetadataReleaseTrack[]): number {
	return tracks.reduce((sum, t) => sum + (t.length_ms ?? 0), 0);
}

/** Pair disc tracks with release tracks in order, each with its match kind. */
export function pairTracks(discTracks: TrackView[], releaseTracks: MetadataReleaseTrack[]): TrackPair[] {
	const n = Math.min(discTracks.length, releaseTracks.length);
	const pairs: TrackPair[] = [];
	for (let i = 0; i < n; i++) {
		const disc = discTracks[i];
		const mb = releaseTracks[i];
		pairs.push({ disc, mb, match: matchIndicator(mb.length_ms, disc.expected_duration_seconds) });
	}
	return pairs;
}

/** The PATCH body saving the cover and titles, or null when neither is there. */
export function releasePatchBody(cover: string | null, pairs: TrackPair[]): JobUpdateRequest | null {
	const trackEdits = pairs.map((p) => ({ track_id: p.disc.id, title: p.mb.title }));
	if (cover === null && trackEdits.length === 0) return null;
	return {
		...(cover !== null ? { poster_url_manual: cover } : {}),
		...(trackEdits.length > 0 ? { tracks: trackEdits } : {})
	};
}
