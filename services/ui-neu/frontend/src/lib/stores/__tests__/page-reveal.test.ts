import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PageRevealState, REVEAL_CAP_MS, REVEAL_SETTLE_MS } from '../page-reveal.svelte';

describe('PageRevealState', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('reveals after the settle time when nothing reports pending', () => {
		const r = new PageRevealState();
		r.begin();
		expect(r.revealed).toBe(false);
		vi.advanceTimersByTime(REVEAL_SETTLE_MS);
		expect(r.revealed).toBe(true);
	});

	it('waits for every pending panel', () => {
		const r = new PageRevealState(10, 1000);
		const a = Symbol('a');
		const b = Symbol('b');
		r.begin();
		r.report(a, true);
		r.report(b, true);
		vi.advanceTimersByTime(50);
		r.report(a, false);
		vi.advanceTimersByTime(50);
		expect(r.revealed).toBe(false);
		r.report(b, false);
		vi.advanceTimersByTime(10);
		expect(r.revealed).toBe(true);
	});

	it('a panel that reports during the settle time holds the reveal', () => {
		const r = new PageRevealState(10, 1000);
		const a = Symbol('a');
		r.begin();
		vi.advanceTimersByTime(5);
		r.report(a, true);
		vi.advanceTimersByTime(100);
		expect(r.revealed).toBe(false);
	});

	it('reveals at the cap even with panels still pending', () => {
		const r = new PageRevealState();
		r.begin();
		r.report(Symbol('slow'), true);
		vi.advanceTimersByTime(REVEAL_CAP_MS - 1);
		expect(r.revealed).toBe(false);
		vi.advanceTimersByTime(1);
		expect(r.revealed).toBe(true);
	});

	it('stays revealed when a panel goes pending again later', () => {
		const r = new PageRevealState(10, 1000);
		r.begin();
		vi.advanceTimersByTime(10);
		r.report(Symbol('poll'), true);
		vi.advanceTimersByTime(1000);
		expect(r.revealed).toBe(true);
	});

	it('begin hides again for the next page', () => {
		const r = new PageRevealState(10, 1000);
		r.begin();
		vi.advanceTimersByTime(10);
		r.begin();
		expect(r.revealed).toBe(false);
	});

	it('dispose cancels the timers', () => {
		const r = new PageRevealState(10, 1000);
		r.begin();
		r.dispose();
		vi.advanceTimersByTime(5000);
		expect(r.revealed).toBe(false);
	});
});
