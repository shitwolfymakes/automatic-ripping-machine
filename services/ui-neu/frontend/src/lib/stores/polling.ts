import { writable, type Readable } from 'svelte/store';
import { browser } from '$app/environment';
import { errorMessage } from '$lib/utils/errors';

export interface PollingStore<T> extends Readable<T> {
	refresh: () => Promise<void>;
	/** Fetch now unless a fetch is already in flight (whose result is just as fresh). */
	refreshIfIdle: () => void;
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
	let inFlight: Promise<void> | null = null;
	// A refresh() asked for while a fetch is in flight: its data may have
	// changed after that fetch read it, so one more fetch follows.
	let again = false;
	// Counts local update() calls, so a fetch can tell whether one landed
	// while it was in flight.
	let localWrites = 0;

	async function fetchOnce() {
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
		}
	}

	function run(): Promise<void> {
		inFlight = (async () => {
			do {
				again = false;
				await fetchOnce();
			} while (again);
			inFlight = null;
		})();
		return inFlight;
	}

	/** Fetch now. Asked for mid-fetch, it runs once more after that fetch. */
	function refresh(): Promise<void> {
		if (inFlight) {
			again = true;
			return inFlight;
		}
		return run();
	}

	/** The timer's fetch, and refreshIfIdle(): skipped while one is in flight, so a slow backend is not hit back to back. */
	function refreshIfIdle() {
		if (!inFlight) void run();
	}

	function startTimer() {
		stopTimer();
		timer = setInterval(refreshIfIdle, intervalMs);
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
		refreshIfIdle,
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
