// When a loading skeleton is on screen. A load that finishes within `delay`
// never shows one, and a skeleton that does show stays for at least `minShow`,
// so a load finishing just after the delay does not flash it for a frame.

/** How long a load may take before its skeleton shows. */
export const SKELETON_DELAY_MS = 300;
/** The shortest time a skeleton stays once shown. */
export const SKELETON_MIN_SHOW_MS = 300;

export class SkeletonGate {
	shown = $state(false);

	#delay: number;
	#minShow: number;
	#now: () => number;
	#delayTimer: ReturnType<typeof setTimeout> | null = null;
	#holdTimer: ReturnType<typeof setTimeout> | null = null;
	#shownAt = 0;

	constructor(delay: number, minShow: number, now: () => number = () => performance.now()) {
		this.#delay = delay;
		this.#minShow = minShow;
		this.#now = now;
	}

	/** Feed the current state: true while there is nothing to show yet. */
	update(pending: boolean): void {
		if (pending) this.#arm();
		else this.#release();
	}

	/** Cancel the timers (component teardown). */
	dispose(): void {
		this.#clearDelay();
		this.#clearHold();
	}

	#arm(): void {
		this.#clearHold();
		if (this.shown || this.#delayTimer) return;
		if (this.#delay === 0) {
			this.#show();
			return;
		}
		this.#delayTimer = setTimeout(() => this.#show(), this.#delay);
	}

	#show(): void {
		this.#delayTimer = null;
		this.shown = true;
		this.#shownAt = this.#now();
	}

	#release(): void {
		this.#clearDelay();
		if (!this.shown || this.#holdTimer) return;
		const remaining = this.#minShow - (this.#now() - this.#shownAt);
		if (remaining <= 0) {
			this.shown = false;
			return;
		}
		this.#holdTimer = setTimeout(() => {
			this.#holdTimer = null;
			this.shown = false;
		}, remaining);
	}

	#clearDelay(): void {
		if (this.#delayTimer) clearTimeout(this.#delayTimer);
		this.#delayTimer = null;
	}

	#clearHold(): void {
		if (this.#holdTimer) clearTimeout(this.#holdTimer);
		this.#holdTimer = null;
	}
}
