import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Writable } from 'svelte/store';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';

// Branch pins for MobileStatsPanel, beside MobileStatsPanel.test.ts. Every
// branch of the component is reachable from the rendered panel, so nothing
// here is left unpinned.

// vi.mock factories are hoisted: all values must be inline (no top-level vars).
vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	const store = writable({});
	return {
		dashboard: { ...store, start: vi.fn(), stop: vi.fn(), error: writable(null) }
	};
});

vi.mock('$lib/stores/auth', async () => {
	const { writable, derived } = await import('svelte/store');
	const _authed = writable(true);
	return {
		isGuest: derived(_authed, (a) => !a),
		__setAuthed: (v: boolean) => _authed.set(v)
	};
});

vi.mock('$lib/stores/resources.svelte', async () => {
	const { readable } = await import('svelte/store');
	return {
		resources: readable({
			cpu_percent: 42,
			cpu_temp: 0,
			memory: { total_gb: 16, used_gb: 8, free_gb: 8, percent: 50 },
			storage: [{ name: 'Raw', path: '/raw', total_gb: 100, used_gb: 20, free_gb: 80, percent: 20 }]
		}),
		startResources: vi.fn(),
		stopResources: vi.fn()
	};
});

import MobileStatsPanel from '$lib/components/layout/MobileStatsPanel.svelte';
import { dashboard } from '$lib/stores/dashboard';

type Overrides = Record<string, unknown>;

const BASE = {
	db_available: true,
	arm_online: true,
	active_jobs: [],
	drives_online: 2,
	drive_names: {},
	notification_count: 0,
	ripping_enabled: true,
	makemkv_key_valid: true,
	makemkv_key_checked_at: null,
	transcoder_online: true,
	transcoder_stats: { worker_running: true, pending: 0 },
	active_transcodes: []
};

function setDashboard(overrides: Overrides = {}) {
	(dashboard as unknown as Writable<unknown>).set({ ...BASE, ...overrides });
}

async function setAuthed(v: boolean) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setAuthed: (v: boolean) => void };
	auth.__setAuthed(v);
}

function row(label: string): HTMLElement {
	return screen.getByText(label);
}

function dotStatus(label: string): string | null {
	return row(label).querySelector('.status-dot')!.getAttribute('data-status');
}

// jsdom can't navigate; prevent the default so anchor clicks don't log
// "Not implemented: navigation to another Document".
const preventNav = (e: Event) => e.preventDefault();
beforeEach(() => {
	document.addEventListener('click', preventNav);
	setDashboard();
});
afterEach(async () => {
	document.removeEventListener('click', preventNav);
	cleanup();
	await setAuthed(true);
});

describe('MobileStatsPanel services', () => {
	it.each([
		['ARM online', { arm_online: true }, 'ARM', 'ok'],
		['ARM offline', { arm_online: false }, 'ARM', 'error'],
		['DB available', { db_available: true }, 'DB', 'ok'],
		['DB unavailable', { db_available: false }, 'DB', 'warn'],
		['Key valid', { makemkv_key_valid: true }, 'Key', 'ok'],
		['Key invalid', { makemkv_key_valid: false }, 'Key', 'error'],
		['Key unchecked (null)', { makemkv_key_valid: null }, 'Key', 'error']
	])('%s shows status %s', (_name, overrides, label, status) => {
		setDashboard(overrides);
		renderComponent(MobileStatsPanel);
		expect(dotStatus(label)).toBe(status);
	});

	it.each([
		['online, worker running', true, { worker_running: true }, 'ok'],
		['online, worker_running missing', true, { pending: 0 }, 'ok'],
		['online, worker_running null', true, { worker_running: null }, 'ok'],
		['online, no stats', true, undefined, 'ok'],
		['online, worker stopped', true, { worker_running: false }, 'warn'],
		['offline, worker running', false, { worker_running: true }, 'off'],
		['offline, worker stopped', false, { worker_running: false }, 'off'],
		['offline, no stats', false, undefined, 'off']
	])('Transcode %s shows status %s', (_name, online, stats, status) => {
		setDashboard({ transcoder_online: online, transcoder_stats: stats });
		renderComponent(MobileStatsPanel);
		expect(dotStatus('Transcode')).toBe(status);
	});

	it('links every service row for an authenticated user', () => {
		renderComponent(MobileStatsPanel);
		const expected: [string, string][] = [
			['ARM', '/settings#system'],
			['DB', '/settings#system'],
			['Transcode', '/transcoder'],
			['Key', '/settings#Keys/makemkv_key']
		];
		for (const [label, href] of expected) {
			expect(row(label).tagName).toBe('A');
			expect(row(label)).toHaveAttribute('href', href);
		}
	});

	it('renders the three settings rows as hrefless spans for a guest', async () => {
		await setAuthed(false);
		renderComponent(MobileStatsPanel);
		for (const label of ['ARM', 'DB', 'Key']) {
			expect(row(label).tagName).toBe('SPAN');
			expect(row(label)).not.toHaveAttribute('href');
		}
		expect(row('Transcode').tagName).toBe('A');
		expect(row('Transcode')).toHaveAttribute('href', '/transcoder');
	});
});

