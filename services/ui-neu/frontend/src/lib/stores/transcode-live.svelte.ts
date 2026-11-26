// The latest progress sample the transcoder published for a task, and the
// subscription that keeps it current.
import { wsClient } from '$lib/api/ws';
import { liveSample, type TranscodeLiveSample } from '$lib/transcode/progress';

export class TranscodeLive {
	#sample = $state<TranscodeLiveSample | null>(null);

	/** Follows the task's progress topic; returns the unsubscribe. */
	follow = (taskId: string): (() => void) => {
		return wsClient.subscribe(`transcode.progress.${taskId}`, (env) => {
			this.#sample = liveSample(taskId, env.payload);
		});
	};

	/** The latest sample when it is for this task, else null. */
	sampleFor = (taskId: string | undefined): TranscodeLiveSample | null => {
		return this.#sample && this.#sample.taskId === taskId ? this.#sample : null;
	};
}
