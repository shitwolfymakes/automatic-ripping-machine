// A transcode task's live progress: the sample the transcoder publishes
// on transcode.progress.{id}, and the ETA and frame rate the card shows
// from it or from the task row.
import type { TranscodeTaskView } from '$lib/types/api.gen';
import { etaTime } from '../jobs/status-format';
import { formatRemaining } from '../utils/format';
import { formatFps } from './fps';

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

/**
 * The ETA for an active task. The transcoder publishes the encoder's own
 * ETA, and that wins. Before the first sample (a card that mounts
 * mid-encode, a socket that is down) the task row carries the value from
 * the last REST heartbeat. As a last resort it is estimated from when the
 * task was claimed, never from created_at, which would count the time it
 * sat queued as encode time. Null when there is nothing to go on.
 */
export function etaLabel(
	task: Pick<TranscodeTaskView, 'eta_seconds' | 'started_at' | 'progress_pct'>,
	live: TranscodeLiveSample | null
): string | null {
	const eta = live?.eta ?? task.eta_seconds;
	if (typeof eta === 'number') return formatRemaining(eta);
	return task.started_at ? etaTime(task.started_at, task.progress_pct) : null;
}

/**
 * The frame rate for an active task: the sample's when it has one, else
 * the task row's from the last REST heartbeat.
 */
export function fpsLabel(
	task: Pick<TranscodeTaskView, 'fps' | 'avg_fps'>,
	live: TranscodeLiveSample | null
): string | null {
	return live?.fps != null ? formatFps(live.fps, live.avgFps) : formatFps(task.fps, task.avg_fps);
}
