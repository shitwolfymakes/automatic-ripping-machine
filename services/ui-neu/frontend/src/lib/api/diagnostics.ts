import type { DiagnosticsResponse } from '$lib/types/api.gen';
import { get } from './client';

export function fetchDiagnostics(): Promise<DiagnosticsResponse> {
	return get<DiagnosticsResponse>('/api/diagnostics');
}
