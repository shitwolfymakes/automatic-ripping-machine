// Settings domain, repointed BFF -> v3.
//
// v3 has NO single aggregated "/api/settings" envelope. The settings screen is
// composed client-side from three v3 reads (GET /api/config + the settings
// schema + the infra dict) into the local `SettingsData` shape the page
// consumes.
//
// Function names are kept stable so consumers compile; return shapes are
// adapted to v3 and retyped at the call sites.
import type {
	ConfigView,
	ConfigUpdateRequest,
	SettingsSchemaResponse,
	KeyCheckResponse,
	TranscodePresetView,
	TranscodePresetCreateRequest
} from '$lib/types/api.gen';
import { get, post, patch } from './client';

// ---------------------------------------------------------------------------
// Aggregated settings — composed client-side (the BFF's single envelope is gone)
// ---------------------------------------------------------------------------

// GET /api/settings/infra is an untyped dict in v3 — model only what the page
// touches as a thin local interface.
export interface InfraInfo {
	[key: string]: unknown;
}

// The composed shape the settings page consumes. v3 has no SettingsResponse
// type; we fan three reads into this. `arm_config` / `transcoder_config` /
// `naming_variables` preserve the BFF-era panel shapes the page renders from
// — none exist on the v3 wire, so they are best-effort projections.
export interface SettingsData {
	config: ConfigView;
	schema: SettingsSchemaResponse;
	infra: InfraInfo;
	arm_config: Record<string, string | null>;
	transcoder_config?: {
		config?: Record<string, unknown>;
		paths?: Record<string, unknown>;
		valid_log_levels?: string[];
		updatable_keys?: string[];
	} | null;
	naming_variables?: Record<string, string> | null;
	// Optional BFF-era panels the settings page renders behind {#if} guards.
	// None are populated under v3 (no aggregating endpoint); typed so the page
	// compiles and the panels stay hidden.
	arm_metadata?: Record<string, unknown> | null;
	transcoder_auth_status?: {
		require_api_auth: boolean;
		webhook_secret_configured: boolean;
	} | null;
	arm_ui_webhook_secret_configured?: boolean | null;
	transcoder_gpu_support?: Record<string, boolean> | null;
}

export async function fetchSettings(): Promise<SettingsData> {
	const [config, schema, infra] = await Promise.all([
		get<ConfigView>('/api/config'),
		get<SettingsSchemaResponse>('/api/settings/schema'),
		get<InfraInfo>('/api/settings/infra')
	]);
	return {
		config,
		schema,
		infra,
		// v3 config is a flat typed row, not the BFF's stringly-typed ARM_* map.
		// The page reads arm_config for legacy panels; expose the config row as a
		// loose string map so those controls render without a BFF envelope.
		arm_config: Object.fromEntries(
			Object.entries(config as Record<string, unknown>).map(([k, v]) => [k, v == null ? null : String(v)])
		),
		transcoder_config: null,
		naming_variables: null
	};
}

// PATCH /api/config — v3 returns the updated ConfigView. The BFF returned
// { success, warning }; adapt to that envelope so the consumer's feedback path
// keeps working (a successful PATCH is { success: true }).
export async function saveArmConfig(config: ConfigUpdateRequest): Promise<{ success: boolean; warning?: string }> {
	await patch<ConfigView>('/api/config', config);
	return { success: true };
}

// ---------------------------------------------------------------------------
// Per-key API key check (POST /api/config/keys/{name}/check): probes one
// provider's key, optionally an unsaved candidate value, and returns the
// tri-state KeyCheckResponse (ok/invalid/missing/error/unknown) that
// SchemaConfigForm renders.
// ---------------------------------------------------------------------------
export function checkApiKey(name: 'tmdb' | 'omdb' | 'tvdb' | 'makemkv', value?: string): Promise<KeyCheckResponse> {
	return post<KeyCheckResponse>(`/api/config/keys/${name}/check`, { value });
}

// ---------------------------------------------------------------------------
// Transcode presets — EXISTS in v3 (CRUD under /api/transcode-presets).
// ---------------------------------------------------------------------------
export function fetchTranscoderPresets(): Promise<TranscodePresetView[]> {
	return get<TranscodePresetView[]>('/api/transcode-presets');
}

export function createCustomPreset(body: TranscodePresetCreateRequest): Promise<TranscodePresetView> {
	return post<TranscodePresetView>('/api/transcode-presets', body);
}
