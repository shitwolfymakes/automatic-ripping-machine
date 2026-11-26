import { describe, it, expect, vi, afterEach } from 'vitest';
import { get } from 'svelte/store';

// Server-side rendering: start and stop leave the fetcher, the timer and the
// document alone.
vi.mock('$app/environment', () => ({ browser: false }));

import { createPollingStore } from '../polling';

afterEach(() => {
	vi.restoreAllMocks();
});

describe('createPollingStore without a browser', () => {
	it('start neither fetches nor listens, and stop does not touch the document', () => {
		const fetcher = vi.fn().mockResolvedValue('fetched');
		const add = vi.spyOn(document, 'addEventListener');
		const remove = vi.spyOn(document, 'removeEventListener');
		const store = createPollingStore(fetcher, 'initial');

		store.start();
		store.stop();

		expect(fetcher).not.toHaveBeenCalled();
		expect(add).not.toHaveBeenCalledWith('visibilitychange', expect.any(Function));
		expect(remove).not.toHaveBeenCalledWith('visibilitychange', expect.any(Function));
		expect(get(store)).toBe('initial');
	});
});
