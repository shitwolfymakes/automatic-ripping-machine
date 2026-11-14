import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PROBE_TIMEOUT_MS, ProbeTimers } from '../settings-probe-timers.svelte';

describe('ProbeTimers', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('shows a started device as probing and not timed out', () => {
		const probes = new ProbeTimers();
		probes.start(['a']);
		expect(probes.isProbing('a')).toBe(true);
		expect(probes.timedOut('a')).toBe(false);
		expect(probes.isProbing('b')).toBe(false);
	});

	it('times a device out once PROBE_TIMEOUT_MS passes', () => {
		const probes = new ProbeTimers();
		probes.start(['a']);
		vi.advanceTimersByTime(PROBE_TIMEOUT_MS);
		expect(probes.isProbing('a')).toBe(false);
		expect(probes.timedOut('a')).toBe(true);
	});

	it('clears the timed-out flag and restarts the timer when started again', () => {
		const probes = new ProbeTimers();
		probes.start(['a']);
		vi.advanceTimersByTime(PROBE_TIMEOUT_MS);
		probes.start(['a']);
		expect(probes.timedOut('a')).toBe(false);
		vi.advanceTimersByTime(PROBE_TIMEOUT_MS - 1);
		expect(probes.isProbing('a')).toBe(true);
		vi.advanceTimersByTime(1);
		expect(probes.timedOut('a')).toBe(true);
	});

	it('restarts a running timer when started again', () => {
		const probes = new ProbeTimers();
		probes.start(['a']);
		vi.advanceTimersByTime(PROBE_TIMEOUT_MS - 1);
		probes.start(['a']);
		vi.advanceTimersByTime(PROBE_TIMEOUT_MS - 1);
		expect(probes.isProbing('a')).toBe(true);
		expect(probes.timedOut('a')).toBe(false);
	});

	it('ends a running probe on stop without marking it timed out', () => {
		const probes = new ProbeTimers();
		probes.start(['a']);
		probes.stop('a');
		expect(probes.isProbing('a')).toBe(false);
		vi.advanceTimersByTime(PROBE_TIMEOUT_MS);
		expect(probes.timedOut('a')).toBe(false);
	});

	it('leaves a timed-out device timed out on stop (the late-probe defect)', () => {
		const probes = new ProbeTimers();
		probes.start(['a']);
		vi.advanceTimersByTime(PROBE_TIMEOUT_MS);
		probes.stop('a');
		expect(probes.timedOut('a')).toBe(true);
	});

	it('does nothing on stop for a device never started', () => {
		const probes = new ProbeTimers();
		probes.stop('a');
		expect(probes.isProbing('a')).toBe(false);
		expect(probes.timedOut('a')).toBe(false);
	});

	it('clears the running timers on dispose so none fires afterwards', () => {
		const probes = new ProbeTimers();
		probes.start(['a', 'b']);
		probes.dispose();
		vi.advanceTimersByTime(PROBE_TIMEOUT_MS);
		expect(probes.timedOut('a')).toBe(false);
		expect(probes.timedOut('b')).toBe(false);
	});
});
