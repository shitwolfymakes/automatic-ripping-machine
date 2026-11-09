// The track-edit bodies the track title override sends: the output options and
// the title override; pure, so each rule is tested without the component.
import type { TrackEditRequest } from '$lib/types/api.gen';

export type TrackEdit = Omit<TrackEditRequest, 'track_id'>;

/**
 * The typed episode number: a number, or null when blank or not a finite
 * number.
 */
export function parseEpisodeNumber(raw: string): number | null {
	const trimmed = raw.trim();
	const n = trimmed === '' ? null : Number(trimmed);
	return Number.isFinite(n) ? n : null;
}

/**
 * The trimmed custom filename, null when blank; on a series track also the
 * episode number (null when blank or not a number) and the trimmed episode
 * name (null when blank); no episode keys otherwise.
 */
export function trackOptionsBody(
	f: { filename: string; episodeNumber: string; episodeName: string },
	isSeries: boolean
): TrackEdit {
	return {
		custom_filename: f.filename.trim() || null,
		...(isSeries && {
			episode_number: parseEpisodeNumber(f.episodeNumber),
			episode_name: f.episodeName.trim() || null
		})
	};
}

/**
 * The trimmed title; the year as a number, `undefined` when blank or not a
 * number; role `episode` for Series and `main` for Movie; the trimmed poster,
 * `undefined` when blank.
 */
export function trackTitleBody(f: {
	title: string;
	year: string;
	type: 'movie' | 'series';
	posterUrl: string;
}): TrackEdit {
	const yr = f.year.trim() ? Number(f.year.trim()) : undefined;
	const role = f.type === 'series' ? 'episode' : 'main';
	return {
		title: f.title.trim(),
		year: Number.isFinite(yr) ? yr : undefined,
		role,
		poster_url: f.posterUrl.trim() || undefined
	};
}
