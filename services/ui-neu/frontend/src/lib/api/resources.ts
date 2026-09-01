import { apiFetch } from '$lib/api/client';
import type { SystemResourcesResponse } from '$lib/types/api.gen';

export function fetchResources(): Promise<SystemResourcesResponse> {
	return apiFetch<SystemResourcesResponse>('/api/system/resources');
}
