import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { WSEnvelope } from '$lib/api/ws';

// Mock the WS client so reconcileSubscriptions can be exercised without a real
// socket. subscribe() records the topic and returns a spy unsubscribe.
const subscribeMock = vi.fn();
const startMock = vi.fn();
const stopMock = vi.fn();
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: (topic: string, handler: (env: WSEnvelope) => void) =>
			subscribeMock(topic, handler),
		start: () => startMock(),
		stop: () => stopMock()
	}
}));

import { ripProgress, onProgress, reconcileSubscriptions, stopWS, formatEta } from '$lib/stores/rips.svelte';

function progressEnv(jobId: string, trackId: string, pct: number): WSEnvelope {
	return {
		op: 'event',
		event_id: `evt_${pct}`,
		event_type: 'ripper.progress',
		emitted_at: 'now',
		topic: `ripper.progress.${jobId}`,
		job_id: jobId,
		track_id: trackId,
		payload: { track_id: trackId, progress_pct: pct }
	};
}

describe('rips store', () => {
	beforeEach(() => {
		subscribeMock.mockReset();
		subscribeMock.mockImplementation(() => vi.fn());
		startMock.mockReset();
		stopMock.mockReset();
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-05-05T00:00:00Z'));
	});

	afterEach(() => {
		stopWS();
		vi.useRealTimers();
	});

	it('first tick of a track sets progress and leaves ETA null', () => {
		onProgress('job_a', progressEnv('job_a', 'trk_1', 5));
		expect(ripProgress.value['job_a']).toEqual({
			track_id: 'trk_1',
			progress_pct: 5,
			eta_seconds: null
		});
	});

	it('computes ETA once enough has elapsed and progressed', () => {
		onProgress('job_a', progressEnv('job_a', 'trk_1', 5));
		// +10s, arrive at 25% — 20% in 10s → 2%/s → 75% remaining → ~38s.
		vi.advanceTimersByTime(10_000);
		onProgress('job_a', progressEnv('job_a', 'trk_1', 25));
		expect(ripProgress.value['job_a'].progress_pct).toBe(25);
		expect(ripProgress.value['job_a'].eta_seconds).toBe(38);
	});

	it('keeps ETA null when the elapsed window is too short', () => {
		onProgress('job_a', progressEnv('job_a', 'trk_1', 5));
		vi.advanceTimersByTime(2_000); // below ETA_MIN_ELAPSED_MS
		onProgress('job_a', progressEnv('job_a', 'trk_1', 9));
		expect(ripProgress.value['job_a'].eta_seconds).toBeNull();
	});

	it('resets the ETA baseline when the track changes', () => {
		onProgress('job_a', progressEnv('job_a', 'trk_1', 5));
		vi.advanceTimersByTime(10_000);
		onProgress('job_a', progressEnv('job_a', 'trk_1', 50));
		expect(ripProgress.value['job_a'].eta_seconds).not.toBeNull();
		// New track → first tick blanks ETA again.
		onProgress('job_a', progressEnv('job_a', 'trk_2', 0));
		expect(ripProgress.value['job_a']).toEqual({
			track_id: 'trk_2',
			progress_pct: 0,
			eta_seconds: null
		});
	});

	it('resets the baseline on a >1pp backward jump under a stable track', () => {
		onProgress('job_a', progressEnv('job_a', 'trk_1', 40));
		vi.advanceTimersByTime(10_000);
		onProgress('job_a', progressEnv('job_a', 'trk_1', 30)); // backward
		expect(ripProgress.value['job_a'].eta_seconds).toBeNull();
		expect(ripProgress.value['job_a'].progress_pct).toBe(30);
	});

	it('reconcileSubscriptions subscribes per ripping job', () => {
		reconcileSubscriptions(['job_a', 'job_b']);
		expect(subscribeMock).toHaveBeenCalledTimes(2);
		expect(subscribeMock).toHaveBeenCalledWith('ripper.progress.job_a', expect.any(Function));
		expect(subscribeMock).toHaveBeenCalledWith('ripper.progress.job_b', expect.any(Function));
	});

	it('reconcileSubscriptions drops state + unsubscribes jobs no longer ripping', () => {
		const unsub = vi.fn();
		subscribeMock.mockReturnValue(unsub);
		reconcileSubscriptions(['job_a']);
		onProgress('job_a', progressEnv('job_a', 'trk_1', 30));
		expect(ripProgress.value['job_a']).toBeDefined();

		reconcileSubscriptions([]); // job_a left the active set
		expect(unsub).toHaveBeenCalled();
		expect(ripProgress.value['job_a']).toBeUndefined();
	});

	it('reconcileSubscriptions is idempotent for an unchanged set', () => {
		reconcileSubscriptions(['job_a']);
		reconcileSubscriptions(['job_a']);
		expect(subscribeMock).toHaveBeenCalledTimes(1); // not re-subscribed
	});
});

describe('formatEta', () => {
	it('returns "< 1m" for sub-minute', () => {
		expect(formatEta(45)).toBe('< 1m');
	});
	it('returns minutes+seconds for under 5 minutes', () => {
		expect(formatEta(150)).toBe('2m 30s');
	});
	it('returns whole minutes for 5+ minute ETAs', () => {
		expect(formatEta(720)).toBe('12m');
	});
	it('returns hours+minutes when over an hour', () => {
		expect(formatEta(4_350)).toBe('1h 12m');
	});
});
