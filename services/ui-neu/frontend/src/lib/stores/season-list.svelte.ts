// The seasons a job's episode source lists, fetched once per job and
// source: what the Fix match form and the per-row season selects offer.
import { fetchSeasons, type EpisodeSource } from '$lib/api/identity';

export class SeasonList {
	/** The source's seasons: [] while they load, null when they could not
	 * load. */
	seasons = $state<number[] | null>([]);
	#key = '';

	/** Fetches the job's seasons from the source, unless they are the
	 * ones already loaded or loading. A failure leaves the list null and
	 * lets the next call try again. */
	follow = (jobId: string, source: EpisodeSource): void => {
		const key = `${jobId}:${source}`;
		if (key === this.#key) return;
		this.#key = key;
		this.seasons = [];
		fetchSeasons(jobId, source).then(
			(r) => {
				if (this.#key === key) this.seasons = r.seasons ?? [];
			},
			() => {
				if (this.#key !== key) return;
				this.seasons = null;
				this.#key = '';
			}
		);
	};

	/** Drops the list, for a panel handed another job. */
	reset = (): void => {
		this.seasons = [];
		this.#key = '';
	};
}
