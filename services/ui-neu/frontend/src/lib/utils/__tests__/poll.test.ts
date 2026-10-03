import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { usePoll } from '../poll';

describe('usePoll', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => {
		vi.useRealTimers();
		Object.defineProperty(document, 'hidden', { value: false, configurable: true });
	});

	it('runs now, then every interval, until stopped', async () => {
		const fn = vi.fn();
		const p = usePoll(fn, 1000);
		await vi.advanceTimersByTimeAsync(0);
		expect(fn).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1000);
		expect(fn).toHaveBeenCalledTimes(2);
		p.stop();
		await vi.advanceTimersByTimeAsync(5000);
		expect(fn).toHaveBeenCalledTimes(2);
	});

	it('skips ticks while the tab is hidden and survives a throwing fn', async () => {
		Object.defineProperty(document, 'hidden', { value: true, configurable: true });
		const fn = vi.fn(() => {
			throw new Error('boom');
		});
		const p = usePoll(fn, 1000);
		await vi.advanceTimersByTimeAsync(3000);
		expect(fn).not.toHaveBeenCalled();
		Object.defineProperty(document, 'hidden', { value: false, configurable: true });
		await vi.advanceTimersByTimeAsync(1000);
		expect(fn).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(1000);
		expect(fn).toHaveBeenCalledTimes(2);
		p.stop();
	});
});
