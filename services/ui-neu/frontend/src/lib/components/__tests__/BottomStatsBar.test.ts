import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { flushSync } from 'svelte';
import type { Writable } from 'svelte/store';
import { renderComponent, screen, cleanup } from '$lib/test-utils';

// Drive the store with a fixed snapshot.
// vi.mock factories are hoisted — all values must be inline (no top-level vars).
vi.mock('$lib/stores/resources.svelte', async () => {
	const { readable } = await import('svelte/store');
	return {
		resources: readable({
			cpu_percent: 95,
			cpu_temp: 0,
			memory: { total_gb: 16, used_gb: 8, free_gb: 8, percent: 50 },
			storage: [{ name: 'Raw', path: '/raw', total_gb: 100, used_gb: 95, free_gb: 5, percent: 95 }]
		}),
		startResources: vi.fn(),
		stopResources: vi.fn()
	};
});

// Writable so a test can navigate between an auth page and a real page.
vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	return { page: writable({ url: new URL('http://localhost/'), params: {} }) };
});

import { page } from '$app/stores';
import { startResources, stopResources } from '$lib/stores/resources.svelte';
import BottomStatsBar from '$lib/components/BottomStatsBar.svelte';

function goTo(pathname: string) {
	(page as unknown as Writable<{ url: URL; params: Record<string, string> }>).set({
		url: new URL(`http://localhost${pathname}`),
		params: {}
	});
}

beforeEach(() => {
	goTo('/');
	vi.mocked(startResources).mockClear();
	vi.mocked(stopResources).mockClear();
});

afterEach(() => cleanup());

describe('BottomStatsBar', () => {
	it('renders CPU, memory and per-root storage', () => {
		renderComponent(BottomStatsBar);
		expect(screen.getByText(/Raw/)).toBeInTheDocument();
		// CPU at 95% present somewhere
		expect(screen.getByText(/95/)).toBeInTheDocument();
		expect(startResources).toHaveBeenCalledTimes(1);
	});

	it.each(['/login', '/change-password'])('does not render or poll on %s (D-137)', (path) => {
		goTo(path);
		renderComponent(BottomStatsBar);
		expect(screen.queryByTestId('bottom-stats-bar')).not.toBeInTheDocument();
		expect(startResources).not.toHaveBeenCalled();
	});

	it('starts polling on leaving an auth page and stops on returning to one (D-137)', () => {
		goTo('/login');
		renderComponent(BottomStatsBar);
		expect(startResources).not.toHaveBeenCalled();

		goTo('/');
		flushSync();
		expect(startResources).toHaveBeenCalledTimes(1);
		expect(screen.getByTestId('bottom-stats-bar')).toBeInTheDocument();

		goTo('/login');
		flushSync();
		expect(stopResources).toHaveBeenCalledTimes(1);
		expect(screen.queryByTestId('bottom-stats-bar')).not.toBeInTheDocument();
	});
});
