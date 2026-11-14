// The help page's shown doc: the page itself and its load status.
import { fetchDocsPage, DocsNotFoundError, type DocsPage } from '$lib/help/api';

export class HelpDoc {
	doc = $state<DocsPage | null>(null);
	status = $state<'loading' | 'ready' | 'missing' | 'error'>('loading');
	#currentId: () => string;

	constructor(currentId: () => string) {
		this.#currentId = currentId;
	}

	/**
	 * Load the page `id`. A result that settles after the route moved on is
	 * dropped; `afterShow` runs once the page is shown, and anything it throws
	 * lands in the catch like a failed load.
	 */
	load = (id: string, afterShow: () => Promise<void>): Promise<void> => {
		this.status = 'loading';
		return fetchDocsPage(id)
			.then(async (p) => {
				if (id !== this.#currentId()) return;
				this.doc = p;
				this.status = 'ready';
				await afterShow();
			})
			.catch((e) => {
				if (id !== this.#currentId()) return;
				this.doc = null;
				this.status = e instanceof DocsNotFoundError ? 'missing' : 'error';
			});
	};
}
