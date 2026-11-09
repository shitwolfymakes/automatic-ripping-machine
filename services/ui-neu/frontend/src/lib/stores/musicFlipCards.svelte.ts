// The music search's flipped result cards, each with its back-face tracklist:
// loading, fetched, or a fallback built from the card when the fetch fails.
import { fetchMusicDetail } from '$lib/api/jobs';
import type { MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';

export class MusicFlipCards {
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- never mutated; each change assigns a new Map, which triggers updates
	#cards = $state(new Map<string, MetadataReleaseDetail | 'loading'>());

	/** The card's back-face data, undefined when the card is not flipped. */
	get = (id: string): MetadataReleaseDetail | 'loading' | undefined => this.#cards.get(id);

	isFlipped = (id: string): boolean => this.#cards.has(id);

	/** Unflips every card. */
	clear = (): void => {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- never mutated; each change assigns a new Map, which triggers updates
		this.#cards = new Map();
	};

	/** Unflips the card, or flips it and loads its tracklist. */
	toggle = async (c: MetadataCandidate): Promise<void> => {
		if (!c.provider_id) return;
		const id = c.provider_id;
		if (this.isFlipped(id)) {
			this.#remove(id);
			return;
		}
		this.#set(id, 'loading');
		try {
			this.#set(id, await fetchMusicDetail(id));
		} catch {
			this.#set(id, fallbackDetail(c));
		}
	};

	readonly #set = (id: string, value: MetadataReleaseDetail | 'loading'): void => {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- copy-on-write; reassigning the $state field triggers updates
		this.#cards = new Map(this.#cards).set(id, value);
	};

	readonly #remove = (id: string): void => {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- copy-on-write; reassigning the $state field triggers updates
		const next = new Map(this.#cards);
		next.delete(id);
		this.#cards = next;
	};
}

// The back face shown when the tracklist fetch fails: the card's own facts and
// no tracks.
function fallbackDetail(c: MetadataCandidate): MetadataReleaseDetail {
	return {
		release_id: c.provider_id,
		title: c.title,
		artist: null,
		year: c.year ?? null,
		poster_url: c.poster_url ?? null,
		disc_count: null,
		track_count: c.track_count ?? null,
		catalog_number: null,
		barcode: null,
		status: null,
		tracks: []
	} as MetadataReleaseDetail;
}