describe('MobileStatsPanel activity', () => {
	it.each([
		['one drive', { drives_online: 1 }, /^1 drive$/],
		['no drives', { drives_online: 0 }, /^0 drives$/],
		['two drives', { drives_online: 2 }, /^2 drives$/],
		['the database down', { db_available: false, drives_online: 2 }, /^-- drives$/],
		['the database down with one drive', { db_available: false, drives_online: 1 }, /^-- drive$/]
	])('shows the drive count for %s', (_name, overrides, text) => {
		setDashboard(overrides);
		renderComponent(MobileStatsPanel);
		expect(screen.getByText(text)).toBeInTheDocument();
	});

	it('links the drive count to the drive settings for an authenticated user', () => {
		renderComponent(MobileStatsPanel);
		const el = screen.getByText(/^2 drives$/);
		expect(el.tagName).toBe('A');
		expect(el).toHaveAttribute('href', '/settings#drives');
	});

	it('shows the drive count as an hrefless span for a guest', async () => {
		await setAuthed(false);
		renderComponent(MobileStatsPanel);
		const el = screen.getByText(/^2 drives$/);
		expect(el.tagName).toBe('SPAN');
		expect(el).not.toHaveAttribute('href');
	});

	it.each([
		['active_jobs is null', null],
		['active_jobs is undefined', undefined],
		['active_jobs is empty', []],
		['no job is ripping', [{ job_id: 1, status: 'transcoding', title: 'A' }]]
	])('shows no ripping line when %s', (_name, jobs) => {
		setDashboard({ active_jobs: jobs });
		renderComponent(MobileStatsPanel);
		expect(screen.queryByText(/ripping/)).toBeNull();
	});

	it('shows the ripping line when a job is ripping', () => {
		setDashboard({ active_jobs: [{ job_id: 1, status: 'ripping', title: 'A' }] });
		renderComponent(MobileStatsPanel);
		expect(screen.getByText(/1 ripping/)).toBeInTheDocument();
	});

	it('shows no transcoding line without active transcodes', () => {
		renderComponent(MobileStatsPanel);
		expect(screen.queryByText(/transcoding/)).toBeNull();
	});

	it('links the transcoding line to the transcoder', () => {
		setDashboard({ active_transcodes: [{ id: 't1' }, { id: 't2' }] });
		renderComponent(MobileStatsPanel);
		const el = screen.getByText(/2 transcoding/);
		expect(el.tagName).toBe('A');
		expect(el).toHaveAttribute('href', '/transcoder');
	});

	it.each([
		['the transcoder is online and pending is above 0', true, { pending: 3 }, true],
		['pending is a numeric string above 0', true, { pending: '3' }, true],
		['pending is 0', true, { pending: 0 }, false],
		['pending is missing', true, { worker_running: true }, false],
		['pending is non-numeric', true, { pending: 'lots' }, false],
		['there are no stats', true, undefined, false],
		['the transcoder is offline', false, { pending: 3 }, false]
	])('queued line with %s: shown is %s', (_name, online, stats, shown) => {
		setDashboard({ transcoder_online: online, transcoder_stats: stats });
		renderComponent(MobileStatsPanel);
		if (shown) expect(screen.getByText(/queued/)).toBeInTheDocument();
		else expect(screen.queryByText(/queued/)).toBeNull();
	});

	it.each([
		['one notification', { notification_count: 1 }, /^1 notification$/],
		['two notifications', { notification_count: 2 }, /^2 notifications$/]
	])('shows %s linked to the notifications page', (_name, overrides, text) => {
		setDashboard(overrides);
		renderComponent(MobileStatsPanel);
		const el = screen.getByText(text);
		expect(el.tagName).toBe('A');
		expect(el).toHaveAttribute('href', '/notifications');
	});

	it.each([
		['zero', 0],
		['null', null],
		['undefined', undefined]
	])('shows no notification line when the count is %s', (_name, count) => {
		setDashboard({ notification_count: count });
		renderComponent(MobileStatsPanel);
		expect(screen.queryByText(/notification/)).toBeNull();
	});
});

describe('MobileStatsPanel navigation', () => {
	it.each([
		['a service link', () => screen.getByText('ARM')],
		['the drive link', () => screen.getByText(/2 drives/)]
	])('calls onnavigate for a click on %s', async (_name, target) => {
		const onnavigate = vi.fn();
		renderComponent(MobileStatsPanel, { props: { onnavigate } });
		await fireEvent.click(target());
		expect(onnavigate).toHaveBeenCalledTimes(1);
	});

	it('does not call onnavigate for a click outside a link', async () => {
		const onnavigate = vi.fn();
		renderComponent(MobileStatsPanel, { props: { onnavigate } });
		await fireEvent.click(screen.getByText('Services'));
		expect(onnavigate).not.toHaveBeenCalled();
	});

	it('does not throw on a link click without onnavigate', async () => {
		renderComponent(MobileStatsPanel);
		await expect(fireEvent.click(screen.getByText('ARM'))).resolves.not.toThrow();
	});
});
