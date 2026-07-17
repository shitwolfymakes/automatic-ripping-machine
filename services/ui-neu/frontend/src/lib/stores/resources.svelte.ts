import { createPollingStore } from './polling';
import { fetchResources } from '$lib/api/resources';
import type { SystemResourcesResponse } from '$lib/types/api.gen';

const empty: SystemResourcesResponse = {
	cpu_percent: 0,
	cpu_temp: 0,
	memory: { total_gb: 0, used_gb: 0, free_gb: 0, percent: 0 },
	storage: []
};

// Hold the last successful payload so a single failed poll doesn't blank the
// bars (mirrors dashboard.ts's sticky behavior).
let lastGood: SystemResourcesResponse = empty;

export async function fetchResourcesSticky(): Promise<SystemResourcesResponse> {
	try {
		lastGood = await fetchResources();
	} catch {
		// keep lastGood
	}
	return lastGood;
}

export const resources = createPollingStore<SystemResourcesResponse>(fetchResourcesSticky, empty, 5000);
export const startResources = () => resources.start();
export const stopResources = () => resources.stop();
