// Shared by the job page and the Home review card: the "Matching episodes…"
// state while the Backend re-matches episodes after a series apply or a type
// flip, and the ripper-event feed that ends it.
import { startRipperEvents, onRipperEvent } from './ripperEvents.svelte';

/** Fallback so the matching state never sticks when no event arrives. */
export const MATCHING_TIMEOUT_MS = 60_000;

/**
 * start() runs once the apply request returns, and the Backend's
 * job.identity_updated burst can land before that. An update seen this
 * recently means the match already finished, so start() stays off.
 */
export const RECENT_UPDATE_MS = 5_000;

export class EpisodeMatching {
	active = $state(false);
	#timer: ReturnType<typeof setTimeout> | null = null;
	#lastUpdate = 0;

	start(): void {
		if (Date.now() - this.#lastUpdate < RECENT_UPDATE_MS) return;
		this.active = true;
		if (this.#timer) clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.stop(), MATCHING_TIMEOUT_MS);
	}

	stop(): void {
		this.active = false;
		if (this.#timer) clearTimeout(this.#timer);
		this.#timer = null;
	}

	/** Records a job.identity_updated burst, so a start() that follows it stays off. */
	noteIdentityUpdated(): void {
		this.#lastUpdate = Date.now();
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

/**
 * The job page's and the review card's event wiring: each burst for the job
 * runs `reload` (the job, then the episode panel), and a burst carrying
 * job.identity_updated ends `matching` once that reload has the new counts.
 * Returns the unsubscribe.
 */
export function watchEpisodeMatching(
	jobId: () => string | null | undefined,
	matching: EpisodeMatching,
	reload: () => Promise<void>
): () => void {
	return onJobEvents(jobId, (identityUpdated) => {
		if (identityUpdated) matching.noteIdentityUpdated();
		reload().then(() => {
			if (identityUpdated) matching.stop();
		});
	});
}
