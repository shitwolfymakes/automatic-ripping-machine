// Settings domain, repointed BFF -> v3.
//
// v3 has NO single aggregated "/api/settings" envelope. The settings screen is
// composed client-side from three v3 reads (GET /api/config + the settings
// schema + the infra dict) into the local `SettingsData` shape the page
// consumes. Several BFF concerns (the transcoder service config, abcde.conf,
// transcoder connection/webhook/scheme probes, the system-info aggregation)
// have NO v3 endpoint and are stubbed via `notAvailable` — the screens that
// reach them are transcoder-gated and/or feature-flagged off.
//
// Function names are kept stable so consumers compile; return shapes are
// adapted to v3 and retyped at the call sites.
import type {
	ConfigView,
	ConfigUpdateRequest,
	SettingsSchemaResponse,
	MetadataKeyTestResponse,
	TranscodePresetView,
	TranscodePresetCreateRequest
} from '$lib/types/api.gen';
import type { Scheme, Preset, Overrides } from '$lib/types/presets';
import { get, post, patch } from './client';
import { notAvailable } from './_stub';

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
			Object.entries(config as Record<string, unknown>).map(([k, v]) => [
				k,
				v == null ? null : String(v)
			])
		),
		transcoder_config: null,
		naming_variables: null
	};
}

// PATCH /api/config — v3 returns the updated ConfigView. The BFF returned
// { success, warning }; adapt to that envelope so the consumer's feedback path
// keeps working (a successful PATCH is { success: true }).
export async function saveArmConfig(
	config: ConfigUpdateRequest
): Promise<{ success: boolean; warning?: string }> {
	await patch<ConfigView>('/api/config', config);
	return { success: true };
}

// ---------------------------------------------------------------------------
// Metadata key test — EXISTS in v3 (GET /api/metadata/test-key).
// v3 tests the STORED key for a provider; it takes only `provider` (no inline
// key). The `key` arg is kept in the signature for call-site stability but is
// not sent. The BFF returned { success, message, provider }; adapt the v3
// MetadataKeyTestResponse ({ provider, valid, detail }) to that shape.
// ---------------------------------------------------------------------------
export async function testMetadataKey(
	_key?: string,
	provider?: string
): Promise<{ success: boolean; message: string; provider: string }> {
	const prov = provider ?? '';
	const res = await get<MetadataKeyTestResponse>(`/api/metadata/test-key?provider=${encodeURIComponent(prov)}`);
	return {
		success: res.valid === true,
		message: res.detail ?? (res.valid ? 'Key is valid' : 'Key is invalid'),
		provider: res.provider
	};
}

// ---------------------------------------------------------------------------
// Transcode presets — EXISTS in v3 (CRUD under /api/transcode-presets).
// NOTE: v3's TranscodePresetView is a FLAT shape (id/name/media_type/tool/...),
// unrelated to the BFF's scheme-driven Preset (slug/shared/tiers). The
// scheme-driven PresetEditor cannot be fed from these directly; its scheme
// half is MISSING (see fetchTranscoderScheme), so the editor renders offline.
// We still wire the list/create to the real v3 endpoints.
// ---------------------------------------------------------------------------
export function fetchTranscoderPresets(): Promise<TranscodePresetView[]> {
	return get<TranscodePresetView[]>('/api/transcode-presets');
}

export function createCustomPreset(body: TranscodePresetCreateRequest): Promise<TranscodePresetView> {
	return post<TranscodePresetView>('/api/transcode-presets', body);
}

// ---------------------------------------------------------------------------
// MISSING in v3 — no endpoint. Stubbed; reachable screens are transcoder-gated
// or feature-flagged off. Async form rejects before any fetch.
// ---------------------------------------------------------------------------

export interface ConnectionTestResult {
	reachable: boolean;
	auth_ok: boolean;
	auth_required: boolean;
	gpu_support: Record<string, boolean> | null;
	worker_running: boolean;
	queue_size: number;
	error: string | null;
}

export interface WebhookTestResult {
	reachable: boolean;
	secret_ok: boolean;
	secret_required: boolean;
	error: string | null;
}

export interface SystemInfoData {
	versions: Record<string, string>;
	endpoints: Record<string, { url: string; reachable: boolean }>;
	paths: Array<{ setting: string; path: string; exists: boolean; writable: boolean }>;
	database: {
		path: string | null;
		size_bytes: number | null;
		available: boolean;
		migration_current: string | null;
		migration_head: string | null;
		up_to_date: boolean | null;
	};
	drives: Array<{
		name: string | null;
		mount: string | null;
		maker: string | null;
		model: string | null;
		capabilities: string[];
		firmware: string | null;
	}>;
}

export interface AbcdeConfigData {
	content: string;
	path: string;
	exists: boolean;
}

// Transcoder service config lives in the transcoder service, not the v3 backend.
// These keep their BFF data-shape return types so consumers that destructure the
// result still type-check; the async body rejects via notAvailable before any
// property is read at runtime (the screens are transcoder-gated / hidden).
export async function saveTranscoderConfig(
	_config: Record<string, unknown>
): Promise<{ success: boolean; applied?: Record<string, unknown> }> {
	notAvailable('Transcoder config');
}

export async function fetchAbcdeConfig(): Promise<AbcdeConfigData> {
	notAvailable('abcde config');
}

export async function saveAbcdeConfig(_content: string): Promise<{ success: boolean }> {
	notAvailable('abcde config');
}

export async function testTranscoderConnection(): Promise<ConnectionTestResult> {
	notAvailable('Transcoder connection test');
}

export async function testTranscoderWebhook(_secret: string): Promise<WebhookTestResult> {
	notAvailable('Transcoder webhook test');
}

export async function fetchSystemInfo(): Promise<SystemInfoData> {
	notAvailable('System info');
}

// Transcoder scheme (encoder/tier capability map) — MISSING in v3. Returning
// null drives the PresetEditor into its offline banner state, which is the
// correct UX while there is no transcoder-scheme backend.
export async function fetchTranscoderScheme(): Promise<Scheme | null> {
	return null;
}

// Re-export the local preset shapes so existing importers of these names from
// the settings api keep resolving (they moved off api.gen into presets.ts).
export type { Scheme, Preset, Overrides };
