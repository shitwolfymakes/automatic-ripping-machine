import type { ConfigView } from '$lib/types/api.gen';
import { get } from './client';

export interface AppConfig {
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

const HIDDEN = '<hidden>';

export async function fetchConfig(): Promise<AppConfig> {
	const cfg = await get<ConfigView>('/api/config');
	return {
		transcoder_capable: cfg.transcode_capable ?? true,
		transcoder_enabled: cfg.transcode_enabled ?? true,
		search_provider_movie: cfg.search_provider_movie ?? null,
		search_provider_tv: cfg.search_provider_tv ?? null,
		tmdb_keyed: cfg.tmdb_api_key === HIDDEN,
		omdb_keyed: cfg.omdb_api_key === HIDDEN,
		tvdb_keyed: cfg.tvdb_api_key === HIDDEN
	};
}

/** The full config view (secrets masked as '<hidden>'). Read-only. */
export function fetchConfigView(): Promise<ConfigView> {
	return get<ConfigView>('/api/config');
}
