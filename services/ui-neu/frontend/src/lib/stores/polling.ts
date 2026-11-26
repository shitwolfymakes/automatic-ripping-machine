import { writable, type Readable } from 'svelte/store';
import { browser } from '$app/environment';
import { errorMessage } from '$lib/utils/errors';

interface PollingStore<T> extends Readable<T> {
	refresh: () => Promise<void>;
	start: () => void;
	stop: () => void;
	update: (fn: (current: T) => T) => void;
	readonly loading: Readable<boolean>;
	readonly error: Readable<string | null>;
	readonly initialized: Readable<boolean>;
}

export function createPollingStore<T>(
	fetcher: () => Promise<T>,
	initialValue: T,
	intervalMs: number = 5000
): PollingStore<T> {
	const data = writable<T>(initialValue);
	const loading = writable<boolean>(false);
	const error = writable<string | null>(null);
	const initialized = writable<boolean>(false);
	let timer: ReturnType<typeof setInterval> | null = null;
	let refreshing = false;
	// Counts local update() calls, so a fetch can tell whether one landed
	// while it was in flight.
	let localWrites = 0;

	async function refresh() {
		if (refreshing) return;
		refreshing = true;
		loading.set(true);
		const writesAtStart = localWrites;
		try {
			const result = await fetcher();
			// A local update() made while the fetch was in flight is newer than
			// its result, so the result is dropped; the next poll reconciles.
			if (writesAtStart === localWrites) data.set(result);
			error.set(null);
			initialized.set(true);
		} catch (e) {
			error.set(errorMessage(e, 'Unknown error'));
		} finally {
			loading.set(false);
			refreshing = false;
		}
	}

	function startTimer() {
		stopTimer();
		timer = setInterval(refresh, intervalMs);
	}

	function stopTimer() {
		if (timer) {
			clearInterval(timer);
			timer = null;
		}
	}

	function onVisibilityChange() {
		if (document.hidden) {
			stopTimer();
		} else {
			refresh();
			startTimer();
		}
	}

	function start() {
		if (!browser) return;
		refresh();
		startTimer();
		document.addEventListener('visibilitychange', onVisibilityChange);
	}

	function stop() {
		stopTimer();
		if (browser) {
			document.removeEventListener('visibilitychange', onVisibilityChange);
		}
	}

	return {
		subscribe: data.subscribe,
		refresh,
		start,
		stop,
		update: (fn: (current: T) => T) => {
			localWrites++;
			data.update(fn);
		},
		loading: { subscribe: loading.subscribe },
		error: { subscribe: error.subscribe },
		initialized: { subscribe: initialized.subscribe }
	};
}
