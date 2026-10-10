import type { ConfigView } from '$lib/types/api.gen';
import { get } from './client';

export interface AppConfig {
	// Deployment fact: can this install run transcode containers at all
	// (set at install time; a ripper-only install is not capable).
	transcoder_capable: boolean;
	// Runtime toggle: Settings > Transcoding "Enable transcoding". Only
	// meaningful when transcoder_capable is true.
	transcoder_enabled: boolean;
	// Configured default metadata provider ('tmdb' | 'omdb'); null when unset.
	metadata_provider: string | null;
}

export async function fetchConfig(): Promise<AppConfig> {
	const cfg = await get<ConfigView>('/api/config');
	return {
		transcoder_capable: cfg.transcode_capable ?? true,
		transcoder_enabled: cfg.transcode_enabled ?? true,
		metadata_provider: cfg.metadata_provider ?? null
	};
}
