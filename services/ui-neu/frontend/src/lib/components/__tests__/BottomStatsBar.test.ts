import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';

// Drive the store with a fixed snapshot.
// vi.mock factories are hoisted — all values must be inline (no top-level vars).
vi.mock('$lib/stores/resources.svelte', async () => {
	const { readable } = await import('svelte/store');
	return {
		resources: readable([
			{
				role: 'backend',
				hostname: 'backend-1',
				version: '1',
				snapshot: {
					cpu_percent: 95,
					cpu_temp: 0,
					memory: { total_gb: 16, used_gb: 8, free_gb: 8, percent: 50 },
					storage: [{ name: 'Raw', path: '/raw', total_gb: 100, used_gb: 95, free_gb: 5, percent: 95 }]
				}
			}
		]),
		startResources: vi.fn(),
		stopResources: vi.fn()
	};
});

import BottomStatsBar from '$lib/components/BottomStatsBar.svelte';

afterEach(() => cleanup());

describe('BottomStatsBar', () => {
	it('renders CPU, memory and per-root storage', () => {
		renderComponent(BottomStatsBar);
		expect(screen.getByText(/Raw/)).toBeInTheDocument();
		// CPU at 95% present somewhere
		expect(screen.getByText(/95/)).toBeInTheDocument();
	});
});
