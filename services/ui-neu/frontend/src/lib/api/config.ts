import type { ConfigView } from '$lib/types/api.gen';
import { apiFetch, get } from './client';

interface AppConfig {
	// Deployment fact: can this install run transcode containers at all
	// (set at install time; a ripper-only install is not capable).
	transcoder_capable: boolean;
	// Runtime toggle: Settings > Transcoding "Enable transcoding". Only
	// meaningful when transcoder_capable is true.
	transcoder_enabled: boolean;
	// The job page's search provider per media type; null when unset.
	search_provider_movie: string | null;
	search_provider_tv: string | null;
	// Whether each keyed provider has a saved API key (the config view masks
	// a saved secret as '<hidden>').
	tmdb_keyed: boolean;
	omdb_keyed: boolean;
	tvdb_keyed: boolean;
}

/** The config view's stand-in for a saved secret (the backend's HIDDEN_SECRET). */
export const HIDDEN_SECRET = '<hidden>';

export async function fetchConfig(): Promise<AppConfig> {
	const cfg = await get<ConfigView>('/api/config');
	return {
		transcoder_capable: cfg.transcode_capable ?? true,
		transcoder_enabled: cfg.transcode_enabled ?? true,
		search_provider_movie: cfg.search_provider_movie ?? null,
		search_provider_tv: cfg.search_provider_tv ?? null,
		tmdb_keyed: cfg.tmdb_api_key === HIDDEN_SECRET,
		omdb_keyed: cfg.omdb_api_key === HIDDEN_SECRET,
		tvdb_keyed: cfg.tvdb_api_key === HIDDEN_SECRET
	};
}

/** The full config view (secrets masked as '<hidden>'). Read-only. */
export function fetchConfigView(): Promise<ConfigView> {
	return get<ConfigView>('/api/config');
}

// The Pause toggle means "hold discs for review": pausing lets discs scan +
// identify and then parks each in AWAITING_REVIEW indefinitely. The backend
// only PARKS (rather than rejecting with 409) when BOTH ripping_paused AND
// hold_for_review are set — see ripper.py identify(). Un-pausing clears both
// and resumes straight-through ripping; config.py gives held discs a fresh
// countdown on the ripping_paused ON->OFF transition so they don't stampede.
export function setRippingEnabled(enabled: boolean): Promise<ConfigView> {
	return apiFetch<ConfigView>('/api/config', {
		method: 'PATCH',
		body: JSON.stringify({ ripping_paused: !enabled, hold_for_review: !enabled })
	});
}
