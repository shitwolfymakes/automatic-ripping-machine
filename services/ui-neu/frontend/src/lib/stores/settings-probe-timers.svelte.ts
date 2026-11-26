// Each device's probe on the GPUs card: running until its result arrives or
// the timeout passes, then timed out.

/** How long a probe may run before the card says it couldn't test. */
export const PROBE_TIMEOUT_MS = 120_000;

export class ProbeTimers {
	#timers = $state<Record<string, ReturnType<typeof setTimeout>>>({});
	#timedOut = $state<Record<string, boolean>>({});

	/** Whether the device's probe is running. */
	isProbing(id: string): boolean {
		return Boolean(this.#timers[id]);
	}

	/** Whether the device's last probe ran out of time. */
	timedOut(id: string): boolean {
		return this.#timedOut[id] === true;
	}

	/**
	 * Starts a probe timer for each device, restarting one already running and
	 * clearing the device's timed-out flag. A timer that runs out stops the
	 * probe and marks the device timed out.
	 */
	start(ids: string[]): void {
		const next = { ...this.#timers };
		const timedOut = { ...this.#timedOut };
		for (const id of ids) {
			if (next[id]) clearTimeout(next[id]);
			delete timedOut[id];
			next[id] = setTimeout(() => {
				const { [id]: _t, ...rest } = this.#timers;
				this.#timers = rest;
				this.#timedOut = { ...this.#timedOut, [id]: true };
			}, PROBE_TIMEOUT_MS);
		}
		this.#timers = next;
		this.#timedOut = timedOut;
	}

	/**
	 * Ends the device's probe when its result arrives: stops its timer, if it
	 * has one, and clears its timed-out flag, so a result that arrives after
	 * the timeout still replaces "couldn't test".
	 */
	stop(id: string): void {
		if (this.#timers[id]) {
			clearTimeout(this.#timers[id]);
			const { [id]: _t, ...rest } = this.#timers;
			this.#timers = rest;
		}
		if (this.#timedOut[id]) {
			const { [id]: _f, ...rest } = this.#timedOut;
			this.#timedOut = rest;
		}
	}

	/** Clears every running timer, for when the card goes away. */
	dispose(): void {
		for (const t of Object.values(this.#timers)) clearTimeout(t);
	}
}
