import type { TranscodeTaskView, TranscodeStatsView, TranscodeWorkerView } from '$lib/types/api.gen';
import { get, post, del, buildQuery } from './client';

// These are "transcodes" (the task model). Every endpoint returns the bare view or array, with no
// response wrapper; the exported names keep the older "transcoder job" naming, and ids are strings.

export function fetchTranscoderStats(): Promise<TranscodeStatsView> {
	return get<TranscodeStatsView>('/api/transcodes/stats');
}

// The bare worker array.
export function fetchTranscoderWorkers(): Promise<TranscodeWorkerView[]> {
	return get<TranscodeWorkerView[]>('/api/transcodes/workers');
}

// The bare task array.
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
