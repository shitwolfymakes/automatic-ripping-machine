// v3 episode matching (design spec 2026-10-02 section 4): the identity view,
// match preview / apply, unpin, and a season's episode list for the picker.
import type { EpisodeListView, IdentityView, MatchPreview, MatchRequest, SeasonListView } from '$lib/types/api.gen';
import { del, get, post } from './client';

export type EpisodeSource = 'tmdb' | 'tvmaze' | 'tvdb';

export function fetchIdentity(jobId: string): Promise<IdentityView> {
	return get<IdentityView>(`/api/jobs/${jobId}/identity`);
}

export function matchIdentity(jobId: string, req: MatchRequest): Promise<MatchPreview> {
	return post<MatchPreview>(`/api/jobs/${jobId}/identity/match`, req);
}

export function unpinIdentity(jobId: string): Promise<IdentityView> {
	return del<IdentityView>(`/api/jobs/${jobId}/identity/pin`);
}

/** Clear episodes: forget the episode match so the placements come off the tracks. */
export function clearEpisodeMatch(jobId: string): Promise<IdentityView> {
	return del<IdentityView>(`/api/jobs/${jobId}/identity/match`);
}
export function fetchEpisodes(jobId: string, source: EpisodeSource, season: number): Promise<EpisodeListView> {
	return get<EpisodeListView>(`/api/jobs/${jobId}/identity/episodes?source=${source}&season=${season}`);
}

export function fetchSeasons(jobId: string, source: EpisodeSource): Promise<SeasonListView> {
	return get<SeasonListView>(`/api/jobs/${jobId}/identity/seasons?source=${source}`);
}
