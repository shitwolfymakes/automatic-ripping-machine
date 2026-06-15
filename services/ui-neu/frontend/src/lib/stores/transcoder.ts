import { createPollingStore } from './polling';
import { fetchTranscoderStats, fetchTranscoderWorkers } from '$lib/api/transcoder';
import type { TranscodeStatsView, TranscodeWorkerView, TranscodeTaskView } from '$lib/types/api.gen';

// v3 stats are the bare TranscodeStatsView (no {online, stats} envelope); the
// poll store's `initialized`/`error` flags carry the online signal instead.
export const emptyStats: TranscodeStatsView = {
	tasks_by_status: {},
	total_tasks: 0,
	gpus_total: 0,
	gpus_available: 0,
	max_parallel: 0
};
// Was WorkersResponse { max_concurrent, active_count, workers }; v3 is a bare
// worker array.
export const emptyWorkers: TranscodeWorkerView[] = [];

/**
 * Singleton transcoder stores — they survive page navigations and retain their
 * last-known data, so returning to the Transcoder page renders the previous
 * stats/workers immediately instead of flashing the "offline" state and popping
 * in once the next poll resolves. Polling is still gated by the page via
 * start()/stop(); only the cached value persists between visits.
 */
export const transcoderStats = createPollingStore(fetchTranscoderStats, emptyStats, 5000);
export const transcoderWorkers = createPollingStore(fetchTranscoderWorkers, emptyWorkers, 5000);

// Last successful task list per tab, so navigating back (or to a
// previously-viewed tab) shows the cards immediately while we refresh in the
// background, rather than dropping to a skeleton each time.
let jobsCache: { tab: string; data: TranscodeTaskView[] } | null = null;

export function getJobsCache(tab: string): TranscodeTaskView[] | null {
	return jobsCache && jobsCache.tab === tab ? jobsCache.data : null;
}

export function setJobsCache(tab: string, data: TranscodeTaskView[]): void {
	jobsCache = { tab, data };
}
