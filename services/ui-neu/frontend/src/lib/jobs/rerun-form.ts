// The Fix match form: its fields, and the match request it sends.
import type { EpisodeSource } from '$lib/api/identity';
import type { JobView, MatchRequest } from '$lib/types/api.gen';
import { EPISODE_SOURCES, shortSourceId, type EpisodeSourceOption } from '../episodes/sources';

/** The Re-run form. An empty season or disc is null (unknown); a season of
 * 'scan' asks the source to try every season. */
export interface RerunForm {
	source: 'tmdb' | 'tvmaze' | 'tvdb';
	season: number | 'scan' | null;
	disc: number | null;
	/** Empty means the backend's default. */
	tolerance: number | null;
}

/** The match request the form sends: its source, and each field the
 * operator set. A season of 'scan' asks the source to try every season. */
export function rerunRequest(form: RerunForm, apply: boolean): MatchRequest {
	const req: MatchRequest = { source: form.source, apply };
	if (form.season === 'scan') req.scan_seasons = true;
	else if (form.season != null) req.season = form.season;
	if (form.disc != null) req.disc_number = form.disc;
	if (form.tolerance != null) req.tolerance = form.tolerance;
	return req;
}

/** The form Fix match opens on: the active source when it is one of
 * EPISODE_SOURCES, else the first option that is not off (TMDb when
 * every one is); the season the source guessed, else the job's; and the
 * job's disc. */
export function fixMatchForm(
	active: string | null,
	options: EpisodeSourceOption[],
	guessedSeason: number | null,
	job: Pick<JobView, 'season' | 'disc_number'>
): RerunForm {
	const current = active ? shortSourceId(active) : null;
	const first = options.find((o) => !o.disabled)?.id ?? 'tmdb';
	return {
		source: current && EPISODE_SOURCES.includes(current) ? current : first,
		season: guessedSeason ?? job.season ?? null,
		disc: job.disc_number ?? null,
		tolerance: null
	};
}

/** The form Fill the rest previews: the picker's source, the fill season
 * and the job's disc. */
export function fillRestForm(
	source: EpisodeSource,
	job: Pick<JobView, 'season' | 'disc_number'>,
	rows: { handSet: boolean; season: number | null }[]
): RerunForm {
	return { source, season: fillSeason(job, rows), disc: job.disc_number ?? null, tolerance: null };
}

/** The season to fill in: the job's, else the one season every hand-set row
 * was saved in; null (no season sent) when they disagree or none is known. */
function fillSeason(job: Pick<JobView, 'season'>, rows: { handSet: boolean; season: number | null }[]): number | null {
	if (job.season != null) return job.season;
	const held = new Set(rows.filter((r) => r.handSet).map((r) => r.season));
	const [only] = held;
	return held.size === 1 && only != null ? only : null;
}
