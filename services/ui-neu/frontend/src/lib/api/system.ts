import { apiFetch } from './client';
import type { SystemDiagnosticsResponse } from '$lib/types/api.gen';

export interface JobStats {
	by_status: Record<string, number>;
	by_type: Record<string, number>;
	total: number;
}

export function fetchJobStats(): Promise<JobStats> {
	return apiFetch<JobStats>('/api/system/job-stats');
}

export interface PreflightCheck {
	name: string;
	success: boolean;
	message: string;
	fixable: boolean;
}

export interface PreflightPath {
	name: string;
	container_path: string;
	host_path: string | null;
	exists: boolean;
	writable: boolean;
	owner_uid: number | null;
	owner_gid: number | null;
	expected_uid: number;
	expected_gid: number;
	match: boolean;
	fixable: boolean;
	require_writable: boolean;
}

export interface PreflightResult {
	arm_uid: number;
	arm_gid: number;
	checks: PreflightCheck[];
	paths: PreflightPath[];
}

// v3 health check: GET /api/system/diagnostics (config, storage paths, drives,
// MakeMKV key and decryption data, transcoder, ripper manager).
export function fetchSystemDiagnostics(): Promise<SystemDiagnosticsResponse> {
	return apiFetch<SystemDiagnosticsResponse>('/api/system/diagnostics');
}

// MISSING in v3: the preflight/fix pair below is the neu BFF contract, kept only
// for the feature-flagged setup wizard (features.setup = false). Nothing shipped
// calls it; System Health uses fetchSystemDiagnostics.
export function runPreflight(): Promise<PreflightResult> {
	return apiFetch<PreflightResult>('/api/system/preflight', { method: 'POST' });
}

export function fixPreflight(items: string[]): Promise<PreflightResult> {
	return apiFetch<PreflightResult>('/api/system/preflight/fix', {
		method: 'POST',
		body: JSON.stringify({ fix: items }),
	});
}
