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
	try {
		localStorage.setItem(`arm:tc-jobs-count:${tab}`, String(data.length));
	} catch {
		// storage unavailable (private mode, SSR) — skeleton falls back to default
	}
}

// Last-known card count per tab, persisted across full page reloads. Sizes the
// loading skeleton to match what's about to render so the fill-in doesn't
// reflow the page. Clamped so a huge history can't paint a wall of skeletons.
export function getLastJobsCount(tab: string, fallback = 3): number {
	try {
		const raw = localStorage.getItem(`arm:tc-jobs-count:${tab}`);
		if (raw == null) return fallback;
		const n = parseInt(raw, 10);
		if (isNaN(n)) return fallback;
		return Math.min(8, Math.max(1, n));
	} catch {
		return fallback;
	}
}
