import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/environment', () => ({ browser: true }));

import { createPollingStore } from '../polling';

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

describe('createPollingStore', () => {
	it('has correct initial state', () => {
		const store = createPollingStore(() => Promise.resolve('data'), 'initial');
		expect(get(store)).toBe('initial');
		expect(get(store.loading)).toBe(false);
		expect(get(store.error)).toBe(null);
		expect(get(store.initialized)).toBe(false);
	});

	it('refresh() updates data on success', async () => {
		const fetcher = vi.fn().mockResolvedValue('fetched');
		const store = createPollingStore(fetcher, 'initial');

		await store.refresh();

		expect(get(store)).toBe('fetched');
		expect(get(store.error)).toBe(null);
		expect(get(store.initialized)).toBe(true);
		expect(get(store.loading)).toBe(false);
	});

	it('refresh() sets error on failure', async () => {
		const fetcher = vi.fn().mockRejectedValue(new Error('Network error'));
		const store = createPollingStore(fetcher, 'initial');

		await store.refresh();

		expect(get(store)).toBe('initial');
		expect(get(store.error)).toBe('Network error');
		expect(get(store.loading)).toBe(false);
	});

	it('refresh() sets "Unknown error" for non-Error throws', async () => {
		const fetcher = vi.fn().mockRejectedValue('string error');
		const store = createPollingStore(fetcher, 'initial');

		await store.refresh();

		expect(get(store.error)).toBe('Unknown error');
	});

	/** A fetcher whose calls each wait for `release()`, resolving to 'r1', 'r2', ... */
	function heldFetcher() {
		const pending: (() => void)[] = [];
		let n = 0;
		const fetcher = vi.fn(
			() =>
				new Promise<string>((r) => {
					const value = `r${++n}`;
					pending.push(() => r(value));
				})
		);
		const release = async () => {
			pending.shift()?.();
			await vi.advanceTimersByTimeAsync(0);
		};
		return { fetcher, release };
	}

	it('refresh() asked for mid-fetch fetches once more after it, however many times it is asked', async () => {
		const { fetcher, release } = heldFetcher();
		const store = createPollingStore(fetcher, 'initial');

		const p1 = store.refresh();
		const p2 = store.refresh();
		void store.refresh();
		expect(fetcher).toHaveBeenCalledTimes(1);

		await release();
		expect(fetcher).toHaveBeenCalledTimes(2);
		expect(get(store)).toBe('r1');

		await release();
		await Promise.all([p1, p2]);
		expect(fetcher).toHaveBeenCalledTimes(2);
		expect(get(store)).toBe('r2');

		// Nothing in flight now: the next refresh() fetches straight away.
		void store.refresh();
		expect(fetcher).toHaveBeenCalledTimes(3);
		await release();
		expect(get(store)).toBe('r3');
	});

	it('a timer tick during a slow fetch is skipped, not queued', async () => {
		const { fetcher, release } = heldFetcher();
		const store = createPollingStore(fetcher, 'initial', 1000);

		store.start();
		await vi.advanceTimersByTimeAsync(2500);
		expect(fetcher).toHaveBeenCalledTimes(1);

		await release();
		expect(fetcher).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(500);
		expect(fetcher).toHaveBeenCalledTimes(2);
		store.stop();
	});

	it('start() calls refresh and begins polling', async () => {
		const fetcher = vi.fn().mockResolvedValue('data');
		const store = createPollingStore(fetcher, 'initial', 1000);

		store.start();
		await vi.advanceTimersByTimeAsync(0);
		expect(fetcher).toHaveBeenCalledTimes(1);

		await vi.advanceTimersByTimeAsync(1000);
		expect(fetcher).toHaveBeenCalledTimes(2);

		await vi.advanceTimersByTimeAsync(1000);
		expect(fetcher).toHaveBeenCalledTimes(3);

		store.stop();
	});

	it('stop() clears the timer', async () => {
		const fetcher = vi.fn().mockResolvedValue('data');
		const store = createPollingStore(fetcher, 'initial', 1000);

		store.start();
		await vi.advanceTimersByTimeAsync(0);
		expect(fetcher).toHaveBeenCalledTimes(1);

		store.stop();

		await vi.advanceTimersByTimeAsync(5000);
		expect(fetcher).toHaveBeenCalledTimes(1);
	});

	it('update() modifies the store data', () => {
		const store = createPollingStore(() => Promise.resolve(0), 5);
		store.update((n) => n + 1);
		expect(get(store)).toBe(6);
	});

	it('drops a fetch result that started before an update()', async () => {
		let resolve!: (v: number) => void;
		const fetcher = vi.fn().mockReturnValueOnce(new Promise<number>((r) => (resolve = r)));
		const store = createPollingStore(fetcher, 0);
		const pending = store.refresh();
		store.update(() => 7);
		resolve(1);
		await pending;
		expect(get(store)).toBe(7);
		expect(get(store.loading)).toBe(false);
		expect(get(store.initialized)).toBe(true);
	});

	it('applies a fetch result that started after an update()', async () => {
		const store = createPollingStore(vi.fn().mockResolvedValue(1), 0);
		store.update(() => 7);
		await store.refresh();
		expect(get(store)).toBe(1);
	});

	it('pauses on visibility hidden and resumes on visible', async () => {
		const fetcher = vi.fn().mockResolvedValue('data');
		const store = createPollingStore(fetcher, 'initial', 1000);

		store.start();
		await vi.advanceTimersByTimeAsync(0);
		expect(fetcher).toHaveBeenCalledTimes(1);

		// Simulate tab hidden
		Object.defineProperty(document, 'hidden', { value: true, writable: true });
		document.dispatchEvent(new Event('visibilitychange'));

		await vi.advanceTimersByTimeAsync(5000);
		expect(fetcher).toHaveBeenCalledTimes(1); // timer stopped

		// Simulate tab visible
		Object.defineProperty(document, 'hidden', { value: false, writable: true });
		document.dispatchEvent(new Event('visibilitychange'));

		await vi.advanceTimersByTimeAsync(0);
		expect(fetcher).toHaveBeenCalledTimes(2); // refresh on visible

		store.stop();
	});

	it('clears error on successful refresh after failure', async () => {
		const fetcher = vi.fn().mockRejectedValueOnce(new Error('fail')).mockResolvedValueOnce('ok');
		const store = createPollingStore(fetcher, 'initial');

		await store.refresh();
		expect(get(store.error)).toBe('fail');

		await store.refresh();
		expect(get(store.error)).toBe(null);
		expect(get(store)).toBe('ok');
	});
});
