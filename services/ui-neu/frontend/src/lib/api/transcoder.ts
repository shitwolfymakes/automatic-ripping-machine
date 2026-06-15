import type { TranscodeTaskView, TranscodeStatsView, TranscodeWorkerView } from '$lib/types/api.gen';
import { get, post, del, buildQuery } from './client';
import { notAvailable } from './_stub';

// v3 calls these "transcodes" (the task model), not the BFF's "transcoder jobs".
// The BFF response wrappers (TranscoderJobListResponse / WorkersResponse /
// TranscoderStatsResponse) are gone — every endpoint returns the bare view or
// array now. Exported NAMES are kept stable; ids are strings in v3.

export function fetchTranscoderStats(): Promise<TranscodeStatsView> {
	return get<TranscodeStatsView>('/api/transcodes/stats');
}

// Was WorkersResponse { max_concurrent, active_count, workers }; v3 returns the
// bare worker array.
export function fetchTranscoderWorkers(): Promise<TranscodeWorkerView[]> {
	return get<TranscodeWorkerView[]>('/api/transcodes/workers');
}

// Was TranscoderJobListResponse { jobs, total }; v3 returns the bare task array.
export function fetchTranscoderJobs(params?: {
	status?: string;
	limit?: number;
	offset?: number;
}): Promise<TranscodeTaskView[]> {
	return get<TranscodeTaskView[]>(
		`/api/transcodes${buildQuery({
			status: params?.status || undefined,
			limit: params?.limit,
			offset: params?.offset
		})}`
	);
}

export function retryTranscoderJob(id: string): Promise<TranscodeTaskView> {
	return post<TranscodeTaskView>(`/api/transcodes/${id}/retry`);
}

export function deleteTranscoderJob(id: string): Promise<void> {
	return del(`/api/transcodes/${id}`);
}

// MISSING in v3 — there is no separate retranscode endpoint; v3 folds re-queue
// into retry. Screens guarded off / use retry instead.
export async function retranscodeTranscoderJob(_id: string): Promise<never> {
	notAvailable('Re-transcode job');
}

// MISSING in v3 — no handbrake-presets endpoint. The PresetEditor falls back to
// free-text, so the stub rejects loudly rather than silently returning {}.
export async function listHandbrakePresets(): Promise<never> {
	notAvailable('HandBrake presets');
}
