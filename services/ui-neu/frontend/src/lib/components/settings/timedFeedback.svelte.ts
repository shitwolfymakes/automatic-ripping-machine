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

	/** Shows a message that stays until another replaces it. */
	hold(type: Feedback['type'], message: string): void {
		this.current = { type, message };
	}

	/**
	 * Shows a message, and clears whichever message is up FEEDBACK_MS later.
	 * The timer is never cancelled, so an earlier message's timer can clear a
	 * later message early.
	 */
	show(type: Feedback['type'], message: string): void {
		this.current = { type, message };
		setTimeout(() => {
			this.current = null;
		}, FEEDBACK_MS);
	}
}
