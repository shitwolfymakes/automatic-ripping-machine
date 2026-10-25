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
}

export async function fetchConfig(): Promise<AppConfig> {
	const cfg = await get<ConfigView>('/api/config');
	return {
		transcoder_capable: cfg.transcode_capable ?? true,
		transcoder_enabled: cfg.transcode_enabled ?? true,
		search_provider_movie: cfg.search_provider_movie ?? null,
		search_provider_tv: cfg.search_provider_tv ?? null
	};
}

/** The full config view (secrets masked as '<hidden>'). Read-only. */
export function fetchConfigView(): Promise<ConfigView> {
	return get<ConfigView>('/api/config');
}
