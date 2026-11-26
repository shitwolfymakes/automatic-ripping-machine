// When a loading skeleton is on screen. A load that finishes within `delay`
// never shows one, and a skeleton that does show stays for at least `minShow`
// from when it came into view, so a load finishing just after the delay does
// not flash it for a frame. While the area is out of view (a page still
// hidden by PageReveal), nobody can see the skeleton, so it drops as soon as
// the load finishes.

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
	#visible = true;
	/** When the skeleton came into view; null while nobody has seen it. */
	#seenAt: number | null = null;

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

	/** Feed whether the area is in view. The minimum show counts from when a shown skeleton comes into view. */
	setVisible(visible: boolean): void {
		this.#visible = visible;
		if (visible && this.shown && this.#seenAt === null) this.#seenAt = this.#now();
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
		this.#seenAt = this.#visible ? this.#now() : null;
	}

	#release(): void {
		this.#clearDelay();
		if (!this.shown || this.#holdTimer) return;
		const remaining = this.#seenAt === null ? 0 : this.#minShow - (this.#now() - this.#seenAt);
		if (remaining <= 0) {
			this.#hide();
			return;
		}
		this.#holdTimer = setTimeout(() => {
			this.#holdTimer = null;
			this.#hide();
		}, remaining);
	}

	#hide(): void {
		this.shown = false;
		this.#seenAt = null;
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
