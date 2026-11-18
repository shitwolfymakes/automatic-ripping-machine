// Open arms the coverage tool reports, none of which can run. Four are
// Svelte's: the memory used and total and a disk's free space are numbers, and
// the CPU temperature text is a string, each interpolated through a compiled
// `(...) ?? ''`. One is the component's own: `($resources.cpu_temp ?? 0)` in
// the temperature text sits inside `{#if ($resources.cpu_temp ?? 0) > 0}`, so
// cpu_temp is always set where it is read.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import { flushSync } from 'svelte';

const h = vi.hoisted(() => ({ store: null as unknown as Record<string, unknown> }));
vi.mock('$lib/stores/resources.svelte', async () => {
	const { writable } = await import('svelte/store');
	const snapshot = writable({
		cpu_percent: 12,
		cpu_temp: null as number | null,
		memory: { total_gb: 16, used_gb: 4, free_gb: 12, percent: 25 },
		storage: [] as { name: string; path: string; total_gb: number; used_gb: number; free_gb: number; percent: number }[]
	});
	const initialized = writable(false);
	h.store = { snapshot, initialized };
	return { resources: Object.assign(snapshot, { initialized }) };
});

import SidebarStats from '../SidebarStats.svelte';
import type { Writable } from 'svelte/store';

const initialized = () => h.store.initialized as Writable<boolean>;
const snapshot = () => h.store.snapshot as Writable<Record<string, unknown>>;

describe('SidebarStats', () => {
	afterEach(() => {
		cleanup();
		initialized().set(false);
	});

	it('draws nothing until the first resources poll lands', () => {
		const { container } = renderComponent(SidebarStats);
		expect(container.querySelector('[data-sidebar-stats]')).toBeNull();
		initialized().set(true);
		flushSync();
		expect(container.querySelector('[data-sidebar-stats]')).not.toBeNull();
		expect(screen.getByText('12%')).toBeInTheDocument();
	});

	it('shows the CPU temperature and the storage rows once ready', () => {
		snapshot().update((s) => ({
			...s,
			cpu_temp: 61,
			storage: [{ name: 'Raw', path: '/raw', total_gb: 100, used_gb: 40, free_gb: 60, percent: 40 }]
		}));
		initialized().set(true);
		renderComponent(SidebarStats);
		expect(screen.getByText(/61/)).toBeInTheDocument();
		expect(screen.getByText('Raw')).toBeInTheDocument();
		expect(screen.getByText('60 GB free')).toBeInTheDocument();
	});
});
