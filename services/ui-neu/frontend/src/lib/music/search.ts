// The music search's request options and its active-filter count, built from
// the form's filters. Pure, so each rule is tested without the component.
import type { searchMusicMetadata } from '$lib/api/jobs';

export type MusicSearchOpts = NonNullable<Parameters<typeof searchMusicMetadata>[1]>;

export interface MusicSearchFilters {
	/** Artist, as typed. */
	artist: string;
	/** Release type, as chosen ('' when unset). */
	type: string;
	/** Release format, as chosen ('' when unset). */
	format: string;
	/** Country, as typed. */
	country: string;
	/** Release status, as chosen ('' when unset). */
	status: string;
	/** The match-track-count box. */
	matchCount: boolean;
}

/**
 * Build the options for a music search. Left out: a blank or whitespace
 * artist or country, an unset type, format or status, and track_count unless
 * the box is on and the disc has tracks. Artist and country are trimmed.
 */
export function buildSearchOpts(filters: MusicSearchFilters, discTrackCount: number): MusicSearchOpts {
	const opts: MusicSearchOpts = {};
	if (filters.artist.trim()) opts.artist = filters.artist.trim();
	if (filters.matchCount && discTrackCount > 0) opts.track_count = discTrackCount;
	if (filters.type) opts.release_type = filters.type;
	if (filters.format) opts.format = filters.format;
	if (filters.country.trim()) opts.country = filters.country.trim();
	if (filters.status) opts.status = filters.status;
	return opts;
}

/**
 * Count the active filters. The artist is not a filter here, a
 * whitespace-only country does not count, and the box counts only when the
 * disc has tracks.
 */
export function countActiveFilters(filters: MusicSearchFilters, discTrackCount: number): number {
	return [
		filters.type,
		filters.format,
		filters.country.trim(),
		filters.status,
		filters.matchCount && discTrackCount > 0 ? 'x' : ''
	].filter(Boolean).length;
}
