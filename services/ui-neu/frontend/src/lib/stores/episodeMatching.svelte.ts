// Shared by the job page and the Home review card: the "Matching episodes…"
// state while the Backend re-matches episodes after a series apply or a type
// flip, and the ripper-event feed that ends it.
import { startRipperEvents, onRipperEvent } from './ripperEvents.svelte';

/** Fallback so the matching state never sticks when no event arrives. */
export const MATCHING_TIMEOUT_MS = 60_000;

export class EpisodeMatching {
	active = $state(false);
	#timer: ReturnType<typeof setTimeout> | null = null;

	start(): void {
		this.active = true;
		if (this.#timer) clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.stop(), MATCHING_TIMEOUT_MS);
	}

	stop(): void {
		this.active = false;
		if (this.#timer) clearTimeout(this.#timer);
		this.#timer = null;
	}
}

/**
 * Calls `handler` for each debounced ripper/transcode event burst that names
 * the job `jobId()` returns. `identityUpdated` is true when the burst carried
 * job.identity_updated, which is what ends matching (rip.identify_resolved
 * fires before the episode stage has run). Returns the unsubscribe.
 */
export function onJobEvents(
	jobId: () => string | null | undefined,
	handler: (identityUpdated: boolean) => void
): () => void {
	startRipperEvents();
	return onRipperEvent((jobIds, eventTypes) => {
		const id = jobId();
		if (!id || !jobIds.has(id)) return;
		handler(eventTypes.get(id)?.has('job.identity_updated') ?? false);
	});
}
