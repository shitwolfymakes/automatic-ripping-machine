import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SkeletonGate } from '../skeleton-gate.svelte';

describe('SkeletonGate', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	const gate = (delay = 300, minShow = 300) => new SkeletonGate(delay, minShow, () => Date.now());

	it('never shows for a load that finishes inside the delay', () => {
		const g = gate();
		g.update(true);
		vi.advanceTimersByTime(299);
		g.update(false);
		vi.advanceTimersByTime(1000);
		expect(g.shown).toBe(false);
	});

	it('shows once the delay passes', () => {
		const g = gate();
		g.update(true);
		vi.advanceTimersByTime(300);
		expect(g.shown).toBe(true);
	});

	it('keeps a shown skeleton up for the minimum time', () => {
		const g = gate();
		g.update(true);
		vi.advanceTimersByTime(300);
		vi.advanceTimersByTime(50);
		g.update(false);
		expect(g.shown).toBe(true);
		vi.advanceTimersByTime(249);
		expect(g.shown).toBe(true);
		vi.advanceTimersByTime(1);
		expect(g.shown).toBe(false);
	});

	it('hides at once when the minimum time has already passed', () => {
		const g = gate();
		g.update(true);
		vi.advanceTimersByTime(300);
		vi.advanceTimersByTime(400);
		g.update(false);
		expect(g.shown).toBe(false);
	});

	it('stays up when pending comes back during the hold', () => {
		const g = gate();
		g.update(true);
		vi.advanceTimersByTime(300);
		g.update(false);
		g.update(true);
		vi.advanceTimersByTime(1000);
		expect(g.shown).toBe(true);
	});

	it('repeated updates do not restart the delay or the hold', () => {
		const g = gate();
		g.update(true);
		vi.advanceTimersByTime(200);
		g.update(true);
		vi.advanceTimersByTime(100);
		expect(g.shown).toBe(true);
		g.update(false);
		vi.advanceTimersByTime(200);
		g.update(false);
		vi.advanceTimersByTime(100);
		expect(g.shown).toBe(false);
	});

	it('shows at once with a zero delay', () => {
		const g = gate(0);
		g.update(true);
		expect(g.shown).toBe(true);
	});

	it('dispose cancels a pending show', () => {
		const g = gate();
		g.update(true);
		g.dispose();
		vi.advanceTimersByTime(1000);
		expect(g.shown).toBe(false);
	});

	it('uses performance.now by default', () => {
		const g = new SkeletonGate(0, 300);
		g.update(true);
		g.update(false);
		expect(g.shown).toBe(true);
		vi.advanceTimersByTime(300);
		expect(g.shown).toBe(false);
	});
});
