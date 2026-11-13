// A metadata search's progress flag and its error line, shared by the title
// searches; the caller owns the results.
import type { MetadataCandidate } from '$lib/types/api.gen';
import { errorMessage } from '$lib/utils/errors';

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

	/**
	 * Runs one request. On success, hands its candidates to `onfound` (even
	 * when there are none) before setting the no-match line; after a failure,
	 * sets the failure line and leaves the caller's results alone.
	 */
	run = async (
		request: () => Promise<{ candidates: MetadataCandidate[] }>,
		messages: SearchMessages,
		onfound: (candidates: MetadataCandidate[]) => void
	): Promise<void> => {
		this.searching = true;
		this.error = null;
		try {
			const resp = await request();
			onfound(resp.candidates);
			if (resp.candidates.length === 0) this.error = messages.empty;
		} catch (e) {
			this.error = errorMessage(e, messages.failed);
		} finally {
			this.searching = false;
		}
	};
}
