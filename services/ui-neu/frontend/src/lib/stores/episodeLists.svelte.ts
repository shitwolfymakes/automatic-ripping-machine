// The episode lists the per-row picker offers, by season, for one job
// and source: each season fetched once, and all dropped when the job or
// source changes.
import { SvelteMap } from 'svelte/reactivity';
import { fetchEpisodes, type EpisodeSource } from '$lib/api/identity';
import type { EpisodeSummary } from '$lib/types/api.gen';

export class EpisodeLists {
	// The lists by season, for the job and source in #for.
	#bySeason = $state.raw<Map<number, EpisodeSummary[]>>(new SvelteMap());
	#for = '';
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- fetch bookkeeping, never read reactively
	readonly #requested = new Set<number>();

	/** The season's episodes; [] until its list loads. */
	get = (season: number): EpisodeSummary[] => this.#bySeason.get(season) ?? [];

	/** Fetches the list of each season not yet asked for, for the job and
	 * source; a new job or source first drops the lists held. A season
	 * whose fetch failed is asked for again on the next call. */
	want = (jobId: string, source: EpisodeSource, seasons: Iterable<number>): void => {
		const key = `${jobId}:${source}`;
		if (key !== this.#for) {
			this.#for = key;
			this.#requested.clear();
			this.#bySeason = new SvelteMap();
		}
		for (const season of seasons) {
			if (this.#requested.has(season)) continue;
			this.#requested.add(season);
			fetchEpisodes(jobId, source, season).then(
				(r) => {
					if (this.#for !== key) return;
					this.#bySeason = new SvelteMap(this.#bySeason).set(season, r.episodes ?? []);
				},
				() => {
					if (this.#for === key) this.#requested.delete(season);
				}
			);
		}
	};

	/** Drops every list, for a panel handed another job. */
	reset = (): void => {
		this.#bySeason = new SvelteMap();
		this.#for = '';
		this.#requested.clear();
	};
}
