// The Fix match form: its fields, and the match request it sends.
import type { MatchRequest } from '$lib/types/api.gen';

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
