// A polling store for page tests that mock a singleton store module. reset()
// swaps in a new store, so one test's data and loaded flag never carry into
// the next. Components read it exactly as they read the real store.
import { createPollingStore, type PollingStore } from '$lib/stores/polling';

export interface ResettablePollingStore<T> extends PollingStore<T> {
	reset: () => void;
}

export function resettablePollingStore<T>(fetcher: () => Promise<T>, initial: T): ResettablePollingStore<T> {
	let current = createPollingStore(fetcher, initial);
	return {
		subscribe: (run, invalidate) => current.subscribe(run, invalidate),
		refresh: () => current.refresh(),
		refreshIfIdle: () => current.refreshIfIdle(),
		start: () => current.start(),
		stop: () => current.stop(),
		update: (fn) => current.update(fn),
		get loading() {
			return current.loading;
		},
		get error() {
			return current.error;
		},
		get initialized() {
			return current.initialized;
		},
		reset: () => {
			current.stop();
			current = createPollingStore(fetcher, initial);
		}
	};
}
