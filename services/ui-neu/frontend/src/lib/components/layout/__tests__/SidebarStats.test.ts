// Open arms the coverage tool reports, none of which can run. Four are
// Svelte's: the memory used and total and a disk's free space are numbers, and
// the CPU temperature text is a string, each interpolated through a compiled
// `(...) ?? ''`. One is the component's own: `($resources.cpu_temp ?? 0)` in
// the temperature text sits inside `{#if ($resources.cpu_temp ?? 0) > 0}`, so
// cpu_temp is always set where it is read.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderComponent, screen, waitFor, cleanup } from '$lib/testing/render';
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

let respond: () => Promise<unknown> = () => Promise.resolve({ version: '0' });
let calls = 0;
vi.mock('$lib/api/system', () => ({
	fetchSystemVersion: () => {
		calls += 1;
		return respond();
	}
}));

import SidebarStats from '../SidebarStats.svelte';
import { VERSION_CHIP_TIMEOUT_MS } from '$lib/layout/version-chip';
import type { Writable } from 'svelte/store';

const initialized = () => h.store.initialized as Writable<boolean>;
const snapshot = () => h.store.snapshot as Writable<Record<string, unknown>>;

describe('SidebarStats', () => {
	beforeEach(() => {
		calls = 0;
	});
	afterEach(() => {
		cleanup();
		initialized().set(false);
	});

	it('draws nothing until the first resources poll lands', async () => {
		respond = () => Promise.resolve({ version: '1' });
		const { container } = renderComponent(SidebarStats);
		flushSync();
		expect(container.querySelector('[data-sidebar-stats]')).toBeNull();
		// The chip mounts with the panel, so nothing asks for the version yet.
		expect(calls).toBe(0);
		initialized().set(true);
		flushSync();
		expect(container.querySelector('[data-sidebar-stats]')).not.toBeNull();
		expect(screen.getByText('12%')).toBeInTheDocument();
		await waitFor(() => expect(calls).toBe(1));
	});

	it('keeps the panel hidden until the version chip settles, so the chip cannot push the bars up', async () => {
		let release: (v: unknown) => void = () => {};
		respond = () => new Promise((resolve) => (release = resolve));
		initialized().set(true);
		const { container } = renderComponent(SidebarStats);
		const panel = () => container.querySelector('[data-sidebar-stats]') as HTMLElement;
		expect(panel().hasAttribute('data-pending')).toBe(true);
		await waitFor(() => expect(calls).toBe(1));
		release({ version: '1' });
		expect(await screen.findByText('v1')).toBeInTheDocument();
		expect(panel().hasAttribute('data-pending')).toBe(false);
		expect(panel().querySelector('[data-version-chip]')).not.toBeNull();
	});

	it('shows the bars without a chip once a version read that never answers times out', async () => {
		vi.useFakeTimers();
		respond = () => new Promise(() => {});
		initialized().set(true);
		const { container } = renderComponent(SidebarStats);
		const panel = () => container.querySelector('[data-sidebar-stats]') as HTMLElement;
		expect(panel().hasAttribute('data-pending')).toBe(true);
		await vi.advanceTimersByTimeAsync(VERSION_CHIP_TIMEOUT_MS);
		expect(panel().hasAttribute('data-pending')).toBe(false);
		expect(panel().querySelector('[data-version-chip]')).toBeNull();
		vi.useRealTimers();
	});

	it('shows the CPU temperature and the storage rows once ready', async () => {
		respond = () => Promise.resolve({ version: '1' });
		snapshot().update((s) => ({
			...s,
			cpu_temp: 61,
			storage: [{ name: 'Raw', path: '/raw', total_gb: 100, used_gb: 40, free_gb: 60, percent: 40 }]
		}));
		initialized().set(true);
		renderComponent(SidebarStats);
		expect(await screen.findByText('60 GB free')).toBeInTheDocument();
		expect(screen.getByText(/61/)).toBeInTheDocument();
		expect(screen.getByText('Raw')).toBeInTheDocument();
	});

	it("draws a bar for a staging area on its own disk, and none for one that shares raw's", async () => {
		respond = () => Promise.resolve({ version: '1' });
		const raw = { name: 'RAW_ROOT', path: '/raw', total_gb: 100, used_gb: 40, free_gb: 60, percent: 40 };
		const staging = { name: 'STAGING_ROOT', path: '/staging', total_gb: 50, used_gb: 5, free_gb: 45, percent: 10 };
		initialized().set(true);
		snapshot().update((s) => ({ ...s, storage: [raw, { ...staging, placement: 'separate_device' }] }));
		const view = renderComponent(SidebarStats);
		expect(await screen.findByText('STAGING_ROOT')).toBeInTheDocument();
		view.unmount();
		snapshot().update((s) => ({ ...s, storage: [raw, { ...staging, placement: 'same_device' }] }));
		renderComponent(SidebarStats);
		expect(await screen.findByText('RAW_ROOT')).toBeInTheDocument();
		expect(screen.queryByText('STAGING_ROOT')).toBeNull();
	});
});
