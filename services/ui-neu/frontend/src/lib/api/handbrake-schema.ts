import type { HandbrakeSchemaSlimView } from '$lib/types/api.gen';
import { get, post } from './client';

export function fetchHandbrakeSchema(): Promise<HandbrakeSchemaSlimView> {
	return get<HandbrakeSchemaSlimView>('/api/handbrake-schema');
}

// A built-in preset's raw values, by its HandBrake name (which has spaces and dots).
export function fetchBuiltinPreset(name: string): Promise<Record<string, unknown>> {
	return get<Record<string, unknown>>(`/api/handbrake-schema/builtin/${encodeURIComponent(name)}`);
}

export async function refreshHandbrakeSchema(): Promise<{ ok: boolean; error: string | null }> {
	const result = await post<{ ok: boolean; error?: string | null }>('/api/handbrake-schema/refresh');
	return { ok: result.ok, error: result.error ?? null };
}
