// The rows a settings card has a request in flight for, so it can disable
// their controls until the request settles.
import { SvelteSet } from 'svelte/reactivity';

export class PendingKeys {
	#keys = new SvelteSet<string>();

	/** Whether a request for `key` is in flight. */
	has(key: string): boolean {
		return this.#keys.has(key);
	}

	/**
	 * Runs `task` with `key` marked in flight, and clears the mark once it
	 * settles, whether it resolved or threw.
	 */
	async run<T>(key: string, task: () => Promise<T>): Promise<T> {
		this.#keys.add(key);
		try {
			return await task();
		} finally {
			this.#keys.delete(key);
		}
	}
}
