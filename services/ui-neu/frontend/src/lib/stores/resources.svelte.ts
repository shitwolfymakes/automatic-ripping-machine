import { createPollingStore } from './polling';
import { fetchResources } from '$lib/api/resources';
import type { HostResourcesView } from '$lib/types/api.gen';

const empty: HostResourcesView[] = [];

// Hold the last non-empty payload so a single failed/empty poll doesn't blank
// the tabs (mirrors dashboard.ts's sticky behavior).
let lastGood: HostResourcesView[] = empty;

export async function fetchResourcesSticky(): Promise<HostResourcesView[]> {
	try {
		const next = await fetchResources();
		if (next.length > 0) lastGood = next;
	} catch {
		// keep lastGood
	}
	return lastGood;
}

export const resources = createPollingStore<HostResourcesView[]>(fetchResourcesSticky, empty, 5000);
export const startResources = () => resources.start();
export const stopResources = () => resources.stop();
