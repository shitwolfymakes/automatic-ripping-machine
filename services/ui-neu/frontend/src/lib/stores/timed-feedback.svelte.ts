// A settings card's feedback line: a message that clears itself after a few
// seconds, or one that stays.

/** How long a feedback message stays up. */
export const FEEDBACK_MS = 4000;

/** A feedback message and whether it reports a success or an error. */
export interface Feedback {
	type: 'success' | 'error';
	message: string;
}

export class TimedFeedback {
	/** The message showing, or null. */
	current = $state<Feedback | null>(null);
	#timer: ReturnType<typeof setTimeout> | null = null;
	readonly #ms: number;

	/** `ms` is how long a `show` message stays up. */
	constructor(ms: number = FEEDBACK_MS) {
		this.#ms = ms;
	}

	/** Shows a message that stays until another replaces it. */
	hold(type: Feedback['type'], message: string): void {
		this.dispose();
		this.current = { type, message };
	}

	/**
	 * Shows a message and clears it `ms` later. A newer message cancels the
	 * pending clear, so each message stays up for its own full duration.
	 */
	show(type: Feedback['type'], message: string): void {
		this.dispose();
		this.current = { type, message };
		this.#timer = setTimeout(() => {
			this.#timer = null;
			this.current = null;
		}, this.#ms);
	}

	/** Removes the message now and cancels its pending clear. */
	clear(): void {
		this.dispose();
		this.current = null;
	}

	/** Cancels the pending clear; call it when the owning component unmounts. */
	dispose(): void {
		if (this.#timer === null) return;
		clearTimeout(this.#timer);
		this.#timer = null;
	}
}
