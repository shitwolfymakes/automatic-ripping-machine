// The transcoder page's task actions: retry and delete, and the feedback
// banner's error.
import { retryTranscoderJob, deleteTranscoderJob } from '$lib/api/transcoder';
import { errorMessage } from '$lib/utils/errors';

export class TranscodeTaskActions {
	#reload: () => unknown;

	error = $state<string | null>(null);

	constructor(reload: () => unknown) {
		this.#reload = reload;
	}

	// A failed action (409 retry of a task no longer failed, 503 delete with
	// the dispatcher down, a network error) shows in the feedback banner, and
	// the list refreshes either way since the failure usually means it is stale.
	#run = async (action: () => Promise<unknown>, verb: string): Promise<void> => {
		this.error = null;
		try {
			await action();
		} catch (e) {
			this.error = errorMessage(e, `${verb} failed`);
		}
		this.#reload();
	};

	retry = (id: string): Promise<void> => {
		return this.#run(() => retryTranscoderJob(id), 'Retry');
	};

	remove = (id: string): Promise<void> | undefined => {
		if (!confirm('Delete this transcode task?')) return;
		return this.#run(() => deleteTranscoderJob(id), 'Delete');
	};

	dismiss = (): void => {
		this.error = null;
	};
}
