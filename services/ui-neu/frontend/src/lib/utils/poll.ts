/**
 * Run `fn` now and then every `ms`, skipping ticks while the tab is hidden.
 * Errors are swallowed: the caller renders its own error state. Call the
 * returned `stop()` from an effect/onMount cleanup.
 */
export function usePoll(fn: () => Promise<void> | void, ms: number): { stop(): void } {
	let stopped = false;
	let timer: ReturnType<typeof setTimeout> | null = null;
	const tick = async () => {
		if (stopped) return;
		if (typeof document === 'undefined' || !document.hidden) {
			try {
				await fn();
			} catch {
				/* the caller renders its own error state */
			}
		}
		if (!stopped) timer = setTimeout(tick, ms);
	};
	void tick();
	return {
		stop() {
			stopped = true;
			if (timer) clearTimeout(timer);
		}
	};
}
