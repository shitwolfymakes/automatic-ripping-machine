import { apiFetch } from './client';
import type { SystemDiagnosticsResponse, SystemVersionResponse } from '$lib/types/api.gen';

// v3 health check: GET /api/system/diagnostics (config, storage paths, drives,
// MakeMKV key and decryption data, transcoder, ripper manager).
export function fetchSystemDiagnostics(): Promise<SystemDiagnosticsResponse> {
	return apiFetch<SystemDiagnosticsResponse>('/api/system/diagnostics');
}

export function fetchSystemVersion(): Promise<SystemVersionResponse> {
	return apiFetch<SystemVersionResponse>('/api/system/version');
}
