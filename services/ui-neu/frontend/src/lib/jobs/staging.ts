// What the job page shows for a track's staging copy (raw to /staging): its
// words, whether it is moving, and the transcode wait it causes. Pure; the
// live bytes come from the job-live store.
import type { TrackStageView, TrackView } from '$lib/types/api.gen';
import { copyPercent, EMPTY_SAMPLE, type LiveSample } from '$lib/live/feeds';

type StageStatus = TrackStageView['status'];

const STATUS_WORDS: Record<StageStatus, string> = {
	pending: 'Waiting to stage',
	copying: 'Staging',
	stalled: 'Staging stalled',
	staged: 'Staged',
	failed: 'Staging failed'
};

/** The phase label for a stage's status. */
export function stageWords(stage: Pick<TrackStageView, 'status'>): string {
	return STATUS_WORDS[stage.status];
}

/** A stage still on its way to /staging: queued, copying or stalled (the stager re-queues or fails it). */
export function isStageActive(stage: Pick<TrackStageView, 'status'>): boolean {
	return stage.status === 'pending' || stage.status === 'copying' || stage.status === 'stalled';
}

/** Whether the job page gives the stage its own line: anything but a finished copy. */
export function showsStageLine(stage: Pick<TrackStageView, 'status'> | null | undefined): boolean {
	return stage != null && stage.status !== 'staged';
}

/** Whether the stage's live feed is worth following: bytes only move while copying. */
export function followsStageFeed(stage: Pick<TrackStageView, 'status'> | null | undefined): boolean {
	return stage?.status === 'copying';
}

/** A queued encode whose staged copy is not there yet: the dispatcher holds it, so the page says why. */
export function waitingForFiles(track: Pick<TrackView, 'transcode_status' | 'stage'>): boolean {
	return track.transcode_status === 'queued' && showsStageLine(track.stage);
}

/** The bytes durable at the last checkpoint, as the sample the progress line draws before any live report. */
export function stageSnapshot(stage: Pick<TrackStageView, 'bytes_durable' | 'source_size'>): LiveSample {
	const total = stage.source_size ?? null;
	return {
		...EMPTY_SAMPLE,
		pct: copyPercent(stage.bytes_durable, total),
		bytesDone: stage.bytes_durable,
		bytesTotal: total
	};
}

/** The sample the stage's progress line draws: the live report, else the checkpoint. */
export function stageProgressSample(
	stage: Pick<TrackStageView, 'bytes_durable' | 'source_size'>,
	live: LiveSample | null
): LiveSample {
	return live ?? stageSnapshot(stage);
}
