// A job's episode identity as the Match episodes tab shows it, with each
// track's output file name. A response for a job the panel no longer
// shows is dropped.
import { SvelteMap } from 'svelte/reactivity';
import { fetchIdentity } from '$lib/api/identity';
import { fetchNamingPreview } from '$lib/api/jobs';
import type { IdentityView } from '$lib/types/api.gen';
import { errorMessage } from '$lib/utils/errors';

export class EpisodeIdentity {
	identity = $state<IdentityView | null>(null);
	/** Each track's output file name and path, by track id. */
	fileNames = $state<Map<string, { name: string; path: string }>>(new SvelteMap());
	loadError = $state<string | null>(null);
	/** A load has finished, whether or not it failed. */
	loaded = $state(false);
	readonly #currentJobId: () => string;

	/** `currentJobId` names the job the panel shows now. */
	constructor(currentJobId: () => string) {
		this.#currentJobId = currentJobId;
	}

	/** Loads the job's identity, then its file names. A failed identity
	 * load keeps its message; a failed file-name load is ignored. */
	load = async (jobId: string): Promise<void> => {
		try {
			const next = await fetchIdentity(jobId);
			if (this.#currentJobId() !== jobId) return;
			this.identity = next;
			this.loadError = null;
		} catch (e) {
			if (this.#currentJobId() !== jobId) return;
			this.loadError = errorMessage(e, 'Could not load episodes');
		}
		this.loaded = true;
		try {
			const preview = await fetchNamingPreview(jobId);
			if (this.#currentJobId() !== jobId) return;
			this.fileNames = new SvelteMap(
				(preview.items ?? []).map((i) => [i.track_id, { name: i.output_name, path: i.output_path }])
			);
		} catch {
			/* file names are a nicety */
		}
	};

	/** Drops everything, for a panel handed another job. */
	reset = (): void => {
		this.identity = null;
		this.loaded = false;
		this.loadError = null;
		this.fileNames = new SvelteMap();
	};
}
