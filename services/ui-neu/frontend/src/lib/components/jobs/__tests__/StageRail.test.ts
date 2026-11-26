// Open arm the coverage tool reports that is Svelte's, not the component's:
// the screen-reader `{seg.state}` compiles to `(...) ?? ''`, and a segment's
// state is always a string.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import type { writable } from 'svelte/store';
import { EMPTY_LIVE, type JobLive } from '$lib/stores/job-live.svelte';
import type { ProgressJob } from '$lib/jobs/progress';

const h = vi.hoisted(() => ({ unwatch: vi.fn(), watch: vi.fn(), live: undefined as unknown }));

vi.mock('$lib/stores/job-live.svelte', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/stores/job-live.svelte')>()),
	jobLive: { watch: h.watch, get: () => h.live }
}));
vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	return { dashboard: writable<unknown>({ review_wait_seconds: 60, ripping_enabled: true }) };
});

import StageRail from '../StageRail.svelte';
import { dashboard } from '$lib/stores/dashboard';

type RailJob = ProgressJob & { id: string };

function job(over: Partial<RailJob> = {}): RailJob {
	return {
		id: 'j1',
		status: 'ripping',
		title: 'Movie',
		rip_progress: { tracks_total: 4, tracks_done: 1, current_track_index: 2 },
		transcode_progress: null,
		wait_start_time: null,
		manual_pause: false,
		episodes_unsure: false,
		metadata_json: null,
		...over
	} as unknown as RailJob;
}

const countdownJob = () =>
	job({ status: 'awaiting_review', rip_progress: null, wait_start_time: new Date().toISOString() });

beforeEach(() => {
	h.unwatch = vi.fn();
	h.watch.mockReset().mockImplementation(() => h.unwatch);
	h.live = {
		...EMPTY_LIVE,
		rip: { pct: 42, etaSeconds: 600, phase: null }
	} as unknown as JobLive;
	(dashboard as unknown as ReturnType<typeof writable>).set({ review_wait_seconds: 60, ripping_enabled: true });
});

afterEach(() => {
	cleanup();
	vi.useRealTimers();
	vi.restoreAllMocks();
});

describe('StageRail', () => {
	it('renders five stages in order ID, Wait, Rip, Encode, Done', () => {
		render(StageRail, { job: job() });
		const items = screen.getByRole('list', { name: 'Job stages' }).querySelectorAll('li');
		expect([...items].map((li) => li.textContent?.split(':')[0].trim())).toEqual([
			'ID',
			'Wait',
			'Rip',
			'Encode',
			'Done'
		]);
	});

	it('marks each stage state for a ripping job', () => {
		render(StageRail, { job: job() });
		const items = screen.getByRole('list', { name: 'Job stages' }).querySelectorAll('li');
		expect([...items].map((li) => li.getAttribute('data-state'))).toEqual([
			'done',
			'done',
			'active',
			'pending',
			'pending'
		]);
		expect(items[2].textContent).toContain(': active');
	});

	it('shows the readout label, detail and figure', () => {
		const { container } = render(StageRail, { job: job() });
		const readout = container.querySelector('p[data-tone]') as HTMLElement;
		expect(readout.dataset.tone).toBe('default');
		expect(readout.textContent).toContain('Ripping');
		expect(readout.textContent).toContain('title 2 of 4');
		expect(screen.getByText(/42%/)).toBeInTheDocument();
	});

	it('shows a bare label when the readout has no detail or figure', () => {
		const { container } = render(StageRail, { job: job({ status: 'awaiting_user_id', rip_progress: null }) });
		const readout = container.querySelector('p[data-tone]') as HTMLElement;
		expect(readout.textContent?.trim()).toBe('Waiting for identification');
	});

	it('clamps a tiny known percent to a visible sliver', () => {
		h.live = { ...EMPTY_LIVE, rip: { pct: 0, etaSeconds: null, phase: null } } as unknown as JobLive;
		const { container } = render(StageRail, { job: job() });
		expect((container.querySelector('.stage-rail-fill') as HTMLElement).style.getPropertyValue('--fill-width')).toBe(
			'2%'
		);
	});

	it('shows an unknown-length fill for an active stage without a percent', () => {
		h.live = { ...EMPTY_LIVE, rip: { pct: null, etaSeconds: null, phase: null } } as unknown as JobLive;
		const { container } = render(StageRail, { job: job() });
		expect(container.querySelector('.stage-rail-fill')?.getAttribute('data-known')).toBe('false');
	});

	it('size md sets data-size', () => {
		const { container } = render(StageRail, { job: job(), size: 'md' });
		expect(container.querySelector('.stage-rail')?.getAttribute('data-size')).toBe('md');
	});

	it('StageRail re-watches when the status changes', async () => {
		const { rerender } = render(StageRail, { job: job() });
		expect(h.watch).toHaveBeenCalledWith({ id: 'j1', status: 'ripping' });
		const first = h.unwatch;
		await rerender({ job: job({ status: 'ripped' }) });
		expect(first).toHaveBeenCalledTimes(1);
		expect(h.watch).toHaveBeenLastCalledWith({ id: 'j1', status: 'ripped' });
		expect(h.watch).toHaveBeenCalledTimes(2);
	});

	it('does not re-watch when only another field changes', async () => {
		const { rerender } = render(StageRail, { job: job() });
		await rerender({ job: job({ title: 'Other' }) });
		expect(h.watch).toHaveBeenCalledTimes(1);
	});

	it('unwatches on unmount', () => {
		const { unmount } = render(StageRail, { job: job() });
		unmount();
		expect(h.unwatch).toHaveBeenCalledTimes(1);
	});

	it('ticks once a second only while counting down', async () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
		const countdown = job({
			status: 'awaiting_review',
			rip_progress: null,
			wait_start_time: new Date('2026-01-01T00:00:00Z').toISOString()
		});
		const { container } = render(StageRail, { job: countdown });
		const readout = container.querySelector('p[data-tone]') as HTMLElement;
		const before = readout.textContent;
		await vi.advanceTimersByTimeAsync(2000);
		expect(readout.textContent).not.toBe(before);
	});

	it('sets no interval for a job that is not counting down', () => {
		const spy = vi.spyOn(globalThis, 'setInterval');
		render(StageRail, { job: job() });
		expect(spy).not.toHaveBeenCalled();
	});

	it('clears the interval when the countdown ends', () => {
		const spy = vi.spyOn(globalThis, 'clearInterval');
		const { unmount } = render(StageRail, { job: countdownJob() });
		unmount();
		expect(spy).toHaveBeenCalled();
	});

	it('falls back to defaults when the dashboard has not loaded', () => {
		(dashboard as unknown as ReturnType<typeof writable>).set(null);
		const { container } = render(StageRail, { job: countdownJob() });
		expect(container.querySelector('p[data-tone]')?.textContent).toContain('Waiting for review');
	});

	it('holds the countdown while ripping is paused', () => {
		(dashboard as unknown as ReturnType<typeof writable>).set({ review_wait_seconds: 60, ripping_enabled: false });
		const { container } = render(StageRail, { job: countdownJob() });
		expect(container.querySelector('p[data-tone]')?.textContent).toContain('Paused');
	});
});
