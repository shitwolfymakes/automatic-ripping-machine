import { apiFetch } from '$lib/api/client';
import type { HostResourcesView } from '$lib/types/api.gen';

export function fetchResources(): Promise<HostResourcesView[]> {
	return apiFetch<HostResourcesView[]>('/api/system/resources');
}
