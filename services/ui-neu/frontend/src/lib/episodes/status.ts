// The EPISODES row on a TV job's review card: its state, source and title counts.

import type { IdentityClaims, IdentityView, JobView, TrackView } from '$lib/types/api.gen';
import { activeSource, SOURCE_LABEL } from '$lib/episodes/sources';
import { isPostRipStatus } from '../jobs/status-groups';

/**
 * How a TV job's episode matching stands: `waiting` (no show yet), `matching`
 * (running, or no episode source has reported), `matched` (every title is
 * placed, by a source or by hand), `guess` (every title placed, but from a
 * held result) or `attention` (some titles are unplaced, or no source could
 * match and the tracks have not loaded).
 */
export type EpisodeState = 'waiting' | 'matching' | 'matched' | 'guess' | 'attention';

export interface EpisodeStatus {
	state: EpisodeState;
	/** Display name of the episode source that matched (or is matching), if known. */
	source: string | null;
	/** Selected video titles, and how many of them have no episode or role; null before the tracks load. */
	total: number | null;
	unmatched: number | null;
}

type EpisodeTrack = Pick<TrackView, 'kind' | 'excluded' | 'episode_number' | 'role'>;

/**
 * How many selected video titles there are, and how many of them are still
 * unplaced; both null before the tracks load.
 */
function countEpisodeTitles(tracks: EpisodeTrack[] | null): {
	total: number | null;
	unmatched: number | null;
} {
	const titles = tracks?.length ? tracks.filter((t) => t.kind === 'video_title' && !t.excluded) : null;
	const total = titles ? titles.length : null;
	// A title is placed once it has an episode number, or a non-episode role (extra, trailer...).
	const unmatched = titles
		? titles.filter((t) => t.episode_number == null && (t.role == null || t.role === 'episode')).length
		: null;
	return { total, unmatched };
}

/** An episode source id's display name; an unknown id shows as itself, no id as null. */
function episodeSourceLabel(id: string | null | undefined): string | null {
	return id ? (SOURCE_LABEL[id] ?? id) : null;
}

/**
 * The EPISODES row on a TV job's review card, or null for a movie or a
 * post-rip job. `tracks` (the card's detail load) adds the title counts;
 * `matching` is the card's own "re-matching now" flag.
 */
export function episodeStatus(
	job: Pick<JobView, 'status' | 'media_type' | 'has_series'> & {
		metadata_json?: JobView['metadata_json'];
		/** The resolver's word that the placement is a guess (a held result). */
		episodes_unsure?: boolean;
	},
	tracks: EpisodeTrack[] | null = null,
	matching = false
): EpisodeStatus | null {
	if (job.media_type !== 'tv' || isPostRipStatus(job.status)) return null;
	const { total, unmatched } = countEpisodeTitles(tracks);
	if (!job.has_series) return { state: 'waiting', source: null, total, unmatched };
	const claims = (job.metadata_json?.identity_claims ?? {}) as IdentityClaims;
	const sources = claims.sources ?? {};
	const episodes = Object.keys(sources).filter((id) => id.startsWith('episodes_'));
	// The card has no per-track provenance, so activeSource falls back to its
	// pin, then the first ok clean source, then the first ok held source: the
	// panel's answer unless provenance says another ok source won.
	const active = activeSource({ pin: claims.pin, sources } as unknown as IdentityView);
	if (matching) return { state: 'matching', source: episodeSourceLabel(active ?? episodes[0]), total, unmatched };
	if (active && sources[active]?.status === 'ok') {
		// Placed but from a held result: the card says so in amber and keeps Review at hand.
		const state = unmatched ? 'attention' : job.episodes_unsure ? 'guess' : 'matched';
		return { state, source: episodeSourceLabel(active), total, unmatched };
	}
	// No source placed them, but the operator may have by hand.
	if (episodes.length > 0) return { state: unmatched === 0 ? 'matched' : 'attention', source: null, total, unmatched };
	return { state: 'matching', source: null, total, unmatched };
}
