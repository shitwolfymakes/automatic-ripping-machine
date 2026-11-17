import { describe, it, expect, vi } from 'vitest';
import { get } from 'svelte/store';
import { resettablePollingStore } from '../resettable-polling-store';

vi.mock('$app/environment', () => ({ browser: true }));

describe('resettablePollingStore', () => {
	it('acts as a polling store and reset() starts over from the initial value', async () => {
		const fetcher = vi.fn().mockResolvedValue('fetched');
		const store = resettablePollingStore(fetcher, 'initial');

		store.start();
		await vi.waitFor(() => expect(get(store)).toBe('fetched'));
		expect(get(store.initialized)).toBe(true);
		expect(get(store.loading)).toBe(false);
		expect(get(store.error)).toBeNull();
		store.stop();

		store.update(() => 'local');
		expect(get(store)).toBe('local');

		store.reset();
		expect(get(store)).toBe('initial');
		expect(get(store.initialized)).toBe(false);

		store.refreshIfIdle();
		await store.refresh();
		expect(get(store)).toBe('fetched');
	});
});
