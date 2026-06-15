import type { ConfigView } from '$lib/types/api.gen';
import { get } from './client';

// v3 exposes GET /api/config -> ConfigView. The BFF's flat AppConfig with a
// dedicated `transcoder_enabled` flag is gone; v3's nearest equivalent is
// `auto_transcode_on_idle`. We project ConfigView down to the single boolean
// the config store still consumes, defaulting to enabled when absent.
export interface AppConfig {
	transcoder_enabled: boolean;
}

export async function fetchConfig(): Promise<AppConfig> {
	const cfg = await get<ConfigView>('/api/config');
	return { transcoder_enabled: cfg.auto_transcode_on_idle ?? true };
}
