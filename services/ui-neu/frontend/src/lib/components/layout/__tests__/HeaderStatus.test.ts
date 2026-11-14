import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/test-utils';

// vi.mock factories are hoisted: all values must be inline (no top-level vars).
vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	return { dashboard: writable({}) };
});

vi.mock('$lib/stores/auth', async () => {
	const { writable, derived } = await import('svelte/store');
	const _authed = writable(true);
	return {
		isGuest: derived(_authed, (a) => !a),
		__setAuthed: (v: boolean) => _authed.set(v)
	};
});

import HeaderStatus from '../HeaderStatus.svelte';
import { dashboard } from '$lib/stores/dashboard';
import * as authModule from '$lib/stores/auth';

const setAuthed = (authModule as unknown as { __setAuthed: (v: boolean) => void }).__setAuthed;

function setDashboard(overrides: Record<string, unknown> = {}) {
	(dashboard as unknown as { set: (v: unknown) => void }).set({
		db_available: true,
		arm_online: true,
		drives_online: 2,
		active_jobs: [],
		active_transcodes: [],
		notification_count: 0,
		makemkv_key_valid: true,
		makemkv_key_checked_at: null,
		transcoder_online: true,
		transcoder_stats: { worker_running: true, pending: 0 },
		...overrides
	});
}

function render() {
	return renderComponent(HeaderStatus, { props: {} });
}

const dots = (c: HTMLElement) => [...c.querySelectorAll('.status-dot')].map((d) => d.getAttribute('data-status'));
const text = (c: HTMLElement, sel: string) => c.querySelector(sel)?.textContent?.trim();

describe('HeaderStatus', () => {
	beforeEach(() => {
		setAuthed(true);
		setDashboard();
	});
	afterEach(() => cleanup());

	it('renders four ok dots with their labels when everything is healthy', () => {
		const { container } = render();
		expect(dots(container)).toEqual(['ok', 'ok', 'ok', 'ok']);
		const labels = [...container.querySelectorAll('.layout-health-label')].map((l) => l.textContent);
		expect(labels).toEqual(['ARM', 'DB', 'Transcode', 'Key']);
	});

	it('links the health dots for a signed-in user', () => {
		const { container } = render();
		const links = [...container.querySelectorAll('.layout-health-link')];
		expect(links.map((l) => l.tagName)).toEqual(['A', 'A', 'A', 'A']);
		expect(links.map((l) => l.getAttribute('href'))).toEqual([
			'/settings#system',
			'/settings#system',
			'/transcoder',
			'/settings#Keys/makemkv_key'
		]);
		expect(container.querySelector('a.layout-activity-link')).toHaveAttribute('href', '/settings#drives');
	});

	it('renders guest health and drive items as spans without hrefs, except Transcode', () => {
		setAuthed(false);
		const { container } = render();
		const links = [...container.querySelectorAll('.layout-health-link')];
		expect(links.map((l) => l.tagName)).toEqual(['SPAN', 'SPAN', 'A', 'SPAN']);
		expect(links[0]).not.toHaveAttribute('href');
		expect(container.querySelector('span.layout-activity-link')).not.toHaveAttribute('href');
	});

	it('shows error/warn dots when ARM and the DB are down and the key is invalid', () => {
		setDashboard({ arm_online: false, db_available: false, makemkv_key_valid: false });
		const { container } = render();
		expect(dots(container)).toEqual(['error', 'warn', 'ok', 'error']);
	});

	it('shows the transcoder dot as warn when online with a stopped worker, off when offline', () => {
		setDashboard({ transcoder_stats: { worker_running: false } });
		const { container, unmount } = render();
		expect(dots(container)[2]).toBe('warn');
		unmount();
		setDashboard({ transcoder_online: false });
		const second = render();
		expect(dots(second.container)[2]).toBe('off');
	});

	it('puts the key validity on the Key link title', () => {
		setDashboard({ makemkv_key_valid: null });
		const { container } = render();
		const key = container.querySelectorAll('.layout-health-link')[3];
		expect(key).toHaveAttribute('title', 'MakeMKV key not checked yet');
	});

	it('shows the drive count with plural and singular labels', () => {
		const { container, unmount } = render();
		expect(text(container, '.layout-activity-link')).toBe('2 drives');
		unmount();
		setDashboard({ drives_online: 1 });
		const one = render();
		expect(text(one.container, '.layout-activity-link')).toBe('1 drive');
	});

	it('shows -- for the drive count when the database is unavailable', () => {
		setDashboard({ db_available: false });
		const { container } = render();
		expect(text(container, '.layout-activity-link')).toBe('-- drives');
	});

	it('hides every activity count when nothing is active', () => {
		const { container } = render();
		for (const cls of ['ripping', 'transcoding', 'queued', 'notification']) {
			expect(container.querySelector(`.layout-activity-${cls}`)).toBeNull();
		}
	});

	it('shows the ripping count from active ripping jobs', () => {
		setDashboard({
			active_jobs: [
				{ job_id: 1, status: 'ripping' },
				{ job_id: 2, status: 'ripping' }
			]
		});
		const { container } = render();
		expect(text(container, '.layout-activity-ripping')).toBe('2 ripping');
	});

	it('treats a missing active_jobs list as zero ripping', () => {
		setDashboard({ active_jobs: undefined });
		const { container } = render();
		expect(container.querySelector('.layout-activity-ripping')).toBeNull();
	});

	it('links the transcoding count to /transcoder', () => {
		setDashboard({ active_transcodes: [{ id: 't1' }, { id: 't2' }, { id: 't3' }] });
		const { container } = render();
		const el = container.querySelector('.layout-activity-transcoding');
		expect(el).toHaveTextContent('3 transcoding');
		expect(el).toHaveAttribute('href', '/transcoder');
	});

	it('shows the queued count only while the transcoder is online with pending work', () => {
		setDashboard({ transcoder_stats: { worker_running: true, pending: 4 } });
		const { container, unmount } = render();
		expect(text(container, '.layout-activity-queued')).toBe('4 queued');
		unmount();
		setDashboard({ transcoder_online: false, transcoder_stats: { pending: 4 } });
		const offline = render();
		expect(offline.container.querySelector('.layout-activity-queued')).toBeNull();
	});

	it('hides the queued count when stats are missing', () => {
		setDashboard({ transcoder_stats: undefined });
		const { container } = render();
		expect(container.querySelector('.layout-activity-queued')).toBeNull();
	});

	it('pluralises the notification count and links to /notifications', () => {
		setDashboard({ notification_count: 1 });
		const { container, unmount } = render();
		expect(text(container, '.layout-activity-notification')).toBe('1 notification');
		unmount();
		setDashboard({ notification_count: 5 });
		const many = render();
		const el = many.container.querySelector('.layout-activity-notification');
		expect(el).toHaveTextContent('5 notifications');
		expect(el).toHaveAttribute('href', '/notifications');
	});

	it('hides the notification count when it is null', () => {
		setDashboard({ notification_count: null });
		const { container } = render();
		expect(container.querySelector('.layout-activity-notification')).toBeNull();
	});
});
