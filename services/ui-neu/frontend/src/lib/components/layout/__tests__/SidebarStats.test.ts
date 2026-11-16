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
import { DEFAULT_REPO_URL } from '$lib/layout/version-chip';
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
		await waitFor(() => expect(calls).toBe(1));
		await Promise.resolve();
		flushSync();
		expect(container.querySelector('[data-sidebar-stats]')).toBeNull();
		initialized().set(true);
		flushSync();
		expect(container.querySelector('[data-sidebar-stats]')).not.toBeNull();
		expect(screen.getByText('12%')).toBeInTheDocument();
	});

	it('draws nothing until the version read is done, so the chip cannot push the panel up', async () => {
		let release: (v: unknown) => void = () => {};
		respond = () => new Promise((resolve) => (release = resolve));
		initialized().set(true);
		const { container } = renderComponent(SidebarStats);
		expect(container.querySelector('[data-sidebar-stats]')).toBeNull();
		release({ version: '1' });
		expect(await screen.findByText('v1')).toBeInTheDocument();
		expect(container.querySelector('[data-sidebar-stats]')).not.toBeNull();
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
});

describe('SidebarStats version chip', () => {
	beforeEach(() => {
		calls = 0;
		initialized().set(true);
	});
	afterEach(() => {
		cleanup();
		initialized().set(false);
	});

	it('shows the green status when up to date', async () => {
		respond = () => Promise.resolve({ version: '2.10.1', latest_version: '2.10.1', update_available: false });
		renderComponent(SidebarStats);
		expect(await screen.findByText('v2.10.1')).toBeTruthy();
		expect(screen.getByText('Up to date')).toBeTruthy();
		expect(screen.queryByRole('link', { name: /Update available/ })).toBeNull();
		const link = screen.getByRole('link', { name: 'ARM v2.10.1 on GitHub (opens in a new tab)' });
		expect(link.getAttribute('href')).toBe(DEFAULT_REPO_URL);
		expect(link.getAttribute('target')).toBe('_blank');
		expect(link.getAttribute('rel')).toBe('noopener noreferrer');
	});

	it('links to the repo_url the backend reports', async () => {
		respond = () => Promise.resolve({ version: '2.10.1', repo_url: 'https://github.com/me/fork' });
		renderComponent(SidebarStats);
		const link = await screen.findByRole('link', { name: 'ARM v2.10.1 on GitHub (opens in a new tab)' });
		expect(link.getAttribute('href')).toBe('https://github.com/me/fork');
	});

	it('does not double a leading v', async () => {
		respond = () => Promise.resolve({ version: 'v2.10.1' });
		renderComponent(SidebarStats);
		expect(await screen.findByText('v2.10.1')).toBeTruthy();
	});

	it('links to the release when an update is available', async () => {
		respond = () =>
			Promise.resolve({
				version: '2.10.1',
				latest_version: '2.11.0',
				update_available: true,
				release_url: 'https://github.com/o/r/releases/tag/v2.11.0'
			});
		renderComponent(SidebarStats);
		const link = await screen.findByRole('link', { name: 'Update available: v2.11.0 (opens in a new tab)' });
		expect(link.getAttribute('href')).toBe('https://github.com/o/r/releases/tag/v2.11.0');
		expect(link.getAttribute('target')).toBe('_blank');
		expect(link.getAttribute('rel')).toBe('noopener noreferrer');
		expect(screen.queryByText('Up to date')).toBeNull();
		expect(link.textContent).toContain('Update available');
		expect(link.querySelectorAll('a')).toHaveLength(0);
	});

	it('shows the version alone when nothing was checked', async () => {
		respond = () => Promise.resolve({ version: '2.10.1', latest_version: null, update_available: null });
		renderComponent(SidebarStats);
		expect(await screen.findByText('v2.10.1')).toBeTruthy();
		expect(screen.queryByText('Up to date')).toBeNull();
		expect(screen.queryByRole('link', { name: /Update available/ })).toBeNull();
		expect(screen.getByRole('link', { name: /on GitHub/ }).getAttribute('href')).toBe(DEFAULT_REPO_URL);
	});

	it('still draws the panel, without a chip, when the fetch fails', async () => {
		respond = () => Promise.reject(new Error('boom'));
		const { container } = renderComponent(SidebarStats);
		await waitFor(() => expect(container.querySelector('[data-sidebar-stats]')).not.toBeNull());
		expect(calls).toBe(1);
		expect(container.querySelector('[data-version-chip]')).toBeNull();
	});

	it('fetches once on mount', async () => {
		respond = () => Promise.resolve({ version: '2.10.1' });
		renderComponent(SidebarStats);
		await screen.findByText('v2.10.1');
		expect(calls).toBe(1);
	});
});
