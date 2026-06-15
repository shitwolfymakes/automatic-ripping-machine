import type { ConfigView } from '$lib/types/api.gen';
import { get } from './client';

// v3 exposes GET /api/config -> ConfigView. The config store still consumes a
// single `transcoder_enabled` boolean that gates the Transcoder nav item. In v3
// the transcoder subsystem is ALWAYS present — the old BFF could disable the
// whole subsystem, v3 cannot — so this flag stays true. (Do not derive it from
// `auto_transcode_on_idle`: that's an auto-transcode-when-idle policy, not a
// subsystem-availability feature flag.)
export interface AppConfig {
	transcoder_enabled: boolean;
}

export async function fetchConfig(): Promise<AppConfig> {
	await get<ConfigView>('/api/config');
	return { transcoder_enabled: true };
}
