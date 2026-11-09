// A transcode task's live progress: the sample the transcoder publishes
// on transcode.progress.{id}.

/** One progress sample for a task; each value is null when not a number. */
export interface TranscodeLiveSample {
	taskId: string;
	eta: number | null;
	fps: number | null;
	avgFps: number | null;
}

/** The sample a progress payload carries for the task. */
export function liveSample(taskId: string, payload: Record<string, unknown>): TranscodeLiveSample {
	const { eta_seconds, fps, avg_fps } = payload;
	return {
		taskId,
		eta: typeof eta_seconds === 'number' ? eta_seconds : null,
		fps: typeof fps === 'number' ? fps : null,
		avgFps: typeof avg_fps === 'number' ? avg_fps : null
	};
}
