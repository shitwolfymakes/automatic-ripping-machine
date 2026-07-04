import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/resources', () => ({
	fetchResources: vi.fn()
}));

import { fetchResources } from '$lib/api/resources';
import { fetchResourcesSticky } from '$lib/stores/resources.svelte';

const view = (hostname: string, cpu: number) => ({
	role: 'ripper',
	hostname,
	version: '1',
	snapshot: {
		cpu_percent: cpu,
		cpu_temp: 0,
		memory: { total_gb: 8, used_gb: 1, free_gb: 7, percent: 12.5 },
		storage: []
	}
});

describe('fetchResourcesSticky', () => {
	beforeEach(() => vi.clearAllMocks());

	it('returns the fetched list', async () => {
		(fetchResources as any).mockResolvedValueOnce([view('h1', 5)]);
		const out = await fetchResourcesSticky();
		expect(out).toHaveLength(1);
		expect(out[0].hostname).toBe('h1');
	});

	it('keeps last-good on failure', async () => {
		(fetchResources as any).mockResolvedValueOnce([view('h1', 5)]);
		await fetchResourcesSticky();
		(fetchResources as any).mockRejectedValueOnce(new Error('boom'));
		const out = await fetchResourcesSticky();
		expect(out).toHaveLength(1);
		expect(out[0].hostname).toBe('h1');
	});

	it('does not overwrite last-good with an empty list on failure', async () => {
		(fetchResources as any).mockResolvedValueOnce([view('h1', 5)]);
		await fetchResourcesSticky();
		(fetchResources as any).mockRejectedValueOnce(new Error('boom'));
		const out = await fetchResourcesSticky();
		expect(out.length).toBeGreaterThan(0);
	});
});
