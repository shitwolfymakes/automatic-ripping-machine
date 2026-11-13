// The Match episodes tab's match runs: a preview or an apply sent for
// the job on screen, the preview it left and the request behind it, and
// the error line of the last run.
import { matchIdentity, type EpisodeSource } from '$lib/api/identity';
import type { MatchPreview, MatchRequest } from '$lib/types/api.gen';
import { shortSourceLabel } from '$lib/episodes/sources';
import { errorMessage } from '$lib/utils/errors';

/** What a run needs from the panel. */
export interface MatchRunHost {
	/** The job the panel shows now; a run for another job is dropped. */
	jobId: () => string;
	/** The label of the source whose placement is on screen, or null. */
	placementLabel: () => string | null;
	/** Closes the Fix match form, once an apply has landed. */
	closeForm: () => void;
	/** Reloads what the panel shows, once an apply has been recorded. */
	reload: () => Promise<void>;
}

/** The error line of a run that failed: what the source said, and that
 * nothing changed, naming the placement still on screen. */
function matchErrorLine(label: string, error: unknown, placementLabel: string | null): string {
	const still = placementLabel
		? ` the placement below is still ${placementLabel}'s.`
		: ' the placement below is unchanged.';
	return `${label} didn't answer (${errorMessage(error, 'error')}). Nothing changed;${still}`;
}

export class MatchRunner {
	preview = $state<MatchPreview | null>(null);
	previewSource = $state<EpisodeSource | null>(null);
	busy = $state(false);
	/** The error line under the form. Clear episodes writes it too. */
	error = $state<string | null>(null);
	lastRequest = $state.raw<MatchRequest | null>(null);
	// The request that produced the preview on screen: Apply sends exactly it.
	// previewSeq invalidates a preview still in flight when the form changes.
	#previewRequest: MatchRequest | null = null;
	#previewSeq = 0;
	readonly #host: MatchRunHost;

	constructor(host: MatchRunHost) {
		this.#host = host;
	}

	/** Drops the preview on screen and any still in flight, and the error
	 * line. */
	drop = (): void => {
		this.#previewSeq++;
		this.#previewRequest = null;
		this.preview = null;
		this.previewSource = null;
		this.error = null;
	};

	/** Forgets every run, for a panel handed another job. */
	reset = (): void => {
		this.drop();
		this.lastRequest = null;
	};

	/** Sends a preview or an apply and keeps what it leaves. */
	run = async (req: MatchRequest): Promise<void> => {
		this.busy = true;
		this.error = null;
		this.lastRequest = req;
		const label = shortSourceLabel(req.source);
		const jobId = this.#host.jobId();
		const seq = ++this.#previewSeq;
		// A preview is stale once the form (or the job) changed while it ran.
		const stale = () => this.#host.jobId() !== jobId || (!req.apply && seq !== this.#previewSeq);
		try {
			const out = await matchIdentity(jobId, req);
			if (stale()) return;
			const failed = out.outcomes?.find((o) => o.status === 'error');
			if (failed) {
				// An apply records its source even when that source failed: reload
				// so the stored state shows, then report the failure.
				if (req.apply) {
					await this.#host.reload();
				}
				if (stale()) return;
				throw new Error(failed.detail ?? 'error');
			}
			await this.#keep(req, out);
		} catch (e) {
			if (stale()) return;
			this.error = matchErrorLine(label, e, this.#host.placementLabel());
		} finally {
			this.busy = false;
		}
	};

	/** Keeps what a run that landed leaves: an apply drops the preview,
	 * closes the form and reloads; a preview goes on screen. */
	#keep = async (req: MatchRequest, out: MatchPreview): Promise<void> => {
		if (req.apply) {
			this.drop();
			this.#host.closeForm();
			await this.#host.reload();
		} else {
			this.preview = out;
			this.previewSource = req.source ?? null;
			this.#previewRequest = req;
		}
	};

	/** Applies the request behind the preview on screen. */
	applyPreview = (): Promise<void> | undefined => {
		if (this.#previewRequest) return this.run({ ...this.#previewRequest, apply: true });
	};
}
