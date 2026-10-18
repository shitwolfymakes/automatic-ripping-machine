import { describe, it, expect, vi, afterEach } from 'vitest';

type Listener = (jobIds: Set<string>, eventTypes: Map<string, Set<string>>) => void;
const listeners: Listener[] = [];
vi.mock('../ripperEvents.svelte', () => ({
	startRipperEvents: vi.fn(),
	onRipperEvent: (fn: Listener) => {
		listeners.push(fn);
		return () => listeners.splice(listeners.indexOf(fn), 1);
	}
}));

import { EpisodeMatching, MATCHING_TIMEOUT_MS, onJobEvents } from '../episodeMatching.svelte';
import { startRipperEvents } from '../ripperEvents.svelte';

function fire(jobId: string, type: string) {
	listeners.forEach((fn) => fn(new Set([jobId]), new Map([[jobId, new Set([type])]])));
}

describe('EpisodeMatching', () => {
	afterEach(() => vi.useRealTimers());

	it('is active from start() until stop()', () => {
		const m = new EpisodeMatching();
		expect(m.active).toBe(false);
		m.start();
		expect(m.active).toBe(true);
		m.stop();
		expect(m.active).toBe(false);
	});

	it('clears itself after the timeout, counted from the latest start()', () => {
		vi.useFakeTimers();
		const m = new EpisodeMatching();
		m.start();
		vi.advanceTimersByTime(MATCHING_TIMEOUT_MS - 1000);
		m.start();
		vi.advanceTimersByTime(MATCHING_TIMEOUT_MS - 1000);
		expect(m.active).toBe(true);
		vi.advanceTimersByTime(1000);
		expect(m.active).toBe(false);
	});

	it('a stop() cancels the pending timeout', () => {
		vi.useFakeTimers();
		const m = new EpisodeMatching();
		m.start();
		m.stop();
		m.active = true;
		vi.advanceTimersByTime(MATCHING_TIMEOUT_MS);
		expect(m.active).toBe(true);
	});
});

describe('onJobEvents', () => {
	it('starts the feed and passes only this job, flagging job.identity_updated', () => {
		const handler = vi.fn();
		let id: string | null = 'job_1';
		const off = onJobEvents(() => id, handler);
		expect(startRipperEvents).toHaveBeenCalled();
		fire('job_2', 'job.identity_updated');
		expect(handler).not.toHaveBeenCalled();
		fire('job_1', 'rip.identify_resolved');
		expect(handler).toHaveBeenLastCalledWith(false);
		fire('job_1', 'job.identity_updated');
		expect(handler).toHaveBeenLastCalledWith(true);
		id = null;
		fire('job_1', 'job.identity_updated');
		expect(handler).toHaveBeenCalledTimes(2);
		off();
		id = 'job_1';
		fire('job_1', 'job.identity_updated');
		expect(handler).toHaveBeenCalledTimes(2);
	});
});
