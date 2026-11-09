// A metadata search's progress flag and its error line, shared by the title
// searches; the caller owns the results.
import type { MetadataCandidate } from '$lib/types/api.gen';

export interface SearchMessages {
	/** Shown when the answer has no candidates. */
	empty: string;
	/** Shown when the request rejects with something that is not an Error. */
	failed: string;
}

/** The IMDb id lookup's two lines. */
export const IMDB_LOOKUP: SearchMessages = { empty: 'No match found for that IMDb ID.', failed: 'IMDb lookup failed' };

export class MetadataSearch {
	/** A request is in flight. */
	searching = $state(false);
	/** The line under the form: no match, or why the request failed. */
	error = $state<string | null>(null);

	/** Runs one request and returns its candidates, or none after a failure. */
	run = async (
		request: () => Promise<{ candidates: MetadataCandidate[] }>,
		messages: SearchMessages
	): Promise<MetadataCandidate[]> => {
		this.searching = true;
		this.error = null;
		try {
			const resp = await request();
			if (resp.candidates.length === 0) this.error = messages.empty;
			return resp.candidates;
		} catch (e) {
			this.error = e instanceof Error ? e.message : messages.failed;
			return [];
		} finally {
			this.searching = false;
		}
	};
}
