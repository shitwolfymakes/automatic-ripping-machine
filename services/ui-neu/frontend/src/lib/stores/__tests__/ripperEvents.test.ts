import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { WSEnvelope } from '$lib/api/ws';

// Mock the WS client. subscribe() captures the handler so tests can inject
// envelopes, and returns a spy unsubscribe.
const subscribeMock = vi.fn();
const startMock = vi.fn();
const unsubscribeSpy = vi.fn();
let capturedHandler: ((env: WSEnvelope) => void) | null = null;
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: (topic: string, handler: (env: WSEnvelope) => void) => {
			capturedHandler = handler;
			return subscribeMock(topic, handler);
		},
		start: () => startMock(),
		stop: vi.fn()
	}
}));

import { startRipperEvents, stopRipperEvents, onRipperEvent } from '$lib/stores/ripperEvents.svelte';

let eventCounter = 0;
function eventEnv(
	jobId: string | null,
	payload: Record<string, unknown> = {},
	eventType = 'rip.completed'
): WSEnvelope {
	eventCounter += 1;
	return {
		op: 'event',
		event_id: `evt_${eventCounter}`,
		event_type: eventType,
		emitted_at: 'now',
		topic: 'ripper.events',
		job_id: jobId,
		track_id: null,
		payload
	};
}

function emit(env: WSEnvelope): void {
	if (capturedHandler === null) throw new Error('startRipperEvents not called');
	capturedHandler(env);
}

describe('ripperEvents store', () => {
	const offs: Array<() => void> = [];

	beforeEach(() => {
		subscribeMock.mockReset();
		subscribeMock.mockReturnValue(unsubscribeSpy);
		startMock.mockReset();
		unsubscribeSpy.mockReset();
		capturedHandler = null;
		vi.useFakeTimers();
	});

	afterEach(() => {
		for (const off of offs.splice(0)) off();
		stopRipperEvents();
		vi.useRealTimers();
	});

	function listen(): ReturnType<typeof vi.fn> {
		const listener = vi.fn();
		offs.push(onRipperEvent(listener));
		return listener;
	}

	it('one event -> one listener call with the job id, after the debounce window', () => {
		startRipperEvents();
		const listener = listen();
		emit(eventEnv('job_a'));
		expect(listener).not.toHaveBeenCalled(); // not before the window
		vi.advanceTimersByTime(300);
		expect(listener).toHaveBeenCalledTimes(1);
		expect(listener).toHaveBeenCalledWith(new Set(['job_a']), new Map([['job_a', new Set(['rip.completed'])]]));
	});

	it('a burst inside one window coalesces to a single call with the union of ids', () => {
		startRipperEvents();
		const listener = listen();
		emit(eventEnv('job_a', {}, 'track.completed'));
		emit(eventEnv('job_a', {}, 'track.completed'));
		emit(eventEnv('job_a', {}, 'rip.completed'));
		emit(eventEnv('job_b', {}, 'rip.started'));
		vi.advanceTimersByTime(300);
		expect(listener).toHaveBeenCalledTimes(1);
		expect(listener).toHaveBeenCalledWith(
			new Set(['job_a', 'job_b']),
			new Map([
				['job_a', new Set(['track.completed', 'rip.completed'])],
				['job_b', new Set(['rip.started'])]
			])
		);
	});

	it('events straddling two windows produce two correctly-partitioned calls', () => {
		startRipperEvents();
		const listener = listen();
		emit(eventEnv('job_a'));
		vi.advanceTimersByTime(300);
		emit(eventEnv('job_b'));
		vi.advanceTimersByTime(300);
		expect(listener).toHaveBeenCalledTimes(2);
		expect(listener).toHaveBeenNthCalledWith(1, new Set(['job_a']), new Map([['job_a', new Set(['rip.completed'])]]));
		expect(listener).toHaveBeenNthCalledWith(2, new Set(['job_b']), new Map([['job_b', new Set(['rip.completed'])]]));
	});

	it('an unregistered listener receives no further calls', () => {
		startRipperEvents();
		const listener = vi.fn();
		const off = onRipperEvent(listener);
		emit(eventEnv('job_a'));
		vi.advanceTimersByTime(300);
		expect(listener).toHaveBeenCalledTimes(1);
		off();
		emit(eventEnv('job_b'));
		vi.advanceTimersByTime(300);
		expect(listener).toHaveBeenCalledTimes(1);
	});

	it('a throwing listener does not prevent the next listener from firing', () => {
		startRipperEvents();
		const bad = vi.fn(() => {
			throw new Error('boom');
		});
		const good = vi.fn();
		offs.push(onRipperEvent(bad));
		offs.push(onRipperEvent(good));
		emit(eventEnv('job_a'));
		vi.advanceTimersByTime(300);
		expect(bad).toHaveBeenCalledTimes(1);
		expect(good).toHaveBeenCalledTimes(1);
	});

	it('start is subscribe-once; stop unsubscribes and clears pending ids', () => {
		startRipperEvents();
		startRipperEvents();
		expect(subscribeMock).toHaveBeenCalledTimes(2);
		expect(subscribeMock).toHaveBeenCalledWith('ripper.events', expect.any(Function));
		expect(subscribeMock).toHaveBeenCalledWith('transcode.events', expect.any(Function));
		const listener = listen();
		emit(eventEnv('job_a'));
		stopRipperEvents();
		expect(unsubscribeSpy).toHaveBeenCalledTimes(2);
		vi.advanceTimersByTime(300);
		expect(listener).not.toHaveBeenCalled(); // pending ids were cleared
	});

	it('job id sourcing: top-level, payload fallback, neither -> dropped', () => {
		startRipperEvents();
		const listener = listen();
		emit(eventEnv('job_top'));
		emit(eventEnv(null, { job_id: 'job_payload' }));
		emit(eventEnv(null, {})); // no id anywhere — dropped
		vi.advanceTimersByTime(300);
		expect(listener).toHaveBeenCalledTimes(1);
		expect(listener).toHaveBeenCalledWith(
			new Set(['job_top', 'job_payload']),
			new Map([
				['job_top', new Set(['rip.completed'])],
				['job_payload', new Set(['rip.completed'])]
			])
		);
	});

	it('a new window starts with empty event-type sets', () => {
		startRipperEvents();
		const listener = listen();
		emit(eventEnv('job_a', {}, 'rip.identify_resolved'));
		vi.advanceTimersByTime(300);
		emit(eventEnv('job_a', {}, 'job.identity_updated'));
		vi.advanceTimersByTime(300);
		expect(listener.mock.calls[0][1]).toEqual(new Map([['job_a', new Set(['rip.identify_resolved'])]]));
		expect(listener.mock.calls[1][1]).toEqual(new Map([['job_a', new Set(['job.identity_updated'])]]));
	});
});
