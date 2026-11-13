// The match picker's fetched details, kept for the life of one result
// list, so going back to a row costs no second call.
import type { MetadataCandidate } from '$lib/types/api.gen';
import { fetchMatchDetails, type MatchProvider } from '$lib/api/jobs';
import { candidateKey, detailsId, isSeriesKind, mergeCandidate } from '$lib/utils/match';
import { errorMessage } from '$lib/utils/errors';

export class MatchDetailsCache {
	/** Fetched details by candidate key. */
	details = $state<Record<string, MetadataCandidate>>({});
	/** Why a row's details could not be fetched, by candidate key. */
	errors = $state<Record<string, string>>({});
	/** Rows whose details are being fetched, by candidate key. */
	loading = $state<Record<string, boolean>>({});
	// Bumped whenever the result list changes; a fetch started for an older list
	// must not write into the new list's state. Private and not $state: it is
	// never rendered.
	#generation = 0;

	/**
	 * Forgets every row, for a new result list. A fetch still running for the
	 * old list writes nothing.
	 */
	reset = (): void => {
		this.#generation++;
		this.details = {};
		this.errors = {};
		this.loading = {};
	};

	/**
	 * The row with its fetched details laid over it, or the row alone when none
	 * have been fetched.
	 */
	merged = (row: MetadataCandidate): MetadataCandidate => {
		const found = this.details[candidateKey(row)];
		return found ? mergeCandidate(row, found) : row;
	};

	/**
	 * Fetches the row's details, unless they are known or loading or the row has
	 * no provider id. Resolves to the details found, or null when none came or
	 * the list changed meanwhile.
	 */
	load = async (row: MetadataCandidate): Promise<MetadataCandidate | null> => {
		const key = candidateKey(row);
		const id = detailsId(row);
		if (!row.provider || !id || this.details[key] || this.loading[key]) return null;
		const gen = this.#generation;
		this.loading = { ...this.loading, [key]: true };
		const { [key]: _drop, ...rest } = this.errors;
		this.errors = rest;
		try {
			const resp = await fetchMatchDetails(row.provider as MatchProvider, isSeriesKind(row.kind) ? 'tv' : 'movie', id);
			if (gen !== this.#generation) return null;
			const found = resp.candidates[0];
			if (found) {
				this.details = { ...this.details, [key]: found };
				return found;
			}
			this.errors = { ...this.errors, [key]: resp.detail ?? 'No details found.' };
		} catch (e) {
			if (gen !== this.#generation) return null;
			this.errors = { ...this.errors, [key]: errorMessage(e, 'Could not load details') };
		} finally {
			if (gen === this.#generation) this.loading = { ...this.loading, [key]: false };
		}
		return null;
	};
}
