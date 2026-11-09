// The help page's search: the query, its hits and the search index, which is
// loaded on first use and kept.
import type MiniSearch from 'minisearch';
import { loadDocsSearch, searchDocs, type DocsSearchHit } from '$lib/docs/api';

export class HelpSearch {
	query = $state('');
	hits = $state<DocsSearchHit[]>([]);
	#index: MiniSearch | null = null;

	// Takes the value from the event rather than bind:value, so the query is
	// never read before the binding has updated it.
	run = async (value: string): Promise<void> => {
		this.query = value;
		if (!this.query.trim()) {
			this.hits = [];
			return;
		}
		try {
			this.#index ??= await loadDocsSearch();
			this.hits = searchDocs(this.#index, this.query);
		} catch {
			console.warn('help: search.json unavailable');
			this.hits = [];
		}
	};

	clear = (): void => {
		this.query = '';
		this.hits = [];
	};
}
