// Writes text to the clipboard and holds a short-lived "copied" flag for
// the button's label.
export class ClipboardCopy {
	/** The last write succeeded less than 1500 ms ago. */
	copied = $state(false);
	#timer: ReturnType<typeof setTimeout> | null = null;

	/**
	 * Writes the text, then sets `copied` for 1500 ms. Does nothing without a
	 * clipboard.
	 */
	copy = (text: string): void => {
		const clipboard = typeof navigator === 'undefined' ? undefined : navigator.clipboard;
		if (!clipboard) return;
		clipboard
			.writeText(text)
			.then(() => {
				this.copied = true;
				if (this.#timer) clearTimeout(this.#timer);
				this.#timer = setTimeout(() => (this.copied = false), 1500);
			})
			.catch(() => {
				/* no clipboard access (http, permissions): the label just stays "Copy" */
			});
	};
}
