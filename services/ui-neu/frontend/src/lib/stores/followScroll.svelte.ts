// Follow new lines while the user hasn't scrolled up; while paused, count the
// lines that arrived so the status bar can say how many are waiting. The
// terminal div unmounts while collapsed, so a newly bound one (first render
// or expand) starts following again at the latest line.
export class FollowScroll {
	/**
	 * New lines scroll the view to the bottom; false once the user scrolls
	 * up.
	 */
	following = $state(true);
	/** Lines that arrived while paused. */
	newWhilePaused = $state(0);
	#seen = 0;
	#bound: HTMLElement | null = null;
	readonly #view: () => HTMLElement | null;

	constructor(view: () => HTMLElement | null) {
		this.#view = view;
	}

	/**
	 * Follows while the view is within 24px of the bottom, and pauses
	 * otherwise.
	 */
	onScroll = (): void => {
		this.following = this.#isAtBottom();
	};

	/** Follows again and scrolls the view to the bottom. */
	jumpToLatest = (): void => {
		this.following = true;
		this.#scrollToBottom();
	};

	/**
	 * The effect's body: takes the line count, the bound view and whether the
	 * effect saw following on. Scrolls and clears the count while following,
	 * counts the new lines while paused, and starts following when a new view
	 * binds while paused.
	 */
	sync = (total: number, view: HTMLElement | null, follow: boolean): void => {
		this.#seen = Math.min(this.#seen, total);
		if (view !== this.#bound) {
			this.#bound = view;
			if (view !== null && !follow) {
				// re-runs this effect with follow on, which scrolls
				this.following = true;
				this.#seen = total;
				return;
			}
		}
		if (follow) {
			this.newWhilePaused = 0;
			this.#scrollToBottom();
		} else if (total > this.#seen) {
			this.newWhilePaused += total - this.#seen;
		}
		this.#seen = total;
	};

	readonly #isAtBottom = (): boolean => {
		const view = this.#view();
		if (view === null) return true;
		return view.scrollHeight - view.scrollTop - view.clientHeight < 24;
	};

	readonly #scrollToBottom = (): void => {
		const view = this.#view();
		if (view === null) return;
		view.scrollTop = view.scrollHeight;
	};
}
