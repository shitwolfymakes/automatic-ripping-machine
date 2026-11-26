// Page-level reveal: the layout keeps a page's content invisible (laid out,
// opacity 0) until every panel on it has something to show, then fades the
// whole page in at once. Panels report through trackPending. A cap stops a
// slow backend from leaving the page blank; past it, the panels' own
// skeletons take over.
import { getContext, setContext } from 'svelte';
import { SvelteSet } from 'svelte/reactivity';

const KEY = Symbol('page-reveal');

/** How long to wait with nothing pending before revealing, so panels that
 *  mount in the same pass get to report first. */
export const REVEAL_SETTLE_MS = 30;
/** The longest a page stays hidden. */
export const REVEAL_CAP_MS = 1000;

export class PageRevealState {
	revealed = $state(false);

	#pending = new SvelteSet<symbol>();
	#settleMs: number;
	#capMs: number;
	#settleTimer: ReturnType<typeof setTimeout> | null = null;
	#capTimer: ReturnType<typeof setTimeout> | null = null;

	constructor(settleMs = REVEAL_SETTLE_MS, capMs = REVEAL_CAP_MS) {
		this.#settleMs = settleMs;
		this.#capMs = capMs;
	}

	/** Hide for a fresh page and wait for its panels. */
	begin(): void {
		this.dispose();
		this.revealed = false;
		this.#capTimer = setTimeout(() => this.#reveal(), this.#capMs);
		this.#scheduleCheck();
	}

	/** A panel reports whether it still has nothing to show. */
	report(id: symbol, pending: boolean): void {
		if (pending) this.#pending.add(id);
		else this.#pending.delete(id);
		this.#scheduleCheck();
	}

	/** Cancel the timers (teardown, or before a fresh begin). */
	dispose(): void {
		if (this.#settleTimer) clearTimeout(this.#settleTimer);
		if (this.#capTimer) clearTimeout(this.#capTimer);
		this.#settleTimer = null;
		this.#capTimer = null;
	}

	#scheduleCheck(): void {
		if (this.revealed || this.#settleTimer) return;
		this.#settleTimer = setTimeout(() => {
			this.#settleTimer = null;
			if (this.#pending.size === 0) this.#reveal();
		}, this.#settleMs);
	}

	#reveal(): void {
		this.dispose();
		this.revealed = true;
	}
}

export function providePageReveal(state: PageRevealState): void {
	setContext(KEY, state);
}

/**
 * Whether the page is on screen yet, as a reactive getter. Call during
 * component init. Outside a PageReveal it is always true.
 */
export function pageRevealed(): () => boolean {
	const reveal = getContext<PageRevealState | undefined>(KEY);
	return () => reveal?.revealed ?? true;
}

/**
 * Hold the page reveal while `isPending()` is true. Call during component
 * init. Outside a PageReveal (tests, the setup walkthrough) it does nothing.
 */
export function trackPending(isPending: () => boolean): void {
	const reveal = getContext<PageRevealState | undefined>(KEY);
	const id = Symbol('panel');
	$effect(() => {
		const pending = isPending();
		reveal?.report(id, pending);
	});
	$effect(() => () => reveal?.report(id, false));
}
