import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/resources', () => ({ fetchResources: vi.fn() }));
import { fetchResources } from '$lib/api/resources';
import { fetchResourcesSticky } from '$lib/stores/resources.svelte';

const sample = {
	cpu_percent: 10,
	cpu_temp: 0,
	memory: { total_gb: 16, used_gb: 2, free_gb: 13, percent: 12 },
	storage: [{ name: 'Raw', path: '/raw', total_gb: 100, used_gb: 40, free_gb: 60, percent: 40 }]
};

describe('fetchResourcesSticky', () => {
	beforeEach(() => vi.mocked(fetchResources).mockReset());

	it('returns fresh data on success', async () => {
		vi.mocked(fetchResources).mockResolvedValueOnce(sample as any);
		expect(await fetchResourcesSticky()).toEqual(sample);
	});

	it('returns last-good on a failed poll', async () => {
		vi.mocked(fetchResources).mockResolvedValueOnce(sample as any);
		await fetchResourcesSticky();
		vi.mocked(fetchResources).mockRejectedValueOnce(new Error('timeout'));
		expect(await fetchResourcesSticky()).toEqual(sample);
	});
});
